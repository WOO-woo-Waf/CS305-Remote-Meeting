import asyncio
import concurrent.futures

import cv2
import numpy as np
import math


class DynamicVideoFrameManager:
    def __init__(self):
        """
        初始化动态视频帧管理器。
        :param frame_width: 每个客户端帧的宽度。
        :param frame_height: 每个客户端帧的高度。
        """
        self.frame_width = 960
        self.frame_height = 540
        self.video_frames = {}  # 存储每个会议的视频帧，键是会议 ID，值是 {客户端 ID: 帧数据} 的字典
        self.executor = concurrent.futures.ThreadPoolExecutor()

    def initialize_meeting(self, meeting_id):
        """
        初始化会议的帧存储。
        :param meeting_id: 会议 ID。
        """
        if meeting_id not in self.video_frames:
            self.video_frames[meeting_id] = {}

    def add_or_update_client_frame(self, meeting_id, client_id, frame):
        """
        添加或更新某个客户端的视频帧。
        :param meeting_id: 会议 ID。
        :param client_id: 客户端 ID。
        :param frame: 客户端的视频帧（OpenCV 图像）。
        """
        if meeting_id not in self.video_frames:
            self.initialize_meeting(meeting_id)
        self.video_frames[meeting_id][client_id] = frame

    def remove_client(self, meeting_id, client_id):
        """
        移除某个客户端的视频帧。
        :param meeting_id: 会议 ID。
        :param client_id: 客户端 ID。
        """
        if meeting_id in self.video_frames and client_id in self.video_frames[meeting_id]:
            del self.video_frames[meeting_id][client_id]

    async def _async_validate_and_resize_frame(self, frame):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, self._validate_and_resize_frame, frame)

    def merge_video_frames(self, meeting_id):
        """
        合并某个会议的所有客户端视频帧，并确保生成的帧可以被正确压缩。
        :param meeting_id: 会议 ID。
        :return: 合成后的帧（OpenCV 图像）。
        """
        if meeting_id not in self.video_frames or not self.video_frames[meeting_id]:
            return None

        # 获取当前会议的客户端帧
        client_frames = list(self.video_frames[meeting_id].values())
        num_clients = len(client_frames)
        if num_clients == 0:
            raise ValueError(f"No frames available for meeting ID {meeting_id}.")
        elif num_clients == 1:
            return self._validate_and_resize_frame(client_frames[0])

        # 动态计算网格布局
        grid_cols = math.ceil(math.sqrt(num_clients))
        grid_rows = math.ceil(num_clients / grid_cols)

        # 创建合成帧，确保像素值在 [0, 255] 范围内，数据类型为 uint8
        combined_frame = np.zeros(
            (grid_rows * self.frame_height, grid_cols * self.frame_width, 3),
            dtype=np.uint8
        )

        # 填充每个客户端帧
        index = 0
        for row in range(grid_rows):
            for col in range(grid_cols):
                if index < num_clients:
                    # 调整帧大小并验证有效性
                    resized_frame = self._validate_and_resize_frame(client_frames[index])

                    # 插入到对应网格位置
                    start_y = row * self.frame_height
                    end_y = start_y + self.frame_height
                    start_x = col * self.frame_width
                    end_x = start_x + self.frame_width
                    combined_frame[start_y:end_y, start_x:end_x] = resized_frame
                index += 1

        return combined_frame

    def _validate_and_resize_frame(self, frame, scale=0.5):
        """
        验证并调整帧格式，确保帧数据可以正确压缩。
        :param frame: 输入的单个帧。
        :return: 验证并调整后的帧。
        """
        if frame is None or not isinstance(frame, np.ndarray) or frame.size == 0:
            raise ValueError("Invalid frame data.")
        # 检查输入帧是否为 BGR 格式（3 个通道）
        if frame.shape[-1] != 3:
            raise ValueError("Input frame is not in BGR format. Expected 3 channels (BGR).")

        # 确保帧的数据类型为 uint8
        if frame.dtype != np.uint8:
            frame = frame.astype(np.uint8)

        # 确保帧像素值在 0-255 范围内
        frame = np.clip(frame, 0, 255)

        target_width = int(self.frame_width * scale)
        target_height = int(self.frame_height * scale)
        # 调整帧大小
        resized_frame = cv2.resize(frame, (self.frame_width, self.frame_height))

        return resized_frame
