https://api.bnf.fr/api-iiif-de-recuperation-des-images-de-gallica
https://api.bnf.fr/fr/wrapper-python-pour-les-api-gallica
https://github.com/ian-nai/PyGallica
基于上面的三个链接（BnF 官方 IIIF 文档、官方 Python 封装说明页、以及 GitHub 上的 PyGallica 项目），整理了这份**Gallica API 深度调用指南**。

这份文档将分为三个部分：
1.  **基础核心**：理解 Gallica 的数据逻辑（ARK ID 与 IIIF）。
2.  **工具实战**：使用 Python 封装库 (`PyGallica`) 进行快速开发。
3.  **底层进阶**：直接构造 IIIF URL 实现图像的高级处理（裁剪、缩放）。

---

# Gallica API 调用帮助文档 (Python 版)

## 0. 核心概念：ARK ID
在调用任何 API 之前，必须理解 BnF 的唯一标识符 **ARK (Archival Resource Key)**。
*   格式：`ark:/12148/{唯一字符串}`
*   示例：`ark:/12148/btv1b8304226d` (某个敦煌卷子的 ID)
*   **注意**：所有 API 调用都需要这个 ID。

---

## 1. 快速上手：使用 PyGallica 库
**来源**: `https://github.com/ian-nai/PyGallica`
这是一个非官方但结构清晰的 Python 封装库，适合**批量搜索**和**获取元数据/全文**。

### 1.1 安装与配置
由于这不是 pip 官方包，建议直接下载源码：
```bash
git clone https://github.com/ian-nai/PyGallica.git
```
在代码中引入：
```python
# 假设你将 pygallica.py 放在了同级目录
from pygallica import GallicaWrapper
```

### 1.2 核心功能函数

#### A. 搜索 (SRU API 封装)
用于通过关键词查找文档 ID。

```python
api = GallicaWrapper()

# 示例：搜索标题包含 "Dunhuang" 且类型为 "manuscript" (手稿) 的资源
# CQL (Contextual Query Language) 是核心查询语法
cql_query = 'dc.title any "Dunhuang" and dc.type adj "manuscrit"'

# 执行搜索，startRecord=1 表示从第1条开始，maximumRecords=10 表示取10条
results = api.search(query=cql_query, startRecord=1, maximumRecords=10)

for record in results:
    print(f"标题: {record.title}")
    print(f"ARK ID: {record.ark}")
    print(f"日期: {record.date}")
```

#### B. 获取全文本 (OCR)
如果文档有 OCR（如印刷品），可以直接提取文本。
```python
# 获取某个 ARK ID 的纯文本
# 注意：手写体（如敦煌卷子）通常没有 OCR，返回可能为空或乱码
text = api.get_document_text(ark="ark:/12148/bpt6k123456")
print(text[:500]) # 打印前500字
```

#### C. 获取目录结构 (Pagination)
对于一本书或一卷经文，需要知道它有多少页。
```python
# 获取文档的分页信息
pagination = api.get_pagination("ark:/12148/btv1b8304226d")
# 返回通常包含页码列表，如 ['f1', 'f2', 'f3'...]
print(f"总页数: {len(pagination)}")
```

---

## 2. 图像获取：IIIF API 详解
**来源**: `https://api.bnf.fr/api-iiif-de-recuperation-des-images-de-gallica`
当 `PyGallica` 无法满足图像处理需求（如只想要高清切片）时，使用原生 IIIF 协议。

### 2.1 URL 构造公式
BnF 的 IIIF 图像链接遵循标准格式：
```
https://gallica.bnf.fr/iiif/{ID}/{Region}/{Size}/{Rotation}/{Quality}.{Format}
```

### 2.2 参数详解表

| 参数 | 说明 | 常用值/示例 |
| :--- | :--- | :--- |
| **ID** | `ark:/12148/{id}/f{页码}` | `ark:/12148/btv1b8304226d/f1` (注意必须带 `f1`, `f2`...) |
| **Region** | 裁剪区域 | `full` (全图)<br>`x,y,w,h` (坐标裁剪, 如 `100,100,500,500`)<br>`pct:x,y,w,h` (百分比裁剪) |
| **Size** | 缩放尺寸 | `full` (原尺寸)<br>`pct:50` (缩小50%)<br>`1000,` (宽缩放到1000px，高自适应) |
| **Rotation**| 旋转角度 | `0` (不旋转)<br>`90`, `180`, `270` |
| **Quality** | 图像质量 | `native` (原色)<br>`gray` (灰度)<br>`bitonal` (黑白二值化，适合文字识别) |
| **Format** | 文件格式 | `jpg`, `png` |

### 2.3 常用场景代码 (Python requests)

#### 场景一：下载某一页的高清原图
```python
import requests

# 构造 URL：第1页，全图，原尺寸，原生色彩，JPG
# 注意：如果不确定图片是否太大，建议先用 pct:50 测试
ark = "ark:/12148/btv1b8304226d"
page = "f1"
url = f"https://gallica.bnf.fr/iiif/{ark}/{page}/full/full/0/native.jpg"

response = requests.get(url, stream=True)
if response.status_code == 200:
    with open(f"{page}.jpg", 'wb') as f:
        for chunk in response.iter_content(1024):
            f.write(chunk)
```

#### 场景二：获取图像元数据 (Info.json)
在下载前，查询图片的真实分辨率（宽、高），避免请求超出服务器限制的大图。
```python
# IIIF Info.json 端点
info_url = f"https://gallica.bnf.fr/iiif/{ark}/{page}/info.json"
info = requests.get(info_url).json()

width = info['width']
height = info['height']
print(f"原图尺寸: {width} x {height}")
```

#### 场景三：裁剪标题区域 (假设已知坐标)
适合做数据集训练。
```python
# 假设标题在顶部，从 0,0 开始，宽100%，高10%
region = f"pct:0,0,100,10" 
url = f"https://gallica.bnf.fr/iiif/{ark}/{page}/{region}/full/0/native.jpg"
# ...下载逻辑同上
```

---

## 3. 高级技巧与注意事项

### 3.1 突破下载限制 (Tiling)
Gallica 对单次请求的图片像素有限制（通常不超过 2500px 或 5000px 边长，视负载而定）。如果 `Size` 设为 `full` 报错 403 或 500，需要使用 **切片下载 (Tiling)**。

*   **逻辑**：根据 `info.json` 的 `tiles` 参数，将大图切成 1024x1024 的小块分别请求，然后在本地拼接。
*   **工具推荐**：不要自己写，使用现成的工具如 `dezoomify-rs` 或 Python 库 `iiif-downloader`。

### 3.2 避免 IP 封禁
*   **请求间隔**：Gallica 对爬虫较为敏感。
*   **代码建议**：
    ```python
    import time
    # 每次请求后休眠 1-2 秒
    time.sleep(1.5)
    ```

### 3.3 查找正确的查询语法 (CQL)
在使用 `PyGallica` 搜索时，如果不知道关键词怎么写：
*   `gallica any "keyword"`: 全文搜索
*   `dc.title all "keyword"`: 标题搜索
*   `dc.type adj "image"`: 限制为图像/手稿
*   `dc.language adj "chi"`: 限制为中文

### 3.4 完整工作流示例
结合 PyGallica 搜索 + IIIF 下载：

```python
from pygallica import GallicaWrapper
import requests
import time

api = GallicaWrapper()

# 1. 搜索敦煌经卷
print("正在搜索...")
records = api.search('gallica any "Dunhuang" and dc.type adj "manuscrit"', maximumRecords=3)

for rec in records:
    print(f"处理: {rec.title} ({rec.ark})")
    
    # 2. 假设我们只取第1页 (f1)
    # 实际项目中应解析 Manifest 获取所有页码
    img_url = f"https://gallica.bnf.fr/iiif/{rec.ark}/f1/full/pct:20/0/native.jpg"
    
    # 3. 下载缩略图
    try:
        r = requests.get(img_url)
        if r.status_code == 200:
            filename = f"{rec.ark.split('/')[-1]}_f1.jpg"
            with open(filename, 'wb') as f:
                f.write(r.content)
            print(f"已下载: {filename}")
        else:
            print(f"下载失败: {r.status_code}")
    except Exception as e:
        print(e)
    
    # 礼貌延时
    time.sleep(2)
```

这套文档涵盖了从发现资源（Search）到获取资源（IIIF）的全流程，应该能满足您大部分的开发需求。