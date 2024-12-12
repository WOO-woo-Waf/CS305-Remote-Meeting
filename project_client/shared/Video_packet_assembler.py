import cv2
import ffmpeg
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

