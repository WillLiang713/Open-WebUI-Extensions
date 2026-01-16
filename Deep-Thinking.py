"""
title: 开启深度思考
author: Open-WebUI-Extensions
description: 开启深度思考模式
version: 0.0.4
licence: MIT
"""

from typing import Optional

from pydantic import BaseModel, Field


class Filter:
    class Valves(BaseModel):
        priority: int = Field(default=0, description="filter priority")

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
        # GLM 格式
        body["thinking"] = {"type": "enabled"}
        # Qwen 格式
        body["enable_thinking"] = True
        return body

