# 敦煌经书残卷 AI 检索与校对

## 🌏 项目定位

本项目提供一套 **HTTP 后端服务 + 桌面客户端**，用于：

- 接收敦煌经书残卷图片；
- 调用 Google Gemini 多模态模型完成 OCR 粗识别；
- 联动 CBETA、Gallica 等工具完成经文检索与推理；
- 返回结构化 JSON 结果与人类可读报告。

> 本 README 包含**普通用户快速上手**和**开发者接口文档**两部分。

---

## 🎯 普通用户快速上手（Windows）

只需 3 步即可开始使用：

### 第一步：配置环境

1. 确保已安装 **Python 3.10+**（[下载地址](https://www.python.org/downloads/)）
2. 在项目根目录创建 `.env` 文件，填入以下内容：

```env
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_APPLICATION_CREDENTIALS=service-account-key.json
```

> 详细配置说明见下方"配置环境变量"章节。

### 第一步：安装 Gallica MCP 服务

如需使用法国国家图书馆（Gallica）的高级检索功能：

1. 确保已安装 **Node.js**（[下载地址](https://nodejs.org/)）
2. 双击 `setup_mcp.bat`，自动安装 [sweet-bnf](https://github.com/ukicar/sweet-bnf) MCP 服务器


### 第二步：启动后端服务

双击 `run_server.bat`，等待出现 `Uvicorn running on http://127.0.0.1:8000`

### 第三步：启动桌面客户端

双击 `run_client.bat`，打开图形界面

### 使用方法

1. 点击 **"选择图片"** 添加要分析的残卷图片
2. 如有多张图片，可勾选 **"批处理模式"** 一次性提交
3. 等待任务完成，在列表中查看状态
4. 点击 **"打开目录"** 查看生成的结果文件

### 功能特性

- **多图并发上传**：支持同时处理多张图片
- **批处理模式**：多张图片合并为一个任务，节省 API 配额
- **断点续传**：失败任务可随时重试，自动恢复进度
- **停止与恢复**：可随时停止正在进行的任务，下次继续
- **结果可视化**：直接查看 AI 识别结果和推理过程

---

## ⚙️ 核心技术栈

- **运行环境**：Python 3.10+
- **Web 框架**：FastAPI + Uvicorn
- **LLM 客户端**：`google-genai`（Gemini API）
- **外部服务**：
  - Google Gemini 3 / Gemini 2.5 Batch API
  - CBETA 检索接口
  - Gallica（法国国家图书馆）及 sweet-bnf MCP Server

---

## 🚀 快速启动后端服务

### 1. 安装依赖

```bash
cd YOUR_PATH
pip install -r requirements.txt
```

### 2. 配置环境变量（.env，Vertex AI 模式）

> 项目现在默认通过 **Vertex AI + Service Account** 调用 Gemini 模型，  
> 详细背景与步骤可参考 `docs/vertex_directions.md`。

在项目根目录创建或编辑 `.env`（示例）：

```env
# 1. GCP 项目与区域
GOOGLE_CLOUD_PROJECT=your-gcp-project-id       # 必填：标准 GCP 项目 ID（不要用 gen-lang-client-*）
GOOGLE_CLOUD_LOCATION=global                   # 建议保持 global，否则无法使用Gemini3Pro

# 2. 认证凭据（Service Account JSON）
#   - 在 GCP 控制台为 Vertex AI 创建服务账号
#   - 下载 JSON 密钥文件放到项目根目录，例如 service-account-key.json
#   - 确保该文件已加入 .gitignore，避免提交到 Git
GOOGLE_APPLICATION_CREDENTIALS=service-account-key.json

# 3. Batch API 输入/输出桶（仅批处理需要）
VERTEX_BATCH_BUCKET=xxx

# 4. 其他可选配置
OUTPUT_DIR=output                              # 可选，结果输出目录，默认为 output
GALLICA_MCP_PATH=D:\mcp-servers\sweet-bnf      # 可选，Gallica MCP 路径
NODE_EXECUTABLE=node                           # 可选，Node 可执行路径
```

> 说明：旧版使用的 `GOOGLE_API_KEY` / `GEMINI_API_KEY` 仅适用于 Google AI Studio 直连模式，  
> 当前代码路径已经切换为 Vertex AI，**不再依赖 API Key**。

> 若需了解 Vertex Batch API 的输入/输出格式，可阅读 `docs/vertex_batch.md`。

### 3. 启动 FastAPI 服务

```bash
python -m uvicorn src.api.server:app --host 0.0.0.0 --port 8000 --reload
```

- 默认访问地址：`http://127.0.0.1:8000`
- 跨域已开放：前端可直接在浏览器中调用。

---

## 🧩 前后端交互总览

典型交互流程（前端视角）：

1. **前端上传图片** → 调用 `/api/v1/jobs/image` 得到 `task_id`；
2. **前端轮询任务状态** → 调用 `/api/v1/jobs/{task_id}`，直到 `status="SUCCEEDED"` 或 `FAILED`；
3. **前端展示结果** → 从 `result` 中读取结构化 JSON 展示；  
   如需“AI 思考过程”，调用 `/api/v1/jobs/{task_id}/process` 获取多轮摘要与工具调用；
4. **批量处理场景** → 前端用 `/api/v1/batches` 上传多张图片，再用 `/api/v1/batches/{batch_id}` 与 `/api/v1/batches/{batch_id}/results` 管理整批任务。

前端只需要处理少量状态枚举与几个固定字段，即可完成完整集成。

---

## 📡 HTTP 接口一览

### 1. 单图异步任务接口

#### 1.1 提交任务：`POST /api/v1/jobs/image`

- **用途**：上传单张图片，异步处理。
- **请求**（`multipart/form-data`）：

```bash
curl.exe -X POST "http://127.0.0.1:8000/api/v1/jobs/image" ^
  -F "file=@input\test0.png"
```

- **响应**：

```json
{ "task_id": "8ddce779-b081-4727-8c5d-8429dc68b5f1" }
```

前端需要缓存该 `task_id`，用于后续轮询。

#### 1.2 查询任务状态：`GET /api/v1/jobs/{task_id}`

```bash
curl.exe "http://127.0.0.1:8000/api/v1/jobs/8ddce779-b081-4727-8c5d-8429dc68b5f1"
```

返回示例（进行中）：

```json
{
  "task_id": "...",
  "status": "RUNNING",
  "created_at": "...",
  "updated_at": "...",
  "result": null,
  "error": null
}
```

状态枚举（前端可直接按字符串处理）：

- `PENDING`：任务已创建，未开始；
- `RUNNING`：正在处理；
- `SUCCEEDED`：成功完成，`result` 为完整 JSON；
- `FAILED`：失败，`error` 含错误信息；
- `CANCELLED`：已取消（可断点续传）。

当 `status="SUCCEEDED"` 时：

```json
{
  "task_id": "...",
  "status": "SUCCEEDED",
  "result": {
    // FinalAnswer 结构（见下文“结果结构”）
  },
  "error": null
}
```

### 2. 批量任务接口

#### 2.1 创建批处理：`POST /api/v1/batches`

- **用途**：一次上传多张图片，后端内部通过 Gemini Batch API 并行多轮处理。
- **请求**：

```bash
curl.exe -X POST "http://127.0.0.1:8000/api/v1/batches" ^
  -F "files=@input\test0.png" ^
  -F "files=@input\temp\test_fragment1.png"
```

- **响应**：

```json
{ "batch_id": "d9a4d4e3-25b0-404b-a13e-38ad2a54ecc5" }
```

#### 2.2 查询批处理状态：`GET /api/v1/batches/{batch_id}`

```bash
curl.exe "http://127.0.0.1:8000/api/v1/batches/d9a4d4e3-25b0-404b-a13e-38ad2a54ecc5"
```

返回示例：

```json
{
  "batch_id": "d9a4d4e3-25b0-404b-a13e-38ad2a54ecc5",
  "status": "BATCH_RUNNING",
  "round": 1,
  "total_jobs": 2,
  "completed_jobs": 0,
  "failed_jobs": 0,
  "details": [
    {
      "session_id": "...",
      "alias": "test0_xxxxxxxx",
      "done": false,
      "error": null,
      "last_round": 0
    }
  ]
}
```

前端可用 `completed_jobs/total_jobs` 展示进度条，用 `details[*].alias` 做每张图片的标识。

#### 2.3 获取批处理结果：`GET /api/v1/batches/{batch_id}/results`

```bash
curl.exe "http://127.0.0.1:8000/api/v1/batches/d9a4d4e3-25b0-404b-a13e-38ad2a54ecc5/results"
```

返回示例：

```json
{
  "batch_id": "d9a4d4e3-25b0-404b-a13e-38ad2a54ecc5",
  "items": [
    {
      "session_id": "...",
      "status": "SUCCEEDED",
      "result": { /* FinalAnswer */ },
      "error": null
    },
    {
      "session_id": "...",
      "status": "FAILED",
      "result": null,
      "error": "详细错误信息"
    }
  ]
}
```

如需只看某个 `session_id`：

```bash
curl.exe "http://127.0.0.1:8000/api/v1/batches/{batch_id}/results?session_id=<id>"
```

### 3. 查看 AI 多轮思考与工具调用过程

#### 3.1 通过 `session_id` 查询：`GET /api/v1/process/{session_id}`

```bash
curl.exe "http://127.0.0.1:8000/api/v1/process/<session_id>"
```

返回 `ProcessResponse`，包含：

- `total_rounds`：轮次数；
- `rounds[*].round_index`：轮次编号；
- `rounds[*].summary`：本轮 AI 思考摘要；
- `rounds[*].tool_calls`：本轮调用的工具（CBETA / Gallica 等）。

前端可以用这个接口绘制“AI 推理时间线”。

#### 3.2 通过 `task_id` 查询：`GET /api/v1/jobs/{task_id}/process`

单图任务场景下，前端无需管理 `session_id`，只要用 `task_id` 即可。

### 4. 任务控制接口

#### 4.1 取消任务：`POST /api/v1/jobs/{task_id}/cancel`

```bash
curl.exe -X POST "http://127.0.0.1:8000/api/v1/jobs/{task_id}/cancel"
```

返回示例：

```json
{
  "task_id": "...",
  "status": "CANCELLED",
  "message": "取消请求已发送，任务将在下一个检查点停止"
}
```

#### 4.2 断点续传：`POST /api/v1/jobs/resume`

基于已有的 `session_id` 继续处理，需要重新上传图片：

```bash
curl.exe -X POST "http://127.0.0.1:8000/api/v1/jobs/resume?session_id=<session_id>" ^
  -F "file=@input\test0.png"
```

返回示例：

```json
{
  "task_id": "新任务ID",
  "session_id": "复用的session_id"
}
```

### 5. 元信息接口

#### 5.1 获取服务信息：`GET /api/v1/meta`

```bash
curl.exe "http://127.0.0.1:8000/api/v1/meta"
```

返回示例：

```json
{
  "version": "1.0.0",
  "output_dir": "C:\\Users\\xxx\\Project_raccoon\\output",
  "supports_batch": true
}
```

---

## 📦 结果结构（FinalAnswer 概览）

服务端返回的 `result` 字段，遵循 `src/schemas.py` 中的 `FinalAnswer` 模型。关键字段包括：

- `ocr_result.recognized_text`：整理后的 OCR 文本（不确定字符用 `[?]` 标记）；
- `ocr_notes[]`：逐列/逐句 OCR 摘要；
- `scripture_locations[]`：经文候选列表，每条包含：
  - `source`：`"CBETA"` / `"Gallica"`；
  - `work_id`、`canon`、`juan` 等（CBETA）；
  - `external_url`（如 Gallica ark 链接）；
  - `confidence`：置信度；
- `key_facts[]`：关于碎片物质形态、版式、题记等要点；
- `candidate_insights[]`：对候选经文的判断与版本学提示；
- `verification_points[]`：推荐人工核对要点；
- `next_actions[]`：下一步建议（CBETA 卷页、Gallica ARK 等）；
- `reasoning`：整体推理说明；
- `session_id`、`tools_used`、`search_iterations` 等元数据。

前端通常只需选取一部分字段做展示，如：

- 识别文本 + 重要不确定字；
- 1–3 条最高置信度的 `scripture_locations`；
- 部分 `key_facts` 与 `verification_points`。

---

## 🧱 与前端集成建议

- **上传策略**：
  - 单图：直接调用 `/api/v1/jobs/image`；
  - 多图：优先使用 `/api/v1/batches`，避免前端并发压垮 Gemini。
- **轮询间隔**：
  - 单任务：每 3–5 秒轮询 `/jobs/{task_id}`；
  - 批量：每 8–15 秒轮询 `/batches/{batch_id}`。
- **失败重试**：
  - 若 `status="FAILED"` 且 `error` 包含网络/配额类提示，可在前端允许用户“一键重试”（重新提交任务）。
- **展示思考过程**：
  - 可选地调用 `/jobs/{task_id}/process` 或 `/process/{session_id}`，按 `round_index` 时间顺序展示 AI 如何逐步缩小候选范围、调用哪些工具。

---

## 🖥️ 本地批处理（离线 CLI）

除了 HTTP 接口，本项目保留了一个命令行入口，方便研究者直接在本机批量处理图片：

```bash
python -m src.main --input input --output output
```

- 自动扫描 `input/` 下的 PNG/JPG/JPEG；
- 为每张图片生成：
  - `output/<文件名>_result.json`
  - `output/<文件名>_report.txt`
  - `output/<文件名>_note.txt`
  - `sessions/<session_id>.rounds.jsonl`

---

## 🔍 调试与故障排查文档

所有更细致的调试说明、脚本示例与排错流程已集中到 `docs/debug/` 目录，包括但不限于：

- 环境诊断与 API Key 检查；
- 单图 `CBETAAgent` 行为验证；
- FastAPI / Batch API 调试步骤；
- 常见错误（429/503/超时、CBETA/Gallica 连接问题）及处理思路。

如需深入排查问题，建议从以下文档开始：

- `docs/debug/环境与接口调试.md`
- `docs/debug/BatchAPI 调试指南.md`

> 如果这些文件尚未创建，你可以将现有的 `快速测试指南.md`、`调试FastAPI接口+BatchAPI.md` 等文档移动/整理到 `docs/debug/` 下，并按需要补充索引。


