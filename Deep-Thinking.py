"""
title: 开启深度思考
author: Open-WebUI-Extensions
description: 开启深度思考模式
version: 0.0.5
licence: MIT
"""

from typing import Optional

from pydantic import BaseModel, Field


class Filter:
    class Valves(BaseModel):
        priority: int = Field(default=0, description="Filter priority")

    class UserValves(BaseModel):
        budget_tokens: int = Field(default=8192, description="Thinking token budget (minimum 1024)")

    def __init__(self):
        self.valves = self.Valves()
        self.toggle = True
        self.icon = (
            "data:image/svg+xml;base64,PHN2ZyB2aWV3Qm94PSIwIDAgNDggNDgiIGZpbGw9Im5v"
            "bmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyIgc3Ryb2tlPSJjdXJyZW"
            "50Q29sb3IiIHN0cm9rZS13aWR0aD0iNCIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJv"
            "a2UtbGluZWpvaW49InJvdW5kIj48cGF0aCBkPSJNMjQgNGMtNy43MzIgMC0xNCA2LjI2OC"
            "0xNCAxNCAwIDUuMjc5IDIuOTMgOS44NyA3LjI1IDEyLjI0VjM2YTYuNzUgNi43NSAwIDAg"
            "MCAxMy41IDB2LTUuNzZDMzUuMDcgMjcuODcgMzggMjMuMjc5IDM4IDE4YzAtNy43MzItNi"
            "4yNjgtMTQtMTQtMTRaIi8+PHBhdGggZD0iTTE4IDQ0aDEyIi8+PC9zdmc+"
        )

    def inlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
    ) -> dict:
        # 获取用户配置的 budget_tokens
        user_valves = __user__.get("valves") if __user__ else None
        budget_tokens = user_valves.budget_tokens if user_valves else 8192

        body["thinking"] = {
            "type": "enabled",
            "budget_tokens": budget_tokens
        }
        body["enable_thinking"] = {
            "type": "enabled",
            "budget_tokens": budget_tokens
        }
        return body

