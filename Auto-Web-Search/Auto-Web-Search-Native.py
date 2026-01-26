"""
title: Auto-Web-Search
author: WillLiang713
description: A tool for performing automated web searches.
git_url: https://github.com/WillLiang713/Open-WebUI-Extensions
version: 1.0.0
required_open_webui_version: >= 0.6.0
"""

import json
from typing import Any, Literal, Optional, cast
from urllib.parse import urlparse

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


class Tools:
    class Valves(BaseModel):
        pass

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
        search_queries: Optional[list[str]] = None,
        queries: Optional[list[str]] = None,
        __event_emitter__: Any = None,
        __user__: Optional[dict] = None,
    ) -> str:
        """Search the web for a query."""
        if __user__ is None:
            raise ValueError("User information is required")

        merged_queries: list[str] = []
        if search_queries:
            merged_queries.extend(search_queries)
        if queries:
            merged_queries.extend(queries)
        if not merged_queries:
            raise ValueError("search_queries is required")

        user = Users.get_user_by_id(__user__["id"])
        if user is None:
            raise ValueError("User not found")

        return await native_web_search(
            merged_queries, emitter=__event_emitter__, user=user
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

        return await fetch_url(url, emitter=__event_emitter__, user=user)


async def fetch_url(url: str, emitter: Any, user: UserModel) -> str:
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

        result_items = cast(list[dict[str, Any]], result.get("items") or [])
        docs = cast(list[dict[str, Any]], result.get("docs") or [])

        if result_items:
            search_results = cast(
                list[dict[str, str]],
                [
                    {
                        "source": item.get("link")
                        or item.get("url")
                        or item.get("source")
                        or "",
                        "title": item.get("title") or item.get("name") or "",
                        "content": item.get("snippet")
                        or item.get("content")
                        or item.get("text")
                        or "",
                    }
                    for item in result_items
                    if item
                ],
            )
        else:
            search_results = cast(
                list[dict[str, str]],
                [
                    {
                        "source": (item.get("metadata") or {}).get("source")
                        or (item.get("metadata") or {}).get("link")
                        or (item.get("metadata") or {}).get("url")
                        or "",
                        "title": (item.get("metadata") or {}).get("title") or "",
                        "content": (item.get("metadata") or {}).get("snippet")
                        or item.get("content")
                        or "",
                    }
                    for item in docs
                    if item
                ],
            )

        item_count = len(search_results)

        if emitter:
            documents = []
            metadata = []
            for sr in search_results:
                link = sr.get("source", "")
                if not link:
                    continue
                title = sr.get("title", "")
                snippet = sr.get("content", "")
                doc = f"{title}\n{snippet}".strip()
                documents.append(doc)
                metadata.append(
                    {
                        "source": link,
                        "name": title,
                        "url": link,
                    }
                )

            if documents:
                await emitter(
                    {
                        "type": "citation",
                        "data": {
                            "source": {"name": "search_web", "id": "search_web"},
                            "document": documents,
                            "metadata": metadata,
                        },
                    }
                )

        await emit_status(
            f"searched {item_count} website{'s' if item_count != 1 else ''}",
            status="web_search",
            done=True,
            extra_data={
                "urls": [sr["source"] for sr in search_results if sr.get("source")]
            },
            emitter=emitter,
        )

        return json.dumps(
            {
                "status": "web search completed successfully!",
                "result_count": item_count,
                "results": search_results,
            }
        )

    except Exception as e:
        await emit_status(
            "encountered an error while searching the web",
            status="web_search",
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
