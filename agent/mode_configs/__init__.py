'''agent 模式注册表：集中管理所有 agent 模式配置

新增 agent 模式步骤：
1. 在本目录新增 <mode>_mode.py，定义 MODE_CONFIG；
2. 在下方 import 并注册进 MODE_REGISTRY；
3. （可选）在 tools/<mode>/ 下实现该模式独有工具。
'''
from agent.mode_configs.emotion_mode import MODE_CONFIG as EMOTION_MODE
from agent.mode_configs.office_mode import MODE_CONFIG as OFFICE_MODE

# 模式名 → 模式配置
MODE_REGISTRY = {
    EMOTION_MODE["name"]: EMOTION_MODE,
    OFFICE_MODE["name"]: OFFICE_MODE,
}

# 默认模式（桌宠日常主模式：情感陪伴）
DEFAULT_MODE = EMOTION_MODE["name"]
