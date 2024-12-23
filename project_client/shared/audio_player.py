import asyncio
import pyaudio


class AudioPlayer:
    def __init__(self, sample_rate=44100, channels=1, format=pyaudio.paInt16):
        """
        初始化异步音频播放器。
        :param sample_rate: 音频采样率（默认 44100 Hz）。
        :param channels: 通道数（默认单声道）。
        :param format: 音频格式（默认 16 位 PCM）。
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.format = format
        self.audio_queues = {}  # 存储每个客户端的音频队列
        self.running = True
        self.pyaudio_instance = pyaudio.PyAudio()

    async def play_audio_stream(self, client_id, audio_queue):
        """
        异步播放某个客户端的音频流。
        :param client_id: 客户端 ID。
        :param audio_queue: 客户端的音频队列。
        """
        stream = self.pyaudio_instance.open(
            format=self.format,
            channels=self.channels,
            rate=self.sample_rate,
            output=True
        )

        while self.running:
            audio_data = await audio_queue.get()
            if audio_data is None:  # 退出信号
                break

            try:
                # 播放音频数据
                stream.write(audio_data)
            except Exception as e:
                raise ValueError(f"Error playing audio for client {client_id}: {e}")

        stream.stop_stream()
        stream.close()

    async def add_audio(self, client_id, audio_data):
        """
        添加音频数据到对应客户端的队列。
        如果客户端不存在，则创建新的队列和任务。
        :param client_id: 客户端 ID。
        :param audio_data: 音频数据（PCM 格式）。
        """
        if client_id not in self.audio_queues:
            # 创建新的音频队列和任务
            audio_queue = asyncio.Queue()
            self.audio_queues[client_id] = audio_queue
            asyncio.create_task(self.play_audio_stream(client_id, audio_queue))

        # 将音频数据放入队列
        await self.audio_queues[client_id].put(audio_data)

    async def stop(self):
        """
        停止所有音频流。
        """
        self.running = False
        for client_id, audio_queue in self.audio_queues.items():
            # 发送退出信号
            await audio_queue.put(None)
        self.audio_queues.clear()
        self.pyaudio_instance.terminate()

