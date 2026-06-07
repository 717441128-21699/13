import os
import random
from datetime import datetime, date, timedelta

from database import get_session, init_db
from models import (
    Warehouse, Product, RealtimeInventory, ERPInventory
)
from logger import setup_logger

logger = setup_logger('sample_data', 'sample_data')


def seed_sample_data():
    init_db()
    logger.info("开始生成示例数据...")

    with get_session() as session:
        if session.query(Warehouse).count() > 0:
            logger.info("已有数据，跳过生成")
            return

        warehouses = [
            {'code': 'WH001', 'name': '上海一号仓', 'location': '上海市浦东新区', 'supervisor': 'supervisor_wh001'},
            {'code': 'WH002', 'name': '广州二号仓', 'location': '广州市天河区', 'supervisor': 'supervisor_wh002'},
            {'code': 'WH003', 'name': '成都三号仓', 'location': '成都市高新区', 'supervisor': 'supervisor_wh003'},
        ]
        for w in warehouses:
            session.add(Warehouse(**w))

        categories = ['A类', 'B类', 'C类']
        products_data = []
        for i in range(1, 101):
            cat = categories[i % 3]
            products_data.append({
                'sku': f'SKU{i:05d}',
                'name': f'商品{i:05d}',
                'category': cat,
                'unit': '件',
                'unit_price': round(random.uniform(10, 2000), 2)
            })
        for p in products_data:
            session.add(Product(**p))
        session.flush()

        products = session.query(Product).all()
        now = datetime.now()

        for wh in ['WH001', 'WH002', 'WH003']:
            for product in products:
                erp_qty = random.randint(0, 500)
                diff = random.randint(-10, 10)
                if random.random() < 0.15:
                    diff = random.randint(-50, 50)
                rt_qty = max(0, erp_qty + diff)

                session.add(ERPInventory(
                    warehouse_code=wh,
                    sku=product.sku,
                    quantity=erp_qty,
                    snapshot_time=now
                ))
                session.add(RealtimeInventory(
                    warehouse_code=wh,
                    sku=product.sku,
                    quantity=rt_qty,
                    snapshot_time=now
                ))

    logger.info(f"示例数据生成完成：{len(warehouses)}仓库, {len(products_data)}商品")


def seed_historical_data():
    logger.info("生成历史差异数据（用于测试专项审计和月度统计）...")

    from models import InventoryDifference
    with get_session() as session:
        if session.query(InventoryDifference).count() > 0:
            logger.info("已有差异数据，跳过历史数据生成")
            return

        today = date.today()
        categories = ['A类', 'B类', 'C类']

        for month_offset in range(6, 0, -1):
            ref_date = today.replace(day=1) - timedelta(days=month_offset * 28)
            for day in range(1, min(29, ref_date.day + 1), 7):
                try:
                    d = ref_date.replace(day=day)
                except ValueError:
                    continue

                for wh in ['WH001', 'WH002', 'WH003']:
                    for i in range(30):
                        sku = f'SKU{(i % 100) + 1:05d}'
                        cat = categories[i % 3]
                        erp_qty = random.randint(100, 500)

                        if cat == 'A类' and wh in ('WH001',):
                            high_diff = random.random() < 0.4
                            diff_qty = random.randint(-50, 50) if high_diff else random.randint(-5, 5)
                        else:
                            diff_qty = random.randint(-5, 5)

                        rt_qty = erp_qty + diff_qty
                        unit_price = random.uniform(50, 500)
                        diff_amount = abs(diff_qty) * unit_price
                        diff_rate = abs(diff_qty) / erp_qty if erp_qty > 0 else 0

                        is_over = abs(diff_qty) > 5 or diff_amount > 1000

                        diff_obj = InventoryDifference(
                            check_date=d,
                            warehouse_code=wh,
                            sku=sku,
                            product_name=f'商品{(i % 100) + 1:05d}',
                            category=cat,
                            realtime_qty=rt_qty,
                            erp_qty=erp_qty,
                            diff_qty=diff_qty,
                            diff_type='盘盈' if diff_qty > 0 else ('盘亏' if diff_qty < 0 else '一致'),
                            unit_price=unit_price,
                            diff_amount=diff_amount,
                            diff_rate=diff_rate,
                            is_over_threshold=is_over,
                            status='resolved' if random.random() < 0.7 else 'pending'
                        )
                        session.add(diff_obj)

    logger.info("历史差异数据生成完成")
