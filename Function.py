"""
title: Live Token Tracker when Chatting
description: Tracks token usage and timing for the Chat
authors: WillLiang713
funding_url: https://github.com/open-webui
version: 0.0.2
license: MIT
requirements: tiktoken, pydantic
environment_variables:
disclaimer: Provided as-is without warranties.
            You must ensure it meets your needs.
"""

import time
from typing import Any, Awaitable, Callable, Optional

import tiktoken
from pydantic import BaseModel, Field


class Config:
    DEBUG = False


def debug_print(msg: str):
    if Config.DEBUG:
        print("[TOKEN TRACKER DEBUG] " + msg)


def get_encoding_for_model(model_name: str):
    """
    Safely get a tiktoken encoding for the given model_name,
    falling back to 'cl100k_base' if unknown.
    """
    try:
        return tiktoken.encoding_for_model(model_name)
    except KeyError:
        debug_print(f"Unknown encoding for model={model_name}, using cl100k_base.")
        return tiktoken.get_encoding("cl100k_base")


class Filter:
    class Valves(BaseModel):
        show_elapsed_time: bool = True
        show_tokens: bool = True
        show_tokens_per_second: bool = True
        debug: bool = False

    def __init__(self):
        self.valves = self.Valves()
        Config.DEBUG = self.valves.debug

        self.input_tokens = 0
        self.start_time = None

    def _remove_roles(self, text: str) -> str:
        """
        Remove lines that begin with 'SYSTEM:', 'USER:', 'ASSISTANT:', or 'PROMPT:'.
        """
        roles = ("SYSTEM:", "USER:", "ASSISTANT:", "PROMPT:")
        lines = text.split("\n")
        cleaned = []
        for line in lines:
            if any(line.startswith(r) for r in roles):
                cleaned.append(line.split(":", 1)[1].strip())
            else:
                cleaned.append(line)
        return "\n".join(cleaned).strip()

    async def inlet(
        self,
        body: dict,
        __event_emitter__: Callable[[Any], Awaitable[None]],
        __model__: Optional[dict] = None,
        __user__: Optional[dict] = None,
    ) -> dict:
        """
        Called before the main generation step:
         - Count input tokens
         - Mark start_time
        """
        messages = body.get("messages", [])
        content_str = "\n".join([m.get("content", "") for m in messages])
        cleaned_text = self._remove_roles(content_str)

        enc = get_encoding_for_model(body.get("model", "unknown-model"))
        self.input_tokens = len(enc.encode(cleaned_text))

        if __event_emitter__:
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {
                        "description": f"Input tokens: {self.input_tokens}",
                        "done": False,
                    },
                }
            )

        self.start_time = time.time()
        return body

    async def outlet(
        self,
        body: dict,
        __event_emitter__: Callable[[Any], Awaitable[None]],
        __model__: Optional[dict] = None,
        __user__: Optional[dict] = None,
    ) -> dict:
        """
        Called after the generation step:
         - Count output tokens
         - Emit stats
        """
        end_time = time.time()
        elapsed = end_time - self.start_time

        messages = body.get("messages", [])
        last_msg_content = messages[-1].get("content", "") if messages else ""
        enc = get_encoding_for_model(body.get("model", "unknown-model"))
        output_tokens = len(enc.encode(last_msg_content))

        total_tokens = self.input_tokens + output_tokens
        tokens_per_sec = total_tokens / elapsed if elapsed > 0 else 0.0

        stats_list = []
        if self.valves.show_elapsed_time:
            stats_list.append(f"{elapsed:.2f} s")
        if self.valves.show_tokens_per_second:
            stats_list.append(f"{tokens_per_sec:.2f} T/s")
        if self.valves.show_tokens:
            stats_list.append(f"{total_tokens} Tokens")

        stats_string = " | ".join(stats_list)

        if __event_emitter__:
            await __event_emitter__(
                {"type": "status", "data": {"description": stats_string, "done": True}}
            )

        return body
