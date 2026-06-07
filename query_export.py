import os
from datetime import datetime, date
from collections import defaultdict

import pandas as pd

from database import get_session
from models import (
    OperationLog, InventoryDifference, WorkOrder, InventoryLedger,
    SpecialAudit, StockCheckTask
)
from config import EXPORT_DIR
from logger import setup_logger

logger = setup_logger('query_export', 'query_export')


def _ensure_dir(d):
    os.makedirs(d, exist_ok=True)
    return d


def query_operation_logs(warehouse_code=None, category=None, start_time=None,
                         end_time=None, operation_type=None, operator=None,
                         sku=None, reference_no=None, limit=1000):
    with get_session() as session:
        q = session.query(OperationLog)
        if warehouse_code:
            q = q.filter(OperationLog.warehouse_code == warehouse_code)
        if category:
            q = q.filter(OperationLog.category == category)
        if sku:
            q = q.filter(OperationLog.sku == sku)
        if reference_no:
            q = q.filter(OperationLog.reference_no == reference_no)
        if operation_type:
            q = q.filter(OperationLog.operation_type == operation_type)
        if operator:
            q = q.filter(OperationLog.operator == operator)
        if start_time:
            if isinstance(start_time, str):
                start_time = datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S')
            q = q.filter(OperationLog.log_time >= start_time)
        if end_time:
            if isinstance(end_time, str):
                end_time = datetime.strptime(end_time, '%Y-%m-%d %H:%M:%S')
            q = q.filter(OperationLog.log_time <= end_time)

        q = q.order_by(OperationLog.log_time.desc())
        if limit:
            q = q.limit(limit)
        logs = q.all()

        return [{
            'log_time': l.log_time.strftime('%Y-%m-%d %H:%M:%S'),
            'operation_type': l.operation_type,
            'operator': l.operator or '',
            'warehouse': l.warehouse_code or '',
            'category': l.category or '',
            'sku': l.sku or '',
            'reference_no': l.reference_no or '',
            'detail': l.detail or '',
            'ip_address': l.ip_address or ''
        } for l in logs]


def query_differences(warehouse_code=None, category=None, start_date=None,
                      end_date=None, diff_type=None, is_over_threshold=None,
                      status=None, sku=None, limit=5000):
    with get_session() as session:
        q = session.query(InventoryDifference)
        if warehouse_code:
            q = q.filter(InventoryDifference.warehouse_code == warehouse_code)
        if category:
            q = q.filter(InventoryDifference.category == category)
        if sku:
            q = q.filter(InventoryDifference.sku == sku)
        if diff_type:
            q = q.filter(InventoryDifference.diff_type == diff_type)
        if is_over_threshold is not None:
            q = q.filter(InventoryDifference.is_over_threshold == is_over_threshold)
        if status:
            q = q.filter(InventoryDifference.status == status)
        if start_date:
            if isinstance(start_date, str):
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            q = q.filter(InventoryDifference.check_date >= start_date)
        if end_date:
            if isinstance(end_date, str):
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            q = q.filter(InventoryDifference.check_date <= end_date)

        q = q.order_by(InventoryDifference.check_date.desc())
        if limit:
            q = q.limit(limit)
        diffs = q.all()

        return [{
            'check_date': str(d.check_date),
            'warehouse': d.warehouse_code,
            'sku': d.sku,
            'product_name': d.product_name,
            'category': d.category or '',
            'realtime_qty': d.realtime_qty,
            'erp_qty': d.erp_qty,
            'diff_qty': d.diff_qty,
            'diff_type': d.diff_type,
            'unit_price': d.unit_price,
            'diff_amount': d.diff_amount,
            'diff_rate': round(d.diff_rate * 100, 2),
            'is_over_threshold': '是' if d.is_over_threshold else '否',
            'status': d.status,
            'work_order_id': d.work_order_id or ''
        } for d in diffs]


def query_work_orders(warehouse_code=None, status=None, is_upgraded=None,
                      start_date=None, end_date=None, auditor=None):
    with get_session() as session:
        q = session.query(WorkOrder)
        if warehouse_code:
            q = q.filter(WorkOrder.warehouse_code == warehouse_code)
        if status:
            q = q.filter(WorkOrder.status == status)
        if is_upgraded is not None:
            q = q.filter(WorkOrder.is_upgraded == is_upgraded)
        if auditor:
            q = q.filter(WorkOrder.auditor == auditor)
        if start_date:
            if isinstance(start_date, str):
                start_date = datetime.strptime(start_date, '%Y-%m-%d')
            q = q.filter(WorkOrder.created_at >= start_date)
        if end_date:
            if isinstance(end_date, str):
                end_date = datetime.strptime(end_date, '%Y-%m-%d') + pd.Timedelta(days=1)
            q = q.filter(WorkOrder.created_at <= end_date)

        q = q.order_by(WorkOrder.created_at.desc())
        orders = q.all()

        return [{
            'order_no': o.order_no,
            'warehouse': o.warehouse_code,
            'category': o.category or '',
            'diff_type': o.diff_type,
            'auditor': o.auditor,
            'supervisor': o.supervisor,
            'status': o.status,
            'priority': o.priority,
            'is_upgraded': '是' if o.is_upgraded else '否',
            'created_at': o.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'assigned_at': o.assigned_at.strftime('%Y-%m-%d %H:%M:%S') if o.assigned_at else '',
            'completed_at': o.completed_at.strftime('%Y-%m-%d %H:%M:%S') if o.completed_at else '',
            'diff_count': len(o.differences)
        } for o in orders]


def export_differences_batch(warehouse_codes=None, categories=None,
                             start_date=None, end_date=None, output_path=None):
    logger.info(f"批量导出差异明细: 仓库={warehouse_codes}, 品类={categories}")
    _ensure_dir(EXPORT_DIR)

    if not output_path:
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = os.path.join(EXPORT_DIR, f'diff_export_{ts}.xlsx')

    with get_session() as session:
        q = session.query(InventoryDifference)
        if warehouse_codes:
            q = q.filter(InventoryDifference.warehouse_code.in_(warehouse_codes))
        if categories:
            q = q.filter(InventoryDifference.category.in_(categories))
        if start_date:
            if isinstance(start_date, str):
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            q = q.filter(InventoryDifference.check_date >= start_date)
        if end_date:
            if isinstance(end_date, str):
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            q = q.filter(InventoryDifference.check_date <= end_date)

        diffs = q.order_by(InventoryDifference.check_date.desc()).all()

    data = []
    for d in diffs:
        data.append({
            '盘点日期': str(d.check_date),
            '仓库': d.warehouse_code,
            'SKU': d.sku,
            '商品名称': d.product_name,
            '品类': d.category or '',
            '实时库存': d.realtime_qty,
            'ERP账面': d.erp_qty,
            '差异数量': d.diff_qty,
            '差异类型': d.diff_type,
            '单价': d.unit_price,
            '差异金额': d.diff_amount,
            '差异率(%)': round(d.diff_rate * 100, 2),
            '超阈值': '是' if d.is_over_threshold else '否',
            '状态': d.status
        })

    pd.DataFrame(data).to_excel(output_path, index=False)
    logger.info(f"批量导出完成: {len(data)} 条 -> {output_path}")
    return {'file': output_path, 'count': len(data)}


def export_operation_logs(warehouse_code=None, category=None, start_time=None,
                          end_time=None, output_path=None):
    logger.info(f"导出操作日志")
    _ensure_dir(EXPORT_DIR)

    if not output_path:
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = os.path.join(EXPORT_DIR, f'op_logs_{ts}.xlsx')

    logs = query_operation_logs(
        warehouse_code=warehouse_code, category=category,
        start_time=start_time, end_time=end_time, limit=None
    )

    df_data = []
    for l in logs:
        df_data.append({
            '时间': l['log_time'],
            '操作类型': l['operation_type'],
            '操作人': l['operator'],
            '仓库': l['warehouse'],
            '品类': l['category'],
            'SKU': l['sku'],
            '关联单号': l['reference_no'],
            '详情': l['detail'],
            'IP': l['ip_address']
        })

    pd.DataFrame(df_data).to_excel(output_path, index=False)
    logger.info(f"操作日志导出完成: {len(logs)} 条")
    return {'file': output_path, 'count': len(logs)}


def get_dashboard_stats():
    today = date.today()
    with get_session() as session:
        today_diffs = session.query(InventoryDifference).filter(
            InventoryDifference.check_date == today
        ).all()
        pending_orders = session.query(WorkOrder).filter(
            WorkOrder.status.in_(['assigned', 'in_progress', 'upgraded'])
        ).count()
        upgraded_orders = session.query(WorkOrder).filter(
            WorkOrder.is_upgraded == True,
            WorkOrder.status.in_(['assigned', 'in_progress', 'upgraded'])
        ).count()
        pending_audits = session.query(SpecialAudit).filter(
            SpecialAudit.status == 'pending'
        ).count()
        active_tasks = session.query(StockCheckTask).filter(
            StockCheckTask.status.in_(['created', 'pushed', 'in_progress'])
        ).count()

    return {
        'today': {
            'total': len(today_diffs),
            'surplus': sum(1 for d in today_diffs if d.diff_type == '盘盈'),
            'deficit': sum(1 for d in today_diffs if d.diff_type == '盘亏'),
            'over_threshold': sum(1 for d in today_diffs if d.is_over_threshold),
            'diff_amount': sum(d.diff_amount for d in today_diffs)
        },
        'pending': {
            'work_orders': pending_orders,
            'upgraded_orders': upgraded_orders,
            'special_audits': pending_audits,
            'stock_tasks': active_tasks
        }
    }
