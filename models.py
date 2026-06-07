from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean, Date
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Warehouse(Base):
    __tablename__ = 'warehouses'
    id = Column(Integer, primary_key=True)
    code = Column(String(20), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    location = Column(String(200))
    supervisor = Column(String(100))


class Product(Base):
    __tablename__ = 'products'
    id = Column(Integer, primary_key=True)
    sku = Column(String(50), unique=True, nullable=False)
    name = Column(String(200), nullable=False)
    category = Column(String(50))
    unit = Column(String(20))
    unit_price = Column(Float, default=0.0)


class RealtimeInventory(Base):
    __tablename__ = 'realtime_inventory'
    id = Column(Integer, primary_key=True)
    warehouse_code = Column(String(20), nullable=False)
    sku = Column(String(50), nullable=False)
    quantity = Column(Float, default=0.0)
    snapshot_time = Column(DateTime, default=datetime.now)


class ERPInventory(Base):
    __tablename__ = 'erp_inventory'
    id = Column(Integer, primary_key=True)
    warehouse_code = Column(String(20), nullable=False)
    sku = Column(String(50), nullable=False)
    quantity = Column(Float, default=0.0)
    snapshot_time = Column(DateTime, default=datetime.now)


class InventoryDifference(Base):
    __tablename__ = 'inventory_differences'
    id = Column(Integer, primary_key=True)
    check_date = Column(Date, nullable=False)
    warehouse_code = Column(String(20), nullable=False)
    sku = Column(String(50), nullable=False)
    product_name = Column(String(200))
    category = Column(String(50))
    realtime_qty = Column(Float, default=0.0)
    erp_qty = Column(Float, default=0.0)
    diff_qty = Column(Float, default=0.0)
    diff_type = Column(String(10))
    unit_price = Column(Float, default=0.0)
    diff_amount = Column(Float, default=0.0)
    diff_rate = Column(Float, default=0.0)
    is_over_threshold = Column(Boolean, default=False)
    work_order_id = Column(Integer, ForeignKey('work_orders.id'))
    status = Column(String(20), default='pending')
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    work_order = relationship('WorkOrder', back_populates='differences')


class WorkOrder(Base):
    __tablename__ = 'work_orders'
    id = Column(Integer, primary_key=True)
    order_no = Column(String(50), unique=True, nullable=False)
    warehouse_code = Column(String(20), nullable=False)
    category = Column(String(50))
    diff_type = Column(String(10))
    auditor = Column(String(100))
    supervisor = Column(String(100))
    status = Column(String(20), default='pending')
    priority = Column(String(10), default='normal')
    is_upgraded = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    assigned_at = Column(DateTime)
    upgraded_at = Column(DateTime)
    reviewed_at = Column(DateTime)
    completed_at = Column(DateTime)
    review_comment = Column(Text)
    differences = relationship('InventoryDifference', back_populates='work_order')


class InventoryLedger(Base):
    __tablename__ = 'inventory_ledger'
    id = Column(Integer, primary_key=True)
    ledger_date = Column(Date, nullable=False)
    warehouse_code = Column(String(20), nullable=False)
    sku = Column(String(50), nullable=False)
    product_name = Column(String(200))
    before_qty = Column(Float, default=0.0)
    adjust_qty = Column(Float, default=0.0)
    after_qty = Column(Float, default=0.0)
    unit_price = Column(Float, default=0.0)
    adjust_amount = Column(Float, default=0.0)
    reason = Column(String(200))
    reference_no = Column(String(50))
    operator = Column(String(100))
    created_at = Column(DateTime, default=datetime.now)


class SpecialAudit(Base):
    __tablename__ = 'special_audits'
    id = Column(Integer, primary_key=True)
    audit_no = Column(String(50), unique=True, nullable=False)
    warehouse_code = Column(String(20), nullable=False)
    category = Column(String(50), nullable=False)
    trigger_month = Column(String(20), nullable=False)
    consecutive_months = Column(Integer, default=0)
    avg_diff_rate = Column(Float, default=0.0)
    status = Column(String(20), default='pending')
    auditor = Column(String(100))
    created_at = Column(DateTime, default=datetime.now)
    completed_at = Column(DateTime)
    audit_report = Column(Text)


class StockCheckTask(Base):
    __tablename__ = 'stock_check_tasks'
    id = Column(Integer, primary_key=True)
    task_no = Column(String(50), unique=True, nullable=False)
    task_type = Column(String(20), nullable=False)
    warehouse_code = Column(String(20), nullable=False)
    category = Column(String(50))
    sample_ratio = Column(Float)
    status = Column(String(20), default='created')
    operator = Column(String(100))
    created_at = Column(DateTime, default=datetime.now)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    items = relationship('StockCheckItem', back_populates='task')


class StockCheckItem(Base):
    __tablename__ = 'stock_check_items'
    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey('stock_check_tasks.id'))
    sku = Column(String(50), nullable=False)
    product_name = Column(String(200))
    system_qty = Column(Float, default=0.0)
    scanned_qty = Column(Float)
    is_scanned = Column(Boolean, default=False)
    scanned_at = Column(DateTime)
    scanner = Column(String(100))
    created_at = Column(DateTime, default=datetime.now)
    task = relationship('StockCheckTask', back_populates='items')


class MonthlyStats(Base):
    __tablename__ = 'monthly_stats'
    id = Column(Integer, primary_key=True)
    stat_month = Column(String(20), nullable=False)
    warehouse_code = Column(String(20), nullable=False)
    total_items = Column(Integer, default=0)
    checked_items = Column(Integer, default=0)
    completion_rate = Column(Float, default=0.0)
    diff_items = Column(Integer, default=0)
    resolved_items = Column(Integer, default=0)
    resolution_rate = Column(Float, default=0.0)
    avg_process_hours = Column(Float, default=0.0)
    total_diff_amount = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.now)


class OperationLog(Base):
    __tablename__ = 'operation_logs'
    id = Column(Integer, primary_key=True)
    log_time = Column(DateTime, default=datetime.now)
    operation_type = Column(String(50), nullable=False)
    operator = Column(String(100))
    warehouse_code = Column(String(20))
    category = Column(String(50))
    sku = Column(String(50))
    reference_no = Column(String(50))
    detail = Column(Text)
    ip_address = Column(String(50))
