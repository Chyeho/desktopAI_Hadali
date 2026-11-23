'''陪伴主图的模型生成参数

原先复用 legacy 情感模式的 `MODE_REGISTRY["emotion"]["model_params"]`，
抽出后主图不再依赖 `agent/mode_configs`，便于旧多模式代码整体归档。
'''

# 与 legacy 情感陪伴模式保持一致的生成参数（温度偏高，回复更自然有变化）
GRAPH_MODEL_PARAMS = {
    "temperature": 0.7,
    "max_tokens": 1024,
    "top_p": 0.9,
    "presence_penalty": 0.5,
    "frequency_penalty": 0.3,
}
