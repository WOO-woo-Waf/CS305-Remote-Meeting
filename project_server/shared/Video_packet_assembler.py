import queue
import threading
import time

import cv2
import ffmpeg
import numpy as np


class VideoPacketAssembler:
    def __init__(self, frame_width, frame_height, packet_size=65000):
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.packet_size = packet_size  # 每个视频包的大小（最大值）
        self.total_packets = 0  # 视频包的总数
        self.packets_received = 0  # 已接收的视频包数
        self.packets = {}  # 存储接收到的视频包
        # 队列存储解码后的帧
        self.decoded_frames_queue = queue.Queue()
        # 初始化异步解码器，并传入回调函数
        self.frame_callback = None
        # self.async_decoder = AsyncDecoder(960, 540, self._on_frame_decoded)
        # self.async_decoder.start()
        self.process = (
            ffmpeg
            .input('pipe:0', format='h264')  # 输入是 H.264 编码的流
            .output('pipe:1', format='rawvideo', pix_fmt='bgr24', s=f'{self.frame_width}x{self.frame_height}', flags='low_delay')
            .run_async(pipe_stdin=True, pipe_stdout=True, pipe_stderr=True)
        )

    def start_assembling(self, total_packets):
        """
        初始化视频包的合并。
        :param total_packets: 视频包的总数
        """
        self.total_packets = total_packets
        self.packets_received = 0
        self.packets = {}  # 清空之前的包

    def add_packet(self, packet_data, sequence_number, total_packets):
        """
        将视频包添加到组装器，并合并完整帧。
        :param packet_data: 视频包数据
        :param sequence_number: 包的序列号
        :return: 如果所有包合并完成，返回完整帧；否则返回 None。
        """
        # 存储接收到的视频包
        # print(f"Received packet {sequence_number}.")
        self.packets[sequence_number] = packet_data
        self.packets_received += 1

        # 检查是否所有包都已接收
        if sequence_number == total_packets:
            # 合并所有视频包
            # 按照序列号排序视频包并合并
            sorted_packets = [self.packets[i] for i in sorted(self.packets.keys())]
            video_frame = b''.join(sorted_packets)  # 合并所有视频包的数据

            # 异步解码
            # print(f"Decoding video frame with {len(video_frame)} bytes.")
            # self.async_decoder.decode_async(video_frame)
            frame = self.create_frame_from_data(video_frame)
            # print(f"{len(frame)}")
            return frame

        return None  # 如果包没有全部到齐，返回 None

    def stop(self):
        """停止解码器"""
        self.async_decoder.stop()

    def _on_frame_decoded(self, frame):
        """将解码后的帧放入队列"""
        print("Decoded frame received.")
        self.decoded_frames_queue.put(frame)

    def get_decoded_frame(self):
        """从队列中获取解码后的帧"""
        # print("Getting decoded frame.")
        # print(self.decoded_frames_queue.qsize())
        try:
            return self.decoded_frames_queue.get(block=False)
        except queue.Empty:
            return None  # 如果超时没有帧可用，返回 None

    def decode(self, frame_data):
        """
        解码单个视频帧。
        :param frame_data: H.264 编码的视频帧数据
        :return: 解码后的 OpenCV 图像帧
        """
        if len(frame_data) == 0:
            raise ValueError("Received empty frame data.")

        try:
            # 将编码数据写入 FFmpeg stdin
            self.process.stdin.write(frame_data)

            # 从 FFmpeg stdout 获取解码后的数据
            decoded_data = self.process.stdout.read(self.frame_width * self.frame_height * 3)  # BGR24 每像素 3 字节

            # 检查解码是否成功
            if len(decoded_data) == 0:
                raise ValueError("FFmpeg returned no data after decoding.")

            # 将字节数据转为 NumPy 数组，表示 BGR 格式图像
            frame = np.frombuffer(decoded_data, np.uint8).reshape((self.frame_width, self.frame_height, 3))

            return frame
        except Exception as e:
            print(f"Error during persistent decoding: {str(e)}")
            raise

    def create_frame_from_data(self, video_data):
        """
        从字节数据创建完整的视频帧。
        :param video_data: 合并后的完整视频帧数据
        :return: OpenCV 图像（frame）
        """
        # 将字节数据转换为 OpenCV 图像
        # frame_array = np.frombuffer(video_data, dtype=np.uint8)
        # frame = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)
        frame = decode_h264_with_ffmpeg(video_data)
        return frame


def decode_h264_with_ffmpeg(frame_data, width=960, height=540):
    if len(frame_data) == 0:
        raise ValueError("Received empty frame data.")

    # 使用 FFmpeg 解码 H.264 数据
    try:
        # 创建 FFmpeg 解码器命令
        process = (
            ffmpeg
            .input('pipe:0', format='h264')  # 输入是 H.264 编码的流
            .output('pipe:1', format='rawvideo', pix_fmt='bgr24', s=f'{width}x{height}', flags='low_delay')
            .run_async(pipe_stdin=True, pipe_stdout=True, pipe_stderr=True)
        )

        # 将编码数据写入 FFmpeg stdin，获取解码后的数据流
        decoded_data, stderr = process.communicate(input=frame_data)

        # # 输出 FFmpeg 错误信息，帮助调试
        # if stderr:
        #     print("FFmpeg stderr:", stderr.decode('utf-8'))

        # 检查解码是否成功
        if len(decoded_data) == 0:
            raise ValueError("FFmpeg returned no data after decoding.")

        # 将字节数据转为 NumPy 数组，表示 BGR 格式图像
        frame = np.frombuffer(decoded_data, np.uint8).reshape((height, width, 3))  # 根据分辨率调整形状

        return frame
    except Exception as e:
        print(f"Error during decoding: {str(e)}")
        raise


class PersistentFFmpegDecoder:
    """
    持久化的 FFmpeg 解码器，用于减少每帧重启解码进程的开销。
    """

    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.process = (
            ffmpeg
            .input('pipe:0', format='h264')  # 输入是 H.264 编码的流
        .output('pipe:1', format='rawvideo', pix_fmt='bgr24', s=f'{width}x{height}', flags='low_delay')
        .run_async(pipe_stdin=True, pipe_stdout=True, pipe_stderr=True)
        )

    def decode(self, frame_data):
        """
        解码单个视频帧。
        :param frame_data: H.264 编码的视频帧数据
        :return: 解码后的 OpenCV 图像帧
        """
        if len(frame_data) == 0:
            raise ValueError("Received empty frame data.")

        try:
            # 将编码数据写入 FFmpeg stdin
            self.process.stdin.write(frame_data)

            # 从 FFmpeg stdout 获取解码后的数据
            decoded_data = self.process.stdout.read(self.width * self.height * 3)  # BGR24 每像素 3 字节

            # 检查解码是否成功
            if len(decoded_data) == 0:
                raise ValueError("FFmpeg returned no data after decoding.")

            # 将字节数据转为 NumPy 数组，表示 BGR 格式图像
            frame = np.frombuffer(decoded_data, np.uint8).reshape((self.height, self.width, 3))

            return frame
        except Exception as e:
            print(f"Error during persistent decoding: {str(e)}")
            self.close()
            raise

    def close(self):
        """关闭解码器进程"""
        self.process.stdin.close()
        self.process.stdout.close()
        self.process.stderr.close()
        self.process.wait()


class AsyncDecoder:
    """
    异步解码器，将解码任务放入独立线程处理。
    """

    def __init__(self, width, height, callback):
        self.thread = None
        self.decoder = PersistentFFmpegDecoder(width, height)
        self.frame_queue = queue.Queue()
        self.stop_flag = threading.Event()
        self.callback = callback

    def decode_async(self, frame_data):
        """
        将解码任务放入队列。
        :param frame_data: H.264 编码的视频帧数据
        """
        # print("decode_async called.")
        self.frame_queue.put(frame_data)

    def start(self):
        """启动解码线程"""
        self.thread = threading.Thread(target=self._decode_loop, daemon=True)
        self.thread.start()

    def _decode_loop(self):
        """后台解码线程"""
        print("Decoder thread started.")
        while not self.stop_flag.is_set():
            # print("Decoder thread running.")
            if not self.frame_queue.empty():
                frame_data = self.frame_queue.get(block=False)
                print(f"Decoding frame with {len(frame_data)} bytes.")
                try:
                    frame = self.decoder.decode(frame_data)
                    # TODO: 在这里处理解码后的帧，例如显示或保存
                    # 通过回调返回解码后的帧
                    self.callback(frame)
                except Exception as e:
                    print(f"Decode error: {e}")
                    time.sleep(0.01)

    def stop(self):
        """停止解码线程"""
        self.stop_flag.set()
        self.thread.join()
        self.decoder.close()
