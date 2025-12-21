"""慢查询分析工具

提供慢查询的详细分析和报告生成功能
"""

from datetime import datetime
from typing import Any

from src.common.database.utils.monitoring import get_monitor
from src.common.logger import get_logger

logger = get_logger("database.slow_query_analyzer")


class SlowQueryAnalyzer:
    """慢查询分析器"""

    @staticmethod
    def generate_html_report(output_file: str | None = None) -> str:
        """生成HTML格式的慢查询报告

        Args:
            output_file: 输出文件路径，None 表示只返回HTML字符串

        Returns:
            HTML字符串
        """
        monitor = get_monitor()
        report = monitor.get_slow_query_report()
        metrics = monitor.get_metrics()

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>数据库慢查询报告</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell', sans-serif;
            background: #f5f5f5;
            padding: 20px;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }}
        header h1 {{
            font-size: 28px;
            margin-bottom: 10px;
        }}
        header p {{
            font-size: 14px;
            opacity: 0.9;
        }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            padding: 30px;
            background: #f9f9f9;
            border-bottom: 1px solid #eee;
        }}
        .stat-card {{
            text-align: center;
            padding: 20px;
            background: white;
            border-radius: 6px;
            border-left: 4px solid #667eea;
        }}
        .stat-card .value {{
            font-size: 28px;
            font-weight: bold;
            color: #333;
            margin: 10px 0;
        }}
        .stat-card .label {{
            font-size: 12px;
            color: #999;
            text-transform: uppercase;
        }}
        .section {{
            padding: 30px;
            border-bottom: 1px solid #eee;
        }}
        .section:last-child {{
            border-bottom: none;
        }}
        .section h2 {{
            font-size: 20px;
            margin-bottom: 20px;
            color: #333;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
        }}
        table thead {{
            background: #f9f9f9;
        }}
        table th {{
            padding: 12px;
            text-align: left;
            font-weight: 600;
            color: #666;
            border-bottom: 2px solid #ddd;
        }}
        table td {{
            padding: 12px;
            border-bottom: 1px solid #eee;
        }}
        table tbody tr:hover {{
            background: #f9f9f9;
        }}
        .badge {{
            display: inline-block;
            padding: 4px 8px;
            border-radius: 3px;
            font-size: 12px;
            font-weight: 600;
        }}
        .badge-warning {{
            background: #fff3cd;
            color: #856404;
        }}
        .badge-danger {{
            background: #f8d7da;
            color: #721c24;
        }}
        .badge-success {{
            background: #d4edda;
            color: #155724;
        }}
        .progress-bar {{
            height: 4px;
            background: #eee;
            border-radius: 2px;
            overflow: hidden;
            margin-top: 4px;
        }}
        .progress-bar-fill {{
            height: 100%;
            background: linear-gradient(90deg, #667eea, #764ba2);
        }}
        .empty-state {{
            text-align: center;
            padding: 40px;
            color: #999;
        }}
        .empty-state-icon {{
            font-size: 48px;
            margin-bottom: 16px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🐢 数据库慢查询报告</h1>
            <p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </header>

        <div class="stats">
            <div class="stat-card">
                <div class="label">总慢查询数</div>
                <div class="value">{report['total']}</div>
            </div>
            <div class="stat-card">
                <div class="label">慢查询阈值</div>
                <div class="value">{report['threshold']}</div>
            </div>
            <div class="stat-card">
                <div class="label">总操作数</div>
                <div class="value">{sum(m.count for m in metrics.operations.values())}</div>
            </div>
            <div class="stat-card">
                <div class="label">慢查询比例</div>
                <div class="value">
                    {f"{(report['total'] / sum(m.count for m in metrics.operations.values()) * 100):.1f}%" if sum(m.count for m in metrics.operations.values()) > 0 else "0%"}
                </div>
            </div>
        </div>

        <div class="section">
            <h2>📊 按操作排名 (Top 10)</h2>
            {_render_operations_table(report) if report['top_operations'] else '<div class="empty-state"><div class="empty-state-icon">📭</div><p>暂无数据</p></div>'}
        </div>

        <div class="section">
            <h2>⏱️ 最近的慢查询 (Top 20)</h2>
            {_render_recent_queries_table(report) if report['recent_queries'] else '<div class="empty-state"><div class="empty-state-icon">📭</div><p>暂无数据</p></div>'}
        </div>

        <div class="section">
            <h2>💡 优化建议</h2>
            {_render_suggestions(report, metrics)}
        </div>
    </div>
</body>
</html>
"""

        if output_file:
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(html)
            logger.info(f"慢查询报告已生成: {output_file}")

        return html

    @staticmethod
    def generate_text_report() -> str:
        """生成文本格式的慢查询报告

        Returns:
            文本字符串
        """
        monitor = get_monitor()
        report = monitor.get_slow_query_report()
        metrics = monitor.get_metrics()

        lines = []
        lines.append("=" * 80)
        lines.append("🐢 数据库慢查询报告".center(80))
        lines.append("=" * 80)
        lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        # 总体统计
        total_ops = sum(m.count for m in metrics.operations.values())
        lines.append("📊 总体统计")
        lines.append("-" * 80)
        lines.append(f"  总慢查询数:     {report['total']}")
        lines.append(f"  慢查询阈值:     {report['threshold']}")
        lines.append(f"  总操作数:       {total_ops}")
        if total_ops > 0:
            lines.append(f"  慢查询比例:     {report['total'] / total_ops * 100:.1f}%")
        lines.append("")

        # 按操作排名
        if report["top_operations"]:
            lines.append("📈 按操作排名 (Top 10)")
            lines.append("-" * 80)
            lines.append(f"{'#':<3} {'操作名':<30} {'次数':<8} {'平均时间':<12} {'最大时间':<12}")
            lines.append("-" * 80)
            for idx, op in enumerate(report["top_operations"], 1):
                lines.append(
                    f"{idx:<3} {op['operation']:<30} {op['count']:<8} "
                    f"{op['avg_time']:<12} {op['max_time']:<12}"
                )
            lines.append("")

        # 最近的慢查询
        if report["recent_queries"]:
            lines.append("⏱️ 最近的慢查询 (最近 20 条)")
            lines.append("-" * 80)
            lines.append(f"{'时间':<20} {'操作':<30} {'执行时间':<15}")
            lines.append("-" * 80)
            for record in report["recent_queries"]:
                lines.append(
                    f"{record['timestamp']:<20} {record['operation']:<30} {record['time']:<15}"
                )
            lines.append("")

        # 优化建议
        lines.append("💡 优化建议")
        lines.append("-" * 80)
        suggestions = _get_suggestions(report, metrics)
        for suggestion in suggestions:
            lines.append(f"  • {suggestion}")

        lines.append("=" * 80)

        return "\n".join(lines)

    @staticmethod
    def get_slow_queries_by_operation(operation_name: str) -> list[Any]:
        """获取特定操作的所有慢查询

        Args:
            operation_name: 操作名称

        Returns:
            慢查询记录列表
        """
        monitor = get_monitor()
        slow_queries = monitor.get_slow_queries()

        return [q for q in slow_queries if q.operation_name == operation_name]

    @staticmethod
    def get_slowest_queries(limit: int = 20) -> list[Any]:
        """获取最慢的查询

        Args:
            limit: 返回数量

        Returns:
            按执行时间排序的慢查询记录列表
        """
        monitor = get_monitor()
        slow_queries = monitor.get_slow_queries()

        return sorted(slow_queries, key=lambda q: q.execution_time, reverse=True)[:limit]


def _render_operations_table(report: dict) -> str:
    """渲染操作排名表格"""
    if not report["top_operations"]:
        return '<div class="empty-state"><p>暂无数据</p></div>'

    rows = []
    for idx, op in enumerate(report["top_operations"], 1):
        rows.append(f"""
        <tr>
            <td>#{idx}</td>
            <td><strong>{op['operation']}</strong></td>
            <td><span class="badge badge-warning">{op['count']}</span></td>
            <td>{op['avg_time']}</td>
            <td>{op['max_time']}</td>
        </tr>
        """)

    return f"""
    <table>
        <thead>
            <tr>
                <th style="width: 5%">#</th>
                <th style="width: 40%">操作名</th>
                <th style="width: 15%">慢查询次数</th>
                <th style="width: 20%">平均执行时间</th>
                <th style="width: 20%">最大执行时间</th>
            </tr>
        </thead>
        <tbody>
            {''.join(rows)}
        </tbody>
    </table>
    """


def _render_recent_queries_table(report: dict) -> str:
    """渲染最近查询表格"""
    if not report["recent_queries"]:
        return '<div class="empty-state"><p>暂无数据</p></div>'

    rows = []
    for record in report["recent_queries"]:
        rows.append(f"""
        <tr>
            <td>{record['timestamp']}</td>
            <td>{record['operation']}</td>
            <td><span class="badge badge-danger">{record['time']}</span></td>
        </tr>
        """)

    return f"""
    <table>
        <thead>
            <tr>
                <th style="width: 25%">时间</th>
                <th style="width: 50%">操作名</th>
                <th style="width: 25%">执行时间</th>
            </tr>
        </thead>
        <tbody>
            {''.join(rows)}
        </tbody>
    </table>
    """


def _get_suggestions(report: dict, metrics: Any) -> list[str]:
    """生成优化建议"""
    suggestions = []

    if report["total"] == 0:
        suggestions.append("✅ 没有检测到慢查询，性能良好！")
        return suggestions

    # 计算比例
    total_ops = sum(m.count for m in metrics.operations.values())
    slow_ratio = report["total"] / total_ops if total_ops > 0 else 0

    if slow_ratio > 0.1:
        suggestions.append(f"⚠️ 慢查询比例较高 ({slow_ratio * 100:.1f}%)，建议检查数据库索引和查询优化")

    if report["top_operations"]:
        top_op = report["top_operations"][0]
        suggestions.append(f"🔍 '{top_op['operation']}' 是最常见的慢查询，建议优先优化这个操作")

        if top_op["count"] > total_ops * 0.3:
            suggestions.append("🚀 优化最频繁的慢查询可能会显著提升性能")

    # 分析操作执行时间
    for op_name, op_metrics in metrics.operations.items():
        if op_metrics.max_time > 5:
            suggestions.append(
                f"⏱️ '{op_name}' 的最大执行时间超过 5 秒 ({op_metrics.max_time:.1f}s)，"
                "这可能表明有异常的查询操作"
            )

    if len(report["top_operations"]) > 1:
        top_2_count = sum(op["count"] for op in report["top_operations"][:2])
        if top_2_count / report["total"] > 0.7:
            suggestions.append("🎯 80% 的慢查询集中在少数操作上，建议针对这些操作进行优化")

    if not suggestions:
        suggestions.append("💡 考虑调整 slow_query_threshold 以获得更细致的分析")

    return suggestions


def _render_suggestions(report: dict, metrics: Any) -> str:
    """渲染优化建议"""
    suggestions = _get_suggestions(report, metrics)

    return f"""
    <ul style="list-style: none; padding: 0;">
        {''.join(f'<li style="padding: 8px 0; line-height: 1.6;">{s}</li>' for s in suggestions)}
    </ul>
    """
