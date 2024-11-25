import asyncio
import struct
import time
import uuid
from asyncio import Lock
from shared.connection_manager import ConnectionManager


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
        self.protocol = None
        self.transport = None
        self.clients = {}  # 存储 {meeting_id: {client_id: (ip, port)}}
        self.buffers = {}   # 存储 {meeting_id: {client_id: [data1, data2, ...]}}
        self.buffer_size = 5  # 默认缓冲区大小
        self.lock = Lock()
        self.connection_manager = ConnectionManager()  # 保持连接管理逻辑

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
        timestamp = int(time.time() * 1000) % (2**32)  # 时间戳在 0 ~ 4294967295
        ssrc = int(time.time()) % (2**32)  # SSRC 在 0 ~ 4294967295
        header = struct.pack('!BBHII', 0x80, payload_type, sequence_number, timestamp, ssrc)
        return header + payload

    def parse_rtp_packet(self, packet):
        """
        解析 RTP 数据包。
        :param packet: RTP 数据包
        :return: 数据包的字段字典和负载
        """
        header_length = 36  # 固定的 RTP 头部长度：1 字节类型 + 4 字节长度 + 16 字节 UUID + 4 字节会议 ID
        header = packet[:header_length]
        payload = packet[header_length:]
        version_payload, payload_length = struct.unpack("!BI", header[:5])
        client_id = uuid.UUID(bytes=header[5:21])  # 将 16 字节的 UUID 转换为标准 UUID 字符串
        meeting_id = struct.unpack("!I", header[21:25])[0]
        return {
            "payload_type": version_payload & 0xFF,
            "payload_length": payload_length,
            "client_id": str(client_id),  # 转换为字符串
            "meeting_id": meeting_id,
            "payload": payload
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
        # 添加数据到缓冲区
        asyncio.create_task(self.rtp_manager.add_to_buffer(client_id, meeting_id, data))
