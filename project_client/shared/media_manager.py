import asyncio
import time
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

        # 视频播放相关
        self.video_queues = {}  # 每个客户端的视频队列
        self.video_threads = {}  # 每个客户端的播放线程
        self.video_running = True

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

        asyncio.create_task(self.capture_camera_frame(cap))
        print("Camera started.")

    async def capture_camera_frame(self,cap):
        while self.camera_running:
            start_time = time.time()
            ret, frame = cap.read()
            if not ret:
                print("Failed to capture video frame.")
                break

            # 调整分辨率
            frame = cv2.resize(frame, (self.width, self.height))

            # 立即压缩和发送
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), self.compression_quality[self.video_quality]]
            _, buffer = cv2.imencode(".jpg", frame, encode_param)
            await self.rtp_client.send_video(buffer.tobytes())

            # 确保帧率稳定
            elapsed_time = time.time() - start_time
            if elapsed_time < self.frame_interval:
                await asyncio.sleep(self.frame_interval - elapsed_time)

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
                # frame = cv2.resize(frame, (self.width, self.height))
                self.process_and_send(screen_data=frame)

                # 确保帧率稳定
                elapsed_time = time.time() - start_time
                if elapsed_time < self.frame_interval:
                    time_to_wait = self.frame_interval - elapsed_time
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

    async def play_video_stream(self, client_id, video_queue):
        """
        播放特定客户端的视频流。
        :param client_id: 客户端 ID。
        :param video_queue: 客户端的视频队列。
        """
        idle_timeout = 3  # 设置队列为空的最大等待时间（秒）
        last_frame_time = time.time()  # 记录最后一次获取帧的时间

        while self.video_running:
            try:
                # 检查队列是否为空
                if video_queue.empty():
                    elapsed_since_last_frame = time.time() - last_frame_time
                    if elapsed_since_last_frame > idle_timeout:
                        print(f"No frames received for client {client_id} for {idle_timeout} seconds. Closing window.")
                        break  # 长时间没有新帧，退出播放任务

                # 获取新帧
                frame = await asyncio.wait_for(video_queue.get(), timeout=idle_timeout)
                if frame is None:  # 退出信号
                    break

                # 更新最后获取帧的时间
                last_frame_time = time.time()

                # 显示视频帧
                resized_frame = cv2.resize(frame, (self.width, self.height))
                cv2.imshow(f"Video Stream - Client {client_id}", resized_frame)
                key = cv2.waitKey(1)
                if key == ord('q'):
                    await self.stop_video_display(client_id)
                    break

            except asyncio.TimeoutError:
                # 超时未收到新帧，退出播放
                print(f"No frames received for client {client_id} within timeout. Closing window.")
                break
            except Exception as e:
                print(f"Error displaying video for client {client_id}: {e}")

        # 清理显示窗口
        cv2.destroyWindow(f"Video Stream - Client {client_id}")
        del self.video_queues[client_id]

    async def add_video(self, client_id, frame):
        """
        添加视频帧到对应客户端的视频队列。
        如果客户端不存在，则创建新的队列和播放任务。
        :param client_id: 客户端 ID。
        :param frame: 视频帧。
        """
        if client_id not in self.video_queues:
            # 创建新的视频队列和播放任务
            video_queue = asyncio.Queue()
            self.video_queues[client_id] = video_queue
            self.video_threads[client_id] = asyncio.create_task(self.play_video_stream(client_id, video_queue))

        # 将帧加入队列
        await self.video_queues[client_id].put(frame)

    async def start_video_display(self, client_id):
        """
        启动客户端的视频播放。
        :param client_id: 客户端 ID。
        """
        if client_id in self.video_threads and self.video_running.get(client_id, False):
            print(f"Video display for client {client_id} is already running.")
            return

        # 创建新的视频队列和播放任务
        self.video_queues[client_id] = asyncio.Queue(maxsize=10)
        self.video_threads[client_id] = asyncio.create_task(self.play_video_stream(client_id, self.video_queues[client_id]))
        print(f"Started video display for client {client_id}.")

    async def stop_video_display(self, client_id):
        """
        停止特定客户端的视频流。
        :param client_id: 客户端 ID。
        """
        if client_id in self.video_threads:
            self.video_running[client_id] = False
            await self.video_queues[client_id].put(None)  # 发送退出信号
            await self.video_threads[client_id]
            await self.cleanup_client(client_id)
            print(f"Stopped video display for client {client_id}.")

    async def cleanup_client(self, client_id):
        """
        清理客户端资源。
        :param client_id: 客户端 ID。
        """
        if client_id in self.video_threads:
            del self.video_threads[client_id]
        if client_id in self.video_queues:
            del self.video_queues[client_id]
        if client_id in self.video_running:
            del self.video_running[client_id]
        print(f"Cleaned up resources for client {client_id}.")

    def stop_all(self):
        """
        停止所有媒体捕获和播放。
        """
        self.stop_camera()
        self.stop_microphone()
        self.stop_screen_recording()
        asyncio.run(self.stop_video_display())  # 停止所有视频播放
        print("All media capturing and playback stopped.")
