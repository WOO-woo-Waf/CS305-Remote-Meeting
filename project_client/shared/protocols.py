# 定义数据格式和协议，与服务端共享。

import json


def create_text_message(sender, message):
    """生成文本消息"""
    return json.dumps({
        "type": "text",
        "sender": sender,
        "message": message
    })


def parse_message(data):
    """解析消息"""
    return json.loads(data)
