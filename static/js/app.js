const API = '';
const state = {
    currentView: 'dashboard',
    warehouses: [],
    categories: [],
    charts: {},
    diffPage: 1,
    logPage: 1,
    scanMode: false,
    currentScanTask: null
};

async function api(url, options = {}) {
    const res = await fetch(API + url, {
        headers: { 'Content-Type': 'application/json' },
        ...options,
        body: options.body ? JSON.stringify(options.body) : undefined
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || `HTTP ${res.status}`);
    }
    return res.json();
}

function toast(msg, type = 'info') {
    const el = document.getElementById('toast');
    el.textContent = msg;
    el.className = `toast show ${type}`;
    setTimeout(() => { el.className = 'toast'; }, 2500);
}

function showModal(html, large = false) {
    const modal = document.getElementById('modal');
    const mc = document.getElementById('modalContent');
    mc.className = 'modal-content' + (large ? ' modal-lg' : '');
    mc.innerHTML = html;
    modal.classList.add('show');
}
function hideModal() {
    document.getElementById('modal').classList.remove('show');
}
document.addEventListener('click', e => {
    if (e.target.classList.contains('modal-close') ||
        e.target.classList.contains('modal-mask')) hideModal();
    if (e.target.closest('[data-action]')) {
        const act = e.target.closest('[data-action]').dataset.action;
        handleAction(act, e.target.closest('[data-action]'));
    }
});

function setView(view) {
    state.currentView = view;
    document.querySelectorAll('.nav-item').forEach(el => {
        el.classList.toggle('active', el.dataset.view === view);
    });
    const names = {
        dashboard: '仪表板', orders: '盘点工单', check: '手动盘点',
        reports: '报告中心', monthly: '月度分析', logs: '操作日志'
    };
    document.getElementById('breadcrumb').textContent = '首页 / ' + names[view];
    destroyCharts();
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

document.querySelectorAll('.nav-item').forEach(el => {
    el.addEventListener('click', e => {
        e.preventDefault();
        setView(el.dataset.view);
    });
});

document.getElementById('btnRunDaily').addEventListener('click', async () => {
    if (!confirm('确认执行每日盘点流程？此操作将比对库存、生成工单、触发审计。')) return;
    const btn = document.getElementById('btnRunDaily');
    btn.disabled = true;
    btn.textContent = '执行中...';
    try {
        const r = await api('/api/daily/run', { method: 'POST' });
        toast(`每日盘点完成！差异${r.compare.total_diff}条，工单${r.orders_created}个`, 'success');
        setView('dashboard');
    } catch (e) { toast(e.message, 'error'); }
    btn.disabled = false;
    btn.textContent = '▶ 执行每日盘点';
});

function destroyCharts() {
    Object.values(state.charts).forEach(c => c && c.dispose && c.dispose());
    state.charts = {};
}

function makeChart(id, option) {
    const el = document.getElementById(id);
    if (!el) return;
    if (state.charts[id]) state.charts[id].dispose();
    const chart = echarts.init(el);
    chart.setOption(option);
    state.charts[id] = chart;
    return chart;
}

window.addEventListener('resize', () => {
    Object.values(state.charts).forEach(c => c && c.resize());
});

function tag(text, type = 'gray') {
    return `<span class="tag tag-${type}">${text}</span>`;
}
function diffStatusTag(s) {
    const map = {
        pending: ['待处理', 'yellow'],
        in_work_order: ['处理中', 'blue'],
        resolved: ['已解决', 'green'],
        ledger_updated: ['已入账', 'green'],
        matched: ['一致', 'gray'],
        rejected: ['已驳回', 'red'],
        completed: ['已完成', 'green']
    };
    const [t, c] = map[s] || [s, 'gray'];
    return tag(t, c);
}
function orderStatusTag(s) {
    const map = {
        pending: ['待分配', 'yellow'],
        assigned: ['待审核', 'blue'],
        in_progress: ['处理中', 'blue'],
        upgraded: ['已升级', 'red'],
        completed: ['已完成', 'green'],
        rejected: ['已驳回', 'red']
    };
    const [t, c] = map[s] || [s, 'gray'];
    return tag(t, c);
}
function taskStatusTag(s) {
    const map = {
        created: ['已创建', 'gray'],
        pushed: ['已推送', 'blue'],
        in_progress: ['盘点中', 'yellow'],
        completed: ['已完成', 'green'],
        cancelled: ['已取消', 'red']
    };
    const [t, c] = map[s] || [s, 'gray'];
    return tag(t, c);
}

async function loadMetaData() {
    try {
        state.warehouses = await api('/api/warehouses');
        state.categories = await api('/api/categories');
    } catch (e) { console.warn(e); }
}
function warehouseOptions(selected = '') {
    return state.warehouses.map(w =>
        `<option value="${w.code}" ${w.code === selected ? 'selected' : ''}>${w.name}</option>`
    ).join('');
}
function categoryOptions(selected = '') {
    return state.categories.map(c =>
        `<option value="${c}" ${c === selected ? 'selected' : ''}>${c}</option>`
    ).join('');
}

async function updateOrderBadge() {
    try {
        const orders = await api('/api/orders?status=assigned');
        const upgraded = await api('/api/orders?is_upgraded=true');
        const total = orders.length + upgraded.filter(o => o.status === 'upgraded').length;
        const badge = document.getElementById('orderBadge');
        badge.textContent = total;
        badge.style.display = total > 0 ? 'block' : 'none';
    } catch (e) {}
}

async function renderDashboard() {
    const el = document.getElementById('content');
    el.innerHTML = `
        <div class="stat-grid" id="statGrid"></div>
        <div class="grid-2">
            <div class="card">
                <div class="card-title">今日差异类型分布</div>
                <div class="chart-box" id="chartDiffType"></div>
            </div>
            <div class="card">
                <div class="card-title">各仓库差异对比</div>
                <div class="chart-box" id="chartByWh"></div>
            </div>
            <div class="card">
                <div class="card-title">差异金额品类分布</div>
                <div class="chart-box" id="chartByCat"></div>
            </div>
            <div class="card">
                <div class="card-title">近6个月差异金额趋势</div>
                <div class="chart-box" id="chartTrend"></div>
            </div>
        </div>
        <div class="card">
            <div class="card-title">最近差异明细
                <div class="actions">
                    <button class="btn btn-secondary btn-sm" data-action="exportDiff">📥 导出差异</button>
                </div>
            </div>
            <div class="table-wrap">
                <table id="diffTable">
                    <thead><tr>
                        <th>日期</th><th>仓库</th><th>SKU</th><th>商品</th><th>品类</th>
                        <th>实时</th><th>ERP</th><th>差异</th><th>类型</th><th>金额</th>
                        <th>超阈值</th><th>状态</th>
                    </tr></thead>
                    <tbody></tbody>
                </table>
            </div>
        </div>
    `;

    try {
        const data = await api('/api/dashboard');
        document.getElementById('statGrid').innerHTML = `
            <div class="stat-card">
                <span class="stat-icon">📦</span>
                <div class="stat-label">商品总数</div>
                <div class="stat-value">${data.overview.products}</div>
            </div>
            <div class="stat-card">
                <span class="stat-icon">🏪</span>
                <div class="stat-label">仓库数量</div>
                <div class="stat-value">${data.overview.warehouses}</div>
            </div>
            <div class="stat-card">
                <span class="stat-icon">📊</span>
                <div class="stat-label">今日差异</div>
                <div class="stat-value" style="color:#ef4444">${data.today.total}</div>
                <div class="stat-trend up">盘盈 ${data.today.surplus} / 盘亏 ${data.today.deficit}</div>
            </div>
            <div class="stat-card">
                <span class="stat-icon">💰</span>
                <div class="stat-label">今日差异金额</div>
                <div class="stat-value">¥${data.today.diff_amount.toLocaleString()}</div>
            </div>
            <div class="stat-card">
                <span class="stat-icon">📋</span>
                <div class="stat-label">待处理工单</div>
                <div class="stat-value" style="color:#f59e0b">${data.pending.work_orders}</div>
                <div class="stat-trend down">已升级 ${data.pending.upgraded_orders}</div>
            </div>
            <div class="stat-card">
                <span class="stat-icon">🔍</span>
                <div class="stat-label">专项审计</div>
                <div class="stat-value" style="color:#8b5cf6">${data.pending.special_audits}</div>
            </div>
            <div class="stat-card">
                <span class="stat-icon">📝</span>
                <div class="stat-label">盘点中任务</div>
                <div class="stat-value" style="color:#3b82f6">${data.pending.stock_tasks}</div>
                <div class="stat-trend up">已完成 ${data.pending.completed_tasks}</div>
            </div>
        `;

        makeChart('chartDiffType', {
            tooltip: { trigger: 'item' },
            legend: { bottom: 0 },
            series: [{
                type: 'pie', radius: ['45%', '70%'], center: ['50%', '45%'],
                label: { formatter: '{b}: {c}' },
                data: [
                    { value: data.today.surplus, name: '盘盈', itemStyle: { color: '#10b981' } },
                    { value: data.today.deficit, name: '盘亏', itemStyle: { color: '#ef4444' } },
                    { value: data.today.matched, name: '一致', itemStyle: { color: '#3b82f6' } },
                    { value: data.today.over_threshold, name: '超阈值', itemStyle: { color: '#f59e0b' } }
                ]
            }]
        });

        const whs = Object.keys(data.by_warehouse);
        makeChart('chartByWh', {
            tooltip: { trigger: 'axis' },
            legend: { top: 0 },
            grid: { left: 40, right: 20, top: 40, bottom: 30 },
            xAxis: { type: 'category', data: whs },
            yAxis: { type: 'value' },
            series: [
                { name: '盘盈', type: 'bar', data: whs.map(w => data.by_warehouse[w].surplus), itemStyle: { color: '#10b981' } },
                { name: '盘亏', type: 'bar', data: whs.map(w => data.by_warehouse[w].deficit), itemStyle: { color: '#ef4444' } }
            ]
        });

        const cats = Object.keys(data.by_category);
        makeChart('chartByCat', {
            tooltip: { trigger: 'item', formatter: '{b}: ¥{c}' },
            legend: { bottom: 0 },
            series: [{
                type: 'pie', radius: '65%', center: ['50%', '45%'],
                label: { formatter: '{b}: ¥{c}' },
                data: cats.map(c => ({ value: Math.round(data.by_category[c].amount), name: c }))
            }]
        });

        try {
            const mStats = await api('/api/monthly/stats');
            const months = [...new Set(mStats.map(s => s.stat_month))].sort().slice(-6);
            const seriesData = {};
            mStats.forEach(s => {
                if (!seriesData[s.warehouse]) seriesData[s.warehouse] = months.map(() => 0);
                const idx = months.indexOf(s.stat_month);
                if (idx >= 0) seriesData[s.warehouse][idx] = Math.round(s.total_diff_amount);
            });
            const colors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'];
            let ci = 0;
            makeChart('chartTrend', {
                tooltip: { trigger: 'axis' },
                legend: { top: 0 },
                grid: { left: 50, right: 20, top: 40, bottom: 30 },
                xAxis: { type: 'category', data: months },
                yAxis: { type: 'value', name: '金额' },
                series: Object.entries(seriesData).map(([wh, d]) => ({
                    name: wh, type: 'line', smooth: true, data: d,
                    itemStyle: { color: colors[ci++ % colors.length] }
                }))
            });
        } catch (e) {}

        const diffs = await api('/api/differences?limit=20');
        const tb = document.querySelector('#diffTable tbody');
        tb.innerHTML = diffs.data.length ? diffs.data.map(d => `
            <tr>
                <td>${d.check_date}</td>
                <td>${d.warehouse}</td>
                <td><code>${d.sku}</code></td>
                <td>${d.product_name}</td>
                <td>${d.category || '-'}</td>
                <td>${d.realtime_qty}</td>
                <td>${d.erp_qty}</td>
                <td style="color:${d.diff_qty > 0 ? '#10b981' : d.diff_qty < 0 ? '#ef4444' : ''};font-weight:600">${d.diff_qty > 0 ? '+' : ''}${d.diff_qty}</td>
                <td>${tag(d.diff_type, d.diff_type === '盘盈' ? 'green' : d.diff_type === '盘亏' ? 'red' : 'gray')}</td>
                <td>¥${d.diff_amount.toFixed(2)}</td>
                <td>${d.is_over_threshold ? tag('是', 'red') : '否'}</td>
                <td>${diffStatusTag(d.status)}</td>
            </tr>
        `).join('') : `<tr><td colspan="12"><div class="empty-state"><div class="emoji">📭</div><p>暂无差异数据</p></div></td></tr>`;
    } catch (e) {
        toast('加载数据失败: ' + e.message, 'error');
    }
}

async function renderOrders() {
    const el = document.getElementById('content');
    el.innerHTML = `
        <div class="card">
            <div class="card-title">筛选条件
                <div class="actions">
                    <button class="btn btn-secondary btn-sm" data-action="refreshOrders">🔄 刷新</button>
                    <button class="btn btn-primary btn-sm" data-action="upgradeAll">⏫ 一键升级超期工单</button>
                </div>
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label>仓库</label>
                    <select class="form-control" id="fWh"><option value="">全部</option>${warehouseOptions()}</select>
                </div>
                <div class="form-group">
                    <label>状态</label>
                    <select class="form-control" id="fStatus">
                        <option value="">全部</option>
                        <option value="pending">待分配</option>
                        <option value="assigned">待审核</option>
                        <option value="in_progress">处理中</option>
                        <option value="upgraded">已升级</option>
                        <option value="completed">已完成</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>是否升级</label>
                    <select class="form-control" id="fUp">
                        <option value="">全部</option>
                        <option value="true">已升级</option>
                        <option value="false">未升级</option>
                    </select>
                </div>
                <div class="form-group" style="flex:0 0 auto;align-self:flex-end">
                    <button class="btn btn-primary" id="btnFilterOrders">🔍 查询</button>
                </div>
            </div>
        </div>
        <div class="card">
            <div class="card-title">工单列表 <span id="orderCount" class="tag tag-blue" style="margin-left:8px"></span></div>
            <div class="table-wrap">
                <table>
                    <thead><tr>
                        <th>工单编号</th><th>仓库</th><th>品类</th><th>类型</th>
                        <th>审核人</th><th>主管</th><th>优先级</th><th>状态</th><th>差异数</th>
                        <th>创建时间</th><th>操作</th>
                    </tr></thead>
                    <tbody id="orderBody"></tbody>
                </table>
            </div>
        </div>
    `;
    document.getElementById('btnFilterOrders').addEventListener('click', loadOrders);
    loadOrders();
}

async function loadOrders() {
    const params = new URLSearchParams();
    const wh = document.getElementById('fWh').value;
    const st = document.getElementById('fStatus').value;
    const up = document.getElementById('fUp').value;
    if (wh) params.set('warehouse', wh);
    if (st) params.set('status', st);
    if (up) params.set('is_upgraded', up);
    const orders = await api('/api/orders?' + params.toString());
    document.getElementById('orderCount').textContent = orders.length + ' 条';
    document.getElementById('orderBody').innerHTML = orders.length ? orders.map(o => `
        <tr>
            <td><code>${o.order_no}</code></td>
            <td>${o.warehouse}</td>
            <td>${o.category || '-'}</td>
            <td>${tag(o.diff_type, o.diff_type === '盘盈' ? 'green' : 'red')}</td>
            <td>${o.auditor}</td>
            <td>${o.supervisor}</td>
            <td>${tag(o.priority, o.priority === 'high' ? 'red' : 'blue')}</td>
            <td>${orderStatusTag(o.status)}${o.is_upgraded ? ' ' + tag('已升级', 'red') : ''}</td>
            <td>${o.diff_count}</td>
            <td>${o.created_at?.slice(0, 16).replace('T', ' ') || ''}</td>
            <td>
                <button class="btn btn-sm btn-primary" data-action="viewOrder" data-no="${o.order_no}">查看</button>
                ${o.status !== 'completed' && o.status !== 'rejected' ? `
                    <button class="btn btn-sm btn-success" data-action="approveOrder" data-no="${o.order_no}">通过</button>
                    <button class="btn btn-sm btn-danger" data-action="rejectOrder" data-no="${o.order_no}">驳回</button>
                ` : ''}
            </td>
        </tr>
    `).join('') : `<tr><td colspan="11"><div class="empty-state"><div class="emoji">📋</div><p>暂无工单</p></div></td></tr>`;
}

async function renderCheck() {
    const el = document.getElementById('content');
    el.innerHTML = `
        <div class="card">
            <div class="card-title">发起盘点任务</div>
            <div class="form-row">
                <div class="form-group">
                    <label>盘点类型</label>
                    <select class="form-control" id="newType">
                        <option value="full">全盘</option>
                        <option value="sample">抽盘</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>仓库</label>
                    <select class="form-control" id="newWh">${warehouseOptions()}</select>
                </div>
                <div class="form-group">
                    <label>品类（可选）</label>
                    <select class="form-control" id="newCat"><option value="">全部</option>${categoryOptions()}</select>
                </div>
                <div class="form-group" id="ratioBox">
                    <label>抽样比例</label>
                    <input type="number" class="form-control" id="newRatio" min="0.05" max="1" step="0.05" value="0.3">
                </div>
                <div class="form-group" style="flex:0 0 auto;align-self:flex-end">
                    <button class="btn btn-primary" id="btnCreateTask">➕ 创建任务</button>
                </div>
            </div>
        </div>
        <div class="card">
            <div class="card-title">盘点任务列表
                <div class="actions">
                    <button class="btn btn-secondary btn-sm" data-action="refreshTasks">🔄 刷新</button>
                </div>
            </div>
            <div class="table-wrap">
                <table>
                    <thead><tr>
                        <th>任务编号</th><th>类型</th><th>仓库</th><th>品类</th>
                        <th>总数</th><th>已扫</th><th>一致</th><th>差异</th><th>状态</th>
                        <th>创建时间</th><th>操作</th>
                    </tr></thead>
                    <tbody id="taskBody"></tbody>
                </table>
            </div>
        </div>
    `;
    document.getElementById('newType').addEventListener('change', e => {
        document.getElementById('ratioBox').style.display = e.target.value === 'sample' ? '' : 'none';
    });
    document.getElementById('btnCreateTask').addEventListener('click', async () => {
        const body = {
            task_type: document.getElementById('newType').value,
            warehouse: document.getElementById('newWh').value,
            category: document.getElementById('newCat').value,
            sample_ratio: parseFloat(document.getElementById('newRatio').value)
        };
        try {
            const r = await api('/api/stock-checks', { method: 'POST', body });
            toast('任务创建成功: ' + r.task.task_no, 'success');
            loadTasks();
        } catch (e) { toast(e.message, 'error'); }
    });
    loadTasks();
}

async function loadTasks() {
    const tasks = await api('/api/stock-checks');
    document.getElementById('taskBody').innerHTML = tasks.length ? tasks.map(t => `
        <tr>
            <td><code>${t.task_no}</code></td>
            <td>${tag(t.task_type === 'full' ? '全盘' : '抽盘', 'blue')}</td>
            <td>${t.warehouse}</td>
            <td>${t.category || '-'}</td>
            <td>${t.total_items}</td>
            <td>${t.scanned_items}</td>
            <td>${t.matched_items}</td>
            <td style="color:${t.diff_items > 0 ? '#ef4444' : ''};font-weight:600">${t.diff_items}</td>
            <td>${taskStatusTag(t.status)}</td>
            <td>${t.created_at?.slice(0, 16).replace('T', ' ') || ''}</td>
            <td>
                <button class="btn btn-sm btn-secondary" data-action="viewTask" data-no="${t.task_no}">详情</button>
                ${t.status === 'created' ? `<button class="btn btn-sm btn-primary" data-action="pushTask" data-no="${t.task_no}">推送终端</button>` : ''}
                ${t.status !== 'completed' && t.status !== 'cancelled' ? `<button class="btn btn-sm btn-success" data-action="scanTask" data-no="${t.task_no}">扫码盘点</button>` : ''}
                ${t.status !== 'completed' && t.status !== 'cancelled' && t.scanned_items > 0 ? `<button class="btn btn-sm btn-primary" data-action="completeTask" data-no="${t.task_no}">完成</button>` : ''}
                <button class="btn btn-sm btn-secondary" data-action="taskReport" data-no="${t.task_no}">报告</button>
            </td>
        </tr>
    `).join('') : `<tr><td colspan="11"><div class="empty-state"><div class="emoji">📝</div><p>暂无任务，请创建</p></div></td></tr>`;
}

async function renderReports() {
    const el = document.getElementById('content');
    el.innerHTML = `
        <div class="grid-2">
            <div class="card">
                <div class="card-title">每日差异报告</div>
                <div class="form-row">
                    <div class="form-group">
                        <label>日期</label>
                        <input type="date" class="form-control" id="repDate" value="${new Date().toISOString().slice(0, 10)}">
                    </div>
                    <div class="form-group" style="flex:0 0 auto;align-self:flex-end">
                        <button class="btn btn-primary" id="btnGenDiff">📊 生成报告</button>
                    </div>
                </div>
                <div id="diffReportLinks" style="margin-top:12px"></div>
            </div>
            <div class="card">
                <div class="card-title">盘点任务报告</div>
                <div class="form-row">
                    <div class="form-group">
                        <label>任务编号</label>
                        <select class="form-control" id="taskSel"><option value="">选择任务</option></select>
                    </div>
                    <div class="form-group" style="flex:0 0 auto;align-self:flex-end">
                        <button class="btn btn-primary" id="btnShowTaskReport">📊 查看报告</button>
                    </div>
                </div>
            </div>
        </div>
        <div class="card" id="taskReportCard" style="display:none">
            <div class="card-title">盘点任务报告详情
                <div class="actions">
                    <button class="btn btn-sm btn-secondary" data-action="dlTaskExcel">📥 Excel</button>
                    <button class="btn btn-sm btn-secondary" data-action="dlTaskPdf">📥 PDF</button>
                </div>
            </div>
            <div id="taskReportBody"></div>
        </div>
    `;

    try {
        const tasks = await api('/api/stock-checks');
        document.getElementById('taskSel').innerHTML += tasks
            .filter(t => t.status === 'completed')
            .map(t => `<option value="${t.task_no}">${t.task_no} (${t.warehouse}, ${t.total_items}条)</option>`)
            .join('');
    } catch (e) {}

    document.getElementById('btnGenDiff').addEventListener('click', async () => {
        try {
            const r = await api('/api/reports/diff', { method: 'POST', body: { date: document.getElementById('repDate').value } });
            document.getElementById('diffReportLinks').innerHTML = `
                <div style="display:flex;gap:10px">
                    <a class="btn btn-secondary btn-sm" href="/api/download/${r.excel}" target="_blank">📥 下载 Excel</a>
                    <a class="btn btn-secondary btn-sm" href="/api/download/${r.pdf}" target="_blank">📥 下载 PDF</a>
                </div>
            `;
            toast('报告生成成功', 'success');
        } catch (e) { toast(e.message, 'error'); }
    });

    document.getElementById('btnShowTaskReport').addEventListener('click', async () => {
        const no = document.getElementById('taskSel').value;
        if (!no) { toast('请选择任务', 'error'); return; }
        try {
            const r = await api('/api/stock-checks/' + no + '/report');
            showTaskReport(r);
        } catch (e) { toast(e.message, 'error'); }
    });
}

function showTaskReport(r) {
    document.getElementById('taskReportCard').style.display = '';
    const trb = document.getElementById('taskReportBody');
    trb.innerHTML = `
        <div class="stat-grid" style="grid-template-columns:repeat(5,1fr)">
            <div class="stat-card"><div class="stat-label">总条目</div><div class="stat-value">${r.total}</div></div>
            <div class="stat-card"><div class="stat-label">已扫描</div><div class="stat-value" style="color:#3b82f6">${r.scanned}</div></div>
            <div class="stat-card"><div class="stat-label">一致</div><div class="stat-value" style="color:#10b981">${r.matched}</div></div>
            <div class="stat-card"><div class="stat-label">差异</div><div class="stat-value" style="color:#ef4444">${r.diff}</div></div>
            <div class="stat-card"><div class="stat-label">差异金额</div><div class="stat-value">¥${r.total_diff_amount.toLocaleString()}</div></div>
        </div>
        <div class="grid-2" style="margin-top:20px">
            <div class="card" style="margin-bottom:0">
                <div class="card-title">扫描/一致/差异对比</div>
                <div class="chart-box-sm" id="tc1"></div>
            </div>
            <div class="card" style="margin-bottom:0">
                <div class="card-title">品类差异分布</div>
                <div class="chart-box-sm" id="tc2"></div>
            </div>
        </div>
        <div class="card" style="margin-top:20px">
            <div class="card-title">差异明细</div>
            <div class="table-wrap">
                <table>
                    <thead><tr><th>SKU</th><th>商品</th><th>系统数量</th><th>扫码数量</th><th>差异</th></tr></thead>
                    <tbody>${r.diff_detail.length ? r.diff_detail.map(d => `
                        <tr>
                            <td><code>${d.sku}</code></td>
                            <td>${d.product_name}</td>
                            <td>${d.system_qty}</td>
                            <td>${d.scanned_qty}</td>
                            <td style="color:${d.diff_qty > 0 ? '#10b981' : '#ef4444'};font-weight:600">${d.diff_qty > 0 ? '+' : ''}${d.diff_qty}</td>
                        </tr>
                    `).join('') : '<tr><td colspan="5">无差异</td></tr>'}</tbody>
                </table>
            </div>
        </div>
    `;
    state._taskNo = r.task_no;

    makeChart('tc1', {
        tooltip: {},
        xAxis: { type: 'category', data: ['已扫描', '一致', '差异'] },
        yAxis: { type: 'value' },
        series: [{ type: 'bar', data: [
            { value: r.scanned, itemStyle: { color: '#3b82f6' } },
            { value: r.matched, itemStyle: { color: '#10b981' } },
            { value: r.diff, itemStyle: { color: '#ef4444' } }
        ], label: { show: true, position: 'top' } }]
    });

    const cats = Object.keys(r.category_diff);
    makeChart('tc2', {
        tooltip: { trigger: 'axis' },
        legend: { top: 0 },
        grid: { left: 80, right: 20, top: 40, bottom: 30 },
        xAxis: { type: 'value' },
        yAxis: { type: 'category', data: cats },
        series: [
            { name: '差异条目', type: 'bar', data: cats.map(c => r.category_diff[c].diff), itemStyle: { color: '#f59e0b' } },
            { name: '总条目', type: 'bar', data: cats.map(c => r.category_diff[c].count), itemStyle: { color: '#3b82f6' } }
        ]
    });
}

async function renderMonthly() {
    const el = document.getElementById('content');
    el.innerHTML = `
        <div class="card">
            <div class="card-title">月度统计概览
                <div class="actions">
                    <button class="btn btn-secondary btn-sm" id="btnRunMonthly">🔄 生成上月报告</button>
                    <button class="btn btn-sm btn-secondary" id="dlMonthlyExcel">📥 下载 Excel</button>
                    <button class="btn btn-sm btn-secondary" id="dlMonthlyPdf">📥 下载 PDF</button>
                </div>
            </div>
            <div id="monthlyLinks"></div>
        </div>
        <div class="grid-2">
            <div class="card">
                <div class="card-title">盘点完成率趋势 (%)</div>
                <div class="chart-box" id="mc1"></div>
            </div>
            <div class="card">
                <div class="card-title">差异解决率趋势 (%)</div>
                <div class="chart-box" id="mc2"></div>
            </div>
            <div class="card">
                <div class="card-title">平均处理时长 (小时)</div>
                <div class="chart-box" id="mc3"></div>
            </div>
            <div class="card">
                <div class="card-title">总差异金额趋势</div>
                <div class="chart-box" id="mc4"></div>
            </div>
        </div>
        <div class="card">
            <div class="card-title">详细数据</div>
            <div class="table-wrap">
                <table>
                    <thead><tr>
                        <th>月份</th><th>仓库</th><th>总条目</th><th>已盘点</th><th>完成率</th>
                        <th>差异数</th><th>已解决</th><th>解决率</th><th>平均处理(小时)</th><th>差异金额</th>
                    </tr></thead>
                    <tbody id="msBody"></tbody>
                </table>
            </div>
        </div>
    `;

    document.getElementById('btnRunMonthly').addEventListener('click', async () => {
        if (!confirm('生成上月月度统计报告？')) return;
        try {
            const r = await api('/api/monthly/run', { method: 'POST' });
            document.getElementById('monthlyLinks').innerHTML = `
                <div style="margin-top:10px;display:flex;gap:10px">
                    <a class="btn btn-secondary btn-sm" href="/api/download/${r.reports.excel}" target="_blank">📥 Excel</a>
                    <a class="btn btn-secondary btn-sm" href="/api/download/${r.reports.pdf}" target="_blank">📥 PDF</a>
                </div>
            `;
            toast('月度报告生成成功', 'success');
            loadMonthly();
        } catch (e) { toast(e.message, 'error'); }
    });

    loadMonthly();
}

async function loadMonthly() {
    const stats = await api('/api/monthly/stats');
    const months = [...new Set(stats.map(s => s.stat_month))].sort().slice(-6);
    const whs = [...new Set(stats.map(s => s.warehouse))];
    const colors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'];

    const mkSeries = (key) => whs.map((wh, i) => ({
        name: wh, type: 'line', smooth: true,
        data: months.map(m => {
            const s = stats.find(x => x.stat_month === m && x.warehouse === wh);
            return s ? +s[key].toFixed(2) : 0;
        }),
        itemStyle: { color: colors[i % colors.length] }
    }));

    makeChart('mc1', {
        tooltip: { trigger: 'axis' }, legend: { top: 0 },
        grid: { left: 50, right: 20, top: 40, bottom: 30 },
        xAxis: { type: 'category', data: months },
        yAxis: { type: 'value', max: 100 },
        series: mkSeries('completion_rate')
    });
    makeChart('mc2', {
        tooltip: { trigger: 'axis' }, legend: { top: 0 },
        grid: { left: 50, right: 20, top: 40, bottom: 30 },
        xAxis: { type: 'category', data: months },
        yAxis: { type: 'value', max: 100 },
        series: mkSeries('resolution_rate')
    });
    makeChart('mc3', {
        tooltip: { trigger: 'axis' }, legend: { top: 0 },
        grid: { left: 50, right: 20, top: 40, bottom: 30 },
        xAxis: { type: 'category', data: months },
        yAxis: { type: 'value' },
        series: mkSeries('avg_process_hours')
    });
    makeChart('mc4', {
        tooltip: { trigger: 'axis' }, legend: { top: 0 },
        grid: { left: 50, right: 20, top: 40, bottom: 30 },
        xAxis: { type: 'category', data: months },
        yAxis: { type: 'value' },
        series: mkSeries('total_diff_amount')
    });

    document.getElementById('msBody').innerHTML = stats.slice(0, 60).map(s => `
        <tr>
            <td>${s.stat_month}</td>
            <td>${s.warehouse}</td>
            <td>${s.total_items}</td>
            <td>${s.checked_items}</td>
            <td>${tag(s.completion_rate.toFixed(1) + '%', s.completion_rate > 90 ? 'green' : s.completion_rate > 70 ? 'yellow' : 'red')}</td>
            <td>${s.diff_items}</td>
            <td>${s.resolved_items}</td>
            <td>${tag(s.resolution_rate.toFixed(1) + '%', s.resolution_rate > 90 ? 'green' : s.resolution_rate > 70 ? 'yellow' : 'red')}</td>
            <td>${s.avg_process_hours.toFixed(1)}</td>
            <td>¥${s.total_diff_amount.toFixed(2)}</td>
        </tr>
    `).join('') || '<tr><td colspan="10"><div class="empty-state">暂无数据，请先生成月度报告</div></td></tr>';
}

async function renderLogs() {
    const el = document.getElementById('content');
    el.innerHTML = `
        <div class="card">
            <div class="card-title">筛选条件
                <div class="actions">
                    <button class="btn btn-secondary btn-sm" data-action="exportLogs">📥 导出日志</button>
                    <button class="btn btn-sm btn-secondary" id="btnSearchLog">🔍 查询</button>
                </div>
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label>仓库</label>
                    <select class="form-control" id="lWh"><option value="">全部</option>${warehouseOptions()}</select>
                </div>
                <div class="form-group">
                    <label>操作类型</label>
                    <input type="text" class="form-control" id="lOpType" placeholder="如 DAILY_COMPARE">
                </div>
                <div class="form-group">
                    <label>操作人</label>
                    <input type="text" class="form-control" id="lOp">
                </div>
                <div class="form-group">
                    <label>单号/SKU</label>
                    <input type="text" class="form-control" id="lRef">
                </div>
                <div class="form-group">
                    <label>开始时间</label>
                    <input type="date" class="form-control" id="lStart">
                </div>
                <div class="form-group">
                    <label>结束时间</label>
                    <input type="date" class="form-control" id="lEnd">
                </div>
            </div>
        </div>
        <div class="card">
            <div class="card-title">操作日志 <span id="logCount" class="tag tag-blue" style="margin-left:8px"></span></div>
            <div class="table-wrap">
                <table>
                    <thead><tr>
                        <th>时间</th><th>操作类型</th><th>操作人</th><th>仓库</th>
                        <th>品类</th><th>SKU</th><th>单号</th><th>详情</th>
                    </tr></thead>
                    <tbody id="logBody"></tbody>
                </table>
            </div>
            <div class="pagination" id="logPagination"></div>
        </div>
    `;
    document.getElementById('btnSearchLog').addEventListener('click', () => { state.logPage = 1; loadLogs(); });
    document.querySelector('[data-action="exportLogs"]').addEventListener('click', exportLogs);
    loadLogs();
}

async function loadLogs() {
    const p = new URLSearchParams({ page: state.logPage, limit: 50 });
    if (document.getElementById('lWh').value) p.set('warehouse', document.getElementById('lWh').value);
    if (document.getElementById('lOpType').value) p.set('operation_type', document.getElementById('lOpType').value);
    if (document.getElementById('lOp').value) p.set('operator', document.getElementById('lOp').value);
    if (document.getElementById('lRef').value) p.set('reference_no', document.getElementById('lRef').value);
    if (document.getElementById('lStart').value) p.set('start_time', document.getElementById('lStart').value);
    if (document.getElementById('lEnd').value) p.set('end_time', document.getElementById('lEnd').value);

    const r = await api('/api/logs?' + p.toString());
    document.getElementById('logCount').textContent = r.total + ' 条';
    document.getElementById('logBody').innerHTML = r.data.length ? r.data.map(l => `
        <tr>
            <td>${l.log_time?.slice(0, 19).replace('T', ' ') || ''}</td>
            <td>${tag(l.operation_type, 'purple')}</td>
            <td>${l.operator || '-'}</td>
            <td>${l.warehouse || '-'}</td>
            <td>${l.category || '-'}</td>
            <td>${l.sku || '-'}</td>
            <td>${l.reference_no || '-'}</td>
            <td style="max-width:400px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="${l.detail}">${l.detail}</td>
        </tr>
    `).join('') : '<tr><td colspan="8"><div class="empty-state">暂无日志</div></td></tr>';

    const totalPages = Math.ceil(r.total / r.limit);
    const pg = document.getElementById('logPagination');
    let html = `<button class="page-btn" ${state.logPage <= 1 ? 'disabled' : ''} onclick="state.logPage=${state.logPage - 1};loadLogs()">上一页</button>`;
    html += `<button class="page-btn active">${state.logPage} / ${totalPages || 1}</button>`;
    html += `<button class="page-btn" ${state.logPage >= totalPages ? 'disabled' : ''} onclick="state.logPage=${state.logPage + 1};loadLogs()">下一页</button>`;
    pg.innerHTML = html;
}

async function exportLogs() {
    const p = new URLSearchParams();
    if (document.getElementById('lWh').value) p.set('warehouse', document.getElementById('lWh').value);
    if (document.getElementById('lStart').value) p.set('start_time', document.getElementById('lStart').value);
    if (document.getElementById('lEnd').value) p.set('end_time', document.getElementById('lEnd').value);
    window.open('/api/export/logs?' + p.toString(), '_blank');
}

async function handleAction(act, el) {
    const no = el.dataset.no;
    try {
        switch (act) {
            case 'refreshOrders': loadOrders(); break;
            case 'upgradeAll': {
                if (!confirm('一键升级所有超48小时未处理工单？')) return;
                await api('/api/orders/any/upgrade', { method: 'POST' }).catch(() => {});
                const orders = await api('/api/orders?is_upgraded=true');
                await Promise.all(orders.map(o => api(`/api/orders/${o.order_no}/upgrade`, { method: 'POST' })));
                toast('已执行升级检查', 'success');
                loadOrders();
                break;
            }
            case 'viewOrder': showOrderDetail(no); break;
            case 'approveOrder': reviewOrder(no, true); break;
            case 'rejectOrder': reviewOrder(no, false); break;
            case 'refreshTasks': loadTasks(); break;
            case 'viewTask': showTaskDetail(no); break;
            case 'pushTask': {
                await api(`/api/stock-checks/${no}/push`, { method: 'POST' });
                toast('已推送至手持终端', 'success');
                loadTasks();
                break;
            }
            case 'scanTask': openScanPanel(no); break;
            case 'completeTask': {
                if (!confirm('确认完成该盘点任务？')) return;
                const r = await api(`/api/stock-checks/${no}/complete`, { method: 'POST' });
                toast('任务完成: ' + r.summary.task_no, 'success');
                loadTasks();
                break;
            }
            case 'taskReport': {
                setView('reports');
                document.getElementById('taskSel').value = no;
                document.getElementById('btnShowTaskReport').click();
                break;
            }
            case 'exportDiff': {
                window.open('/api/export/differences', '_blank');
                break;
            }
            case 'dlTaskExcel': case 'dlTaskPdf': {
                const tno = state._taskNo;
                if (!tno) { toast('请先查看报告', 'error'); return; }
                try {
                    const tasks = await api('/api/stock-checks?status=completed');
                    window.open(`/api/download/stock_check_${tno}.xlsx`, '_blank');
                } catch (e) {
                    toast('请先在盘点任务列表中点击「完成」生成报告后下载', 'error');
                }
                break;
            }
        }
    } catch (e) { toast(e.message, 'error'); }
}

async function showOrderDetail(no) {
    const order = (await api('/api/orders')).find(o => o.order_no === no);
    if (!order) return;
    const diffs = await api(`/api/differences?limit=500`);
    const related = diffs.data.filter(d => d.work_order_id === order.id);
    showModal(`
        <div class="modal-header">
            <h3>工单详情 - ${no}</h3>
            <button class="modal-close">✕</button>
        </div>
        <div class="grid-2">
            <div>
                <p><strong>仓库：</strong>${order.warehouse}</p>
                <p><strong>品类：</strong>${order.category || '-'}</p>
                <p><strong>差异类型：</strong>${tag(order.diff_type, order.diff_type === '盘盈' ? 'green' : 'red')}</p>
                <p><strong>审核人：</strong>${order.auditor}</p>
                <p><strong>主管：</strong>${order.supervisor}</p>
                <p><strong>优先级：</strong>${tag(order.priority, order.priority === 'high' ? 'red' : 'blue')}</p>
                <p><strong>状态：</strong>${orderStatusTag(order.status)}${order.is_upgraded ? ' ' + tag('已升级', 'red') : ''}</p>
                <p><strong>创建：</strong>${order.created_at?.replace('T', ' ') || ''}</p>
                <p><strong>审核备注：</strong>${order.review_comment || '-'}</p>
            </div>
            <div>
                <p><strong>差异条目数：</strong>${related.length}</p>
            </div>
        </div>
        <div class="card" style="margin-top:16px">
            <div class="card-title">差异明细</div>
            <div class="table-wrap">
                <table>
                    <thead><tr><th>SKU</th><th>商品</th><th>品类</th><th>实时</th><th>ERP</th><th>差异</th><th>金额</th><th>状态</th></tr></thead>
                    <tbody>${related.length ? related.map(d => `
                        <tr>
                            <td><code>${d.sku}</code></td>
                            <td>${d.product_name}</td>
                            <td>${d.category || '-'}</td>
                            <td>${d.realtime_qty}</td>
                            <td>${d.erp_qty}</td>
                            <td style="color:${d.diff_qty > 0 ? '#10b981' : '#ef4444'}">${d.diff_qty > 0 ? '+' : ''}${d.diff_qty}</td>
                            <td>¥${d.diff_amount.toFixed(2)}</td>
                            <td>${diffStatusTag(d.status)}</td>
                        </tr>
                    `).join('') : '<tr><td colspan="8">无数据</td></tr>'}</tbody>
                </table>
            </div>
        </div>
    `, true);
}

async function reviewOrder(no, approved) {
    showModal(`
        <div class="modal-header">
            <h3>${approved ? '审核通过' : '审核驳回'} - ${no}</h3>
            <button class="modal-close">✕</button>
        </div>
        <div class="form-group">
            <label>审核备注</label>
            <textarea class="form-control" id="reviewComment" placeholder="请输入审核意见..."></textarea>
        </div>
        <div class="modal-footer">
            <button class="btn btn-secondary" onclick="hideModal()">取消</button>
            <button class="btn ${approved ? 'btn-success' : 'btn-danger'}" id="btnConfirmReview">确认${approved ? '通过' : '驳回'}</button>
        </div>
    `);
    document.getElementById('btnConfirmReview').addEventListener('click', async () => {
        try {
            await api(`/api/orders/${no}/review`, {
                method: 'POST',
                body: { approved, comment: document.getElementById('reviewComment').value }
            });
            toast('审核成功，台账已更新', 'success');
            hideModal();
            loadOrders();
            updateOrderBadge();
        } catch (e) { toast(e.message, 'error'); }
    });
}

async function showTaskDetail(no) {
    const r = await api('/api/stock-checks/' + no);
    showModal(`
        <div class="modal-header">
            <h3>盘点任务详情 - ${no}</h3>
            <button class="modal-close">✕</button>
        </div>
        <p><strong>仓库：</strong>${r.warehouse}　<strong>类型：</strong>${tag(r.task_type === 'full' ? '全盘' : '抽盘', 'blue')}　<strong>状态：</strong>${taskStatusTag(r.status)}</p>
        <p><strong>条目总数：</strong>${r.items.length}　<strong>已扫：</strong>${r.items.filter(i => i.is_scanned).length}</p>
        <div style="margin-top:12px;max-height:400px;overflow-y:auto">
            ${r.items.map(i => `
                <div class="checklist-item ${i.is_scanned ? 'scanned' : ''}">
                    <span class="sku">${i.sku}</span>
                    <span class="name">${i.product_name}</span>
                    <span class="qty">系统: ${i.system_qty}</span>
                    ${i.is_scanned ? `
                        <span class="qty">扫码: ${i.scanned_qty}</span>
                        <span class="diff ${i.scanned_qty - i.system_qty > 0 ? 'plus' : i.scanned_qty - i.system_qty < 0 ? 'minus' : ''}">
                            差异: ${i.scanned_qty - i.system_qty > 0 ? '+' : ''}${i.scanned_qty - i.system_qty}
                        </span>
                    ` : tag('未扫', 'gray')}
                </div>
            `).join('')}
        </div>
    `, true);
}

async function openScanPanel(no) {
    const r = await api('/api/stock-checks/' + no);
    state.currentScanTask = { no, items: r.items };
    renderScanPanel();
}

function renderScanPanel() {
    const { no, items } = state.currentScanTask;
    const unscanned = items.filter(i => !i.is_scanned);
    const scanned = items.filter(i => i.is_scanned);

    showModal(`
        <div class="modal-header">
            <h3>📱 手持终端扫码模拟 - ${no}</h3>
            <button class="modal-close">✕</button>
        </div>
        <div class="scan-box">
            <h4>快速扫码录入</h4>
            <div class="form-row">
                <div class="form-group" style="flex:2">
                    <label>选择 SKU / 输入条码</label>
                    <select class="form-control" id="scanSku">
                        <option value="">-- 选择未扫 SKU --</option>
                        ${unscanned.map(i => `<option value="${i.sku}">${i.sku} - ${i.product_name} (系统: ${i.system_qty})</option>`).join('')}
                    </select>
                </div>
                <div class="form-group" style="flex:1">
                    <label>实际数量</label>
                    <input type="number" class="form-control" id="scanQty" value="0" min="0">
                </div>
                <div class="form-group" style="flex:0 0 auto;align-self:flex-end">
                    <button class="btn btn-success" id="btnSubmitScan">✅ 扫码提交</button>
                </div>
            </div>
            <div style="margin-top:8px;color:#64748b;font-size:12px">
                💡 提示：点击下方「快速填充一致」可将未扫 SKU 自动按系统数量填充
            </div>
            <div style="margin-top:10px">
                <button class="btn btn-secondary btn-sm" id="btnAutoFill">⚡ 快速填充一致</button>
                <button class="btn btn-secondary btn-sm" id="btnRandomFill">🎲 模拟随机差异</button>
            </div>
        </div>
        <div style="display:flex;gap:12px;margin-bottom:12px">
            ${tag(`总条目: ${items.length}`, 'blue')}
            ${tag(`已扫: ${scanned.length}`, 'green')}
            ${tag(`待扫: ${unscanned.length}`, unscanned.length ? 'yellow' : 'gray')}
        </div>
        <div style="max-height:320px;overflow-y:auto" id="scanItemsList">
            ${items.map(i => `
                <div class="checklist-item ${i.is_scanned ? 'scanned' : ''}">
                    <span class="sku">${i.sku}</span>
                    <span class="name">${i.product_name}</span>
                    <span class="qty">系统: ${i.system_qty}</span>
                    ${i.is_scanned ? `
                        <span class="qty">扫码: ${i.scanned_qty}</span>
                        <span class="diff ${i.scanned_qty - i.system_qty > 0 ? 'plus' : i.scanned_qty - i.system_qty < 0 ? 'minus' : ''}">
                            ${i.scanned_qty - i.system_qty > 0 ? '+' : ''}${i.scanned_qty - i.system_qty}
                        </span>
                    ` : tag('待扫', 'gray')}
                </div>
            `).join('')}
        </div>
    `, true);

    document.getElementById('btnSubmitScan').addEventListener('click', async () => {
        const sku = document.getElementById('scanSku').value;
        const qty = parseFloat(document.getElementById('scanQty').value);
        if (!sku) { toast('请选择 SKU', 'error'); return; }
        if (isNaN(qty)) { toast('请输入数量', 'error'); return; }
        try {
            await api('/api/scan', { method: 'POST', body: { task_no: no, sku, scanned_qty: qty } });
            toast(`扫码成功: ${sku} = ${qty}`, 'success');
            const r = await api('/api/stock-checks/' + no);
            state.currentScanTask = { no, items: r.items };
            renderScanPanel();
        } catch (e) { toast(e.message, 'error'); }
    });

    document.getElementById('btnAutoFill').addEventListener('click', async () => {
        if (!confirm('将所有未扫 SKU 自动按系统数量填充？')) return;
        let done = 0;
        for (const i of unscanned) {
            try {
                await api('/api/scan', { method: 'POST', body: { task_no: no, sku: i.sku, scanned_qty: i.system_qty } });
                done++;
            } catch (e) {}
        }
        toast(`自动填充 ${done} 条`, 'success');
        const r = await api('/api/stock-checks/' + no);
        state.currentScanTask = { no, items: r.items };
        renderScanPanel();
    });

    document.getElementById('btnRandomFill').addEventListener('click', async () => {
        if (!confirm('模拟随机差异填充？')) return;
        let done = 0;
        for (const i of unscanned) {
            const diff = Math.random() < 0.7 ? 0 : Math.floor(Math.random() * 10) - 5;
            const qty = Math.max(0, i.system_qty + diff);
            try {
                await api('/api/scan', { method: 'POST', body: { task_no: no, sku: i.sku, scanned_qty: qty } });
                done++;
            } catch (e) {}
        }
        toast(`随机填充 ${done} 条`, 'success');
        const r = await api('/api/stock-checks/' + no);
        state.currentScanTask = { no, items: r.items };
        renderScanPanel();
    });
}

(async function init() {
    await loadMetaData();
    setView('dashboard');
    updateOrderBadge();
    setInterval(updateOrderBadge, 30000);
})();
