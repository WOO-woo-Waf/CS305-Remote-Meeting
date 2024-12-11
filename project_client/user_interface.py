import asyncio
import threading
import aioconsole
from network.rtp_client import RTPClient
from shared.uiHandler import UIHandler
from shared.media_manager import MediaManager

server_ip = "127.0.0.1"
server_port = 5555

client_ip = "127.0.0.1"
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
        self.shared_data = {}  # 存储共享状态（如屏幕、摄像头）
        ui_start_event = threading.Event()
        self.ui_handler = UIHandler(ui_start_event)  # UI 窗口线程的处理对象
        self.web_socket = websocket  # WebSocket 连接
        self.create_meetings = {}
        self.rtp_client = None
        self.media_manager = None

    async def rtp_connect(self):
        self.rtp_client = RTPClient(server_ip, server_port, client_port,
                                    self.web_socket.client_id, self.conference_id, client_ip)
        await self.web_socket.register_rtp_address(client_ip, self.rtp_client.client_port, self.conference_id)
        print("RTP Client connected.")
        self.media_manager = MediaManager(self.rtp_client)
        self.media_manager.start_screen_recording()
        self.media_manager.start_microphone()

    def display_help(self):
        """显示帮助菜单"""
        print("\n=== 帮助菜单 ===")
        print("create       创建一个新会议")
        print("join <ID>    加入指定会议")
        print("quit         退出当前会议")
        print("cancel       取消当前会议")
        print("share <type> 开启/关闭共享（如屏幕、摄像头）")
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
        self.on_meeting = True
        self.conference_id = conference_id
        self.status = f"会议中-{self.conference_id}"
        print(f"成功加入会议 {conference_id}")
        # self.start_ui()
        if not self.rtp_client:
            await self.rtp_connect()

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
            self.on_meeting = False
            self.conference_id = None
            self.status = "空闲"
            print("会议已取消。")
        else:
            print("当前没有会议，无法取消。")

    def share_data(self, data_type):
        """切换共享功能（屏幕、摄像头等）"""
        if data_type not in self.shared_data:
            self.shared_data[data_type] = False  # 默认关闭
        self.shared_data[data_type] = not self.shared_data[data_type]
        state = "开启" if self.shared_data[data_type] else "关闭"
        print(f"{data_type} 共享已{state}。")

    def start_ui(self):
        """启动 UI 界面用于展示接收的数据"""
        if not self.ui_handler:
            self.ui_handler = UIHandler()
            # 创建一个线程运行 UI 界面
            ui_thread = threading.Thread(target=self.ui_handler.run_ui, daemon=True)
            ui_thread.start()

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
            elif user_input.startswith("share"):
                try:
                    _, data_type = user_input.split(maxsplit=1)
                    self.share_data(data_type)
                except ValueError:
                    print("请指定共享类型（如屏幕、摄像头）。")
            elif user_input == "exit":
                print("退出系统。再见！")
            else:
                print("未知指令，请输入 'help' 查看帮助。")




