import asyncio
import socket
import struct
import time
import uuid
from asyncio import Lock

from shared.Video_packet_assembler import VideoPacketAssembler
from shared.dynamic_video_frame_manager import DynamicVideoFrameManager
from shared.connection_manager import ConnectionManager
import cv2
import pyaudio
import numpy as np
import math

MAX_UDP_PACKET_SIZE = 65000  # 最大 UDP 数据包大小


class RTPManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(RTPManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """
        初始化 RTPManager，用于管理 RTP 数据包的创建、解析和转发。
        """
        self.frame_interval = 1 / 30  # 目标帧率（每秒 30 帧）
        self.protocol = None
        self.transport = None
        self.clients = {}  # 存储 {meeting_id: {client_id: (ip, port)}}
        self.buffers = {}  # 存储 {meeting_id: {client_id: [data1, data2, ...]}}
        self.buffer_size = 1  # 默认缓冲区大小
        self.connection_manager = ConnectionManager()  # 保持连接管理逻辑
        self.dynamic_video_frame_manager = DynamicVideoFrameManager(frame_width=960, frame_height=540)

        # 初始化音频播放流
        self.audio_player = pyaudio.PyAudio()
        self.audio_stream = self.audio_player.open(format=pyaudio.paInt16,
                                                   channels=1,
                                                   rate=44100,
                                                   output=True)
        self.lock = asyncio.Lock()
        self.video_assemblers = {}  # 存储每个视频流的 VideoPacketAssembler
        self.video_frame = {}  # 存储每个会议的客户端帧

    async def register_client(self, meeting_id, client_id, address):
        """
        注册客户端到会议中。
        :param client_id: 客户端 ID
        :param meeting_id: 会议 ID
        :param address: 客户端的 (IP, Port)
        """
        async with self.lock:
            # 初始化会议和客户端信息
            if meeting_id not in self.clients:
                self.clients[meeting_id] = {}
                self.buffers[meeting_id] = {}
                print(f"Meeting {meeting_id} initialized.")
                self.register_meeting(meeting_id)
            self.clients[meeting_id][client_id] = address
            self.buffers[meeting_id][client_id] = []  # 初始化缓冲区
            print(f"Client {client_id} registered to meeting {meeting_id}. Current clients: {self.clients}")

    async def unregister_client(self, client_id, meeting_id):
        """
        从会议中移除客户端。
        :param client_id: 客户端 ID
        :param meeting_id: 会议 ID
        """
        async with self.lock:
            if meeting_id in self.clients and client_id in self.clients[meeting_id]:
                del self.clients[meeting_id][client_id]
                del self.buffers[meeting_id][client_id]
                if not self.clients[meeting_id]:  # 如果会议中无其他客户端，则删除会议
                    del self.clients[meeting_id]
                    del self.buffers[meeting_id]
                print(f"Client {client_id} unregistered from meeting {meeting_id}. Current clients: {self.clients}")
                self.dynamic_video_frame_manager.remove_client(meeting_id, client_id)

    def register_meeting(self, meeting_id):
        """
        注册会议并启动视频帧转发任务。
        :param meeting_id: 会议 ID
        """
        self.dynamic_video_frame_manager.initialize_meeting(meeting_id)
        print(f"Starting video frame forwarding task for meeting {meeting_id}.")
        asyncio.create_task(self.send_video_to_meeting(meeting_id))

    def create_rtp_packet(self, payload_type, payload, sequence_number, total_packets):
        """
        创建 RTP 数据包。
        :param payload_type: 数据类型 (0x01: 视频, 0x02: 音频)
        :param payload: 负载数据
        :param sequence_number: 包的序列号（用于视频包的排序）
        :param total_packets: 视频总包数（用于标记整个帧的分包数量）
        :return: RTP 数据包
        """
        payload_length = len(payload)

        # 使用当前时间戳（秒级）替代客户端 ID 和会议 ID
        timestamp = int(time.time() * 1000)  # 毫秒级时间戳
        timestamp_bytes = struct.pack('!Q', timestamp)  # 8 字节时间戳（大端序）

        # 将序列号和总包数转换为字节流
        sequence_number_bytes = struct.pack('!H', sequence_number)  # 2 字节序列号
        total_packets_bytes = struct.pack('!H', total_packets)  # 2 字节总包数

        # 创建 RTP 头部（1 字节 payload_type + 2 字节 payload_length + 2 字节 sequence_number + 2 字节 total_packets + 8 字节时间戳）
        header = struct.pack(
            '!BBH8sHH',  # 格式： 1 字节 (payload_type) + 2 字节 (payload_length) + 2 字节 (sequence_number) + 2 字节 (
            # total_packets) + 8 字节时间戳
            payload_type,  # 数据类型，视频或音频
            (payload_length >> 8) & 0xFF,  # 高 8 位
            payload_length & 0xFF,  # 低 8 位
            timestamp_bytes,  # 时间戳（8 字节）
            sequence_number,  # 包的序列号
            total_packets  # 视频总包数
        )

        # 返回 RTP 数据包（头部 + 负载）
        return header + payload

    def parse_rtp_packet(self, packet):
        """
        解析 RTP 数据包。
        :param packet: RTP 数据包
        :return: 数据包的字段字典和负载
        """
        header_length = 1 + 2 + 2 + 2 + 16 + 4 + 1
        # 1 字节 payload_type + 2 字节 payload_length + 2 字节 sequence_number +
        # 2 字节 total_packets + 16 字节 client_id + 4 字节 meeting_id

        if len(packet) < header_length:
            raise ValueError("Packet is too short to be a valid RTP packet")

        header = packet[:header_length]  # RTP 包头
        payload = packet[header_length:]  # RTP 负载（实际的数据）

        # 解析 RTP 头部
        (payload_type, high_byte, low_byte,
         client_id_bytes, meeting_id_bytes,
         sequence_number, total_packets) = struct.unpack('!BBH16s4sHH', header)

        # 计算负载长度
        payload_length = (high_byte << 8) | low_byte

        # 将 client_id 转换为 UUID 字符串
        client_id = str(uuid.UUID(bytes=client_id_bytes))

        # 将 meeting_id 转换为字符串（假设它是一个编码后的字符串）
        meeting_id = meeting_id_bytes.decode('utf-8').strip('\x00')

        # 返回解析后的数据
        return {
            'payload_type': payload_type,
            'payload_length': payload_length,
            'sequence_number': sequence_number,
            'total_packets': total_packets,
            'client_id': client_id,
            'meeting_id': meeting_id,
            'payload': payload  # 返回负载数据
        }

    async def start_udp_server(self, host, port):
        """
        启动 UDP 服务器，监听 RTP 数据包。
        :param host: 主机地址
        :param port: 监听端口
        """
        loop = asyncio.get_event_loop()
        self.transport, self.protocol = await loop.create_datagram_endpoint(
            lambda: RTPProtocol(self),
            local_addr=(host, port)
        )
        # 设置接收缓冲区大小
        sock = self.transport.get_extra_info('socket')  # 获取底层的套接字
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 * 1024 * 1024)  # 8MB 接收缓冲区
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 8 * 1024 * 1024)  # 8MB 发送缓冲区
        print(f"RTP UDP server started on {host}:{port}")

    async def add_to_buffer(self, client_id, meeting_id, data):
        """
        添加数据到缓冲区。
        :param client_id: 客户端 ID
        :param meeting_id: 会议 ID
        :param data: 接收到的数据
        """
        async with self.lock:
            if meeting_id not in self.buffers or client_id not in self.buffers[meeting_id]:
                print(f"Invalid meeting_id ({meeting_id}) or client_id ({client_id}).")
                return

            # 添加数据到缓冲区
            self.buffers[meeting_id][client_id].append(data)

            # 如果缓冲区达到指定大小，批量转发
            if len(self.buffers[meeting_id][client_id]) >= self.buffer_size:
                # print(f"Buffer for client {client_id} in meeting {meeting_id} is full, forwarding data...")
                await self.forward_rtp(client_id, meeting_id)

    async def forward_rtp(self, sender_id, meeting_id):
        """
        转发缓冲区中的数据到会议中的其他客户端。
        :param sender_id: 发送者 ID
        :param meeting_id: 会议 ID
        """
        async with self.lock:
            if meeting_id not in self.clients:
                print(f"Meeting {meeting_id} does not exist.")
                return

            # 获取发送者缓冲区中的数据
            data_to_forward = b'|END|'.join(self.buffers[meeting_id][sender_id])
            self.buffers[meeting_id][sender_id] = []  # 清空缓冲区

            # 获取会议参与者
            participants = self.connection_manager.get_participants(meeting_id)

            # 广播数据到会议中的其他客户端
            for client_id in participants:
                if client_id != sender_id:  # 不转发给发送者
                    client_address = self.clients[meeting_id].get(client_id)
                    if client_address:
                        print(f"Forwarding RTP data to {client_address} in meeting {meeting_id}.")
                        self.transport.sendto(data_to_forward, client_address)

    async def play_video(self, client_id, meeting_id, video_payload, sequence_number, total_packets):
        """
        解析视频数据并显示，处理视频包的合并。
        :param video_payload: 视频数据
        :param client_id: 客户端ID
        :param meeting_id: 会议ID
        :param sequence_number: 视频包的序列号
        :param total_packets: 视频总包数
        """
        # 如果没有为该视频流初始化组装器，则创建一个新的
        if (meeting_id, client_id) not in self.video_assemblers:
            self.video_assemblers[(meeting_id, client_id)] = VideoPacketAssembler(frame_width=1920, frame_height=1080,
                                                                                  packet_size=65000)
            self.video_assemblers[(meeting_id, client_id)].start_assembling(total_packets)

        # 将视频包添加到组装器中
        frame = self.video_assemblers[(meeting_id, client_id)].add_packet(video_payload, sequence_number)
        # print(f"Received video packet {sequence_number + 1}
        # /{total_packets} from {client_id} in meeting {meeting_id}.")
        if frame is not None:
            self.dynamic_video_frame_manager.add_or_update_client_frame(meeting_id, client_id, frame)
            # print(f"Playing video stream {client_id} in meeting {meeting_id}")
            # # 获取当前时间戳
            # start_time = time.time()
            # # 设置窗口大小并显示
            # resized_frame = cv2.resize(frame, (960, 540))
            # cv2.imshow("Video Stream", resized_frame)
            # # cv2.imshow("Video Stream", frame)
            # # 等待一段时间以确保帧率稳定
            # elapsed_time = time.time() - start_time
            # time_to_wait = max(0, self.frame_interval - elapsed_time)  # 计算剩余时间，确保帧率
            # time.sleep(time_to_wait)  # 控制帧率，确保每秒显示 target_fps 帧
            # cv2.waitKey(1)

    def play_audio(self, client_id, meeting_id, audio_payload):
        """
        播放音频数据。
        """
        # self.audio_stream.write(audio_payload)

    async def send_data_to_client(self, client_id, client_address, video_payload, data_type):
        """
        向单个客户端发送数据，支持数据分割。
        :param client_id: 客户端 ID
        :param client_address: 客户端地址 (IP, Port)
        :param video_payload: 要发送的数据（字节流）
        :param data_type: 数据类型 ('video' 或 'audio')
        """
        # total_size = len(data)
        # num_packets = (total_size + MAX_UDP_PACKET_SIZE - 1) // MAX_UDP_PACKET_SIZE
        #
        # for sequence_number in range(num_packets):
        #     # 分割数据
        #     start_index = sequence_number * MAX_UDP_PACKET_SIZE
        #     end_index = min(start_index + MAX_UDP_PACKET_SIZE, total_size)
        #     packet_data = data[start_index:end_index]
        #
        #     # 创建 RTP 数据包
        #     rtp_packet = self.create_rtp_packet(
        #         payload_type=0x01 if data_type == 'video' else 0x02,  # 视频为 0x01，音频为 0x02
        #         payload=packet_data,
        #         sequence_number=sequence_number,
        #         total_packets=num_packets
        #     )
        #
        #     # 发送数据
        #     self.transport.sendto(rtp_packet, client_address)

        # print(f"Sent {data_type} packet {sequence_number + 1}/{num_packets} to {client_id} at {client_address}.")
        payload_type = 0x01 if data_type == 'video' else 0x02

        total_packets = len(video_payload) // MAX_UDP_PACKET_SIZE + 1  # 计算视频帧的总包数
        sequence_number = 0  # 初始化序列号
        while len(video_payload) > MAX_UDP_PACKET_SIZE:
            packet_part = video_payload[:MAX_UDP_PACKET_SIZE]
            # 检查数据包大小
            # print(f"Packet size: {len(packet_part)} bytes")
            sequence_number = sequence_number + 1
            rtp_packet = self.create_rtp_packet(payload_type=payload_type, payload=packet_part,
                                                sequence_number=sequence_number,
                                                total_packets=total_packets)
            self.transport.sendto(rtp_packet, client_address)
            video_payload = video_payload[MAX_UDP_PACKET_SIZE:]
        sequence_number = sequence_number + 1
        # 发送剩余的部分（如果有的话）
        if video_payload:
            rtp_packet = self.create_rtp_packet(payload_type=payload_type, payload=video_payload,
                                                sequence_number=sequence_number,
                                                total_packets=total_packets)
            self.transport.sendto(rtp_packet, client_address)

    async def send_video_to_meeting(self, meeting_id, exclude_client_id=None):
        """
        向会议中的所有客户端实时发送合成的视频帧。
        :param meeting_id: 会议 ID
        :param exclude_client_id: （可选）要排除的客户端 ID
        """
        async with self.lock:
            if meeting_id not in self.clients:
                print(f"Meeting {meeting_id} does not exist.")
                return

        while True:
            # 从 DynamicVideoFrameManager 获取最新合成帧
            frame = self.dynamic_video_frame_manager.merge_video_frames(meeting_id)
            if frame is not None:
                # 将帧编码为 JPG 格式
                _, encoded_frame = cv2.imencode('.jpg', frame,[int(cv2.IMWRITE_JPEG_QUALITY), 10])
                frame_data = encoded_frame.tobytes()
                # print(f"Sending video frame to meeting {meeting_id}.")
                # 遍历会议中的每个客户端并发送帧
                async with self.lock:
                    for client_id, client_address in self.clients[meeting_id].items():
                        if client_id != exclude_client_id:
                            # print(f"Sending video frame to {client_id} at {client_address} in meeting {meeting_id}.")
                            # 使用单独任务发送帧
                            await asyncio.create_task(
                                self.send_data_to_client(client_id, client_address, frame_data, data_type='video'))

            # 控制帧率
            await asyncio.sleep(self.frame_interval)

    async def send_audio_to_meeting(self, meeting_id, audio_data, exclude_client_id=None):
        """
        向会议中的所有客户端发送音频数据。
        :param meeting_id: 会议 ID
        :param audio_data: 音频数据（字节流）
        :param exclude_client_id: （可选）要排除的客户端 ID
        """
        async with self.lock:
            if meeting_id not in self.clients:
                print(f"Meeting {meeting_id} does not exist.")
                return

            # 向每个客户端发送音频数据
            for client_id, client_address in self.clients[meeting_id].items():
                if client_id != exclude_client_id:
                    await asyncio.create_task(
                        self.send_data_to_client(client_id, client_address, audio_data, data_type='audio'))
                    # print(f"Sending audio data to {client_id} at {client_address} in meeting {meeting_id}.")


class RTPProtocol(asyncio.DatagramProtocol):
    def __init__(self, rtp_manager):
        """
        RTP 协议处理器，用于解析接收到的 RTP 数据包。
        :param rtp_manager: RTPManager 实例
        """
        self.rtp_manager = rtp_manager

    def datagram_received(self, data, addr):
        """
        接收到 UDP 数据包时触发。
        :param data: 数据包
        :param addr: 数据包来源地址 (IP, Port)
        """
        rtp_data = self.rtp_manager.parse_rtp_packet(data)
        payload_type = rtp_data["payload_type"]
        client_id = rtp_data["client_id"]
        meeting_id = rtp_data["meeting_id"]
        payload = rtp_data['payload']
        sequence_number = rtp_data.get("sequence_number", 0)
        total_packets = rtp_data.get("total_packets", 1)

        # print(f"Received RTP packet from {client_id} in meeting {meeting_id}")
        # print(f"Payload type: {payload_type}, Payload length: {len(payload)}")

        # 根据负载类型来播放数据
        if payload_type == 0x01:  # 视频类型
            asyncio.create_task(self.rtp_manager.play_video(client_id, meeting_id,
                                                            payload, sequence_number, total_packets))
        elif payload_type == 0x02:  # 音频类型
            asyncio.create_task(self.rtp_manager.send_audio_to_meeting(meeting_id, payload))
