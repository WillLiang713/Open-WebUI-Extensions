"""
title: Auto-Web-Search
author: @WillLiang713
description: A tool for performing automated web searches.
repository_url: https://github.com/WillLiang713/OpenWebUI-Auto-Web-Search
version: 1.0.0
required_open_webui_version: >= 0.6.0
"""

import json
import os
from typing import Any, Literal, Optional, cast
from urllib.parse import urlparse

import httpx
from open_webui.main import Request, app
from open_webui.models.users import UserModel, Users
from open_webui.retrieval.utils import get_content_from_url
from open_webui.routers.retrieval import SearchForm, process_web_search
from pydantic import BaseModel, Field


async def emit_status(
    description: str,
    emitter: Any,
    status: Literal[
        "in_progress", "complete", "error", "web_search", "web_search_queries_generated"
    ] = "complete",
    extra_data: Optional[dict] = None,
    done: Optional[bool] = None,
    error: Optional[bool] = None,
):
    if not emitter:
        raise ValueError("Emitter is required to emit status updates")
    if extra_data is None:
        extra_data = {}

    if status in ("in_progress", "complete", "error"):
        extra_data["status"] = status
    else:
        extra_data["action"] = status
    """ if status == "web_search":
        status_key["action"] = "web_search"
    else:
        status_key["status"] = status """

    await emitter(
        {
            "type": "status",
            "data": {
                "description": description,
                "done": done if done is not None else status in ("complete", "error"),
                "error": error if error is not None else status == "error",
                **(extra_data or {}),
            },
        }
    )


async def get_request() -> Request:
    return Request(scope={"type": "http", "app": app})


def _clean_value(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _resolve_key(valve_value: Optional[str], env_name: str) -> Optional[str]:
    return _clean_value(valve_value) or _clean_value(os.getenv(env_name))


def _resolve_base_url(value: Optional[str], env_name: str, default: str) -> str:
    resolved = _clean_value(value) or _clean_value(os.getenv(env_name)) or default
    return resolved.rstrip("/")


def _normalize_provider(value: Optional[str], default: str) -> str:
    cleaned = _clean_value(value) or default
    return cleaned.lower()


def _select_search_provider(
    provider: str,
    tavily_api_key: Optional[str],
    exa_api_key: Optional[str],
    jina_api_key: Optional[str],
) -> str:
    if provider == "tavily":
        return "tavily" if tavily_api_key else "native"
    if provider == "exa":
        return "exa" if exa_api_key else "native"
    if provider in ("jina", "jina_search"):
        if jina_api_key:
            return "jina_search"
        return "jina_search"
    if provider == "native":
        return "native"
    return "native"


def _select_fetch_provider(
    provider: str,
    firecrawl_api_key: Optional[str],
    tavily_api_key: Optional[str],
    exa_api_key: Optional[str],
) -> str:
    if provider == "firecrawl":
        return "firecrawl" if firecrawl_api_key else "native"
    if provider == "tavily":
        return "tavily" if tavily_api_key else "native"
    if provider == "exa":
        return "exa" if exa_api_key else "native"
    if provider in ("jina", "jina_reader"):
        return "jina_reader"
    if provider == "native":
        return "native"
    return "native"


def _build_jina_search_url(base_url: str, query: str) -> tuple[str, dict[str, Any]]:
    cleaned = base_url.rstrip("/")
    if "{query}" in cleaned:
        return cleaned.format(query=query), {}
    if cleaned.endswith("/search"):
        return cleaned, {"q": query}
    return f"{cleaned}/search", {"q": query}


def _build_jina_reader_url(base_url: str, url: str) -> str:
    cleaned = base_url.rstrip("/")
    if "{url}" in cleaned:
        return cleaned.format(url=url)
    return f"{cleaned}/{url}"


def _domain_from_url(u: str) -> str:
    try:
        return urlparse(u).netloc or u
    except Exception:
        return u


def _normalize_search_item(item: dict[str, Any]) -> dict[str, str]:
    url = item.get("link") or item.get("url") or ""
    title = item.get("title") or item.get("name") or ""
    content = item.get("snippet") or item.get("content") or item.get("text") or ""

    url = str(url)
    if url and not (url.startswith("http://") or url.startswith("https://")):
        url = ""

    name = title or (_domain_from_url(url) if url else "") or "unknown"
    return {"name": str(name), "url": url, "content": str(content)}


async def _emit_search_citations(
    search_results: list[dict[str, str]], emitter: Any
) -> None:
    if not emitter:
        return
    for sr in search_results:
        await emitter(
            {
                "type": "citation",
                "data": {
                    "document": [sr["content"]],
                    "metadata": [
                        {
                            "source": sr["url"],
                            "url": sr["url"],
                            "link": sr["url"],
                            "title": sr["name"],
                            "name": sr["name"],
                        }
                    ],
                    "source": {
                        "name": sr["name"],
                        "url": sr["url"],
                    },
                },
            }
        )


class Tools:
    class Valves(BaseModel):
        search_provider: str = Field(
            default="tavily",
            description="Search provider: native, tavily, exa, or jina_search.",
        )
        fetch_provider: str = Field(
            default="firecrawl",
            description="Fetch provider: native, firecrawl, tavily, exa, or jina_reader.",
        )
        firecrawl_api_key: Optional[str] = Field(
            default=None, description="API key for Firecrawl."
        )
        firecrawl_base_url: str = Field(
            default="https://api.firecrawl.dev",
            description="Firecrawl base URL.",
        )
        tavily_api_key: Optional[str] = Field(
            default=None, description="API key for Tavily."
        )
        tavily_base_url: str = Field(
            default="https://api.tavily.com",
            description="Tavily base URL.",
        )
        tavily_search_depth: str = Field(
            default="basic",
            description="Tavily search depth (basic or advanced).",
        )
        tavily_max_results: int = Field(
            default=3, ge=1, le=10, description="Max results per query for Tavily."
        )
        exa_api_key: Optional[str] = Field(default=None, description="API key for Exa.")
        exa_base_url: str = Field(
            default="https://api.exa.ai",
            description="Exa base URL.",
        )
        exa_max_results: int = Field(
            default=3, ge=1, le=10, description="Max results per query for Exa."
        )
        jina_api_key: Optional[str] = Field(default=None, description="API key for Jina.")
        jina_search_base_url: str = Field(
            default="https://s.jina.ai",
            description="Jina Search base URL.",
        )
        jina_search_max_results: int = Field(
            default=3, ge=1, le=10, description="Max results per query for Jina Search."
        )
        jina_reader_base_url: str = Field(
            default="https://r.jina.ai",
            description="Jina Reader base URL.",
        )

    def __init__(self):
        self.valves = self.Valves()
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the web for factual information, current events, or specific topics. Only use this tool when a search query is explicitly needed or when the user asks for information that requires looking up current or factual data.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "search_queries": {
                                "type": "array",
                                "description": "An array of search queries.",
                                "items": {
                                    "type": "string",
                                    "title": "Search Query",
                                    "description": "A search query can be anything from a simple search term to a complex question.",
                                },
                                "minItems": 1,
                                "maxItems": 5,
                            }
                        },
                        "required": ["search_queries"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "fetch_url_content",
                    "description": "Browse and retrieve the full content from any URL including webpages, articles, YouTube videos, and other online resources. Use this whenever you need to access content from a specific link.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "The URL to browse and retrieve content from.",
                            }
                        },
                        "required": ["url"],
                    },
                },
            },
        ]

    async def web_search(
        self,
        search_queries: list[str],
        __event_emitter__: Any = None,
        __user__: Optional[dict] = None,
    ) -> str:
        """Search the web for a query."""
        if __user__ is None:
            raise ValueError("User information is required")

        cleaned: list[str] = []

        for q in search_queries:
            if isinstance(q, dict):
                q = q.get("query") or q.get("text") or ""
            q = str(q or "").strip()
            if q:
                cleaned.append(q)

        search_queries = cleaned[:5]

        user = Users.get_user_by_id(__user__["id"])
        if user is None:
            raise ValueError("User not found")

        tavily_api_key = _resolve_key(self.valves.tavily_api_key, "TAVILY_API_KEY")
        search_provider = _normalize_provider(self.valves.search_provider, "tavily")

        return await web_search_with_provider(
            search_queries,
            emitter=__event_emitter__,
            user=user,
            provider=search_provider,
            tavily_api_key=tavily_api_key,
            tavily_base_url=_resolve_base_url(
                self.valves.tavily_base_url,
                "TAVILY_BASE_URL",
                "https://api.tavily.com",
            ),
            tavily_search_depth=self.valves.tavily_search_depth,
            tavily_max_results=self.valves.tavily_max_results,
            exa_api_key=_resolve_key(self.valves.exa_api_key, "EXA_API_KEY"),
            exa_base_url=_resolve_base_url(
                self.valves.exa_base_url,
                "EXA_BASE_URL",
                "https://api.exa.ai",
            ),
            exa_max_results=self.valves.exa_max_results,
            jina_api_key=_resolve_key(self.valves.jina_api_key, "JINA_API_KEY"),
            jina_search_base_url=_resolve_base_url(
                self.valves.jina_search_base_url,
                "JINA_SEARCH_BASE_URL",
                "https://s.jina.ai",
            ),
            jina_search_max_results=self.valves.jina_search_max_results,
        )

    async def fetch_url_content(
        self,
        url: str,
        __event_emitter__: Any = None,
        __user__: Optional[dict] = None,
    ) -> str:
        """Fetch content from a URL."""
        if __user__ is None:
            raise ValueError("User information is required")

        user = Users.get_user_by_id(__user__["id"])
        if user is None:
            raise ValueError("User not found")

        firecrawl_api_key = _resolve_key(
            self.valves.firecrawl_api_key, "FIRECRAWL_API_KEY"
        )
        tavily_api_key = _resolve_key(self.valves.tavily_api_key, "TAVILY_API_KEY")
        fetch_provider = _normalize_provider(self.valves.fetch_provider, "firecrawl")
        exa_api_key = _resolve_key(self.valves.exa_api_key, "EXA_API_KEY")
        jina_api_key = _resolve_key(self.valves.jina_api_key, "JINA_API_KEY")

        return await fetch_url_with_fallback(
            url,
            emitter=__event_emitter__,
            user=user,
            provider=fetch_provider,
            firecrawl_api_key=firecrawl_api_key,
            firecrawl_base_url=_resolve_base_url(
                self.valves.firecrawl_base_url,
                "FIRECRAWL_BASE_URL",
                "https://api.firecrawl.dev",
            ),
            tavily_api_key=tavily_api_key,
            tavily_base_url=_resolve_base_url(
                self.valves.tavily_base_url,
                "TAVILY_BASE_URL",
                "https://api.tavily.com",
            ),
            exa_api_key=exa_api_key,
            exa_base_url=_resolve_base_url(
                self.valves.exa_base_url,
                "EXA_BASE_URL",
                "https://api.exa.ai",
            ),
            jina_api_key=jina_api_key,
            jina_reader_base_url=_resolve_base_url(
                self.valves.jina_reader_base_url,
                "JINA_READER_BASE_URL",
                "https://r.jina.ai",
            ),
        )


async def native_fetch_url(url: str, emitter: Any, user: UserModel) -> str:
    """Fetch content from a URL using the native web loader."""
    try:
        # Extract domain name from URL
        parsed_url = urlparse(url)
        domain = parsed_url.netloc or parsed_url.path.split("/")[0]

        await emit_status(
            f"browsing {domain}",
            status="in_progress",
            emitter=emitter,
            done=False,
        )

        request = await get_request()
        content, docs = get_content_from_url(request, url)

        for doc in docs:
            metadata = doc.metadata or {}
            await emitter(
                {
                    "type": "citation",
                    "data": {
                        "document": [doc.page_content],
                        "metadata": [metadata],
                        "source": {
                            "name": metadata.get("title")
                            or metadata.get("source")
                            or url
                        },
                    },
                }
            )

        await emit_status(
            f"read webpage from {domain}",
            status="complete",
            emitter=emitter,
            extra_data={"url": url},
        )

        return json.dumps(
            {
                "status": "success",
                "url": url,
                "content": content,
                "documents": [
                    {"content": doc.page_content, "metadata": doc.metadata}
                    for doc in docs
                ],
            }
        )

    except Exception as e:
        await emit_status(
            "failed to read webpage",
            status="error",
            emitter=emitter,
            error=True,
        )
        return json.dumps(
            {
                "status": "error",
                "url": url,
                "error": str(e),
            }
        )


async def fetch_url_with_fallback(
    url: str,
    emitter: Any,
    user: UserModel,
    provider: str,
    firecrawl_api_key: Optional[str] = None,
    firecrawl_base_url: str = "https://api.firecrawl.dev",
    tavily_api_key: Optional[str] = None,
    tavily_base_url: str = "https://api.tavily.com",
    exa_api_key: Optional[str] = None,
    exa_base_url: str = "https://api.exa.ai",
    jina_api_key: Optional[str] = None,
    jina_reader_base_url: str = "https://r.jina.ai",
) -> str:
    selected = _select_fetch_provider(
        provider, firecrawl_api_key, tavily_api_key, exa_api_key
    )
    if selected == "firecrawl":
        return await firecrawl_fetch_url(
            url=url,
            emitter=emitter,
            api_key=firecrawl_api_key,
            base_url=firecrawl_base_url,
        )
    if selected == "tavily":
        return await tavily_fetch_url(
            url=url,
            emitter=emitter,
            api_key=tavily_api_key,
            base_url=tavily_base_url,
        )
    if selected == "exa":
        return await exa_fetch_url(
            url=url,
            emitter=emitter,
            api_key=exa_api_key,
            base_url=exa_base_url,
        )
    if selected == "jina_reader":
        return await jina_reader_fetch_url(
            url=url,
            emitter=emitter,
            api_key=jina_api_key,
            base_url=jina_reader_base_url,
        )
    return await native_fetch_url(url=url, emitter=emitter, user=user)


async def firecrawl_fetch_url(
    url: str, emitter: Any, api_key: str, base_url: str
) -> str:
    try:
        parsed_url = urlparse(url)
        domain = parsed_url.netloc or parsed_url.path.split("/")[0]

        await emit_status(
            f"browsing {domain}",
            status="in_progress",
            emitter=emitter,
            done=False,
        )

        endpoint = f"{base_url}/v2/scrape"
        payload = {
            "url": url,
            "formats": ["markdown"],
            "onlyMainContent": True,
            "timeout": 30000,
        }
        headers = {"Authorization": f"Bearer {api_key}"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(endpoint, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        if isinstance(data, dict) and data.get("success") is False:
            raise RuntimeError(data.get("error") or "Firecrawl request failed")

        payload_data = data.get("data") if isinstance(data, dict) else {}
        if not isinstance(payload_data, dict):
            payload_data = {}

        content = ""
        for key in ("markdown", "content", "text", "html"):
            if payload_data.get(key):
                content = str(payload_data.get(key) or "")
                break

        metadata = payload_data.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        if payload_data.get("title") and not metadata.get("title"):
            metadata["title"] = payload_data.get("title")
        metadata.setdefault("source", url)
        metadata.setdefault("url", url)

        await emitter(
            {
                "type": "citation",
                "data": {
                    "document": [content],
                    "metadata": [metadata],
                    "source": {
                        "name": metadata.get("title") or metadata.get("source") or url
                    },
                },
            }
        )

        await emit_status(
            f"read webpage from {domain}",
            status="complete",
            emitter=emitter,
            extra_data={"url": url},
        )

        return json.dumps(
            {
                "status": "success",
                "url": url,
                "content": content,
                "documents": [{"content": content, "metadata": metadata}],
            }
        )

    except Exception as e:
        await emit_status(
            "failed to read webpage",
            status="error",
            emitter=emitter,
            error=True,
        )
        return json.dumps(
            {
                "status": "error",
                "url": url,
                "error": str(e),
            }
        )


async def tavily_fetch_url(
    url: str, emitter: Any, api_key: str, base_url: str
) -> str:
    try:
        parsed_url = urlparse(url)
        domain = parsed_url.netloc or parsed_url.path.split("/")[0]

        await emit_status(
            f"browsing {domain}",
            status="in_progress",
            emitter=emitter,
            done=False,
        )

        endpoint = f"{base_url}/extract"
        payload = {
            "api_key": api_key,
            "urls": [url],
            "include_images": False,
            "include_raw_content": False,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(endpoint, json=payload)
            response.raise_for_status()
            data = response.json()

        results = data.get("results") if isinstance(data, dict) else None
        item = results[0] if isinstance(results, list) and results else {}
        if not isinstance(item, dict):
            item = {}

        content = (
            item.get("content")
            or item.get("raw_content")
            or item.get("text")
            or ""
        )
        metadata = {
            "source": item.get("url") or url,
            "url": item.get("url") or url,
            "title": item.get("title") or item.get("name") or _domain_from_url(url),
        }

        await emitter(
            {
                "type": "citation",
                "data": {
                    "document": [content],
                    "metadata": [metadata],
                    "source": {
                        "name": metadata.get("title") or metadata.get("source") or url
                    },
                },
            }
        )

        await emit_status(
            f"read webpage from {domain}",
            status="complete",
            emitter=emitter,
            extra_data={"url": url},
        )

        return json.dumps(
            {
                "status": "success",
                "url": url,
                "content": content,
                "documents": [{"content": content, "metadata": metadata}],
            }
        )

    except Exception as e:
        await emit_status(
            "failed to read webpage",
            status="error",
            emitter=emitter,
            error=True,
        )
        return json.dumps(
            {
                "status": "error",
                "url": url,
                "error": str(e),
            }
        )


async def exa_fetch_url(
    url: str, emitter: Any, api_key: str, base_url: str
) -> str:
    try:
        parsed_url = urlparse(url)
        domain = parsed_url.netloc or parsed_url.path.split("/")[0]

        await emit_status(
            f"browsing {domain}",
            status="in_progress",
            emitter=emitter,
            done=False,
        )

        endpoint = f"{base_url}/contents"
        payload = {"urls": [url], "text": True}
        headers = {"Authorization": f"Bearer {api_key}"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(endpoint, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        results = data.get("results") if isinstance(data, dict) else None
        item = results[0] if isinstance(results, list) and results else {}
        if not isinstance(item, dict):
            item = {}

        content = (
            item.get("text")
            or item.get("content")
            or item.get("summary")
            or item.get("snippet")
            or item.get("highlights")
            or ""
        )
        if isinstance(content, list):
            content = "\n".join([str(part) for part in content if part])
        if not isinstance(content, str):
            content = str(content)

        metadata = {
            "source": item.get("url") or url,
            "url": item.get("url") or url,
            "title": item.get("title") or item.get("name") or _domain_from_url(url),
        }

        await emitter(
            {
                "type": "citation",
                "data": {
                    "document": [content],
                    "metadata": [metadata],
                    "source": {
                        "name": metadata.get("title") or metadata.get("source") or url
                    },
                },
            }
        )

        await emit_status(
            f"read webpage from {domain}",
            status="complete",
            emitter=emitter,
            extra_data={"url": url},
        )

        return json.dumps(
            {
                "status": "success",
                "url": url,
                "content": content,
                "documents": [{"content": content, "metadata": metadata}],
            }
        )

    except Exception as e:
        await emit_status(
            "failed to read webpage",
            status="error",
            emitter=emitter,
            error=True,
        )
        return json.dumps(
            {
                "status": "error",
                "url": url,
                "error": str(e),
            }
        )


async def jina_reader_fetch_url(
    url: str,
    emitter: Any,
    api_key: Optional[str],
    base_url: str,
) -> str:
    try:
        parsed_url = urlparse(url)
        domain = parsed_url.netloc or parsed_url.path.split("/")[0]

        await emit_status(
            f"browsing {domain}",
            status="in_progress",
            emitter=emitter,
            done=False,
        )

        endpoint = _build_jina_reader_url(base_url, url)
        headers: dict[str, str] = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(endpoint, headers=headers)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type.lower():
                data = response.json()
                content = (
                    data.get("data")
                    or data.get("content")
                    or data.get("text")
                    or json.dumps(data)
                )
            else:
                content = response.text

        metadata = {
            "source": url,
            "url": url,
            "title": _domain_from_url(url),
        }

        await emitter(
            {
                "type": "citation",
                "data": {
                    "document": [content],
                    "metadata": [metadata],
                    "source": {
                        "name": metadata.get("title") or metadata.get("source") or url
                    },
                },
            }
        )

        await emit_status(
            f"read webpage from {domain}",
            status="complete",
            emitter=emitter,
            extra_data={"url": url},
        )

        return json.dumps(
            {
                "status": "success",
                "url": url,
                "content": content,
                "documents": [{"content": content, "metadata": metadata}],
            }
        )

    except Exception as e:
        await emit_status(
            "failed to read webpage",
            status="error",
            emitter=emitter,
            error=True,
        )
        return json.dumps(
            {
                "status": "error",
                "url": url,
                "error": str(e),
            }
        )


async def web_search_with_provider(
    search_queries: list[str],
    emitter: Any,
    user: UserModel,
    provider: str,
    tavily_api_key: Optional[str] = None,
    tavily_base_url: str = "https://api.tavily.com",
    tavily_search_depth: str = "basic",
    tavily_max_results: int = 5,
    exa_api_key: Optional[str] = None,
    exa_base_url: str = "https://api.exa.ai",
    exa_max_results: int = 5,
    jina_api_key: Optional[str] = None,
    jina_search_base_url: str = "https://s.jina.ai",
    jina_search_max_results: int = 5,
) -> str:
    selected = _select_search_provider(
        provider, tavily_api_key, exa_api_key, jina_api_key
    )
    if selected == "tavily":
        return await tavily_web_search(
            search_queries=search_queries,
            emitter=emitter,
            api_key=tavily_api_key,
            base_url=tavily_base_url,
            search_depth=tavily_search_depth,
            max_results=tavily_max_results,
        )
    if selected == "exa":
        return await exa_web_search(
            search_queries=search_queries,
            emitter=emitter,
            api_key=exa_api_key,
            base_url=exa_base_url,
            max_results=exa_max_results,
        )
    if selected == "jina_search":
        return await jina_web_search(
            search_queries=search_queries,
            emitter=emitter,
            api_key=jina_api_key,
            base_url=jina_search_base_url,
            max_results=jina_search_max_results,
        )
    return await native_web_search(
        search_queries=search_queries,
        emitter=emitter,
        user=user,
    )


async def tavily_web_search(
    search_queries: list[str],
    emitter: Any,
    api_key: str,
    base_url: str,
    search_depth: str,
    max_results: int,
) -> str:
    try:
        await emit_status(
            "searching the web",
            extra_data={"queries": search_queries},
            status="web_search_queries_generated",
            done=False,
            emitter=emitter,
        )

        endpoint = f"{base_url}/search"
        results: list[dict[str, Any]] = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            for query in search_queries:
                payload = {
                    "api_key": api_key,
                    "query": query,
                    "search_depth": search_depth,
                    "include_answer": False,
                    "include_images": False,
                    "include_raw_content": False,
                    "max_results": max_results,
                }
                response = await client.post(endpoint, json=payload)
                response.raise_for_status()
                data = response.json()
                items = data.get("results") if isinstance(data, dict) else None
                if isinstance(items, list):
                    results.extend(items)

        search_results = [_normalize_search_item(it) for it in results if it]
        await _emit_search_citations(search_results, emitter)

        await emit_status(
            f"searched {len(search_results)} website{'s' if len(search_results) != 1 else ''}",
            status="web_search",
            done=True,
            extra_data={
                "urls": [sr["url"] for sr in search_results],
                "items": [
                    {
                        "title": sr["name"],
                        "link": sr["url"],
                        "url": sr["url"],
                        "source": sr["url"],
                    }
                    for sr in search_results
                ],
            },
            emitter=emitter,
        )

        return json.dumps(
            {
                "status": "web search completed successfully!",
                "result_count": len(search_results),
                "results": search_results,
            }
        )

    except Exception as e:
        await emit_status(
            f"encountered an error while searching the web: {str(e)}",
            status="error",
            done=True,
            error=True,
            emitter=emitter,
        )
        return json.dumps(
            {
                "status": "web search failed",
                "error": str(e),
            }
        )


async def exa_web_search(
    search_queries: list[str],
    emitter: Any,
    api_key: str,
    base_url: str,
    max_results: int,
) -> str:
    try:
        await emit_status(
            "searching the web",
            extra_data={"queries": search_queries},
            status="web_search_queries_generated",
            done=False,
            emitter=emitter,
        )

        endpoint = f"{base_url}/search"
        results: list[dict[str, Any]] = []
        headers = {"Authorization": f"Bearer {api_key}"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            for query in search_queries:
                payload = {
                    "query": query,
                    "num_results": max_results,
                    "text": True,
                    "use_autoprompt": True,
                }
                response = await client.post(endpoint, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                items = data.get("results") if isinstance(data, dict) else None
                if isinstance(items, list):
                    results.extend(items)

        search_results = [_normalize_search_item(it) for it in results if it]
        await _emit_search_citations(search_results, emitter)

        await emit_status(
            f"searched {len(search_results)} website{'s' if len(search_results) != 1 else ''}",
            status="web_search",
            done=True,
            extra_data={
                "urls": [sr["url"] for sr in search_results],
                "items": [
                    {
                        "title": sr["name"],
                        "link": sr["url"],
                        "url": sr["url"],
                        "source": sr["url"],
                    }
                    for sr in search_results
                ],
            },
            emitter=emitter,
        )

        return json.dumps(
            {
                "status": "web search completed successfully!",
                "result_count": len(search_results),
                "results": search_results,
            }
        )

    except Exception as e:
        await emit_status(
            f"encountered an error while searching the web: {str(e)}",
            status="error",
            done=True,
            error=True,
            emitter=emitter,
        )
        return json.dumps(
            {
                "status": "web search failed",
                "error": str(e),
            }
        )


async def jina_web_search(
    search_queries: list[str],
    emitter: Any,
    api_key: Optional[str],
    base_url: str,
    max_results: int,
) -> str:
    try:
        await emit_status(
            "searching the web",
            extra_data={"queries": search_queries},
            status="web_search_queries_generated",
            done=False,
            emitter=emitter,
        )

        results: list[dict[str, Any]] = []
        headers: dict[str, str] = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            for query in search_queries:
                endpoint, params = _build_jina_search_url(base_url, query)
                if params:
                    params.setdefault("limit", max_results)
                response = await client.get(endpoint, params=params or None, headers=headers)
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                if "application/json" in content_type.lower():
                    data = response.json()
                    items: Any = None
                    if isinstance(data, list):
                        items = data
                    elif isinstance(data, dict):
                        items = data.get("results") or data.get("data") or data.get("items")
                    if isinstance(items, dict):
                        items = [items]
                    if isinstance(items, list):
                        results.extend(items)
                else:
                    results.append(
                        {
                            "title": f"Jina Search: {query}",
                            "url": endpoint,
                            "text": response.text,
                        }
                    )

        search_results = [_normalize_search_item(it) for it in results if it]
        await _emit_search_citations(search_results, emitter)

        await emit_status(
            f"searched {len(search_results)} website{'s' if len(search_results) != 1 else ''}",
            status="web_search",
            done=True,
            extra_data={
                "urls": [sr["url"] for sr in search_results],
                "items": [
                    {
                        "title": sr["name"],
                        "link": sr["url"],
                        "url": sr["url"],
                        "source": sr["url"],
                    }
                    for sr in search_results
                ],
            },
            emitter=emitter,
        )

        return json.dumps(
            {
                "status": "web search completed successfully!",
                "result_count": len(search_results),
                "results": search_results,
            }
        )

    except Exception as e:
        await emit_status(
            f"encountered an error while searching the web: {str(e)}",
            status="error",
            done=True,
            error=True,
            emitter=emitter,
        )
        return json.dumps(
            {
                "status": "web search failed",
                "error": str(e),
            }
        )


async def native_web_search(
    search_queries: list[str], emitter: Any, user: UserModel
) -> str:
    """Search using the native search engine."""
    try:
        await emit_status(
            "searching the web",
            extra_data={"queries": search_queries},
            status="web_search_queries_generated",
            done=False,
            emitter=emitter,
        )

        form = SearchForm.model_validate({"queries": search_queries})
        result = await process_web_search(
            request=await get_request(), form_data=form, user=user
        )

        items = cast(
            list[dict[str, Any]], result.get("items") or result.get("docs") or []
        )

        search_results = [_normalize_search_item(it) for it in items if it]
        await _emit_search_citations(search_results, emitter)
        await emit_status(
            f"searched {len(search_results)} website{'s' if len(search_results) != 1 else ''}",
            status="web_search",
            done=True,
            extra_data={
                "urls": [sr["url"] for sr in search_results],
                "items": [
                    {
                        "title": sr["name"],
                        "link": sr["url"],
                        "url": sr["url"],
                        "source": sr["url"],
                    }
                    for sr in search_results
                ],
            },
            emitter=emitter,
        )



        return json.dumps(
            {
                "status": "web search completed successfully!",
                "result_count": len(search_results),
                "results": search_results,
            }
        )

    except Exception as e:
        await emit_status(
            f"encountered an error while searching the web: {str(e)}",
            status="error",
            done=True,
            error=True,
            emitter=emitter,
        )
        return json.dumps(
            {
                "status": "web search failed",
                "error": str(e),
            }
        )



