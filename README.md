# Open-WebUI-Extensions

本仓库收集与维护一组适用于 [Open WebUI](https://github.com/open-webui/open-webui) 的扩展脚本与提示词模板，涵盖：Tools / Filters / Pipes / Prompts。

> 说明：本仓库以“可直接复制到 Open WebUI 工作空间导入”为目标；README 中仅列出当前目录里**实际存在**的脚本与文件，避免出现失效链接。

---

## 核心插件概览

### 搜索与网页内容 (Tools)

- **[Auto-Web-Search (Native)](./Auto-Web-Search/Auto-Web-Search-Native.py)**
  - **描述**：调用 Open WebUI 自带的检索与网页加载能力的“原生搜索/抓取”工具。
  - **核心特性**：支持 `web_search`（多 query）与 `fetch_url_content`（抓取指定 URL）；可通过事件实时输出状态与引用（citation）。
  - **适用场景**：需要让模型检索互联网信息，或读取指定链接正文。

- **[Weather](./Weather/Weather.py)**
  - **描述**：高德天气查询工具。
  - **核心特性**：基于高德开放平台 API；支持实时天气与未来天气预报；内置常用城市 adcode 映射。
  - **数据文件**：[`Weather/AMap_adcode_citycode.xlsx`](./Weather/AMap_adcode_citycode.xlsx)（全国 adcode/citycode 表，可用于扩展映射）。

### 监控与增强 (Filters)

- **[Live-Token](./Live-Token.py)**
  - **描述**：实时 Token / 耗时 / 生成速率统计。
  - **核心特性**：优先使用 API 返回的 `usage`；无 `usage` 时使用 `tiktoken` 估算；支持多模态内容的粗略计数策略。

- **[Deep-Thinking](./Deep-Thinking.py)**
  - **描述**：深度思考模式开启器。
  - **核心特性**：为支持推理/思考字段的模型请求自动注入 `thinking` 配置。

- **[Time-Inject-Filter](./Time-Inject-Filter.py)**
  - **描述**：时间上下文注入。
  - **核心特性**：自动注入当前日期、时间、时区、星期信息；可注入到 system message 或最后一条 user message 前。

### 实用工具 (Tools)

- **[Time-Tool](./Time-Tool.py)**：返回配置时区的当前时间（JSON）。
- **[Calculator](./Calculator.py)**：基于 SymPy 的科学计算器（表达式解析 + 求值）。

### 模型适配 (Pipes)

- **[OpenRouter-Reasoning](./OpenRouter/OpenRouter-Reasoning.py)**
  - **描述**：为 OpenRouter 推理模型提供思考强度控制，并对流式响应中的 reasoning 进行包装处理。

---

## Prompts（提示词模板）

这些模板用于从聊天记录自动生成“追问 / 标签 / 标题”（输出为 JSON）：

- **追问**：[`Prompts/fllow.md`](./Prompts/fllow.md)
- **标签**：[`Prompts/tags.md`](./Prompts/tags.md)
- **标题**：[`Prompts/title.md`](./Prompts/title.md)

---

## 安装与使用

1. **选择脚本**：点击上面的 `.py` 文件链接，复制其源代码。
2. **导入 Open WebUI**：
   - 打开 Open WebUI -> **Workspace (工作空间)**。
   - 根据脚本类型导入：**Tools / Filters / Pipes**（不同版本 UI 文案可能略有差异）。
   - 点击 **Create (+) / Import**，粘贴代码并保存。
3. **配置 Valves (阀门/设置)**：
   - 部分插件需要配置参数（例如 [`Weather/Weather.py`](./Weather/Weather.py) 需要 `AMAP_API_KEY`）。
   - 在插件管理界面点击设置图标，填写对应的 `VALVES`。
4. **依赖说明**：
   - 少量脚本在头部元信息里声明了 `requirements`（例如 [`Live-Token.py`](./Live-Token.py) 需要 `tiktoken`）。
   - 具体安装方式取决于你的 Open WebUI 部署方式（Docker/本地/容器镜像等）。

---

## 贡献

欢迎提交 Issue / Pull Request 来新增扩展或修复问题。

---

**提示**：本仓库由 [@WillLiang713](https://github.com/WillLiang713) 维护。
