from datetime import date, datetime, timedelta
from collections import defaultdict

from database import get_session
from models import InventoryDifference, WorkOrder
from config import DEFAULT_AUDITORS, WAREHOUSE_SUPERVISORS, UPGRADE_HOURS
from logger import setup_logger
from operation_logger import log_operation

logger = setup_logger('wo', 'work_order')


def _gen_no():
    return f"WO{datetime.now().strftime('%Y%m%d%H%M%S')}{datetime.now().microsecond % 1000:03d}"


def _auditor(cat):
    return DEFAULT_AUDITORS.get(cat or 'C类', DEFAULT_AUDITORS['C类'])


def _supervisor(wh):
    return WAREHOUSE_SUPERVISORS.get(wh, 'default_supervisor')


def create_work_orders(check_date=None):
    check_date = check_date or date.today()
    logger.info(f"生成 {check_date} 工单")

    with get_session() as session:
        diffs = session.query(InventoryDifference).filter(
            InventoryDifference.check_date == check_date,
            InventoryDifference.is_over_threshold == True,
            InventoryDifference.work_order_id == None,
            InventoryDifference.status != 'matched'
        ).all()

        groups = defaultdict(list)
        for d in diffs:
            groups[(d.warehouse_code, d.category or '未分类', d.diff_type)].append(d)

        created = []
        for (wh, cat, dtype), ds in groups.items():
            order_no = _gen_no()
            priority = 'high' if any(abs(d.diff_qty) > 20 or d.diff_amount > 5000 for d in ds) else 'normal'
            wo = WorkOrder(
                order_no=order_no, warehouse_code=wh, category=cat, diff_type=dtype,
                auditor=_auditor(cat), supervisor=_supervisor(wh),
                status='assigned', priority=priority, assigned_at=datetime.now()
            )
            session.add(wo)
            session.flush()
            for d in ds:
                d.work_order_id = wo.id
                d.status = 'in_work_order'
            created.append({'order_no': order_no, 'warehouse': wh, 'category': cat,
                            'diff_type': dtype, 'items': len(ds)})
            log_operation('CREATE_WORK_ORDER', warehouse_code=wh, category=cat,
                          reference_no=order_no, operator='system',
                          detail=f'审核人:{_auditor(cat)},条目:{len(ds)}')

    logger.info(f"生成工单 {len(created)}")
    return created


def check_and_upgrade_orders():
    now = datetime.now()
    cutoff = now - timedelta(hours=UPGRADE_HOURS)
    with get_session() as session:
        orders = session.query(WorkOrder).filter(
            WorkOrder.status.in_(['assigned', 'in_progress']),
            WorkOrder.is_upgraded == False,
            WorkOrder.assigned_at <= cutoff
        ).all()
        upgraded = []
        for o in orders:
            o.is_upgraded = True
            o.upgraded_at = now
            o.status = 'upgraded'
            upgraded.append(o.order_no)
            log_operation('UPGRADE_WORK_ORDER', warehouse_code=o.warehouse_code,
                          category=o.category, reference_no=o.order_no, operator='system',
                          detail=f'超{UPGRADE_HOURS}小时,升级至:{o.supervisor}')
    logger.info(f"升级工单 {len(upgraded)}: {upgraded}")
    return upgraded


def review_work_order(order_no, approved, comment='', operator='auditor'):
    logger.info(f"审核 {order_no}: {'通过' if approved else '驳回'}")
    with get_session() as session:
        order = session.query(WorkOrder).filter(WorkOrder.order_no == order_no).first()
        if not order:
            raise ValueError(f'工单 {order_no} 不存在')
        order.reviewed_at = datetime.now()
        order.review_comment = comment
        if approved:
            order.status = 'completed'
            order.completed_at = datetime.now()
            for d in order.differences:
                d.status = 'resolved'
        else:
            order.status = 'rejected'
            for d in order.differences:
                d.status = 'rejected'
        log_operation('REVIEW_WORK_ORDER', warehouse_code=order.warehouse_code,
                      category=order.category, reference_no=order_no, operator=operator,
                      detail=f'结果:{"通过" if approved else "驳回"},备注:{comment}')
    return {'order_no': order_no, 'approved': approved}
