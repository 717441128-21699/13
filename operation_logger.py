from datetime import datetime
from database import get_session
from models import OperationLog


def log_operation(operation_type, operator=None, warehouse_code=None,
                  category=None, sku=None, reference_no=None, detail=None,
                  ip_address=None):
    with get_session() as session:
        log = OperationLog(
            log_time=datetime.now(),
            operation_type=operation_type,
            operator=operator,
            warehouse_code=warehouse_code,
            category=category,
            sku=sku,
            reference_no=reference_no,
            detail=str(detail) if detail else None,
            ip_address=ip_address
        )
        session.add(log)
