from datetime import date, datetime, timedelta
from collections import defaultdict

from database import get_session
from models import InventoryDifference, WorkOrder
from config import DEFAULT_AUDITORS, WAREHOUSE_SUPERVISORS, UPGRADE_HOURS
from logger import setup_logger
from operation_logger import log_operation

logger = setup_logger('work_order', 'work_order')


def _gen_order_no():
    return f"WO{datetime.now().strftime('%Y%m%d%H%M%S')}{datetime.now().microsecond % 1000:03d}"


def _get_auditor(category):
    return DEFAULT_AUDITORS.get(category or 'C类', DEFAULT_AUDITORS['C类'])


def _get_supervisor(warehouse_code):
    return WAREHOUSE_SUPERVISORS.get(warehouse_code, 'default_supervisor')


def create_work_orders(check_date=None):
    check_date = check_date or date.today()
    logger.info(f"开始为 {check_date} 的超阈值差异生成盘点工单")

    with get_session() as session:
        over_threshold = session.query(InventoryDifference).filter(
            InventoryDifference.check_date == check_date,
            InventoryDifference.is_over_threshold == True,
            InventoryDifference.work_order_id == None,
            InventoryDifference.status != 'matched'
        ).all()

        if not over_threshold:
            logger.info("无超阈值差异，无需生成工单")
            return []

        grouped = defaultdict(list)
        for d in over_threshold:
            key = (d.warehouse_code, d.category or '未分类', d.diff_type)
            grouped[key].append(d)

        created_orders = []
        for (wh, cat, dtype), diffs in grouped.items():
            order_no = _gen_order_no()
            auditor = _get_auditor(cat)
            supervisor = _get_supervisor(wh)

            priority = 'high' if any(
                abs(d.diff_qty) > 20 or d.diff_amount > 5000 for d in diffs
            ) else 'normal'

            order = WorkOrder(
                order_no=order_no,
                warehouse_code=wh,
                category=cat,
                diff_type=dtype,
                auditor=auditor,
                supervisor=supervisor,
                status='assigned',
                priority=priority,
                assigned_at=datetime.now()
            )
            session.add(order)
            session.flush()

            for d in diffs:
                d.work_order_id = order.id
                d.status = 'in_work_order'

            created_orders.append({
                'order_no': order_no,
                'warehouse': wh,
                'category': cat,
                'diff_type': dtype,
                'auditor': auditor,
                'items': len(diffs),
                'priority': priority
            })
            log_operation(
                operation_type='CREATE_WORK_ORDER',
                warehouse_code=wh,
                category=cat,
                reference_no=order_no,
                operator='system',
                detail=f"分配审核人:{auditor},差异条目:{len(diffs)}"
            )

    logger.info(f"已生成 {len(created_orders)} 个盘点工单")
    return created_orders


def check_and_upgrade_orders():
    logger.info("检查并升级超期未处理工单")

    now = datetime.now()
    cutoff = now - timedelta(hours=UPGRADE_HOURS)

    with get_session() as session:
        pending = session.query(WorkOrder).filter(
            WorkOrder.status.in_(['assigned', 'in_progress']),
            WorkOrder.is_upgraded == False,
            WorkOrder.assigned_at <= cutoff
        ).all()

        upgraded = []
        for order in pending:
            order.is_upgraded = True
            order.upgraded_at = now
            order.status = 'upgraded'
            upgraded.append(order.order_no)

            log_operation(
                operation_type='UPGRADE_WORK_ORDER',
                warehouse_code=order.warehouse_code,
                category=order.category,
                reference_no=order.order_no,
                operator='system',
                detail=f"超{UPGRADE_HOURS}小时未处理，升级至主管:{order.supervisor}"
            )

    if upgraded:
        logger.info(f"已升级 {len(upgraded)} 个工单至仓库主管: {upgraded}")
    else:
        logger.info("无需要升级的工单")

    return upgraded


def review_work_order(order_no, approved, comment='', operator='auditor'):
    logger.info(f"审核工单 {order_no}, 结果: {'通过' if approved else '驳回'}")

    with get_session() as session:
        order = session.query(WorkOrder).filter(
            WorkOrder.order_no == order_no
        ).first()
        if not order:
            raise ValueError(f"工单 {order_no} 不存在")

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

        log_operation(
            operation_type='REVIEW_WORK_ORDER',
            warehouse_code=order.warehouse_code,
            category=order.category,
            reference_no=order_no,
            operator=operator,
            detail=f"审核结果:{'通过' if approved else '驳回'}, 备注:{comment}"
        )

    logger.info(f"工单 {order_no} 审核完成")
    return {'order_no': order_no, 'approved': approved}


def get_pending_orders(warehouse_code=None, is_upgraded=None):
    with get_session() as session:
        q = session.query(WorkOrder).filter(
            WorkOrder.status.in_(['assigned', 'in_progress', 'upgraded'])
        )
        if warehouse_code:
            q = q.filter(WorkOrder.warehouse_code == warehouse_code)
        if is_upgraded is not None:
            q = q.filter(WorkOrder.is_upgraded == is_upgraded)

        orders = q.all()
        return [{
            'order_no': o.order_no,
            'warehouse': o.warehouse_code,
            'category': o.category,
            'diff_type': o.diff_type,
            'auditor': o.auditor,
            'supervisor': o.supervisor,
            'status': o.status,
            'priority': o.priority,
            'is_upgraded': o.is_upgraded,
            'created_at': o.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'assigned_at': o.assigned_at.strftime('%Y-%m-%d %H:%M:%S') if o.assigned_at else None,
            'diff_count': len(o.differences)
        } for o in orders]
