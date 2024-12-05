# 音视频采集和播放模块，负责操作摄像头和麦克风。
import asyncio
import time

import cv2
import pyaudio
import threading
import pyautogui
from PIL import Image
import numpy as np


class MediaManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(MediaManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, rtp_client, target_fps=30):
        """
        初始化媒体管理器，负责管理摄像头、麦克风和屏幕录制。
        :param rtp_client: RTP 客户端实例，用于发送音视频数据
        """
        self.rtp_client = rtp_client
        self.running = False  # 控制线程状态
        self.target_fps = target_fps

    def start_camera(self):
        """
        打开摄像头，捕获视频帧并发送。
        """
        cap = cv2.VideoCapture(0)
        self.running = True

        def capture_video():
            while self.running:
                ret, frame = cap.read()

                if not ret:
                    print("Failed to capture video frame.")
                    break

                # 压缩视频帧
                _, buffer = cv2.imencode(".jpg", frame)
                video_data = buffer.tobytes()

                # 发送视频帧
                self.rtp_client.send_video(video_data)

            cap.release()

        threading.Thread(target=capture_video, daemon=True).start()
        print("Camera started.")

    def start_microphone(self):
        """
        打开麦克风，捕获音频数据并发送。
        """
        audio = pyaudio.PyAudio()
        stream = audio.open(format=pyaudio.paInt16, channels=1, rate=44100, input=True, frames_per_buffer=1024)
        self.running = True

        def capture_audio():
            while self.running:
                try:
                    audio_data = stream.read(1024, exception_on_overflow=False)
                    asyncio.run(self.rtp_client.send_audio(audio_data))
                except Exception as e:
                    # print("Error capturing audio:", e)
                    pass

            stream.stop_stream()
            stream.close()
            audio.terminate()

        threading.Thread(target=capture_audio, daemon=True).start()
        print("Microphone started.")

    def start_screen_recording(self):
        """
        开始屏幕录制，捕获屏幕图像并发送。
        """
        self.running = True
        screen_size = pyautogui.size()
        # 计算每帧的时间间隔（秒）
        frame_interval = 1 / self.target_fps

        def capture_screen():
            while self.running:
                start_time = time.time()  # 记录当前时间
                # 截取屏幕
                screen = pyautogui.screenshot()
                self.rtp_client.ui_handler.update_video_frame(self.rtp_client.client_id, screen)
                if screen is None:
                    print("Failed to capture screen.")
                    continue

                # print(screen)
                # 将 PIL 图像转换为 numpy 数组
                frame = np.array(screen)
                # 转换颜色格式（PIL 默认是 RGB，OpenCV 需要 BGR）
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

                # 压缩图像为 JPEG 格式
                # _, buffer = cv2.imencode('.jpg', frame)
                _, buffer = cv2.imencode('.png', frame)
                screen_data = buffer.tobytes()
                # 使用 asyncio.ensure_future 调度 send_video
                asyncio.run(self.rtp_client.send_video(screen_data))
                # 计算本次处理的时间
                elapsed_time = time.time() - start_time
                # 计算剩余时间，确保帧率稳定
                time_to_wait = max(0, frame_interval - elapsed_time)
                time.sleep(time_to_wait)  # 休眠，等待合适的时间间隔

        threading.Thread(target=capture_screen, daemon=True).start()
        print("Screen recording started.")



    def stop(self):
        """
        停止所有媒体捕获。
        """
        self.running = False
        print("All media capturing stopped.")
