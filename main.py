import asyncio
import threading

import websockets
import socket
import struct
import time
import json

from network.websocket_client import WebSocketClient
from user_interface import OperationInterface, UIHandler

server_ip = "127.0.0.1"
server_port = 5555

client_ip = "127.0.0.1"
client_port = 5001

# 在 main 函数中同时运行 start_interface 和 run 方法
async def main():
    # 启动 UIHandler
    ui_handler = UIHandler()
    ui_thread = threading.Thread(target=ui_handler.run_ui, daemon=True)
    ui_thread.start()

    websockets_client = WebSocketClient("ws://localhost:8000/ws")
    cil = OperationInterface(websockets_client)

    # 创建两个任务
    run_task = asyncio.create_task(websockets_client.run())
    interface_task = asyncio.create_task(cil.start_interface())
    # 并行运行
    await asyncio.gather(interface_task, run_task)

# 运行主程序
if __name__ == "__main__":
    asyncio.run(main())


