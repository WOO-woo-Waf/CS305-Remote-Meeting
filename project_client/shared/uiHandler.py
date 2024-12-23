# import tkinter as tk
# from tkinter.scrolledtext import ScrolledText
#
# import cv2
# from PIL import Image, ImageTk
# import threading
# import queue
# import time
#
#
# class UIHandler:
#     _instance = None
#
#     def __new__(cls, *args, **kwargs):
#         if not cls._instance:
#             cls._instance = super(UIHandler, cls).__new__(cls)
#         return cls._instance
#
#     def __init__(self):
#         """初始化 UI 界面"""
#         self.root = None
#         self.text_area = None  # 文本信息区域
#         self.video_frame = None  # 视频展示区域
#         self.audio_canvas = None  # 音频波形显示区域
#         self.audio_status_label = None  # 音频状态标签
#         self.queue = queue.Queue()  # 线程安全的消息队列，用于线程间通信
#
#     def run_ui(self):
#         """运行 UI 界面"""
#         # 在副线程中初始化 Tkinter 主窗口
#         self.root = tk.Tk()
#         self.root.title("会议展示界面")
#         self.root.geometry("960x720")
#
#         # 设置 UI
#         self.setup_ui()
#
#         # 启动队列轮询
#         self.poll_queue()
#
#         # 主循环
#         self.root.mainloop()
#
#     def setup_ui(self):
#         """设置 UI 布局"""
#         # 文本信息区域（顶部）
#         text_frame = tk.Frame(self.root)
#         text_frame.pack(fill=tk.BOTH, padx=10, pady=5, expand=False)
#
#         tk.Label(text_frame, text="文本信息", anchor="w").pack(anchor=tk.W, padx=5, pady=2)
#         self.text_area = ScrolledText(text_frame, wrap=tk.WORD, height=6)
#         self.text_area.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
#
#         # 视频展示区域（中间）
#         video_frame = tk.Frame(self.root, bg="black")
#         video_frame.pack(fill=tk.BOTH, padx=10, pady=5, expand=True)
#
#         tk.Label(video_frame, text="视频区域", bg="black", fg="white").pack(anchor=tk.W, padx=5, pady=2)
#         self.video_frame = tk.Label(video_frame, bg="gray")
#         self.video_frame.pack(fill=tk.BOTH, expand=False, padx=5, pady=5)
#
#         # 音频状态区域（底部）
#         audio_frame = tk.Frame(self.root)
#         audio_frame.pack(fill=tk.BOTH, padx=10, pady=5, expand=False)
#
#         tk.Label(audio_frame, text="音频状态", anchor="w").pack(anchor=tk.W, padx=5, pady=2)
#         self.audio_canvas = tk.Canvas(audio_frame, bg="white", height=60)
#         self.audio_canvas.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
#         self.audio_status_label = tk.Label(audio_frame, text="音频状态：无音频", anchor="w", bg="white")
#         self.audio_status_label.pack(anchor=tk.W, padx=5, pady=5)
#
#     def update_text(self, message):
#         """通过队列将任务发送到主线程"""
#         self.queue.put(lambda: self._update_text_in_main_thread(message))
#
#     def _update_text_in_main_thread(self, message):
#         """在主线程中更新文本区域"""
#         if self.text_area:
#             self.text_area.insert(tk.END, message + "\n")
#             self.text_area.see(tk.END)  # 自动滚动到底部
#
#     def update_video_frame(self, frame):
#         """
#         接收 OpenCV 的帧数据，并更新视频区域
#         :param frame: OpenCV 读取的帧数据 (BGR 格式)
#         """
#         self.queue.put(lambda: self._update_video_frame_in_main_thread(frame))
#
#     def _update_video_frame_in_main_thread(self, frame):
#         """
#         在主线程中更新视频帧内容
#         :param frame: OpenCV 的帧数据 (BGR 格式)
#         """
#         try:
#             # 将 OpenCV 的帧从 BGR 转为 RGB
#             frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
#
#             # 将 NumPy 数组转换为 PIL 图像
#             image = Image.fromarray(frame_rgb)
#             image = image.resize((960, 540), Image.Resampling.LANCZOS)  # 调整分辨率为视频显示区域大小
#
#             # 转换为 Tkinter 可用的图像
#             photo = ImageTk.PhotoImage(image)
#
#             # 更新视频区域的图像
#             self.video_frame.config(image=photo)
#             self.video_frame.image = photo  # 防止垃圾回收
#         except Exception as e:
#             print(f"更新视频帧失败: {e}")
#
#     def update_audio_status(self, audio_status, waveform=None):
#         """通过队列将音频状态更新任务发送到主线程"""
#         self.queue.put(lambda: self._update_audio_status_in_main_thread(audio_status, waveform))
#
#     def _update_audio_status_in_main_thread(self, audio_status, waveform):
#         """在主线程中更新音频状态和波形"""
#         self.audio_status_label.config(text=f"音频状态：{audio_status}")
#
#         # 清空波形画布
#         self.audio_canvas.delete("all")
#         if waveform:
#             width = self.audio_canvas.winfo_width()
#             height = self.audio_canvas.winfo_height()
#             step = max(1, len(waveform) // width)
#             points = [
#                 (i, height // 2 - int(waveform[i * step] * (height // 2)))
#                 for i in range(width)
#             ]
#             for x, y in points:
#                 self.audio_canvas.create_line(x, height // 2, x, y, fill="blue")
#
#     def poll_queue(self):
#         """定期检查队列并执行任务"""
#         while not self.queue.empty():
#             task = self.queue.get()
#             task()  # 执行队列中的任务
#         # 调度下一次轮询
#         if self.root:
#             self.root.after(100, self.poll_queue)


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

        # # 中部分：视频展示区域
        # video_frame = tk.Frame(self.root, bg="black", height=250)
        # video_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        #
        # tk.Label(video_frame, text="视频信息", bg="black", fg="white").pack(anchor=tk.NW, padx=5, pady=2)
        # self.video_frame = tk.Label(video_frame, text="视频帧区域\n(接口留空待实现)", bg="gray", fg="white", width=100,
        #                             height=10)
        # self.video_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        #
        # # 下部分：音频信息展示
        # audio_frame = tk.Frame(self.root)
        # audio_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        #
        # tk.Label(audio_frame, text="音频信息").pack(anchor=tk.W, padx=5, pady=2)
        # self.audio_info = tk.Label(audio_frame, text="音频状态：无音频\n(接口留空待实现)", bg="white", fg="black",
        #                            width=80, height=5)
        # self.audio_info.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

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