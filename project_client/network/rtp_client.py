import asyncio
import socket
import struct
import time
import uuid
import cv2
import pyaudio
import threading
import numpy as np
from collections import deque

from project_client.shared.Video_packet_assembler import VideoPacketAssembler

MAX_UDP_PACKET_SIZE = 65000  # 定义一个最大 UDP 数据包大小，通常是 65535 字节


class RTPClient:
    def __init__(self, server_ip, server_port, client_port, client_id, meeting_id, client_ip="0.0.0.0"):
        """
        初始化 RTP 客户端。
        :param server_ip: RTP 服务器 IP
        :param server_port: RTP 服务器端口
        :param client_ip: 客户端本地 IP
        :param client_port: 客户端本地端口（默认 0 表示随机端口）
        :param client_id: 客户端 ID (UUID 格式)
        """
        self.server_ip = server_ip
        self.server_port = server_port
        self.client_id = client_id
        self.meeting_id = meeting_id

        # 接收缓冲区
        self.buffer = deque(maxlen=20)  # 设置缓冲区大小（可根据需求调整）

        # 音频播放初始化
        self.audio_player = pyaudio.PyAudio()
        self.audio_stream = self.audio_player.open(format=pyaudio.paInt16,
                                                   channels=1,
                                                   rate=44100,
                                                   output=True)

        # UDP 套接字
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setblocking(False)
        self.sock.bind((client_ip, client_port))  # 为客户端分配本地 IP 和端口
        self.client_ip, self.client_port = self.sock.getsockname()

        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 * 1024 * 1024)  # 增加接收缓冲区
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 8 * 1024 * 1024)  # 增加发送缓冲区

        print(f"RTP Client initialized with IP {self.client_ip} and port {self.client_port}")
        # ui.update_text(f"RTP Client initialized with IP {self.client_ip} and port {self.client_port}")
        self.video_assemblers = None  # 视频包组装器
        self.frame_interval = 1 / 5  # 视频帧之间的时间间隔（30 FPS）
        asyncio.create_task(self.receive_data())  # 开启接收任务

    # def create_rtp_packet(self, payload_type, payload):
    #     """
    #     创建 RTP 数据包。
    #     :param payload_type: 数据类型 (0x01: 视频, 0x02: 音频)
    #     :param payload: 负载数据
    #     :return: RTP 数据包
    #     """
    #     # payload 应该是字节流，因此 length 应该是字节流的长度
    #     payload_length = len(payload)
    #
    #     # 确保 self.client_id 是一个有效的 UUID 字符串
    #     # uuid.UUID(self.client_id) 确保转换为 UUID 类型，然后转化为字节流
    #     client_id_bytes = uuid.UUID(self.client_id).bytes  # 转换为 16 字节的字节流
    #     if len(client_id_bytes) != 16:
    #         raise ValueError("client_id should be a valid UUID")
    #
    #     # 将 meeting_id 转换为字节流
    #     meeting_id_bytes = self.meeting_id.encode('utf-8')  # 将 meeting_id 字符串转为字节流
    #     # 填充字节流，如果长度小于 4 字节，填充为零
    #     meeting_id_bytes = meeting_id_bytes.ljust(4, b'\0')[:4]  # 保证长度为 4 字节
    #
    #     # 创建 RTP 头部（1 字节 payload_type + 2 字节 payload_length + 16 字节 client_id + 4 字节 meeting_id）
    #     header = struct.pack(
    #         '!BBH16s4s',  # 格式： 1 字节 (payload_type) + 2 字节 (payload_length) + 16 字节 UUID + 4 字节 meeting_id
    #         payload_type,  # 数据类型，视频或音频
    #         (payload_length >> 8) & 0xFF,  # 高 8 位
    #         payload_length & 0xFF,  # 低 8 位
    #         client_id_bytes,  # 客户端 ID（16 字节 UUID）
    #         meeting_id_bytes  # 会议 ID（4 字节）
    #     )
    #
    #     # 返回 RTP 数据包（头部 + 负载）
    #     return header + payload
    def create_rtp_packet(self, payload_type, payload, sequence_number, total_packets):
        """
        创建 RTP 数据包。
        :param payload_type: 数据类型 (0x01: 视频, 0x02: 音频)
        :param payload: 负载数据
        :param sequence_number: 包的序列号（用于视频包的排序）
        :param total_packets: 视频总包数（用于标记整个帧的分包数量）
        :return: RTP 数据包
        """
        # payload 应该是字节流，因此 length 应该是字节流的长度
        payload_length = len(payload)

        # 确保 self.client_id 是一个有效的 UUID 字符串
        client_id_bytes = uuid.UUID(self.client_id).bytes  # 转换为 16 字节的字节流
        if len(client_id_bytes) != 16:
            raise ValueError("client_id should be a valid UUID")

        # 将 meeting_id 转换为字节流
        meeting_id_bytes = self.meeting_id.encode('utf-8')  # 将 meeting_id 字符串转为字节流
        # 填充字节流，如果长度小于 4 字节，填充为零
        meeting_id_bytes = meeting_id_bytes.ljust(4, b'\0')[:4]  # 保证长度为 4 字节

        # 将序列号和总包数转换为字节流
        sequence_number_bytes = struct.pack('!H', sequence_number)  # 2 字节序列号
        total_packets_bytes = struct.pack('!H', total_packets)  # 2 字节总包数

        # 创建 RTP 头部（1 字节 payload_type + 2 字节 payload_length + 2 字节 sequence_number + 2 字节 total_packets + 16 字节
        # client_id + 4 字节 meeting_id）
        header = struct.pack(
            '!BBH16s4sHH',  # 格式： 1 字节 (payload_type) + 2 字节 (payload_length) + 2 字节 (sequence_number) + 2 字节 (
            # total_packets) + 16 字节 UUID + 4 字节 meeting_id
            payload_type,  # 数据类型，视频或音频
            (payload_length >> 8) & 0xFF,  # 高 8 位
            payload_length & 0xFF,  # 低 8 位
            client_id_bytes,  # 客户端 ID（16 字节 UUID）
            meeting_id_bytes,  # 会议 ID（4 字节）
            sequence_number,  # 包的序列号
            total_packets  # 视频总包数
        )

        # 返回 RTP 数据包（头部 + 负载）
        return header + payload

    def parse_rtp_packet(self, packet):
        """
        解析 RTP 数据包。
        :param packet: RTP 数据包（二进制字节流）
        :return: 包含头部信息和负载数据的字典
        """
        # RTP 头部格式：1 字节 payload_type + 2 字节 payload_length + 8 字节时间戳 + 2 字节 sequence_number + 2 字节 total_packets
        header_format = '!BBH8sHH'
        header_size = struct.calcsize(header_format)

        if len(packet) < header_size:
            raise ValueError("Invalid RTP packet: Header size is too small")

        # 解析头部
        header = packet[:header_size]
        payload = packet[header_size:]

        payload_type, high_length, low_length, timestamp_bytes, sequence_number, total_packets = struct.unpack(
            header_format, header)

        # 计算负载长度
        payload_length = (high_length << 8) | low_length

        # if len(payload) != payload_length:
        #     raise ValueError("Payload length mismatch")

        # 解析时间戳
        timestamp = struct.unpack('!Q', timestamp_bytes)[0]

        # 返回解析结果
        return {
            "payload_type": payload_type,
            "payload_length": payload_length,
            "timestamp": timestamp,
            "sequence_number": sequence_number,
            "total_packets": total_packets,
            "payload": payload
        }

    async def send_video(self, video_payload):
        """
        发送视频数据。
        :param video_payload: 捕获的视频帧数据
        """
        total_packets = len(video_payload) // MAX_UDP_PACKET_SIZE + 1  # 计算视频帧的总包数
        sequence_number = 0  # 初始化序列号
        while len(video_payload) > MAX_UDP_PACKET_SIZE:
            packet_part = video_payload[:MAX_UDP_PACKET_SIZE]
            # 检查数据包大小
            # print(f"Packet size: {len(packet_part)} bytes")
            sequence_number = sequence_number + 1
            await self.send_data(payload_type=0x01, payload=packet_part, sequence_number=sequence_number,
                                 total_packets=total_packets)
            video_payload = video_payload[MAX_UDP_PACKET_SIZE:]
        sequence_number = sequence_number + 1
        # 发送剩余的部分（如果有的话）
        if video_payload:
            await self.send_data(payload_type=0x01, payload=video_payload, sequence_number=sequence_number,
                                 total_packets=total_packets)

    async def send_audio(self, audio_data):
        """
        发送音频数据。
        :param audio_data: 捕获的音频数据
        """
        # 音频数据无需进一步编码（假设它已经是适合 RTP 传输的格式）
        await self.send_data(payload_type=0x02, payload=audio_data, sequence_number=0, total_packets=1)

    async def send_data(self, payload_type, payload, sequence_number, total_packets):
        """
        发送数据到 RTP 服务器。
        :param total_packets:
        :param sequence_number:
        :param payload_type: 数据类型 (0x01: 视频, 0x02: 音频)
        :param payload: 数据内容
        """
        if not self.meeting_id:
            raise ValueError("Meeting ID is not set. Please set meeting_id before sending data.")
        packet = self.create_rtp_packet(payload_type, payload, sequence_number, total_packets)
        self.sock.sendto(packet, (self.server_ip, self.server_port))
        # print(f"Sent RTP packet to {self.server_ip}:{self.server_port}")

    async def receive_data(self):
        """
        接收 RTP 数据包并解析。
        """
        loop = asyncio.get_event_loop()
        while True:
            try:
                # 接收批量 RTP 数据包
                data = await loop.sock_recv(self.sock, 65000)
                data_ = self.parse_rtp_packet(data)
                # print(f"Received RTP packet from : {data_["timestamp"]}")

                payload_type = data_["payload_type"]
                payload = data_["payload"]
                sequence_number = data_["sequence_number"]
                total_packets = data_["total_packets"]

                # 根据负载类型来播放数据
                if payload_type == 0x01:  # 视频类型
                    await asyncio.create_task(self.play_video(payload, sequence_number, total_packets))
                elif payload_type == 0x02:  # 音频类型
                    # print("Playing audio...")
                    self.play_audio(data_["payload"])

            except BlockingIOError:
                await asyncio.sleep(0.01)

    def process_buffer(self):
        """
        处理接收缓冲区中的 RTP 数据包。
        """
        while self.buffer:
            packet = self.buffer.popleft()
            if not packet:  # 如果分隔符导致空包，跳过
                continue
            rtp_data = self.parse_rtp_packet(packet)
            print(f"Processing RTP packet: {rtp_data}")
            if rtp_data["payload_type"] == 0x01:  # 视频数据
                self.handle_video_data(rtp_data["payload"])
            elif rtp_data["payload_type"] == 0x02:  # 音频数据
                self.handle_audio_data(rtp_data["payload"])

    def handle_video_data(self, video_payload):
        """
        处理视频数据并解码显示。
        :param video_payload: 视频负载数据
        """
        frame_array = np.frombuffer(video_payload, dtype=np.uint8)
        frame = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)
        if frame is not None:
            cv2.imshow("Video Stream", frame)
            cv2.waitKey(1)

    def handle_audio_data(self, audio_payload):
        """
        处理音频数据并播放。
        :param audio_payload: 音频负载数据
        """
        self.audio_stream.write(audio_payload)

    def set_meeting_id(self, meeting_id):
        """
        设置会议 ID。
        :param meeting_id: 会议 ID
        """
        self.meeting_id = meeting_id

    def play_audio(self, audio_payload):
        """
        播放音频数据。
        :param audio_payload: 音频数据
        """
        self.audio_stream.write(audio_payload)

    async def play_video(self, video_payload, sequence_number, total_packets):
        """
        解析视频数据并显示，处理视频包的合并。
        :param video_payload: 视频数据
        :param sequence_number: 视频包的序列号
        :param total_packets: 视频总包数
        """
        # 如果视频包组装器不存在，创建一个新的
        if self.video_assemblers is None:
            self.video_assemblers = VideoPacketAssembler(1920, 1080)
            self.video_assemblers.start_assembling(total_packets)

        # 将视频包添加到组装器中
        frame = self.video_assemblers.add_packet(video_payload, sequence_number)

        # 如果合并成功，播放视频
        if frame is not None:
            # print(f"Playing video stream {client_id} in meeting {meeting_id}")
            # 获取当前时间戳
            start_time = time.time()
            # 设置窗口大小并显示
            resized_frame = cv2.resize(frame, (960, 540))
            cv2.imshow("Video Stream_client", resized_frame)
            # cv2.imshow("Video Stream", frame)
            # 等待一段时间以确保帧率稳定
            elapsed_time = time.time() - start_time
            time_to_wait = max(0, self.frame_interval - elapsed_time)  # 计算剩余时间，确保帧率
            time.sleep(time_to_wait)  # 控制帧率，确保每秒显示 target_fps 帧
            cv2.waitKey(1)

