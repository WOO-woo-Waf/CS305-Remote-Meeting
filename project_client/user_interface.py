import asyncio
import threading
import aioconsole
from network.rtp_client import RTPClient
from shared.uiHandler import UIHandler
from shared.media_manager import MediaManager

server_ip = "10.16.180.184"
server_port = 5555

client_ip = "10.16.180.184"
client_port = 5001


class OperationInterface:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(OperationInterface, cls).__new__(cls)
        return cls._instance

    def __init__(self, websocket):
        self.status = "空闲"  # 当前状态
        self.conference_id = None  # 当前会议 ID
        self.on_meeting = False  # 是否正在会议中
        self.shared_data = {"screen": True, "camera": False, "audio": True}  # 共享数据状态
        ui_start_event = threading.Event()
        self.ui_handler = UIHandler(ui_start_event)  # UI 窗口线程的处理对象
        self.web_socket = websocket  # WebSocket 连接
        self.create_meetings = {}
        self.rtp_client = None
        self.media_manager = None
        self.rtp_mode = "unconnected"
        self.cancel_ack = False

    def connect_to_p2p(self, ip, port):
        self.rtp_client.connect_to_p2p(ip, port)

    def stop_p2p(self):
        self.rtp_client.stop_p2p()

    async def rtp_connect(self):
        self.rtp_client = RTPClient(server_ip, server_port, client_port,
                                    self.web_socket.client_id, self.conference_id, client_ip)
        await self.web_socket.register_rtp_address(client_ip, self.rtp_client.client_port, self.conference_id)
        print("RTP Client connected.")
        self.media_manager = MediaManager(self.rtp_client)
        self.media_manager.start_screen_recording()
        # self.media_manager.start_camera()
        self.media_manager.start_microphone()

    def display_help(self):
        """显示帮助菜单"""
        print("\n=== 帮助菜单 ===")
        print("create       创建一个新会议")
        print("join <ID>    加入指定会议")
        print("quit         退出当前会议")
        print("cancel       取消当前会议")
        print("open/close camera 开启/关闭摄像头（不能与屏幕共享同时开启）")
        print("open/close screen 开启/关闭屏幕共享（不能与摄像头同时开启）")
        print("open/close microphone 开启/关闭麦克风")
        print("change quality 调整视频质量 (low,medium,high)")
        print("help         显示帮助菜单")
        print("exit         退出界面")
        print("=================")

    async def create_conference(self):
        """创建会议"""
        if not self.on_meeting:
            print("正在创建会议...")
            await self.web_socket.create_meeting("111")
            self.on_meeting = True
            await asyncio.sleep(1)  # 等待服务器返回会议 ID
            if self.conference_id:
                self.status = f"会议中-{self.conference_id}"
                print(f"会议创建成功，会议 ID: {self.conference_id}")
            # self.start_ui()
            if not self.rtp_client:
                await self.rtp_connect()

        else:
            print("您已经在会议中，无法创建新会议。")

    async def join_conference(self, conference_id):
        """加入会议"""
        print(f"正在加入会议 {conference_id}...")
        await self.web_socket.join_meeting(conference_id)
        await self.web_socket.send_text_message(conference_id, "Hello everyone!")
        self.on_meeting = True
        self.conference_id = conference_id
        self.status = f"会议中-{self.conference_id}"
        print(f"成功加入会议 {conference_id}")
        # self.start_ui()
        if not self.rtp_client:
            await self.rtp_connect()
        else:
            await self.web_socket.register_rtp_address(client_ip, self.rtp_client.client_port, self.conference_id)

    async def quit_conference(self):
        """退出会议"""
        if self.on_meeting:
            print(f"正在退出会议 {self.conference_id}...")
            await self.web_socket.leave_meeting(self.conference_id)
            self.on_meeting = False
            self.conference_id = None
            self.status = "空闲"
            print("您已退出会议。")
        else:
            print("当前不在任何会议中，无法退出。")

    async def cancel_conference(self):
        """取消会议"""
        if self.on_meeting:
            print(f"正在取消会议 {self.conference_id}...")
            await self.web_socket.cancel_meeting(self.conference_id)
            await asyncio.sleep(1)
            if self.cancel_ack:
                self.cancel_ack = False
                self.on_meeting = False
                self.conference_id = None
                self.status = "空闲"
                print("会议已取消。")
            else:
                print("会议取消失败。")
        else:
            print("当前没有会议，无法取消。")

    def share_data(self, action, device_type):
        """Toggle the state of a device (screen, camera, microphone) based on action."""
        if device_type not in self.shared_data:
            print(f"未知设备类型 {device_type}。")
            return

        if action == "open":
            if not self.shared_data[device_type]:
                if device_type == "screen" and not self.shared_data["camera"]:
                    self.media_manager.start_screen_recording()
                elif device_type == "camera" and not self.shared_data["screen"]:
                    self.media_manager.start_camera()
                elif device_type == "microphone":
                    self.media_manager.start_microphone()
                else:
                    print(f"无法开启 {device_type}，可能与其他设备冲突。")
                    return
                self.shared_data[device_type] = True
                print(f"{device_type} 共享已开启。")
            else:
                print(f"{device_type} 已经是开启状态。")
        elif action == "close":
            if self.shared_data[device_type]:
                if device_type == "screen":
                    self.media_manager.stop_screen_recording()
                elif device_type == "camera":
                    self.media_manager.stop_camera()
                elif device_type == "microphone":
                    self.media_manager.stop_microphone()
                self.shared_data[device_type] = False
                print(f"{device_type} 共享已关闭。")
            else:
                print(f"{device_type} 已经是关闭状态。")
    def start_ui(self):
        """启动 UI 界面用于展示接收的数据"""
        if not self.ui_handler:
            self.ui_handler = UIHandler()
            # 创建一个线程运行 UI 界面
            ui_thread = threading.Thread(target=self.ui_handler.run_ui, daemon=True)
            ui_thread.start()
        else:
            print("UI 界面已启动。")

    async def start_interface(self):
        """启动命令行界面主循环"""
        print("欢迎使用会议管理系统！输入 'help' 查看命令。")
        while True:
            current_status = f"({self.status})"
            # 异步获取用户输入，并处理字符串
            user_input = await aioconsole.ainput(f"{current_status} 请输入指令: ")
            user_input = user_input.strip().lower()
            if user_input == "help":
                self.display_help()
            elif user_input == "create":
                await self.create_conference()
            elif user_input.startswith("join"):
                try:
                    _, conf_id = user_input.split(maxsplit=1)
                    await self.join_conference(conf_id)
                except ValueError:
                    print("请提供一个有效的会议 ID。")
            elif user_input == "quit":
                await self.quit_conference()
            elif user_input == "cancel":
                await self.cancel_conference()
            elif user_input.startswith("open") or user_input.startswith("close"):
                try:
                    action, device_type = user_input.split(maxsplit=1)
                    self.share_data(action, device_type)
                except ValueError:
                    print("请指定正确的操作和设备类型（如 open camera）。")
            elif user_input.startswith("change"):
                try:
                    _,quality = user_input.split(maxsplit=1)
                    self.media_manager.set_video_quality(quality)
                except ValueError:
                    print("请输入正确格式: change + quality")
            elif user_input.startswith("send"):
                try:
                    _, message = user_input.split(maxsplit=1)
                    await self.web_socket.send_text_message(self.conference_id, message)
                except ValueError:
                    print("请输入要发送的消息。")
            elif user_input == "check":
                await self.web_socket.check_meeting_all()
            else:
                print("未知指令，请输入 'help' 查看帮助。")