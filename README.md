# Open-WebUI-Extensions

本仓库致力于收集和开发适用于 [Open WebUI](https://github.com/open-webui/open-webui) 的各类功能强大且实用的扩展（Tools, Filters, Actions, Pipes）。

无论你是想增强搜索能力、监控 Token 消耗，还是适配特定模型，这里都有你需要的工具。

---

## 核心插件概览

### 搜索类 (Tools)

*   **[Auto-Web-Search](./Auto-Web-Search/Auto-Web-Search.py)**
    *   **描述**：全能自动化网页搜索工具。
    *   **核心特性**：支持 Tavily, Exa, Jina 等多种主流搜索引擎；具备网页抓取功能（Firecrawl, Reader 等）；支持状态实时反馈和精美的引用显示。
    *   **适用场景**：需要大模型进行实时、准确的互联网信息检索时。

*   **[Weather](./Weather/Weather.py)**
    *   **描述**：高德天气查询工具。
    *   **核心特性**：基于高德开放平台 API，支持全国城市的实时天气及未来几天天气预报查询。
    *   **适用场景**：日常生活查询、出行规划助手。

### 监控与增强 (Filters)

*   **[Live-Token](./Live-Token.py)**
    *   **描述**：实时 Token 追踪器。
    *   **核心特性**：在聊天界面实时显示输入/输出 Token 数量、响应耗时、生成速率 (T/s)。
    *   **适用场景**：成本控制、性能调优、多模态内容 Token 估算。

*   **[Deep-Thinking](./Deep-Thinking.py)**
    *   **描述**：深度思考模式开启器。
    *   **核心特性**：为支持思索/推理功能的模型自动注入 `thinking` 字段，一键开启深度思考。

*   **[Time-Inject-Filter](./Time-Inject-Filter.py)**
    *   **描述**：时间上下文注入。
    *   **核心特性**：自动将当前精确的日期、时间、时区、星期信息注入系统提示词或用户消息中，让模型“知道今夕是何年”。

### 实用工具 (Tools & Others)

*   **[Time-Tool](./Time-Tool.py)**：支持时区的时间查询工具，供模型主动调用。
*   **[Calculator](./calculator.py)**：基于 SymPy 的安全科学计算器，解决大模型常有的“算术难”问题。
*   **[Max-Turns-Limit](./max_turns_limit.py)**：对话轮数限制器。通过强制限制对话次数，有效避免长上下文带来的性能下降 and Token 浪费。

### 模型适配 (Pipes & Actions)

*   **[Gemini-Adapter](./Gemini-Adapter)**
    *   针对 Google Gemini 系列模型深度优化，提供包括聊天适配、网页搜索增强、URL 上下文传递等功能。

*   **[Claude-Messages](./Claude/Claude-Message.py)**
    *   Claude API Pipe，支持思考模式、图片输入、Beta 工具（代码执行/网页抓取）。

*   **[OpenAI-Responses](./OpenAI/OpenAI-Responses.py)**
    *   OpenAI Realtime 适配插件。

*   **[OpenRouter-Reasoning](./OpenRouter/OpenRouter-Reasoning.py)**
    *   为 OpenRouter 的 GPT-5 / Gemini 3 系列推理模型提供思考强度控制。

---

## 安装与使用

1.  **下载代码**：点击对应的 `.py` 文件，复制其源代码。
2.  **导入 Open WebUI**：
    *   前往 Open WebUI 界面 -> **Workspace (工作空间)** -> **Functions (函数)** 或 **Tools (工具)**。
    *   点击 **Create (+) / Import**。
    *   粘贴代码并保存。
3.  **配置 Valves (阀门/设置)**：
    *   许多插件（如搜索和天气）需要配置 API Key。
    *   在插件管理界面，点击对应插件的设置图标，填写所需的 `VALVES` 配置。

---

## 开发者指南

如果你有新的想法或发现了 Bug，欢迎提交 Issue 或 Pull Request！

### 环境建议
建议使用 `uv` 进行依赖管理（仓库已包含 `pyproject.toml` 和 `uv.lock`）。

```bash
uv sync
```

---

**提示**：本仓库由 [@WillLiang713](https://github.com/WillLiang713) 维护。如有疑问，欢迎通过 GitHub 互动。
