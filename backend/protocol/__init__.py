'''protocol 包：前后端 HTTP + SSE 协议 v1 的请求 / 事件模型

约束：字段名与事件名只在本包定义一次，server 与 client 共用，禁止两边各写一份 dict。
'''
