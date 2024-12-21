class MeetingLifecycleManager:
    def __init__(self, connection_manager):
        """
        初始化会议生命周期管理器。
        :param connection_manager: ConnectionManager 实例
        """
        self.connection_manager = connection_manager  # 用于管理连接和会议数据

    def create_meeting(self, creator_id):
        """
        创建会议。
        :param creator_id: 创建者客户端 ID
        :return: 成功返回 True，否则返回 False
        """
        meeting_id = self.connection_manager.create_meeting(creator_id)
        if meeting_id:
            print(f"Meeting {meeting_id} created by {creator_id}")
            return meeting_id
        print(f"Failed to create meeting {meeting_id}")
        return "UNKNOWN"

    def join_meeting(self, meeting_id, client_id):
        """
        加入会议。
        :param meeting_id: 会议 ID
        :param client_id: 客户端 ID
        :return: 成功返回 True，否则返回 False
        """
        if self.connection_manager.add_participant(meeting_id, client_id):
            print(f"Client {client_id} joined meeting {meeting_id}")
            return True
        print(f"Failed to join meeting {meeting_id} for client {client_id}")
        return False

    def exit_meeting(self, meeting_id, client_id):
        """
        退出会议。
        :param meeting_id: 会议 ID
        :param client_id: 客户端 ID
        """
        self.connection_manager.remove_participant(meeting_id, client_id)
        print(f"Client {client_id} exited meeting {meeting_id}")

    def cancel_meeting(self, meeting_id, creator_id):
        """
        取消会议。
        :param meeting_id: 会议 ID
        :param creator_id: 创建者客户端 ID
        :return: 成功返回 True，否则返回 False
        """
        participants = self.connection_manager.get_participants(meeting_id)
        if participants:
            print(f"Meeting {meeting_id} canceled by {creator_id}")
            return participants
        print(f"Failed to cancel meeting {meeting_id} by {creator_id}")
        return None

    def get_meeting_status(self, meeting_id):
        """
        获取会议状态。
        :param meeting_id: 会议 ID
        :return: 会议状态字典或 None
        """
        participants = self.connection_manager.get_participants(meeting_id)
        if participants:
            return {
                "meeting_id": meeting_id,
                "participants": participants
            }
        print(f"Meeting {meeting_id} not found")
        return None
