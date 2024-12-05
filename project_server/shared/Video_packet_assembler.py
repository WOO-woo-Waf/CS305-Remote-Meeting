import cv2
import numpy as np


class VideoPacketAssembler:
    def __init__(self, frame_width, frame_height, packet_size=32767):
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.packet_size = packet_size  # 每个视频包的大小（最大值）
        self.total_packets = 0  # 视频包的总数
        self.packets_received = 0  # 已接收的视频包数
        self.packets = {}  # 存储接收到的视频包

    def start_assembling(self, total_packets):
        """
        初始化视频包的合并。
        :param total_packets: 视频包的总数
        """
        self.total_packets = total_packets
        self.packets_received = 0
        self.packets = {}  # 清空之前的包

    def add_packet(self, packet_data, sequence_number):
        """
        将视频包添加到组装器，并合并完整帧。
        :param packet_data: 视频包数据
        :param sequence_number: 包的序列号
        :return: 如果所有包合并完成，返回完整帧；否则返回 None。
        """
        # 存储接收到的视频包
        self.packets[sequence_number] = packet_data
        self.packets_received += 1

        # 检查是否所有包都已接收
        if self.packets_received % self.total_packets == 0:
            # 合并所有视频包
            # 按照序列号排序视频包并合并
            sorted_packets = [self.packets[i] for i in sorted(self.packets.keys())]
            video_frame = b''.join(sorted_packets)  # 合并所有视频包的数据

            # 处理合并后的完整帧
            return self.create_frame_from_data(video_frame)

        return None  # 如果包没有全部到齐，返回 None

    def create_frame_from_data(self, video_data):
        """
        从字节数据创建完整的视频帧。
        :param video_data: 合并后的完整视频帧数据
        :return: OpenCV 图像（frame）
        """
        # 将字节数据转换为 OpenCV 图像
        frame_array = np.frombuffer(video_data, dtype=np.uint8)
        frame = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)
        return frame