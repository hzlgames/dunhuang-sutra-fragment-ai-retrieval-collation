#!/usr/bin/env python3
"""
实时监控 AI 处理过程的脚本

用法:
    python monitor_process.py <图片路径>
    python monitor_process.py input/test0.png
"""

import requests
import json
import time
import sys
from pathlib import Path


BASE_URL = "http://127.0.0.1:8000"


def submit_and_monitor(image_path: str):
    """提交任务并实时监控处理过程"""
    
    if not Path(image_path).exists():
        print(f"❌ 文件不存在: {image_path}")
        return
    
    # 1. 提交任务
    print(f"📤 提交任务: {image_path}")
    print("="*60)
    
    try:
        with open(image_path, 'rb') as f:
            response = requests.post(
                f"{BASE_URL}/api/v1/jobs/image",
                files={'file': f}
            )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"❌ 提交失败: {e}")
        return
    
    task_id = response.json()['task_id']
    print(f"✅ Task ID: {task_id}\n")
    
    # 2. 监控处理过程
    last_round = 0
    check_count = 0
    max_checks = 200  # 最多检查 200 次（约 16 分钟）
    
    while check_count < max_checks:
        check_count += 1
        
        try:
            # 查询任务状态
            status_resp = requests.get(f"{BASE_URL}/api/v1/jobs/{task_id}")
            status_resp.raise_for_status()
            status_data = status_resp.json()
            status = status_data['status']
            
            print(f"[{check_count}] 📊 状态: {status}", end="")
            
            # 尝试获取处理过程
            try:
                process_resp = requests.get(
                    f"{BASE_URL}/api/v1/jobs/{task_id}/process"
                )
                
                if process_resp.status_code == 200:
                    process_data = process_resp.json()
                    current_rounds = process_data['total_rounds']
                    print(f" | 已完成轮次: {current_rounds}")
                    
                    # 显示新轮次
                    if current_rounds > last_round:
                        for i in range(last_round, current_rounds):
                            round_info = process_data['rounds'][i]
                            print(f"\n{'='*60}")
                            print(f"🔄 轮次 {round_info['round_index']}")
                            print(f"⏰ 时间: {round_info['timestamp']}")
                            
                            # 显示 AI 思考摘要（前 300 字符）
                            summary = round_info['summary']
                            if len(summary) > 300:
                                summary = summary[:300] + "..."
                            print(f"\n💭 AI 思考:")
                            print(f"   {summary}")
                            
                            # 显示工具调用
                            tool_calls = round_info['tool_calls']
                            if tool_calls:
                                print(f"\n🔧 工具调用 ({len(tool_calls)} 次):")
                                for tool in tool_calls:
                                    status_emoji = "✅" if tool.get('status') == 'success' else "❌"
                                    print(f"   {status_emoji} {tool['name']}")
                                    
                                    # 显示参数（简化版）
                                    if 'args' in tool:
                                        args = tool['args']
                                        # 只显示第一个参数或关键参数
                                        if isinstance(args, dict):
                                            key_arg = None
                                            for k in ['text', 'keyword', 'query', 'sutra_id']:
                                                if k in args:
                                                    key_arg = f"{k}={str(args[k])[:60]}"
                                                    break
                                            if key_arg:
                                                print(f"      参数: {key_arg}...")
                        
                        last_round = current_rounds
                        print()
                elif process_resp.status_code == 404:
                    print(" | ⚠️ 处理记录尚未生成")
                else:
                    print(f" | ⚠️ 无法获取处理记录 ({process_resp.status_code})")
            
            except requests.exceptions.RequestException:
                print(" | ⚠️ 处理记录查询失败")
            
            # 检查是否完成
            if status in ['SUCCEEDED', 'FAILED']:
                print(f"\n{'='*60}")
                print(f"🏁 任务完成: {status}")
                
                if status == 'SUCCEEDED' and status_data.get('result'):
                    print("\n📄 最终结果:")
                    result = status_data['result']
                    
                    # 显示关键信息
                    print(f"   碎片类型: {result.get('fragment_type', 'N/A')}")
                    print(f"   置信度: {result.get('confidence', 'N/A')}")
                    
                    source_work = result.get('source_work', {})
                    if source_work:
                        print(f"   来源作品: {source_work.get('title', 'N/A')}")
                        print(f"   CBETA ID: {source_work.get('cbeta_id', 'N/A')}")
                    
                    matched = result.get('matched_passages', [])
                    if matched:
                        print(f"   匹配段落: {len(matched)} 个")
                    
                    print(f"\n   完整结果已保存到本地文件")
                
                elif status == 'FAILED' and status_data.get('error'):
                    print(f"\n❌ 错误信息: {status_data['error']}")
                
                break
        
        except requests.exceptions.RequestException as e:
            print(f"\n⚠️ 请求失败: {e}")
        
        time.sleep(5)
    
    if check_count >= max_checks:
        print(f"\n⏱️ 已超过最大检查次数 ({max_checks})")


def main():
    if len(sys.argv) < 2:
        print("用法: python monitor_process.py <图片路径>")
        print("\n示例:")
        print("  python monitor_process.py input/test0.png")
        print("  python monitor_process.py input/temp/test_fragment.png")
        sys.exit(1)
    
    image_path = sys.argv[1]
    
    print("\n🚀 AI 处理过程监控工具")
    print("="*60)
    print(f"API 地址: {BASE_URL}")
    print(f"图片路径: {image_path}")
    print()
    
    submit_and_monitor(image_path)


if __name__ == "__main__":
    main()

