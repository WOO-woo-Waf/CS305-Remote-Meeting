# 负责 NAT 穿透的 STUN/TURN 配置

from aiortc import RTCConfiguration, RTCIceServer


class STUNManager:
    @staticmethod
    def get_stun_configuration():
        """提供 STUN 和 TURN 配置"""
        return RTCConfiguration([
            RTCIceServer(urls=["stun:stun.l.google.com:19302"]),
            RTCIceServer(urls=["turn:turn.server.com:3478"], username="user", credential="pass")
        ])
#有新的方案，不用这个类了
