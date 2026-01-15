"""
title: Gemini Chat
description: Text generation with Gemini
author: OVINC CN
git_url: https://github.com/OVINC-CN/OpenWebUIPlugin.git
version: 0.0.7
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
            default="gemini-2.5-pro",
            title="模型",
            description="使用英文逗号分隔多个模型",
        )
        base_url: str = Field(
            default="https://generativelanguage.googleapis.com/v1beta/models",
            title="Base URL",
        )
        api_key: str = Field(default="", title="API Key")
        allow_params: Optional[str] = Field(
            default="",
            title="透传参数",
            description="允许配置的参数，使用英文逗号分隔，例如 temperature",
        )
        timeout: int = Field(default=600, title="请求超时时间 (秒)")
        proxy: Optional[str] = Field(default=None, title="代理地址")

    class UserValves(BaseModel):
        enable_reasoning: bool = Field(default=True, title="展示思考内容")
        reasoning_effort_flash: Literal["minimal", "low", "medium", "high"] = Field(
            default="high",
            title="Flash 推理强度",
            description="适用 Gemini 3 Flash：minimal/low/medium/high",
        )
        reasoning_effort_pro: Literal["minimal", "low", "medium", "high"] = Field(
            default="high",
            title="Pro 推理强度",
            description="适用 Gemini 3 Pro：low/high（上游最终决定支持范围）",
        )
        thinking_budget: int = Field(
            default=-1,
            title="思考预算",
            description="适用 Gemini 2.5 系列，-1 表示自动控制",
        )

    def __init__(self):
        self.valves = self.Valves()

    def pipes(self):
        return [{"id": model, "name": model} for model in self.valves.models.split(",")]

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
                headers={"x-goog-api-key": self.valves.api_key},
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
                        response.raise_for_status()
                        return

                    # 按官方逻辑处理思考内容与正文
                    is_thinking = user_valves.enable_reasoning
                    tool_call_index = 0
                    total_tool_calls = 0
                    buffer = ""
                    if is_thinking:
                        yield self._format_data(
                            is_stream=True, model=model, content="<think>"
                        )

                    async for raw_line in response.aiter_lines():
                        line = raw_line.strip()
                        if not line:
                            if buffer:
                                try:
                                    line = json.loads(buffer)
                                    buffer = ""
                                except json.JSONDecodeError:
                                    buffer = ""
                                    continue
                            else:
                                continue
                        if isinstance(line, str) and (
                            line.startswith("event:") or not line.startswith("data:")
                        ):
                            continue
                        if isinstance(line, str):
                            data_line = line[5:].lstrip()
                            if data_line == "[DONE]":
                                break
                            # Buffer SSE data lines to tolerate split JSON chunks.
                            buffer += data_line
                            try:
                                line = json.loads(buffer)
                                buffer = ""
                            except json.JSONDecodeError:
                                continue

                        for item in line.get("candidates", []):
                            content = item.get("content", {})
                            if not content:
                                yield self._format_data(
                                    is_stream=True,
                                    model=model,
                                    finish_reason=item.get("finishReason", ""),
                                )
                                continue

                            parts = content.get("parts", [])
                            if not parts:
                                yield self._format_data(
                                    is_stream=True,
                                    model=model,
                                    finish_reason=item.get("finishReason", ""),
                                )
                                continue

                            tool_calls: List[Dict[str, Any]] = []

                            for part in parts:
                                # 处理思考内容
                                if part.get("thought", False):
                                    if is_thinking:
                                        thought_text = part.get("text", "")
                                        if thought_text:
                                            yield self._format_data(
                                                is_stream=True,
                                                model=model,
                                                content=thought_text,
                                            )
                                    continue

                                func_call = part.get("functionCall") or part.get("function_call")
                                if func_call:
                                    # 处理函数调用
                                    if is_thinking:
                                        is_thinking = False
                                        yield self._format_data(
                                            is_stream=True,
                                            model=model,
                                            content="</think>",
                                        )
                                    tool_calls.append(
                                        self._convert_function_call(
                                            func_call, index=tool_call_index
                                        )
                                    )
                                    tool_call_index += 1
                                    continue

                                # 处理正文内容
                                text = part.get("text")
                                if text or part.get("executableCode") or part.get(
                                    "codeExecutionResult"
                                ):
                                    if is_thinking:
                                        is_thinking = False
                                        yield self._format_data(
                                            is_stream=True,
                                            model=model,
                                            content="</think>",
                                        )
                                if text:
                                    yield self._format_data(
                                        is_stream=True,
                                        model=model,
                                        content=text,
                                    )

                                # 处理代码内容
                                if part.get("executableCode"):
                                    data = {
                                        "event": {
                                            "type": "status",
                                            "data": {
                                                "description": (
                                                    f"executableCode {part['executableCode'].get('language', '')}"
                                                ),
                                                "done": False,
                                            },
                                        }
                                    }
                                    yield f"data: {json.dumps(data)}\n\n"
                                if part.get("codeExecutionResult"):
                                    data = {
                                        "event": {
                                            "type": "status",
                                            "data": {
                                                "description": (
                                                    "codeExecutionResult "
                                                    f"{part['codeExecutionResult'].get('outcome', '')}"
                                                ),
                                                "done": True,
                                            },
                                        }
                                    }
                                    yield f"data: {json.dumps(data)}\n\n"

                            # 输出工具调用结果
                            if tool_calls:
                                total_tool_calls += len(tool_calls)
                                legacy_fn_call = (
                                    tool_calls[0]["function"]
                                    if total_tool_calls == 1 and len(tool_calls) == 1
                                    else None
                                )
                                yield self._format_data(
                                    is_stream=True,
                                    model=model,
                                    tool_calls=tool_calls,
                                    function_call=legacy_fn_call,
                                    finish_reason="tool_calls",
                                    role="assistant",
                                )
                    if is_thinking:
                        yield self._format_data(
                            is_stream=True, model=model, content="</think>"
                        )

        except Exception as err:
            logger.exception("[GeminiChatPipe] failed of %s", err)
            yield self._format_data(is_stream=False, content=str(err))

    async def _build_payload(
        self, body: dict, user_valves: UserValves
    ) -> Tuple[str, dict]:
        # payload
        model = body["model"].split(".", 1)[1]
        is_gemini_3_series = "gemini-3" in model
        is_gemini_3_pro_series = "gemini-3-pro" in model
        all_contents = []

        # read messages
        for message in body["messages"]:
            # parse content
            role = message["role"]
            message_content = message.get("content")
            if role in {"tool", "function"}:
                all_contents.append(
                    self._build_function_response(message, message_content)
                )
                continue
            if role == "assistant" and (
                message.get("tool_calls") or message.get("function_call")
            ):
                all_contents.append(self._build_assistant_with_tools(message))
                continue
            parts = self._build_parts_from_content(message_content)
            all_contents.append({"role": role, "parts": parts})

        # separate system instructions
        contents = []
        systemInstruction = {"parts": []}
        for content in all_contents:
            if content["role"] == "system":
                systemInstruction["parts"].extend(content["parts"])
                continue
            if content["role"] == "assistant":
                content["role"] = "model"
            contents.append(content)

        # get thinking budget
        think_config = {"includeThoughts": True}
        if is_gemini_3_series:
            if "gemini-3-flash" in model:
                think_config["thinkingLevel"] = user_valves.reasoning_effort_flash
            elif "gemini-3-pro" in model:
                think_config["thinkingLevel"] = user_valves.reasoning_effort_pro
            else:
                think_config["thinkingLevel"] = user_valves.reasoning_effort_flash
        elif user_valves.thinking_budget >= 0:
            think_config["thinkingBudget"] = user_valves.thinking_budget

        # other parameters
        extra_data = {}
        allowed_params = [k for k in self.valves.allow_params.split(",") if k]
        for key, val in body.items():
            if key in allowed_params:
                extra_data[key] = val

        # init payload
        payload = {
            "method": "POST",
            "url": f"{self.valves.base_url}/{model}:streamGenerateContent?alt=sse",
            "json": {
                **extra_data,
                **(
                    {"systemInstruction": systemInstruction}
                    if systemInstruction["parts"]
                    else {}
                ),
                "contents": contents,
                "generationConfig": {"thinkingConfig": think_config},
            },
        }

        tools_param = body.get("tools", [])
        functions_param = body.get("functions", [])
        gemini_tools = self._convert_tools(tools_param, functions_param)
        tool_choice = body.get("tool_choice") or body.get("function_call")
        tool_config = self._convert_tool_config(tool_choice)
        if gemini_tools and not tool_config:
            tool_config = {"functionCallingConfig": {"mode": "AUTO"}}
        if gemini_tools:
            payload["json"]["tools"] = gemini_tools
        if tool_config:
            payload["json"]["toolConfig"] = tool_config

        return model, payload

    def _build_parts_from_content(self, message_content: Any) -> List[Dict[str, Any]]:
        if message_content is None:
            return []
        if isinstance(message_content, str):
            return [{"text": message_content}]
        if isinstance(message_content, list):
            tmp_content: List[Dict[str, Any]] = []
            for content in message_content:
                if content["type"] == "text":
                    tmp_content.append({"text": content["text"]})
                elif content["type"] == "image_url":
                    image_url = content["image_url"]["url"]
                    header, encoded = image_url.split(",", 1)
                    mime_type = header.split(";")[0].split(":")[1]
                    tmp_content.append(
                        {"inline_data": {"mime_type": mime_type, "data": encoded}}
                    )
                else:
                    raise TypeError("message content invalid")
            return tmp_content
        raise TypeError("message content invalid")

    def _build_assistant_with_tools(self, message: dict) -> dict:
        parts = self._build_parts_from_content(message.get("content"))
        fn_call = message.get("function_call")
        if fn_call:
            args = self._safe_json_loads(fn_call.get("arguments", {}))
            parts.append(
                {
                    "functionCall": {
                        "name": fn_call.get("name", ""),
                        "args": args,
                    }
                }
            )
        for tool_call in message.get("tool_calls", []):
            args = self._safe_json_loads(
                tool_call.get("function", {}).get("arguments", {})
            )
            parts.append(
                {
                    "functionCall": {
                        "name": tool_call.get("function", {}).get("name", ""),
                        "args": args,
                    }
                }
            )
        return {"role": "model", "parts": parts}

    def _build_function_response(
        self, message: dict, message_content: Any
    ) -> Dict[str, Any]:
        function_name = message.get("name") or message.get("tool_call_id") or "function"
        response_body = message_content
        if isinstance(response_body, list):
            texts = [
                content.get("text", "")
                for content in response_body
                if isinstance(content, dict) and content.get("type") == "text"
            ]
            response_body = "".join(texts)
        if isinstance(response_body, str):
            try:
                response_body = json.loads(response_body)
            except Exception:
                response_body = {"content": response_body}
        elif not isinstance(response_body, dict):
            response_body = {"content": response_body}
        return {
            "role": "function",
            "parts": [
                {
                    "functionResponse": {
                        "name": function_name,
                        "response": response_body,
                    }
                }
            ],
        }

    @staticmethod
    def _safe_json_loads(value: Any) -> Any:
        if value is None:
            return {}
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return {"__raw__": value}
        return value

    def _convert_tools(
        self, tools: List[dict], functions: Optional[List[dict]] = None
    ) -> List[dict]:
        if not tools and not functions:
            return []
        function_declarations: List[Dict[str, Any]] = []
        for tool in tools or []:
            if not tool:
                continue
            if tool.get("functionDeclarations"):
                function_declarations.extend(tool.get("functionDeclarations") or [])
                continue
            if tool.get("function_declarations"):
                function_declarations.extend(tool.get("function_declarations") or [])
                continue
            if tool.get("type") == "function" and tool.get("function"):
                fn = tool["function"]
                function_declarations.append(
                    {
                        "name": fn.get("name", ""),
                        "description": fn.get("description", ""),
                        "parameters": fn.get("parameters", {}),
                    }
                )
        for fn in functions or []:
            function_declarations.append(
                {
                    "name": fn.get("name", ""),
                    "description": fn.get("description", ""),
                    "parameters": fn.get("parameters", {}),
                }
            )
        if not function_declarations:
            return []
        return [{"functionDeclarations": function_declarations}]

    def _convert_tool_config(self, tool_choice: Optional[Any]) -> Optional[dict]:
        if not tool_choice:
            return None
        config: Dict[str, Any] = {"functionCallingConfig": {}}
        if isinstance(tool_choice, str):
            mode_map = {"auto": "AUTO", "none": "NONE", "required": "ANY"}
            mode = mode_map.get(tool_choice)
            if not mode:
                return None
            config["functionCallingConfig"]["mode"] = mode
        elif isinstance(tool_choice, dict):
            fn_name = tool_choice.get("function", {}).get("name") or tool_choice.get(
                "name"
            )
            if not fn_name:
                return None
            config["functionCallingConfig"]["mode"] = "ANY"
            config["functionCallingConfig"]["allowedFunctionNames"] = [fn_name]
        else:
            return None
        return config

    def _convert_function_call(
        self, function_call: Dict[str, Any], index: Optional[int] = None
    ) -> Dict[str, Any]:
        args = function_call.get("args", {})
        if isinstance(args, str):
            args_str = args
        else:
            try:
                args_str = json.dumps(args)
            except Exception:
                args_str = str(args)
        data: Dict[str, Any] = {
            "id": f"call_{uuid.uuid4().hex}",
            "type": "function",
            "function": {
                "name": function_call.get("name", ""),
                "arguments": args_str,
            },
        }
        if index is not None:
            data["index"] = index
        return data

    def _format_data(
        self,
        is_stream: bool,
        model: Optional[str] = "",
        content: Optional[str] = "",
        usage: Optional[dict] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        function_call: Optional[Dict[str, Any]] = None,
        finish_reason: Optional[str] = None,
        role: Optional[str] = None,
    ) -> str:
        data: Dict[str, Any] = {
            "id": f"chat.{uuid.uuid4().hex}",
            "object": "chat.completion.chunk",
            "choices": [],
            "created": int(time.time()),
            "model": model,
        }
        if content or tool_calls or finish_reason is not None or role or function_call:
            choice: Dict[str, Any] = {"index": 0}
            if is_stream:
                delta: Dict[str, Any] = {}
                if role:
                    delta["role"] = role
                if content:
                    delta["content"] = content
                if tool_calls:
                    delta["tool_calls"] = tool_calls
                if function_call:
                    delta["function_call"] = function_call
                choice["delta"] = delta
                if finish_reason is not None:
                    choice["finish_reason"] = finish_reason
            else:
                message: Dict[str, Any] = {"role": role or "assistant"}
                if content:
                    message["content"] = content
                if tool_calls:
                    message["tool_calls"] = tool_calls
                if function_call:
                    message["function_call"] = function_call
                choice["message"] = message
                choice["finish_reason"] = finish_reason or "stop"
            data["choices"] = [choice]
        if usage:
            data["usage"] = usage
        return f"data: {json.dumps(data)}\n\n"
