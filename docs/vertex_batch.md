以下是针对 \*\*Gemini 3.0 Pro Preview (`gemini-3-pro-preview`)\*\* 的完整 Batch 操作指南。



---



\### 1. 核心流程图解

1\.  \*\*准备数据\*\*：把你的 1000+ 条 Prompt 写进一个 `.jsonl` 文件。

2\.  \*\*上传云端\*\*：把这个文件传到 Google Cloud Storage (GCS) 存储桶里。

3\.  \*\*提交任务\*\*：用 Python 代码告诉 Vertex AI：“去那个桶里拿数据，用 Gemini 3.0 跑，跑完放回桶里。”

4\.  \*\*收菜\*\*：等几小时后，去桶里下载结果文件。



---



\### 2. 第一步：准备输入文件 (.jsonl)

Batch API \*\*极度挑剔\*\*文件格式。必须是 \*\*JSONL (JSON Lines)\*\*，且每一行必须符合官方规定的 `GenerateContentRequest` 结构。



创建一个名为 `batch\_input.jsonl` 的文件，内容示例如下：



```json

{"request": {"contents": \[{"role": "user", "parts": \[{"text": "请为一款名为'极速3000'的跑鞋写一句广告词"}]}]}}

{"request": {"contents": \[{"role": "user", "parts": \[{"text": "请为一款名为'云端咖啡'的速溶咖啡写一句广告词"}]}]}}

{"request": {"contents": \[{"role": "user", "parts": \[{"text": "请为一款名为'暗夜猎手'的游戏键盘写一句广告词"}]}]}}

```

\*注意：每一行都是一个独立的 JSON 对象，不要加逗号，不要加外层的 `\[]`。\*



\### 3. 第二步：上传到 GCS 存储桶

你需要一个 Google Cloud Storage (GCS) Bucket。

1\.  去 \[GCP Console - Cloud Storage](https://console.cloud.google.com/storage) 创建一个桶（比如叫 `my-gemini-batch-bucket`）。

2\.  把上面的 `batch\_input.jsonl` 上传进去。

3\.  记住路径：`gs://my-gemini-batch-bucket/batch\_input.jsonl`。



---



\### 4. 第三步：提交 Batch 任务 (Python 代码)

使用你已经安装好的 `google-genai` 库，并确保 `.env` 已配置 `GOOGLE_CLOUD_PROJECT / GOOGLE_CLOUD_LOCATION / GOOGLE_APPLICATION_CREDENTIALS` 与 `VERTEX_BATCH_BUCKET`。

\*\*执行代码：\*\*



```python

from google import genai

import os

import time



\# 1. 初始化客户端 (Vertex 模式 / ADC)

client = genai.Client(

&nbsp;   vertexai=True,

&nbsp;   project=os.environ\["GOOGLE\_CLOUD\_PROJECT"],

&nbsp;   location=os.environ.get("GOOGLE\_CLOUD\_LOCATION", "global")

)



\# 2. 定义输入和输出路径 (GCS)

bucket = os.environ.get("VERTEX\_BATCH\_BUCKET", "hanhan_dunhuang_batch_storage")

input\_uri = f"gs://{bucket}/batch\_input.jsonl"

output\_uri = f"gs://{bucket}/results/"



\# 3. 提交 Batch 任务

\# 注意：Gemini 3.0 Pro Preview 的模型 ID 可能会变动，

\# 请在 Vertex Model Garden 确认准确 ID，通常是 'gemini-3-pro-preview'

print("正在提交 Batch 任务...")



batch\_job = client.batches.create(

&nbsp;   model="gemini-3-pro-preview",

&nbsp;   src=input\_uri,

&nbsp;   config=genai.types.CreateBatchJobConfig(

&nbsp;       dest=genai.types.BatchJobDestination(gcs\_uri=output\_uri)

&nbsp;   )

)



print(f"任务已提交！")

print(f"任务 ID: {batch\_job.name}")

print(f"任务状态: {batch\_job.state}")



\# 4. (可选) 简单的轮询监控

print("等待任务完成 (这可能需要很久)...")

while batch\_job.state == "JOB\_STATE\_RUNNING" or batch\_job.state == "JOB\_STATE\_PENDING":

&nbsp;   time.sleep(30)

&nbsp;   batch\_job = client.batches.get(name=batch\_job.name)

&nbsp;   print(f"当前状态: {batch\_job.state}")



if batch\_job.state == "JOB\_STATE\_SUCCEEDED":

&nbsp;   print(f"任务完成！结果已保存在: {batch\_job.output\_location}")

else:

&nbsp;   print(f"任务失败，详情: {batch\_job.error}")

```



---



\### 5. 第四步：查看结果

任务完成后，去你的 GCS 桶里的 `results/` 目录下看。

你会发现生成了一堆名为 `prediction-model-...jsonl` 的文件。



下载下来打开，每一行大概长这样：

```json

{"status": "...", "response": {"candidates": \[{"content": {"parts": \[{"text": "极速3000：每一步，都是超越。"}]}}]}}

```

