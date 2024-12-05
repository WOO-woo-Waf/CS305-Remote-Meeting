# 处理客户端连接的类
import json


class ConnectionManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(ConnectionManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        # 存储会议：{meeting_id: {"creator": client_id, "participants": []}}
        self.meetings = {}
        # 存储客户端连接：{client_id: websocket}
        self.connections = {}
        self.user_meeting_map = {}  # 存储每个用户的当前会议
        self.id_manager = 0

    # === 连接管理 ===
    def add_connection(self, client_id, websocket):
        """添加客户端连接"""
        self.connections[client_id] = websocket

    def remove_connection(self, client_id):
        """移除客户端连接"""
        if client_id in self.connections:
            self.connections[client_id] = None

    def get_connection(self, client_id):
        """获取客户端的 WebSocket 连接"""
        return self.connections.get(client_id)

    # === 会议管理 ===
    def create_meeting(self, creator_id):
        """创建会议"""
        self.id_manager += 1
        meeting_id = "m-" + str(self.id_manager)
        self.meetings[meeting_id] = {
            "creator": creator_id,
            "participants": [creator_id]
        }
        self.user_meeting_map[creator_id] = meeting_id  # 更新创建者的会议映射
        return meeting_id

    def add_participant(self, meeting_id, client_id):
        """加入会议"""
        if meeting_id not in self.meetings:
            return False

        if client_id in self.meetings[meeting_id]["participants"]:
            return True  # 已经在会议中
        if client_id in self.user_meeting_map:
            current_meeting = self.user_meeting_map[client_id]
            if current_meeting != meeting_id:
                self.remove_participant(current_meeting, client_id)
        self.meetings[meeting_id]["participants"].append(client_id)
        self.user_meeting_map[client_id] = meeting_id  # 更新用户当前会议映射
        return True

    def remove_participant(self, meeting_id, client_id):
        """移除参与者"""
        if meeting_id in self.meetings:
            if client_id in self.meetings[meeting_id]["participants"]:
                self.meetings[meeting_id]["participants"].remove(client_id)
                # 更新用户映射
                if client_id in self.user_meeting_map:
                    del self.user_meeting_map[client_id]

    def cancel_meeting(self, meeting_id, creator_id):
        """取消会议"""
        if meeting_id in self.meetings and self.meetings[meeting_id]["creator"] == creator_id:
            participants = self.meetings[meeting_id]["participants"]
            # 移除所有参与者的会议映射
            for client_id in participants:
                if client_id in self.user_meeting_map:
                    del self.user_meeting_map[client_id]
            del self.meetings[meeting_id]
            return True
        return False

    def get_participants(self, meeting_id):
        """获取会议中的参与者列表"""
        return self.meetings.get(meeting_id, {}).get("participants", [])

    # === 数据转发 ===
    async def route_text(self, meeting_id, sender_id, message):
        """转发文本消息到会议中的所有参与者"""
        participants = self.get_participants(meeting_id)
        for participant_id in participants:
            if participant_id != sender_id:  # 不转发给发送者
                websocket = self.get_connection(participant_id)
                if websocket:
                    await websocket.send(json.dumps({
                        "action": "RECEIVE_TEXT",
                        "sender": sender_id,
                        "message": message
                    }))

    # === 清理方法 ===
    def clean_up(self):
        """清理空的会议和断开的客户端"""
        # 清理会议中没有参与者的会议
        empty_meetings = [meeting_id for meeting_id, data in self.meetings.items()
                          if not data["participants"]]
        for meeting_id in empty_meetings:
            print(f"清理空会议: {meeting_id}")
            del self.meetings[meeting_id]

        # 检查每个会议，移除不存在的客户端
        disconnected_clients = [client_id for client_id in self.connections if self.connections[client_id] is None]
        for meeting_id, data in self.meetings.items():
            participants = data["participants"]
            for client_id in disconnected_clients:
                if client_id in participants:
                    print(f"从会议 {meeting_id} 移除断开的客户端: {client_id}")
                    participants.remove(client_id)

        # 清理断开的客户端记录
        for client_id in disconnected_clients:
            print(f"清理断开的客户端连接: {client_id}")
            if client_id in self.connections:
                del self.connections[client_id]
