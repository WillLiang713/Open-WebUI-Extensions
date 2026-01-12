"""
title: Timezone Time Tool
author: @WillLiang713 (patched by ChatGPT)
description: A tool that returns the current time for a configured timezone.
version: 1.0.1
required_open_webui_version: >= 0.6.0
"""

import json
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None


class Tools:
    class Valves(BaseModel):
        DEFAULT_TIMEZONE: str = Field(
            default="Asia/Shanghai",
            description="Default IANA time zone name (e.g., Asia/Shanghai).",
        )

    def __init__(self):
        self.valves = self.Valves()
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_time",
                    "description": "Get the current time using the configured timezone.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            }
        ]

    def _resolve_timezone(self) -> timezone:
        name = (self.valves.DEFAULT_TIMEZONE or "").strip() or "UTC"
        if ZoneInfo is None:
            return timezone.utc
        try:
            return ZoneInfo(name)
        except Exception:
            return timezone.utc

    async def get_time(
        self,
        __event_emitter__: Optional[object] = None,
        __user__: Optional[dict] = None,
    ) -> str:
        tz = self._resolve_timezone()
        now = datetime.now(tz)

        return json.dumps(
            {
                "timezone": getattr(tz, "key", None) or str(tz),
                "iso": now.isoformat(),
                "formatted": now.strftime("%Y-%m-%d %H:%M:%S %Z%z"),
            }
        )
