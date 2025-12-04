# Vertex AI 初始化设置核心指南 (SOP)
## 1. 核心结论
*   **认证方式**：必须使用 **Service Account (ADC)**。当前版本 SDK 不支持在 Vertex AI 模式下使用 API Key。
*   **项目要求**：必须使用**标准 Google Cloud 项目**。避免使用 AI Studio 自动生成的项目（`gen-lang-client-*`），因为它们通常缺少 Vertex AI 模型访问权限。
---
## 2. 关键步骤清单
### 第一步：GCP 项目配置 (管理员)
**导出密钥**：
    *   下载 JSON 文件，重命名为 `service-account-key.json`。
### 第二步：环境配置 (DevOps/开发)
在项目根目录配置 `.env` 文件（**切勿提交到 Git**）：
```ini
# 1. 项目标识
GOOGLE_CLOUD_PROJECT="your-standard-project-id"  # 必须是标准项目ID
GOOGLE_CLOUD_LOCATION="global" 
# 2. 认证凭据 (绝对路径或相对路径)
GOOGLE_APPLICATION_CREDENTIALS="service-account-key.json"
# 3. 模型选择
GEMINI_MODEL_NAME=……
```
### 第三步：代码实现 (Python)
使用 `google-genai` SDK 的标准初始化模式：
```python
import os
from google import genai
from dotenv import load_dotenv
# 加载环境变量
load_dotenv()
def get_vertex_client():
    # 检查必要配置
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        raise ValueError("❌ 未设置 GOOGLE_APPLICATION_CREDENTIALS")
    # 初始化客户端 (SDK 会自动读取环境变量中的凭据)
    client = genai.Client(
        vertexai=True,
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location=os.environ["GOOGLE_CLOUD_LOCATION"]
    )
    return client
# 使用示例
if __name__ == "__main__":
    client = get_vertex_client()
    response = client.models.generate_content(
        model=os.environ.get("GEMINI_MODEL_NAME", "gemini-3-preview"),
        contents="Hello Vertex AI!"
    )
    print(response.text)
```
---
## 3. 常见避坑指南
| 问题现象 | 根本原因 | 解决方案 |
| :--- | :--- | :--- |
| `401 API keys are not supported` | 试图在 Vertex 模式下用 API Key | 切换到 Service Account (JSON) 认证 |
| `404 Publisher Model not found` | 使用了 AI Studio 自动生成的项目 | 创建并使用标准的 GCP 项目 |
| `403 Permission Denied` | 服务账号缺少权限 | 确保已分配 `Vertex AI User` 角色 |
| `SSL / Connection Error` | 网络环境限制 | 配置 `HTTP_PROXY` / `HTTPS_PROXY` 环境变量 |
---
## 4. 文件安全规范
*   ❌ **禁止提交**：`.env`, `service-account-key.json` (务必加入 `.gitignore`)
