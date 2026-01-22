"""
title: Gemini Tools
author: OVINC CN
git_url: https://github.com/OVINC-CN/OpenWebUIPlugin.git
description: Gemini tools: code execution + web search + url context
version: 0.0.3
licence: MIT
"""

from pydantic import BaseModel, Field


class Filter:
    class Valves(BaseModel):
        priority: int = Field(default=0, description="filter priority")

    def __init__(self):
        self.valves = self.Valves()
        self.toggle = True
        self.icon = (
            "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCA0OCA0OCIg"
            "ZmlsbD0ibm9uZSIgc3Ryb2tlPSIjNDI4NUY0IiBzdHJva2Utd2lkdGg9IjQiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxp"
            "bmVqb2luPSJyb3VuZCI+CiAgPHBhdGggZD0iTTQwIDI0YzAgOC44MzctNy4xNjMgMTYtMTYgMTZTOCAzMi44MzcgOCAyNCAxNS4xNjMg"
            "OCAyNCA4YzQuNDE4IDAgOC40MTggMS43OSAxMS4zMTQgNC42ODYiLz4KICA8cGF0aCBkPSJNNDAgMjRIMjQiLz4KICA8cGF0aCBkPSJN"
            "NDAgMjR2OCIvPgo8L3N2Zz4="
        )

    def inlet(self, body: dict) -> dict:
        tools = body.get("tools") or []
        body["tools"] = tools

        # Normalize Gemini tool casing (snake -> camel)
        for tool in tools:
            if isinstance(tool, dict):
                if "google_search" in tool and "googleSearch" not in tool:
                    tool["googleSearch"] = tool.pop("google_search")
                if "code_execution" in tool and "codeExecution" not in tool:
                    tool["codeExecution"] = tool.pop("code_execution")
                if "url_context" in tool and "urlContext" not in tool:
                    tool["urlContext"] = tool.pop("url_context")
                if "function_declarations" in tool and "functionDeclarations" not in tool:
                    tool["functionDeclarations"] = tool.pop("function_declarations")

        existing = {k for t in tools if isinstance(t, dict) for k in t}

        if "googleSearch" not in existing:
            tools.append({"googleSearch": {}})
        if "codeExecution" not in existing:
            tools.append({"codeExecution": {}})
        if "urlContext" not in existing:
            tools.append({"urlContext": {}})

        return body
