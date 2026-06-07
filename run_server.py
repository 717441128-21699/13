import os

if __name__ == '__main__':
    print("=" * 60)
    print("  企业级库存盘点与差异自动化管理系统 - Web 服务")
    print("=" * 60)

    print("\n[初始化] 正在创建数据库表...")
    from database import init_db
    init_db()
    print("[初始化] 数据库表创建完成")

    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'inventory.db')
    if not os.path.exists(db_path) or os.path.getsize(db_path) < 10000:
        print("[初始化] 检测到空数据库，正在生成示例数据...")
        from sample_data import seed_sample_data, seed_historical_data
        seed_sample_data()
        seed_historical_data()
        print("[初始化] 示例数据生成完成！\n")

    print("[启动] 正在加载 Flask 应用...")
    from api import app

    host = '0.0.0.0'
    port = 5000
    print(f"  📊 仪表板与前端: http://localhost:{port}")
    print(f"  🔌 REST API 基础:  http://localhost:{port}/api/")
    print(f"  📖 API 接口示例:")
    print(f"     GET  /api/dashboard          仪表板统计")
    print(f"     GET  /api/differences        差异列表")
    print(f"     GET  /api/orders             工单列表")
    print(f"     POST /api/scan               扫码录入")
    print(f"     GET  /api/logs               操作日志")
    print(f"     GET  /api/download/<文件>    下载报告")
    print("\n按 Ctrl+C 停止服务")
    print("=" * 60)

    app.run(host=host, port=port, debug=False, threaded=True)
