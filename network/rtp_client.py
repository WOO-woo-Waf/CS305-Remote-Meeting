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

MAX_UDP_PACKET_SIZE = 1200 # 定义一个最大 UDP 数据包大小，通常是 65535 字节


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
        self.client_stream = []

        self.ui_handler = None

        # 接收缓冲区
        self.buffer = deque(maxlen=20)  # 设置缓冲区大小（可根据需求调整）
        self.fragment_buffer = {}

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
            await self.send_data(payload_type=0x01, payload=packet_part, sequence_number=sequence_number, total_packets=total_packets)
            video_payload = video_payload[MAX_UDP_PACKET_SIZE:]
        sequence_number = sequence_number + 1
        # 发送剩余的部分（如果有的话）
        if video_payload:
            await self.send_data(payload_type=0x01, payload=video_payload, sequence_number=sequence_number, total_packets=total_packets)

    async def send_audio(self, audio_data):
        """
        发送音频数据。
        :param audio_data: 捕获的音频数据
        """
        # 音频数据无需进一步编码（假设它已经是适合 RTP 传输的格式）
        await self.send_data(payload_type=0x02, payload=audio_data,sequence_number=0, total_packets=1)

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

    def process_buffer(self):
        """
        处理接收缓冲区中的 RTP 数据包，支持分片重组。
        """
        partial_frames = {}  # 存储分片数据 {sequence_number: [None] * total_chunks}
        last_activity = {}  # 记录每个帧的最后接收时间 {sequence_number: last_update_time}
        frame_timeout = 5  # 超时时间（秒）

        while self.buffer:
            packet = self.buffer.popleft()
            if not packet:  # 如果分隔符导致空包，跳过
                continue

            # 解析 RTP 分片头部
            rtp_data = self.parse_rtp_packet(packet)
            sequence_number = rtp_data["sequence_number"]
            total_chunks = rtp_data["total_packets"]
            chunk_index = rtp_data["chunk_index"]
            payload = rtp_data["payload"]

            # 初始化分片存储
            if sequence_number not in partial_frames:
                partial_frames[sequence_number] = [None] * total_chunks
                last_activity[sequence_number] = time.time()

            # 存储分片数据
            partial_frames[sequence_number][chunk_index] = payload
            last_activity[sequence_number] = time.time()

            # 检查是否完成
            if all(partial_frames[sequence_number]):
                full_frame = b''.join(partial_frames[sequence_number])
                del partial_frames[sequence_number]
                del last_activity[sequence_number]


                print("success full frame")
                # 根据负载类型调用相应的处理逻辑
                if rtp_data["payload_type"] == 0x01:  # 视频数据
                    self.handle_video_data(full_frame, rtp_data["client_id"])
                elif rtp_data["payload_type"] == 0x02:  # 音频数据
                    self.handle_audio_data(full_frame)

        # 清理超时未完成的帧
        current_time = time.time()
        to_remove = [seq for seq, last_time in last_activity.items()
                     if current_time - last_time > frame_timeout]
        for seq in to_remove:
            del partial_frames[seq]
            del last_activity[seq]
            print(f"Removed incomplete frame with sequence_number {seq} due to timeout.")

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

    def parse_rtp_packet(self, packet):
        """
        解析 RTP 数据包。
        :param packet: RTP 数据包
        :return: RTP 包头和负载
        """
        header_length = 36  # 固定头部长度
        header = packet[:header_length]
        payload = packet[header_length:]
        # 解析头部
        (payload_type,
         high_byte,
         low_byte,
         client_id_bytes,
         meeting_id_bytes,
         sequence_number,
         total_packets) = struct.unpack("!BBH16s4sHH", header)

        payload_length = (high_byte << 8) | low_byte
        client_id = str(uuid.UUID(bytes=client_id_bytes))
        meeting_id = meeting_id_bytes.decode('utf-8').strip('\x00')

        return {
            "payload_type": payload_type,
            "payload_length": payload_length,
            "client_id": client_id,
            "meeting_id": meeting_id,
            "sequence_number": sequence_number,
            "total_packets": total_packets,
            "payload": payload
        }

    async def receive_data(self):
        """
        接收 RTP 数据包并解析。
        """
        loop = asyncio.get_event_loop()
        while True:
            try:
                data, addr = await loop.sock_recv(self.sock, 65535)
                # 假设数据包以 '|END|' 分隔
                packets = data.split(b'|END|')
                for packet in packets:
                    if not packet:
                        continue
                    rtp_data = self.parse_rtp_packet(packet)
                    client = rtp_data.get("client_id")
                    meeting_id = rtp_data.get("meeting_id")
                    payload_type = rtp_data.get("payload_type")
                    sequence_number = rtp_data.get("sequence_number")
                    total_packets = rtp_data.get("total_packets")
                    payload = rtp_data.get("payload")

                    if payload_type == 0x01:  # 视频数据
                        await self.handle_video_fragment(client, meeting_id, payload, sequence_number, total_packets)
                    elif payload_type == 0x02:  # 音频数据
                        self.handle_audio_data(payload)
            except BlockingIOError:
                await asyncio.sleep(0.01)

    async def handle_video_fragment(self, client_id, meeting_id, payload, sequence_number, total_packets):
        """
        处理视频数据的分片，并在所有分片到达后进行重组和播放。
        """
        frame_id = (client_id, meeting_id)  # 可以根据需求定义更复杂的 frame_id

        if frame_id not in self.fragment_buffer:
            self.fragment_buffer[frame_id] = {
                'fragments': {},
                'total': total_packets
            }

        self.fragment_buffer[frame_id]['fragments'][sequence_number] = payload

        # 检查是否所有分片都已收到
        if len(self.fragment_buffer[frame_id]['fragments']) == self.fragment_buffer[frame_id]['total']:
            # 按序号排序并拼接所有分片
            fragments = self.fragment_buffer[frame_id]['fragments']
            full_payload = b''.join(fragments[i] for i in sorted(fragments.keys()))

            # 处理完整的视频帧
            self.handle_video_data(full_payload, client_id)

            # 清除缓冲区中的分片
            del self.fragment_buffer[frame_id]

    def handle_video_data(self, video_payload, client):
        """
        处理完整的视频数据并解码显示。
        :param video_payload: 完整的视频负载数据
        :param client: 客户端 ID
        """
        frame_array = np.frombuffer(video_payload, dtype=np.uint8)
        frame = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)
        if frame is not None:
            self.ui_handler.update_video_frame(client, frame)
            print("update video frame")
            cv2.imshow("Video Stream", frame)
            cv2.waitKey(1)
