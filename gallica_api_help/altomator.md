这是一份基于 GitHub 项目 `altomator/IIIF` （https://github.com/altomator/IIIF）的深度研究报告，结合了法国国家图书馆 (BnF) Gallica 官方 API 的技术细节。

### 核心结论

**`altomator/IIIF` 不是一个可以直接安装的 Python 库或 SDK**，而是一个由 BnF 技术专家（或深度用户）创建的**“实验实验室”和“代码食谱”**。

它展示了如何挖掘 Gallica 隐藏的高级功能（如 ALTO OCR 文本定位、自动标注、批量图像提取），而这些功能在官方文档中往往一笔带过。

以下是为您整理的**Gallica API 深度使用指南**，融合了官方标准与 `altomator` 的高级技巧。

---

### 一、 基础架构：Gallica 的三层 API 体系

要像 `altomator` 那样玩转 Gallica，首先需要理解 BnF 的三个核心接口层级：

#### 1. 搜索层 (SRU API) - 入口
用于通过关键词找到文档的 ID（即 `ARK` 码）。
*   **协议**: SRU (Search/Retrieve via URL) 1.2
*   **查询语言**: CQL (Contextual Query Language)
*   **端点**: `https://gallica.bnf.fr/SRU`
*   **示例**: 搜索标题包含 "Chine" 的手稿
    ```
    https://gallica.bnf.fr/SRU?operation=searchRetrieve&version=1.2&query=dc.title all "Chine" and dc.type adj "manuscrit"&maximumRecords=10
    ```
*   **关键输出**: XML 响应中的 `<dc:identifier>` 字段，例如 `https://gallica.bnf.fr/ark:/12148/btv1b8304226d`。这里的 `btv1b8304226d` 就是核心 ID。

#### 2. 结构层 (IIIF Presentation API) - 骨架
这是 `altomator` 项目操作的核心对象。它描述了一本书有多少页、每一页的图片链接在哪里、OCR 文本在哪里。
*   **Manifest URL**: `https://gallica.bnf.fr/iiif/ark:/12148/{ID}/manifest.json`
*   **示例**: `https://gallica.bnf.fr/iiif/ark:/12148/btv1b8304226d/manifest.json`
*   **用途**: 解析此 JSON 文件，你可以获得整本书每一页的高清图下载链接。

#### 3. 图像层 (IIIF Image API) - 实体
用于获取像素数据。
*   **格式**: `{scheme}://{server}/{prefix}/{identifier}/{region}/{size}/{rotation}/{quality}.{format}`
*   **示例 (裁剪并下载某页的局部)**:
    `https://gallica.bnf.fr/iiif/ark:/12148/btv1b8304226d/f1/100,100,800,800/pct:50/0/native.jpg`
    *(解释：第 f1 页，从坐标 100,100 切割 800x800 的区域，缩放 50%，不旋转，原色，JPG格式)*

---

### 二、 `altomator/IIIF` 项目揭示的高级技巧

`altomator` 项目最有价值的地方在于它展示了如何**“越狱”**基本浏览功能，实现数据化研究。

#### 1. 获取 OCR 全文 (ALTO XML)
官方网页只能看纯文本，但 `altomator` 展示了如何将 IIIF Manifest 与底层的 OCR XML 文件（ALTO 格式）关联。
*   **原理**: 在 Manifest 的 Canvas（画布）层级中，通常有一个 `seeAlso` 字段指向 XML。
*   **Hack 技巧**: 如果 Manifest 里没有直接给出，你可以通过 URL 规则猜测。
    *   图片 URL: `.../f1/full/...`
    *   对应的 OCR XML 往往隐藏在类似的路径下，或者需要通过 `ContentSearch` 服务反向查找。
    *   **用途**: 做 NLP 分析（词频、实体识别）时，直接下载 XML 比爬取网页文本更结构化，包含坐标信息。

#### 2. 自动标注与计算机视觉 (AI Annotations)
该项目展示了如何将 AI 模型（如 Roboflow 训练的字首插图检测模型）的结果转化为标准的 **IIIF Annotation List**。
*   **工作流**:
    1.  下载 Gallica 图片。
    2.  运行 AI 模型识别（如识别“首字母装饰”）。
    3.  生成一个 JSON 文件（AnnotationList），包含坐标框（xywh）。
    4.  在本地的 Mirador 阅读器中，将这个 JSON 挂载到 Gallica 的原始 Manifest 上。
*   **价值**: 你不需要修改 BnF 的原始数据，就可以在“外挂”层面上通过 IIIF 协议叠加自己的研究成果（如标记出所有的印章）。

#### 3. 批量提取工具链 (Perl/Shell Scripts)
项目中包含了一些实用的脚本（如 `extractIMG.pl`），其逻辑可以被轻易移植到 Python：
*   **输入**: 一个包含多个 ARK ID 的文本文件。
*   **处理**:
    1.  请求 Manifest JSON。
    2.  遍历 `sequences` -> `canvases` -> `images`。
    3.  构建 IIIF Image URL（通常使用 `/full/full/0/native.jpg` 获取原图）。
    4.  **注意**: 脚本中暗示了需要处理**限流**（Rate Limiting）。

---

### 三、 Gallica API 实战工作流 (Python版复刻建议)

基于上述研究，如果您想复现 `altomator` 的能力，建议编写如下 Python 脚本流程：

#### 步骤 1: 搜索获取 ID
```python
import requests
import xml.etree.ElementTree as ET

# 搜索 "Dunhuang" 相关的 Image 类型资源
base_url = "https://gallica.bnf.fr/SRU"
params = {
    "operation": "searchRetrieve",
    "version": "1.2",
    "query": 'gallica any "Dunhuang" and dc.type adj "image"',
    "maximumRecords": 10
}
response = requests.get(base_url, params=params)
# 解析 XML 获取 ark ID (如 btv1b...)
# 提示: 关注 <dc:identifier> 标签
```

#### 步骤 2: 解析 IIIF Manifest
```python
ark_id = "btv1b8304226d"
manifest_url = f"https://gallica.bnf.fr/iiif/ark:/12148/{ark_id}/manifest.json"
manifest = requests.get(manifest_url).json()

# 提取所有页面的图片链接
image_urls = []
for canvas in manifest['sequences'][0]['canvases']:
    # 获取图片服务的基础 URL
    img_service = canvas['images'][0]['resource']['service']['@id']
    # 拼接全图下载链接 (IIIF 语法)
    full_img_url = f"{img_service}/full/full/0/native.jpg"
    image_urls.append(full_img_url)
```

#### 步骤 3: 批量下载与 OCR 黑科技
如果您需要 OCR 文本，可以尝试构建 ALTO 下载链接。虽然官方 API 文档较少提及，但社区发现通常可以通过以下 endpoint 获取文本层：
`https://gallica.bnf.fr/RequestDigitalElement?O={ID}&E={PAGE_ORDER}& Deb=1`
或者利用 IIIF 的 `otherContent` 字段查找标注列表。

### 四、 关键注意事项

1.  **频率限制 (Rate Limiting)**:
    `altomator` 的代码和相关 R 语言客户端 (`bnfimage`) 都提到 BnF 服务器对高频请求比较敏感。
    *   **建议**: 每次 HTTP 请求间隔 **1-3秒**。如果并发过高，IP 会被暂时封禁。

2.  **图像尺寸限制**:
    虽然 IIIF 允许请求 `/full/full/...`，但对于超高分辨率的大图（如敦煌卷子），Gallica 可能会拒绝直接返回整张几十 MB 的 JPG。
    *   **解决方案**: 使用 **Tiling（切片）** 策略。即请求 `/0,0,1024,1024/full/...` 分块下载，然后本地拼接。`iiif-dl` 是一个现成的工具可以做这件事。

3.  **版权**:
    Gallica 上的大部分古籍（Public Domain）可以免费用于非商业研究，但在批量下载用于构建数据集时，最好查阅具体的 `Rights` 字段。

### 总结
`altomator/IIIF` 指明了一条**“通过 IIIF 协议标准，将 Gallica 当作数据库而非网页使用”**的路径。对于敦煌文献研究，这不仅意味着可以下载图片，还可以通过坐标系统精确引用经卷上的某一行字，甚至叠加自己的校勘层。