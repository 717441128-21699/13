from datetime import date, datetime
from collections import defaultdict

from sqlalchemy import func

from database import get_session
from models import (
    InventoryDifference, InventoryLedger, WorkOrder, ERPInventory, Product
)
from logger import setup_logger
from operation_logger import log_operation

logger = setup_logger('ledger', 'ledger')


def update_ledger_from_work_order(order_no, operator='system', reason='盘点差异调整'):
    logger.info(f"根据工单 {order_no} 更新库存台账")

    with get_session() as session:
        order = session.query(WorkOrder).filter(
            WorkOrder.order_no == order_no
        ).first()
        if not order:
            raise ValueError(f"工单 {order_no} 不存在")

        ledger_entries = []
        today = date.today()

        for diff in order.differences:
            if diff.status != 'resolved':
                continue

            adjust_qty = diff.diff_qty
            before_qty = diff.erp_qty
            after_qty = before_qty + adjust_qty
            adjust_amount = adjust_qty * diff.unit_price

            ledger = InventoryLedger(
                ledger_date=today,
                warehouse_code=diff.warehouse_code,
                sku=diff.sku,
                product_name=diff.product_name,
                before_qty=before_qty,
                adjust_qty=adjust_qty,
                after_qty=after_qty,
                unit_price=diff.unit_price,
                adjust_amount=adjust_amount,
                reason=reason,
                reference_no=order_no,
                operator=operator
            )
            session.add(ledger)
            ledger_entries.append(ledger)

            erp_records = session.query(ERPInventory).filter(
                ERPInventory.warehouse_code == diff.warehouse_code,
                ERPInventory.sku == diff.sku
            ).order_by(ERPInventory.snapshot_time.desc()).all()

            if erp_records:
                latest = erp_records[0]
                latest.quantity = after_qty
                latest.snapshot_time = datetime.now()
            else:
                new_erp = ERPInventory(
                    warehouse_code=diff.warehouse_code,
                    sku=diff.sku,
                    quantity=after_qty,
                    snapshot_time=datetime.now()
                )
                session.add(new_erp)

            diff.status = 'ledger_updated'

        log_operation(
            operation_type='UPDATE_LEDGER',
            warehouse_code=order.warehouse_code,
            category=order.category,
            reference_no=order_no,
            operator=operator,
            detail=f"台账更新{len(ledger_entries)}条"
        )

    logger.info(f"已更新 {len(ledger_entries)} 条台账记录")
    return {
        'order_no': order_no,
        'ledger_count': len(ledger_entries)
    }


def update_ledger_single(warehouse_code, sku, adjust_qty, unit_price,
                         reason='手动调整', operator='manual', reference_no=None):
    logger.info(f"手动更新台账: {warehouse_code}/{sku}, 调整数量:{adjust_qty}")

    with get_session() as session:
        product = session.query(Product).filter(Product.sku == sku).first()
        product_name = product.name if product else ''

        subq = session.query(
            ERPInventory.warehouse_code,
            ERPInventory.sku,
            func.max(ERPInventory.snapshot_time).label('max_time')
        ).filter(
            ERPInventory.warehouse_code == warehouse_code,
            ERPInventory.sku == sku
        ).group_by(ERPInventory.warehouse_code, ERPInventory.sku).subquery()

        erp_latest = session.query(ERPInventory).join(
            subq,
            (ERPInventory.warehouse_code == subq.c.warehouse_code) &
            (ERPInventory.sku == subq.c.sku) &
            (ERPInventory.snapshot_time == subq.c.max_time)
        ).first()

        before_qty = erp_latest.quantity if erp_latest else 0.0
        after_qty = before_qty + adjust_qty
        adjust_amount = adjust_qty * unit_price

        ledger = InventoryLedger(
            ledger_date=date.today(),
            warehouse_code=warehouse_code,
            sku=sku,
            product_name=product_name,
            before_qty=before_qty,
            adjust_qty=adjust_qty,
            after_qty=after_qty,
            unit_price=unit_price,
            adjust_amount=adjust_amount,
            reason=reason,
            reference_no=reference_no,
            operator=operator
        )
        session.add(ledger)

        if erp_latest:
            erp_latest.quantity = after_qty
            erp_latest.snapshot_time = datetime.now()
        else:
            new_erp = ERPInventory(
                warehouse_code=warehouse_code,
                sku=sku,
                quantity=after_qty,
                snapshot_time=datetime.now()
            )
            session.add(new_erp)

        log_operation(
            operation_type='MANUAL_LEDGER',
            warehouse_code=warehouse_code,
            sku=sku,
            reference_no=reference_no,
            operator=operator,
            detail=f"调整前:{before_qty}, 调整后:{after_qty}, 原因:{reason}"
        )

    logger.info("台账手动更新完成")
    return {'warehouse': warehouse_code, 'sku': sku, 'after_qty': after_qty}


def get_ledger_records(warehouse_code=None, start_date=None, end_date=None, sku=None):
    with get_session() as session:
        q = session.query(InventoryLedger)
        if warehouse_code:
            q = q.filter(InventoryLedger.warehouse_code == warehouse_code)
        if sku:
            q = q.filter(InventoryLedger.sku == sku)
        if start_date:
            q = q.filter(InventoryLedger.ledger_date >= start_date)
        if end_date:
            q = q.filter(InventoryLedger.ledger_date <= end_date)
        q = q.order_by(InventoryLedger.ledger_date.desc())
        records = q.all()

        return [{
            'date': r.ledger_date.strftime('%Y-%m-%d'),
            'warehouse': r.warehouse_code,
            'sku': r.sku,
            'product_name': r.product_name,
            'before_qty': r.before_qty,
            'adjust_qty': r.adjust_qty,
            'after_qty': r.after_qty,
            'unit_price': r.unit_price,
            'adjust_amount': r.adjust_amount,
            'reason': r.reason,
            'reference_no': r.reference_no,
            'operator': r.operator
        } for r in records]
