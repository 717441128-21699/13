from datetime import date, datetime
from collections import defaultdict
import calendar

from database import get_session
from models import InventoryDifference, SpecialAudit
from config import AUDIT_DIFF_RATE, AUDIT_CONSECUTIVE_MONTHS
from logger import setup_logger
from operation_logger import log_operation

logger = setup_logger('audit', 'audit')


def _gen_audit_no():
    return f"SA{datetime.now().strftime('%Y%m%d%H%M%S')}"


def _get_month_key(d):
    return f"{d.year}-{d.month:02d}"


def _last_n_months(n, from_date=None):
    from_date = from_date or date.today()
    months = []
    y, m = from_date.year, from_date.month
    for _ in range(n):
        m -= 1
        if m == 0:
            m = 12
            y -= 1
        months.append(f"{y}-{m:02d}")
    return list(reversed(months))


def check_special_audit():
    logger.info("检查连续差异品类，触发专项审计")

    with get_session() as session:
        all_diffs = session.query(InventoryDifference).filter(
            InventoryDifference.diff_qty != 0
        ).all()

    monthly_data = defaultdict(lambda: defaultdict(lambda: {
        'total_qty': 0.0, 'diff_qty': 0.0, 'count': 0
    }))

    for d in all_diffs:
        m = _get_month_key(d.check_date)
        key = (d.warehouse_code, d.category or '未分类')
        md = monthly_data[m][key]
        md['total_qty'] += max(abs(d.erp_qty), abs(d.realtime_qty))
        md['diff_qty'] += abs(d.diff_qty)
        md['count'] += 1

    last_months = _last_n_months(AUDIT_CONSECUTIVE_MONTHS)
    current_month = last_months[-1]

    triggered_audits = []

    for m in last_months:
        if m not in monthly_data:
            continue

    all_keys = set()
    for m in last_months:
        all_keys.update(monthly_data[m].keys())

    for key in all_keys:
        warehouse_code, category = key
        consecutive = 0
        rates = []

        for m in last_months:
            md = monthly_data[m].get(key)
            if md and md['total_qty'] > 0:
                rate = md['diff_qty'] / md['total_qty']
                rates.append(rate)
                if rate > AUDIT_DIFF_RATE:
                    consecutive += 1
                else:
                    consecutive = 0
            else:
                consecutive = 0
                rates.append(0.0)

        if consecutive >= AUDIT_CONSECUTIVE_MONTHS:
            with get_session() as session:
                existing = session.query(SpecialAudit).filter(
                    SpecialAudit.warehouse_code == warehouse_code,
                    SpecialAudit.category == category,
                    SpecialAudit.trigger_month == current_month
                ).first()

                if not existing:
                    avg_rate = sum(rates) / len(rates) if rates else 0.0
                    audit_no = _gen_audit_no()
                    audit = SpecialAudit(
                        audit_no=audit_no,
                        warehouse_code=warehouse_code,
                        category=category,
                        trigger_month=current_month,
                        consecutive_months=consecutive,
                        avg_diff_rate=avg_rate,
                        status='pending',
                        auditor='internal_audit'
                    )
                    session.add(audit)
                    triggered_audits.append({
                        'audit_no': audit_no,
                        'warehouse': warehouse_code,
                        'category': category,
                        'consecutive': consecutive,
                        'avg_rate': round(avg_rate * 100, 2)
                    })

                    log_operation(
                        operation_type='TRIGGER_AUDIT',
                        warehouse_code=warehouse_code,
                        category=category,
                        reference_no=audit_no,
                        operator='system',
                        detail=f"连续{consecutive}个月差异率>{AUDIT_DIFF_RATE*100}%,平均差异率:{avg_rate*100:.2f}%"
                    )

    if triggered_audits:
        logger.info(f"触发 {len(triggered_audits)} 项专项审计: {triggered_audits}")
    else:
        logger.info("无需要触发的专项审计")

    return triggered_audits


def complete_special_audit(audit_no, audit_report, operator='auditor'):
    logger.info(f"完成专项审计 {audit_no}")

    with get_session() as session:
        audit = session.query(SpecialAudit).filter(
            SpecialAudit.audit_no == audit_no
        ).first()
        if not audit:
            raise ValueError(f"审计 {audit_no} 不存在")

        audit.status = 'completed'
        audit.completed_at = datetime.now()
        audit.audit_report = audit_report
        audit.auditor = operator

        log_operation(
            operation_type='COMPLETE_AUDIT',
            warehouse_code=audit.warehouse_code,
            category=audit.category,
            reference_no=audit_no,
            operator=operator,
            detail=f"审计完成，报告摘要:{audit_report[:100]}"
        )

    logger.info(f"专项审计 {audit_no} 已完成")
    return {'audit_no': audit_no, 'status': 'completed'}


def get_pending_audits():
    with get_session() as session:
        audits = session.query(SpecialAudit).filter(
            SpecialAudit.status == 'pending'
        ).all()
        return [{
            'audit_no': a.audit_no,
            'warehouse': a.warehouse_code,
            'category': a.category,
            'trigger_month': a.trigger_month,
            'consecutive': a.consecutive_months,
            'avg_diff_rate': round(a.avg_diff_rate * 100, 2),
            'created_at': a.created_at.strftime('%Y-%m-%d %H:%M:%S')
        } for a in audits]
