"""程序主入口（P3 起为客户端 shim）

真正的实现已迁到 `client/main.py`：UI 进程不再直接持有 Agent，
而是通过本机 HTTP + SSE 与 `backend` 通信。保留本文件是为了
`python main.py` 的启动方式与测试路径不变。
"""
import sys

from client.main import main

if __name__ == "__main__":
    sys.exit(main())
