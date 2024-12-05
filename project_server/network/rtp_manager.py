import asyncio
import socket
import struct
import time
import uuid
from asyncio import Lock

from shared.Video_packet_assembler import VideoPacketAssembler
from shared.connection_manager import ConnectionManager
import cv2
import pyaudio
import numpy as np


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
        self.frame_interval = 1 / 60  # 目标帧率（每秒 30 帧）
        self.protocol = None
        self.transport = None
        self.clients = {}  # 存储 {meeting_id: {client_id: (ip, port)}}
        self.buffers = {}  # 存储 {meeting_id: {client_id: [data1, data2, ...]}}
        self.buffer_size = 1  # 默认缓冲区大小
        self.connection_manager = ConnectionManager()  # 保持连接管理逻辑

        # 初始化音频播放流
        self.audio_player = pyaudio.PyAudio()
        self.audio_stream = self.audio_player.open(format=pyaudio.paInt16,
                                                   channels=1,
                                                   rate=44100,
                                                   output=True)
        self.lock = asyncio.Lock()
        self.video_assemblers = {}  # 存储每个视频流的 VideoPacketAssembler

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

    def create_rtp_packet(self, payload_type, payload):
        """
        创建 RTP 数据包。
        :param payload_type: 负载类型 (如音频或视频)
        :param payload: 负载数据
        :return: RTP 数据包
        """
        sequence_number = int(time.time() * 1000) % 65536  # 生成序列号
        timestamp = int(time.time() * 1000) % (2 ** 32)  # 时间戳在 0 ~ 4294967295
        ssrc = int(time.time()) % (2 ** 32)  # SSRC 在 0 ~ 4294967295
        header = struct.pack('!BBHII', 0x80, payload_type, sequence_number, timestamp, ssrc)
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
                print(f"Buffer for client {client_id} in meeting {meeting_id} is full, forwarding data...")
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
            self.video_assemblers[(meeting_id, client_id)] = VideoPacketAssembler(frame_width=1920, frame_height=1080, packet_size=65000)
            self.video_assemblers[(meeting_id, client_id)].start_assembling(total_packets)

        # 将视频包添加到组装器中
        frame = self.video_assemblers[(meeting_id, client_id)].add_packet(video_payload, sequence_number)

        # 如果合并成功，播放视频
        if frame is not None:
            # print(f"Playing video stream {client_id} in meeting {meeting_id}")
            # 获取当前时间戳
            start_time = time.time()
            # 设置窗口大小并显示
            resized_frame = cv2.resize(frame, (960, 540))
            cv2.imshow("Video Stream", resized_frame)
            # cv2.imshow("Video Stream", frame)
            # 等待一段时间以确保帧率稳定
            elapsed_time = time.time() - start_time
            time_to_wait = max(0, self.frame_interval - elapsed_time)  # 计算剩余时间，确保帧率
            time.sleep(time_to_wait)  # 控制帧率，确保每秒显示 target_fps 帧
            cv2.waitKey(1)
        else:
            # print(f"Waiting for more packets for video stream {client_id} in meeting {meeting_id}")
            pass

    def play_audio(self, audio_payload):
        """
        播放音频数据。
        :param audio_payload: 音频数据
        """
        self.audio_stream.write(audio_payload)


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
        print(f"Payload type: {payload_type}, Payload length: {len(payload)}")

        # 将数据添加到缓冲区并转发
        asyncio.create_task(self.rtp_manager.add_to_buffer(client_id, meeting_id, data))

        # 根据负载类型来播放数据
        if payload_type == 0x01:  # 视频类型
            asyncio.create_task(self.rtp_manager.play_video(client_id, meeting_id, payload, sequence_number, total_packets))
        elif payload_type == 0x02:  # 音频类型
            self.rtp_manager.play_audio(rtp_data["payload"])
