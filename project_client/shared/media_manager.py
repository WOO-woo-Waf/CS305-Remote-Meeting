import asyncio
import time
from turtledemo.penrose import start

import cv2
import pyaudio
import threading
import pyautogui
import numpy as np


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

        # 视频质量设置
        self.video_quality = "medium"
        self.resolution_settings = {
            "low": (640, 360),
            "medium": (1280, 720),
            "high": (1920, 1080)
        }
        self.compression_quality = {
            "low": 50,
            "medium": 75,
            "high": 90
        }
        self.width, self.height = self.resolution_settings[self.video_quality]
        self.set_video_quality(self.video_quality)

    def set_video_quality(self, quality):
        """
        设置视频质量，包括分辨率和压缩率。
        """
        if quality not in self.resolution_settings:
            raise ValueError("Invalid video quality. Choose from 'low', 'medium', 'high'.")
        self.video_quality = quality
        self.width, self.height = self.resolution_settings[quality]
        print(f"Video quality set to {quality}. Resolution: {self.width}x{self.height}, Compression Quality: {self.compression_quality[quality]}")

    def start_camera(self):
        """
        打开摄像头，捕获视频帧并发送。
        """
        cap = cv2.VideoCapture(0)
        self.camera_running = True

        def capture_video():
            while self.camera_running:
                start_time = time.time()
                ret, frame = cap.read()
                if not ret:
                    print("Failed to capture video frame.")
                    break

                # 调整分辨率
                frame = cv2.resize(frame, (self.width, self.height))
                self.process_and_send(video_data=frame)

                # 确保帧率稳定
                elapsed_time = time.time() - start_time
                time_to_wait = max(0, self.frame_interval - elapsed_time)
                time.sleep(time_to_wait)

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

        def capture_screen():
            while self.screen_running:
                start_time = time.time()

                # 截取屏幕并调整分辨率
                screen = pyautogui.screenshot()
                frame = np.array(screen)
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                frame = cv2.resize(frame, (self.width, self.height))
                self.process_and_send(screen_data=frame)

                # 确保帧率稳定
                elapsed_time = time.time() - start_time
                time_to_wait = max(0, self.frame_interval - elapsed_time)
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
        if video_data is not None or screen_data is not None:
            # 如果有视频和屏幕帧，进行合成
            if video_data is not None and screen_data is not None:
                video_frame = video_data
                screen_frame = screen_data

                # 调整屏幕帧大小与视频帧一致
                screen_frame = cv2.resize(screen_frame, (self.width, self.height))

                # 缩小摄像头内容
                small_frame_height = 160
                small_frame_width = 160
                small_frame = cv2.resize(video_frame, (small_frame_width, small_frame_height))

                # 定义摄像头画面放置位置（右下角）
                x_offset = screen_frame.shape[1] - small_frame_width - 20
                y_offset = screen_frame.shape[0] - small_frame_height - 20

                # 将小画面嵌入屏幕录制内容中
                combined_frame = screen_frame.copy()
                combined_frame[y_offset:y_offset + small_frame_height, x_offset:x_offset + small_frame_width] = small_frame

                # 压缩合成后的图像
                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), self.compression_quality[self.video_quality]]
                _, combined_buffer = cv2.imencode(".jpg", combined_frame, encode_param)
                asyncio.run(self.rtp_client.send_video(combined_buffer.tobytes()))

            # 单独处理视频帧
            elif video_data is not None:
                frame = cv2.resize(video_data, (self.width, self.height))
                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), self.compression_quality[self.video_quality]]
                _, buffer = cv2.imencode(".jpg", frame, encode_param)
                asyncio.run(self.rtp_client.send_video(buffer.tobytes()))

            # 单独处理屏幕帧
            elif screen_data is not None:
                frame = cv2.resize(screen_data, (self.width, self.height))
                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), self.compression_quality[self.video_quality]]
                _, buffer = cv2.imencode(".jpg", frame, encode_param)
                asyncio.run(self.rtp_client.send_video(buffer.tobytes()))

        # 处理音频数据
        if audio_data is not None:
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
                    frame = self.frame_queue.pop(0)
                    resized_frame = cv2.resize(frame, (self.width, self.height))
                    cv2.imshow("Video Stream", resized_frame)
                    key = cv2.waitKey(1)
                    if key == ord('q'):
                        self.stop_video_display()
                        break

        threading.Thread(target=display_thread, daemon=True).start()
        print("Video display thread started.")

    def stop_video_display(self):
        """
        停止视频显示。
        """
        self.display_running = False
        cv2.destroyAllWindows()
        print("Video display stopped.")
