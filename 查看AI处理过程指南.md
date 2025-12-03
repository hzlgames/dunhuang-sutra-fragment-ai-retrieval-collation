# 查看 AI 处理过程指南

## 概述

系统会自动记录 AI 的每一轮思考、工具调用和中间结果到 `sessions/*.rounds.jsonl` 文件中。现在您可以通过 API 端点实时查看这些信息。

---

## 方法一：通过 task_id 查看（推荐）

### 1. 提交任务
```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/v1/jobs/image" -F "file=@input\test0.png"
```

响应：
```json
{"task_id": "160d1eab-16c5-4e44-ba20-4b2c7a5aa3ea"}
```

### 2. 查看处理过程
```powershell
curl.exe "http://127.0.0.1:8000/api/v1/jobs/160d1eab-16c5-4e44-ba20-4b2c7a5aa3ea/process"
```

**响应示例**：
```json
{
  "session_id": "206dd2ab-27b2-4622-a7a3-b33e27bc2dbf",
  "total_rounds": 3,
  "rounds": [
    {
      "round_index": 1,
      "timestamp": "2025-12-03T11:20:51.680366Z",
      "summary": "**Considering Ancient Texts** I've been examining these fragments, focusing on their potential historical context...",
      "tool_calls": [
        {
          "name": "search_similar",
          "args": {
            "text": "須菩提忍辱波羅蜜..."
          },
          "result_summary": "{'query_string': '須菩提忍辱波羅蜜...', 'SQL': 'SELECT id, canon...",
          "status": "success"
        },
        {
          "name": "search_variants",
          "args": {
            "query": "无"
          },
          "result_summary": "{'status': 'success', 'original': '無', 'variants': [...]",
          "status": "success"
        },
        {
          "name": "search_gallica_dunhuang",
          "args": {
            "keyword": "金剛般若波羅蜜經"
          },
          "result_summary": "{'metadata': {'query': 'gallica all \"(Dunhuang...",
          "status": "success"
        }
      ],
      "notes": []
    },
    {
      "round_index": 2,
      "timestamp": "2025-12-03T11:21:15.234567Z",
      "summary": "**Analyzing Search Results** Based on the CBETA search, I found multiple matches...",
      "tool_calls": [...],
      "notes": []
    }
  ]
}
```

---

## 方法二：通过 session_id 查看

### 1. 从批处理获取 session_id
```powershell
curl.exe "http://127.0.0.1:8000/api/v1/batches/YOUR_BATCH_ID"
```

响应中包含每个任务的 `session_id`：
```json
{
  "details": [
    {
      "session_id": "80e49e56-b955-4f9c-958c-4593c12b81f2",
      "alias": "test0_80e49e56",
      ...
    }
  ]
}
```

### 2. 查看该 session 的处理过程
```powershell
curl.exe "http://127.0.0.1:8000/api/v1/process/80e49e56-b955-4f9c-958c-4593c12b81f2"
```

---

## 方法三：直接读取本地文件

### 查看所有 session 记录
```powershell
Get-ChildItem -Path sessions -Filter *.rounds.jsonl
```

### 读取特定 session 的记录
```powershell
Get-Content "sessions\206dd2ab-27b2-4622-a7a3-b33e27bc2dbf.rounds.jsonl"
```

或使用 Python：
```python
import json

session_id = "206dd2ab-27b2-4622-a7a3-b33e27bc2dbf"
with open(f"sessions/{session_id}.rounds.jsonl", "r", encoding="utf-8") as f:
    for line in f:
        round_data = json.loads(line)
        print(f"\n=== Round {round_data['round_index']} ===")
        print(f"时间: {round_data['timestamp']}")
        print(f"摘要: {round_data['summary'][:200]}...")
        print(f"工具调用: {len(round_data['tool_calls'])} 次")
        for tool in round_data['tool_calls']:
            print(f"  - {tool['name']}: {tool['status']}")
```

---

## 使用 Python 测试脚本

我已经更新了 `test_api.py`，添加查看处理过程的功能：

```python
import requests
import json

# 1. 提交任务
response = requests.post(
    "http://127.0.0.1:8000/api/v1/jobs/image",
    files={'file': open('input/test0.png', 'rb')}
)
task_id = response.json()['task_id']
print(f"Task ID: {task_id}")

# 2. 等待任务运行一段时间...
import time
time.sleep(30)

# 3. 查看处理过程
response = requests.get(
    f"http://127.0.0.1:8000/api/v1/jobs/{task_id}/process"
)
process_data = response.json()

print(f"\nSession ID: {process_data['session_id']}")
print(f"总轮次: {process_data['total_rounds']}\n")

for round_info in process_data['rounds']:
    print(f"=== 轮次 {round_info['round_index']} ===")
    print(f"时间: {round_info['timestamp']}")
    print(f"AI 思考: {round_info['summary'][:200]}...")
    print(f"工具调用: {len(round_info['tool_calls'])} 次")
    for tool in round_info['tool_calls']:
        print(f"  - {tool['name']}: {tool['status']}")
        if 'args' in tool:
            print(f"    参数: {str(tool['args'])[:100]}...")
    print()
```

---

## 响应字段说明

### ProcessResponse
| 字段 | 类型 | 说明 |
|------|------|------|
| `session_id` | string | 会话 ID |
| `total_rounds` | int | 总轮次数 |
| `rounds` | array | 每一轮的详细信息 |

### RoundInfo（每一轮）
| 字段 | 类型 | 说明 |
|------|------|------|
| `round_index` | int | 轮次编号（从 1 开始） |
| `timestamp` | string | ISO 8601 时间戳 |
| `summary` | string | AI 的思考摘要（包含推理过程） |
| `tool_calls` | array | 该轮调用的工具列表 |
| `notes` | array | 额外注释（可选） |

### ToolCall（工具调用）
| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | 工具名称（如 `search_similar`, `search_gallica_dunhuang`） |
| `args` | object | 调用参数 |
| `result_summary` | string | 结果摘要 |
| `status` | string | 执行状态（success/failure） |

---

## 常见工具说明

### CBETA 相关工具
- `search_similar`: 根据文本搜索相似段落
- `search_variants`: 查询汉字异体字
- `get_sutra_details`: 获取经文详细信息

### Gallica 相关工具
- `search_gallica_dunhuang`: 在 Gallica 数据库中搜索敦煌文献
- 其他 MCP 工具...

---

## 实时监控示例

### PowerShell 循环查询
```powershell
$taskId = "YOUR_TASK_ID"
while ($true) {
    $response = curl.exe "http://127.0.0.1:8000/api/v1/jobs/$taskId/process" | ConvertFrom-Json
    Write-Host "当前轮次: $($response.total_rounds)"
    Start-Sleep -Seconds 5
}
```

### Python 实时监控
```python
import requests
import time

task_id = "YOUR_TASK_ID"
last_round = 0

while True:
    try:
        response = requests.get(
            f"http://127.0.0.1:8000/api/v1/jobs/{task_id}/process"
        )
        data = response.json()
        
        if data['total_rounds'] > last_round:
            # 有新轮次
            for i in range(last_round, data['total_rounds']):
                round_info = data['rounds'][i]
                print(f"\n🔄 新轮次 {round_info['round_index']}")
                print(f"   {round_info['summary'][:100]}...")
                print(f"   工具调用: {len(round_info['tool_calls'])} 次")
            last_round = data['total_rounds']
        
        # 检查任务状态
        status_response = requests.get(
            f"http://127.0.0.1:8000/api/v1/jobs/{task_id}"
        )
        status = status_response.json()['status']
        
        if status in ['SUCCEEDED', 'FAILED']:
            print(f"\n✅ 任务完成，状态: {status}")
            break
            
    except requests.exceptions.RequestException:
        print("⚠️ 任务可能还未开始或记录未生成")
    
    time.sleep(5)
```

---

## 注意事项

1. **任务必须已开始执行**：只有任务状态变为 `RUNNING` 后，才会生成 `session_id` 和处理记录

2. **记录是累积的**：随着 AI 执行，`rounds` 数组会逐渐增加

3. **文件位置**：
   - 会话记录：`sessions/{session_id}.json`
   - 轮次记录：`sessions/{session_id}.rounds.jsonl`（JSONL 格式，每行一个 JSON 对象）

4. **隐私与性能**：
   - `summary` 字段可能很长（包含完整的 AI 思考）
   - `result_summary` 是工具返回结果的摘要，不是完整数据
   - 如果需要完整的工具返回结果，需要从原始日志或数据库查询

---

## 故障排查

### 错误：未找到处理记录
**可能原因**：
- 任务还未开始执行（状态仍为 `PENDING`）
- 任务执行失败，未生成记录
- session_id 错误

**解决方法**：
```powershell
# 1. 检查任务状态
curl.exe "http://127.0.0.1:8000/api/v1/jobs/YOUR_TASK_ID"

# 2. 确认 session_id 存在
Get-ChildItem -Path sessions -Filter *.rounds.jsonl
```

### 错误：读取处理记录失败
**可能原因**：文件格式错误或损坏

**解决方法**：手动检查文件内容
```powershell
Get-Content "sessions\YOUR_SESSION_ID.rounds.jsonl"
```

---

## 完整示例

```python
#!/usr/bin/env python3
"""完整的处理过程查看示例"""

import requests
import json
import time

BASE_URL = "http://127.0.0.1:8000"

def submit_and_monitor(image_path):
    # 1. 提交任务
    print(f"📤 提交任务: {image_path}")
    with open(image_path, 'rb') as f:
        response = requests.post(
            f"{BASE_URL}/api/v1/jobs/image",
            files={'file': f}
        )
    task_id = response.json()['task_id']
    print(f"✅ Task ID: {task_id}\n")
    
    # 2. 监控处理过程
    last_round = 0
    while True:
        # 查询任务状态
        status_resp = requests.get(f"{BASE_URL}/api/v1/jobs/{task_id}")
        status_data = status_resp.json()
        status = status_data['status']
        
        print(f"📊 状态: {status}")
        
        # 尝试获取处理过程
        try:
            process_resp = requests.get(
                f"{BASE_URL}/api/v1/jobs/{task_id}/process"
            )
            if process_resp.status_code == 200:
                process_data = process_resp.json()
                
                # 显示新轮次
                if process_data['total_rounds'] > last_round:
                    for i in range(last_round, process_data['total_rounds']):
                        round_info = process_data['rounds'][i]
                        print(f"\n{'='*60}")
                        print(f"🔄 轮次 {round_info['round_index']}")
                        print(f"⏰ {round_info['timestamp']}")
                        print(f"\n💭 AI 思考:")
                        print(f"   {round_info['summary'][:300]}...")
                        print(f"\n🔧 工具调用 ({len(round_info['tool_calls'])} 次):")
                        for tool in round_info['tool_calls']:
                            status_emoji = "✅" if tool['status'] == 'success' else "❌"
                            print(f"   {status_emoji} {tool['name']}")
                            if 'args' in tool:
                                args_str = str(tool['args'])[:80]
                                print(f"      参数: {args_str}...")
                    last_round = process_data['total_rounds']
        except:
            print("⚠️ 处理记录尚未生成")
        
        # 检查是否完成
        if status in ['SUCCEEDED', 'FAILED']:
            print(f"\n{'='*60}")
            print(f"🏁 任务完成: {status}")
            if status == 'SUCCEEDED':
                print("\n📄 最终结果:")
                print(json.dumps(status_data['result'], indent=2, ensure_ascii=False)[:500])
            elif status_data.get('error'):
                print(f"\n❌ 错误: {status_data['error']}")
            break
        
        time.sleep(5)
        print()

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python monitor_process.py <图片路径>")
        sys.exit(1)
    
    submit_and_monitor(sys.argv[1])
```

使用方法：
```bash
python monitor_process.py input/test0.png
```

---

## 下一步

现在您可以：
1. 实时监控 AI 的思考过程
2. 调试工具调用问题
3. 优化提示词和工具配置
4. 分析处理性能瓶颈

享受透明的 AI 处理过程！🚀

