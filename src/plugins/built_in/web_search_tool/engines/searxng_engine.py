"""
SearXNG search engine implementation

参考: https://docs.searxng.org/dev/search_api.html (公开JSON接口说明)
"""

from __future__ import annotations

import asyncio
import functools
from typing import Any, List

import httpx

from src.common.logger import get_logger
from src.plugin_system.apis import config_api

from .base import BaseSearchEngine

logger = get_logger("searxng_engine")


class SearXNGSearchEngine(BaseSearchEngine):
    """SearXNG 元搜索引擎实现

    通过在配置中提供一个或多个公开 / 自建 SearXNG 实例来使用。

    配置项(位于主配置 bot_config.toml 的 [web_search] 部分):
        searxng_instances = ["https://searxng.example.com"]
        # 可选: 若实例启用 token 验证，可在 searxng_api_keys 中提供对应 token (顺序与实例列表一致)
        searxng_api_keys = ["token1", "token2"]
    """

    def __init__(self):
        self._load_config()
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0))

    def _load_config(self):
        instances = config_api.get_global_config("web_search.searxng_instances", None)
        if isinstance(instances, list):
            # 过滤空值
            self.instances: List[str] = [u.rstrip("/") for u in instances if isinstance(u, str) and u.strip()]
        else:
            self.instances = []

        api_keys = config_api.get_global_config("web_search.searxng_api_keys", None)
        if isinstance(api_keys, list):
            self.api_keys: List[str | None] = [k.strip() if isinstance(k, str) and k.strip() else None for k in api_keys]
        else:
            self.api_keys = []

        # 与实例列表对齐（若 keys 少则补 None）
        if self.api_keys and len(self.api_keys) < len(self.instances):
            self.api_keys.extend([None] * (len(self.instances) - len(self.api_keys)))

        logger.debug(
            f"SearXNG 引擎配置: instances={self.instances}, api_keys={'yes' if any(self.api_keys) else 'no'}"
        )

    def is_available(self) -> bool:
        return bool(self.instances)

    async def search(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        if not self.is_available():
            return []

        query = args["query"]
        num_results = args.get("num_results", 3)
        time_range = args.get("time_range", "any")

        # SearXNG 的时间范围参数: day / week / month / year
        searx_time = None
        if time_range == "week":
            searx_time = "week"
        elif time_range == "month":
            searx_time = "month"

        # 轮询实例：简单使用循环尝试，直到获得结果或全部失败
        results: list[dict[str, Any]] = []
        for idx, base_url in enumerate(self.instances):
            token = self.api_keys[idx] if idx < len(self.api_keys) else None
            try:
                instance_results = await self._search_one_instance(base_url, query, num_results, searx_time, token)
                if instance_results:
                    results.extend(instance_results)
                if len(results) >= num_results:
                    break
            except Exception as e:  # noqa: BLE001
                logger.warning(f"SearXNG 实例 {base_url} 调用失败: {e}")
                continue

        # 截断到需要的数量
        return results[:num_results]

    async def _search_one_instance(
        self, base_url: str, query: str, num_results: int, searx_time: str | None, api_key: str | None
    ) -> list[dict[str, Any]]:
        # 构造 URL & 参数
        url = f"{base_url}/search"
        params = {
            "q": query,
            "format": "json",
            "categories": "general",  # 可扩展: 允许从 args 传 categories
            "language": "zh-CN",
            "safesearch": 1,
        }
        if searx_time:
            params["time_range"] = searx_time

        headers = {}
        if api_key:
            # SearXNG 可通过 Authorization 或 X-Token (取决于实例配置)，尝试常见方案
            headers["Authorization"] = f"Token {api_key}"

        # 在线程池中运行同步请求（httpx.AsyncClient 直接 await 即可，这里直接调用）
        try:
            resp = await self._client.get(url, params=params, headers=headers)
            resp.raise_for_status()
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"请求失败: {e}") from e

        try:
            data = resp.json()
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"解析 JSON 失败: {e}") from e

        raw_results = data.get("results", []) if isinstance(data, dict) else []

        parsed: list[dict[str, Any]] = []
        for item in raw_results:
            title = item.get("title") or item.get("url", "无标题")
            url_item = item.get("url") or item.get("link", "")
            snippet = item.get("content") or item.get("snippet") or ""
            snippet = (snippet[:300] + "...") if len(snippet) > 300 else snippet
            parsed.append({"title": title, "url": url_item, "snippet": snippet, "provider": "SearXNG"})
            if len(parsed) >= num_results:  # 单实例限量
                break

        return parsed

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):  # noqa: D401
        await self._client.aclose()
