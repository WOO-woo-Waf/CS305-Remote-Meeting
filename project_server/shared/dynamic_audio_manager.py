import numpy as np
import time
import math


class DynamicAudioManager:
    def __init__(self, sample_rate=44100, frame_size=1024, buffer_duration=1.0):
        """
        初始化动态音频管理器。
        :param sample_rate: 音频采样率（如 44100 Hz）。
        :param frame_size: 每帧包含的采样点数（如 1024）。
        :param buffer_duration: 缓冲区的时长（秒）。
        """
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        self.buffer_duration = buffer_duration
        self.audio_buffers = {}  # 存储每个会议的音频帧，键是会议 ID，值是 {客户端 ID: [(timestamp, payload)]} 的字典
        self.max_frames = math.ceil((sample_rate * buffer_duration) / frame_size)  # 最大缓冲帧数

    def initialize_meeting(self, meeting_id):
        """
        初始化会议的音频缓冲区。
        :param meeting_id: 会议 ID。
        """
        if meeting_id not in self.audio_buffers:
            self.audio_buffers[meeting_id] = {}

    def add_or_update_client_audio(self, meeting_id, client_id, timestamp, payload):
        """
        添加或更新某个客户端的音频帧。
        :param meeting_id: 会议 ID。
        :param client_id: 客户端 ID。
        :param timestamp: 音频帧的时间戳（毫秒级）。
        :param payload: 音频帧的负载（PCM 数据）。
        """
        if meeting_id not in self.audio_buffers:
            self.initialize_meeting(meeting_id)

        if client_id not in self.audio_buffers[meeting_id]:
            self.audio_buffers[meeting_id][client_id] = []

        # 添加帧到缓冲区
        self.audio_buffers[meeting_id][client_id].append((timestamp, payload))

        # 保持缓冲区大小
        if len(self.audio_buffers[meeting_id][client_id]) > self.max_frames:
            self.audio_buffers[meeting_id][client_id].pop(0)

    def remove_client(self, meeting_id, client_id):
        """
        移除某个客户端的音频缓冲区。
        :param meeting_id: 会议 ID。
        :param client_id: 客户端 ID。
        """
        if meeting_id in self.audio_buffers and client_id in self.audio_buffers[meeting_id]:
            del self.audio_buffers[meeting_id][client_id]

    def mix_audio(self, meeting_id):
        """
        混合某个会议的所有客户端音频帧。
        :param meeting_id: 会议 ID。
        :return: 混合后的音频帧（PCM 数据）。
        """
        if meeting_id not in self.audio_buffers or not self.audio_buffers[meeting_id]:
            return None

        # 获取当前会议的所有客户端音频缓冲区
        client_buffers = self.audio_buffers[meeting_id]
        if not client_buffers:
            return None

        # 对齐时间戳并混合
        mixed_audio = None
        for client_id, frames in client_buffers.items():
            # 解压时间戳和负载，按时间戳排序
            frames = sorted(frames, key=lambda x: x[0])
            payloads = [np.frombuffer(frame[1], dtype=np.int16) for frame in frames]

            # 累加音频数据
            if mixed_audio is None:
                mixed_audio = np.sum(payloads, axis=0, dtype=np.int32)
            else:
                mixed_audio += np.sum(payloads, axis=0, dtype=np.int32)

        if mixed_audio is None:
            return None

        # 防止溢出并裁剪范围到 [-32768, 32767]
        mixed_audio = np.clip(mixed_audio, -32768, 32767).astype(np.int16)

        return mixed_audio.tobytes()

    def get_mixed_audio(self, meeting_id):
        """
        获取并输出某个会议的混合音频。
        :param meeting_id: 会议 ID。
        :return: 混合后的音频帧。
        """
        mixed_audio = self.mix_audio(meeting_id)

        # 清空已处理的缓冲区
        if meeting_id in self.audio_buffers:
            for client_id in self.audio_buffers[meeting_id]:
                self.audio_buffers[meeting_id][client_id] = []

        return mixed_audio
