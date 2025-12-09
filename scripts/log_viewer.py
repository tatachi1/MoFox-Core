#!/usr/bin/env python3
"""
MoFox-Core 日志查看器
一个基于 HTTP 的日志查看服务，支持实时查看、搜索和筛选日志。

用法:
    python scripts/log_viewer.py
    python -m scripts.log_viewer [--port PORT] [--host HOST]
"""

import argparse
import gzip
import json
import re
import sys
import tarfile
import threading
import webbrowser
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

# 添加项目根目录到路径（支持直接运行和模块运行）
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 切换工作目录到项目根目录
import os

os.chdir(PROJECT_ROOT)

# 日志目录
LOG_DIR = PROJECT_ROOT / "logs"

# 从 logger.py 导入颜色和别名配置
DEFAULT_MODULE_COLORS = {}
DEFAULT_MODULE_ALIASES = {}
try:
    from src.common.logger import (
        DEFAULT_MODULE_ALIASES,
        DEFAULT_MODULE_COLORS,
    )
except ImportError:
    pass  # 使用空字典


@dataclass
class LogEntry:
    """日志条目"""

    timestamp: str
    level: str
    logger_name: str
    event: str
    color: str | None = None
    alias: str | None = None
    extra: dict | None = None
    line_number: int = 0
    file_name: str = ""


class LogReader:
    """日志文件读取器"""

    def __init__(self, log_dir: Path):
        self.log_dir = log_dir
        self._cache: dict[str, list[LogEntry]] = {}
        self._cache_mtime: dict[str, float] = {}
        self._filter_cache: dict[str, tuple[list[LogEntry], str]] = {}  # 筛选结果缓存
        self._lock = threading.Lock()

    def get_log_files(self) -> list[dict[str, Any]]:
        """获取所有日志文件列表"""
        files = []
        if not self.log_dir.exists():
            return files

        for f in sorted(self.log_dir.glob("app_*.log.jsonl*"), reverse=True):
            try:
                stat = f.stat()
                is_compressed = f.suffix == ".gz" or ".tar.gz" in f.name
                files.append(
                    {
                        "name": f.name,
                        "size": stat.st_size,
                        "size_human": self._human_size(stat.st_size),
                        "mtime": stat.st_mtime,
                        "mtime_human": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                        "compressed": is_compressed,
                    }
                )
            except OSError:
                continue
        return files

    def _human_size(self, size: int) -> str:
        """转换为人类可读的文件大小"""
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    def read_log_file(self, filename: str, use_cache: bool = True) -> list[LogEntry]:
        """读取日志文件内容"""
        filepath = self.log_dir / filename
        if not filepath.exists():
            return []

        # 检查缓存
        with self._lock:
            if use_cache and filename in self._cache:
                try:
                    current_mtime = filepath.stat().st_mtime
                    if self._cache_mtime.get(filename) == current_mtime:
                        return self._cache[filename]
                except OSError:
                    pass

        entries = []
        try:
            # 处理压缩文件
            if ".tar.gz" in filename:
                entries = self._read_tar_gz(filepath)
            elif filename.endswith(".gz"):
                entries = self._read_gzip(filepath)
            else:
                entries = self._read_plain(filepath)

            # 更新缓存
            with self._lock:
                self._cache[filename] = entries
                try:
                    self._cache_mtime[filename] = filepath.stat().st_mtime
                except OSError:
                    pass

        except Exception as e:
            print(f"读取日志文件 {filename} 时出错: {e}")

        return entries

    def _read_plain(self, filepath: Path) -> list[LogEntry]:
        """读取普通日志文件"""
        entries = []
        with open(filepath, encoding="utf-8", errors="replace") as f:
            for line_num, line in enumerate(f, 1):
                entry = self._parse_line(line, line_num, filepath.name)
                if entry:
                    entries.append(entry)
        return entries

    def _read_gzip(self, filepath: Path) -> list[LogEntry]:
        """读取 gzip 压缩的日志文件"""
        entries = []
        with gzip.open(filepath, "rt", encoding="utf-8", errors="replace") as f:
            for line_num, line in enumerate(f, 1):
                entry = self._parse_line(line, line_num, filepath.name)
                if entry:
                    entries.append(entry)
        return entries

    def _read_tar_gz(self, filepath: Path) -> list[LogEntry]:
        """读取 tar.gz 压缩的日志文件"""
        entries = []
        try:
            with tarfile.open(filepath, "r:gz") as tar:
                for member in tar.getmembers():
                    if member.isfile():
                        f = tar.extractfile(member)
                        if f:
                            content = f.read().decode("utf-8", errors="replace")
                            for line_num, line in enumerate(content.splitlines(), 1):
                                entry = self._parse_line(line, line_num, filepath.name)
                                if entry:
                                    entries.append(entry)
        except Exception as e:
            print(f"读取 tar.gz 文件 {filepath} 时出错: {e}")
        return entries

    def _parse_line(self, line: str, line_num: int, filename: str) -> LogEntry | None:
        """解析单行日志"""
        line = line.strip()
        if not line:
            return None

        try:
            data = json.loads(line)
            logger_name = data.get("logger_name", "unknown")

            # 获取颜色和别名（优先使用日志中的，否则使用默认配置）
            color = data.get("color") or DEFAULT_MODULE_COLORS.get(logger_name)
            alias = data.get("alias") or DEFAULT_MODULE_ALIASES.get(logger_name)

            # 提取额外字段
            extra = {k: v for k, v in data.items() if k not in ("timestamp", "level", "logger_name", "event", "color", "alias")}

            return LogEntry(
                timestamp=data.get("timestamp", ""),
                level=data.get("level", "info"),
                logger_name=logger_name,
                event=data.get("event", ""),
                color=color,
                alias=alias,
                extra=extra if extra else None,
                line_number=line_num,
                file_name=filename,
            )
        except json.JSONDecodeError:
            # 非 JSON 格式的行，尝试作为纯文本处理
            return LogEntry(
                timestamp="",
                level="info",
                logger_name="raw",
                event=line,
                line_number=line_num,
                file_name=filename,
            )

    def search_logs(
        self,
        filename: str,
        query: str = "",
        level: str = "",
        logger: str = "",
        start_time: str = "",
        end_time: str = "",
        limit: int = 1000,
        offset: int = 0,
        regex: bool = False,
    ) -> tuple[list[LogEntry], int]:
        """搜索和筛选日志"""
        entries = self.read_log_file(filename)

        # 如果没有筛选条件，直接返回分页结果
        if not query and not level and not logger and not start_time and not end_time:
            total = len(entries)
            return entries[offset : offset + limit], total

        # 生成筛选条件的缓存 key
        cache_key = f"{filename}:{query}:{level}:{logger}:{start_time}:{end_time}:{regex}"

        # 检查筛选缓存
        with self._lock:
            cached = self._filter_cache.get(filename)
            if cached and cached[1] == cache_key:
                filtered = cached[0]
                return filtered[offset : offset + limit], len(filtered)

        # 编译正则表达式（如果需要）
        query_pattern = None
        query_lower = ""
        if query:
            if regex:
                try:
                    query_pattern = re.compile(query, re.IGNORECASE)
                except re.error:
                    query_pattern = None
            else:
                query_lower = query.lower()

        filtered = []
        for entry in entries:
            # 日志级别筛选
            if level and entry.level.lower() != level.lower():
                continue

            # Logger 名称筛选
            if logger and entry.logger_name.lower() != logger.lower():
                continue

            # 时间范围筛选
            if start_time and entry.timestamp < start_time:
                continue
            if end_time and entry.timestamp > end_time:
                continue

            # 关键词搜索
            if query:
                if query_pattern:
                    if not (query_pattern.search(entry.event) or query_pattern.search(entry.logger_name) or (entry.alias and query_pattern.search(entry.alias))):
                        continue
                else:
                    search_text = f"{entry.event} {entry.logger_name} {entry.alias or ''}".lower()
                    if query_lower not in search_text:
                        continue

            filtered.append(entry)

        # 更新筛选缓存
        with self._lock:
            self._filter_cache[filename] = (filtered, cache_key)

        total = len(filtered)
        return filtered[offset : offset + limit], total

    def get_loggers(self, filename: str) -> list[dict[str, str]]:
        """获取日志文件中的所有 logger"""
        entries = self.read_log_file(filename)
        loggers = {}
        for entry in entries:
            if entry.logger_name not in loggers:
                loggers[entry.logger_name] = {
                    "name": entry.logger_name,
                    "alias": entry.alias or DEFAULT_MODULE_ALIASES.get(entry.logger_name, ""),
                    "color": entry.color or DEFAULT_MODULE_COLORS.get(entry.logger_name, ""),
                }
        return sorted(loggers.values(), key=lambda x: x["name"])

    def get_stats(self, filename: str) -> dict[str, Any]:
        """获取日志统计信息"""
        entries = self.read_log_file(filename)

        level_counts = defaultdict(int)
        logger_counts = defaultdict(int)

        for entry in entries:
            level_counts[entry.level] += 1
            logger_counts[entry.logger_name] += 1

        return {
            "total": len(entries),
            "by_level": dict(level_counts),
            "by_logger": dict(sorted(logger_counts.items(), key=lambda x: -x[1])[:20]),
        }


# HTML 模板
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>日志查看器</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }

        :root {
            --bg: #0d1117;
            --bg-card: #161b22;
            --bg-input: #21262d;
            --border: #30363d;
            --text: #e6edf3;
            --text-dim: #8b949e;
            --accent: #58a6ff;
            --accent-dim: #388bfd;
            --green: #3fb950;
            --yellow: #d29922;
            --red: #f85149;
            --orange: #db6d28;
            --purple: #a371f7;
            --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', sans-serif;
            --font-mono: 'JetBrains Mono', 'Cascadia Code', 'Fira Code', Consolas, monospace;
        }

        body {
            font-family: var(--font-sans);
            background: var(--bg);
            color: var(--text);
            line-height: 1.5;
            font-size: 13px;
            -webkit-font-smoothing: antialiased;
        }

        .app { display: flex; height: 100vh; }

        /* 侧边栏 */
        .sidebar {
            width: 280px;
            background: var(--bg-card);
            border-right: 1px solid var(--border);
            display: flex;
            flex-direction: column;
            flex-shrink: 0;
        }

        .sidebar-header {
            padding: 16px;
            border-bottom: 1px solid var(--border);
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .sidebar-header svg { color: var(--accent); }

        .file-list {
            flex: 1;
            overflow-y: auto;
            padding: 8px;
        }

        .file-item {
            padding: 10px 12px;
            border-radius: 6px;
            cursor: pointer;
            margin-bottom: 4px;
            transition: background 0.15s;
        }

        .file-item:hover { background: var(--bg-input); }
        .file-item.active { background: var(--accent-dim); color: #fff; }

        .file-item .name {
            font-size: 13px;
            font-weight: 500;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .file-item .meta {
            font-size: 11px;
            color: var(--text-dim);
            margin-top: 2px;
        }

        .file-item.active .meta { color: rgba(255,255,255,0.7); }

        /* 主内容区 */
        .main { flex: 1; display: flex; flex-direction: column; min-width: 0; }

        /* 工具栏 */
        .toolbar {
            padding: 12px 16px;
            background: var(--bg-card);
            border-bottom: 1px solid var(--border);
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            align-items: center;
        }

        .toolbar-group {
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .toolbar-group label {
            font-size: 12px;
            color: var(--text-dim);
        }

        input, select {
            background: var(--bg-input);
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 6px 10px;
            color: var(--text);
            font-size: 13px;
            font-family: var(--font-sans);
            outline: none;
        }

        input:focus, select:focus { border-color: var(--accent); }

        input[type="search"] { width: 240px; }
        input[type="number"] { width: 70px; font-family: var(--font-mono); }

        .btn {
            background: var(--bg-input);
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 6px 12px;
            color: var(--text);
            font-size: 13px;
            font-family: var(--font-sans);
            cursor: pointer;
            transition: all 0.15s;
            display: inline-flex;
            align-items: center;
            gap: 4px;
        }

        .btn:hover { background: var(--border); }
        .btn-primary { background: var(--accent); border-color: var(--accent); color: #fff; }
        .btn-primary:hover { background: var(--accent-dim); }

        .checkbox {
            display: flex;
            align-items: center;
            gap: 4px;
            font-size: 12px;
            color: var(--text-dim);
            cursor: pointer;
        }

        .checkbox input { margin: 0; }

        .spacer { flex: 1; }

        /* 统计条 */
        .stats-bar {
            padding: 8px 16px;
            background: var(--bg-card);
            border-bottom: 1px solid var(--border);
            display: flex;
            gap: 16px;
            font-size: 12px;
        }

        .stat { display: flex; align-items: center; gap: 4px; }
        .stat-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
        }

        .stat-dot.debug { background: var(--orange); }
        .stat-dot.info { background: var(--accent); }
        .stat-dot.warning { background: var(--yellow); }
        .stat-dot.error { background: var(--red); }
        .stat-dot.critical { background: var(--purple); }

        /* 日志列表 */
        .log-container { flex: 1; overflow: hidden; display: flex; flex-direction: column; }

        .log-list {
            flex: 1;
            overflow-y: auto;
            font-family: var(--font-mono);
            font-size: 12px;
            letter-spacing: -0.3px;
        }

        .log-entry {
            display: flex;
            padding: 6px 16px;
            border-bottom: 1px solid var(--border);
            gap: 12px;
            align-items: flex-start;
        }

        .log-entry:hover { background: rgba(88, 166, 255, 0.05); }

        .log-time {
            color: var(--text-dim);
            white-space: nowrap;
            min-width: 90px;
            flex-shrink: 0;
            font-size: 11px;
        }

        .log-level {
            min-width: 50px;
            flex-shrink: 0;
            font-weight: 600;
            text-transform: uppercase;
            font-size: 10px;
            padding: 2px 0;
        }

        .log-level.debug { color: var(--orange); }
        .log-level.info { color: var(--accent); }
        .log-level.warning { color: var(--yellow); }
        .log-level.error { color: var(--red); }
        .log-level.critical { color: var(--purple); }

        .log-logger {
            min-width: 100px;
            max-width: 140px;
            flex-shrink: 0;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            font-weight: 500;
        }

        .log-msg {
            flex: 1;
            white-space: pre-wrap;
            word-break: break-word;
            min-width: 0;
        }

        .log-msg .hl {
            background: rgba(210, 153, 34, 0.3);
            border-radius: 2px;
            padding: 0 2px;
        }

        /* 分页栏 */
        .pagination {
            padding: 10px 16px;
            background: var(--bg-card);
            border-top: 1px solid var(--border);
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            font-size: 13px;
        }

        .pagination .info { color: var(--text-dim); margin: 0 12px; }

        .pagination button:disabled { opacity: 0.4; cursor: not-allowed; }

        /* 空状态 */
        .empty {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100%;
            color: var(--text-dim);
            gap: 8px;
        }

        .empty svg { opacity: 0.3; }

        /* 加载动画 */
        .loading { text-align: center; padding: 40px; color: var(--text-dim); }

        /* 自动刷新指示 */
        .refresh-badge {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            font-size: 11px;
            color: var(--green);
            margin-left: 8px;
        }

        .refresh-badge::before {
            content: '';
            width: 6px;
            height: 6px;
            background: var(--green);
            border-radius: 50%;
            animation: blink 1.5s infinite;
        }

        @keyframes blink {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.3; }
        }

        /* 滚动条 */
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: var(--text-dim); }
    </style>
</head>
<body>
    <div class="app">
        <aside class="sidebar">
            <div class="sidebar-header">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M16 13H8"/><path d="M16 17H8"/><path d="M10 9H8"/>
                </svg>
                日志文件
            </div>
            <div class="file-list" id="fileList">
                <div class="loading">加载中...</div>
            </div>
        </aside>

        <main class="main">
            <div class="toolbar">
                <div class="toolbar-group">
                    <input type="search" id="searchInput" placeholder="搜索内容..." onkeydown="if(event.key==='Enter')doSearch()">
                    <label class="checkbox"><input type="checkbox" id="regexCheck"> 正则</label>
                </div>

                <div class="toolbar-group">
                    <label>级别</label>
                    <select id="levelSelect" onchange="resetAndSearch()">
                        <option value="">全部</option>
                        <option value="debug">DEBUG</option>
                        <option value="info">INFO</option>
                        <option value="warning">WARNING</option>
                        <option value="error">ERROR</option>
                        <option value="critical">CRITICAL</option>
                    </select>
                </div>

                <div class="toolbar-group">
                    <label>模块</label>
                    <select id="loggerSelect" onchange="resetAndSearch()">
                        <option value="">全部</option>
                    </select>
                </div>

                <button class="btn btn-primary" onclick="doSearch()">搜索</button>
                <button class="btn" onclick="clearSearch()">清除</button>

                <div class="spacer"></div>

                <div class="toolbar-group">
                    <label class="checkbox">
                        <input type="checkbox" id="paginationCheck" checked onchange="togglePagination()">
                        分页
                    </label>
                    <label>每页</label>
                    <input type="number" id="pageSizeInput" value="200" min="50" max="5000" step="50" onchange="updatePageSize()">
                </div>

                <div class="toolbar-group">
                    <label class="checkbox">
                        <input type="checkbox" id="autoRefreshCheck" onchange="toggleAutoRefresh()">
                        自动刷新
                    </label>
                    <span class="refresh-badge" id="refreshBadge" style="display:none">实时</span>
                </div>
            </div>

            <div class="stats-bar" id="statsBar"></div>

            <div class="log-container">
                <div class="log-list" id="logList">
                    <div class="empty">
                        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1">
                            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                            <path d="M14 2v6h6"/>
                        </svg>
                        <span>选择左侧文件查看日志</span>
                    </div>
                </div>
                <div class="pagination" id="pagination" style="display:none"></div>
            </div>
        </main>
    </div>

    <script>
        const S = {
            file: null,
            logs: [],
            total: 0,
            page: 1,
            pageSize: 200,
            usePagination: true,
            timer: null,
            query: '',
            level: '',
            logger: '',
            regex: false
        };

        // 加载文件列表
        async function loadFiles() {
            const res = await fetch('/api/files');
            const files = await res.json();
            const el = document.getElementById('fileList');
            if (!files.length) {
                el.innerHTML = '<div class="empty">无日志文件</div>';
                return;
            }
            el.innerHTML = files.map(f => `
                <div class="file-item" data-name="${f.name}" onclick="openFile('${f.name}')">
                    <div class="name">${f.name}</div>
                    <div class="meta">${f.size_human} · ${f.mtime_human.split(' ')[0]}</div>
                </div>
            `).join('');
        }

        async function openFile(name) {
            S.file = name;
            S.page = 1;
            document.querySelectorAll('.file-item').forEach(el => {
                el.classList.toggle('active', el.dataset.name === name);
            });
            await loadLoggers();
            await loadStats();
            await doSearch();
        }

        async function loadLoggers() {
            const res = await fetch(`/api/loggers?file=${encodeURIComponent(S.file)}`);
            const list = await res.json();
            const sel = document.getElementById('loggerSelect');
            sel.innerHTML = '<option value="">全部</option>' +
                list.map(l => `<option value="${l.name}">${l.alias || l.name}</option>`).join('');
        }

        async function loadStats() {
            const res = await fetch(`/api/stats?file=${encodeURIComponent(S.file)}`);
            const stats = await res.json();
            const bar = document.getElementById('statsBar');
            const levels = ['debug','info','warning','error','critical'];
            bar.innerHTML = `<span style="color:var(--text-dim)">共 ${stats.total.toLocaleString()} 条</span>` +
                levels.filter(l => stats.by_level[l]).map(l =>
                    `<div class="stat"><span class="stat-dot ${l}"></span>${l.toUpperCase()} ${stats.by_level[l]}</div>`
                ).join('');
        }

        async function doSearch() {
            if (!S.file) return;
            S.query = document.getElementById('searchInput').value;
            S.level = document.getElementById('levelSelect').value;
            S.logger = document.getElementById('loggerSelect').value;
            S.regex = document.getElementById('regexCheck').checked;

            const limit = S.usePagination ? S.pageSize : 100000;
            const offset = S.usePagination ? (S.page - 1) * S.pageSize : 0;

            const params = new URLSearchParams({
                file: S.file,
                query: S.query,
                level: S.level,
                logger: S.logger,
                regex: S.regex,
                limit: limit,
                offset: offset
            });

            document.getElementById('logList').innerHTML = '<div class="loading">加载中...</div>';

            try {
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), 30000);

                const res = await fetch(`/api/logs?${params}`, { signal: controller.signal });
                clearTimeout(timeoutId);

                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();
                S.logs = data.logs;
                S.total = data.total;
                renderLogs();
                renderPagination();
            } catch (err) {
                console.error('加载失败:', err);
                document.getElementById('logList').innerHTML =
                    `<div class="empty">加载失败: ${err.message}<br><button class="btn" onclick="doSearch()">重试</button></div>`;
            }
        }

        function renderLogs() {
            const el = document.getElementById('logList');
            if (!S.logs.length) {
                el.innerHTML = '<div class="empty">无匹配结果</div>';
                return;
            }

            el.innerHTML = S.logs.map(log => {
                let msg = ansiToHtml(log.event);
                if (S.query && !S.regex) {
                    const re = new RegExp(`(${escRe(S.query)})`, 'gi');
                    msg = msg.replace(re, '<span class="hl">$1</span>');
                }
                const name = log.alias || log.logger_name;
                const color = log.color || 'inherit';
                return `<div class="log-entry">
                    <span class="log-time">${log.timestamp}</span>
                    <span class="log-level ${log.level}">${log.level}</span>
                    <span class="log-logger" style="color:${color}" title="${log.logger_name}">${name}</span>
                    <span class="log-msg">${msg}</span>
                </div>`;
            }).join('');
        }

        function renderPagination() {
            const el = document.getElementById('pagination');
            if (!S.usePagination || S.total <= S.pageSize) {
                el.style.display = 'none';
                return;
            }
            el.style.display = 'flex';
            const pages = Math.ceil(S.total / S.pageSize);
            el.innerHTML = `
                <button class="btn" onclick="goPage(1)" ${S.page<=1?'disabled':''}>首页</button>
                <button class="btn" onclick="goPage(${S.page-1})" ${S.page<=1?'disabled':''}>上页</button>
                <span class="info">第 ${S.page} / ${pages} 页 (${S.total.toLocaleString()} 条)</span>
                <button class="btn" onclick="goPage(${S.page+1})" ${S.page>=pages?'disabled':''}>下页</button>
                <button class="btn" onclick="goPage(${pages})" ${S.page>=pages?'disabled':''}>末页</button>
            `;
        }

        function goPage(p) { S.page = p; doSearch(); }

        function resetAndSearch() {
            S.page = 1;
            doSearch();
        }

        function clearSearch() {
            document.getElementById('searchInput').value = '';
            document.getElementById('levelSelect').value = '';
            document.getElementById('loggerSelect').value = '';
            document.getElementById('regexCheck').checked = false;
            S.page = 1;
            if (S.file) doSearch();
        }

        function togglePagination() {
            S.usePagination = document.getElementById('paginationCheck').checked;
            S.page = 1;
            if (S.file) doSearch();
        }

        function updatePageSize() {
            const v = parseInt(document.getElementById('pageSizeInput').value) || 200;
            S.pageSize = Math.max(50, Math.min(5000, v));
            S.page = 1;
            if (S.file) doSearch();
        }

        function toggleAutoRefresh() {
            const on = document.getElementById('autoRefreshCheck').checked;
            document.getElementById('refreshBadge').style.display = on ? 'inline-flex' : 'none';
            if (on) {
                S.timer = setInterval(() => { if (S.file) doSearch(); }, 3000);
            } else {
                clearInterval(S.timer);
                S.timer = null;
            }
        }

        function esc(s) {
            if (!s) return '';
            return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
        }

        // ANSI 颜色码转 HTML
        function ansiToHtml(s) {
            if (!s) return '';
            // 先转义 HTML
            s = esc(s);
            // ANSI 颜色映射
            const colors = {
                '30': '#4d4d4d', '31': '#f85149', '32': '#3fb950', '33': '#d29922',
                '34': '#58a6ff', '35': '#a371f7', '36': '#39c5cf', '37': '#c9d1d9',
                '90': '#6e7681', '91': '#ff7b72', '92': '#56d364', '93': '#e3b341',
                '94': '#79c0ff', '95': '#d2a8ff', '96': '#56d4dd', '97': '#ffffff'
            };
            const bgColors = {
                '40': '#4d4d4d', '41': '#f85149', '42': '#3fb950', '43': '#d29922',
                '44': '#58a6ff', '45': '#a371f7', '46': '#39c5cf', '47': '#c9d1d9'
            };
            let result = '';
            let currentStyle = [];
            // 匹配 ANSI 转义序列
            const regex = /\\x1b\\[([0-9;]*)m|\\033\\[([0-9;]*)m|\\u001b\\[([0-9;]*)m|\\[([0-9;]*)m/g;
            let lastIndex = 0;
            let match;
            while ((match = regex.exec(s)) !== null) {
                result += s.slice(lastIndex, match.index);
                const codes = (match[1] || match[2] || match[3] || match[4] || '0').split(';');
                for (const code of codes) {
                    if (code === '0' || code === '') {
                        if (currentStyle.length > 0) {
                            result += '</span>';
                            currentStyle = [];
                        }
                    } else if (colors[code]) {
                        if (currentStyle.length > 0) result += '</span>';
                        result += `<span style="color:${colors[code]}">`;
                        currentStyle = [code];
                    } else if (bgColors[code]) {
                        if (currentStyle.length > 0) result += '</span>';
                        result += `<span style="background:${bgColors[code]}">`;
                        currentStyle = [code];
                    } else if (code === '1') {
                        if (currentStyle.length > 0) result += '</span>';
                        result += '<span style="font-weight:bold">';
                        currentStyle = [code];
                    }
                }
                lastIndex = regex.lastIndex;
            }
            result += s.slice(lastIndex);
            if (currentStyle.length > 0) result += '</span>';
            return result;
        }

        function escRe(s) {
            return s.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&');
        }

        loadFiles();
    </script>
</body>
</html>
"""


class LogViewerHandler(SimpleHTTPRequestHandler):
    """HTTP 请求处理器"""

    log_reader: LogReader = None  # type: ignore

    def log_message(self, format, *args):
        """自定义日志格式"""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {args[0]}")

    def do_GET(self):
        """处理 GET 请求"""
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        # API 路由
        if path == "/":
            self.send_html(HTML_TEMPLATE)
        elif path == "/api/files":
            self.send_json(self.log_reader.get_log_files())
        elif path == "/api/logs":
            self.handle_logs_api(query)
        elif path == "/api/loggers":
            filename = query.get("file", [""])[0]
            self.send_json(self.log_reader.get_loggers(filename))
        elif path == "/api/stats":
            filename = query.get("file", [""])[0]
            self.send_json(self.log_reader.get_stats(filename))
        else:
            self.send_error(404, "Not Found")

    def handle_logs_api(self, query: dict):
        """处理日志搜索 API"""
        filename = query.get("file", [""])[0]
        search_query = query.get("query", [""])[0]
        level = query.get("level", [""])[0]
        logger = query.get("logger", [""])[0]
        regex = query.get("regex", ["false"])[0].lower() == "true"
        limit = int(query.get("limit", ["100"])[0])
        offset = int(query.get("offset", ["0"])[0])

        logs, total = self.log_reader.search_logs(
            filename=filename,
            query=search_query,
            level=level,
            logger=logger,
            limit=limit,
            offset=offset,
            regex=regex,
        )

        # 转换为可序列化的格式
        logs_data = [
            {
                "timestamp": log.timestamp,
                "level": log.level,
                "logger_name": log.logger_name,
                "event": log.event,
                "color": log.color,
                "alias": log.alias,
                "extra": log.extra,
                "line_number": log.line_number,
            }
            for log in logs
        ]

        self.send_json({"logs": logs_data, "total": total})

    def send_html(self, content: str):
        """发送 HTML 响应"""
        encoded = content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def send_json(self, data: Any):
        """发送 JSON 响应"""
        content = json.dumps(data, ensure_ascii=False, default=str)
        encoded = content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def run_server(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True):
    """启动 HTTP 服务器"""
    # 初始化日志读取器
    LogViewerHandler.log_reader = LogReader(LOG_DIR)

    server = HTTPServer((host, port), LogViewerHandler)
    url = f"http://{host}:{port}"

    print(f"\n  📋 日志查看器已启动: {url}\n")

    # 自动打开浏览器
    if open_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  服务器已停止")
        server.shutdown()


def main():
    parser = argparse.ArgumentParser(description="日志查看器")
    parser.add_argument("--host", default="127.0.0.1", help="服务器地址 (默认: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="服务器端口 (默认: 8765)")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()

    run_server(args.host, args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
