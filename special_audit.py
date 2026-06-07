from datetime import date, datetime, timedelta
from collections import defaultdict

from database import get_session
from models import InventoryDifference, SpecialAudit
from config import AUDIT_DIFF_RATE, AUDIT_CONSECUTIVE_MONTHS
from logger import setup_logger
from operation_logger import log_operation

logger = setup_logger('sa', 'special_audit')


def _mk(d):
    return f"{d.year}-{d.month:02d}"


def _last_n(n, from_date=None):
    d = from_date or date.today()
    out = []
    y, m = d.year, d.month
    for _ in range(n):
        m -= 1
        if m == 0:
            m = 12
            y -= 1
        out.append(f"{y}-{m:02d}")
    return list(reversed(out))


def check_special_audit():
    logger.info("检查专项审计触发")
    with get_session() as session:
        diffs = session.query(InventoryDifference).filter(
            InventoryDifference.diff_qty != 0
        ).all()

    monthly = defaultdict(lambda: defaultdict(lambda: {'tq': 0.0, 'dq': 0.0}))
    for d in diffs:
        m = _mk(d.check_date)
        key = (d.warehouse_code, d.category or '未分类')
        monthly[m][key]['tq'] += max(abs(d.erp_qty), abs(d.realtime_qty))
        monthly[m][key]['dq'] += abs(d.diff_qty)

    last_months = _last_n(AUDIT_CONSECUTIVE_MONTHS)
    triggered = []

    with get_session() as session:
        all_keys = set()
        for m in last_months:
            all_keys.update(monthly[m].keys())

        for key in all_keys:
            wh, cat = key
            consecutive = 0
            rates = []
            for m in last_months:
                md = monthly[m].get(key)
                if md and md['tq'] > 0:
                    r = md['dq'] / md['tq']
                    rates.append(r)
                    consecutive = consecutive + 1 if r > AUDIT_DIFF_RATE else 0
                else:
                    consecutive = 0
                    rates.append(0.0)

            if consecutive >= AUDIT_CONSECUTIVE_MONTHS:
                cur = last_months[-1]
                exist = session.query(SpecialAudit).filter(
                    SpecialAudit.warehouse_code == wh,
                    SpecialAudit.category == cat,
                    SpecialAudit.trigger_month == cur
                ).first()
                if not exist:
                    avg = sum(rates) / len(rates)
                    audit_no = f"SA{datetime.now().strftime('%Y%m%d%H%M%S')}"
                    session.add(SpecialAudit(
                        audit_no=audit_no, warehouse_code=wh, category=cat,
                        trigger_month=cur, consecutive_months=consecutive,
                        avg_diff_rate=avg, status='pending', auditor='internal_audit'
                    ))
                    triggered.append({'audit_no': audit_no, 'warehouse': wh,
                                      'category': cat, 'consecutive': consecutive,
                                      'avg_rate': round(avg * 100, 2)})
                    log_operation('TRIGGER_AUDIT', warehouse_code=wh, category=cat,
                                  reference_no=audit_no, operator='system',
                                  detail=f'连续{consecutive}月>{AUDIT_DIFF_RATE*100}%')

    logger.info(f"触发审计 {len(triggered)}: {triggered}")
    return triggered
