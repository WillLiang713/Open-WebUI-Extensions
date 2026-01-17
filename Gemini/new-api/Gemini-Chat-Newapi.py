"""
title: Gemini Chat
description: Text generation with Gemini
author: OVINC CN
git_url: https://github.com/OVINC-CN/OpenWebUIPlugin.git
version: 0.0.8
licence: MIT
"""

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterable, Dict, List, Literal, Optional, Tuple

import httpx
from fastapi import Request
from open_webui.env import GLOBAL_LOG_LEVEL
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

logger = logging.getLogger(__name__)
logger.setLevel(GLOBAL_LOG_LEVEL)


# ============================================================================
# 状态管理
# ============================================================================

@dataclass
class StreamState:
    """流式处理状态管理"""
    model: str = ""
    is_thinking: bool = True
    tool_call_index: int = 0
    total_tool_calls: int = 0
    buffer: str = ""

    def close_thinking(self) -> bool:
        """关闭思考状态，返回是否需要输出关闭标签"""
        if self.is_thinking:
            self.is_thinking = False
            return True
        return False


# ============================================================================
# 主类
# ============================================================================

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

    # ========================================================================
    # 入口方法
    # ========================================================================

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
        state = StreamState(model=model)

        try:
            async with httpx.AsyncClient(
                headers={"x-goog-api-key": self.valves.api_key},
                proxy=self.valves.proxy or None,
                trust_env=True,
                timeout=self.valves.timeout,
            ) as client:
                async with client.stream(**payload) as response:
                    if response.status_code != 200:
                        async for chunk in self._handle_error_response(response):
                            yield chunk
                        return

                    # 开始思考块
                    yield self._format_data(is_stream=True, model=model, content="<think>")

                    async for raw_line in response.aiter_lines():
                        parsed = self._parse_sse_line(raw_line, state)
                        if parsed is None:
                            continue

                        async for chunk in self._process_candidates(parsed, state):
                            yield chunk

                    # 确保关闭思考块
                    if state.is_thinking:
                        yield self._close_thinking_block(state)

        except Exception as err:
            logger.exception("[GeminiChatPipe] failed of %s", err)
            yield self._format_data(is_stream=False, content=str(err))

    # ========================================================================
    # 流式处理辅助方法
    # ========================================================================

    async def _handle_error_response(self, response) -> AsyncIterable[str]:
        """处理错误响应"""
        text = ""
        async for line in response.aiter_lines():
            text += line
        logger.error("response invalid with %d: %s", response.status_code, text)
        response.raise_for_status()
        # 使用 if False 让这成为一个 async generator
        if False:
            yield ""

    def _parse_sse_line(self, raw_line: str, state: StreamState) -> Optional[dict]:
        """解析 SSE 行，返回解析后的 JSON 对象或 None"""
        line = raw_line.strip()

        if not line:
            if state.buffer:
                try:
                    result = json.loads(state.buffer)
                    state.buffer = ""
                    return result
                except json.JSONDecodeError:
                    state.buffer = ""
            return None

        if line.startswith("event:") or not line.startswith("data:"):
            return None

        data_line = line[5:].lstrip()
        if data_line == "[DONE]":
            return None

        state.buffer += data_line
        try:
            result = json.loads(state.buffer)
            state.buffer = ""
            return result
        except json.JSONDecodeError:
            return None

    async def _process_candidates(
        self, data: dict, state: StreamState
    ) -> AsyncIterable[str]:
        """处理候选结果"""
        for item in data.get("candidates", []):
            content = item.get("content", {})
            if not content:
                yield self._format_data(
                    is_stream=True,
                    model=state.model,
                    finish_reason=item.get("finishReason", ""),
                )
                continue

            parts = content.get("parts", [])
            if not parts:
                yield self._format_data(
                    is_stream=True,
                    model=state.model,
                    finish_reason=item.get("finishReason", ""),
                )
                continue

            async for chunk in self._process_parts(parts, state):
                yield chunk

    async def _process_parts(
        self, parts: List[dict], state: StreamState
    ) -> AsyncIterable[str]:
        """处理消息的各个部分"""
        tool_calls: List[Dict[str, Any]] = []

        for part in parts:
            # 处理思考内容
            if part.get("thought", False):
                if state.is_thinking:
                    thought_text = part.get("text", "")
                    if thought_text:
                        yield self._format_data(
                            is_stream=True, model=state.model, content=thought_text
                        )
                continue

            # 处理函数调用
            func_call = part.get("functionCall") or part.get("function_call")
            if func_call:
                if state.close_thinking():
                    yield self._close_thinking_block(state)
                tool_calls.append(
                    self._convert_function_call(func_call, index=state.tool_call_index)
                )
                state.tool_call_index += 1
                continue

            # 处理正文和代码执行
            text = part.get("text")
            has_code = part.get("executableCode") or part.get("codeExecutionResult")

            if text or has_code:
                if state.close_thinking():
                    yield self._close_thinking_block(state)

            if text:
                yield self._format_data(is_stream=True, model=state.model, content=text)

            # 处理代码执行事件
            if part.get("executableCode"):
                yield self._format_code_event(
                    f"executableCode {part['executableCode'].get('language', '')}",
                    done=False,
                )
            if part.get("codeExecutionResult"):
                yield self._format_code_event(
                    f"codeExecutionResult {part['codeExecutionResult'].get('outcome', '')}",
                    done=True,
                )

        # 输出工具调用结果
        if tool_calls:
            state.total_tool_calls += len(tool_calls)
            legacy_fn_call = (
                tool_calls[0]["function"]
                if state.total_tool_calls == 1 and len(tool_calls) == 1
                else None
            )
            yield self._format_data(
                is_stream=True,
                model=state.model,
                tool_calls=tool_calls,
                function_call=legacy_fn_call,
                finish_reason="tool_calls",
                role="assistant",
            )

    def _close_thinking_block(self, state: StreamState) -> str:
        """生成关闭思考块的数据"""
        return self._format_data(is_stream=True, model=state.model, content="</think>")

    def _format_code_event(self, description: str, done: bool) -> str:
        """格式化代码执行事件"""
        data = {
            "event": {
                "type": "status",
                "data": {"description": description, "done": done},
            }
        }
        return f"data: {json.dumps(data)}\n\n"

    # ========================================================================
    # Payload 构建
    # ========================================================================

    async def _build_payload(
        self, body: dict, user_valves: UserValves
    ) -> Tuple[str, dict]:
        model = body["model"].split(".", 1)[1]
        contents, system_instruction = self._build_contents(body["messages"])
        think_config = self._build_think_config(model, user_valves)
        extra_data = self._build_extra_params(body)

        payload = {
            "method": "POST",
            "url": f"{self.valves.base_url}/{model}:streamGenerateContent?alt=sse",
            "json": {
                **extra_data,
                **({"systemInstruction": system_instruction} if system_instruction["parts"] else {}),
                "contents": contents,
                "generationConfig": {"thinkingConfig": think_config},
            },
        }

        self._add_tools_to_payload(payload, body)
        return model, payload

    def _build_contents(self, messages: List[dict]) -> Tuple[List[dict], dict]:
        """构建消息内容和系统指令"""
        all_contents = []
        for message in messages:
            role = message["role"]
            message_content = message.get("content")

            if role in {"tool", "function"}:
                all_contents.append(self._build_function_response(message, message_content))
            elif role == "assistant" and (message.get("tool_calls") or message.get("function_call")):
                all_contents.append(self._build_assistant_with_tools(message))
            else:
                parts = self._build_parts_from_content(message_content)
                all_contents.append({"role": role, "parts": parts})

        # 分离系统指令
        contents = []
        system_instruction = {"parts": []}
        for content in all_contents:
            if content["role"] == "system":
                system_instruction["parts"].extend(content["parts"])
            else:
                if content["role"] == "assistant":
                    content["role"] = "model"
                contents.append(content)

        return contents, system_instruction

    def _build_think_config(self, model: str, user_valves: UserValves) -> dict:
        """构建思考配置"""
        config = {"includeThoughts": True}

        if "gemini-3" in model:
            if "gemini-3-flash" in model:
                config["thinkingLevel"] = user_valves.reasoning_effort_flash
            elif "gemini-3-pro" in model:
                config["thinkingLevel"] = user_valves.reasoning_effort_pro
            else:
                config["thinkingLevel"] = user_valves.reasoning_effort_flash
        elif user_valves.thinking_budget >= 0:
            config["thinkingBudget"] = user_valves.thinking_budget

        return config

    def _build_extra_params(self, body: dict) -> dict:
        """构建额外参数"""
        allowed_params = [k for k in self.valves.allow_params.split(",") if k]
        return {key: val for key, val in body.items() if key in allowed_params}

    def _add_tools_to_payload(self, payload: dict, body: dict) -> None:
        """添加工具配置到 payload"""
        tools_param = list(body.get("tools") or [])
        functions_param = body.get("functions", [])
        gemini_tools = self._convert_tools(tools_param, functions_param)

        has_google_search = any(
            isinstance(tool, dict) and "googleSearch" in tool for tool in gemini_tools
        )
        has_function_decls = any(
            isinstance(tool, dict) and "functionDeclarations" in tool for tool in gemini_tools
        )

        # Google Search 与函数声明互斥，优先使用 Google Search
        if has_google_search and has_function_decls:
            gemini_tools = [tool for tool in gemini_tools if "googleSearch" in tool]
            has_function_decls = False

        tool_choice = body.get("tool_choice") or body.get("function_call")
        tool_config = self._convert_tool_config(tool_choice) if has_function_decls else None

        if has_function_decls and not tool_config:
            tool_config = {"functionCallingConfig": {"mode": "AUTO"}}

        if gemini_tools:
            payload["json"]["tools"] = gemini_tools
        if tool_config:
            payload["json"]["toolConfig"] = tool_config

    # ========================================================================
    # 消息构建
    # ========================================================================

    def _build_parts_from_content(self, message_content: Any) -> List[Dict[str, Any]]:
        """从消息内容构建 parts"""
        if message_content is None:
            return []
        if isinstance(message_content, str):
            return [{"text": message_content}]
        if isinstance(message_content, list):
            parts: List[Dict[str, Any]] = []
            for content in message_content:
                if content["type"] == "text":
                    parts.append({"text": content["text"]})
                elif content["type"] == "image_url":
                    image_url = content["image_url"]["url"]
                    header, encoded = image_url.split(",", 1)
                    mime_type = header.split(";")[0].split(":")[1]
                    parts.append({"inline_data": {"mime_type": mime_type, "data": encoded}})
                else:
                    raise TypeError("message content invalid")
            return parts
        raise TypeError("message content invalid")

    def _build_assistant_with_tools(self, message: dict) -> dict:
        """构建带工具调用的助手消息"""
        parts = self._build_parts_from_content(message.get("content"))

        fn_call = message.get("function_call")
        if fn_call:
            args = self._safe_json_loads(fn_call.get("arguments", {}))
            parts.append({"functionCall": {"name": fn_call.get("name", ""), "args": args}})

        for tool_call in message.get("tool_calls", []):
            args = self._safe_json_loads(tool_call.get("function", {}).get("arguments", {}))
            parts.append({
                "functionCall": {
                    "name": tool_call.get("function", {}).get("name", ""),
                    "args": args,
                }
            })

        return {"role": "model", "parts": parts}

    def _build_function_response(self, message: dict, message_content: Any) -> Dict[str, Any]:
        """构建函数响应"""
        function_name = message.get("name") or message.get("tool_call_id") or "function"
        response_body = self._normalize_function_response(message_content)

        return {
            "role": "function",
            "parts": [{"functionResponse": {"name": function_name, "response": response_body}}],
        }

    def _normalize_function_response(self, response_body: Any) -> dict:
        """标准化函数响应体"""
        if isinstance(response_body, list):
            texts = [
                content.get("text", "")
                for content in response_body
                if isinstance(content, dict) and content.get("type") == "text"
            ]
            response_body = "".join(texts)

        if isinstance(response_body, str):
            try:
                return json.loads(response_body)
            except Exception:
                return {"content": response_body}

        if not isinstance(response_body, dict):
            return {"content": response_body}

        return response_body

    # ========================================================================
    # 工具转换
    # ========================================================================

    @staticmethod
    def _safe_json_loads(value: Any) -> Any:
        """安全解析 JSON"""
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
        """转换工具列表为 Gemini 格式"""
        if not tools and not functions:
            return []

        results: List[Dict[str, Any]] = []
        function_declarations: List[Dict[str, Any]] = []

        for tool in tools or []:
            if not tool:
                continue

            # Google Search
            if tool.get("googleSearch") is not None or tool.get("google_search") is not None:
                search_config = tool.get("googleSearch") or tool.get("google_search")
                results.append({"googleSearch": search_config or {}})
                continue

            # 已有函数声明
            decls = tool.get("functionDeclarations") or tool.get("function_declarations")
            if decls:
                function_declarations.extend(decls)
                continue

            # OpenAI 格式的函数
            if tool.get("type") == "function" and tool.get("function"):
                function_declarations.append(self._build_function_declaration(tool["function"]))

        # 处理独立的 functions 参数
        for fn in functions or []:
            function_declarations.append(self._build_function_declaration(fn))

        if function_declarations:
            results.append({"functionDeclarations": function_declarations})

        return results

    def _build_function_declaration(self, fn: dict) -> dict:
        """构建函数声明"""
        return {
            "name": fn.get("name", ""),
            "description": fn.get("description", ""),
            "parameters": fn.get("parameters", {}),
        }

    def _convert_tool_config(self, tool_choice: Optional[Any]) -> Optional[dict]:
        """转换工具配置"""
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
            fn_name = tool_choice.get("function", {}).get("name") or tool_choice.get("name")
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
        """转换函数调用为 OpenAI 格式"""
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

    # ========================================================================
    # 输出格式化
    # ========================================================================

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
        """格式化为 OpenAI 兼容的 SSE 数据"""
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
