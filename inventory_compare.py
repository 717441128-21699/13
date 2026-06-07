from datetime import date, datetime
from collections import defaultdict
from sqlalchemy import func

from database import get_session
from models import RealtimeInventory, ERPInventory, Product, InventoryDifference
from config import THRESHOLD_QUANTITY, THRESHOLD_AMOUNT
from logger import setup_logger
from operation_logger import log_operation

logger = setup_logger('inv_cmp', 'inventory_compare')


def _get_latest(session, cls):
    subq = session.query(
        cls.warehouse_code, cls.sku,
        func.max(cls.snapshot_time).label('max_time')
    ).group_by(cls.warehouse_code, cls.sku).subquery()
    return session.query(cls).join(
        subq,
        (cls.warehouse_code == subq.c.warehouse_code) &
        (cls.sku == subq.c.sku) &
        (cls.snapshot_time == subq.c.max_time)
    ).all()


def compare_inventory(check_date=None):
    check_date = check_date or date.today()
    logger.info(f"执行 {check_date} 库存比对")

    with get_session() as session:
        realtime = _get_latest(session, RealtimeInventory)
        erp = _get_latest(session, ERPInventory)
        products = {p.sku: p for p in session.query(Product).all()}

        rt_map = {(r.warehouse_code, r.sku): r for r in realtime}
        ep_map = {(e.warehouse_code, e.sku): e for e in erp}
        all_keys = set(rt_map) | set(ep_map)

        existing = {(d.warehouse_code, d.sku)
                    for d in session.query(InventoryDifference).filter(
                        InventoryDifference.check_date == check_date).all()}

        total = over = surplus = deficit = 0
        for key in all_keys:
            if key in existing:
                continue
            wh, sku = key
            rt_qty = rt_map[key].quantity if key in rt_map else 0.0
            ep_qty = ep_map[key].quantity if key in ep_map else 0.0
            diff = rt_qty - ep_qty
            if diff == 0 and key in rt_map and key in ep_map:
                continue

            p = products.get(sku)
            pname = p.name if p else ''
            cat = p.category if p else None
            price = p.unit_price if p else 0.0
            amount = abs(diff) * price
            rate = (abs(diff) / ep_qty) if ep_qty > 0 else (1.0 if rt_qty > 0 else 0.0)
            dtype = '盘盈' if diff > 0 else ('盘亏' if diff < 0 else '一致')
            is_over = abs(diff) > THRESHOLD_QUANTITY or amount > THRESHOLD_AMOUNT

            session.add(InventoryDifference(
                check_date=check_date, warehouse_code=wh, sku=sku,
                product_name=pname, category=cat,
                realtime_qty=rt_qty, erp_qty=ep_qty, diff_qty=diff,
                diff_type=dtype, unit_price=price, diff_amount=amount,
                diff_rate=rate, is_over_threshold=is_over,
                status='pending' if diff != 0 else 'matched'
            ))
            total += 1
            if is_over:
                over += 1
            if dtype == '盘盈':
                surplus += 1
            elif dtype == '盘亏':
                deficit += 1

    log_operation('DAILY_COMPARE', detail=f'日期:{check_date},差异:{total},超阈值:{over},盘盈:{surplus},盘亏:{deficit}')
    logger.info(f"差异{total},超阈值{over},盘盈{surplus},盘亏{deficit}")
    return {'date': str(check_date), 'total_diff': total, 'over_threshold': over,
            'surplus': surplus, 'deficit': deficit}
