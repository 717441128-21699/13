import os
from datetime import datetime, date
from collections import defaultdict

import pandas as pd

from database import get_session
from models import (
    OperationLog, InventoryDifference, WorkOrder, InventoryLedger,
    StockCheckTask, StockCheckItem, Product, MonthlyStats, RealtimeInventory, ERPInventory
)
from config import EXPORT_DIR
from logger import setup_logger

logger = setup_logger('qe', 'query_export')


def query_differences(warehouse=None, category=None, start_date=None, end_date=None,
                      diff_type=None, over_threshold=None, status=None, sku=None,
                      limit=200, page=1):
    with get_session() as session:
        from sqlalchemy import and_
        clauses = []
        if warehouse:
            clauses.append(InventoryDifference.warehouse_code == warehouse)
        if category:
            clauses.append(InventoryDifference.category == category)
        if sku:
            clauses.append(InventoryDifference.sku.like(f"%{sku}%"))
        if diff_type:
            clauses.append(InventoryDifference.diff_type == diff_type)
        if status:
            clauses.append(InventoryDifference.status == status)
        if over_threshold is not None:
            clauses.append(InventoryDifference.is_over_threshold == over_threshold)
        if start_date:
            if isinstance(start_date, str):
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            clauses.append(InventoryDifference.check_date >= start_date)
        if end_date:
            if isinstance(end_date, str):
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            clauses.append(InventoryDifference.check_date <= end_date)

        q = session.query(InventoryDifference)
        if clauses:
            q = q.filter(*clauses)
        q = q.order_by(InventoryDifference.check_date.desc())
        total = q.count()
        diffs = q.offset((page - 1) * limit).limit(limit).all()

        data = []
        for d in diffs:
            data.append({
                'id': d.id, 'check_date': str(d.check_date),
                'warehouse': d.warehouse_code, 'sku': d.sku,
                'product_name': d.product_name, 'category': d.category or '',
                'realtime_qty': float(d.realtime_qty), 'erp_qty': float(d.erp_qty),
                'diff_qty': float(d.diff_qty), 'diff_type': d.diff_type,
                'unit_price': float(d.unit_price), 'diff_amount': float(d.diff_amount),
                'diff_rate': round(float(d.diff_rate) * 100, 2),
                'is_over_threshold': d.is_over_threshold,
                'status': d.status, 'work_order_id': d.work_order_id
            })
    return {'total': total, 'page': page, 'limit': limit, 'data': data}


def query_orders(warehouse=None, status=None, is_upgraded=None, auditor=None):
    with get_session() as session:
        q = session.query(WorkOrder)
        if warehouse:
            q = q.filter(WorkOrder.warehouse_code == warehouse)
        if status:
            q = q.filter(WorkOrder.status == status)
        if is_upgraded is not None:
            q = q.filter(WorkOrder.is_upgraded == is_upgraded)
        if auditor:
            q = q.filter(WorkOrder.auditor == auditor)
        q = q.order_by(WorkOrder.created_at.desc())
        orders = q.limit(200).all()

        data = []
        for o in orders:
            data.append({
                'id': o.id, 'order_no': o.order_no, 'warehouse': o.warehouse_code,
                'category': o.category or '', 'diff_type': o.diff_type,
                'auditor': o.auditor, 'supervisor': o.supervisor,
                'status': o.status, 'priority': o.priority,
                'is_upgraded': o.is_upgraded,
                'created_at': o.created_at.isoformat() if o.created_at else None,
                'assigned_at': o.assigned_at.isoformat() if o.assigned_at else None,
                'upgraded_at': o.upgraded_at.isoformat() if o.upgraded_at else None,
                'completed_at': o.completed_at.isoformat() if o.completed_at else None,
                'review_comment': o.review_comment,
                'diff_count': len(o.differences)
            })
    return data


def query_logs(warehouse=None, category=None, op_type=None, operator=None,
               sku=None, ref=None, start_time=None, end_time=None,
               limit=200, page=1):
    with get_session() as session:
        q = session.query(OperationLog)
        if warehouse:
            q = q.filter(OperationLog.warehouse_code == warehouse)
        if category:
            q = q.filter(OperationLog.category == category)
        if op_type:
            q = q.filter(OperationLog.operation_type == op_type)
        if operator:
            q = q.filter(OperationLog.operator == operator)
        if sku:
            q = q.filter(OperationLog.sku.like(f"%{sku}%"))
        if ref:
            q = q.filter(OperationLog.reference_no.like(f"%{ref}%"))
        if start_time:
            try:
                st = datetime.strptime(start_time, '%Y-%m-%d')
                q = q.filter(OperationLog.log_time >= st)
            except Exception:
                pass
        if end_time:
            try:
                et = datetime.strptime(end_time + ' 23:59:59', '%Y-%m-%d %H:%M:%S')
                q = q.filter(OperationLog.log_time <= et)
            except Exception:
                pass
        q = q.order_by(OperationLog.log_time.desc())
        total = q.count()
        logs = q.offset((page - 1) * limit).limit(limit).all()
        data = []
        for l in logs:
            data.append({
                'id': l.id, 'log_time': l.log_time.isoformat(),
                'operation_type': l.operation_type, 'operator': l.operator or '',
                'warehouse': l.warehouse_code or '', 'category': l.category or '',
                'sku': l.sku or '', 'reference_no': l.reference_no or '',
                'detail': l.detail or '', 'ip_address': l.ip_address or ''
            })
    return {'total': total, 'page': page, 'limit': limit, 'data': data}


def export_differences_batch(warehouse_codes=None, categories=None,
                             start_date=None, end_date=None):
    r = query_differences(
        limit=100000, page=1,
        start_date=start_date, end_date=end_date
    )
    filtered = []
    for d in r['data']:
        if warehouse_codes and d['warehouse'] not in warehouse_codes:
            continue
        if categories and d['category'] not in categories:
            continue
        filtered.append(d)

    os.makedirs(EXPORT_DIR, exist_ok=True)
    path = os.path.join(EXPORT_DIR, f'diff_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx')
    pd.DataFrame(filtered).to_excel(path, index=False)
    logger.info(f"导出差异: {path} ({len(filtered)}条)")
    return {'file': path, 'count': len(filtered)}


def export_operation_logs(warehouse=None, start_time=None, end_time=None):
    r = query_logs(warehouse=warehouse, start_time=start_time,
                   end_time=end_time, limit=100000, page=1)
    os.makedirs(EXPORT_DIR, exist_ok=True)
    path = os.path.join(EXPORT_DIR, f'logs_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx')
    pd.DataFrame(r['data']).to_excel(path, index=False)
    logger.info(f"导出日志: {path} ({r['total']}条)")
    return {'file': path, 'count': r['total']}
