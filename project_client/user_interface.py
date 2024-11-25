import asyncio
import threading
import tkinter as tk
import aioconsole
from tkinter.scrolledtext import ScrolledText
import time


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


class UIHandler:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(UIHandler, cls).__new__(cls)
        return cls._instance

    def __init__(self, start_event=None):
        """初始化 UI 界面"""
        self.root = None
        self.text_area = None  # 用于显示文本信息
        self.video_frame = None  # 视频展示区域
        self.audio_info = None  # 音频状态展示区域
        self.start_event = start_event

    def run_ui(self):
        """运行 UI 界面"""
        self.root = tk.Tk()
        self.root.title("会议展示界面")
        self.root.geometry("900x600")

        # 界面布局
        self.setup_ui()
        # 通知主线程 UI 已启动
        self.start_event.set()

        # 主循环
        self.root.mainloop()

    def close_ui(self):
        """关闭 UI 界面"""
        if self.root:
            self.root.destroy()

    def setup_ui(self):
        """设置 UI 布局"""
        # 上部分：文本信息展示
        text_frame = tk.Frame(self.root)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        tk.Label(text_frame, text="文本信息").pack(anchor=tk.W, padx=5, pady=2)
        self.text_area = ScrolledText(text_frame, wrap=tk.WORD, height=10)
        self.text_area.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 中部分：视频展示区域
        video_frame = tk.Frame(self.root, bg="black", height=250)
        video_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        tk.Label(video_frame, text="视频信息", bg="black", fg="white").pack(anchor=tk.NW, padx=5, pady=2)
        self.video_frame = tk.Label(video_frame, text="视频帧区域\n(接口留空待实现)", bg="gray", fg="white", width=100, height=10)
        self.video_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 下部分：音频信息展示
        audio_frame = tk.Frame(self.root)
        audio_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        tk.Label(audio_frame, text="音频信息").pack(anchor=tk.W, padx=5, pady=2)
        self.audio_info = tk.Label(audio_frame, text="音频状态：无音频\n(接口留空待实现)", bg="white", fg="black", width=80, height=5)
        self.audio_info.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    # --- 以下为接口方法，用于更新展示内容 ---

    def update_text(self, message):
        """
        更新文本信息
        :param message: 新的文本内容
        """
        self.text_area.insert(tk.END, message + "\n")
        self.text_area.see(tk.END)  # 自动滚动到底部

    def update_video_frame(self, frame):
        """
        更新视频帧内容
        :param frame: 视频帧数据（后续可以嵌入图像处理逻辑）
        """
        # 示例：在 UI 上显示一个占位符文本
        self.video_frame.config(text=f"更新视频帧: {frame}")

    def update_audio_info(self, audio_status):
        """
        更新音频状态
        :param audio_status: 音频状态（如：正在播放音频/静音）
        """
        self.audio_info.config(text=f"音频状态：{audio_status}")


# 示例运行
if __name__ == "__main__":
    cli = OperationInterface()
    cli.start_interface()


