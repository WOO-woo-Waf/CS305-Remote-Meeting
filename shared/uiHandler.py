import tkinter as tk
from tkinter.scrolledtext import ScrolledText
from PIL import Image, ImageTk  # 确保已安装 Pillow 库

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
        self.video_container = None  # 视频展示容器
        self.start_event = start_event
        self.video_labels = {}  # 存储多个视频窗口的 Label，key为client_id

    def run_ui(self):
        """运行 UI 界面"""
        self.root = tk.Tk()
        self.root.title("会议展示界面")
        self.root.geometry("1200x800")  # 调整窗口大小以容纳更多视频

        # 界面布局
        self.setup_ui()
        # 通知主线程 UI 已启动
        if self.start_event:
            self.start_event.set()

        # 主循环
        self.root.mainloop()

    def close_ui(self):
        """关闭 UI 界面"""
        if self.root:
            self.root.destroy()

    def setup_ui(self):
        """设置 UI 布局"""
        # 上部分：文本信息展示（减小尺寸）
        text_frame = tk.Frame(self.root)
        text_frame.pack(fill=tk.BOTH, expand=False, padx=10, pady=5)  # expand=False

        tk.Label(text_frame, text="文本信息").pack(anchor=tk.W, padx=5, pady=2)
        self.text_area = ScrolledText(text_frame, wrap=tk.WORD, height=5)  # height=5
        self.text_area.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 中部分：视频展示区域（增大尺寸）
        video_frame = tk.Frame(self.root, bg="black", height=700)
        video_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        tk.Label(video_frame, text="视频信息", bg="black", fg="white").pack(anchor=tk.NW, padx=5, pady=2)
        self.video_container = tk.Frame(video_frame, bg="black")
        self.video_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 移除音频信息展示部分

    # --- 以下为接口方法，用于更新展示内容 ---

    def update_text(self, message):
        """
        更新文本信息
        :param message: 新的文本内容
        """
        self.text_area.insert(tk.END, message + "\n")
        self.text_area.see(tk.END)  # 自动滚动到底部

    def add_video_window(self, client_id, initial_frame=None):
        """
        添加一个新的视频窗口，并动态排列。
        :param client_id: 客户端的唯一标识符
        :param initial_frame: 初始显示的图像（PIL.Image 格式）
        """
        print(f"视频窗口 {client_id} 开始创建")
        if client_id in self.video_labels:
            print(f"视频窗口 {client_id} 已存在。")
            return

        # 创建一个 Label 用于显示视频帧
        video_label = tk.Label(self.video_container, bg="gray")
        self.video_labels[client_id] = video_label

        # 计算动态排列的行和列
        num_videos = len(self.video_labels)
        cols = 3  # 每行最多3个视频窗口，可以根据需要调整
        rows = (num_videos + cols - 1) // cols  # 计算需要的行数

        # 重新排列所有视频窗口
        for idx, (cid, lbl) in enumerate(self.video_labels.items()):
            row = idx // cols
            col = idx % cols
            lbl.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")

        # 配置行和列的权重，以便窗口自适应大小
        for r in range(rows):
            self.video_container.rowconfigure(r, weight=1)
        for c in range(cols):
            self.video_container.columnconfigure(c, weight=1)

        if initial_frame:
            self.update_video_frame(client_id, initial_frame)

    def update_video_frame(self, client_id, frame):
        """
        更新指定客户端的视频窗口内容。
        :param client_id: 客户端的唯一标识符
        :param frame: 视频帧数据（PIL.Image 格式）
        """
        if client_id not in self.video_labels:
            print(f"视频窗口 {client_id} 不存在，无法更新。")
            return

        # 进行裁剪操作（根据需要调整）
        width, height = frame.size
        left = 50
        top = 50
        right = width - 50
        bottom = height - 50
        cropped_frame = frame.crop((left, top, right, bottom))

        # 调整图像大小以适应 Label
        cropped_frame = cropped_frame.resize((400, 250))  # 根据需要调整大小

        # 转换为 ImageTk.PhotoImage
        photo_image = ImageTk.PhotoImage(cropped_frame)

        # 更新 Label 显示图像
        self.video_labels[client_id].config(image=photo_image)
        self.video_labels[client_id].image = photo_image  # 保持引用

    def remove_video_window(self, client_id):
        """
        移除指定客户端的视频窗口。
        :param client_id: 客户端的唯一标识符
        """
        if client_id not in self.video_labels:
            print(f"视频窗口 {client_id} 不存在，无法移除。")
            return

        self.video_labels[client_id].destroy()
        del self.video_labels[client_id]
