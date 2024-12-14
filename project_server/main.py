from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from network.websocket_manager import WebSocketManager
from shared.connection_manager import ConnectionManager
from network.rtp_manager import RTPManager

# 初始化 FastAPI 应用
app = FastAPI()

# 允许跨域请求（根据需求限制域名）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 修改为实际允许的域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 核心模块实例化
websocket_manager = WebSocketManager()
rtp_manager = RTPManager(websocket_manager)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket 接口：用于处理客户端实时通信。
    """
    await websocket.accept()
    try:
        await websocket_manager.handle_connection(websocket, "/ws")
    except WebSocketDisconnect:
        print("WebSocket client disconnected")


@app.on_event("startup")
async def startup_event():
    """
    在服务启动时运行：启动 RTP 服务器。
    """
    await rtp_manager.start_udp_server(host="0.0.0.0", port=5555)
