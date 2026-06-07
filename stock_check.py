import random
from datetime import datetime
from sqlalchemy import func

from database import get_session
from models import (
    StockCheckTask, StockCheckItem, Product, ERPInventory
)
from logger import setup_logger
from operation_logger import log_operation

logger = setup_logger('sc', 'stock_check')


def _gen_no():
    return f"SC{datetime.now().strftime('%Y%m%d%H%M%S')}"


def create_stock_check_task(task_type, warehouse_code, category=None,
                            sample_ratio=0.3, operator='system'):
    logger.info(f"创建盘点任务: {task_type} {warehouse_code}")
    if task_type not in ('full', 'sample'):
        raise ValueError("task_type 必须是 full 或 sample")

    with get_session() as session:
        subq = session.query(
            ERPInventory.warehouse_code, ERPInventory.sku,
            func.max(ERPInventory.snapshot_time).label('max_time')
        ).filter(ERPInventory.warehouse_code == warehouse_code
                 ).group_by(ERPInventory.warehouse_code, ERPInventory.sku).subquery()
        erp = session.query(ERPInventory).join(
            subq,
            (ERPInventory.warehouse_code == subq.c.warehouse_code) &
            (ERPInventory.sku == subq.c.sku) &
            (ERPInventory.snapshot_time == subq.c.max_time)
        ).all()

        skus = {e.sku for e in erp}
        if category:
            ps = session.query(Product).filter(
                Product.sku.in_(list(skus)), Product.category == category
            ).all()
            fs = {p.sku for p in ps}
            erp = [e for e in erp if e.sku in fs]

        if task_type == 'sample' and 0 < sample_ratio < 1:
            random.seed(datetime.now().microsecond)
            k = max(1, int(len(erp) * sample_ratio))
            erp = random.sample(erp, min(k, len(erp)))

        if not erp:
            raise ValueError("无可盘点数据")

        task_no = _gen_no()
        task = StockCheckTask(
            task_no=task_no, task_type=task_type, warehouse_code=warehouse_code,
            category=category, sample_ratio=sample_ratio if task_type == 'sample' else None,
            status='created', operator=operator
        )
        session.add(task)
        session.flush()

        products = {p.sku: p for p in session.query(Product).all()}
        for e in erp:
            p = products.get(e.sku)
            session.add(StockCheckItem(
                task_id=task.id, sku=e.sku,
                product_name=p.name if p else '',
                system_qty=e.quantity, is_scanned=False
            ))

        log_operation('CREATE_CHECK_TASK', warehouse_code=warehouse_code, category=category,
                      reference_no=task_no, operator=operator,
                      detail=f'类型:{task_type},条目:{len(erp)}')

    logger.info(f"任务 {task_no} 创建成功, 共 {len(erp)} 条")
    return {'task_no': task_no, 'task_type': task_type,
            'warehouse': warehouse_code, 'items': len(erp)}


def push_task_to_terminal(task_no):
    with get_session() as session:
        task = session.query(StockCheckTask).filter(
            StockCheckTask.task_no == task_no
        ).first()
        if not task:
            raise ValueError(f"任务 {task_no} 不存在")
        task.status = 'pushed'
        task.started_at = datetime.now()
        payload = {
            'task_no': task.task_no,
            'warehouse': task.warehouse_code,
            'task_type': task.task_type,
            'total_items': len(task.items),
            'items': [{'id': i.id, 'sku': i.sku, 'product_name': i.product_name,
                       'system_qty': i.system_qty} for i in task.items]
        }
        log_operation('PUSH_TO_TERMINAL', warehouse_code=task.warehouse_code,
                      reference_no=task_no, detail=f'推送{len(task.items)}条')
    return payload


def scan_item(task_no, item_id, scanned_qty, scanner='operator'):
    logger.info(f"扫码: {task_no} 条目 {item_id} = {scanned_qty}")
    with get_session() as session:
        task = session.query(StockCheckTask).filter(
            StockCheckTask.task_no == task_no
        ).first()
        if not task or task.status in ('completed', 'cancelled'):
            raise ValueError("任务无效")
        item = session.query(StockCheckItem).filter(
            StockCheckItem.id == item_id, StockCheckItem.task_id == task.id
        ).first()
        if not item:
            raise ValueError("条目不存在")
        item.scanned_qty = float(scanned_qty)
        item.is_scanned = True
        item.scanned_at = datetime.now()
        item.scanner = scanner
        if task.status == 'created':
            task.status = 'in_progress'
            task.started_at = datetime.now()
        log_operation('SCAN_ITEM', warehouse_code=task.warehouse_code, sku=item.sku,
                      reference_no=task_no, operator=scanner,
                      detail=f'系统:{item.system_qty},扫码:{scanned_qty}')
    return {'item_id': item_id, 'sku': item.sku, 'scanned_qty': scanned_qty}


def complete_stock_check_task(task_no, operator='system'):
    with get_session() as session:
        task = session.query(StockCheckTask).filter(
            StockCheckTask.task_no == task_no
        ).first()
        if not task:
            raise ValueError(f"任务 {task_no} 不存在")
        task.status = 'completed'
        task.completed_at = datetime.now()
        total = len(task.items)
        scanned = sum(1 for i in task.items if i.is_scanned)
        matched = sum(1 for i in task.items if i.is_scanned and i.scanned_qty == i.system_qty)
        diff = scanned - matched
        log_operation('COMPLETE_CHECK_TASK', warehouse_code=task.warehouse_code,
                      reference_no=task_no, operator=operator,
                      detail=f'总:{total},已扫:{scanned},一致:{matched},差异:{diff}')

    summary = {'total': total, 'scanned': scanned, 'matched': matched, 'diff': diff}
    logger.info(f"任务 {task_no} 完成: {summary}")
    return {'task_no': task_no, 'summary': summary}


def get_task_checklist(task_no):
    with get_session() as session:
        task = session.query(StockCheckTask).filter(
            StockCheckTask.task_no == task_no
        ).first()
        if not task:
            raise ValueError(f"任务 {task_no} 不存在")
        return {
            'task_no': task.task_no,
            'warehouse': task.warehouse_code,
            'category': task.category,
            'task_type': task.task_type,
            'status': task.status,
            'items': [{'id': i.id, 'sku': i.sku, 'product_name': i.product_name,
                       'system_qty': float(i.system_qty),
                       'scanned_qty': float(i.scanned_qty) if i.is_scanned else None,
                       'is_scanned': i.is_scanned} for i in task.items]
        }
