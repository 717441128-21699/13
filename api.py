import os
from datetime import datetime, date

from flask import Flask, jsonify, request, send_file, abort
from flask_cors import CORS

from database import init_db, get_session
from models import (
    InventoryDifference, WorkOrder, StockCheckTask, StockCheckItem,
    OperationLog, Product, Warehouse, MonthlyStats, SpecialAudit,
    RealtimeInventory, ERPInventory
)
from config import REPORT_DIR, EXPORT_DIR

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

init_db()


def _to_dict(obj, fields):
    return {f: getattr(obj, f) for f in fields}


def _json_default(o):
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if hasattr(o, '__float__'):
        return float(o)
    return str(o)


@app.route('/')
def index():
    return send_file(os.path.join(app.static_folder, 'index.html'))


@app.route('/api/dashboard')
def api_dashboard():
    today = date.today()
    with get_session() as session:
        today_diffs = session.query(InventoryDifference).filter(
            InventoryDifference.check_date == today
        ).all()
        pending_orders = session.query(WorkOrder).filter(
            WorkOrder.status.in_(['assigned', 'in_progress', 'upgraded', 'pending'])
        ).count()
        upgraded_orders = session.query(WorkOrder).filter(
            WorkOrder.is_upgraded == True,
            WorkOrder.status.in_(['assigned', 'in_progress', 'upgraded'])
        ).count()
        pending_audits = session.query(SpecialAudit).filter(
            SpecialAudit.status == 'pending'
        ).count()
        active_tasks = session.query(StockCheckTask).filter(
            StockCheckTask.status.in_(['created', 'pushed', 'in_progress'])
        ).count()
        completed_tasks = session.query(StockCheckTask).filter(
            StockCheckTask.status == 'completed'
        ).count()
        total_products = session.query(Product).count()
        total_warehouses = session.query(Warehouse).count()

        from sqlalchemy import func
        total_realtime = session.query(func.sum(RealtimeInventory.quantity)).scalar() or 0
        total_erp = session.query(func.sum(ERPInventory.quantity)).scalar() or 0

    by_warehouse = {}
    by_category = {}
    for d in today_diffs:
        wh = by_warehouse.setdefault(d.warehouse_code, {
            'total': 0, 'surplus': 0, 'deficit': 0, 'amount': 0.0
        })
        wh['total'] += 1
        if d.diff_type == '盘盈':
            wh['surplus'] += 1
        elif d.diff_type == '盘亏':
            wh['deficit'] += 1
        wh['amount'] += float(d.diff_amount or 0)

        cat = by_category.setdefault(d.category or '未分类', {
            'total': 0, 'surplus': 0, 'deficit': 0, 'amount': 0.0
        })
        cat['total'] += 1
        if d.diff_type == '盘盈':
            cat['surplus'] += 1
        elif d.diff_type == '盘亏':
            cat['deficit'] += 1
        cat['amount'] += float(d.diff_amount or 0)

    return jsonify({
        'today': {
            'date': str(today),
            'total': len(today_diffs),
            'surplus': sum(1 for d in today_diffs if d.diff_type == '盘盈'),
            'deficit': sum(1 for d in today_diffs if d.diff_type == '盘亏'),
            'matched': sum(1 for d in today_diffs if d.diff_type == '一致'),
            'over_threshold': sum(1 for d in today_diffs if d.is_over_threshold),
            'diff_amount': float(sum(d.diff_amount or 0 for d in today_diffs))
        },
        'pending': {
            'work_orders': pending_orders,
            'upgraded_orders': upgraded_orders,
            'special_audits': pending_audits,
            'stock_tasks': active_tasks,
            'completed_tasks': completed_tasks
        },
        'overview': {
            'products': total_products,
            'warehouses': total_warehouses,
            'realtime_qty': float(total_realtime),
            'erp_qty': float(total_erp)
        },
        'by_warehouse': by_warehouse,
        'by_category': by_category
    })


@app.route('/api/differences')
def api_differences():
    args = request.args
    with get_session() as session:
        q = session.query(InventoryDifference)
        if args.get('warehouse'):
            q = q.filter(InventoryDifference.warehouse_code == args['warehouse'])
        if args.get('category'):
            q = q.filter(InventoryDifference.category == args['category'])
        if args.get('sku'):
            q = q.filter(InventoryDifference.sku.like(f"%{args['sku']}%"))
        if args.get('diff_type'):
            q = q.filter(InventoryDifference.diff_type == args['diff_type'])
        if args.get('status'):
            q = q.filter(InventoryDifference.status == args['status'])
        if args.get('over_threshold'):
            q = q.filter(InventoryDifference.is_over_threshold == (args['over_threshold'] == 'true'))
        if args.get('start_date'):
            try:
                sd = datetime.strptime(args['start_date'], '%Y-%m-%d').date()
                q = q.filter(InventoryDifference.check_date >= sd)
            except Exception:
                pass
        if args.get('end_date'):
            try:
                ed = datetime.strptime(args['end_date'], '%Y-%m-%d').date()
                q = q.filter(InventoryDifference.check_date <= ed)
            except Exception:
                pass

        q = q.order_by(InventoryDifference.check_date.desc())
        limit = int(args.get('limit', 200))
        page = int(args.get('page', 1))
        total = q.count()
        diffs = q.offset((page - 1) * limit).limit(limit).all()

        data = []
        for d in diffs:
            data.append({
                'id': d.id,
                'check_date': str(d.check_date),
                'warehouse': d.warehouse_code,
                'sku': d.sku,
                'product_name': d.product_name,
                'category': d.category or '',
                'realtime_qty': float(d.realtime_qty),
                'erp_qty': float(d.erp_qty),
                'diff_qty': float(d.diff_qty),
                'diff_type': d.diff_type,
                'unit_price': float(d.unit_price),
                'diff_amount': float(d.diff_amount),
                'diff_rate': round(float(d.diff_rate) * 100, 2),
                'is_over_threshold': d.is_over_threshold,
                'status': d.status,
                'work_order_id': d.work_order_id
            })

    return jsonify({'total': total, 'page': page, 'limit': limit, 'data': data})


@app.route('/api/orders')
def api_orders():
    args = request.args
    with get_session() as session:
        q = session.query(WorkOrder)
        if args.get('warehouse'):
            q = q.filter(WorkOrder.warehouse_code == args['warehouse'])
        if args.get('status'):
            q = q.filter(WorkOrder.status == args['status'])
        if args.get('is_upgraded'):
            q = q.filter(WorkOrder.is_upgraded == (args['is_upgraded'] == 'true'))
        if args.get('auditor'):
            q = q.filter(WorkOrder.auditor == args['auditor'])

        q = q.order_by(WorkOrder.created_at.desc())
        orders = q.limit(200).all()

        data = []
        for o in orders:
            data.append({
                'id': o.id,
                'order_no': o.order_no,
                'warehouse': o.warehouse_code,
                'category': o.category or '',
                'diff_type': o.diff_type,
                'auditor': o.auditor,
                'supervisor': o.supervisor,
                'status': o.status,
                'priority': o.priority,
                'is_upgraded': o.is_upgraded,
                'created_at': o.created_at.isoformat() if o.created_at else None,
                'assigned_at': o.assigned_at.isoformat() if o.assigned_at else None,
                'upgraded_at': o.upgraded_at.isoformat() if o.upgraded_at else None,
                'completed_at': o.completed_at.isoformat() if o.completed_at else None,
                'review_comment': o.review_comment,
                'diff_count': len(o.differences)
            })
    return jsonify(data)


@app.route('/api/orders/<order_no>/review', methods=['POST'])
def api_review_order(order_no):
    from work_order_manager import review_work_order
    body = request.get_json(silent=True) or {}
    try:
        result = review_work_order(
            order_no=order_no,
            approved=body.get('approved', True),
            comment=body.get('comment', ''),
            operator=body.get('operator', 'web_user')
        )
        if body.get('approved'):
            from ledger_manager import update_ledger_from_work_order
            update_ledger_from_work_order(order_no, operator=body.get('operator', 'web_user'))
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/orders/<order_no>/upgrade', methods=['POST'])
def api_upgrade_order(order_no):
    from work_order_manager import check_and_upgrade_orders
    check_and_upgrade_orders()
    return jsonify({'success': True})


@app.route('/api/daily/run', methods=['POST'])
def api_run_daily():
    from inventory_compare import compare_inventory
    from work_order_manager import create_work_orders, check_and_upgrade_orders
    from special_audit import check_special_audit
    from report_generator import generate_diff_report_excel, generate_diff_report_pdf

    result = compare_inventory()
    orders = create_work_orders()
    upgraded = check_and_upgrade_orders()
    audits = check_special_audit()
    excel_path = generate_diff_report_excel()
    pdf_path = generate_diff_report_pdf()

    return jsonify({
        'success': True,
        'compare': result,
        'orders_created': len(orders),
        'upgraded': len(upgraded),
        'audits': len(audits),
        'reports': {
            'excel': os.path.basename(excel_path),
            'pdf': os.path.basename(pdf_path)
        }
    })


@app.route('/api/stock-checks', methods=['GET'])
def api_stock_check_list():
    args = request.args
    with get_session() as session:
        q = session.query(StockCheckTask)
        if args.get('warehouse'):
            q = q.filter(StockCheckTask.warehouse_code == args['warehouse'])
        if args.get('status'):
            q = q.filter(StockCheckTask.status == args['status'])
        q = q.order_by(StockCheckTask.created_at.desc())
        tasks = q.limit(200).all()

        data = []
        for t in tasks:
            scanned = sum(1 for i in t.items if i.is_scanned)
            matched = sum(1 for i in t.items if i.is_scanned and i.scanned_qty == i.system_qty)
            data.append({
                'id': t.id,
                'task_no': t.task_no,
                'task_type': t.task_type,
                'warehouse': t.warehouse_code,
                'category': t.category or '',
                'sample_ratio': t.sample_ratio,
                'status': t.status,
                'operator': t.operator,
                'created_at': t.created_at.isoformat() if t.created_at else None,
                'started_at': t.started_at.isoformat() if t.started_at else None,
                'completed_at': t.completed_at.isoformat() if t.completed_at else None,
                'total_items': len(t.items),
                'scanned_items': scanned,
                'matched_items': matched,
                'diff_items': scanned - matched
            })
        return jsonify(data)


@app.route('/api/stock-checks', methods=['POST'])
def api_create_stock_check():
    from stock_check import create_stock_check_task
    body = request.get_json(silent=True) or {}
    try:
        result = create_stock_check_task(
            task_type=body.get('task_type', 'full'),
            warehouse_code=body.get('warehouse', 'WH001'),
            category=body.get('category') or None,
            sample_ratio=float(body.get('sample_ratio', 0.3)),
            operator=body.get('operator', 'web_user')
        )
        return jsonify({'success': True, 'task': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/stock-checks/<task_no>', methods=['GET'])
def api_stock_check_detail(task_no):
    from stock_check import get_task_checklist
    try:
        data = get_task_checklist(task_no)
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 404


@app.route('/api/stock-checks/<task_no>/push', methods=['POST'])
def api_push_task(task_no):
    from stock_check import push_task_to_terminal
    try:
        payload = push_task_to_terminal(task_no)
        return jsonify({'success': True, 'payload': payload})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/scan', methods=['POST'])
def api_scan():
    body = request.get_json(silent=True) or {}
    task_no = body.get('task_no')
    item_id = body.get('item_id')
    scanned_qty = body.get('scanned_qty')
    scanner = body.get('scanner', 'web_user')
    sku = body.get('sku')

    if not task_no or (item_id is None and not sku) or scanned_qty is None:
        return jsonify({'success': False, 'error': '缺少参数: task_no, item_id(或sku), scanned_qty'}), 400

    with get_session() as session:
        from stock_check import scan_item as _scan
        try:
            if item_id is None:
                task = session.query(StockCheckTask).filter(
                    StockCheckTask.task_no == task_no
                ).first()
                if not task:
                    return jsonify({'success': False, 'error': '任务不存在'}), 404
                item = session.query(StockCheckItem).filter(
                    StockCheckItem.task_id == task.id,
                    StockCheckItem.sku == sku
                ).first()
                if not item:
                    return jsonify({'success': False, 'error': 'SKU不在该任务中'}), 404
                item_id = item.id

            result = _scan(task_no, item_id, float(scanned_qty), scanner)
            return jsonify({'success': True, 'result': result})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/stock-checks/<task_no>/complete', methods=['POST'])
def api_complete_task(task_no):
    from stock_check import complete_stock_check_task
    from report_generator import generate_stock_check_report
    body = request.get_json(silent=True) or {}
    try:
        summary = complete_stock_check_task(task_no, operator=body.get('operator', 'web_user'))
        report_paths = generate_stock_check_report(task_no)
        return jsonify({
            'success': True,
            'summary': summary,
            'reports': {k: os.path.basename(v) for k, v in report_paths.items()}
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/stock-checks/<task_no>/report')
def api_task_report_data(task_no):
    with get_session() as session:
        task = session.query(StockCheckTask).filter(
            StockCheckTask.task_no == task_no
        ).first()
        if not task:
            return jsonify({'error': '任务不存在'}), 404
        items = task.items
        total = len(items)
        scanned = sum(1 for i in items if i.is_scanned)
        matched = sum(1 for i in items if i.is_scanned and i.scanned_qty == i.system_qty)
        diff_items = [i for i in items if i.is_scanned and i.scanned_qty != i.system_qty]

        products = {p.sku: p for p in session.query(Product).all()}
        category_diff = {}
        total_diff_amount = 0.0
        for i in diff_items:
            p = products.get(i.sku)
            cat = p.category if p else '未分类'
            price = p.unit_price if p else 0.0
            diff = abs(i.scanned_qty - i.system_qty)
            total_diff_amount += diff * price
            if cat not in category_diff:
                category_diff[cat] = {'count': 0, 'diff': 0, 'amount': 0.0}
            category_diff[cat]['count'] += 1
            category_diff[cat]['diff'] += 1
            category_diff[cat]['amount'] += diff * price

        for i in items:
            p = products.get(i.sku)
            cat = p.category if p else '未分类'
            if cat not in category_diff:
                category_diff[cat] = {'count': 0, 'diff': 0, 'amount': 0.0}
            category_diff[cat]['count'] += 1

    return jsonify({
        'task_no': task_no,
        'warehouse': task.warehouse_code,
        'task_type': task.task_type,
        'status': task.status,
        'total': total,
        'scanned': scanned,
        'matched': matched,
        'diff': len(diff_items),
        'total_diff_amount': float(total_diff_amount),
        'scan_rate': round(scanned / total * 100, 2) if total > 0 else 0,
        'match_rate': round(matched / scanned * 100, 2) if scanned > 0 else 0,
        'diff_rate': round(len(diff_items) / scanned * 100, 2) if scanned > 0 else 0,
        'category_diff': category_diff,
        'diff_detail': [{
            'sku': i.sku,
            'product_name': i.product_name,
            'system_qty': float(i.system_qty),
            'scanned_qty': float(i.scanned_qty),
            'diff_qty': float(i.scanned_qty - i.system_qty)
        } for i in diff_items]
    })


@app.route('/api/audit/check', methods=['POST'])
def api_audit_check():
    from special_audit import check_special_audit
    audits = check_special_audit()
    return jsonify({'success': True, 'audits': audits})


@app.route('/api/audits')
def api_audits():
    from special_audit import get_pending_audits
    return jsonify(get_pending_audits())


@app.route('/api/monthly/stats')
def api_monthly_stats():
    with get_session() as session:
        stats = session.query(MonthlyStats).order_by(
            MonthlyStats.stat_month.desc()
        ).limit(60).all()
        data = [{
            'stat_month': s.stat_month,
            'warehouse': s.warehouse_code,
            'total_items': s.total_items,
            'checked_items': s.checked_items,
            'completion_rate': float(s.completion_rate),
            'diff_items': s.diff_items,
            'resolved_items': s.resolved_items,
            'resolution_rate': float(s.resolution_rate),
            'avg_process_hours': float(s.avg_process_hours),
            'total_diff_amount': float(s.total_diff_amount)
        } for s in stats]
    return jsonify(data)


@app.route('/api/monthly/run', methods=['POST'])
def api_run_monthly():
    from monthly_reporter import generate_monthly_report
    body = request.get_json(silent=True) or {}
    try:
        result = generate_monthly_report(body.get('month'))
        return jsonify({
            'success': True,
            'reports': {k: os.path.basename(v) for k, v in result.items()}
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/logs')
def api_logs():
    args = request.args
    with get_session() as session:
        q = session.query(OperationLog)
        if args.get('warehouse'):
            q = q.filter(OperationLog.warehouse_code == args['warehouse'])
        if args.get('category'):
            q = q.filter(OperationLog.category == args['category'])
        if args.get('operation_type'):
            q = q.filter(OperationLog.operation_type == args['operation_type'])
        if args.get('operator'):
            q = q.filter(OperationLog.operator == args['operator'])
        if args.get('sku'):
            q = q.filter(OperationLog.sku.like(f"%{args['sku']}%"))
        if args.get('reference_no'):
            q = q.filter(OperationLog.reference_no.like(f"%{args['reference_no']}%"))
        if args.get('start_time'):
            try:
                st = datetime.strptime(args['start_time'], '%Y-%m-%d %H:%M:%S')
                q = q.filter(OperationLog.log_time >= st)
            except Exception:
                try:
                    st = datetime.strptime(args['start_time'], '%Y-%m-%d')
                    q = q.filter(OperationLog.log_time >= st)
                except Exception:
                    pass
        if args.get('end_time'):
            try:
                et = datetime.strptime(args['end_time'], '%Y-%m-%d %H:%M:%S')
                q = q.filter(OperationLog.log_time <= et)
            except Exception:
                try:
                    et = datetime.strptime(args['end_time'] + ' 23:59:59', '%Y-%m-%d %H:%M:%S')
                    q = q.filter(OperationLog.log_time <= et)
                except Exception:
                    pass

        q = q.order_by(OperationLog.log_time.desc())
        limit = int(args.get('limit', 200))
        page = int(args.get('page', 1))
        total = q.count()
        logs = q.offset((page - 1) * limit).limit(limit).all()

        data = []
        for l in logs:
            data.append({
                'id': l.id,
                'log_time': l.log_time.isoformat(),
                'operation_type': l.operation_type,
                'operator': l.operator or '',
                'warehouse': l.warehouse_code or '',
                'category': l.category or '',
                'sku': l.sku or '',
                'reference_no': l.reference_no or '',
                'detail': l.detail or '',
                'ip_address': l.ip_address or ''
            })
    return jsonify({'total': total, 'page': page, 'limit': limit, 'data': data})


@app.route('/api/warehouses')
def api_warehouses():
    with get_session() as session:
        whs = session.query(Warehouse).all()
        data = [{'code': w.code, 'name': w.name, 'location': w.location, 'supervisor': w.supervisor} for w in whs]
        if not data:
            data = [
                {'code': 'WH001', 'name': '上海一号仓', 'location': '上海市浦东新区'},
                {'code': 'WH002', 'name': '广州二号仓', 'location': '广州市天河区'},
                {'code': 'WH003', 'name': '成都三号仓', 'location': '成都市高新区'}
            ]
    return jsonify(data)


@app.route('/api/categories')
def api_categories():
    with get_session() as session:
        from sqlalchemy import distinct
        cats = session.query(distinct(Product.category)).filter(Product.category.isnot(None)).all()
        data = [c[0] for c in cats if c[0]]
        if not data:
            data = ['A类', 'B类', 'C类']
    return jsonify(data)


@app.route('/api/download/<path:filename>')
def api_download(filename):
    for d in [EXPORT_DIR, REPORT_DIR]:
        fp = os.path.join(d, filename)
        if os.path.exists(fp):
            return send_file(fp, as_attachment=True)
    sub_dirs = [os.path.join(REPORT_DIR, d) for d in os.listdir(REPORT_DIR) if os.path.isdir(os.path.join(REPORT_DIR, d))]
    for d in sub_dirs:
        fp = os.path.join(d, filename)
        if os.path.exists(fp):
            return send_file(fp, as_attachment=True)
    abort(404)


@app.route('/api/reports/diff', methods=['POST'])
def api_generate_diff_report():
    from report_generator import generate_diff_report_excel, generate_diff_report_pdf
    body = request.get_json(silent=True) or {}
    check_date = None
    if body.get('date'):
        check_date = datetime.strptime(body['date'], '%Y-%m-%d').date()
    excel_path = generate_diff_report_excel(check_date)
    pdf_path = generate_diff_report_pdf(check_date)
    return jsonify({
        'success': True,
        'excel': os.path.basename(excel_path),
        'pdf': os.path.basename(pdf_path)
    })


@app.route('/api/export/differences')
def api_export_differences():
    from query_export import export_differences_batch
    args = request.args
    result = export_differences_batch(
        warehouse_codes=args.get('warehouses', '').split(',') if args.get('warehouses') else None,
        categories=args.get('categories', '').split(',') if args.get('categories') else None,
        start_date=args.get('start_date'),
        end_date=args.get('end_date')
    )
    return send_file(result['file'], as_attachment=True)


@app.route('/api/export/logs')
def api_export_logs():
    from query_export import export_operation_logs
    args = request.args
    result = export_operation_logs(
        warehouse_code=args.get('warehouse'),
        start_time=args.get('start_time'),
        end_time=args.get('end_time')
    )
    return send_file(result['file'], as_attachment=True)
