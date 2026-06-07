from datetime import date, datetime
from sqlalchemy import func

from database import get_session
from models import (
    InventoryDifference, InventoryLedger, WorkOrder, ERPInventory, Product
)
from logger import setup_logger
from operation_logger import log_operation

logger = setup_logger('lg', 'ledger')


def update_ledger_from_work_order(order_no, operator='system', reason='盘点差异调整'):
    logger.info(f"根据工单 {order_no} 更新台账")
    count = 0
    with get_session() as session:
        order = session.query(WorkOrder).filter(WorkOrder.order_no == order_no).first()
        if not order:
            raise ValueError(f'工单 {order_no} 不存在')
        today = date.today()
        for d in order.differences:
            if d.status != 'resolved':
                continue
            before = d.erp_qty
            adjust = d.diff_qty
            after = before + adjust
            amount = adjust * d.unit_price

            session.add(InventoryLedger(
                ledger_date=today, warehouse_code=d.warehouse_code, sku=d.sku,
                product_name=d.product_name, before_qty=before, adjust_qty=adjust,
                after_qty=after, unit_price=d.unit_price, adjust_amount=amount,
                reason=reason, reference_no=order_no, operator=operator
            ))

            subq = session.query(
                ERPInventory.warehouse_code, ERPInventory.sku,
                func.max(ERPInventory.snapshot_time).label('max_time')
            ).filter(ERPInventory.warehouse_code == d.warehouse_code,
                     ERPInventory.sku == d.sku
                     ).group_by(ERPInventory.warehouse_code, ERPInventory.sku).subquery()
            erp = session.query(ERPInventory).join(
                subq,
                (ERPInventory.warehouse_code == subq.c.warehouse_code) &
                (ERPInventory.sku == subq.c.sku) &
                (ERPInventory.snapshot_time == subq.c.max_time)
            ).first()
            if erp:
                erp.quantity = after
                erp.snapshot_time = datetime.now()
            else:
                session.add(ERPInventory(warehouse_code=d.warehouse_code, sku=d.sku,
                                         quantity=after, snapshot_time=datetime.now()))
            d.status = 'ledger_updated'
            count += 1

        log_operation('UPDATE_LEDGER', warehouse_code=order.warehouse_code,
                      category=order.category, reference_no=order_no, operator=operator,
                      detail=f'更新{count}条')
    logger.info(f"更新台账 {count} 条")
    return {'order_no': order_no, 'count': count}
