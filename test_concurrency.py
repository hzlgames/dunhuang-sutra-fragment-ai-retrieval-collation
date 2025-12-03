"""
并发请求能力测试脚本

用途：
- 同时向 `/api/v1/jobs/image` 提交多张图片，观察整体耗时与每个任务耗时；
- 粗略判断后端是否具备“并行处理多个图片分析请求”的能力。

前提条件：
- FastAPI 服务已启动：
    python -m uvicorn src.api.server:app --host 0.0.0.0 --port 8000 --reload
- 已在 `.env` 中正确配置 GOOGLE_API_KEY / GEMINI_API_KEY 等依赖环境；
- 已安装 requests：
    pip install -r requirements.txt
"""

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional

import requests


def submit_job(base_url: str, image_path: Path) -> Optional[str]:
    """提交单个异步任务，返回 task_id。"""
    with image_path.open("rb") as f:
        files = {"file": f}
        resp = requests.post(f"{base_url}/api/v1/jobs/image", files=files)
    if resp.status_code != 200:
        print(f"❌ 提交失败 [{image_path}]: {resp.status_code} - {resp.text}")
        return None
    data = resp.json()
    task_id = data.get("task_id")
    print(f"✅ 已提交任务，文件={image_path}, task_id={task_id}")
    return task_id


def poll_job(base_url: str, task_id: str, poll_interval: float, timeout: float) -> Dict:
    """
    轮询单个任务直至结束或超时。

    返回：
        {
            "task_id": ...,
            "status": "SUCCEEDED" | "FAILED" | "TIMEOUT",
            "error": str | None,
            "duration": float (秒)
        }
    """
    start = time.time()
    while True:
        if time.time() - start > timeout:
            return {
                "task_id": task_id,
                "status": "TIMEOUT",
                "error": f"轮询超时（>{timeout} 秒）",
                "duration": time.time() - start,
            }
        try:
            resp = requests.get(f"{base_url}/api/v1/jobs/{task_id}")
        except Exception as exc:
            return {
                "task_id": task_id,
                "status": "FAILED",
                "error": f"请求失败: {exc}",
                "duration": time.time() - start,
            }

        if resp.status_code != 200:
            return {
                "task_id": task_id,
                "status": "FAILED",
                "error": f"HTTP {resp.status_code}: {resp.text}",
                "duration": time.time() - start,
            }

        data = resp.json()
        status = data.get("status")
        if status in {"SUCCEEDED", "FAILED"}:
            return {
                "task_id": task_id,
                "status": status,
                "error": data.get("error"),
                "duration": time.time() - start,
            }

        time.sleep(poll_interval)


def worker(base_url: str, image_path: Path, poll_interval: float, timeout: float) -> Dict:
    """单个并发工作：提交任务 + 轮询完成。"""
    t0 = time.time()
    task_id = submit_job(base_url, image_path)
    if not task_id:
        return {
            "image": str(image_path),
            "task_id": None,
            "status": "FAILED",
            "error": "提交失败",
            "submit_to_done": 0.0,
        }
    result = poll_job(base_url, task_id, poll_interval=poll_interval, timeout=timeout)
    t1 = time.time()
    return {
        "image": str(image_path),
        "task_id": task_id,
        "status": result["status"],
        "error": result.get("error"),
        "submit_to_done": result["duration"],
        "wall_time": t1 - t0,
    }


def run_concurrent(
    base_url: str,
    image_paths: List[Path],
    poll_interval: float = 5.0,
    timeout: float = 900.0,
) -> List[Dict]:
    """并发跑多张图片，返回每个任务的统计信息。"""
    print("\n========== 并发测试开始 ==========")
    print(f"服务地址: {base_url}")
    print("测试图片列表:")
    for p in image_paths:
        print(f"  - {p}")

    overall_start = time.time()
    results: List[Dict] = []

    with ThreadPoolExecutor(max_workers=len(image_paths)) as executor:
        future_to_img = {
            executor.submit(worker, base_url, p, poll_interval, timeout): p
            for p in image_paths
        }
        for future in as_completed(future_to_img):
            res = future.result()
            results.append(res)
            print(
                f"\n🎯 完成: image={res['image']}, status={res['status']}, "
                f"耗时≈{res['submit_to_done']:.1f}s, 总墙钟时间≈{res['wall_time']:.1f}s"
            )

    overall_end = time.time()
    wall = overall_end - overall_start

    print("\n========== 并发测试结束 ==========")
    print(f"整体墙钟时间(从首次提交到全部完成): {wall:.1f} 秒")

    # 简单并行度评估：如果 sum(单任务耗时) 远大于 wall_time，则说明有并行
    sum_durations = sum(r.get("submit_to_done", 0.0) for r in results)
    if wall > 0:
        parallel_factor = sum_durations / wall
    else:
        parallel_factor = 0.0

    print(f"单任务耗时之和: {sum_durations:.1f} 秒")
    print(f"并行度粗略指标 (sum_durations / wall_time): {parallel_factor:.2f}")
    print("经验判断：")
    if parallel_factor >= 1.5:
        print("  ➜ 看起来后端具备一定的并行处理能力（多请求重叠执行）。")
    else:
        print("  ➜ 看起来后端整体更接近串行处理（或任务本身很快，难以区分）。")

    print("\n详细结果 JSON：")
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="测试后端并行处理多个图片分析请求的能力")
    parser.add_argument(
        "--images",
        nargs="+",
        required=True,
        help="要并发提交的图片路径列表，例如：input/test0.png input/temp/test_fragment1.png",
    )
    parser.add_argument(
        "--url",
        type=str,
        default="http://127.0.0.1:8000",
        help="API 服务地址（默认: http://127.0.0.1:8000）",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=5.0,
        help="轮询间隔秒数（默认 5 秒）",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=900.0,
        help="单任务最大等待时间（秒），默认 900 秒",
    )

    args = parser.parse_args()

    image_paths = [Path(p) for p in args.images]
    missing = [str(p) for p in image_paths if not p.exists()]
    if missing:
        print("❌ 以下文件不存在：")
        for m in missing:
            print(f"  - {m}")
        return

    run_concurrent(
        base_url=args.url,
        image_paths=image_paths,
        poll_interval=args.poll_interval,
        timeout=args.timeout,
    )


if __name__ == "__main__":
    main()


