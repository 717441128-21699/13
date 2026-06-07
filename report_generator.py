import os
import io
from datetime import date, datetime
from collections import defaultdict, OrderedDict

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
    InventoryDifference, StockCheckTask, StockCheckItem, WorkOrder,
    Product, Warehouse
)
from config import REPORT_DIR, EXPORT_DIR
from logger import setup_logger

logger = setup_logger('report', 'report')


def _ensure_dir(d):
    os.makedirs(d, exist_ok=True)
    return d


def generate_diff_summary(check_date=None):
    check_date = check_date or date.today()
    with get_session() as session:
        diffs = session.query(InventoryDifference).filter(
            InventoryDifference.check_date == check_date
        ).all()

    summary = {
        'date': str(check_date),
        'total': len(diffs),
        'surplus': sum(1 for d in diffs if d.diff_type == '盘盈'),
        'deficit': sum(1 for d in diffs if d.diff_type == '盘亏'),
        'matched': sum(1 for d in diffs if d.diff_type == '一致'),
        'over_threshold': sum(1 for d in diffs if d.is_over_threshold),
        'total_diff_amount': sum(d.diff_amount for d in diffs),
        'by_warehouse': defaultdict(lambda: {
            'total': 0, 'surplus': 0, 'deficit': 0, 'amount': 0.0
        }),
        'by_category': defaultdict(lambda: {
            'total': 0, 'surplus': 0, 'deficit': 0, 'amount': 0.0
        })
    }
    for d in diffs:
        wh = summary['by_warehouse'][d.warehouse_code]
        wh['total'] += 1
        if d.diff_type == '盘盈':
            wh['surplus'] += 1
        elif d.diff_type == '盘亏':
            wh['deficit'] += 1
        wh['amount'] += d.diff_amount

        cat = summary['by_category'][d.category or '未分类']
        cat['total'] += 1
        if d.diff_type == '盘盈':
            cat['surplus'] += 1
        elif d.diff_type == '盘亏':
            cat['deficit'] += 1
        cat['amount'] += d.diff_amount

    summary['by_warehouse'] = dict(summary['by_warehouse'])
    summary['by_category'] = dict(summary['by_category'])
    return summary


def generate_diff_charts(summary, output_dir):
    _ensure_dir(output_dir)
    chart_paths = []

    try:
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle(f'库存差异分析报告 - {summary["date"]}', fontsize=16, fontweight='bold')

        ax1 = axes[0, 0]
        labels = ['盘盈', '盘亏', '一致', '超阈值']
        values = [summary['surplus'], summary['deficit'], summary['matched'], summary['over_threshold']]
        colors_list = ['#2ecc71', '#e74c3c', '#3498db', '#f39c12']
        bars = ax1.bar(labels, values, color=colors_list)
        ax1.set_title('差异类型分布')
        ax1.set_ylabel('条目数')
        for bar, v in zip(bars, values):
            ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                     str(v), ha='center', va='bottom')

        ax2 = axes[0, 1]
        if summary['by_warehouse']:
            whs = list(summary['by_warehouse'].keys())
            x = range(len(whs))
            surplus_vals = [summary['by_warehouse'][w]['surplus'] for w in whs]
            deficit_vals = [summary['by_warehouse'][w]['deficit'] for w in whs]
            width = 0.35
            ax2.bar([i - width / 2 for i in x], surplus_vals, width, label='盘盈', color='#2ecc71')
            ax2.bar([i + width / 2 for i in x], deficit_vals, width, label='盘亏', color='#e74c3c')
            ax2.set_xticks(x)
            ax2.set_xticklabels(whs, rotation=45)
            ax2.set_title('各仓库差异分布')
            ax2.legend()
        else:
            ax2.text(0.5, 0.5, '无数据', ha='center')
            ax2.set_title('各仓库差异分布')

        ax3 = axes[1, 0]
        if summary['by_category']:
            cats = list(summary['by_category'].keys())
            amounts = [summary['by_category'][c]['amount'] for c in cats]
            ax3.pie(amounts, labels=cats, autopct='%1.1f%%', startangle=90)
            ax3.set_title('差异金额品类分布')
        else:
            ax3.text(0.5, 0.5, '无数据', ha='center')
            ax3.set_title('差异金额品类分布')

        ax4 = axes[1, 1]
        if summary['by_category']:
            cats = list(summary['by_category'].keys())
            rates = []
            for c in cats:
                s = summary['by_category'][c]
                total = s['surplus'] + s['deficit']
                rates.append(total / s['total'] * 100 if s['total'] > 0 else 0)
            bars = ax4.barh(cats, rates, color='#9b59b6')
            ax4.set_title('品类差异率 (%)')
            ax4.set_xlabel('差异率 %')
            for bar, v in zip(bars, rates):
                ax4.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height() / 2,
                         f'{v:.1f}%', va='center')
        else:
            ax4.text(0.5, 0.5, '无数据', ha='center')
            ax4.set_title('品类差异率 (%)')

        plt.tight_layout(rect=[0, 0, 1, 0.95])
        chart_path = os.path.join(output_dir, 'diff_charts.png')
        fig.savefig(chart_path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        chart_paths.append(chart_path)
    except Exception as e:
        logger.error(f"生成图表失败: {e}")

    return chart_paths


def generate_diff_report_excel(check_date=None, output_path=None):
    check_date = check_date or date.today()
    _ensure_dir(EXPORT_DIR)
    if not output_path:
        output_path = os.path.join(EXPORT_DIR, f'diff_report_{check_date}.xlsx')

    with get_session() as session:
        diffs = session.query(InventoryDifference).filter(
            InventoryDifference.check_date == check_date
        ).all()

        data = []
        for d in diffs:
            data.append({
                '盘点日期': str(d.check_date),
                '仓库': d.warehouse_code,
                'SKU': d.sku,
                '商品名称': d.product_name,
                '品类': d.category or '',
                '实时库存': d.realtime_qty,
                'ERP账面': d.erp_qty,
                '差异数量': d.diff_qty,
                '差异类型': d.diff_type,
                '单价': d.unit_price,
                '差异金额': d.diff_amount,
                '差异率': f'{d.diff_rate * 100:.2f}%',
                '是否超阈值': '是' if d.is_over_threshold else '否',
                '状态': d.status,
                '创建时间': d.created_at.strftime('%Y-%m-%d %H:%M:%S') if d.created_at else ''
            })

    summary = generate_diff_summary(check_date)
    chart_paths = generate_diff_charts(summary, REPORT_DIR)

    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        pd.DataFrame(data).to_excel(writer, sheet_name='差异明细', index=False)

        summary_df = pd.DataFrame([{
            '盘点日期': summary['date'],
            '总条目数': summary['total'],
            '盘盈数': summary['surplus'],
            '盘亏数': summary['deficit'],
            '一致数': summary['matched'],
            '超阈值数': summary['over_threshold'],
            '总差异金额': round(summary['total_diff_amount'], 2)
        }])
        summary_df.to_excel(writer, sheet_name='汇总', index=False)

        wh_data = []
        for wh, s in summary['by_warehouse'].items():
            wh_data.append({
                '仓库': wh,
                '总条目': s['total'],
                '盘盈': s['surplus'],
                '盘亏': s['deficit'],
                '差异金额': round(s['amount'], 2)
            })
        pd.DataFrame(wh_data).to_excel(writer, sheet_name='仓库汇总', index=False)

        cat_data = []
        for cat, s in summary['by_category'].items():
            cat_data.append({
                '品类': cat,
                '总条目': s['total'],
                '盘盈': s['surplus'],
                '盘亏': s['deficit'],
                '差异金额': round(s['amount'], 2)
            })
        pd.DataFrame(cat_data).to_excel(writer, sheet_name='品类汇总', index=False)

    logger.info(f"差异报告Excel已生成: {output_path}")
    return output_path


def generate_diff_report_pdf(check_date=None, output_path=None):
    check_date = check_date or date.today()
    _ensure_dir(REPORT_DIR)
    if not output_path:
        output_path = os.path.join(REPORT_DIR, f'diff_report_{check_date}.pdf')

    summary = generate_diff_summary(check_date)
    chart_paths = generate_diff_charts(summary, REPORT_DIR)

    doc = SimpleDocTemplate(output_path, pagesize=A4,
                            leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=15 * mm, bottomMargin=15 * mm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('CustomTitle', parent=styles['Title'], fontSize=18, spaceAfter=12)
    h2_style = ParagraphStyle('H2', parent=styles['Heading2'], fontSize=13, spaceAfter=8)
    normal_style = styles['Normal']

    story = []
    story.append(Paragraph(f'库存差异报告 - {check_date}', title_style))
    story.append(Paragraph(f'生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', normal_style))
    story.append(Spacer(1, 6 * mm))

    summary_data = [
        ['指标', '数值'],
        ['总条目数', str(summary['total'])],
        ['盘盈数', str(summary['surplus'])],
        ['盘亏数', str(summary['deficit'])],
        ['一致数', str(summary['matched'])],
        ['超阈值数', str(summary['over_threshold'])],
        ['总差异金额', f'{summary["total_diff_amount"]:.2f}']
    ]
    t = Table(summary_data, colWidths=[80 * mm, 50 * mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#ecf0f1')])
    ]))
    story.append(t)
    story.append(Spacer(1, 8 * mm))

    for cp in chart_paths:
        if os.path.exists(cp):
            story.append(Paragraph('差异分析图表', h2_style))
            img = Image(cp, width=170 * mm, height=120 * mm)
            story.append(img)
            story.append(Spacer(1, 6 * mm))

    story.append(Paragraph('各仓库差异汇总', h2_style))
    wh_table_data = [['仓库', '总条目', '盘盈', '盘亏', '差异金额']]
    for wh, s in summary['by_warehouse'].items():
        wh_table_data.append([wh, str(s['total']), str(s['surplus']),
                              str(s['deficit']), f'{s["amount"]:.2f}'])
    t2 = Table(wh_table_data, colWidths=[30 * mm, 25 * mm, 25 * mm, 25 * mm, 40 * mm])
    t2.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2ecc71')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#ecf0f1')])
    ]))
    story.append(t2)

    doc.build(story)
    logger.info(f"差异报告PDF已生成: {output_path}")
    return output_path


def generate_stock_check_report(task_no, output_format='both'):
    task_info = None
    items_data = []
    total = 0
    scanned = 0
    matched = 0
    diff = 0
    total_diff_amount = 0.0
    category_diff = defaultdict(lambda: {'count': 0, 'diff': 0, 'amount': 0.0})

    with get_session() as session:
        task = session.query(StockCheckTask).filter(
            StockCheckTask.task_no == task_no
        ).first()
        if not task:
            raise ValueError(f"任务 {task_no} 不存在")

        task_info = {
            'task_no': task.task_no,
            'warehouse_code': task.warehouse_code,
            'task_type': task.task_type
        }

        products = {p.sku: p for p in session.query(Product).all()}

        items = task.items
        total = len(items)
        scanned = sum(1 for i in items if i.is_scanned)
        matched = sum(1 for i in items if i.is_scanned and i.scanned_qty == i.system_qty)
        diff_items = [i for i in items if i.is_scanned and i.scanned_qty != i.system_qty]
        diff = len(diff_items)

        for i in diff_items:
            p = products.get(i.sku)
            price = p.unit_price if p else 0.0
            total_diff_amount += abs((i.scanned_qty - i.system_qty) * price)

        for item in items:
            p = products.get(item.sku)
            cat = p.category if p else '未分类'
            price = p.unit_price if p else 0.0
            category_diff[cat]['count'] += 1
            if item.is_scanned and item.scanned_qty != item.system_qty:
                category_diff[cat]['diff'] += 1
                category_diff[cat]['amount'] += abs(item.scanned_qty - item.system_qty) * price

            items_data.append({
                'sku': item.sku,
                'product_name': item.product_name,
                'system_qty': item.system_qty,
                'scanned_qty': item.scanned_qty,
                'is_scanned': item.is_scanned,
                'scanned_at': item.scanned_at.strftime('%Y-%m-%d %H:%M:%S') if item.scanned_at else '',
                'scanner': item.scanner or ''
            })

    result = {}
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    _ensure_dir(EXPORT_DIR)
    _ensure_dir(REPORT_DIR)

    if output_format in ('excel', 'both'):
        excel_path = os.path.join(EXPORT_DIR, f'stock_check_{task_no}_{timestamp}.xlsx')
        detail_data = []
        for item in items_data:
            diff_qty = (item['scanned_qty'] - item['system_qty']) if item['is_scanned'] else None
            detail_data.append({
                'SKU': item['sku'],
                '商品名称': item['product_name'],
                '系统数量': item['system_qty'],
                '扫码数量': item['scanned_qty'] if item['is_scanned'] else '',
                '差异数量': diff_qty if diff_qty is not None else '',
                '是否扫码': '是' if item['is_scanned'] else '否',
                '扫码时间': item['scanned_at'],
                '扫码人': item['scanner']
            })

        with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
            pd.DataFrame(detail_data).to_excel(writer, sheet_name='盘点明细', index=False)

            summary_df = pd.DataFrame([{
                '任务编号': task_no,
                '仓库': task_info['warehouse_code'],
                '盘点类型': '全盘' if task_info['task_type'] == 'full' else '抽盘',
                '总条目': total,
                '已扫描': scanned,
                '一致': matched,
                '差异': diff,
                '总差异金额': round(total_diff_amount, 2),
                '扫描完成率': f'{scanned / total * 100:.1f}%' if total > 0 else '0%',
                '差异率': f'{diff / scanned * 100:.1f}%' if scanned > 0 else '0%'
            }])
            summary_df.to_excel(writer, sheet_name='汇总', index=False)

            cat_df = pd.DataFrame([{
                '品类': cat,
                '总条目': s['count'],
                '差异条目': s['diff'],
                '差异金额': round(s['amount'], 2)
            } for cat, s in category_diff.items()])
            cat_df.to_excel(writer, sheet_name='品类分析', index=False)

            try:
                chart_dir = os.path.join(REPORT_DIR, f'check_{task_no}')
                _ensure_dir(chart_dir)
                _generate_stock_check_charts(task_no, {
                    'total': total, 'scanned': scanned, 'matched': matched,
                    'diff': diff, 'diff_amount': total_diff_amount,
                    'category_diff': dict(category_diff)
                }, chart_dir)
            except Exception as e:
                logger.error(f"生成盘点图表失败: {e}")

        result['excel'] = excel_path
        logger.info(f"盘点报告Excel已生成: {excel_path}")

    if output_format in ('pdf', 'both'):
        pdf_path = os.path.join(REPORT_DIR, f'stock_check_{task_no}_{timestamp}.pdf')
        chart_dir = os.path.join(REPORT_DIR, f'check_{task_no}')
        _ensure_dir(chart_dir)
        chart_paths = _generate_stock_check_charts(task_no, {
            'total': total, 'scanned': scanned, 'matched': matched,
            'diff': diff, 'diff_amount': total_diff_amount,
            'category_diff': dict(category_diff)
        }, chart_dir)

        doc = SimpleDocTemplate(pdf_path, pagesize=A4,
                                leftMargin=20 * mm, rightMargin=20 * mm,
                                topMargin=15 * mm, bottomMargin=15 * mm)
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('Title', parent=styles['Title'], fontSize=18, spaceAfter=12)
        h2 = ParagraphStyle('H2', parent=styles['Heading2'], fontSize=13, spaceAfter=8)

        story = [
            Paragraph(f'盘点任务报告 - {task_no}', title_style),
            Paragraph(f'仓库: {task_info["warehouse_code"]} | 类型: {task_info["task_type"]} | 生成: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', styles['Normal']),
            Spacer(1, 6 * mm)
        ]

        sum_data = [
            ['指标', '数值'],
            ['总条目', str(total)],
            ['已扫描', str(scanned)],
            ['一致', str(matched)],
            ['差异', str(diff)],
            ['总差异金额', f'{total_diff_amount:.2f}'],
            ['扫描完成率', f'{scanned / total * 100:.1f}%' if total > 0 else '0%']
        ]
        t = Table(sum_data, colWidths=[80 * mm, 50 * mm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
        ]))
        story.append(t)
        story.append(Spacer(1, 6 * mm))

        for cp in chart_paths:
            if os.path.exists(cp):
                story.append(Image(cp, width=160 * mm, height=100 * mm))
                story.append(Spacer(1, 4 * mm))

        doc.build(story)
        result['pdf'] = pdf_path
        logger.info(f"盘点报告PDF已生成: {pdf_path}")

    return result


def _generate_stock_check_charts(task_no, data, output_dir):
    _ensure_dir(output_dir)
    paths = []

    try:
        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        fig.suptitle(f'盘点任务分析 - {task_no}', fontsize=14, fontweight='bold')

        ax1 = axes[0]
        labels = ['已扫描', '一致', '差异']
        vals = [data['scanned'], data['matched'], data['diff']]
        cs = ['#3498db', '#2ecc71', '#e74c3c']
        bars = ax1.bar(labels, vals, color=cs)
        ax1.set_title('盘点结果统计')
        for b, v in zip(bars, vals):
            ax1.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.3, str(v), ha='center')

        ax2 = axes[1]
        if data['category_diff']:
            cats = list(data['category_diff'].keys())
            diff_vals = [data['category_diff'][c]['diff'] for c in cats]
            bars = ax2.barh(cats, diff_vals, color='#e67e22')
            ax2.set_title('品类差异分布')
            for b, v in zip(bars, diff_vals):
                ax2.text(b.get_width() + 0.1, b.get_y() + b.get_height() / 2, str(v), va='center')
        else:
            ax2.text(0.5, 0.5, '无数据', ha='center')
            ax2.set_title('品类差异分布')

        plt.tight_layout()
        p = os.path.join(output_dir, 'charts.png')
        fig.savefig(p, dpi=150, bbox_inches='tight')
        plt.close(fig)
        paths.append(p)
    except Exception as e:
        logger.error(f"生成盘点图表失败: {e}")

    return paths
