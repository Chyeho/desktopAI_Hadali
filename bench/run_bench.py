"""批量评测：逐条请求 `/v1/chat` 的 SSE 流，统计延迟、工具调用与错误

用法：
    python bench/run_bench.py                    # 自动拉起后端（--port 0）并跑全部 20 条
    python bench/run_bench.py --limit 5          # 只跑前 5 条
    python bench/run_bench.py --server-url http://127.0.0.1:8765 --token xxx
    python bench/run_bench.py --no-spawn         # 只连已存在的后端，不拉起

输出：`bench/result.csv`（每条一行）+ 控制台 P50/P95、工具调用率、错误率。

说明：本脚本不依赖 Qt / client 包，可在无 GUI 的机器上跑；会真实调用大模型，
     消耗 API 额度，建议先 `--limit 1` 验证连通性。
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import queue
import secrets
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
from httpx_sse import connect_sse

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_BASE_URL = "http://127.0.0.1:8765"
TOKEN_HEADER = "X-Hadali-Token"
READY_PREFIX = "HADALI_SERVER_READY"


# ---------- 后端起停（不依赖 client 包，避免 Qt 依赖） ----------
def probe(base_url: str, token: str, timeout: float = 0.5,
          client: httpx.Client | None = None) -> bool:
    headers = {TOKEN_HEADER: token} if token else {}
    try:
        if client is not None:
            return client.get(f"{base_url}/v1/health", headers=headers,
                              timeout=timeout).status_code == 200
        with httpx.Client(timeout=timeout) as own_client:
            return own_client.get(f"{base_url}/v1/health", headers=headers).status_code == 200
    except Exception:
        return False


def _read_ready_port(proc: subprocess.Popen, timeout: float) -> int | None:
    lines: queue.Queue[str] = queue.Queue()

    def reader():
        for line in proc.stdout:
            lines.put(line.rstrip("\n"))

    threading.Thread(target=reader, daemon=True).start()
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            line = lines.get(timeout=0.2)
        except queue.Empty:
            continue
        if line.startswith(READY_PREFIX):
            return int(json.loads(line[len(READY_PREFIX):].strip())["port"])
    return None


def start_server(timeout: float = 25.0) -> tuple[str, str, subprocess.Popen]:
    """拉起 `python -m backend --port 0`，返回 (base_url, token, proc)"""
    token = os.environ.get("HADALI_TOKEN") or secrets.token_urlsafe(32)
    env = os.environ.copy()
    env["HADALI_TOKEN"] = token
    proc = subprocess.Popen(
        [sys.executable, "-m", "backend", "--host", "127.0.0.1", "--port", "0"],
        cwd=str(ROOT), env=env, stdout=subprocess.PIPE, text=True,
    )
    port = _read_ready_port(proc, timeout)
    if port is None:
        proc.terminate()
        raise SystemExit("后端启动超时，请先用 `python -m backend --port 8765` 手动启动")
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + timeout
    probe_client = httpx.Client(timeout=0.3)
    try:
        while time.time() < deadline:
            if probe(base_url, token, timeout=0.3, client=probe_client):
                return base_url, token, proc
            time.sleep(0.2)
    finally:
        probe_client.close()
    proc.terminate()
    raise SystemExit("后端已启动但健康检查未通过")


# ---------- 单轮评测 ----------
def run_turn(client: httpx.Client, base_url: str, token: str, text: str,
             session_id: str) -> dict:
    headers = {"Accept": "text/event-stream"}
    if token:
        headers[TOKEN_HEADER] = token
    started = time.perf_counter()
    first_event_ms = None
    tool_calls = 0
    result = {
        "first_event_ms": "", "total_ms": "", "latency_ms": "",
        "tool_calls": 0, "error": "", "reply_len": 0,
    }
    try:
        with connect_sse(client, "POST", f"{base_url}/v1/chat",
                         json={"session_id": session_id, "text": text},
                         headers=headers) as source:
            source.response.raise_for_status()
            for message in source.iter_sse():
                if first_event_ms is None:
                    first_event_ms = round((time.perf_counter() - started) * 1000, 2)
                if message.event == "tool.call":
                    tool_calls += 1
                elif message.event == "error":
                    result["error"] = json.loads(message.data).get("code", "UNKNOWN")
                elif message.event == "turn.end":
                    data = json.loads(message.data)
                    result["latency_ms"] = data.get("latency_ms", "")
                    result["reply_len"] = len(data.get("reply", ""))
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    result["first_event_ms"] = first_event_ms if first_event_ms is not None else ""
    result["total_ms"] = round((time.perf_counter() - started) * 1000, 2)
    result["tool_calls"] = tool_calls
    return result


def percentile(values: list[float], p: float) -> float:
    """线性插值分位数（n 较小时比 statistics.quantiles 稳定）"""
    if not values:
        return 0.0
    data = sorted(values)
    k = (len(data) - 1) * p
    low, high = math.floor(k), math.ceil(k)
    if low == high:
        return data[low]
    return data[low] + (data[high] - data[low]) * (k - low)


def load_prompts(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="桌宠后端 SSE 批量评测")
    parser.add_argument("--server-url", default=os.environ.get("HADALI_SERVER_URL", DEFAULT_BASE_URL))
    parser.add_argument("--token", default=os.environ.get("HADALI_TOKEN", ""))
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 条（0 = 全部）")
    parser.add_argument("--session-id", default="bench", help="会话 ID（默认独立会话，不污染 default）")
    parser.add_argument("--turn-timeout", type=float, default=120.0, help="单条读超时（秒）")
    parser.add_argument("--no-spawn", action="store_true", help="只连接已存在的后端")
    parser.add_argument("--prompts", default=str(ROOT / "bench" / "prompts.jsonl"))
    parser.add_argument("--out", default=str(ROOT / "bench" / "result.csv"))
    args = parser.parse_args(argv)

    base_url = args.server_url.rstrip("/")
    token = args.token
    proc = None
    if probe(base_url, token):
        pass
    elif token and probe(base_url, ""):
        token = ""
    elif args.no_spawn:
        print(f"未检测到可用后端：{base_url}（--no-spawn 已禁用自动拉起）")
        return 1
    else:
        print("未检测到后端，正在自动拉起（首次冷启动约 15s）...")
        base_url, token, proc = start_server()

    prompts = load_prompts(Path(args.prompts))
    if args.limit > 0:
        prompts = prompts[: args.limit]

    rows = []
    # 复用同一个 Client：Windows 上 `httpx.Client()` 初始化约 1.4s，逐条新建会污染首事件延迟
    timeout = httpx.Timeout(connect=5.0, read=args.turn_timeout, write=10.0, pool=10.0)
    with httpx.Client(timeout=timeout) as client:
        for index, prompt in enumerate(prompts, start=1):
            metrics = run_turn(client, base_url, token, prompt["text"], args.session_id)
            row = {
                "id": prompt["id"],
                "category": prompt["category"],
                "text": prompt["text"],
                **metrics,
            }
            rows.append(row)
            status = row["error"] or "ok"
            print(f"[{index}/{len(prompts)}] {row['id']} {status} "
                  f"first={row['first_event_ms']}ms total={row['total_ms']}ms "
                  f"tools={row['tool_calls']}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "id", "category", "text", "first_event_ms", "total_ms",
            "latency_ms", "tool_calls", "reply_len", "error",
        ])
        writer.writeheader()
        writer.writerows(rows)

    totals = [r["total_ms"] for r in rows if isinstance(r["total_ms"], (int, float))]
    firsts = [r["first_event_ms"] for r in rows if isinstance(r["first_event_ms"], (int, float))]
    errors = sum(1 for r in rows if r["error"])
    with_tools = sum(1 for r in rows if r["tool_calls"])
    print("\n===== 汇总 =====")
    print(f"样本数        : {len(rows)}")
    print(f"首事件延迟 P50/P95: {percentile(firsts, 0.5):.1f} / {percentile(firsts, 0.95):.1f} ms")
    print(f"总延迟 P50/P95    : {percentile(totals, 0.5):.1f} / {percentile(totals, 0.95):.1f} ms")
    print(f"工具调用率    : {with_tools / len(rows) * 100:.1f}%" if rows else "工具调用率    : -")
    print(f"错误率        : {errors / len(rows) * 100:.1f}%" if rows else "错误率        : -")
    print(f"CSV           : {out}")

    if proc is not None:
        proc.terminate()
        try:
            proc.wait(5)
        except Exception:
            proc.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
