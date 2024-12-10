import asyncio
import threading

import websockets
import socket
import struct
import time
import json

from network.websocket_client import WebSocketClient
from user_interface import OperationInterface, UIHandler

# # 创建 RTP 数据包
# def create_rtp_packet(payload_type, payload):
#     sequence_number = int(time.time() * 1000) % 65536
#     timestamp = int(time.time() * 1000)
#     ssrc = 123456  # 假设一个固定的 SSRC
#     header = struct.pack('!BBHII', 0x80, payload_type, sequence_number, timestamp, ssrc)
#     return header + payload
#
#
# # WebSocket 客户端
# async def websocket_client():
#     async with websockets.connect("ws://localhost:8000/ws") as websocket:
#         # 初始化连接
#         await websocket.send(json.dumps({"action": "INIT", "client_id": None}))
#         response = await websocket.recv()
#         print("INIT Response:", response)
#
#         # # 创建会议
#         # await websocket.send(json.dumps({"action": "CREATE_MEETING", "meeting_id": "meeting_123"}))
#         # response = await websocket.recv()
#         # print("CREATE_MEETING Response:", response)
#         #
#         # # 加入会议
#         # await websocket.send(json.dumps({"action": "JOIN_MEETING", "meeting_id": "meeting_123"}))
#         # response = await websocket.recv()
#         # print("JOIN_MEETING Response:", response)
#         #
#         # # 发送文本消息
#         # await websocket.send(json.dumps({
#         #     "action": "SEND_MESSAGE",
#         #     "meeting_id": "meeting_123",
#         #     "message": "Hello everyone!"
#         # }))
#         # response = await websocket.recv()
#         # print("SEND_MESSAGE Response:", response)
#         #
#         # while True:
#         #     response = await websocket.recv()
#         #     print("MESSAGE Response:", response)
#         # 注册 RTP 地址
#         rtp_ip = "127.0.0.1"  # 测试 RTP IP
#         rtp_port = 5555       # 测试 RTP 端口
#
#         register_message = {
#             "action": "REGISTER_RTP",
#             "rtp_ip": rtp_ip,
#             "rtp_port": rtp_port
#         }
#         await websocket.send(json.dumps(register_message))
#         print("RTP address registration message sent")
#
#         response = await websocket.recv()
#         print(f"Server response: {response}")
#
#         # 模拟发送 RTP 数据包
#         await send_rtp_packet(rtp_ip, 5006)
#
#
# async def send_rtp_packet(ip, port):
#     """
#     发送 RTP 数据包到服务器。
#     :param ip: RTP 服务器 IP
#     :param port: RTP 服务器端口
#     """
#     print(f"Sending RTP packet to {ip}:{port}")
#     sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
#     sock.bind(("0.0.0.0", 5555))
#     # 构造 RTP 数据包
#     payload_type = 96  # 示例负载类型
#     sequence_number = int(time.time() * 1000) % 65536  # 序列号在 0 ~ 65535
#     timestamp = int(time.time() * 1000) % (2**32)  # 时间戳在 0 ~ 4294967295
#     ssrc = int(time.time()) % (2**32)  # SSRC 在 0 ~ 4294967295
#     header = struct.pack('!BBHII', 0x80, payload_type, sequence_number, timestamp, ssrc)
#     payload = b'This is a test RTP payload'
#     packet = header + payload
#
#     # 发送 RTP 数据包
#     sock.sendto(packet, (ip, port))
#     print("RTP packet sent")
#
#     try:
#         while True:
#             # 接收数据包
#             data, addr = sock.recvfrom(4096)  # 最大数据包大小为 4096 字节
#             print(f"Received RTP packet from {addr}")
#
#             # 解析数据包
#             data = parse_rtp_packet(data)
#             print(f"RTP Header: {data}")
#             print(f"Payload: {payload[:50]}...")  # 打印负载的前 50 字节
#     except KeyboardInterrupt:
#         print("Stopping RTP reception.")
#     finally:
#         sock.close()
#
#
# def parse_rtp_packet(packet):
#     """
#     解析 RTP 数据包。
#     :param packet: RTP 数据包
#     :return: 数据包的字段字典和负载
#     """
#     header = packet[:12]
#     payload = packet[12:]
#     version, payload_type, sequence_number, timestamp, ssrc = struct.unpack('!BBHII', header)
#     return {
#         "version": version >> 6,
#         "payload_type": payload_type,
#         "sequence_number": sequence_number,
#         "timestamp": timestamp,
#         "ssrc": ssrc,
#         "payload": payload
#     }

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


