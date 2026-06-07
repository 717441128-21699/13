import os
from datetime import date, datetime, timedelta
from collections import defaultdict

import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib as mpl

try:
    mpl.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS', 'DejaVu Sans']
    mpl.rcParams['axes.unicode_minus'] = False
except Exception:
    pass

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
)

from database import get_session
from models import (
    InventoryDifference, WorkOrder, StockCheckTask, StockCheckItem,
    MonthlyStats, Warehouse
)
from config import REPORT_DIR, EXPORT_DIR
from logger import setup_logger
from operation_logger import log_operation

logger = setup_logger('monthly_stats', 'monthly_stats')


def _ensure_dir(d):
    os.makedirs(d, exist_ok=True)
    return d


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


def generate_monthly_stats(stat_month=None):
    if not stat_month:
        today = date.today()
        first_day = today.replace(day=1)
        last_month = first_day - timedelta(days=1)
        stat_month = _get_month_key(last_month)

    logger.info(f"生成 {stat_month} 月度统计")

    y, m = map(int, stat_month.split('-'))
    if m == 12:
        next_y, next_m = y + 1, 1
    else:
        next_y, next_m = y, m + 1
    start_date = date(y, m, 1)
    end_date = date(next_y, next_m, 1) - timedelta(days=1)

    with get_session() as session:
        warehouses = session.query(Warehouse).all()
        wh_codes = [w.code for w in warehouses]
        if not wh_codes:
            wh_codes = ['WH001', 'WH002', 'WH003']

        diffs = session.query(InventoryDifference).filter(
            InventoryDifference.check_date >= start_date,
            InventoryDifference.check_date <= end_date
        ).all()

        orders = session.query(WorkOrder).filter(
            WorkOrder.created_at >= datetime(y, m, 1),
            WorkOrder.created_at < datetime(next_y, next_m, 1)
        ).all()

        tasks = session.query(StockCheckTask).filter(
            StockCheckTask.created_at >= datetime(y, m, 1),
            StockCheckTask.created_at < datetime(next_y, next_m, 1)
        ).all()

    warehouse_data = defaultdict(lambda: {
        'total_items': 0,
        'checked_items': 0,
        'diff_items': 0,
        'resolved_items': 0,
        'process_hours': [],
        'total_diff_amount': 0.0
    })

    for d in diffs:
        wd = warehouse_data[d.warehouse_code]
        wd['total_items'] += 1
        wd['checked_items'] += 1
        if d.diff_qty != 0:
            wd['diff_items'] += 1
        if d.status in ('resolved', 'ledger_updated', 'completed'):
            wd['resolved_items'] += 1
        wd['total_diff_amount'] += d.diff_amount

    for o in orders:
        wd = warehouse_data[o.warehouse_code]
        if o.assigned_at and o.completed_at:
            hours = (o.completed_at - o.assigned_at).total_seconds() / 3600
            wd['process_hours'].append(hours)

    for t in tasks:
        wd = warehouse_data[t.warehouse_code]
        wd['checked_items'] += len(t.items)

    results = []
    for wh_code in set(list(warehouse_data.keys()) + wh_codes):
        wd = warehouse_data[wh_code]
        completion_rate = (
            wd['checked_items'] / wd['total_items'] * 100
            if wd['total_items'] > 0 else 0.0
        )
        resolution_rate = (
            wd['resolved_items'] / wd['diff_items'] * 100
            if wd['diff_items'] > 0 else 0.0
        )
        avg_hours = sum(wd['process_hours']) / len(wd['process_hours']) if wd['process_hours'] else 0.0

        with get_session() as session:
            existing = session.query(MonthlyStats).filter(
                MonthlyStats.stat_month == stat_month,
                MonthlyStats.warehouse_code == wh_code
            ).first()
            if existing:
                existing.total_items = wd['total_items']
                existing.checked_items = wd['checked_items']
                existing.completion_rate = completion_rate
                existing.diff_items = wd['diff_items']
                existing.resolved_items = wd['resolved_items']
                existing.resolution_rate = resolution_rate
                existing.avg_process_hours = avg_hours
                existing.total_diff_amount = wd['total_diff_amount']
            else:
                stat = MonthlyStats(
                    stat_month=stat_month,
                    warehouse_code=wh_code,
                    total_items=wd['total_items'],
                    checked_items=wd['checked_items'],
                    completion_rate=completion_rate,
                    diff_items=wd['diff_items'],
                    resolved_items=wd['resolved_items'],
                    resolution_rate=resolution_rate,
                    avg_process_hours=avg_hours,
                    total_diff_amount=wd['total_diff_amount']
                )
                session.add(stat)

        results.append({
            'stat_month': stat_month,
            'warehouse': wh_code,
            'total_items': wd['total_items'],
            'checked_items': wd['checked_items'],
            'completion_rate': round(completion_rate, 2),
            'diff_items': wd['diff_items'],
            'resolved_items': wd['resolved_items'],
            'resolution_rate': round(resolution_rate, 2),
            'avg_process_hours': round(avg_hours, 2),
            'total_diff_amount': round(wd['total_diff_amount'], 2)
        })

    log_operation(
        operation_type='MONTHLY_STATS',
        detail=f"月份:{stat_month},仓库数:{len(results)}"
    )
    logger.info(f"月度统计完成，共 {len(results)} 个仓库")
    return results


def generate_trend_charts(months, output_dir):
    _ensure_dir(output_dir)
    paths = []

    try:
        with get_session() as session:
            all_stats = session.query(MonthlyStats).filter(
                MonthlyStats.stat_month.in_(months)
            ).all()

        data_by_wh = defaultdict(dict)
        for s in all_stats:
            data_by_wh[s.warehouse_code][s.stat_month] = s

        warehouses = list(data_by_wh.keys()) or ['WH001']

        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle('库存盘点KPI趋势分析', fontsize=16, fontweight='bold')

        ax1 = axes[0, 0]
        for wh in warehouses:
            rates = []
            for m in months:
                s = data_by_wh[wh].get(m)
                rates.append(s.completion_rate if s else 0)
            ax1.plot(months, rates, marker='o', label=wh, linewidth=2)
        ax1.set_title('盘点完成率趋势 (%)')
        ax1.set_ylabel('完成率 %')
        ax1.set_ylim(0, 110)
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        ax2 = axes[0, 1]
        for wh in warehouses:
            rates = []
            for m in months:
                s = data_by_wh[wh].get(m)
                rates.append(s.resolution_rate if s else 0)
        ax2.plot(months, rates, marker='s', label=wh, linewidth=2)
        ax2.set_title('差异解决率趋势 (%)')
        ax2.set_ylabel('解决率 %')
        ax2.set_ylim(0, 110)
        ax2.legend()
        ax2.grid(True, alpha=0.3)

        ax3 = axes[1, 0]
        for wh in warehouses:
            hours = []
            for m in months:
                s = data_by_wh[wh].get(m)
                hours.append(s.avg_process_hours if s else 0)
        ax3.bar(months, hours, alpha=0.7, label=warehouses[0])
        ax3.set_title('平均处理时长 (小时)')
        ax3.set_ylabel('小时')
        ax3.grid(True, alpha=0.3, axis='y')

        ax4 = axes[1, 1]
        for wh in warehouses:
            amounts = []
            for m in months:
                s = data_by_wh[wh].get(m)
                amounts.append(s.total_diff_amount if s else 0)
        ax4.plot(months, amounts, marker='^', label=wh, linewidth=2)
        ax4.set_title('总差异金额趋势')
        ax4.set_ylabel('金额')
        ax4.legend()
        ax4.grid(True, alpha=0.3)

        for ax in axes.flat:
            for label in ax.get_xticklabels():
                label.set_rotation(30)
                label.set_ha('right')

        plt.tight_layout(rect=[0, 0, 1, 0.95])
        p = os.path.join(output_dir, 'trend_charts.png')
        fig.savefig(p, dpi=150, bbox_inches='tight')
        plt.close(fig)
        paths.append(p)
    except Exception as e:
        logger.error(f"生成趋势图表失败: {e}")

    return paths


def generate_monthly_report(stat_month=None, output_format='both'):
    if not stat_month:
        today = date.today()
        first_day = today.replace(day=1)
        last_month = first_day - timedelta(days=1)
        stat_month = _get_month_key(last_month)

    stats = generate_monthly_stats(stat_month)
    last_6_months = _last_n_months(6)
    chart_dir = os.path.join(REPORT_DIR, f'monthly_{stat_month}')
    trend_charts = generate_trend_charts(last_6_months, chart_dir)

    result = {}
    _ensure_dir(EXPORT_DIR)
    _ensure_dir(REPORT_DIR)

    if output_format in ('excel', 'both'):
        excel_path = os.path.join(EXPORT_DIR, f'monthly_report_{stat_month}.xlsx')
        with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
            pd.DataFrame(stats).to_excel(writer, sheet_name='月度统计', index=False)

            with get_session() as session:
                trend_data = []
                all_stats = session.query(MonthlyStats).filter(
                    MonthlyStats.stat_month.in_(last_6_months)
                ).all()
                for s in all_stats:
                    trend_data.append({
                        '月份': s.stat_month,
                        '仓库': s.warehouse_code,
                        '盘点完成率(%)': round(s.completion_rate, 2),
                        '差异解决率(%)': round(s.resolution_rate, 2),
                        '平均处理时长(小时)': round(s.avg_process_hours, 2),
                        '总差异金额': round(s.total_diff_amount, 2)
                    })
                pd.DataFrame(trend_data).to_excel(writer, sheet_name='趋势数据', index=False)
        result['excel'] = excel_path
        logger.info(f"月度报告Excel已生成: {excel_path}")

    if output_format in ('pdf', 'both'):
        pdf_path = os.path.join(REPORT_DIR, f'monthly_report_{stat_month}.pdf')
        doc = SimpleDocTemplate(pdf_path, pagesize=A4,
                                leftMargin=20 * mm, rightMargin=20 * mm,
                                topMargin=15 * mm, bottomMargin=15 * mm)
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('Title', parent=styles['Title'], fontSize=18, spaceAfter=12)
        h2 = ParagraphStyle('H2', parent=styles['Heading2'], fontSize=13, spaceAfter=8)

        story = [
            Paragraph(f'月度库存盘点分析报告 - {stat_month}', title_style),
            Paragraph(f'生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', styles['Normal']),
            Spacer(1, 6 * mm),
            Paragraph('各仓库KPI指标', h2)
        ]

        header = ['仓库', '总条目', '完成率(%)', '差异数', '解决率(%)', '平均处理(小时)', '差异金额']
        table_data = [header]
        for s in stats:
            table_data.append([
                s['warehouse'], str(s['total_items']), str(s['completion_rate']),
                str(s['diff_items']), str(s['resolution_rate']),
                str(s['avg_process_hours']), f"{s['total_diff_amount']:.2f}"
            ])
        t = Table(table_data, colWidths=[22 * mm, 18 * mm, 22 * mm, 18 * mm, 22 * mm, 28 * mm, 28 * mm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#ecf0f1')])
        ]))
        story.append(t)
        story.append(Spacer(1, 6 * mm))

        for cp in trend_charts:
            if os.path.exists(cp):
                story.append(Paragraph('趋势分析图表', h2))
                story.append(Image(cp, width=170 * mm, height=120 * mm))
                story.append(Spacer(1, 4 * mm))

        doc.build(story)
        result['pdf'] = pdf_path
        logger.info(f"月度报告PDF已生成: {pdf_path}")

    return result
