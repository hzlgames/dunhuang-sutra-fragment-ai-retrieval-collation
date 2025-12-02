# Gallica MCP 调试与排错指南

本指南独立于主 README，专门用于帮助你部署并调试 **sweet-bnf Gallica MCP Server**，以及在本项目中验证它是否正常工作。  
参考资料：

- MCPworld 说明页：[MCPworld: sweet-bnf 介绍](https://www.mcpworld.com/zh/detail/c5cabea64de985e0d58d1c155c57db3c)
- sweet-bnf 仓库：[ukicar/sweet-bnf](https://github.com/ukicar/sweet-bnf)

---

## 一、环境前提检查

- **操作系统**：Windows（PowerShell）
- **Python 环境**：已能正常运行本项目：

  ```powershell
  cd C:\Users\Lenovo\Desktop\Project_raccoon
  python -m src.main --input input --output output
  ```

- **Node.js 环境**：

  安装 Node.js（建议 18+ LTS），在 PowerShell 中确认：

  ```powershell
  node -v
  npm -v
  ```

  如命令报错，需先安装 Node.js 再继续。

---

## 二、部署 sweet-bnf MCP Server（Node 端）

### 1. 克隆仓库并安装依赖

选择一个你用来放外部项目的目录，例如 `D:\mcp-servers`：

```powershell
cd D:\
mkdir mcp-servers
cd mcp-servers

git clone https://github.com/ukicar/sweet-bnf.git
cd sweet-bnf

npm install
npm run build   # 成功后会生成 dist/index.js
```

构建成功后，应当能看到：

- `package.json`
- `dist\index.js`

### 2. 单独验证 MCP Server 能否启动

在 `sweet-bnf` 目录执行：

```powershell
cd D:\mcp-servers\sweet-bnf
node dist/index.js
```

- 正常情况：进程挂起等待（不立刻退出），表示 MCP Server 正在通过 STDIO 等待客户端连接。
- 如果 **立刻报错或退出**（缺依赖 / Node 版本不兼容 / Gallica 环境缺失等），请先根据错误内容修复，必要时参考：
  - MCPworld 页面：[MCPworld: sweet-bnf 介绍](https://www.mcpworld.com/zh/detail/c5cabea64de985e0d58d1c155c57db3c)
  - sweet-bnf 仓库 README

> 只有当 `node dist/index.js` 能稳定挂起无报错时，Python 端的 MCP 客户端才有可能工作正常。

---

## 三、在 Python 项目中配置 MCP 路径

Python 侧使用 `GallicaMCPClient` 通过 STDIO 调用 sweet-bnf。你只需配置好：

- sweet-bnf 根目录路径
- Node 命令（`node` 或绝对路径）

假设 sweet-bnf 路径为：

```text
D:\mcp-servers\sweet-bnf
```

### 1. 在 `.env` 中配置（推荐）

在本项目根目录（`C:\Users\Lenovo\Desktop\Project_raccoon`）创建或编辑 `.env`，加入：

```ini
# sweet-bnf 根目录
GALLICA_MCP_PATH=D:\mcp-servers\sweet-bnf
# 如需自定义 node 可执行文件路径可改成绝对路径
NODE_EXECUTABLE=node
```

`GallicaMCPClient` 内部的启动逻辑（简化）是：

- 如果存在 `GALLICA_MCP_PATH\dist\index.js`：
  - 执行：`NODE_EXECUTABLE dist/index.js`
- 否则回退执行：`npm run start`

因此只要：

- `GALLICA_MCP_PATH` 指向正确目录；
- `npm run build` 已成功生成 `dist/index.js`；

Python 端就会用 Node 启动 sweet-bnf MCP Server。

### 2. 在 PowerShell 中临时配置（一次性调试）

如果暂时不想改 `.env`，可以在 PowerShell 里临时设置，然后运行调试脚本：

```powershell
cd C:\Users\Lenovo\Desktop\Project_raccoon

$env:GALLICA_MCP_PATH = "D:\mcp-servers\sweet-bnf"
$env:NODE_EXECUTABLE = "node"

python -m src.gallica_mcp
```

关闭当前 PowerShell 窗口后，临时环境变量会消失，适合做一次性验证。

---

## 四、快速健康检查流程

这一节是你每次改完配置后最应该走的一条“快速自检路径”。

### 1. 运行 MCP 调试脚本

在本项目根目录执行：

```powershell
cd C:\Users\Lenovo\Desktop\Project_raccoon
python -m src.gallica_mcp
```

关注输出中的几行关键信息：

#### 1）源模式与可用性

- `ℹ️ GALLICA_MCP_PATH 未配置，使用本地回退`  
  → Python 没读到 `GALLICA_MCP_PATH`，当前在 **本地回退模式**。

- `ℹ️ Gallica MCP 切换至本地回退（启动失败: ...）`  
  → 路径有了，但启动 Node 失败（括号内是原因）。

- `✅ Gallica MCP Server 已启动: D:\mcp-servers\sweet-bnf`  
  → MCP 已成功启动。

- `MCP 可用: False`  
  → 当前仍然走的是本地回退。

- `MCP 可用: True`  
  → Python 已成功连上 sweet-bnf MCP Server。

#### 2）搜索来源与结果字段

在“测试敦煌文献搜索”部分，关注：

- `来源: mcp`  
  → 当前 Gallica 搜索是经由 **sweet-bnf MCP Server** 完成的。

- `来源: fallback`  
  → 当前仍由旧版 `GallicaClient`（requests + SRU）完成搜索。

- `状态: success / error`  
  → 表示工具调用本身是否成功。

- `总记录数: N`  
  → N=0 不一定是错误，可能只是搜索条件太苛刻，需要换关键词验证。

---

## 五、与主流程联动的建议调试顺序

当上面的单独 MCP 自检通过后，建议按下面顺序验证整个 OCR+CBETA+Gallica 流程。

### 步骤 1：基础环境诊断（Google + CBETA）

1. 诊断 Python 和 Google API 环境：

   ```powershell
   python diagnose_env.py
   ```

2. 验证 Gemini + CBETA 联动：

   ```powershell
   python verify_integration.py
   ```

   - 期望返回 `FinalAnswer` JSON；
   - 若只是偶发 503/429，多为 Google 端限流，与 Gallica 无关。

### 步骤 2：单独验证 Gallica MCP / 回退

1. **优先测试 MCP：**

   ```powershell
   python -m src.gallica_mcp
   ```

   目标：看到 `MCP 可用: True` 且 `来源: mcp`。  
   若失败，参考下节“常见问题与对策”。

2. **验证回退客户端（可选）：**

   ```powershell
   python src/gallica_client.py
   python debug_gallica.py
   ```

   用于确认 SRU 接口本身在当前网络下是通的。

### 步骤 3：验证主 Agent 流程中的 Gallica 调用

再运行完整管线，例如：

```powershell
python -m src.main --input input --output output
```

在控制台与 `output/*_stream.jsonl` 中注意：

- `tool_call` 事件里是否出现：
  - `search_gallica` / `search_gallica_dunhuang`
  - 或新增的 `search_gallica_by_title` / `get_gallica_page_text` 等
- `tool_result` 的 `summary` 中，`_source` 字段是 `mcp` 还是 `fallback`。

这可以判断：

- 模型有没有“主动想到要用 Gallica”；
- 实际是通过 MCP 还是回退实现完成的。

---

## 六、常见问题与对策

### 问题 1：`GALLICA_MCP_PATH 未配置`

**现象：**

- 调试脚本输出 `ℹ️ GALLICA_MCP_PATH 未配置，使用本地回退`
- `MCP 可用: False`，`来源: fallback`

**排查：**

1. 确认 `.env` 位于项目根目录，内容类似：

   ```ini
   GALLICA_MCP_PATH=D:\mcp-servers\sweet-bnf
   NODE_EXECUTABLE=node
   ```

2. 使用模块方式运行（会加载 `.env`）：

   ```powershell
   python -m src.gallica_mcp
   ```

3. 在同一 PowerShell 窗口中打印环境变量确认：

   ```powershell
   echo $env:GALLICA_MCP_PATH
   ```

如仍为空，则说明 `.env` 没被正确加载，可考虑在调试脚本中加一行：

```python
from dotenv import load_dotenv
load_dotenv()
```

（当前 `src/main.py` 已有一处 `load_dotenv()`；若直接运行其它脚本，可按需补充。）

### 问题 2：`Gallica MCP 切换至本地回退（启动失败: ...）`

**现象：**

- 输出含 `ℹ️ Gallica MCP 切换至本地回退（启动失败: 某某错误）`
- 表示路径有了，但 Node 进程启动失败或瞬间退出。

**排查路径：**

1. 回到 sweet-bnf 目录，单独启动 MCP：

   ```powershell
   cd D:\mcp-servers\sweet-bnf
   node dist/index.js
   ```

2. 根据终端错误信息逐项修复：
   - 缺包：`npm install` 或根据错误安装额外依赖；
   - Node 版本不符：升级 Node；
   - Gallica 相关环境变量缺失：参考 sweet-bnf README 或 MCPworld 页面补齐。

只要 `node dist/index.js` 能稳定挂住无报错，Python 端连接 MCP 的成功率就会很高。

### 问题 3：`MCP 可用: True`，但搜索结果为 0

**现象：**

- 调试脚本显示 MCP 已连接，`来源: mcp`
- 但 `总记录数: 0` 或结果与你预期不符。

**思路：**

1. 判断是否只是“真的没有数据”：
   - 换成更宽松的关键词进行 `natural_language_search`；
   - 或直接用 sweet-bnf 提供的 `search_by_title` / `search_by_author` 精确测试一个你确信存在的条目。

2. 如怀疑是工具封装/过滤过严：
   - 可在 `GallicaMCPClient` 中增加一个专门调用 `natural_language_search` 的调试方法；
   - 或在 Cursor/Claude 中直接以 MCP 服务器形式注册 sweet-bnf，查看原始 JSON 返回情况。

---

## 七、可复制的完整调试脚本清单

按优先级排列，在出现问题时依次执行：

1. **诊断环境（Google + CBETA）**

   ```powershell
   python diagnose_env.py
   python verify_integration.py
   ```

2. **优先检查 Gallica MCP（Node）**

   ```powershell
   cd D:\mcp-servers\sweet-bnf
   node dist/index.js
   ```

3. **检查 Gallica MCP（Python 客户端）**

   ```powershell
   cd C:\Users\Lenovo\Desktop\Project_raccoon
   python -m src.gallica_mcp
   ```

4. **如需回退模式连通性测试**

   ```powershell
   python src/gallica_client.py
   python debug_gallica.py
   ```

5. **端到端 OCR+CBETA+Gallica 流程**

   ```powershell
   python -m src.main --input input --output output
   ```

---

当你按上述步骤调试时，如果在任意一步遇到新的报错，只要把**完整终端输出**贴回对话，我可以基于这份调试文档继续帮你做更细的定位与修正。


