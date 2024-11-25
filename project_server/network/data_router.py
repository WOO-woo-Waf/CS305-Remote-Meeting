import json


class DataRouter:
    def __init__(self, connection_manager, rtp_manager):
        """
        初始化 DataRouter。
        :param connection_manager: ConnectionManager 实例，用于获取会议和连接信息
        :param rtp_manager: RTPManager 实例，用于处理 RTP 数据流转发
        """
        self.connection_manager = connection_manager
        self.rtp_manager = rtp_manager

    async def route_text(self, meeting_id, sender_id, message):
        """
        转发文本消息到会议中的所有参与者。
        :param meeting_id: 会议 ID
        :param sender_id: 发送者 ID
        :param message: 文本消息
        """
        participants = self.connection_manager.get_participants(meeting_id)
        for participant_id in participants:
            if participant_id:  # 不转发给发送者
                print(f"Sending message to {participant_id} in meeting {meeting_id}")
                websocket = self.connection_manager.get_connection(participant_id)
                if websocket:
                    await websocket.send_json({
                        "meeting_id": meeting_id,
                        "action": "NEW_MESSAGE",
                        "sender": sender_id,
                        "message": message
                    })

    async def route_audio(self, meeting_id, sender_id, audio_data):
        """
        转发音频流到会议中的所有参与者。
        :param meeting_id: 会议 ID
        :param sender_id: 发送者 ID
        :param audio_data: 音频数据 (RTP 数据包)
        """
        participants = self.connection_manager.get_participants(meeting_id)
        for participant_id in participants:
            if participant_id != sender_id:  # 不转发给发送者
                client_address = self.rtp_manager.clients.get(participant_id)
                if client_address:
                    self.rtp_manager.transport.sendto(audio_data, client_address)

    async def route_video(self, meeting_id, sender_id, video_data):
        """
        转发视频流到会议中的所有参与者。
        :param meeting_id: 会议 ID
        :param sender_id: 发送者 ID
        :param video_data: 视频数据 (RTP 数据包)
        """
        participants = self.connection_manager.get_participants(meeting_id)
        for participant_id in participants:
            if participant_id != sender_id:  # 不转发给发送者
                client_address = self.rtp_manager.clients.get(participant_id)
                if client_address:
                    self.rtp_manager.transport.sendto(video_data, client_address)
