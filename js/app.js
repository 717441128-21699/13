const API_BASE = '/api';
let currentView = 'dashboard';
let charts = {};
let warehouses = [];
let categories = [];

async function api(path, options = {}) {
    const url = path.startsWith('http') ? path : API_BASE + path;
    const resp = await fetch(url, {
        headers: { 'Content-Type': 'application/json' },
        ...options
    });
    try {
        return await resp.json();
    } catch (e) {
        return { success: false, error: resp.statusText };
    }
}

function safeChart(domId) {
    if (typeof echarts === 'undefined') {
        console.warn('[ECharts] 未加载，跳过图表渲染:', domId);
        return null;
    }
    const el = document.getElementById(domId);
    if (!el) {
        console.warn('[ECharts] DOM元素不存在:', domId);
        return null;
    }
    return echarts.init(el);
}

function renderChart(domId, option) {
    const c = safeChart(domId);
    if (c && option) c.setOption(option);
    return c;
}

function showToast(msg, type = '') {
    const t = document.getElementById('toast');
    t.className = 'toast show ' + type;
    t.textContent = msg;
    setTimeout(() => t.classList.remove('show'), 2500);
}

function openModal(title, body, footer = '', large = false) {
    document.getElementById('modalTitle').textContent = title;
    document.getElementById('modalBody').innerHTML = body;
    document.getElementById('modalFooter').innerHTML = footer;
    document.getElementById('modalBox').className = 'modal-box' + (large ? ' large' : '');
    document.getElementById('modal').classList.add('show');
}

function closeModal() {
    document.getElementById('modal').classList.remove('show');
}

function statusTag(status) {
    const map = {
        'assigned': ['tag-blue', '已分配'],
        'in_progress': ['tag-orange', '处理中'],
        'upgraded': ['tag-red', '已升级'],
        'pending': ['tag-orange', '待处理'],
        'approved': ['tag-green', '审核通过'],
        'rejected': ['tag-gray', '审核驳回'],
        'completed': ['tag-green', '已完成'],
        'created': ['tag-blue', '已创建'],
        'pushed': ['tag-purple', '已推送'],
        'resolved': ['tag-green', '已解决'],
        'unresolved': ['tag-red', '未解决']
    };
    const m = map[status] || ['tag-gray', status];
    return `<span class="tag ${m[0]}">${m[1]}</span>`;
}

function diffTag(type) {
    if (type === '盘盈') return '<span class="tag tag-green">盘盈</span>';
    if (type === '盘亏') return '<span class="tag tag-red">盘亏</span>';
    if (type === '一致') return '<span class="tag tag-gray">一致</span>';
    return type;
}

function money(n) {
    return '¥' + Number(n || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function setView(view) {
    currentView = view;
    document.querySelectorAll('.menu-item').forEach(el => {
        el.classList.toggle('active', el.dataset.view === view);
    });
    const titles = {
        dashboard: ['仪表板', '首页 / 仪表板'],
        orders: ['盘点工单', '首页 / 盘点工单'],
        check: ['手动盘点', '首页 / 手动盘点'],
        reports: ['差异报告', '首页 / 差异报告'],
        monthly: ['月度分析', '首页 / 月度分析'],
        logs: ['操作日志', '首页 / 操作日志']
    };
    const t = titles[view] || ['', ''];
    document.getElementById('pageTitle').textContent = t[0];
    document.getElementById('pageBreadcrumb').textContent = t[1];

    Object.values(charts).forEach(c => c && c.dispose && c.dispose());
    charts = {};

    document.getElementById('content').innerHTML = '<div class="loading">加载中...</div>';
    const renderers = {
        dashboard: renderDashboard,
        orders: renderOrders,
        check: renderCheck,
        reports: renderReports,
        monthly: renderMonthly,
        logs: renderLogs
    };
    (renderers[view] || renderDashboard)();
}

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.menu-item').forEach(el => {
        el.addEventListener('click', () => setView(el.dataset.view));
    });
    api('/warehouses').then(d => { warehouses = d || []; });
    api('/categories').then(d => { categories = d || []; });
    setView('dashboard');
});

async function runDailyJob() {
    showToast('正在执行每日盘点任务...');
    const r = await api('/daily/run', { method: 'POST' });
    if (r.success) {
        showToast(`完成！比对 ${r.compare?.total || 0} 条，生成工单 ${r.orders_created || 0} 个`, 'success');
        setView(currentView);
    } else {
        showToast('执行失败: ' + (r.error || ''), 'error');
    }
}

async function renderDashboard() {
    const d = await api('/dashboard');
    if (!d || d.error) {
        document.getElementById('content').innerHTML = '<div class="empty">数据加载失败</div>';
        return;
    }

    const html = `
        <div class="stat-cards">
            <div class="stat-card">
                <div>
                    <div class="label">今日差异数</div>
                    <div class="value red">${d.today.total || 0}</div>
                </div>
                <div class="stat-icon red">⚠️</div>
            </div>
            <div class="stat-card">
                <div>
                    <div class="label">待处理工单</div>
                    <div class="value orange">${d.pending.work_orders || 0}</div>
                </div>
                <div class="stat-icon orange">📋</div>
            </div>
            <div class="stat-card">
                <div>
                    <div class="label">已升级工单</div>
                    <div class="value red">${d.pending.upgraded_orders || 0}</div>
                </div>
                <div class="stat-icon red">🚨</div>
            </div>
            <div class="stat-card">
                <div>
                    <div class="label">专项审计</div>
                    <div class="value purple">${d.pending.special_audits || 0}</div>
                </div>
                <div class="stat-icon purple">🔍</div>
            </div>
            <div class="stat-card">
                <div>
                    <div class="label">盘点中任务</div>
                    <div class="value blue">${d.pending.stock_tasks || 0}</div>
                </div>
                <div class="stat-icon blue">✅</div>
            </div>
            <div class="stat-card">
                <div>
                    <div class="label">今日差异金额</div>
                    <div class="value red">${money(d.today.diff_amount)}</div>
                </div>
                <div class="stat-icon red">💰</div>
            </div>
        </div>

        <div class="grid-2">
            <div class="card">
                <div class="card-title">差异类型分布（今日）</div>
                <div id="chart_diff_type" class="chart"></div>
            </div>
            <div class="card">
                <div class="card-title">各仓库差异数量</div>
                <div id="chart_wh" class="chart"></div>
            </div>
        </div>

        <div class="grid-2">
            <div class="card">
                <div class="card-title">各品类差异统计</div>
                <div id="chart_cat" class="chart"></div>
            </div>
            <div class="card">
                <div class="card-title">库存总览</div>
                <div id="chart_overview" class="chart"></div>
            </div>
        </div>
    `;
    document.getElementById('content').innerHTML = html;

    charts.diff_type = safeChart('chart_diff_type');
    charts.diff_type && charts.diff_type.setOption({
        tooltip: { trigger: 'item' },
        legend: { bottom: 0 },
        series: [{
            type: 'pie',
            radius: ['45%', '70%'],
            avoidLabelOverlap: true,
            label: { show: true, formatter: '{b}\n{c}件' },
            data: [
                { value: d.today.surplus || 0, name: '盘盈', itemStyle: { color: '#10b981' } },
                { value: d.today.deficit || 0, name: '盘亏', itemStyle: { color: '#ef4444' } },
                { value: d.today.matched || 0, name: '一致', itemStyle: { color: '#94a3b8' } },
                { value: d.today.over_threshold || 0, name: '超阈值', itemStyle: { color: '#f59e0b' } }
            ].filter(x => x.value > 0)
        }]
    });

    const whNames = Object.keys(d.by_warehouse);
    charts.wh = safeChart('chart_wh');
    charts.wh && charts.wh.setOption({
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
        legend: { top: 0 },
        grid: { left: 50, right: 20, top: 40, bottom: 30 },
        xAxis: { type: 'category', data: whNames },
        yAxis: { type: 'value' },
        series: [
            { name: '盘盈', type: 'bar', stack: 'total', data: whNames.map(w => d.by_warehouse[w].surplus), itemStyle: { color: '#10b981' } },
            { name: '盘亏', type: 'bar', stack: 'total', data: whNames.map(w => d.by_warehouse[w].deficit), itemStyle: { color: '#ef4444' } }
        ]
    });

    const catNames = Object.keys(d.by_category);
    charts.cat = safeChart('chart_cat');
    charts.cat && charts.cat.setOption({
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
        legend: { top: 0 },
        grid: { left: 50, right: 40, top: 40, bottom: 30 },
        xAxis: { type: 'value' },
        yAxis: { type: 'category', data: catNames },
        series: [{
            name: '差异金额(元)',
            type: 'bar',
            data: catNames.map(c => d.by_category[c].amount),
            itemStyle: { color: '#3b82f6' },
            label: { show: true, position: 'right', formatter: p => money(p.value) }
        }]
    });

    charts.overview = safeChart('chart_overview');
    charts.overview && charts.overview.setOption({
        tooltip: { trigger: 'item' },
        legend: { bottom: 0 },
        series: [{
            type: 'pie',
            radius: '65%',
            label: { show: true, formatter: '{b}\n{c}件' },
            data: [
                { value: d.overview.products || 0, name: '商品总数', itemStyle: { color: '#6366f1' } },
                { value: d.overview.warehouses || 0, name: '仓库数', itemStyle: { color: '#8b5cf6' } },
                { value: d.today.over_threshold || 0, name: '超阈值差异', itemStyle: { color: '#f59e0b' } }
            ]
        }]
    });

    window.addEventListener('resize', () => Object.values(charts).forEach(c => c && c.resize()));
}

let ordersPage = 1;
async function renderOrders() {
    const whOpts = warehouses.map(w => `<option value="${w.code}">${w.name}</option>`).join('');
    const html = `
        <div class="card">
            <div class="filter-bar">
                <select id="f_wh"><option value="">全部仓库</option>${whOpts}</select>
                <select id="f_status">
                    <option value="">全部状态</option>
                    <option value="assigned">已分配</option>
                    <option value="in_progress">处理中</option>
                    <option value="upgraded">已升级</option>
                    <option value="approved">审核通过</option>
                    <option value="rejected">审核驳回</option>
                    <option value="completed">已完成</option>
                </select>
                <select id="f_upgrade">
                    <option value="">是否升级</option>
                    <option value="true">已升级</option>
                    <option value="false">未升级</option>
                </select>
                <button class="btn btn-primary" onclick="loadOrders()">查询</button>
                <button class="btn btn-default" onclick="refreshOrders()">重置</button>
                <button class="btn btn-warning" style="margin-left:auto" onclick="upgradeOrders()">批量升级超时工单</button>
            </div>
            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>工单号</th><th>仓库</th><th>品类</th><th>类型</th>
                            <th>审核人</th><th>主管</th><th>状态</th><th>优先级</th>
                            <th>差异数</th><th>创建时间</th><th>操作</th>
                        </tr>
                    </thead>
                    <tbody id="orders_body"></tbody>
                </table>
            </div>
            <div class="pagination">
                <span class="page-info" id="orders_info"></span>
            </div>
        </div>
    `;
    document.getElementById('content').innerHTML = html;
    loadOrders();
}

function refreshOrders() {
    ['f_wh', 'f_status', 'f_upgrade'].forEach(id => document.getElementById(id).value = '');
    ordersPage = 1;
    loadOrders();
}

async function loadOrders() {
    const params = new URLSearchParams();
    const wh = document.getElementById('f_wh').value;
    const st = document.getElementById('f_status').value;
    const up = document.getElementById('f_upgrade').value;
    if (wh) params.append('warehouse', wh);
    if (st) params.append('status', st);
    if (up) params.append('is_upgraded', up);
    const list = await api('/orders?' + params.toString());
    const body = document.getElementById('orders_body');
    if (!list || !list.length) {
        body.innerHTML = '<tr><td colspan="11" class="empty">暂无数据</td></tr>';
        return;
    }
    body.innerHTML = list.map(o => `
        <tr>
            <td><b>${o.order_no}</b></td>
            <td>${o.warehouse}</td>
            <td>${o.category || '-'}</td>
            <td>${diffTag(o.diff_type)}</td>
            <td>${o.auditor || '-'}</td>
            <td>${o.is_upgraded ? ('<span class="tag tag-red">'+(o.supervisor||'已升级')+'</span>') : (o.supervisor || '-')}</td>
            <td>${statusTag(o.status)}</td>
            <td>${o.priority === 'high' ? '<span class="tag tag-red">高</span>' : o.priority === 'medium' ? '<span class="tag tag-orange">中</span>' : '<span class="tag tag-gray">低</span>'}</td>
            <td>${o.diff_count || 0}</td>
            <td>${(o.created_at || '').slice(0, 16).replace('T', ' ')}</td>
            <td>
                <button class="btn btn-sm btn-primary" onclick="viewOrder('${o.order_no}')">详情</button>
                ${['assigned', 'in_progress', 'upgraded'].includes(o.status) ? `
                    <button class="btn btn-sm btn-success" onclick="reviewOrder('${o.order_no}', true)">通过</button>
                    <button class="btn btn-sm btn-danger" onclick="reviewOrder('${o.order_no}', false)">驳回</button>
                ` : ''}
            </td>
        </tr>
    `).join('');
    document.getElementById('orders_info').textContent = `共 ${list.length} 条`;
}

async function upgradeOrders() {
    const r = await api('/orders/upgrade-all', { method: 'POST' });
    showToast(r.success ? '已检查并升级超时工单' : '操作失败', r.success ? 'success' : 'error');
    loadOrders();
}

async function viewOrder(orderNo) {
    const r = await api('/orders?status=');
    const order = (r || []).find(o => o.order_no === orderNo);
    if (!order) return showToast('工单不存在', 'error');
    const diffs = await api(`/differences?status=&limit=50`);
    const related = (diffs.data || []).filter(d => d.work_order_id === order.id);
    openModal(`工单详情 - ${orderNo}`, `
        <div class="detail-grid">
            <div class="detail-item"><div class="label">状态</div><div class="value">${statusTag(order.status)}</div></div>
            <div class="detail-item"><div class="label">仓库</div><div class="value">${order.warehouse}</div></div>
            <div class="detail-item"><div class="label">品类</div><div class="value">${order.category || '-'}</div></div>
            <div class="detail-item"><div class="label">差异类型</div><div class="value">${diffTag(order.diff_type)}</div></div>
            <div class="detail-item"><div class="label">审核人</div><div class="value">${order.auditor || '-'}</div></div>
            <div class="detail-item"><div class="label">差异数</div><div class="value">${order.diff_count || 0}</div></div>
        </div>
        <h4 style="margin-bottom:10px">差异明细</h4>
        <div class="table-wrap">
            <table>
                <thead><tr><th>SKU</th><th>商品</th><th>实盘</th><th>ERP</th><th>差异</th><th>金额</th></tr></thead>
                <tbody>
                    ${related.length ? related.map(d => `
                        <tr>
                            <td>${d.sku}</td><td>${d.product_name}</td>
                            <td>${d.realtime_qty}</td><td>${d.erp_qty}</td>
                            <td class="${d.diff_qty > 0 ? 'tag-green' : d.diff_qty < 0 ? 'tag-red' : ''}">${d.diff_qty}</td>
                            <td>${money(d.diff_amount)}</td>
                        </tr>
                    `).join('') : '<tr><td colspan="6" class="empty">暂无明细</td></tr>'}
                </tbody>
            </table>
        </div>
        ${order.review_comment ? `<div style="margin-top:14px"><b>审核备注：</b>${order.review_comment}</div>` : ''}
    `, `
        ${['assigned', 'in_progress', 'upgraded'].includes(order.status) ? `
            <button class="btn btn-success" onclick="reviewOrder('${orderNo}', true);closeModal()">审核通过</button>
            <button class="btn btn-danger" onclick="reviewOrder('${orderNo}', false);closeModal()">审核驳回</button>
        ` : ''}
        <button class="btn btn-default" onclick="closeModal()">关闭</button>
    `, true);
}

function reviewOrder(orderNo, approved) {
    const comment = approved ? '' : prompt('请输入驳回原因：');
    if (!approved && comment === null) return;
    api(`/orders/${orderNo}/review`, {
        method: 'POST',
        body: JSON.stringify({ approved, comment: comment || '', operator: 'web_user' })
    }).then(r => {
        showToast(r.success ? (approved ? '审核通过' : '已驳回') : (r.error || '操作失败'), r.success ? 'success' : 'error');
        if (r.success) loadOrders();
    });
}

let checkTasksPage = 1;
async function renderCheck() {
    const whOpts = warehouses.map(w => `<option value="${w.code}">${w.name}</option>`).join('');
    const catOpts = categories.map(c => `<option value="${c}">${c}</option>`).join('');
    const html = `
        <div class="card">
            <div class="card-title">
                <span>盘点任务</span>
                <button class="btn btn-primary" onclick="openCreateTask()">+ 新建盘点任务</button>
            </div>
            <div class="filter-bar">
                <select id="cf_wh"><option value="">全部仓库</option>${whOpts}</select>
                <select id="cf_status">
                    <option value="">全部状态</option>
                    <option value="created">已创建</option>
                    <option value="pushed">已推送</option>
                    <option value="in_progress">进行中</option>
                    <option value="completed">已完成</option>
                </select>
                <button class="btn btn-primary" onclick="loadTasks()">查询</button>
            </div>
            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>任务编号</th><th>类型</th><th>仓库</th><th>品类</th>
                            <th>抽样</th><th>状态</th><th>创建人</th>
                            <th>总数/已扫/匹配</th><th>创建时间</th><th>操作</th>
                        </tr>
                    </thead>
                    <tbody id="tasks_body"></tbody>
                </table>
            </div>
        </div>
    `;
    document.getElementById('content').innerHTML = html;
    loadTasks();
}

async function loadTasks() {
    const params = new URLSearchParams();
    const wh = document.getElementById('cf_wh')?.value;
    const st = document.getElementById('cf_status')?.value;
    if (wh) params.append('warehouse', wh);
    if (st) params.append('status', st);
    const list = await api('/stock-checks?' + params.toString());
    const body = document.getElementById('tasks_body');
    if (!list || !list.length) {
        body.innerHTML = '<tr><td colspan="10" class="empty">暂无数据，点击右上角创建任务</td></tr>';
        return;
    }
    body.innerHTML = list.map(t => `
        <tr>
            <td><b>${t.task_no}</b></td>
            <td>${t.task_type === 'full' ? '<span class="tag tag-blue">全盘</span>' : '<span class="tag tag-purple">抽盘</span>'}</td>
            <td>${t.warehouse}</td>
            <td>${t.category || '-'}</td>
            <td>${t.sample_ratio ? Math.round(t.sample_ratio * 100) + '%' : '-'}</td>
            <td>${statusTag(t.status)}</td>
            <td>${t.operator || '-'}</td>
            <td>${t.total_items || 0} / <span class="tag tag-blue">${t.scanned_items || 0}</span> / <span class="tag tag-green">${t.matched_items || 0}</span></td>
            <td>${(t.created_at || '').slice(0, 16).replace('T', ' ')}</td>
            <td>
                <button class="btn btn-sm btn-primary" onclick="openTask('${t.task_no}')">详情/扫码</button>
                ${['created'].includes(t.status) ? `<button class="btn btn-sm btn-warning" onclick="pushTask('${t.task_no}')">推送</button>` : ''}
                ${['created', 'pushed', 'in_progress'].includes(t.status) && (t.scanned_items || 0) > 0 ? `<button class="btn btn-sm btn-success" onclick="completeTask('${t.task_no}')">完成</button>` : ''}
                ${t.status === 'completed' ? `<button class="btn btn-sm btn-default" onclick="viewReport('${t.task_no}')">报告</button>` : ''}
            </td>
        </tr>
    `).join('');
}

function openCreateTask() {
    const whOpts = warehouses.map(w => `<option value="${w.code}">${w.name}</option>`).join('');
    const catOpts = '<option value="">全品类</option>' + categories.map(c => `<option value="${c}">${c}</option>`).join('');
    openModal('新建盘点任务', `
        <div class="form-group">
            <label>盘点类型</label>
            <select id="nk_type">
                <option value="full">全盘</option>
                <option value="sample">抽盘</option>
            </select>
        </div>
        <div class="form-row">
            <div class="form-group">
                <label>仓库</label>
                <select id="nk_wh">${whOpts}</select>
            </div>
            <div class="form-group">
                <label>品类</label>
                <select id="nk_cat">${catOpts}</select>
            </div>
        </div>
        <div class="form-group">
            <label>抽样比例（抽盘时生效，0-1）</label>
            <input type="number" id="nk_ratio" value="0.3" step="0.1" min="0.1" max="1">
        </div>
    `, `
        <button class="btn btn-primary" onclick="createTask()">创建</button>
        <button class="btn btn-default" onclick="closeModal()">取消</button>
    `);
}

async function createTask() {
    const body = {
        task_type: document.getElementById('nk_type').value,
        warehouse: document.getElementById('nk_wh').value,
        category: document.getElementById('nk_cat').value,
        sample_ratio: parseFloat(document.getElementById('nk_ratio').value) || 0.3,
        operator: 'web_user'
    };
    const r = await api('/stock-checks', { method: 'POST', body: JSON.stringify(body) });
    if (r.success) {
        showToast('任务创建成功', 'success');
        closeModal();
        loadTasks();
    } else {
        showToast(r.error || '创建失败', 'error');
    }
}

async function pushTask(taskNo) {
    const r = await api(`/stock-checks/${taskNo}/push`, { method: 'POST' });
    showToast(r.success ? `已推送至终端，共 ${r.payload?.items?.length || 0} 项` : (r.error || '推送失败'), r.success ? 'success' : 'error');
    if (r.success) loadTasks();
}

async function completeTask(taskNo) {
    if (!confirm('确认完成该盘点任务？将生成盘点报告。')) return;
    const r = await api(`/stock-checks/${taskNo}/complete`, { method: 'POST', body: JSON.stringify({ operator: 'web_user' }) });
    if (r.success) {
        showToast('任务已完成，报告已生成', 'success');
        if (r.reports) {
            setTimeout(() => {
                if (r.reports.excel) window.open(`${API_BASE}/download/${r.reports.excel}`);
            }, 500);
        }
        loadTasks();
    } else {
        showToast(r.error || '操作失败', 'error');
    }
}

async function openTask(taskNo) {
    const detail = await api(`/stock-checks/${taskNo}`);
    if (!detail || detail.error) return showToast('任务不存在', 'error');
    const items = detail.items || [];
    const total = items.length;
    const scanned = items.filter(i => i.is_scanned).length;
    const matched = items.filter(i => i.is_scanned && i.scanned_qty === i.system_qty).length;
    const rate = total ? Math.round(scanned / total * 100) : 0;

    openModal(`盘点任务 - ${taskNo}`, `
        <div class="detail-grid">
            <div class="detail-item"><div class="label">状态</div><div class="value">${statusTag(detail.status || 'created')}</div></div>
            <div class="detail-item"><div class="label">仓库</div><div class="value">${detail.warehouse_code || '-'}</div></div>
            <div class="detail-item"><div class="label">总数</div><div class="value">${total}</div></div>
            <div class="detail-item"><div class="label">已扫</div><div class="value blue" style="color:#3b82f6">${scanned}</div></div>
            <div class="detail-item"><div class="label">匹配</div><div class="value green" style="color:#10b981">${matched}</div></div>
            <div class="detail-item"><div class="label">扫描率</div><div class="value">${rate}%</div></div>
        </div>
        <div class="progress-bar"><div class="fill" style="width:${rate}%"></div></div>

        <div class="scan-panel" style="margin-top:18px">
            <h4>扫码录入（模拟）</h4>
            <div class="scan-inputs">
                <input id="scan_sku" placeholder="输入SKU（如 P001）">
                <input id="scan_qty" type="number" placeholder="实盘数量" value="1">
                <button class="btn btn-primary" onclick="doScan('${taskNo}')">扫码录入</button>
            </div>
            <div style="color:#64748b;font-size:12px">输入 SKU 和实际数量，模拟扫码枪录入。</div>
        </div>

        <h4 style="margin-bottom:10px">盘点明细</h4>
        <div class="table-wrap" style="max-height:300px;overflow:auto">
            <table>
                <thead>
                    <tr><th>SKU</th><th>商品</th><th>系统数量</th><th>实盘数量</th><th>状态</th></tr>
                </thead>
                <tbody>
                    ${items.map(i => `
                        <tr>
                            <td>${i.sku}</td>
                            <td>${i.product_name || '-'}</td>
                            <td>${i.system_qty}</td>
                            <td>${i.is_scanned ? i.scanned_qty : '<span style="color:#94a3b8">未扫描</span>'}</td>
                            <td>${i.is_scanned ? (i.scanned_qty === i.system_qty ? '<span class="tag tag-green">匹配</span>' : '<span class="tag tag-red">差异</span>') : '<span class="tag tag-gray">待扫</span>'}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `, `
        <button class="btn btn-default" onclick="closeModal()">关闭</button>
    `, true);
}

async function doScan(taskNo) {
    const sku = document.getElementById('scan_sku').value.trim();
    const qty = document.getElementById('scan_qty').value;
    if (!sku) return showToast('请输入SKU', 'warning');
    if (qty === '' || qty < 0) return showToast('请输入正确数量', 'warning');
    const r = await api('/scan', {
        method: 'POST',
        body: JSON.stringify({ task_no: taskNo, sku, scanned_qty: parseFloat(qty), scanner: 'web_user' })
    });
    if (r.success) {
        showToast('扫码成功', 'success');
        openTask(taskNo);
        loadTasks();
    } else {
        showToast(r.error || '扫码失败', 'error');
    }
}

async function viewReport(taskNo) {
    const d = await api(`/stock-checks/${taskNo}/report`);
    if (!d || d.error) return showToast('报告获取失败', 'error');
    openModal(`盘点报告 - ${taskNo}`, `
        <div class="detail-grid">
            <div class="detail-item"><div class="label">总项数</div><div class="value">${d.total || 0}</div></div>
            <div class="detail-item"><div class="label">已扫描</div><div class="value blue" style="color:#3b82f6">${d.scanned || 0}</div></div>
            <div class="detail-item"><div class="label">匹配</div><div class="value green" style="color:#10b981">${d.matched || 0}</div></div>
            <div class="detail-item"><div class="label">差异</div><div class="value red" style="color:#ef4444">${d.diff || 0}</div></div>
            <div class="detail-item"><div class="label">扫描率</div><div class="value">${d.scan_rate || 0}%</div></div>
            <div class="detail-item"><div class="label">差异金额</div><div class="value red" style="color:#ef4444">${money(d.total_diff_amount)}</div></div>
        </div>
        <div id="rpt_chart" style="height:260px;margin-bottom:16px"></div>
        ${d.diff_detail && d.diff_detail.length ? `
            <h4 style="margin-bottom:10px">差异明细</h4>
            <div class="table-wrap" style="max-height:200px;overflow:auto">
                <table>
                    <thead><tr><th>SKU</th><th>商品</th><th>系统</th><th>实盘</th><th>差异</th></tr></thead>
                    <tbody>
                        ${d.diff_detail.map(x => `
                            <tr>
                                <td>${x.sku}</td><td>${x.product_name}</td>
                                <td>${x.system_qty}</td><td>${x.scanned_qty}</td>
                                <td class="${x.diff_qty > 0 ? 'tag-green' : 'tag-red'}">${x.diff_qty}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        ` : '<div class="empty">无差异项</div>'}
    `, `<button class="btn btn-default" onclick="closeModal()">关闭</button>`, true);

    setTimeout(() => {
        const c = safeChart('rpt_chart');
        if (c) {
            c.setOption({
                tooltip: { trigger: 'item' },
                legend: { bottom: 0 },
                series: [{
                    type: 'pie',
                    radius: ['40%', '70%'],
                    label: { formatter: '{b}\n{c}' },
                    data: [
                        { value: d.matched || 0, name: '匹配', itemStyle: { color: '#10b981' } },
                        { value: d.diff || 0, name: '差异', itemStyle: { color: '#ef4444' } },
                        { value: (d.total || 0) - (d.scanned || 0), name: '未扫', itemStyle: { color: '#94a3b8' } }
                    ]
                }]
            });
        }
    }, 100);
}

let diffPage = 1;
async function renderReports() {
    const whOpts = warehouses.map(w => `<option value="${w.code}">${w.name}</option>`).join('');
    const catOpts = categories.map(c => `<option value="${c}">${c}</option>`).join('');
    const html = `
        <div class="card">
            <div class="card-title">
                <span>差异明细与报告</span>
                <div>
                    <button class="btn btn-success" onclick="exportDiffs()">📥 导出Excel</button>
                    <button class="btn btn-primary" style="margin-left:8px" onclick="generateDiffReport()">📄 生成今日报告</button>
                </div>
            </div>
            <div class="filter-bar">
                <select id="rd_wh"><option value="">全部仓库</option>${whOpts}</select>
                <select id="rd_cat"><option value="">全部品类</option>${catOpts}</select>
                <select id="rd_type">
                    <option value="">全部类型</option>
                    <option value="盘盈">盘盈</option>
                    <option value="盘亏">盘亏</option>
                    <option value="一致">一致</option>
                </select>
                <select id="rd_over">
                    <option value="">是否超阈值</option>
                    <option value="true">超阈值</option>
                    <option value="false">未超阈值</option>
                </select>
                <input id="rd_sku" placeholder="SKU搜索">
                <input type="date" id="rd_sd">
                <input type="date" id="rd_ed">
                <button class="btn btn-primary" onclick="loadDiffs()">查询</button>
                <button class="btn btn-default" onclick="resetDiffs()">重置</button>
            </div>
            <div id="diff_summary"></div>
            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>日期</th><th>仓库</th><th>SKU</th><th>商品</th><th>品类</th>
                            <th>实盘</th><th>ERP</th><th>差异</th><th>类型</th>
                            <th>金额</th><th>差异率</th><th>超阈值</th><th>状态</th>
                        </tr>
                    </thead>
                    <tbody id="diff_body"></tbody>
                </table>
            </div>
            <div class="pagination">
                <button onclick="diffPage=Math.max(1,diffPage-1);loadDiffs()">上一页</button>
                <span class="page-info" id="diff_info"></span>
                <button onclick="diffPage++;loadDiffs()">下一页</button>
            </div>
        </div>
    `;
    document.getElementById('content').innerHTML = html;
    loadDiffs();
}

function resetDiffs() {
    ['rd_wh', 'rd_cat', 'rd_type', 'rd_over', 'rd_sku', 'rd_sd', 'rd_ed'].forEach(id => document.getElementById(id).value = '');
    diffPage = 1;
    loadDiffs();
}

async function loadDiffs() {
    const params = new URLSearchParams({ page: diffPage, limit: 20 });
    const wh = document.getElementById('rd_wh').value;
    const cat = document.getElementById('rd_cat').value;
    const ty = document.getElementById('rd_type').value;
    const ov = document.getElementById('rd_over').value;
    const sku = document.getElementById('rd_sku').value;
    const sd = document.getElementById('rd_sd').value;
    const ed = document.getElementById('rd_ed').value;
    if (wh) params.append('warehouse', wh);
    if (cat) params.append('category', cat);
    if (ty) params.append('diff_type', ty);
    if (ov) params.append('over_threshold', ov);
    if (sku) params.append('sku', sku);
    if (sd) params.append('start_date', sd);
    if (ed) params.append('end_date', ed);

    const r = await api('/differences?' + params.toString());
    const body = document.getElementById('diff_body');
    if (!r || !r.data || !r.data.length) {
        body.innerHTML = '<tr><td colspan="13" class="empty">暂无数据</td></tr>';
        document.getElementById('diff_info').textContent = '共 0 条';
        return;
    }
    const summary = r.data.reduce((a, d) => {
        a.total++;
        a.amount += d.diff_amount || 0;
        return a;
    }, { total: 0, amount: 0 });
    document.getElementById('diff_summary').innerHTML = `
        <div class="stat-cards" style="grid-template-columns:repeat(3,1fr);margin-bottom:14px">
            <div class="stat-card"><div><div class="label">当前页差异数</div><div class="value red">${summary.total}</div></div><div class="stat-icon red">⚠️</div></div>
            <div class="stat-card"><div><div class="label">当前页差异金额</div><div class="value red">${money(summary.amount)}</div></div><div class="stat-icon orange">💰</div></div>
            <div class="stat-card"><div><div class="label">总记录数</div><div class="value blue">${r.total}</div></div><div class="stat-icon blue">📋</div></div>
        </div>
    `;
    body.innerHTML = r.data.map(d => `
        <tr>
            <td>${d.check_date}</td>
            <td>${d.warehouse}</td>
            <td><b>${d.sku}</b></td>
            <td>${d.product_name}</td>
            <td>${d.category || '-'}</td>
            <td>${d.realtime_qty}</td>
            <td>${d.erp_qty}</td>
            <td class="${d.diff_qty > 0 ? 'tag-green' : d.diff_qty < 0 ? 'tag-red' : ''}"><b>${d.diff_qty}</b></td>
            <td>${diffTag(d.diff_type)}</td>
            <td>${money(d.diff_amount)}</td>
            <td>${d.diff_rate || 0}%</td>
            <td>${d.is_over_threshold ? '<span class="tag tag-red">是</span>' : '<span class="tag tag-gray">否</span>'}</td>
            <td>${statusTag(d.status || 'pending')}</td>
        </tr>
    `).join('');
    const tp = Math.ceil(r.total / 20);
    document.getElementById('diff_info').textContent = `第 ${diffPage}/${tp || 1} 页，共 ${r.total} 条`;
}

function exportDiffs() {
    const params = new URLSearchParams();
    const wh = document.getElementById('rd_wh').value;
    const cat = document.getElementById('rd_cat').value;
    const sd = document.getElementById('rd_sd').value;
    const ed = document.getElementById('rd_ed').value;
    if (wh) params.append('warehouses', wh);
    if (cat) params.append('categories', cat);
    if (sd) params.append('start_date', sd);
    if (ed) params.append('end_date', ed);
    window.location.href = `${API_BASE}/export/differences?${params.toString()}`;
}

async function generateDiffReport() {
    const r = await api('/reports/diff', { method: 'POST' });
    if (r.success) {
        showToast('报告生成成功，开始下载', 'success');
        setTimeout(() => { if (r.excel) window.open(`${API_BASE}/download/${r.excel}`); }, 300);
        setTimeout(() => { if (r.pdf) window.open(`${API_BASE}/download/${r.pdf}`); }, 800);
    } else {
        showToast(r.error || '生成失败', 'error');
    }
}

async function renderMonthly() {
    const html = `
        <div class="card">
            <div class="card-title">
                <span>月度统计分析</span>
                <button class="btn btn-primary" onclick="runMonthly()">▶ 生成上月报告</button>
            </div>
            <div class="grid-2">
                <div class="card" style="margin:0">
                    <div class="card-title">关键指标趋势</div>
                    <div id="m_chart1" class="chart"></div>
                </div>
                <div class="card" style="margin:0">
                    <div class="card-title">差异解决率</div>
                    <div id="m_chart2" class="chart"></div>
                </div>
            </div>
            <div style="height:16px"></div>
            <div class="grid-2">
                <div class="card" style="margin:0">
                    <div class="card-title">平均处理时长（小时）</div>
                    <div id="m_chart3" class="chart-sm"></div>
                </div>
                <div class="card" style="margin:0">
                    <div class="card-title">月度差异金额（元）</div>
                    <div id="m_chart4" class="chart-sm"></div>
                </div>
            </div>
            <div style="height:16px"></div>
            <div class="card" style="margin:0">
                <div class="card-title">历史数据</div>
                <div class="table-wrap">
                    <table>
                        <thead>
                            <tr>
                                <th>月份</th><th>仓库</th><th>总项数</th><th>已盘点</th>
                                <th>完成率</th><th>差异数</th><th>已解决</th>
                                <th>解决率</th><th>平均处理时长(h)</th><th>差异金额</th>
                            </tr>
                        </thead>
                        <tbody id="m_body"></tbody>
                    </table>
                </div>
            </div>
        </div>
    `;
    document.getElementById('content').innerHTML = html;

    const stats = await api('/monthly/stats');
    const data = stats || [];
    const months = [...new Set(data.map(s => s.stat_month))].sort();
    const byMonth = {};
    months.forEach(m => {
        byMonth[m] = data.filter(s => s.stat_month === m).reduce((a, s) => {
            a.total_items += s.total_items;
            a.checked_items += s.checked_items;
            a.diff_items += s.diff_items;
            a.resolved_items += s.resolved_items;
            a.total_diff_amount += s.total_diff_amount;
            a.avg_sum += (s.avg_process_hours || 0);
            a.avg_cnt++;
            return a;
        }, { total_items: 0, checked_items: 0, diff_items: 0, resolved_items: 0, total_diff_amount: 0, avg_sum: 0, avg_cnt: 0 });
    });

    if (!months.length) {
        document.getElementById('m_body').innerHTML = '<tr><td colspan="10" class="empty">暂无数据，点击右上角生成报告</td></tr>';
        return;
    }

    charts.m1 = safeChart('m_chart1');
    charts.m1 && charts.m1.setOption({
        tooltip: { trigger: 'axis' },
        legend: { top: 0 },
        grid: { left: 50, right: 20, top: 40, bottom: 30 },
        xAxis: { type: 'category', data: months },
        yAxis: { type: 'value' },
        series: [
            { name: '总项数', type: 'line', smooth: true, data: months.map(m => byMonth[m].total_items), itemStyle: { color: '#6366f1' } },
            { name: '已盘点', type: 'line', smooth: true, data: months.map(m => byMonth[m].checked_items), itemStyle: { color: '#3b82f6' } },
            { name: '差异数', type: 'line', smooth: true, data: months.map(m => byMonth[m].diff_items), itemStyle: { color: '#ef4444' } }
        ]
    });

    charts.m2 = safeChart('m_chart2');
    charts.m2 && charts.m2.setOption({
        tooltip: { trigger: 'axis' },
        legend: { top: 0 },
        grid: { left: 50, right: 20, top: 40, bottom: 30 },
        xAxis: { type: 'category', data: months },
        yAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%' } },
        series: [
            { name: '盘点完成率', type: 'bar', data: months.map(m => byMonth[m].total_items ? Math.round(byMonth[m].checked_items / byMonth[m].total_items * 100) : 0), itemStyle: { color: '#3b82f6' } },
            { name: '差异解决率', type: 'bar', data: months.map(m => byMonth[m].diff_items ? Math.round(byMonth[m].resolved_items / byMonth[m].diff_items * 100) : 0), itemStyle: { color: '#10b981' } }
        ]
    });

    charts.m3 = safeChart('m_chart3');
    charts.m3 && charts.m3.setOption({
        tooltip: { trigger: 'axis' },
        grid: { left: 50, right: 20, top: 30, bottom: 30 },
        xAxis: { type: 'category', data: months },
        yAxis: { type: 'value', name: '小时' },
        series: [{
            type: 'line', smooth: true, areaStyle: {},
            data: months.map(m => byMonth[m].avg_cnt ? +(byMonth[m].avg_sum / byMonth[m].avg_cnt).toFixed(1) : 0),
            itemStyle: { color: '#f59e0b' }
        }]
    });

    charts.m4 = safeChart('m_chart4');
    charts.m4 && charts.m4.setOption({
        tooltip: { trigger: 'axis' },
        grid: { left: 50, right: 20, top: 30, bottom: 30 },
        xAxis: { type: 'category', data: months },
        yAxis: { type: 'value' },
        series: [{
            type: 'bar',
            data: months.map(m => +byMonth[m].total_diff_amount.toFixed(2)),
            itemStyle: { color: '#ef4444' },
            label: { show: true, position: 'top', formatter: p => money(p.value) }
        }]
    });

    document.getElementById('m_body').innerHTML = data.slice(0, 30).map(s => `
        <tr>
            <td><b>${s.stat_month}</b></td>
            <td>${s.warehouse}</td>
            <td>${s.total_items}</td>
            <td>${s.checked_items}</td>
            <td>${(s.completion_rate * 100).toFixed(1)}%</td>
            <td class="tag-red">${s.diff_items}</td>
            <td>${s.resolved_items}</td>
            <td>${(s.resolution_rate * 100).toFixed(1)}%</td>
            <td>${s.avg_process_hours.toFixed(1)}</td>
            <td class="tag-red">${money(s.total_diff_amount)}</td>
        </tr>
    `).join('');

    window.addEventListener('resize', () => Object.values(charts).forEach(c => c && c.resize()));
}

async function runMonthly() {
    const r = await api('/monthly/run', { method: 'POST' });
    if (r.success) {
        showToast('月度报告生成成功', 'success');
        if (r.reports) {
            setTimeout(() => {
                Object.values(r.reports).forEach(f => window.open(`${API_BASE}/download/${f}`));
            }, 300);
        }
        renderMonthly();
    } else {
        showToast(r.error || '生成失败', 'error');
    }
}

let logsPage = 1;
async function renderLogs() {
    const whOpts = warehouses.map(w => `<option value="${w.code}">${w.name}</option>`).join('');
    const opTypes = ['inventory_compare', 'work_order_create', 'work_order_review', 'work_order_upgrade',
        'ledger_update', 'special_audit', 'stock_check_create', 'stock_check_scan',
        'stock_check_complete', 'report_generate', 'data_export', 'login', 'logout'];
    const typeOpts = opTypes.map(t => `<option value="${t}">${t}</option>`).join('');
    const html = `
        <div class="card">
            <div class="card-title">
                <span>操作日志</span>
                <button class="btn btn-success" onclick="exportLogs()">📥 导出日志</button>
            </div>
            <div class="filter-bar">
                <select id="lg_wh"><option value="">全部仓库</option>${whOpts}</select>
                <select id="lg_type"><option value="">全部操作</option>${typeOpts}</select>
                <input id="lg_op" placeholder="操作人">
                <input id="lg_sku" placeholder="SKU">
                <input id="lg_ref" placeholder="参考单号">
                <input type="date" id="lg_sd">
                <input type="date" id="lg_ed">
                <button class="btn btn-primary" onclick="loadLogs()">查询</button>
                <button class="btn btn-default" onclick="resetLogs()">重置</button>
            </div>
            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>时间</th><th>操作类型</th><th>操作人</th>
                            <th>仓库</th><th>品类</th><th>SKU</th>
                            <th>参考单号</th><th>详情</th><th>IP</th>
                        </tr>
                    </thead>
                    <tbody id="log_body"></tbody>
                </table>
            </div>
            <div class="pagination">
                <button onclick="logsPage=Math.max(1,logsPage-1);loadLogs()">上一页</button>
                <span class="page-info" id="log_info"></span>
                <button onclick="logsPage++;loadLogs()">下一页</button>
            </div>
        </div>
    `;
    document.getElementById('content').innerHTML = html;
    loadLogs();
}

function resetLogs() {
    ['lg_wh', 'lg_type', 'lg_op', 'lg_sku', 'lg_ref', 'lg_sd', 'lg_ed'].forEach(id => document.getElementById(id).value = '');
    logsPage = 1;
    loadLogs();
}

async function loadLogs() {
    const params = new URLSearchParams({ page: logsPage, limit: 20 });
    const f = (id) => document.getElementById(id)?.value;
    if (f('lg_wh')) params.append('warehouse', f('lg_wh'));
    if (f('lg_type')) params.append('operation_type', f('lg_type'));
    if (f('lg_op')) params.append('operator', f('lg_op'));
    if (f('lg_sku')) params.append('sku', f('lg_sku'));
    if (f('lg_ref')) params.append('reference_no', f('lg_ref'));
    if (f('lg_sd')) params.append('start_time', f('lg_sd'));
    if (f('lg_ed')) params.append('end_time', f('lg_ed'));

    const r = await api('/logs?' + params.toString());
    const body = document.getElementById('log_body');
    if (!r || !r.data || !r.data.length) {
        body.innerHTML = '<tr><td colspan="9" class="empty">暂无数据</td></tr>';
        document.getElementById('log_info').textContent = '共 0 条';
        return;
    }
    body.innerHTML = r.data.map(l => `
        <tr>
            <td style="white-space:nowrap">${l.log_time.replace('T', ' ').slice(0, 19)}</td>
            <td><span class="tag tag-blue">${l.operation_type}</span></td>
            <td>${l.operator || '-'}</td>
            <td>${l.warehouse || '-'}</td>
            <td>${l.category || '-'}</td>
            <td>${l.sku || '-'}</td>
            <td>${l.reference_no || '-'}</td>
            <td style="max-width:260px;overflow:hidden;text-overflow:ellipsis" title="${l.detail || ''}">${l.detail || '-'}</td>
            <td>${l.ip_address || '-'}</td>
        </tr>
    `).join('');
    const tp = Math.ceil(r.total / 20);
    document.getElementById('log_info').textContent = `第 ${logsPage}/${tp || 1} 页，共 ${r.total} 条`;
}

function exportLogs() {
    const params = new URLSearchParams();
    const f = (id) => document.getElementById(id)?.value;
    if (f('lg_wh')) params.append('warehouse', f('lg_wh'));
    if (f('lg_sd')) params.append('start_time', f('lg_sd'));
    if (f('lg_ed')) params.append('end_time', f('lg_ed'));
    window.location.href = `${API_BASE}/export/logs?${params.toString()}`;
}
