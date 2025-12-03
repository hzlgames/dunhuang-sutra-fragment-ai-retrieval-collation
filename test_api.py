"""
FastAPI 接口测试脚本
用于测试单任务异步接口和批处理接口

使用方法:
    python test_api.py --single input/test0.png
    python test_api.py --batch input/test0.png input/temp/test_fragment.png
"""

import argparse
import time
import requests
import json
from pathlib import Path


BASE_URL = "http://127.0.0.1:8000"


def test_single_job(image_path: str):
    """测试单任务异步接口"""
    print(f"\n{'='*60}")
    print("测试单任务异步接口 (/api/v1/jobs/image)")
    print(f"{'='*60}")
    
    # 1. 提交任务
    print(f"\n[1] 提交任务: {image_path}")
    with open(image_path, 'rb') as f:
        files = {'file': f}
        response = requests.post(f"{BASE_URL}/api/v1/jobs/image", files=files)
    
    if response.status_code != 200:
        print(f"❌ 提交失败: {response.status_code} - {response.text}")
        return
    
    data = response.json()
    task_id = data['task_id']
    print(f"✅ 任务已提交，task_id: {task_id}")
    
    # 2. 轮询状态
    print(f"\n[2] 轮询任务状态...")
    max_attempts = 30
    for i in range(max_attempts):
        time.sleep(5)
        response = requests.get(f"{BASE_URL}/api/v1/jobs/{task_id}")
        data = response.json()
        status = data['status']
        
        print(f"    [{i+1}/{max_attempts}] 状态: {status}")
        
        if status == "SUCCEEDED":
            print(f"\n✅ 任务成功完成！")
            print(f"\n结果预览:")
            print(json.dumps(data['result'], indent=2, ensure_ascii=False)[:500] + "...")
            return data
        elif status == "FAILED":
            print(f"\n❌ 任务失败: {data.get('error', '未知错误')}")
            return None
    
    print(f"\n⚠️ 轮询超时（{max_attempts * 5}秒），任务可能仍在执行")
    return None


def test_batch_jobs(image_paths: list):
    """测试批处理接口"""
    print(f"\n{'='*60}")
    print("测试批处理接口 (/api/v1/batches)")
    print(f"{'='*60}")
    
    # 1. 创建批处理
    print(f"\n[1] 创建批处理任务，共 {len(image_paths)} 张图片:")
    for path in image_paths:
        print(f"    - {path}")
    
    files = [('files', open(path, 'rb')) for path in image_paths]
    response = requests.post(f"{BASE_URL}/api/v1/batches", files=files)
    for _, f in files:
        f.close()
    
    if response.status_code != 200:
        print(f"❌ 创建失败: {response.status_code} - {response.text}")
        return
    
    data = response.json()
    batch_id = data['batch_id']
    print(f"✅ 批处理已创建，batch_id: {batch_id}")
    
    # 2. 轮询状态
    print(f"\n[2] 轮询批处理状态...")
    max_attempts = 50
    for i in range(max_attempts):
        time.sleep(10)
        response = requests.get(f"{BASE_URL}/api/v1/batches/{batch_id}")
        data = response.json()
        status = data['status']
        completed = data['completed_jobs']
        failed = data['failed_jobs']
        total = data['total_jobs']
        round_num = data['round']
        
        print(f"    [{i+1}/{max_attempts}] 状态: {status}, 轮次: {round_num}, "
              f"进度: {completed}/{total} 成功, {failed} 失败")
        
        if status == "SUCCEEDED":
            print(f"\n✅ 批处理成功完成！")
            break
        elif status == "FAILED":
            print(f"\n❌ 批处理失败")
            print(f"\n失败详情:")
            for detail in data['details']:
                if detail['error']:
                    print(f"  - {detail['alias']}: {detail['error']}")
            break
    else:
        print(f"\n⚠️ 轮询超时（{max_attempts * 10}秒）")
        return None
    
    # 3. 获取结果
    print(f"\n[3] 获取批处理结果...")
    response = requests.get(f"{BASE_URL}/api/v1/batches/{batch_id}/results")
    results = response.json()
    
    print(f"\n结果汇总:")
    for item in results['items']:
        session_id = item['session_id']
        item_status = item['status']
        print(f"  - Session {session_id[:8]}: {item_status}")
        if item_status == "SUCCEEDED" and item['result']:
            print(f"    碎片类型: {item['result'].get('fragment_type', 'N/A')}")
        elif item['error']:
            print(f"    错误: {item['error']}")
    
    return results


def main():
    parser = argparse.ArgumentParser(description='测试 FastAPI 接口')
    parser.add_argument('--single', type=str, help='测试单任务接口，指定图片路径')
    parser.add_argument('--batch', nargs='+', help='测试批处理接口，指定多个图片路径')
    parser.add_argument('--url', type=str, default="http://127.0.0.1:8000", 
                        help='API 服务地址（默认: http://127.0.0.1:8000）')
    
    args = parser.parse_args()
    
    global BASE_URL
    BASE_URL = args.url
    
    if args.single:
        if not Path(args.single).exists():
            print(f"❌ 文件不存在: {args.single}")
            return
        test_single_job(args.single)
    
    elif args.batch:
        missing = [p for p in args.batch if not Path(p).exists()]
        if missing:
            print(f"❌ 以下文件不存在:")
            for p in missing:
                print(f"  - {p}")
            return
        test_batch_jobs(args.batch)
    
    else:
        parser.print_help()
        print("\n示例:")
        print("  python test_api.py --single input/test0.png")
        print("  python test_api.py --batch input/test0.png input/temp/test_fragment.png")


if __name__ == "__main__":
    main()

