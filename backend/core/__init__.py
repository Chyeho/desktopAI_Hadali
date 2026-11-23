'''core 包：与 UI 无关的纯逻辑门面（对话、会话、指标）

约束：本包及其依赖（agent / tools / utils / modelFactory）不得 import
PySide6、live2d、httpx、fastapi，也不持有任何 GUI 状态。
'''
