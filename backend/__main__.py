'''命令行入口：python -m backend [--host 127.0.0.1] [--port 8765]

`--port 0` 时随机端口，并在 stdout 输出一行
`HADALI_SERVER_READY {"port": <N>}` 供 client launcher 解析。
'''
import argparse
import asyncio
import json

import uvicorn

from backend.api.app import create_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="backend", description="Hadali 对话后端（FastAPI + SSE）"
    )
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认仅本机）")
    parser.add_argument("--port", type=int, default=8765, help="监听端口；0 表示随机端口")
    return parser


async def _serve_and_announce(server: uvicorn.Server) -> None:
    '''等 server 真正监听后再输出就绪行（仅 --port 0 使用）'''
    task = asyncio.create_task(server.serve())
    while not server.started and not task.done():
        await asyncio.sleep(0.05)
    if server.started:
        port = server.servers[0].sockets[0].getsockname()[1]
        print(f"HADALI_SERVER_READY {json.dumps({'port': port})}", flush=True)
    await task


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    config = uvicorn.Config(
        create_app(),
        host=args.host,
        port=args.port,
        log_level="info",
        loop="asyncio",
    )
    server = uvicorn.Server(config)
    if args.port == 0:
        asyncio.run(_serve_and_announce(server))
    else:
        server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
