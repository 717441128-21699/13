# 企业级库存盘点与差异自动化管理系统

## 功能特性

### 1. 每日自动比对
- 自动拉取各仓库实时库存与ERP账面数据
- 逐条比对，自动标记**盘盈**/**盘亏**差异
- 阈值判断：数量>5 或 金额>1000 自动标记超阈值

### 2. 盘点工单自动化
- 超阈值差异按**仓库+品类+差异类型**自动分组生成工单
- 按品类自动分配审核人（A/B/C类对应不同审核人）
- **超48小时未处理**自动升级至仓库主管

### 3. 审核与台账更新
- 工单审核（通过/驳回），备注记录
- 审核通过后**自动更新库存台账**
- 同步回写ERP账面数据

### 4. 专项审计触发
- 监控品类月度差异率
- **连续3个月差异率>3%** 自动触发专项审计流程

### 5. 手动盘点任务
- 支持**全盘**与**抽盘**（可配置抽样比例）
- 自动生成盘点清单，推送至手持终端
- 扫码录入自动匹配库存，差异即时显示

### 6. 报告与导出
- 盘点报告含对比图表：差异率、金额分布、品类分布
- **PDF** 和 **Excel** 双通道导出

### 7. 月度统计分析
- 各仓库盘点完成率、差异解决率、平均处理时长
- 6个月趋势分析图表
- PDF/Excel报告导出

### 8. 操作日志与查询
- 全量操作日志记录
- 支持**仓库+品类+时间段**组合查询
- 差异明细批量导出

## 快速开始

### 启动 Web 界面（推荐）

```bash
pip install -r requirements.txt
python run_server.py
```

启动后访问：
- **前端仪表板**：http://localhost:5000
- **RESTful API**：http://localhost:5000/api/

首次启动会自动初始化数据库并生成示例数据（3仓库×100商品×6个月历史数据）。

### Web 界面功能

| 页面 | 功能 |
|------|------|
| 📊 仪表板 | 库存概览、KPI 卡片、ECharts 图表（差异分布/仓库对比/品类分布/月度趋势）、最近差异 |
| 📋 盘点工单 | 多条件筛选、查看工单详情、审核通过/驳回（自动更新台账）、一键升级超期工单 |
| 📝 手动盘点 | 创建全盘/抽盘任务、推送终端、扫码录入（含模拟一致/随机差异）、完成任务 |
| 📈 报告中心 | 生成每日差异报告、查看盘点任务报告（含 ECharts 图表）、下载 PDF/Excel |
| 📅 月度分析 | 6 个月 4 张趋势图（完成率/解决率/处理时长/差异金额）、下载报告 |
| 📜 操作日志 | 多条件组合查询、分页、批量导出 Excel |

扫码接口：`POST /api/scan`
```json
{ "task_no": "SC20260607...", "sku": "SKU00001", "scanned_qty": 123, "scanner": "张三" }
```

### CLI 命令行（备选）

### 生成示例数据

```bash
python main.py seed                    # 基础示例数据
python main.py seed --historical       # 含6个月历史差异数据（用于测试审计/月度统计）
```

### 执行每日盘点流程

```bash
python main.py daily                   # 执行今日盘点
python main.py daily --date 2026-06-01 # 指定日期
```

流程：比对 → 生成工单 → 升级检查 → 审核更新 → 审计检查 → 出报告

### 手动盘点任务

```bash
# 创建全盘任务
python main.py stock-check create --type full --warehouse WH001

# 创建抽盘任务（30%抽样）
python main.py stock-check create --type sample --warehouse WH001 --ratio 0.3

# 推送至手持终端
python main.py stock-check push --task-no SCxxxxxxxxx

# 模拟扫码
python main.py stock-check scan --task-no SCxxxxxxxxx --count 10

# 完成并生成报告
python main.py stock-check complete --task-no SCxxxxxxxxx
```

### 查询与导出

```bash
python main.py query dashboard         # 仪表板概览
python main.py query diff              # 查询差异
python main.py query order             # 查询工单
python main.py query log               # 查询操作日志
python main.py query export_diff       # 批量导出差异明细
python main.py query export_log        # 导出操作日志
```

### 专项审计

```bash
python main.py audit check             # 检查并触发专项审计
python main.py audit list              # 查看待处理审计
python main.py audit complete --audit-no SAxxxxxxxxx --report "审计报告内容"
```

### 月度报告

```bash
python main.py monthly                 # 生成上月报告
python main.py monthly --month 2026-05 # 指定月份
```

### 启动定时调度

```bash
python main.py scheduler
```

默认调度：
- 每日 02:00 执行库存盘点
- 每月 1日 03:00 生成月度报告

## 配置说明

所有配置在 [config.py](file:///e:/solo/13/config.py) 中：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| THRESHOLD_QUANTITY | 5 | 数量阈值 |
| THRESHOLD_AMOUNT | 1000.0 | 金额阈值 |
| UPGRADE_HOURS | 48 | 超期升级小时数 |
| AUDIT_DIFF_RATE | 0.03 (3%) | 审计触发差异率 |
| AUDIT_CONSECUTIVE_MONTHS | 3 | 连续触发月数 |

## 模块结构

| 文件 | 功能 |
|------|------|
| [main.py](file:///e:/solo/13/main.py) | 主入口：CLI命令、调度器 |
| [config.py](file:///e:/solo/13/config.py) | 全局配置 |
| [models.py](file:///e:/solo/13/models.py) | 数据模型（10+实体表） |
| [database.py](file:///e:/solo/13/database.py) | 数据库连接与会话管理 |
| [inventory_compare.py](file:///e:/solo/13/inventory_compare.py) | 每日库存比对与差异标记 |
| [work_order_manager.py](file:///e:/solo/13/work_order_manager.py) | 工单生成、分配、升级、审核 |
| [ledger_manager.py](file:///e:/solo/13/ledger_manager.py) | 库存台账更新 |
| [special_audit.py](file:///e:/solo/13/special_audit.py) | 专项审计触发与管理 |
| [stock_check.py](file:///e:/solo/13/stock_check.py) | 手动盘点任务与手持终端对接 |
| [report_generator.py](file:///e:/solo/13/report_generator.py) | 差异/盘点报告与图表、PDF/Excel导出 |
| [monthly_reporter.py](file:///e:/solo/13/monthly_reporter.py) | 月度统计与趋势分析 |
| [query_export.py](file:///e:/solo/13/query_export.py) | 组合查询与批量导出 |
| [operation_logger.py](file:///e:/solo/13/operation_logger.py) | 操作日志记录 |
| [logger.py](file:///e:/solo/13/logger.py) | 文件日志工具 |
| [sample_data.py](file:///e:/solo/13/sample_data.py) | 示例数据生成 |

## 输出目录

- `reports/` - PDF报告和图表
- `exports/` - Excel导出文件
- `logs/` - 运行日志
