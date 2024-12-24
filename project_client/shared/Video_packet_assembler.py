import cv2
import ffmpeg
import numpy as np
import concurrent.futures
import asyncio


class VideoPacketAssembler:
    def __init__(self, frame_width, frame_height, packet_size=32767, max_workers=4):
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.packet_size = packet_size  # 每个视频包的大小（最大值）
        self.total_packets = 0  # 视频包的总数
        self.packets_received = 0  # 已接收的视频包数
        self.packets = {}  # 存储接收到的视频包
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)

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
        if sequence_number > total_packets or sequence_number <= 0:
            return None  # 丢弃无效包

        # 存储接收到的视频包
        # print(f"Received packet {sequence_number}.")
        self.packets[sequence_number] = packet_data
        self.packets_received += 1

        # 检查是否所有包都已接收
        if sequence_number == total_packets:
            # 按照序列号排序视频包并合并
            sorted_packets = [self.packets[i] for i in range(1, total_packets + 1) if i in self.packets]

            if len(sorted_packets) < total_packets:
                return None  # 丢弃未完整的帧
            video_frame = b''.join(sorted_packets)  # 合并所有视频包的数据
            self.packets.clear()  # 清理已处理的包
            self.packets_received = 0
            # 异步解码
            # print(f"Decoding video frame with {len(video_frame)} bytes.")
            # frame = await self._decode_and_resize(video_frame)
            frame = self.create_frame_from_data(video_frame)
            # print(f"{len(frame)}")
            return frame
        return None

    def create_frame_from_data(self, video_data):
        """
        从字节数据创建完整的视频帧。
        :param video_data: 合并后的完整视频帧数据
        :return: OpenCV 图像（frame）
        """
        # 将字节数据转换为 OpenCV 图像
        try:
            # 将字节数据转换为 OpenCV 图像
            frame_array = np.frombuffer(video_data, dtype=np.uint8)
            frame = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)

            # 验证解码结果
            if frame is None or frame.size == 0:
                raise ValueError("Failed to decode frame from video data.")

            # 调整帧大小为预期尺寸
            frame = cv2.resize(frame, (self.frame_width, self.frame_height))
            return frame

        except Exception as e:
            print(f"Error decoding video frame: {e}")
            return None

    async def _decode_and_resize(self, video_data):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, self._sync_decode_and_resize, video_data)

    def _sync_decode_and_resize(self, video_data):
        try:
            frame_array = np.frombuffer(video_data, dtype=np.uint8)
            frame = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)
            if frame is None or frame.size == 0:
                raise ValueError("Failed to decode frame from video data.")
            return frame
        except Exception as e:
            print(f"Error decoding video frame: {e}")
            return None

    def close(self):
        """
        关闭线程池以释放资源。
        """
        self.executor.shutdown(wait=True)
        print("ThreadPoolExecutor shut down.")
