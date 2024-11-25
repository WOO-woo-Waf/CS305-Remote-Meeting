import asyncio
import socket
import struct
import uuid
import cv2
import pyaudio
import threading
import numpy as np
from collections import deque


class RTPClient:
    def __init__(self, server_ip, server_port, client_ip="0.0.0.0", client_port=0, client_id=None):
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
        self.client_id = client_id or str(uuid.uuid4())  # 自动生成 UUID
        self.meeting_id = None  # 将在会话中指定会议 ID

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

        print(f"RTP Client initialized with IP {self.client_ip} and port {self.client_port}")

    def create_rtp_packet(self, payload_type, payload):
        """
        创建 RTP 数据包。
        :param payload_type: 数据类型 (0x01: 视频, 0x02: 音频)
        :param payload: 负载数据
        :return: RTP 数据包
        """
        payload_length = len(payload)
        header = struct.pack(
            '!BI16sI',
            payload_type,  # 数据类型
            payload_length,  # 数据长度
            uuid.UUID(self.client_id).bytes,  # 客户端 ID
            self.meeting_id  # 会议 ID
        )
        return header + payload

    def parse_rtp_packet(self, packet):
        """
        解析 RTP 数据包。
        :param packet: RTP 数据包
        :return: RTP 包头和负载
        """
        header_length = 36  # 固定头部长度
        header = packet[:header_length]
        payload = packet[header_length:]
        payload_type, payload_length = struct.unpack("!BI", header[:5])
        client_id = uuid.UUID(bytes=header[5:21])  # 解析 UUID
        meeting_id = struct.unpack("!I", header[21:25])[0]

        return {
            "payload_type": payload_type,
            "payload_length": payload_length,
            "client_id": str(client_id),
            "meeting_id": meeting_id,
            "payload": payload
        }

    async def send_data(self, payload_type, payload):
        """
        发送数据到 RTP 服务器。
        :param payload_type: 数据类型 (0x01: 视频, 0x02: 音频)
        :param payload: 数据内容
        """
        if not self.meeting_id:
            raise ValueError("Meeting ID is not set. Please set meeting_id before sending data.")
        packet = self.create_rtp_packet(payload_type, payload)
        self.sock.sendto(packet, (self.server_ip, self.server_port))
        print(f"Sent RTP packet to {self.server_ip}:{self.server_port}")

    async def receive_data(self):
        """
        接收 RTP 数据包并解析。
        """
        loop = asyncio.get_event_loop()
        while True:
            try:
                # 接收批量 RTP 数据包
                data, addr = await loop.sock_recv(self.sock, 65535)
                self.buffer.extend(data.split(b'|END|'))  # 假设服务端以 '|END|' 分隔多个 RTP 包
                self.process_buffer()
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

