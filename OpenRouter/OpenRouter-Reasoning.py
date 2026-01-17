"""
title: OpenRouter Inference Control
author: Open-WebUI-Extensions
description: 为 OpenRouter 的 GPT-5 / Gemini 3 系列推理模型提供思考强度控制
version: 0.0.3
licence: MIT
"""

import json
import logging
import time
import uuid
from typing import Any, AsyncIterable, Dict, List, Literal, Optional, Tuple

import httpx
from fastapi import Request
from open_webui.env import GLOBAL_LOG_LEVEL
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

logger = logging.getLogger(__name__)
logger.setLevel(GLOBAL_LOG_LEVEL)


class Pipe:
    class Valves(BaseModel):
        models: str = Field(
            default="openai/gpt-5.2",
            title="模型",
            description="使用英文逗号分隔多个模型，例如 openai/gpt-5.2,google/gemini-3-pro",
        )
        base_url: str = Field(
            default="https://openrouter.ai/api/v1",
            title="Base URL",
        )
        api_key: str = Field(default="", title="API Key")
        timeout: int = Field(default=600, title="请求超时时间 (秒)")
        proxy: Optional[str] = Field(default=None, title="代理地址")

    class UserValves(BaseModel):
        reasoning_effort: Literal["xhigh", "high", "medium", "low", "none"] = Field(
            default="medium",
            title="思考强度",
            description="xhigh=最深(95%), high=高(80%), medium=中(50%), low=低(20%), none=禁用",
        )
        exclude_reasoning: bool = Field(
            default=False,
            title="隐藏思考过程",
            description="启用后模型仍会进行推理，但不会在响应中显示思考过程",
        )

    def __init__(self):
        self.valves = self.Valves()

    def pipes(self):
        result = []
        for model in self.valves.models.split(","):
            model = model.strip()
            if not model:
                continue
            # id 保留完整模型名用于 API 请求
            # name 简化显示（从 "openai/gpt-5.2" 提取 "gpt-5.2"）
            display_name = model.split("/")[-1] if "/" in model else model
            result.append({"id": model, "name": display_name})
        return result

    async def pipe(
        self,
        body: dict,
        __user__: dict,
        __request__: Request,
    ) -> StreamingResponse:
        return StreamingResponse(
            self._pipe(body=body, __user__=__user__, __request__=__request__)
        )

    async def _pipe(
        self, body: dict, __user__: dict, __request__: Request
    ) -> AsyncIterable:
        user_valves: Pipe.UserValves = __user__["valves"]
        model, payload = await self._build_payload(body=body, user_valves=user_valves)
        
        try:
            async with httpx.AsyncClient(
                base_url=self.valves.base_url,
                headers={
                    "Authorization": f"Bearer {self.valves.api_key}",
                    "HTTP-Referer": "https://open-webui.com",
                    "X-Title": "Open WebUI",
                },
                proxy=self.valves.proxy or None,
                trust_env=True,
                timeout=self.valves.timeout,
            ) as client:
                async with client.stream(**payload) as response:
                    if response.status_code != 200:
                        text = ""
                        async for line in response.aiter_lines():
                            text += line
                        logger.error(
                            "response invalid with %d: %s", response.status_code, text
                        )
                        yield self._format_data(
                            model=model,
                            content=f"Error {response.status_code}: {text}",
                            finish_reason="stop",
                        )
                        return

                    # 处理流式响应
                    is_thinking = False
                    has_started_content = False
                    
                    async for raw_line in response.aiter_lines():
                        line = raw_line.strip()
                        if not line:
                            continue
                        if not line.startswith("data:"):
                            continue
                        
                        data_line = line[5:].strip()
                        if data_line == "[DONE]":
                            break
                        
                        try:
                            data = json.loads(data_line)
                        except json.JSONDecodeError:
                            continue
                        
                        choices = data.get("choices", [])
                        if not choices:
                            continue
                        
                        choice = choices[0]
                        delta = choice.get("delta", {})
                        finish_reason = choice.get("finish_reason")
                        
                        # 处理 reasoning 内容（思考过程）
                        reasoning = delta.get("reasoning")
                        if reasoning:
                            if not is_thinking:
                                is_thinking = True
                                yield self._format_data(model=model, content="<think>")
                            yield self._format_data(model=model, content=reasoning)
                            continue
                        
                        # 处理正文内容
                        content = delta.get("content")
                        if content:
                            if is_thinking and not has_started_content:
                                is_thinking = False
                                has_started_content = True
                                yield self._format_data(model=model, content="</think>")
                            yield self._format_data(model=model, content=content)
                        
                        # 处理结束
                        if finish_reason:
                            if is_thinking:
                                yield self._format_data(model=model, content="</think>")
                            yield self._format_data(
                                model=model,
                                content="",
                                finish_reason=finish_reason,
                            )

        except Exception as err:
            logger.exception("[GPTReasoningPipe] failed: %s", err)
            yield self._format_data(model=model, content=str(err), finish_reason="stop")

    async def _build_payload(
        self, body: dict, user_valves: UserValves
    ) -> Tuple[str, dict]:
        # 解析模型名称（移除 pipe 前缀）
        model = body["model"]
        if "." in model:
            model = model.split(".", 1)[1]
        
        # 构建消息
        messages = body.get("messages", [])
        
        # 构建 reasoning 配置
        reasoning_config: Dict[str, Any] = {}
        
        if user_valves.reasoning_effort != "none":
            reasoning_config["effort"] = user_valves.reasoning_effort
        else:
            # none 表示完全禁用推理
            reasoning_config["effort"] = "none"
        
        if user_valves.exclude_reasoning:
            reasoning_config["exclude"] = True
        
        # 构建请求体
        data: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
        }
        
        # 添加 reasoning 配置
        if reasoning_config:
            data["reasoning"] = reasoning_config
        
        # 透传其他参数
        passthrough_keys = ["temperature", "top_p", "max_tokens", "max_completion_tokens", "stop"]
        for key in passthrough_keys:
            if key in body:
                data[key] = body[key]
        
        payload = {
            "method": "POST",
            "url": "/chat/completions",
            "json": data,
        }
        
        return model, payload

    def _format_data(
        self,
        model: str = "",
        content: str = "",
        finish_reason: Optional[str] = None,
    ) -> str:
        data = {
            "id": f"chatcmpl-{uuid.uuid4().hex}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": content} if content else {},
                    "finish_reason": finish_reason,
                }
            ],
        }
        return f"data: {json.dumps(data)}\n\n"
