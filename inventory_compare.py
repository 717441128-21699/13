from datetime import date, datetime
from collections import defaultdict

from database import get_session
from models import (
    RealtimeInventory, ERPInventory, Product, InventoryDifference
)
from config import THRESHOLD_QUANTITY, THRESHOLD_AMOUNT
from logger import setup_logger
from operation_logger import log_operation

logger = setup_logger('inventory_compare', 'inventory_compare')


def _get_latest_snapshot(session, model_cls):
    from sqlalchemy import func
    subq = session.query(
        model_cls.warehouse_code,
        model_cls.sku,
        func.max(model_cls.snapshot_time).label('max_time')
    ).group_by(
        model_cls.warehouse_code, model_cls.sku
    ).subquery()

    return session.query(model_cls).join(
        subq,
        (model_cls.warehouse_code == subq.c.warehouse_code) &
        (model_cls.sku == subq.c.sku) &
        (model_cls.snapshot_time == subq.c.max_time)
    ).all()


def _build_product_map(session):
    products = session.query(Product).all()
    return {p.sku: p for p in products}


def compare_inventory(check_date=None):
    check_date = check_date or date.today()
    logger.info(f"开始执行 {check_date} 库存比对任务")

    with get_session() as session:
        realtime_list = _get_latest_snapshot(session, RealtimeInventory)
        erp_list = _get_latest_snapshot(session, ERPInventory)
        product_map = _build_product_map(session)

        realtime_map = {}
        for r in realtime_list:
            key = (r.warehouse_code, r.sku)
            realtime_map[key] = r

        erp_map = {}
        for e in erp_list:
            key = (e.warehouse_code, e.sku)
            erp_map[key] = e

        all_keys = set(realtime_map.keys()) | set(erp_map.keys())
        existing = session.query(InventoryDifference).filter(
            InventoryDifference.check_date == check_date
        ).all()
        existing_keys = {(d.warehouse_code, d.sku) for d in existing}

        diff_count = 0
        over_threshold_count = 0
        surplus_count = 0
        deficit_count = 0

        for key in all_keys:
            if key in existing_keys:
                continue

            warehouse_code, sku = key
            rt = realtime_map.get(key)
            ep = erp_map.get(key)

            realtime_qty = rt.quantity if rt else 0.0
            erp_qty = ep.quantity if ep else 0.0
            diff_qty = realtime_qty - erp_qty

            if diff_qty == 0 and rt and ep:
                continue

            product = product_map.get(sku)
            product_name = product.name if product else ''
            category = product.category if product else None
            unit_price = product.unit_price if product else 0.0

            diff_amount = abs(diff_qty) * unit_price

            if erp_qty > 0:
                diff_rate = abs(diff_qty) / erp_qty
            elif realtime_qty > 0:
                diff_rate = 1.0
            else:
                diff_rate = 0.0

            if diff_qty > 0:
                diff_type = '盘盈'
                surplus_count += 1
            elif diff_qty < 0:
                diff_type = '盘亏'
                deficit_count += 1
            else:
                diff_type = '一致'

            is_over = (abs(diff_qty) > THRESHOLD_QUANTITY) or (
                diff_amount > THRESHOLD_AMOUNT
            )
            if is_over:
                over_threshold_count += 1

            diff = InventoryDifference(
                check_date=check_date,
                warehouse_code=warehouse_code,
                sku=sku,
                product_name=product_name,
                category=category,
                realtime_qty=realtime_qty,
                erp_qty=erp_qty,
                diff_qty=diff_qty,
                diff_type=diff_type,
                unit_price=unit_price,
                diff_amount=diff_amount,
                diff_rate=diff_rate,
                is_over_threshold=is_over,
                status='pending' if diff_qty != 0 else 'matched'
            )
            session.add(diff)
            diff_count += 1

    log_operation(
        operation_type='DAILY_COMPARE',
        detail=f"日期:{check_date},差异数:{diff_count},超阈值:{over_threshold_count},盘盈:{surplus_count},盘亏:{deficit_count}"
    )
    logger.info(
        f"库存比对完成：差异{diff_count}条，超阈值{over_threshold_count}条，"
        f"盘盈{surplus_count}条，盘亏{deficit_count}条"
    )
    return {
        'date': check_date,
        'total_diff': diff_count,
        'over_threshold': over_threshold_count,
        'surplus': surplus_count,
        'deficit': deficit_count
    }


def get_differences_summary(check_date=None, warehouse_code=None, category=None):
    check_date = check_date or date.today()
    with get_session() as session:
        q = session.query(InventoryDifference).filter(
            InventoryDifference.check_date == check_date
        )
        if warehouse_code:
            q = q.filter(InventoryDifference.warehouse_code == warehouse_code)
        if category:
            q = q.filter(InventoryDifference.category == category)
        diffs = q.all()

    summary = defaultdict(lambda: {
        'count': 0, 'surplus': 0, 'deficit': 0,
        'total_amount': 0.0, 'over_threshold': 0
    })
    for d in diffs:
        key = (d.warehouse_code, d.category or '未分类')
        s = summary[key]
        s['count'] += 1
        s['total_amount'] += d.diff_amount
        if d.diff_type == '盘盈':
            s['surplus'] += 1
        elif d.diff_type == '盘亏':
            s['deficit'] += 1
        if d.is_over_threshold:
            s['over_threshold'] += 1

    return dict(summary)
