import asyncio
import socket
import struct
import time
import uuid
import cv2
import ffmpeg
import pyaudio
import threading
import numpy as np
from collections import deque
from asyncio import Queue

from shared.Video_packet_assembler import VideoPacketAssembler
from shared.media_manager import MediaManager
from shared.audio_player import AudioPlayer

MAX_UDP_PACKET_SIZE = 1500  # 定义一个最大 UDP 数据包大小，通常是 65535 字节

media_manager = MediaManager(None)


class RTPClient:
    def __init__(self, server_ip, server_port, client_port, client_id, meeting_id, client_ip="0.0.0.0", mode="unconnected"):
        """
        初始化 RTP 客户端。
        :param server_ip: RTP 服务器 IP
        :param server_port: RTP 服务器端口
        :param client_ip: 客户端本地 IP
        :param client_port: 客户端本地端口（默认 0 表示随机端口）
        :param client_id: 客户端 ID (UUID 格式)
        """
        self.data_queue = Queue()
        self.server_ip = server_ip
        self.server_port = server_port
        self.p2p_ip = None
        self.p2p_port = None
        self.client_id = client_id
        self.meeting_id = meeting_id
        self.mode = mode

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
        while True:
            try:    # 绑定端口
                self.sock.bind((client_ip, client_port))
                break
            except OSError:
                client_port += 1
        self.client_ip, self.client_port = self.sock.getsockname()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 * 1024 * 1024)  # 增加接收缓冲区
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 8 * 1024 * 1024)  # 增加发送缓冲区

        print(f"RTP Client initialized with IP {self.client_ip} and port {self.client_port}")
        # self.video_assemblers = None  # 视频包组装器
        self.frame_interval = 1 / 30  # 视频帧之间的时间间隔（30 FPS）
        asyncio.create_task(self.receive_data())  # 启动接收任务
        asyncio.create_task(self.process_data())  # 启动处理任务
        self.pipeline = (
            f"udpsrc port={self.server_port} ! application/x-rtp, payload=96 ! rtph264depay ! avdec_h264 "
            f"! videoconvert ! appsink"
        )
        self.capture = None
        self.running = False
        self.thread = None  # 用于接收和播放视频的线程

        self.audio_player = AudioPlayer()

        # 自动启动视频接收
        # self.start_video_thread()
        self.video_assemblers = {}  # 存储每个视频流的 VideoPacketAssembler

    def connect_to_p2p(self, ip, port):
        self.p2p_ip = ip
        self.p2p_port = port
        self.mode = "p2p"

    def stop_p2p(self):
        self.mode = "CS"

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

        # 使用当前时间戳（秒级）替代客户端 ID 和会议 ID
        timestamp = int(time.time() * 1000)  # 毫秒级时间戳
        timestamp_bytes = struct.pack('!Q', timestamp)  # 8 字节时间戳（大端序）

        # 创建 RTP 头部（1 字节 payload_type + 2 字节 payload_length + 2 字节 sequence_number + 2 字节 total_packets + 16 字节
        # client_id + 4 字节 meeting_id）
        header = struct.pack(
            '!BBH16s4sHH8s',  # 格式： 1 字节 (payload_type) + 2 字节 (payload_length) + 2 字节 (sequence_number) + 2 字节 (
            # total_packets) + 16 字节 UUID + 4 字节 meeting_id
            payload_type,  # 数据类型，视频或音频
            (payload_length >> 8) & 0xFF,  # 高 8 位
            payload_length & 0xFF,  # 低 8 位
            client_id_bytes,  # 客户端 ID（16 字节 UUID）
            meeting_id_bytes,  # 会议 ID（4 字节）
            sequence_number,  # 包的序列号
            total_packets,    # 视频总包数
            timestamp_bytes  # 时间戳（8 字节）
        )

        # 返回 RTP 数据包（头部 + 负载）
        return header + payload

    def create_rtp_packet_p2p(self, payload_type, payload, sequence_number, total_packets):
        """
        创建 RTP 数据包。
        :param payload_type: 数据类型 (0x01: 视频, 0x02: 音频)
        :param payload: 负载数据
        :param sequence_number: 包的序列号（用于视频包的排序）
        :param total_packets: 视频总包数（用于标记整个帧的分包数量）
        :return: RTP 数据包
        """
        payload_length = len(payload)

        # 确保 self.client_id 是一个有效的 UUID 字符串
        client_id_bytes = uuid.UUID(self.client_id).bytes  # 转换为 16 字节的字节流
        if len(client_id_bytes) != 16:
            raise ValueError("client_id should be a valid UUID")

        # 使用当前时间戳（秒级）替代客户端 ID 和会议 ID
        timestamp = int(time.time() * 1000)  # 毫秒级时间戳
        timestamp_bytes = struct.pack('!Q', timestamp)  # 8 字节时间戳（大端序）

        # 将序列号和总包数转换为字节流
        sequence_number_bytes = struct.pack('!H', sequence_number)  # 2 字节序列号
        total_packets_bytes = struct.pack('!H', total_packets)  # 2 字节总包数

        # 创建 RTP 头部（1 字节 payload_type + 2 字节 payload_length + 2 字节 sequence_number + 2 字节 total_packets + 8 字节时间戳）
        header = struct.pack(
            '!BBH8sHH16s',  # 格式： 1 字节 (payload_type) + 2 字节 (payload_length) + 2 字节 (sequence_number) + 2 字节 (
            # total_packets) + 8 字节时间戳
            payload_type,  # 数据类型，视频或音频
            (payload_length >> 8) & 0xFF,  # 高 8 位
            payload_length & 0xFF,  # 低 8 位
            timestamp_bytes,  # 时间戳（8 字节）
            sequence_number,  # 包的序列号
            total_packets,  # 视频总包数
            client_id_bytes  # 客户端 ID（16 字节 UUID）
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
        header_format = '!BBH8sHH16s'
        header_size = struct.calcsize(header_format)

        if len(packet) < header_size:
            raise ValueError("Invalid RTP packet: Header size is too small")

        # 解析头部
        header = packet[:header_size]
        payload = packet[header_size:]

        payload_type, high_length, low_length, timestamp_bytes, sequence_number, total_packets, client_id_bytes = struct.unpack(
            header_format, header)

        # 将 client_id 转换为 UUID 字符串
        client_id = str(uuid.UUID(bytes=client_id_bytes))

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
            "payload": payload,
            "client_id": client_id
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
        if self.mode == "p2p":
            packet = self.create_rtp_packet_p2p(payload_type, payload, sequence_number, total_packets)
        else:
            packet = self.create_rtp_packet(payload_type, payload, sequence_number, total_packets)
        self.sock.sendto(packet, (self.p2p_ip, self.p2p_port) if self.mode == "p2p" else (self.server_ip, self.server_port))
        # print(f"Sent RTP packet to {self.server_ip}:{self.server_port}")

    async def receive_data(self):
        """
        接收 RTP 数据包并解析。
        """
        loop = asyncio.get_event_loop()
        while True:
            try:
                # 接收批量 RTP 数据包
                data = await loop.sock_recv(self.sock, MAX_UDP_PACKET_SIZE + 100)
                data_ = self.parse_rtp_packet(data)
                # 将数据放入队列中
                await self.data_queue.put(data_)
            except BlockingIOError:
                await asyncio.sleep(0.01)  # 避免高 CPU 占用

    async def process_data(self):
        """
        从队列中处理数据包。
        """
        while True:
            data_ = await self.data_queue.get()  # 从队列获取数据
            try:
                payload_type = data_["payload_type"]
                payload = data_["payload"]
                sequence_number = data_["sequence_number"]
                total_packets = data_["total_packets"]
                client_id = data_["client_id"]

                # print(f"Received RTP packet from {client_id} ({len(payload)} bytes)")
                # print(f"Payload type: {payload_type}, Sequence number: {sequence_number}, Total packets: {total_packets}")
                # 根据负载类型来播放数据
                if payload_type == 0x01:  # 视频类型
                    asyncio.create_task(self.play_video(payload, sequence_number, total_packets, client_id))
                elif payload_type == 0x02:  # 音频类型
                    asyncio.create_task(self.play_audio(payload, client_id))
            except Exception as e:
                print(f"Error processing data: {e}")

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

    async def play_audio(self, audio_payload, client_id):
        """
        播放音频数据。
        :param audio_payload: 音频数据
        """
        await self.audio_player.add_audio(client_id, audio_payload)

    async def play_video(self, video_payload, sequence_number, total_packets, client_id):
        """
        解析视频数据并显示，处理视频包的合并。
        :param video_payload: 视频数据
        :param sequence_number: 视频包的序列号
        :param total_packets: 视频总包数
        """
        if client_id not in self.video_assemblers:
            self.video_assemblers[client_id] = VideoPacketAssembler(frame_width=960, frame_height=540)
            self.video_assemblers[client_id].start_assembling(total_packets)

        # 将视频包添加到组装器中
        frame = await self.video_assemblers[client_id].add_packet(video_payload, sequence_number, total_packets)

        if frame is not None:
            # # 获取当前时间戳
            # start_time = time.time()
            #
            # # 调整帧的大小
            # resized_frame = cv2.resize(frame, (1440, 810))
            #
            # # print(f"Received video frame from client {client_id} ({len(video_payload)} bytes")
            # # 使用 cv2.imshow 显示帧
            # cv2.imshow(f"Video Stream_client {self.meeting_id} {self.client_port}", resized_frame)
            # print(f"Video Stream_client {self.meeting_id} {self.client_port}")
            # # 等待按键事件并设置适当的退出条件
            # key = cv2.waitKey(1)
            # if key == ord('q'):  # 如果按下 'q' 键退出
            #     print("Exiting video stream...")
            #     cv2.destroyAllWindows()
            #     return
            #
            # # 控制帧率
            # elapsed_time = time.time() - start_time
            # time_to_wait = max(0, self.frame_interval - elapsed_time)  # 计算剩余时间，确保帧率
            # time.sleep(time_to_wait)

            # if not media_manager.display_running:
            #     media_manager.start_video_display()
            # media_manager.frame_queue.append(frame)
            await media_manager.add_video(client_id, frame)







