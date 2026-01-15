"""
title: Gemini URL Context Toggle
author: OVINC CN
description: Toggle URL context tool in requests.
version: 0.0.1
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
            "data:image/svg+xml;base64,PHN2ZyBkYXRhLXYtMmJjNjQ2MGU9IiIgdmlld0JveD0iMCAwIDQ4IDQ4IiBmaWxsPSJub25lIiB4bWx"
            "ucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHN0cm9rZT0iY3VycmVudENvbG9yIiBjbGFzcz0iYXJjby1pY29uIGFyY28taWNv"
            "bi1saW5rIiBzdHJva2Utd2lkdGg9IjQiIHN0cm9rZS1saW5lY2FwPSJidXR0IiBzdHJva2UtbGluZWpvaW49Im1pdGVyIiBmaWx0ZXI9I"
            "iIgc3R5bGU9ImZvbnQtc2l6ZTogMzJweDsiPjxwYXRoIGQ9Im0xNC4xIDI1LjQxNC00Ljk1IDQuOTVhNiA2IDAgMCAwIDguNDg2IDguND"
            "g1bDguNDg1LTguNDg1YTYgNiAwIDAgMCAwLTguNDg1bTcuNzc5LjcwNyA0Ljk1LTQuOTVhNiA2IDAgMSAwLTguNDg2LTguNDg1bC04LjQ"
            "4NSA4LjQ4NWE2IDYgMCAwIDAgMCA4LjQ4NSI+PC9wYXRoPjwvc3ZnPg=="
        )

    def inlet(self, body: dict) -> dict:
        tools = list(body.get("tools") or [])
        has_url_context = any(
            isinstance(tool, dict)
            and ("urlContext" in tool or "url_context" in tool)
            for tool in tools
        )
        if not has_url_context:
            tools.append({"urlContext": {}})
        body["tools"] = tools
        return body
