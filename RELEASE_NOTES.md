# Release v1.0.0 - 敦煌经书残卷 AI 检索与校对系统

##  首次发布

本项目提供完整的敦煌经书残卷AI检索与校对解决方案，包含桌面客户端和HTTP后端服务。

##  主要功能

- **桌面客户端**：Windows图形界面，支持拖拽上传、批处理、进度实时显示
- **OCR识别**：基于Google Gemini多模态模型的高精度文字识别
- **经文检索**：集成CBETA（中华电子佛典协会）和Gallica（法国国家图书馆）检索
- **批处理模式**：支持多图并行处理，自动管理API配额
- **断点续传**：任务失败可随时恢复，保留处理进度
- **一键启动**：提供Windows批处理脚本，无需手动配置

##  快速开始

### 环境要求

- Python 3.10+
- Google Cloud Platform账号（需开通Vertex AI）
- （可选）Node.js（使用Gallica检索功能时需要）

### 安装步骤

1. **克隆仓库**
\\\ash
git clone https://github.com/hzlgames/dunhuang-sutra-fragment-ai-retrieval-collation.git
cd dunhuang-sutra-fragment-ai-retrieval-collation
\\\

2. **安装依赖**
\\\ash
pip install -r requirements.txt
\\\

3. **配置环境变量**
   - 复制 \.env.example\ 为 \.env\
   - 填入您的GCP项目信息
   - 下载Service Account密钥文件到项目根目录

4. **（可选）安装Gallica MCP服务**
\\\ash
setup_mcp.bat
\\\

5. **启动服务**
   - 双击 \un_server.bat\ 启动后端
   - 双击 \un_client.bat\ 启动客户端

详细说明请参考 [README.md](README.md)

##  技术栈

- **后端**：FastAPI + Uvicorn
- **AI模型**：Google Gemini 3 Pro / 2.5 Pro (Vertex AI)
- **客户端**：Python Tkinter
- **外部服务**：CBETA API、Gallica (sweet-bnf MCP)

##  完整文件清单

### 核心源代码
- \src/ai_agent.py\ - AI Agent核心逻辑
- \src/batch_jobs.py\ - 批处理任务管理
- \src/api/server.py\ - FastAPI服务端
- \src/cbeta_tools.py\ - CBETA检索工具
- \src/gallica_mcp.py\ - Gallica MCP客户端

### 桌面客户端
- \desktop_client/app.py\ - 主界面
- \desktop_client/api_client.py\ - API客户端

### 配置和启动脚本
- \.env.example\ - 环境变量配置模板
- \un_server.bat\ - 后端启动脚本
- \un_client.bat\ - 客户端启动脚本
- \setup_mcp.bat\ - MCP服务安装脚本

### 文档
- \README.md\ - 完整使用说明
- \docs/vertex_directions.md\ - Vertex AI配置指南
- \docs/vertex_batch.md\ - Batch API使用说明

##  重要提示

1. **敏感信息保护**
   - 请勿将 \service-account-key.json\ 提交到Git
   - \.env\ 文件已在 \.gitignore\ 中排除
   - 确保不要泄露GCP项目凭据

2. **API配额管理**
   - Vertex AI有使用限额，建议使用批处理模式
   - 单图任务适合测试，批处理适合生产环境

3. **系统要求**
   - 建议图片分辨率至少1000x1000像素
   - 确保网络连接稳定（需访问Google API和CBETA）

##  已知问题

- 批处理模式在某些情况下可能需要较长等待时间
- Gallica检索需要单独安装Node.js环境

##  更新日志

### v1.0.0 (2025-12-04)

**新增**
- 桌面客户端图形界面
- Windows一键启动脚本
- Vertex AI + Service Account认证
- 批处理API支持
- 断点续传功能
- 环境配置模板文件

**优化**
- 更新README添加快速上手指南
- 规范化项目结构
- 完善文档说明

**安全**
- 更新.gitignore保护敏感信息
- 清理临时文件和测试数据

##  许可证

[查看LICENSE文件]

##  贡献

欢迎提交Issue和Pull Request！

##  联系方式

如有问题，请通过GitHub Issues联系。
