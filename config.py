import os
from datetime import timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'inventory.db')}"

REPORT_DIR = os.path.join(BASE_DIR, 'reports')
EXPORT_DIR = os.path.join(BASE_DIR, 'exports')
LOG_DIR = os.path.join(BASE_DIR, 'logs')

for d in [REPORT_DIR, EXPORT_DIR, LOG_DIR]:
    os.makedirs(d, exist_ok=True)

THRESHOLD_QUANTITY = 5
THRESHOLD_AMOUNT = 1000.0

UPGRADE_HOURS = 48

AUDIT_DIFF_RATE = 0.03
AUDIT_CONSECUTIVE_MONTHS = 3

DEFAULT_AUDITORS = {
    'A类': 'auditor_category_a',
    'B类': 'auditor_category_b',
    'C类': 'auditor_category_c',
}

WAREHOUSE_SUPERVISORS = {
    'WH001': 'supervisor_wh001',
    'WH002': 'supervisor_wh002',
    'WH003': 'supervisor_wh003',
}

SCHEDULE_DAILY_HOUR = 2
SCHEDULE_DAILY_MINUTE = 0
SCHEDULE_MONTHLY_DAY = 1
SCHEDULE_MONTHLY_HOUR = 3
SCHEDULE_MONTHLY_MINUTE = 0
