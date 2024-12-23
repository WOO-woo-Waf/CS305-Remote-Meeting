import json
import uuid
import websockets
from shared.connection_manager import ConnectionManager
from shared.meeting_manager import MeetingLifecycleManager
from network.rtp_manager import RTPManager
from network.data_router import DataRouter


class WebSocketManager:
    def __init__(self):
        self.connection_manager = ConnectionManager()  # 使用共享的连接管理器
        self.rtp_manager = RTPManager(self)  # 初始化 RTPManager
        self.data_router = DataRouter(self.connection_manager, self.rtp_manager)  # 数据路由器
        self.meeting_lifecycle_manager = MeetingLifecycleManager(self.connection_manager)  # 会议生命周期管理器

    async def handle_connection(self, websocket, path):
        """处理 WebSocket 连接的生命周期"""
        try:
            # 等待客户端发送初始化请求
            init_message = await websocket.receive_text()
            init_data = json.loads(init_message)

            if init_data.get("action") == "INIT":
                # 生成或获取客户端 ID
                client_id = init_data.get("client_id") or str(uuid.uuid4())
                self.connection_manager.add_connection(client_id, websocket)
                print(f"Client {client_id} initialized and connected.")
                # 回复初始化确认消息
                init_ack = {
                    "action": "INIT_ACK",
                    "client_id": client_id,
                    "message": "Connection established"
                }
                await websocket.send_json(init_ack)
                # 开始监听客户端后续的消息
                await self.listen_to_client(client_id, websocket)
        except websockets.ConnectionClosed:
            print("Connection closed before initialization.")
        except Exception as e:
            print(f"Error during connection initialization: {e}")

    async def listen_to_client(self, client_id, websocket):
        """监听已初始化客户端的消息"""
        try:
            while True:
                try:
                    # 接收消息
                    message = await websocket.receive_json()
                    print(f"receive{message}")
                    # # 尝试解析 JSON 数据
                    # try:
                    #     data = json.loads(message)
                    #     print(f"{data}")
                    # except json.JSONDecodeError:
                    #     print(f"Client {client_id} sent invalid JSON: {message}")
                    #     await websocket.send_text("Invalid JSON format")
                    #     continue
                    #
                    #     # 处理客户端消息
                    await self.process_message(client_id, message)
                except Exception as e:
                    print(f"Error processing message from client {client_id}: {e}")
                    await websocket.send_text(f"Error: {str(e)}")
        except websockets.ConnectionClosed as e:
            # 捕获 WebSocket 连接关闭的异常
            print(f"Client {client_id} disconnected. Reason: {e.code}, {e.reason}")
            self.connection_manager.remove_connection(client_id)
            await self.rtp_manager.unregister_client(client_id, self.connection_manager.get_meeting_id(client_id))
            self.connection_manager.clean_up()
        except Exception as e:
            # 捕获其他异常
            print(f"Unexpected error for client {client_id}: {e}")
            self.connection_manager.remove_connection(client_id)
            await self.rtp_manager.unregister_client(client_id, self.connection_manager.get_meeting_id(client_id))
            self.connection_manager.clean_up()

    async def process_message(self, client_id, data):
        """处理客户端的操作请求"""
        try:
            # data = json.loads(message)
            action = data.get("action", "UNKNOWN")
            print(f"Received action {action} from client {client_id}")

            # 心跳机制
            if action == "PING":
                await self.send_message(client_id, {
                    "action": "PONG",
                    "message": "Server is alive"
                })

            # 会议相关操作
            elif action == "CREATE_MEETING":
                await self.create_meeting(client_id, data)

            elif action == "JOIN_MEETING":
                await self.join_meeting(client_id, data)

            elif action == "EXIT_MEETING":
                await self.exit_meeting(client_id, data)

            elif action == "CANCEL_MEETING":
                await self.cancel_meeting(client_id, data)

            elif action == "REGISTER_RTP":
                # 注册 RTP 地址
                rtp_ip = data.get("rtp_ip", "UNKNOWN")
                rtp_port = data.get("rtp_port", "UNKNOWN")
                meeting_id = data.get("meeting_id", "UNKNOWN")
                if not rtp_ip or not rtp_port:
                    await self.send_message(client_id, {
                        "action": "ERROR",
                        "message": "RTP IP and Port are required"
                    })

                await self.rtp_manager.register_client(meeting_id, client_id, (rtp_ip, int(rtp_port)))
                await self.send_message(client_id, {
                    "action": "REGISTER_RTP_ACK",
                    "message": f"RTP address registered: {rtp_ip}:{rtp_port}"
                })

            # elif action == "SEND_AUDIO":
            #     # 音频流的路由 (通过 RTP)
            #     meeting_id = data.get("meeting_id")
            #     audio_data = data.get("audio_data")  # 音频数据（需要以 RTP 方式接收）
            #     await self.data_router.route_audio(meeting_id, client_id, audio_data)
            #
            # elif action == "SEND_VIDEO":
            #     # 视频流的路由 (通过 RTP)
            #     meeting_id = data.get("meeting_id")
            #     video_data = data.get("video_data")  # 视频数据（需要以 RTP 方式接收）
            #     await self.data_router.route_video(meeting_id, client_id, video_data)

            elif action == "SEND_MESSAGE":
                # 处理客户端发送的聊天信息
                await self.handle_send_message(client_id, data)

            else:
                await self.send_message(client_id, {
                    "action": "ERROR",
                    "message": f"Unknown action: {action}"
                })

        except Exception as e:
            print(f"Error processing message from {client_id}: {e}")

    async def create_meeting(self, client_id, data):
        """处理创建会议请求"""
        meeting_id = self.meeting_lifecycle_manager.create_meeting(client_id)
        print("create_meeting success")
        if meeting_id:
            await self.send_message(client_id, {
                "action": "CREATE_MEETING_ACK",
                "meeting_id": meeting_id,
                "message": "Meeting created successfully"
            })
        else:
            await self.send_message(client_id, {
                "action": "ERROR",
                "message": "Meeting creation failed"
            })

    async def join_meeting(self, client_id, data):
        """处理加入会议请求"""
        meeting_id = data.get("meeting_id", "UNKNOWN")
        text = self.meeting_lifecycle_manager.join_meeting(meeting_id, client_id)
        # await self.rtp_manager.join_meeting(meeting_id, client_id)
        if text == "SUCCESS":
            await self.send_message(client_id, {
                "action": "JOIN_MEETING_ACK",
                "meeting_id": meeting_id,
                "participants": self.connection_manager.get_participants(meeting_id),
                "message": "Joined meeting successfully"
            })
        elif text == "ALREADY_IN_MEETING":
            await self.send_message(client_id, {
                "action": "ERROR",
                "message": "You are already in the meeting"
            })
        elif text == "ALREADY_IN_OTHER_MEETING":
            await self.send_message(client_id, {
                "action": "ERROR",
                "message": "You are already in another meeting"
            })
        elif text == "MEETING_NOT_FOUND":
            await self.send_message(client_id, {
                "action": "ERROR",
                "message": f"Meeting {meeting_id} not found"
            })
        else:
            await self.send_message(client_id, {
                "action": "ERROR",
                "message": f"Failed to join meeting {meeting_id}"
            })

    async def exit_meeting(self, client_id, data):
        """处理退出会议请求"""
        meeting_id = data.get("meeting_id", "UNKNOWN")
        if not meeting_id:
            await self.send_message(client_id, {
                "action": "ERROR",
                "message": "Meeting ID is required"
            })
            return

        self.meeting_lifecycle_manager.exit_meeting(meeting_id, client_id)
        await self.rtp_manager.unregister_client(client_id, meeting_id)
        if len(self.connection_manager.get_participants(meeting_id)) == 1:
            await self.stop_p2p(client_id)
            await self.stop_p2p(self.connection_manager.get_participants(meeting_id)[0])

        await self.send_message(client_id, {
            "action": "EXIT_MEETING_ACK",
            "meeting_id": meeting_id,
            "message": "Exited meeting successfully"
        })

    async def cancel_meeting(self, client_id, data):
        """处理取消会议请求"""
        meeting_id = data.get("meeting_id", "UNKNOWN")
        if not meeting_id:
            await self.send_message(client_id, {
                "action": "ERROR",
                "message": "Meeting ID is required"
            })
            return

        participants = self.meeting_lifecycle_manager.cancel_meeting(meeting_id, client_id)
        if participants:
            for participant_id in participants:
                await self.rtp_manager.unregister_client(participant_id, meeting_id)
                await self.send_message(participant_id, {
                    "action": "MEETING_CANCELED",
                    "meeting_id": meeting_id,
                    "message": "Meeting has been canceled by the creator"
                })
            await self.rtp_manager.unregister_client(client_id, meeting_id)
            await self.send_message(client_id, {
                "action": "MEETING_CANCELED",
                "meeting_id": meeting_id,
                "message": "Meeting has been canceled successfully"
            })
        else:
            await self.send_message(client_id, {
                "action": "ERROR",
                "message": "Failed to cancel meeting"
            })

    async def handle_send_message(self, client_id, data):
        """处理聊天信息的发送"""
        meeting_id = data.get("meeting_id", "UNKNOWN")
        message = data.get("message", "UNKNOWN")
        if not meeting_id or not message:
            await self.send_message(client_id, {
                "action": "ERROR",
                "message": "Meeting ID and message are required"
            })
            return

        # 调用 DataRouter 转发消息
        await self.data_router.route_text(meeting_id, client_id, message)

    async def p2p_send_address(self, client_id, to_client_id, ip, port):
        """处理点对点通信的地址发送"""
        await self.send_message(client_id, {
            "action": "P2P_ADDRESS",
            "message": "P2P address received",
            "ip": ip,
            "port": port,
            "client_id": to_client_id
        })

    async def stop_p2p(self, client_id):
        """处理关闭点对点通信的请求"""
        await self.send_message(client_id, {
            "action": "STOP_P2P",
            "message": "P2P connection stopped"
        })

    async def send_message(self, client_id, message):
        """向指定客户端发送消息"""
        websocket = self.connection_manager.get_connection(client_id)
        if websocket:
            await websocket.send_json(message)
