# 快速安装指南

## Windows用户（推荐）

### 1. 下载项目
- 前往 [Releases页面](https://github.com/hzlgames/dunhuang-sutra-fragment-ai-retrieval-collation/releases)
- 下载 `Source code (zip)`
- 解压到任意目录

### 2. 安装Python
- 下载 [Python 3.10+](https://www.python.org/downloads/)
- 安装时勾选 "Add Python to PATH"

### 3. 安装依赖
打开命令提示符（CMD）或PowerShell，进入项目目录：
```bash
cd 你的项目目录
pip install -r requirements.txt
```

### 4. 配置GCP凭据

#### 4.1 获取Service Account密钥
1. 访问 [Google Cloud Console](https://console.cloud.google.com/)
2. 创建项目或选择现有项目
3. 启用 Vertex AI API
4. 创建Service Account：
   - 导航到 "IAM与管理" → "服务帐号"
   - 点击 "创建服务帐号"
   - 授予 "Vertex AI 用户" 角色
5. 下载JSON密钥文件，重命名为 `service-account-key.json`
6. 将文件放到项目根目录

#### 4.2 配置环境变量
1. 复制 `.env.example` 为 `.env`
2. 编辑 `.env` 文件：
```env
GOOGLE_CLOUD_PROJECT=你的GCP项目ID
GOOGLE_CLOUD_LOCATION=global
GOOGLE_APPLICATION_CREDENTIALS=service-account-key.json
```

### 5. 启动使用
1. 双击 `run_server.bat` 启动后端（等待显示 "Uvicorn running"）
2. 双击 `run_client.bat` 启动客户端界面
3. 上传图片开始分析！

## 可选：安装Gallica检索功能

1. 安装 [Node.js](https://nodejs.org/)
2. 双击 `setup_mcp.bat`
3. 在 `.env` 中添加：
```env
GALLICA_MCP_PATH=D:\mcp-servers\sweet-bnf
```

## 故障排查

### 问题1：提示"找不到Python"
- 重新安装Python并勾选 "Add to PATH"
- 或手动添加Python到系统环境变量

### 问题2：pip安装失败
```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 问题3：GCP认证失败
- 检查 `.env` 文件中的项目ID是否正确
- 确认 `service-account-key.json` 文件存在且路径正确
- 确认Service Account有Vertex AI权限

### 问题4：后端无法启动
- 确认8000端口未被占用
- 检查防火墙设置

## 详细文档

完整使用说明请参考 [README.md](README.md)
