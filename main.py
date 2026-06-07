import os
import sys
import random
import argparse
from datetime import datetime, date

from database import init_db
from logger import setup_logger

logger = setup_logger('main', 'main')


def cmd_daily(args):
    from inventory_compare import compare_inventory
    from work_order_manager import create_work_orders, check_and_upgrade_orders
    from ledger_manager import update_ledger_from_work_order
    from special_audit import check_special_audit
    from report_generator import generate_diff_report_excel, generate_diff_report_pdf

    check_date = None
    if args.date:
        from datetime import datetime as dt
        check_date = dt.strptime(args.date, '%Y-%m-%d').date()

    logger.info("=" * 60)
    logger.info("执行每日库存盘点流程")
    logger.info("=" * 60)

    result = compare_inventory(check_date)
    print(f"[1/6] 库存比对完成: {result}")

    orders = create_work_orders(check_date)
    print(f"[2/6] 工单生成完成: {len(orders)} 个工单")

    upgraded = check_and_upgrade_orders()
    print(f"[3/6] 超期工单升级检查: {len(upgraded)} 个升级")

    from work_order_manager import get_pending_orders
    pending = get_pending_orders()
    for o in pending[:3]:
        try:
            from work_order_manager import review_work_order
            review_work_order(o['order_no'], approved=True, comment='自动审核通过', operator='auto_test')
            update_ledger_from_work_order(o['order_no'], operator='auto_test')
        except Exception as e:
            logger.warning(f"自动审核工单 {o['order_no']} 失败: {e}")
    print(f"[4/6] 自动审核/台账更新完成")

    audits = check_special_audit()
    print(f"[5/6] 专项审计检查: {len(audits)} 项触发")

    excel_path = generate_diff_report_excel(check_date)
    pdf_path = generate_diff_report_pdf(check_date)
    print(f"[6/6] 报告生成:")
    print(f"       Excel: {excel_path}")
    print(f"       PDF:   {pdf_path}")


def cmd_monthly(args):
    from monthly_reporter import generate_monthly_report

    stat_month = args.month
    logger.info(f"生成 {stat_month or '上月'} 月度报告")

    result = generate_monthly_report(stat_month)
    if 'excel' in result:
        print(f"Excel报告: {result['excel']}")
    if 'pdf' in result:
        print(f"PDF报告:   {result['pdf']}")


def cmd_stock_check(args):
    from stock_check import (
        create_stock_check_task, push_task_to_terminal,
        scan_item, complete_stock_check_task, get_task_checklist
    )
    from report_generator import generate_stock_check_report

    if args.action == 'create':
        result = create_stock_check_task(
            task_type=args.type,
            warehouse_code=args.warehouse,
            category=args.category,
            sample_ratio=args.ratio,
            operator=args.operator or 'cli'
        )
        print(f"盘点任务创建成功: {result}")

    elif args.action == 'push':
        payload = push_task_to_terminal(args.task_no)
        print(f"任务已推送至手持终端，条目数: {payload['total_items']}")

    elif args.action == 'scan':
        from stock_check import get_task_checklist
        task = get_task_checklist(args.task_no)
        items = [i for i in task['items'] if not i['is_scanned']]
        if not items:
            print("无待扫描条目")
            return
        for item in items[:args.count]:
            scanned = item['system_qty'] + (0 if random.random() < 0.7 else random.randint(-5, 5))
            scan_item(args.task_no, item['id'], scanned, scanner=args.operator or 'cli')
        print(f"已模拟扫描 {min(args.count, len(items))} 条")

    elif args.action == 'complete':
        result = complete_stock_check_task(args.task_no, operator=args.operator or 'cli')
        print(f"任务完成: {result['task_no']}, 差异: {result['summary']['diff']}")
        report = generate_stock_check_report(args.task_no)
        if 'excel' in report:
            print(f"盘点Excel报告: {report['excel']}")
        if 'pdf' in report:
            print(f"盘点PDF报告:   {report['pdf']}")

    elif args.action == 'report':
        report = generate_stock_check_report(args.task_no)
        if 'excel' in report:
            print(f"Excel报告: {report['excel']}")
        if 'pdf' in report:
            print(f"PDF报告:   {report['pdf']}")

    elif args.action == 'list':
        task = get_task_checklist(args.task_no)
        print(f"任务: {task['task_no']} | 仓库: {task['warehouse']} | 状态: {task['status']}")
        for item in task['items'][:10]:
            status = f"已扫 {item['scanned_qty']}" if item['is_scanned'] else '未扫'
            print(f"  {item['sku']}: 系统={item['system_qty']}, {status}")


def cmd_query(args):
    from query_export import (
        query_differences, query_work_orders, query_operation_logs,
        export_differences_batch, export_operation_logs, get_dashboard_stats
    )

    if args.type == 'dashboard':
        stats = get_dashboard_stats()
        print("===== 仪表板统计 =====")
        print(f"今日差异: {stats['today']['total']} (盘盈{stats['today']['surplus']} 盘亏{stats['today']['deficit']})")
        print(f"超阈值: {stats['today']['over_threshold']}, 差异金额: {stats['today']['diff_amount']:.2f}")
        print(f"待处理工单: {stats['pending']['work_orders']} (已升级{stats['pending']['upgraded_orders']})")
        print(f"待处理审计: {stats['pending']['special_audits']}, 盘点中任务: {stats['pending']['stock_tasks']}")

    elif args.type == 'diff':
        diffs = query_differences(
            warehouse_code=args.warehouse,
            category=args.category,
            start_date=args.start_date,
            end_date=args.end_date,
            limit=args.limit
        )
        print(f"查询到 {len(diffs)} 条差异:")
        for d in diffs[:20]:
            print(f"  {d['check_date']} {d['warehouse']} {d['sku']} {d['diff_type']} "
                  f"数量={d['diff_qty']:+} 金额={d['diff_amount']:.2f} {d['status']}")

    elif args.type == 'order':
        orders = query_work_orders(
            warehouse_code=args.warehouse,
            status=args.status
        )
        print(f"查询到 {len(orders)} 个工单:")
        for o in orders[:20]:
            print(f"  {o['order_no']} {o['warehouse']} {o['category'] or '-'} "
                  f"{o['diff_type']} 审核人={o['auditor']} {o['status']}")

    elif args.type == 'log':
        logs = query_operation_logs(
            warehouse_code=args.warehouse,
            operation_type=args.op_type,
            limit=args.limit
        )
        print(f"查询到 {len(logs)} 条日志:")
        for l in logs[:20]:
            print(f"  {l['log_time']} {l['operation_type']} {l['operator'] or '-'} "
                  f"{l['warehouse'] or '-'} {l['detail'][:50]}")

    elif args.type == 'export_diff':
        result = export_differences_batch(
            warehouse_codes=args.warehouse.split(',') if args.warehouse else None,
            categories=args.category.split(',') if args.category else None,
            start_date=args.start_date,
            end_date=args.end_date
        )
        print(f"差异导出完成: {result['file']} ({result['count']} 条)")

    elif args.type == 'export_log':
        result = export_operation_logs(
            warehouse_code=args.warehouse,
            start_time=args.start_date,
            end_time=args.end_date
        )
        print(f"日志导出完成: {result['file']} ({result['count']} 条)")


def cmd_audit(args):
    from special_audit import check_special_audit, get_pending_audits, complete_special_audit

    if args.action == 'check':
        audits = check_special_audit()
        print(f"触发 {len(audits)} 项专项审计:")
        for a in audits:
            print(f"  {a}")

    elif args.action == 'list':
        audits = get_pending_audits()
        print(f"待处理审计 {len(audits)} 项:")
        for a in audits:
            print(f"  {a['audit_no']} {a['warehouse']} {a['category']} "
                  f"连续{a['consecutive']}月 差异率{a['avg_diff_rate']}%")

    elif args.action == 'complete':
        complete_special_audit(args.audit_no, args.report or '审计完成，未见异常', args.operator or 'cli')
        print(f"审计 {args.audit_no} 已完成")


def cmd_seed(args):
    from sample_data import seed_sample_data, seed_historical_data
    init_db()
    seed_sample_data()
    if args.historical:
        seed_historical_data()
    print("示例数据生成完成")


def cmd_scheduler(args):
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger
    from config import (
        SCHEDULE_DAILY_HOUR, SCHEDULE_DAILY_MINUTE,
        SCHEDULE_MONTHLY_DAY, SCHEDULE_MONTHLY_HOUR, SCHEDULE_MONTHLY_MINUTE
    )

    def daily_job():
        from inventory_compare import compare_inventory
        from work_order_manager import create_work_orders, check_and_upgrade_orders
        from special_audit import check_special_audit
        from report_generator import generate_diff_report_excel, generate_diff_report_pdf

        logger.info("[调度] 开始每日任务")
        try:
            compare_inventory()
            create_work_orders()
            check_and_upgrade_orders()
            check_special_audit()
            generate_diff_report_excel()
            generate_diff_report_pdf()
            logger.info("[调度] 每日任务完成")
        except Exception as e:
            logger.error(f"[调度] 每日任务失败: {e}")

    def monthly_job():
        from monthly_reporter import generate_monthly_report
        logger.info("[调度] 开始月度任务")
        try:
            generate_monthly_report()
            logger.info("[调度] 月度任务完成")
        except Exception as e:
            logger.error(f"[调度] 月度任务失败: {e}")

    scheduler = BlockingScheduler(timezone='Asia/Shanghai')
    scheduler.add_job(
        daily_job,
        CronTrigger(hour=SCHEDULE_DAILY_HOUR, minute=SCHEDULE_DAILY_MINUTE),
        id='daily_inventory',
        name='每日库存盘点'
    )
    scheduler.add_job(
        monthly_job,
        CronTrigger(day=SCHEDULE_MONTHLY_DAY, hour=SCHEDULE_MONTHLY_HOUR, minute=SCHEDULE_MONTHLY_MINUTE),
        id='monthly_report',
        name='月度统计报告'
    )

    print(f"调度器启动:")
    print(f"  每日任务: 每天 {SCHEDULE_DAILY_HOUR:02d}:{SCHEDULE_DAILY_MINUTE:02d}")
    print(f"  月度任务: 每月 {SCHEDULE_MONTHLY_DAY}日 {SCHEDULE_MONTHLY_HOUR:02d}:{SCHEDULE_MONTHLY_MINUTE:02d}")
    print("按 Ctrl+C 停止")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("调度器已停止")


def main():
    parser = argparse.ArgumentParser(description='企业级库存盘点与差异自动化管理系统')
    subparsers = parser.add_subparsers(dest='command', help='命令')

    p_seed = subparsers.add_parser('seed', help='生成示例数据')
    p_seed.add_argument('--historical', action='store_true', help='同时生成历史数据')
    p_seed.set_defaults(func=cmd_seed)

    p_daily = subparsers.add_parser('daily', help='执行每日库存盘点流程')
    p_daily.add_argument('--date', help='指定盘点日期 YYYY-MM-DD')
    p_daily.set_defaults(func=cmd_daily)

    p_monthly = subparsers.add_parser('monthly', help='生成月度统计报告')
    p_monthly.add_argument('--month', help='指定月份 YYYY-MM')
    p_monthly.set_defaults(func=cmd_monthly)

    p_sc = subparsers.add_parser('stock-check', help='手动盘点任务管理')
    p_sc.add_argument('action', choices=['create', 'push', 'scan', 'complete', 'report', 'list'])
    p_sc.add_argument('--task-no', help='任务编号')
    p_sc.add_argument('--type', choices=['full', 'sample'], default='full')
    p_sc.add_argument('--warehouse', default='WH001')
    p_sc.add_argument('--category', default=None)
    p_sc.add_argument('--ratio', type=float, default=0.3)
    p_sc.add_argument('--count', type=int, default=10)
    p_sc.add_argument('--operator', default=None)
    p_sc.set_defaults(func=cmd_stock_check)

    p_q = subparsers.add_parser('query', help='查询与导出')
    p_q.add_argument('type', choices=['dashboard', 'diff', 'order', 'log', 'export_diff', 'export_log'])
    p_q.add_argument('--warehouse', default=None)
    p_q.add_argument('--category', default=None)
    p_q.add_argument('--status', default=None)
    p_q.add_argument('--op-type', default=None)
    p_q.add_argument('--start-date', default=None)
    p_q.add_argument('--end-date', default=None)
    p_q.add_argument('--limit', type=int, default=50)
    p_q.set_defaults(func=cmd_query)

    p_audit = subparsers.add_parser('audit', help='专项审计管理')
    p_audit.add_argument('action', choices=['check', 'list', 'complete'])
    p_audit.add_argument('--audit-no', help='审计编号')
    p_audit.add_argument('--report', default=None)
    p_audit.add_argument('--operator', default=None)
    p_audit.set_defaults(func=cmd_audit)

    p_sched = subparsers.add_parser('scheduler', help='启动定时调度服务')
    p_sched.set_defaults(func=cmd_scheduler)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    init_db()
    args.func(args)


if __name__ == '__main__':
    main()
