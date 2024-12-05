import asyncio
import socket


class RTPClient:
    def __init__(self, server_ip, server_port, client_ip="0.0.0.0", client_port=0):
        self.server_ip = server_ip
        self.server_port = server_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setblocking(False)
        self.sock.bind((client_ip, client_port))
        print(f"Client initialized on {self.sock.getsockname()}")  # 插入测试日志

    async def send_test_packet(self):
        loop = asyncio.get_event_loop()
        test_data = b"Test packet from client"
        print(f"Sending test packet to {self.server_ip}:{self.server_port}")  # 插入测试日志
        self.sock.sendto(test_data, (self.server_ip, self.server_port))
        try:
            data, addr = await loop.sock_recv(self.sock, 65535)
            print(f"Received response from {addr}: {data}")  # 插入测试日志
        except Exception as e:
            print(f"Error receiving data: {e}")  # 插入测试日志


async def main():
    client = RTPClient("127.0.0.1", 5000)
    await client.send_test_packet()

asyncio.run(main())
