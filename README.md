# 敦煌经书残卷 AI 检索与校对 · Dunhuang Sutra Fragment Retrieval & Collation

## 🌏 项目简介 · Project Overview

**中文**：本项目面向敦煌学 / 佛教文献研究者，使用 Google Gemini 多模态能力，对敦煌经书残卷图片进行 OCR 粗识别，并自动联动 CBETA 与 Gallica（法国国家图书馆）检索，对照写本/刻本文本，给出候选经文、校勘线索与人工校对建议。  
**English**: This project targets researchers of Dunhuang studies and Buddhist texts. It leverages Google Gemini for multimodal OCR on Dunhuang sutra fragments, then cross-checks CBETA and Gallica manuscripts to propose candidate passages, collational hints, and suggestions for human verification.

## ⚡ 快速上手 · Quick Start

1. 克隆仓库 / Clone the repo  
   ```bash
   git clone https://github.com/hzlgames/dunhuang-sutra-fragment-ai-analyzer.git
   cd dunhuang-sutra-fragment-ai-analyzer
   ```
2. 创建虚拟环境并安装依赖 / Create venv & install deps  
   ```bash
   python -m venv venv
   venv\Scripts\activate  # Windows
   pip install -r requirements.txt
   ```
3. 配置 `GOOGLE_API_KEY`（以及可选的 `GEMINI_API_KEY`、`GALLICA_MCP_PATH`），详见下文“配置步骤”。  
4. 批量处理图片 / Batch processing:  
   ```bash
   python -m src.main --input input --output output
   ```
5. 单张验证 / Single image verification:  
   ```bash
   python verify_integration.py
   ```

## 📋 概述（原名：OCR 多渠道使用指南）

系统现在聚焦于 **Google 官方 Gemini API**，通过一个统一的 `CBETAAgent` 完成：
- **OCR 粗识别**（允许标注不确定字符）
- **CBETA 检索与考证**
- **Gallica（法国国家图书馆）敦煌文献检索与对照**

即：优先在 CBETA 中找出处，必要时自动调用 Gallica 作为“敦煌/西域写本分身”，进行多模态比对。

## 🛟 轮次持久化与自动恢复

1. `CBETAAgent` 会在每轮推理结束后，把该轮的 OCR 摘要 + 工具调用记录写入 `sessions/<session_id>.rounds.jsonl`，确保即便 AI 连线中断或你只想复用已有搜索路径，也可以从本地拿出关键线索。
2. `SessionManager` 提供 `load_rounds` 和 `build_round_history_contents`，可以把这些记录转成可直接拼装到 Gemini 上下文中的“历史摘要段”，自动向模型说明前面的思路与调用结果。
3. `resume_with_session(session_id, …)` 入口允许你以已存在的会话 ID 继续思考，只需提供新的 OCR/图片输入，模型会在已有总结的基础上开展下一轮探索；也可以通过 `include_final_output=False` 仅保存中间轮结果而跳过最终 JSON 结构化输出。
4. 配合新加的 `tests/test_round_persistence.py`，确保轮次存档读写与自动恢复逻辑在常规测试环境下可被验证。

## 🔧 配置步骤

### 1. 配置 Google 官方 API

1. 访问 [Google AI Studio](https://aistudio.google.com/app/apikey)
2. 登录您的 Google 账号
3. 点击 "Create API Key" 按钮
4. 复制生成的 API Key
5. 打开 `.env` 文件，将 `GOOGLE_API_KEY` 的值替换为您的 Key

示例：
```
GOOGLE_API_KEY=AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
```

### 2. 配置第三方代理 API (可选)

如果您有 new.12ai.org 的 API Key：

```
GEMINI_API_KEY=sk-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
```

### 3. 配置 Gallica sweet-bnf MCP Server（STDIO）

1. 克隆 sweet-bnf 仓库并安装依赖  
   ```bash
   git clone https://github.com/ukicar/sweet-bnf.git
   cd sweet-bnf
   npm install
   npm run build
   ```
2. 在本项目根目录设置环境变量（可写入 `.env`）：  
   ```
   GALLICA_MCP_PATH=/path/to/sweet-bnf
   NODE_EXECUTABLE=node        # 如需指定 node 全路径可修改
   ```
3. 运行 `CBETAAgent` 时会自动尝试通过 STDIO 启动 MCP；若启动失败会退回旧 `GallicaClient`（requests 实现）。
4. 需要禁用 MCP 时，可在 `AgentConfig` 传入 `gallica_mcp_enabled=False` 或设置环境变量。
5. 调试 MCP 状态可执行 `python src/gallica_mcp.py`，程序会输出当前来源（MCP / fallback）与可用工具列表。

## 🚀 使用方法

### 运行方式：统一 Agent 流程

#### 1. 批量处理图片并生成报告

```bash
python -m src.main --input input --output output
```

- 默认读取 `input/` 下的 PNG/JPG/JPEG 图片，逐张送入 `CBETAAgent`
- 运行过程中会实时打印模型思考、工具调用、文本片段；同时生成 `output/*.jsonl` 流日志
- 每张图片的最终结果落在：
  - `output/<文件名>_result.json`：结构化 JSON（符合 `FinalAnswer` Schema）
  - `output/<文件名>_report.txt`：**人类可读报告**（OCR 摘要 + 候选经文 + 校对提示 + 后续建议）

如需只写日志不上屏，可添加 `--quiet`。

#### 2. 单张验证

使用保留的 `verify_integration.py`：

```bash
python verify_integration.py
```

脚本会拉起同一 `CBETAAgent`，处理 `input/test_fragment.png` 并打印完整 JSON。

## ⚙️ 高级配置

### Gemini 3 配置参数

所有调用都走 `CBETAAgent`，核心配置集中在 `AgentConfig`：

```python
AgentConfig(
    model_name="gemini-3-pro-preview",
    thinking_level="high",   # 可视需要改为 "low"
    max_tool_rounds=5,       # 最多工具调用轮数（不含最终结构化输出轮）
    retry_interval=30,       # API 失败时的重试间隔（秒）
    normal_retries=3,        # 普通轮重试次数
    final_retries=5,         # 最终结构化输出轮重试次数
    verbose=True,            # 控制默认 stdout 流输出
)
```

模型参数遵循 Google 官方推荐：`temperature=1.0`、`max_output_tokens=8192`（在代码中固定），避免随意调整。

## 📊 输出设置

### Google API (Gemini 3)
- **模型**: `gemini-3-pro-preview`
- **最大输出**: 8192 tokens（在 `AgentConfig` 中固定）
- **温度**: 1.0
- **思考级别**: `high` 为默认，可在 `AgentConfig` 调整为 `low`
- **媒体处理**: 直接上传原图，无额外分辨率开关
- **工具调用**: 允许一轮中并行调用多个工具（CBETA + Gallica）

## 📝 输出内容与调试视角

### 完整流程 (`src.main`)

运行：

```bash
python -m src.main --input input --output output
```

每张图片会产出四类与调试 / 整理相关的文件：

1. **流式事件日志**：`output/<文件名>_stream.jsonl`
   - 每行一条 JSON，字段示意：
   - `event`: `thought` / `tool_call` / `tool_result` / `text` / `error`
   - `payload`: 事件具体内容（如调用的工具名、参数、摘要等）
   - 适合用来还原模型多轮 OCR+推理的完整轨迹。

2. **结构化结果**：`output/<文件名>_result.json`
   - 严格符合 `src/schemas.py` 中 `FinalAnswer` 的结构。
   - 核心字段：
     - `ocr_result.recognized_text`: 最终整理的 OCR 文本（允许用 `[?]` 标记不确定字符）
     - `ocr_notes`: **逐列/逐句 OCR 摘要**，解释哪些字不确定、如何判断
     - `scripture_locations`: 经文候选列表及置信度（主要来自 CBETA，也可以包含 Gallica 写本作为“藏卷”对照）
       - 对 CBETA 候选：可设置 `source="CBETA"`，并保证 `work_id` / `canon` / `juan` 等信息完整。
       - 对 Gallica 候选：可设置 `source="Gallica"`，并在 `external_url` 中给出可直接打开的 Gallica 在线阅读链接（如 `https://gallica.bnf.fr/ark:/12148/.../f3.item`）。
     - `key_facts`: 片段关键信息列表，每条一句，**直接从图像与正文可见信息中提取**，包括但不限于：
       - 物质形态：册子本 / 单叶 / 对开叶、叶数、装订方式、首尾及左右上下残损情况等；
       - 题记与尾题：首题、尾题、署名、题记中的时间与人物；
       - 版式与标记：有无科分标题、行数/栏数、朱笔圈点或删除、杂写、插图等。
     - `candidate_insights`: 对候选经文的关键判断与“CBETA vs Gallica”对比结论
     - `verification_points`: 推荐人工校对的要点（疑难字、需查卷/页、Gallica ARK 等）
     - `next_actions`: 给研究者的下一步建议（如“查 T1753 卷2 某页”，“查 Gallica ark:/12148/... f3 页”）
     - `reasoning`: 推理过程文字说明
     - `tools_used`, `search_iterations`, `session_id` 等统计信息。
   - 可作为二次程序处理或导入其他分析管线的基础数据。

3. **可读报告**：`output/<文件名>_report.txt`
   - 为研究者/产品同学准备的**人工校对友好版摘要**，大致结构为：
     - 「OCR 摘要」：整理后的全文 + 不确定字符 + 分列/分句说明
     - 「候选经文（按置信度排序）」：每条列出经号、卷、作译者、片段、置信度及理由
     - 「校对提示」：建议重点核对的文字与位置（含 Gallica 页码/ARK）
     - 「建议的下一步」：如何在 CBETA / Gallica 继续深挖
     - 「推理与工具」：简洁回顾 AI 的推理路径与工具使用统计

4. **附带说明文档**：`output/<文件名>_note.txt`
   - 面向正式研究成果附录的“文献整理说明”草稿，风格参考 `文献整理结果示例.txt`：
     - 首行使用图片文件名（去掉扩展名）作为编号（如 `P.3801`、`Дх.00931`）；
     - 「文献内容：」：基于 `scripture_locations` 与 `key_facts` 列出主要经文信息（经名、经号、译者、CBETA/Gallica 信息、首尾残缺情况等），必要时将 Gallica 写本视作“藏卷”写入；
     - 「物质形态：」：优先复用 `key_facts` 中与装帧/残损相关的条目；如无可用信息，则给出一条占位说明，提示研究者根据原件补充（如“册子本，两张对开叶，首尾俱残”等）；
     - 「参：」部分目前预留给研究者根据实际论文、工具书等手动补充（如张总、党燕妮等研究），模型不会强行自动生成，以免混入不准确引文。
   - 该文件意在为研究者提供一个可直接复制进论文或目录的基础骨架，节省手动誊写时间，但**仍需人工审阅与润色**。

### 单张验证 (`verify_integration.py`)

运行：

```bash
python verify_integration.py
```

该脚本只处理 `input/test_fragment.png`，并在控制台直接打印最终 JSON。  
适合用来确认：
- API Key 是否有效
- 网络、CBETA 接口是否正常
- `CBETAAgent` 能否顺利完成多轮 OCR+搜索+推理。

如需快速检查 Gallica MCP 状态，可运行：
```bash
python src/gallica_mcp.py
```
输出中若出现 “Gallica MCP 已连接” 即表示 STDIO 通道正常；如显示回退模式，请检查 `GALLICA_MCP_PATH` 是否指向 `sweet-bnf`（参考 [sweet-bnf](https://github.com/ukicar/sweet-bnf)）。

## 🔍 故障排查（按优先级）

1. **API Key / 网络**
   - `python diagnose_env.py` 是否通过？
   - 是否可以在浏览器访问 `https://ai.google.dev/`？

2. **Google 模型可用性**
   - `verify_integration.py` 是否能返回 `FinalAnswer`？
   - 错误信息中如包含 403/404/429，请参考 Google 官方文档排查权限与配额。
   - 若出现 `503 UNAVAILABLE` 或 `Server disconnected`，说明 Gemini 模型过载：
     - 稍等 1–2 分钟再试；
     - 或暂时降低 `max_tool_rounds`，减轻压力。

3. **CBETA 接口**
   - `debug_api.py`、`tests.test_cbeta_tools` 是否返回 `status="success"`？
   - 若频繁超时，可尝试减小 `rows` 或检查本机到 `cbdata.dila.edu.tw` 的连通性。

4. **Gallica 接口（敦煌文献）**
   - **优先**测试 MCP：`python src/gallica_mcp.py`，确认可用工具列表是否从 MCP 返回；
   - 若 MCP 启动失败，请检查 Node.js 版本、`sweet-bnf` 目录是否已 `npm run build`，以及 `GALLICA_MCP_PATH` 配置；
   - MCP 不可用时系统会自动回退到旧 `GallicaClient`，可使用 `python src/gallica_client.py` 或 `python debug_gallica.py` 验证 SRU 连通性；
   - 若返回 `status="error"` 且包含 `503`，说明 Gallica 服务器暂时维护或限流，可稍后重试；
   - 若返回“非 XML 响应”，可能触发防爬，可降低并发或增大 `request_interval`。

5. **Agent 逻辑**
   - `tests.test_ai_agent`（文本）通过但 `tests.test_ai_agent_with_image` 失败，多半是图片路径或上传问题。
   - 检查 `FinalAnswer.ocr_result.recognized_text` 是否为空；如为空，先确认图片内容与格式。
   - 核对 `tools_used` 中是否出现 Gallica 相关工具（如 `search_gallica_dunhuang`）；若一直不调用，说明 prompt 或案例不触发，可在 `ocr_text` 中加入明显“敦煌”线索进行测试。

6. **端到端输出**
   - 若 `src.main` 成功运行但 `output/*_result.json` 为空或结构异常，优先查看对应的 `*_stream.jsonl` 中是否有 `error` 事件。
   - 若始终停留在工具调用阶段、最终未生成结构化输出，可能是连续多次 API 503；可以：
     - 先用 `--input` 指向单张图片减少压力；
     - 或临时把 `max_tool_rounds` 调小（如 3）以缩短时间。

## 📦 依赖项

确保已安装所有依赖：

```bash
pip install -r requirements.txt
```

主要依赖：
- `google-genai`: Google GenAI SDK（用于 Gemini 3）
- `requests`: HTTP 请求（CBETA 接口）
- `beautifulsoup4`: HTML 解析（少数 CBETA 返回的 HTML 响应）
- `pillow`: 图片处理
- `python-dotenv`: 环境变量管理
- 外部依赖：`Node.js`（用于运行 sweet-bnf MCP Server）

## ⚠️ 注意事项与最佳实践

1. Google API 通常需要稳定的科学上网环境。
2. 建议优先通过 `diagnose_env.py` → `verify_integration.py` 的顺序调试，避免一开始就跑完整流程。
3. 图片请放置在 `input/` 文件夹，支持 PNG/JPG/JPEG。
4. 若出现 `RemoteProtocolError` 或超时，可在 `AgentConfig` 中把 `thinking_level` 降为 `"low"` 并减少 `max_tool_rounds`。
5. 调试复杂问题时，优先阅读对应的 `*_stream.jsonl`，再结合 `*_result.json` 和 `*_report.txt` 统一定位问题：
   - `thought`：看 AI 如何拆字、分行、选择关键词；
   - `tool_call`：看是否在合适时机调用了 Gallica / CBETA 工具；
   - `tool_result`：快速了解工具返回摘要。
6. 当你在做版本学/敦煌学研究时，建议配合：  
   - CBETA 在线界面（核对段落）  
   - Gallica 在线阅读页（核对写本图像）  
   - 本工具生成的 `*_report.txt`（串联 OCR、候选、校对要点和下一步计划）。
