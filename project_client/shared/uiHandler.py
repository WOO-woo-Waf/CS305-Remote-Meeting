import asyncio
import threading
import tkinter as tk
import aioconsole
from tkinter.scrolledtext import ScrolledText


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
        self.video_frame = tk.Label(video_frame, text="视频帧区域\n(接口留空待实现)", bg="gray", fg="white", width=100,
                                    height=10)
        self.video_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 下部分：音频信息展示
        audio_frame = tk.Frame(self.root)
        audio_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        tk.Label(audio_frame, text="音频信息").pack(anchor=tk.W, padx=5, pady=2)
        self.audio_info = tk.Label(audio_frame, text="音频状态：无音频\n(接口留空待实现)", bg="white", fg="black",
                                   width=80, height=5)
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