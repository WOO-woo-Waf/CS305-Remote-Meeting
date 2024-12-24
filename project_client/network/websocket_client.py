import asyncio
import time

import websockets
import json
import uuid

from user_interface import OperationInterface
from shared.uiHandler import UIHandler

ui = UIHandler()


class WebSocketClient:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(WebSocketClient, cls).__new__(cls)
        return cls._instance

    def __init__(self, server_url):
        """
        初始化 WebSocket 客户端。
        :param server_url: WebSocket 服务器地址 (如 ws://localhost:8000/ws)
        """
        self.server_url = server_url
        self.websocket = None
        self.client_id = str(uuid.uuid4())  # 自动生成唯一的客户端 ID
        self.reconnect_delay = 5  # 断开后尝试重新连接的延迟时间（秒）
        # self.ui = UIHandler()
        self.cil = OperationInterface(self)
        self.websocket_lock = asyncio.Lock()  # 在类初始化时创建锁

    async def connect(self):
        """
        连接 WebSocket 服务器并发送初始化请求。
        """
        while True:
            try:
                # self.ui.update_text("尝试连接服务器...")
                self.websocket = await websockets.connect(self.server_url)
                init_message = {"action": "INIT", "client_id": self.client_id}
                await self.websocket.send(json.dumps(init_message))
                response = await self.websocket.recv()
                # self.ui.update_text(f"INIT Response:, {response}")
                ui.update_text(f"INIT Response:, {response}")
                break  # 成功连接后退出循环
            except Exception as e:
                # self.ui.update_text(f"连接失败: {e}，将在 {self.reconnect_delay} 秒后重试...")
                ui.update_text(f"连接失败: {e}，将在 {self.reconnect_delay} 秒后重试...")
                await asyncio.sleep(self.reconnect_delay)

    async def create_meeting(self, meeting_id):
        """
        创建会议。
        :param meeting_id: 会议 ID
        """
        message = {"action": "CREATE_MEETING", "meeting_id": meeting_id}
        await self._send_message(message)

    async def join_meeting(self, meeting_id):
        """
        加入会议。
        :param meeting_id: 会议 ID
        """
        message = {"action": "JOIN_MEETING", "meeting_id": meeting_id}
        await self._send_message(message)

    async def leave_meeting(self, meeting_id):
        """
        离开会议。
        :param meeting_id: 会议 ID
        """
        message = {"action": "EXIT_MEETING", "meeting_id": meeting_id}
        await self._send_message(message)

    async def cancel_meeting(self, meeting_id):
        """
        取消会议。
        :param meeting_id: 会议 ID
        """
        message = {"action": "CANCEL_MEETING", "meeting_id": meeting_id}
        await self._send_message(message)

    async def send_text_message(self, meeting_id, message):
        """
        发送文本消息。
        :param meeting_id: 会议 ID
        :param message: 文本消息内容
        """
        timestamp = int(time.time() * 1000)  # 毫秒级时间戳
        send_message = {
            "action": "SEND_MESSAGE",
            "meeting_id": meeting_id,
            "message": message + f" 时间戳 ({timestamp})"
        }
        await self._send_message(send_message)

    async def register_rtp_address(self, rtp_ip, rtp_port, meeting_id):
        """
        注册 RTP 地址。
        :param meeting_id: 会议号
        :param rtp_ip: RTP IP 地址
        :param rtp_port: RTP 端口
        """
        register_message = {
            "action": "REGISTER_RTP",
            "rtp_ip": rtp_ip,
            "rtp_port": rtp_port,
            "meeting_id": meeting_id
        }
        await self._send_message(register_message)

    async def heartbeat(self):
        """
        定时发送心跳消息。
        """
        while True:
            try:
                ping_message = {"action": "PING"}
                # ui.update_text(f"发送心跳: {ping_message}")
                await self._send_message(ping_message)
                await asyncio.sleep(30)  # 每 20 秒发送一次心跳
            except Exception as e:
                print(f"心跳发送失败: {e}，尝试重新连接...")
                ui.update_text(f"心跳发送失败: {e}，尝试重新连接...")
                break

    async def listen_for_messages(self):
        """
        监听来自服务器的消息。
        """
        while True:
            try:
                message = await self.websocket.recv()
                data = json.loads(message)
                await self.process_server_message(data)  # 调用消息处理方法
            except websockets.ConnectionClosed:
                # self.ui.update_text("服务器连接已关闭，尝试重新连接...")
                ui.update_text("服务器连接已关闭，尝试重新连接...")
                break

    async def check_meeting_all(self):
        """
        查询会议状态。
        """
        message = {"action": "CHECK_MEETING_ALL"}
        await self._send_message(message)

    async def change_cs_mode_to_same(self, isSame):
        message = {"action": "CHANGE_CS_MODE_TO_SAME"}
        await self._send_message(message)

    async def _send_message(self, message):
        """
        发送消息到 WebSocket 服务器。
        :param message: 要发送的消息 (dict)
        """

        async with self.websocket_lock:
            try:
                await self.websocket.send(json.dumps(message))
            except Exception as e:
                # self.ui.update_text(f"发送消息失败: {e}")
                ui.update_text(f"发送消息失败: {e}")

    async def process_server_message(self, data):
        """
        处理服务器返回的消息。
        :param data: 从服务器接收到的消息 (dict)
        """
        try:
            action = data.get("action")  # 获取消息类型
            if not action:
                # self.ui.update_text(f"无效消息格式: {data}")
                ui.update_text(f"无效消息格式: {data}")
                return

            if action == "INIT_ACK":
                # 处理初始化确认
                # self.ui.update_text(f"[服务器响应] 初始化完成: {data}")
                ui.update_text(f"[服务器响应] 初始化完成: {data}")

            elif action == "CREATE_MEETING_ACK":
                # 处理会议创建确认
                meeting_id = data.get("meeting_id")
                self.cil.conference_id = meeting_id
                # self.ui.update_text(f"[服务器响应] 会议已创建，会议 ID: {meeting_id}")
                ui.update_text(f"[服务器响应] 会议已创建，会议 ID: {meeting_id}")

            elif action == "JOIN_MEETING_ACK":
                # 处理加入会议确认
                meeting_id = data.get("meeting_id")
                participants = data.get("participants", [])
                ui.update_text(f"[服务器响应] 加入会议成功，会议 ID: {meeting_id}, 当前参与者: {participants}")

            elif action == "EXIT_MEETING_ACK":
                # 处理离开会议确认
                meeting_id = data.get("meeting_id")
                self.cil.stop_p2p()
                ui.update_text(f"[服务器响应] 已离开会议，会议 ID: {meeting_id}")

            elif action == "MEETING_CANCELED":
                # 处理取消会议确认
                meeting_id = data.get("meeting_id")
                self.cil.cancel_ack = True
                self.cil.stop_p2p()
                ui.update_text(f"[服务器响应] 会议已取消，会议 ID: {meeting_id}")

            elif action == "NEW_MESSAGE":
                # 处理新的文本消息
                meeting_id = data.get("meeting_id")
                sender = data.get("sender")
                message = data.get("message")
                ui.update_text(f"[新消息] 会议 ID: {meeting_id}, 发送者: {sender}, 内容: {message}")

            elif action == "REGISTER_RTP_ACK":
                # 处理 RTP 地址注册确认
                message = data.get("message")
                ui.update_text(f"[服务器响应] {message}")

            elif action == "PONG":
                # 处理心跳确认
                ui.update_text(f"[服务器响应] 心跳回复: {data}")

            elif action == "ERROR":
                message = data.get("message")
                ui.update_text(f"[服务器响应] ERROR: {message}")

            elif action == "P2P_ADDRESS":
                # 处理 P2P 地址分配
                to_client_id = data.get("client_id")
                ip = data.get("ip")
                port = data.get("port")
                message = data.get("message")
                ui.update_text(
                    f"[服务器响应] P2P 地址分配: {message}, 客户端 ID: {to_client_id}, IP: {ip}, 端口: {port}")
                self.cil.connect_to_p2p(ip, port)

            elif action == "STOP_P2P":
                self.cil.stop_p2p()
                ui.update_text(f"[服务器响应] P2P 连接已关闭")

            elif action == "MEETING_LIST":
                # 处理会议状态查询
                meetings = data.get("meetings", {})
                ui.update_text(f"[服务器响应]{action}: {meetings}")
            else:
                # 未知消息类型
                ui.update_text(f"[未知消息类型] {action}: {data}")

        except Exception as e:
            ui.update_text(f"处理消息时发生错误: {e}, 消息内容: {data}")

    async def run(self):
        # while True:
        #     await self.connect()  # 保证连接成功
        #     try:
        #         # 启动心跳和消息监听任务
        #         heartbeat_task = asyncio.create_task(self.heartbeat())
        #         listen_task = asyncio.create_task(self.listen_for_messages())
        #
        #         # 并发运行任务，任意任务出错时退出
        #         await asyncio.gather(
        #             heartbeat_task,
        #             listen_task
        #         )
        #     except Exception as e:
        #         print(f"运行时出现异常: {e}，尝试重新连接...")
        #     finally:
        #         # 取消未完成任务，避免挂起
        #         heartbeat_task.cancel()
        #         listen_task.cancel()
        #         await asyncio.sleep(5)  # 延迟后重新启动
        await self.connect()
        # 启动心跳和消息监听任务
        heartbeat_task = asyncio.create_task(self.heartbeat())
        listen_task = asyncio.create_task(self.listen_for_messages())

        # 并发运行任务，任意任务出错时退出
        await asyncio.gather(
            heartbeat_task,
            listen_task
        )
