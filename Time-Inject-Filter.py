"""
title: 时间信息注入
author: Open-WebUI-Extensions
description: 自动为用户消息注入当前时间信息（日期、时间、时区、星期）
version: 0.0.1
licence: MIT
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Filter:
    class Valves(BaseModel):
        priority: int = Field(default=0, description="过滤器优先级")
        timezone: str = Field(default="Asia/Shanghai", description="时区设置")
        inject_to_system: bool = Field(
            default=True, description="是否注入到系统消息中（否则注入到用户消息前）"
        )

    def __init__(self):
        self.valves = self.Valves()

    def _get_time_info(self) -> str:
        """获取当前时间信息"""
        try:
            import zoneinfo

            tz = zoneinfo.ZoneInfo(self.valves.timezone)
        except Exception:
            tz = None

        now = datetime.now(tz)

        # 星期映射
        weekday_names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        weekday = weekday_names[now.weekday()]

        # 格式化时间信息
        time_info = f"""# 以下是时间信息参考
当前日期：{now.strftime("%Y-%m-%d")}
当前时间：{now.strftime("%H:%M:%S")}
当前时区：{self.valves.timezone}
当前星期：{weekday}"""

        return time_info

    def inlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
    ) -> dict:
        time_info = self._get_time_info()
        messages = body.get("messages", [])

        if not messages:
            return body

        if self.valves.inject_to_system:
            # 注入到系统消息中
            system_message_exists = False
            for msg in messages:
                if msg.get("role") == "system":
                    # 在现有系统消息末尾追加时间信息
                    msg["content"] = msg.get("content", "") + "\n\n" + time_info
                    system_message_exists = True
                    break

            if not system_message_exists:
                # 如果没有系统消息，创建一个
                messages.insert(0, {"role": "system", "content": time_info})
        else:
            # 注入到最后一条用户消息前
            for i in range(len(messages) - 1, -1, -1):
                if messages[i].get("role") == "user":
                    original_content = messages[i].get("content", "")
                    messages[i]["content"] = time_info + "\n\n" + original_content
                    break

        body["messages"] = messages
        return body
