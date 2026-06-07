import random
from datetime import datetime
from collections import defaultdict

from database import get_session
from models import (
    StockCheckTask, StockCheckItem, Product, ERPInventory
)
from logger import setup_logger
from operation_logger import log_operation

logger = setup_logger('stock_check', 'stock_check')


def _gen_task_no():
    return f"SC{datetime.now().strftime('%Y%m%d%H%M%S')}"


def create_stock_check_task(task_type, warehouse_code, category=None,
                            sample_ratio=0.3, operator='system'):
    logger.info(f"创建盘点任务: 类型={task_type}, 仓库={warehouse_code}")

    if task_type not in ('full', 'sample'):
        raise ValueError("task_type 必须是 'full' 或 'sample'")

    with get_session() as session:
        q = session.query(ERPInventory).filter(
            ERPInventory.warehouse_code == warehouse_code
        )

        from sqlalchemy import func
        subq = q.from_self(
            ERPInventory.warehouse_code,
            ERPInventory.sku,
            func.max(ERPInventory.snapshot_time).label('max_time')
        ).group_by(ERPInventory.warehouse_code, ERPInventory.sku).subquery()

        erp_items = session.query(ERPInventory).join(
            subq,
            (ERPInventory.warehouse_code == subq.c.warehouse_code) &
            (ERPInventory.sku == subq.c.sku) &
            (ERPInventory.snapshot_time == subq.c.max_time)
        ).all()

        sku_set = set()
        for item in erp_items:
            sku_set.add(item.sku)

        if category:
            products = session.query(Product).filter(
                Product.sku.in_(list(sku_set)),
                Product.category == category
            ).all()
            filtered_skus = {p.sku for p in products}
            erp_items = [i for i in erp_items if i.sku in filtered_skus]

        if task_type == 'sample' and 0 < sample_ratio < 1:
            random.seed(datetime.now().microsecond)
            k = max(1, int(len(erp_items) * sample_ratio))
            erp_items = random.sample(erp_items, min(k, len(erp_items)))

        if not erp_items:
            raise ValueError("没有可盘点的库存数据")

        task_no = _gen_task_no()
        task = StockCheckTask(
            task_no=task_no,
            task_type=task_type,
            warehouse_code=warehouse_code,
            category=category,
            sample_ratio=sample_ratio if task_type == 'sample' else None,
            status='created',
            operator=operator
        )
        session.add(task)
        session.flush()

        product_map = {p.sku: p for p in session.query(Product).all()}

        for erp in erp_items:
            product = product_map.get(erp.sku)
            item = StockCheckItem(
                task_id=task.id,
                sku=erp.sku,
                product_name=product.name if product else '',
                system_qty=erp.quantity,
                is_scanned=False
            )
            session.add(item)

        log_operation(
            operation_type='CREATE_CHECK_TASK',
            warehouse_code=warehouse_code,
            category=category,
            reference_no=task_no,
            operator=operator,
            detail=f"类型:{task_type},条目数:{len(erp_items)},抽样率:{sample_ratio if task_type=='sample' else 'N/A'}"
        )

    logger.info(f"盘点任务 {task_no} 创建成功，共 {len(erp_items)} 条")
    return {
        'task_no': task_no,
        'task_type': task_type,
        'warehouse': warehouse_code,
        'item_count': len(erp_items)
    }


def push_task_to_terminal(task_no):
    logger.info(f"推送盘点任务 {task_no} 至手持终端")

    with get_session() as session:
        task = session.query(StockCheckTask).filter(
            StockCheckTask.task_no == task_no
        ).first()
        if not task:
            raise ValueError(f"任务 {task_no} 不存在")

        task.status = 'pushed'
        task.started_at = datetime.now()

        terminal_payload = {
            'task_no': task.task_no,
            'warehouse': task.warehouse_code,
            'task_type': task.task_type,
            'total_items': len(task.items),
            'items': [{
                'id': item.id,
                'sku': item.sku,
                'product_name': item.product_name,
                'system_qty': item.system_qty
            } for item in task.items]
        }

        log_operation(
            operation_type='PUSH_TO_TERMINAL',
            warehouse_code=task.warehouse_code,
            reference_no=task_no,
            detail=f"推送至手持终端,共{len(task.items)}条"
        )

    logger.info(f"任务 {task_no} 已推送")
    return terminal_payload


def scan_item(task_no, item_id, scanned_qty, scanner='operator'):
    logger.info(f"任务 {task_no} 扫码: 条目 {item_id}, 数量 {scanned_qty}")

    with get_session() as session:
        task = session.query(StockCheckTask).filter(
            StockCheckTask.task_no == task_no
        ).first()
        if not task:
            raise ValueError(f"任务 {task_no} 不存在")
        if task.status in ('completed', 'cancelled'):
            raise ValueError(f"任务 {task_no} 已结束")

        item = session.query(StockCheckItem).filter(
            StockCheckItem.id == item_id,
            StockCheckItem.task_id == task.id
        ).first()
        if not item:
            raise ValueError(f"条目 {item_id} 不存在")

        item.scanned_qty = scanned_qty
        item.is_scanned = True
        item.scanned_at = datetime.now()
        item.scanner = scanner

        if task.status == 'created':
            task.status = 'in_progress'
            task.started_at = datetime.now()

        log_operation(
            operation_type='SCAN_ITEM',
            warehouse_code=task.warehouse_code,
            sku=item.sku,
            reference_no=task_no,
            operator=scanner,
            detail=f"条目ID:{item_id},SKU:{item.sku},系统数量:{item.system_qty},扫码数量:{scanned_qty}"
        )

    logger.info(f"扫码成功: {item.sku} -> {scanned_qty}")
    return {'item_id': item_id, 'sku': item.sku, 'scanned_qty': scanned_qty}


def complete_stock_check_task(task_no, operator='system'):
    logger.info(f"完成盘点任务 {task_no}")

    with get_session() as session:
        task = session.query(StockCheckTask).filter(
            StockCheckTask.task_no == task_no
        ).first()
        if not task:
            raise ValueError(f"任务 {task_no} 不存在")

        task.status = 'completed'
        task.completed_at = datetime.now()

        summary = {
            'total': len(task.items),
            'scanned': 0,
            'matched': 0,
            'diff': 0,
            'diff_qty_total': 0.0,
            'diff_items': []
        }

        for item in task.items:
            if item.is_scanned:
                summary['scanned'] += 1
                diff = item.scanned_qty - item.system_qty
                if diff == 0:
                    summary['matched'] += 1
                else:
                    summary['diff'] += 1
                    summary['diff_qty_total'] += abs(diff)
                    summary['diff_items'].append({
                        'sku': item.sku,
                        'product_name': item.product_name,
                        'system_qty': item.system_qty,
                        'scanned_qty': item.scanned_qty,
                        'diff_qty': diff
                    })

        log_operation(
            operation_type='COMPLETE_CHECK_TASK',
            warehouse_code=task.warehouse_code,
            reference_no=task_no,
            operator=operator,
            detail=f"完成,总条目:{summary['total']},已扫:{summary['scanned']},一致:{summary['matched']},差异:{summary['diff']}"
        )

    logger.info(f"任务 {task_no} 完成: {summary['scanned']}/{summary['total']} 已扫描, {summary['diff']} 条差异")
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
            'items': [{
                'id': item.id,
                'sku': item.sku,
                'product_name': item.product_name,
                'system_qty': item.system_qty,
                'scanned_qty': item.scanned_qty,
                'is_scanned': item.is_scanned
            } for item in task.items]
        }
