"""
title: Live Token Tracker when Chatting
description: Tracks token usage and timing for the Chat (supports multimodal content)
author: WillLiang713
git_url: https://github.com/WillLiang713/Open-WebUI-Extensions
version: 1.1.0
requirements: tiktoken, pydantic
environment_variables:
disclaimer: Provided as-is without warranties.
            You must ensure it meets your needs.
"""

import time
from typing import Any, Awaitable, Callable, Optional

import tiktoken
from pydantic import BaseModel


class Config:
    DEBUG = False
    # If True, count image blocks as a placeholder string "[image]" for rough token accounting.
    # This is NOT real vision token counting, just a heuristic to avoid undercounting too much.
    COUNT_IMAGES_AS_PLACEHOLDER = False


def debug_print(msg: str):
    if Config.DEBUG:
        print("[TOKEN TRACKER DEBUG] " + msg)


def format_number(n: int) -> str:
    """Format number without separators for cleaner display."""
    return str(n)


def format_time(seconds: float) -> str:
    """Format time: show as 'm s' if >= 60s, otherwise just 's'."""
    if seconds >= 60:
        mins = int(seconds // 60)
        secs = seconds % 60
        return f"{mins}m {secs:.1f}s"
    return f"{seconds:.2f}s"


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
        prefer_api_usage: bool = True  # 优先使用 API 返回的 usage 数据
        debug: bool = False
        # Optional valve to count images as placeholder
        count_images_as_placeholder: bool = False

    def __init__(self):
        self.valves = self.Valves()
        Config.DEBUG = self.valves.debug
        Config.COUNT_IMAGES_AS_PLACEHOLDER = self.valves.count_images_as_placeholder

        self.input_tokens = 0
        self.input_tokens_estimated = True  # 是否为估算值
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

    def _content_to_text(self, content: Any) -> str:
        """
        Convert OpenAI-style message content into plain text for token counting.
        Supports:
          - str
          - list[{"type":"text","text":...}, {"type":"image_url",...}, ...]
        Images are ignored by default (or optionally counted as "[image]" placeholder).
        """
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            parts = []
            for item in content:
                # item can be dict blocks (OpenAI multimodal format)
                if isinstance(item, dict):
                    t = item.get("type")
                    if t == "text":
                        parts.append(str(item.get("text", "")))
                    elif t in ("image_url", "image", "input_image"):
                        if Config.COUNT_IMAGES_AS_PLACEHOLDER:
                            parts.append("[image]")
                    else:
                        # Unknown block type: ignore (or stringify if you prefer)
                        pass
                # some implementations may include raw strings in the list
                elif isinstance(item, str):
                    parts.append(item)
                else:
                    # ignore unknown item types
                    pass

            return "\n".join([p for p in parts if p]).strip()

        # Fallback for unexpected types (dict/int/None)
        return str(content or "")

    def _messages_to_text(self, messages: list) -> str:
        """
        Turn a list of messages into a single text blob for token counting.
        """
        chunks = []
        for m in messages:
            content = self._content_to_text(m.get("content", ""))
            if content:
                chunks.append(content)
        return "\n".join(chunks)

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
        # Sync config with valves each call (in case UI toggles change at runtime)
        Config.DEBUG = self.valves.debug
        Config.COUNT_IMAGES_AS_PLACEHOLDER = self.valves.count_images_as_placeholder

        messages = body.get("messages", [])
        content_str = self._messages_to_text(messages)
        cleaned_text = self._remove_roles(content_str)

        enc = get_encoding_for_model(body.get("model", "unknown-model"))
        self.input_tokens = len(enc.encode(cleaned_text))

        if __event_emitter__:
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {
                        "description": f"Prompt Tokens: {format_number(self.input_tokens)}",
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
         - Count output tokens (prefer API usage if available)
         - Emit stats
        """
        end_time = time.time()
        elapsed = end_time - self.start_time if self.start_time else 0.0

        # 尝试从 API 返回的 usage 数据中读取 token 数量
        usage = body.get("usage", {})
        input_tokens = 0
        output_tokens = 0
        is_estimated = True

        if self.valves.prefer_api_usage and usage:
            # 优先使用 API 返回的真实数据
            api_prompt_tokens = usage.get("prompt_tokens", 0)
            api_completion_tokens = usage.get("completion_tokens", 0)
            
            if api_prompt_tokens > 0 or api_completion_tokens > 0:
                input_tokens = api_prompt_tokens
                output_tokens = api_completion_tokens
                is_estimated = False
                debug_print(f"Using API usage: prompt={input_tokens}, completion={output_tokens}")

        # 如果没有 API 数据，回退到 tiktoken 估算
        if is_estimated:
            input_tokens = self.input_tokens
            
            messages = body.get("messages", [])
            last_msg_raw = messages[-1].get("content", "") if messages else ""
            last_msg_text = self._content_to_text(last_msg_raw)

            enc = get_encoding_for_model(body.get("model", "unknown-model"))
            output_tokens = len(enc.encode(last_msg_text))
            debug_print(f"Using tiktoken estimation: input={input_tokens}, output={output_tokens}")

        total_tokens = input_tokens + output_tokens
        tokens_per_sec = output_tokens / elapsed if elapsed > 0 else 0.0

        # 构建统计信息字符串（简洁风格）
        stats_list = []
        if self.valves.show_elapsed_time:
            stats_list.append(format_time(elapsed))
        if self.valves.show_tokens_per_second:
            stats_list.append(f"{tokens_per_sec:.1f}/s")
        if self.valves.show_tokens:
            stats_list.append(
                f"Prompt: {format_number(input_tokens)} | Completion: {format_number(output_tokens)} | Total: {format_number(total_tokens)}"
            )

        stats_string = " | ".join(stats_list)

        if __event_emitter__:
            await __event_emitter__(
                {"type": "status", "data": {"description": stats_string, "done": True}}
            )

        return body
