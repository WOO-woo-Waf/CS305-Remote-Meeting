# 音视频采集和播放模块，负责操作摄像头和麦克风。
import asyncio
import time

import cv2
import ffmpeg
import pyaudio
import threading
import pyautogui
from PIL import Image
import numpy as np
import asyncio
import time


class MediaManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(MediaManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, rtp_client, target_fps=24):
        """
        初始化媒体管理器，负责管理摄像头、麦克风和屏幕录制。
        :param rtp_client: RTP 客户端实例，用于发送音视频数据
        """
        self.rtp_client = rtp_client
        self.camera_running = False
        self.microphone_running = False
        self.screen_running = False
        self.display_running = False
        self.target_fps = target_fps
        self.frame_interval = 1 / target_fps
        self.frame_queue = []  # 用于存储待显示的帧

    def start_camera(self):
        """
        打开摄像头，捕获视频帧并发送。
        """
        cap = cv2.VideoCapture(0)
        self.camera_running = True
        frame_interval = 1 / self.target_fps

        def capture_video():
            while self.camera_running:
                start_time = time.time()  # 记录当前时间
                ret, frame = cap.read()
                if not ret:
                    print("Failed to capture video frame.")
                    break

                # 压缩视频帧
                _, buffer = cv2.imencode(".jpg", frame)
                video_data = buffer.tobytes()
                self.process_and_send(video_data=video_data)

                # 计算本次处理的时间
                elapsed_time = time.time() - start_time
                # 计算剩余时间，确保帧率稳定
                if frame_interval - elapsed_time > 0:
                    time_to_wait = frame_interval - elapsed_time
                else:
                    time_to_wait = 0
                time.sleep(time_to_wait)  # 休眠，等待合适的时间间隔

            cap.release()

        threading.Thread(target=capture_video, daemon=True).start()
        print("Camera started.")

    def stop_camera(self):
        """
        停止摄像头捕获。
        """
        self.camera_running = False
        print("Camera stopped.")

    def start_microphone(self):
        """
        打开麦克风，捕获音频数据并发送。
        """
        audio = pyaudio.PyAudio()
        stream = audio.open(format=pyaudio.paInt16, channels=1, rate=44100, input=True, frames_per_buffer=1024)
        self.microphone_running = True

        def capture_audio():
            while self.microphone_running:
                try:
                    audio_data = stream.read(1024, exception_on_overflow=False)
                    self.process_and_send(audio_data=audio_data)
                except Exception as e:
                    print("Error capturing audio:", e)

            stream.stop_stream()
            stream.close()
            audio.terminate()

        threading.Thread(target=capture_audio, daemon=True).start()
        print("Microphone started.")

    def stop_microphone(self):
        """
        停止麦克风捕获。
        """
        self.microphone_running = False
        print("Microphone stopped.")

    def start_screen_recording(self):
        """
        开始屏幕录制，捕获屏幕图像并发送。
        """
        self.screen_running = True
        # 计算每帧的时间间隔（秒）
        frame_interval = 1 / self.target_fps

        def capture_screen():
            while self.screen_running:
                start_time = time.time()  # 记录当前时间
                # 截取屏幕
                screen = pyautogui.screenshot()
                if screen is None:
                    print("Failed to capture screen.")
                    continue

                # 将 PIL 图像转换为 numpy 数组
                frame = np.array(screen)
                # 转换颜色格式（PIL 默认是 RGB，OpenCV 需要 BGR）
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

                # 压缩图像为 JPEG 格式
                _, buffer = cv2.imencode('.jpg', frame)
                screen_data = buffer.tobytes()
                self.process_and_send(screen_data=screen_data)

                # 计算本次处理的时间
                elapsed_time = time.time() - start_time
                if elapsed_time < frame_interval:
                    time_to_wait = frame_interval - elapsed_time
                else:
                    time_to_wait = 0
                time.sleep(time_to_wait)

        threading.Thread(target=capture_screen, daemon=True).start()
        print("Screen recording started.")

    def stop_screen_recording(self):
        """
        停止屏幕录制。
        """
        self.screen_running = False
        print("Screen recording stopped.")

    def process_and_send(self, video_data=None, screen_data=None, audio_data=None):
        """
        处理和发送捕获的数据。
        如果有视频和屏幕数据，则合成后发送；否则分别发送。
        """
        if video_data and screen_data:
            # 解码图像数据
            video_frame = cv2.imdecode(np.frombuffer(video_data, dtype=np.uint8), cv2.IMREAD_COLOR)
            screen_frame = cv2.imdecode(np.frombuffer(screen_data, dtype=np.uint8), cv2.IMREAD_COLOR)

            # 调整屏幕帧大小与视频帧一致
            screen_frame = cv2.resize(screen_frame, (video_frame.shape[1], video_frame.shape[0]))

            # 合成图像（简单叠加）
            combined_frame = cv2.addWeighted(video_frame, 0.7, screen_frame, 0.3, 0)

            # 压缩合成后的图像
            _, combined_buffer = cv2.imencode(".jpg", combined_frame)
            asyncio.run(self.rtp_client.send_video(combined_buffer.tobytes()))

        elif video_data:
            asyncio.run(self.rtp_client.send_video(video_data))

        elif screen_data:
            asyncio.run(self.rtp_client.send_video(screen_data))

        if audio_data:
            asyncio.run(self.rtp_client.send_audio(audio_data))

    def stop_all(self):
        """
        停止所有媒体捕获。
        """
        self.stop_camera()
        self.stop_microphone()
        self.stop_screen_recording()
        print("All media capturing stopped.")

    def start_video_display(self):
        """
        启动一个独立线程，用于显示视频帧。
        """
        self.display_running = True

        def display_thread():
            while self.display_running:
                if self.frame_queue:
                    # 从队列中取出一帧
                    frame = self.frame_queue.pop(0)
                    start_time = time.time()

                    # 调整帧的大小
                    resized_frame = cv2.resize(frame, (960, 540))

                    # 显示帧
                    cv2.imshow("Video Stream", resized_frame)

                    # 检测退出按键
                    key = cv2.waitKey(1)
                    if key == ord('q'):
                        print("Exiting video display...")
                        self.stop_video_display()
                        break

                    # 控制帧率
                    elapsed_time = time.time() - start_time
                    time_to_wait = max(0, self.frame_interval - elapsed_time)
                    time.sleep(time_to_wait)

        threading.Thread(target=display_thread, daemon=True).start()
        print("Video display thread started.")

    def stop_video_display(self):
        """
        停止视频显示。
        """
        self.display_running = False
        cv2.destroyAllWindows()
        print("Video display stopped.")
