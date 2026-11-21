'''陪伴主图 CLI 演示

用法（项目根目录）：
    .venv\\Scripts\\python.exe -m agent.graph.demo

读取 .env 中的 API_KEY / BASE_URL / MODEL，进入多轮对话；输入 exit / quit 退出。
'''
from core.facade import DEFAULT_BASE_URL, DEFAULT_MODEL, load_env
from modelFactory.factory import ChatModelFactory
from agent.graph.runner import CompanionGraphAgent
from utils.path_tool import get_abs_path


def _build_agent() -> CompanionGraphAgent:
    env = load_env(get_abs_path(".env"))
    api_key = env.get("API_KEY", "")
    if not api_key:
        raise SystemExit("未在 .env 中找到有效的 API_KEY")

    factory = ChatModelFactory(
        api_key=api_key,
        base_url=env.get("BASE_URL", DEFAULT_BASE_URL),
        model=env.get("MODEL", DEFAULT_MODEL),
    )
    llm = factory.generator(temperature=0.7, max_tokens=1024, top_p=0.9)
    return CompanionGraphAgent(llm)


def main() -> None:
    agent = _build_agent()

    print("哈达莉已就绪，输入 exit / quit 退出。")
    while True:
        try:
            user_input = input("用户：").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            break

        print("哈达莉：", end="", flush=True)
        for kind, payload in agent.stream_chat(user_input):
            if kind == "delta":
                print(payload, end="", flush=True)
        print()


if __name__ == "__main__":
    main()
