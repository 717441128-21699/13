import os
from datetime import date, datetime, timedelta
from collections import defaultdict

import pandas as pd

from database import get_session
from models import (
    InventoryDifference, WorkOrder, StockCheckTask, MonthlyStats, Warehouse
)
from config import REPORT_DIR, EXPORT_DIR
from logger import setup_logger

logger = setup_logger('mr', 'monthly')


def _mk(d):
    return f"{d.year}-{d.month:02d}"


def _last_n(n, from_date=None):
    d = from_date or date.today()
    out = []
    y, m = d.year, d.month
    for _ in range(n):
        m -= 1
        if m == 0:
            m = 12
            y -= 1
        out.append(f"{y}-{m:02d}")
    return list(reversed(out))


def generate_monthly_stats(stat_month=None):
    if not stat_month:
        today = date.today()
        last = today.replace(day=1) - timedelta(days=1)
        stat_month = _mk(last)

    y, m = map(int, stat_month.split('-'))
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    sd = date(y, m, 1)
    ed = date(ny, nm, 1) - timedelta(days=1)

    with get_session() as session:
        whs = [w.code for w in session.query(Warehouse).all()] or ['WH001', 'WH002', 'WH003']
        diffs = session.query(InventoryDifference).filter(
            InventoryDifference.check_date >= sd,
            InventoryDifference.check_date <= ed
        ).all()
        orders = session.query(WorkOrder).filter(
            WorkOrder.created_at >= datetime(y, m, 1),
            WorkOrder.created_at < datetime(ny, nm, 1)
        ).all()
        tasks = session.query(StockCheckTask).filter(
            StockCheckTask.created_at >= datetime(y, m, 1),
            StockCheckTask.created_at < datetime(ny, nm, 1)
        ).all()

    data = defaultdict(lambda: {'items': 0, 'checked': 0, 'diff': 0,
                                 'resolved': 0, 'hours': [], 'amount': 0.0})
    for d in diffs:
        wd = data[d.warehouse_code]
        wd['items'] += 1
        wd['checked'] += 1
        if d.diff_qty != 0:
            wd['diff'] += 1
        if d.status in ('resolved', 'ledger_updated', 'completed'):
            wd['resolved'] += 1
        wd['amount'] += float(d.diff_amount or 0)
    for o in orders:
        if o.assigned_at and o.completed_at:
            data[o.warehouse_code]['hours'].append(
                (o.completed_at - o.assigned_at).total_seconds() / 3600
            )
    for t in tasks:
        data[t.warehouse_code]['checked'] += len(t.items)

    results = []
    with get_session() as session:
        for wh in set(list(data.keys()) + whs):
            wd = data[wh]
            cr = wd['checked'] / wd['items'] * 100 if wd['items'] > 0 else 0.0
            rr = wd['resolved'] / wd['diff'] * 100 if wd['diff'] > 0 else 0.0
            ah = sum(wd['hours']) / len(wd['hours']) if wd['hours'] else 0.0
            exist = session.query(MonthlyStats).filter(
                MonthlyStats.stat_month == stat_month,
                MonthlyStats.warehouse_code == wh
            ).first()
            if exist:
                exist.total_items = wd['items']
                exist.checked_items = wd['checked']
                exist.completion_rate = cr
                exist.diff_items = wd['diff']
                exist.resolved_items = wd['resolved']
                exist.resolution_rate = rr
                exist.avg_process_hours = ah
                exist.total_diff_amount = wd['amount']
            else:
                session.add(MonthlyStats(
                    stat_month=stat_month, warehouse_code=wh,
                    total_items=wd['items'], checked_items=wd['checked'],
                    completion_rate=cr, diff_items=wd['diff'],
                    resolved_items=wd['resolved'], resolution_rate=rr,
                    avg_process_hours=ah, total_diff_amount=wd['amount']
                ))
            results.append({
                'stat_month': stat_month, 'warehouse': wh,
                'total_items': wd['items'], 'checked_items': wd['checked'],
                'completion_rate': round(cr, 2), 'diff_items': wd['diff'],
                'resolved_items': wd['resolved'], 'resolution_rate': round(rr, 2),
                'avg_process_hours': round(ah, 2),
                'total_diff_amount': round(wd['amount'], 2)
            })
    logger.info(f"月度统计 {stat_month}: {len(results)} 仓库")
    return results


def generate_monthly_report(stat_month=None):
    if not stat_month:
        today = date.today()
        last = today.replace(day=1) - timedelta(days=1)
        stat_month = _mk(last)

    stats = generate_monthly_stats(stat_month)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    os.makedirs(EXPORT_DIR, exist_ok=True)
    os.makedirs(REPORT_DIR, exist_ok=True)

    excel = os.path.join(EXPORT_DIR, f'monthly_{stat_month}_{ts}.xlsx')
    with pd.ExcelWriter(excel, engine='openpyxl') as writer:
        pd.DataFrame(stats).to_excel(writer, sheet_name='月度统计', index=False)
        with get_session() as session:
            trend = []
            all_s = session.query(MonthlyStats).all()
            for s in all_s:
                trend.append({'月份': s.stat_month, '仓库': s.warehouse_code,
                              '完成率(%)': round(float(s.completion_rate), 2),
                              '解决率(%)': round(float(s.resolution_rate), 2),
                              '平均处理(小时)': round(float(s.avg_process_hours), 2),
                              '差异金额': round(float(s.total_diff_amount), 2)})
            pd.DataFrame(trend).to_excel(writer, sheet_name='趋势数据', index=False)

    pdf = os.path.join(REPORT_DIR, f'monthly_{stat_month}_{ts}.txt')
    with open(pdf, 'w', encoding='utf-8') as f:
        f.write(f"月度库存盘点报告 - {stat_month}\n")
        f.write(f"生成时间: {datetime.now()}\n\n")
        for s in stats:
            f.write(f"仓库 {s['warehouse']}: 完成率 {s['completion_rate']}%, "
                    f"解决率 {s['resolution_rate']}%, 平均处理 {s['avg_process_hours']}h, "
                    f"差异金额 {s['total_diff_amount']}\n")

    logger.info(f"月度报告: Excel={excel}, PDF(TXT)={pdf}")
    return {'excel': excel, 'pdf': pdf}
