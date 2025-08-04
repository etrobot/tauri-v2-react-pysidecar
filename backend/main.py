import os
import sys
import asyncio
import threading
from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from uvicorn import Config, Server
import subprocess
import pandas as pd
from collections import deque
from datetime import datetime
from multiprocessing import Process, Queue

# 主进程与子进程共享的队列
buffer_queue = Queue(maxsize=200)

PORT_API = 61125

# Global variables
server_instance = None  # Global reference to the Uvicorn server instance
concept_df = None  # Global variable for concepts data
log_messages = deque(maxlen=1000)  # Store last 1000 log messages
active_websockets = set()  # Store active WebSocket connections


app = FastAPI(
    title="API server",
    version="0.1.0",
)

# getConcepts 子进程管理
get_concepts_proc = None
# getChanges 子进程管理
get_changes_proc = None
get_changes_timer = None
get_changes_stop_event = threading.Event()

@app.post("/api/start_get_concepts")
def start_get_concepts():
    global get_concepts_proc
    # 检查子进程是否正在运行
    if get_concepts_proc is not None and get_concepts_proc.poll() is None:
        return {"status": "already running", "pid": get_concepts_proc.pid}
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    # 启动子进程执行 getConcepts
    get_concepts_proc = subprocess.Popen([
        sys.executable, "-c", "from concepts import getConcepts; getConcepts()"
    ], cwd=backend_dir)
    return {"status": "started", "pid": get_concepts_proc.pid}


# 允许本地开发端口 1420 和 1430 跨域访问
# Configure CORS settings
origins = [
    "http://localhost:1420",  # for Tauri dev
    "http://127.0.0.1:1420",
    "http://localhost:1430",
    "http://127.0.0.1:1430",
    "tauri://localhost",      # for Tauri prod
    "http://localhost:61125",  # for API server
    "http://127.0.0.1:61125",
    "http://0.0.0.0:61125"    # for frontend development
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,  # Required for WebSocket
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.websocket("/ws/changes")
async def websocket_changes(websocket: WebSocket):
    print(f"[ws/changes] New WebSocket connection from {websocket.client}")
    await websocket.accept()
    import json
    try:
        while True:
            # 优先从缓冲队列读取
            sent = False
            try:
                while not buffer_queue.empty():
                    data = buffer_queue.get_nowait()
                    await websocket.send_text(json.dumps(data, ensure_ascii=False))
                    sent = True
            except Exception as e:
                await websocket.send_text(json.dumps({"error": str(e)}, ensure_ascii=False))
            # 如果队列为空，降级为读csv
            if not sent:
                try:
                    csv_path = get_resource_path("static/changes.csv")
                    if not csv_path or not os.path.exists(csv_path):
                        await websocket.send_text("[]")
                    else:
                        import pandas as pd
                        df = pd.read_csv(csv_path)
                        data = df.where(pd.notnull(df), None).to_dict(orient="records")
                        await websocket.send_text(json.dumps(data, ensure_ascii=False))
                except Exception as e:
                    await websocket.send_text(json.dumps({"error": str(e)}, ensure_ascii=False))
            await asyncio.sleep(2)

    except Exception as e:
        print(f"[ws/changes] WebSocket error: {e}")
    finally:
        print(f"[ws/changes] WebSocket connection closed: {websocket.client}")
        try:
            await websocket.close()
        except RuntimeError as e:
            print(f"[ws/changes] WebSocket already closed: {e}")


@app.websocket("/ws/logs")
async def websocket_endpoint(websocket: WebSocket):
    try:
        print(f"New WebSocket connection attempt from {websocket.client}")
        await websocket.accept()
        active_websockets.add(websocket)
        print(f"WebSocket connection accepted, total active connections: {len(active_websockets)}")
        # 发送历史日志
        for message in log_messages:
            try:
                await websocket.send_text(message)
            except Exception as e:
                print(f"Error sending historical message: {e}")
                break
        # 保持连接直到客户端断开
        while True:
            try:
                await websocket.receive_text()
                # Optional: send a ping to keep connection alive
                await websocket.send_text("ping")
            except Exception as e:
                print(f"WebSocket connection error: {e}")
                break
    except Exception as e:
        print(f"WebSocket general error: {e}")
    finally:
        active_websockets.remove(websocket)
        print(f"WebSocket connection closed, remaining active connections: {len(active_websockets)}")
        print(f"WebSocket connection accepted, total active connections: {len(active_websockets)}")
        
        # 发送历史日志
        for message in log_messages:
            try:
                await websocket.send_text(message)
            except Exception as e:
                print(f"Error sending historical message: {e}")
                break
        
        # 保持连接直到客户端断开
        while True:
            try:
                await websocket.receive_text()
                # Optional: send a ping to keep connection alive
                await websocket.send_text("ping")
            except Exception as e:
                print(f"WebSocket connection error: {e}")
                break

@app.get("/api/watch/status")
async def get_watch_status():
    """Get the status of the fluctuation watch process"""
    global watch_process
    if watch_process is None:
        return {"status": "not_running"}

    return_code = watch_process.poll()
    if return_code is None:
        return {"status": "running", "pid": watch_process.pid}
    else:
        return {"status": "stopped", "return_code": return_code}


@app.get("/api/changes/json")
async def get_changes_json():
    """Get changes data in JSON format (from static/changes.csv)"""
    try:
        csv_path = get_resource_path("static/changes.csv")
        if not csv_path or not os.path.exists(csv_path):
            raise HTTPException(status_code=404, detail="Changes not found")
        df = pd.read_csv(csv_path)
        data = df.where(pd.notnull(df), None).to_dict(orient="records")
        return JSONResponse(content=data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading changes.csv: {str(e)}")


# This must be the last route to catch all other routes
@app.get("/{rest_of_path:path}")
async def serve_frontend(rest_of_path: str):
    dist_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dist"))
    # This is the file path to check
    file_path = os.path.join(dist_dir, rest_of_path)

    # If the file exists and it's a file, serve it
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return FileResponse(file_path)

    # Otherwise, it's a route for the SPA, so serve index.html
    index_path = os.path.join(dist_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    
    # If index.html doesn't exist, then something is wrong with the frontend build
    raise HTTPException(status_code=404, detail="Frontend not found. Make sure you have built the frontend and the 'dist' directory is correct.")

def get_data_dir():
    """获取用户数据目录"""
    if sys.platform == "darwin":  # macOS
        return os.path.expanduser("~/Library/Application Support/YourAppName")
    elif sys.platform == "win32":  # Windows
        return os.path.expanduser("~/AppData/Local/YourAppName")
    else:  # Linux
        return os.path.expanduser("~/.local/share/YourAppName")

def get_resource_path(relative_path):
    """获取资源文件的路径，支持开发环境和打包环境"""
    try:
        # PyInstaller 创建临时文件夹 _MEIpass，并将路径存储在 _MEIPASS 中
        if hasattr(sys, '_MEIPASS'):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
        
        full_path = os.path.join(base_path, relative_path)
        if os.path.exists(full_path):
            return full_path
        else:
            print(f"Warning: Resource not found at {full_path}")
            return None
    except Exception as e:
        print(f"Error accessing resource path: {e}")
        return None

def setup_static_directory():
    """设置静态文件目录"""
    if hasattr(sys, '_MEIPASS'):
        # 打包后：在用户数据目录创建
        static_dir = os.path.join(get_data_dir(), "static")
    else:
        # 开发模式：在当前目录创建
        static_dir = "static"

    os.makedirs(static_dir, exist_ok=True)
    return static_dir


async def broadcast_message(message: str):
    """向所有连接的WebSocket客户端广播消息"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_message = f"[{timestamp}] {message}"
    log_messages.append(formatted_message)
    
    # 广播到所有活动的WebSocket连接
    disconnected = set()
    for websocket in active_websockets:
        try:
            await websocket.send_text(formatted_message)
        except Exception:
            disconnected.add(websocket)
    
    # 移除断开的连接
    active_websockets.difference_update(disconnected)

def output_reader(pipe, name):
    """从管道读取输出并打印"""
    for line in pipe:
        message = f"[{name}] {line.strip()}"
        print(message)
        # 使用asyncio创建一个新的事件循环来发送WebSocket消息
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(broadcast_message(message))
        loop.close()


# Programmatically force shutdown this sidecar.
def kill_process():
    global server_instance
    if server_instance is not None:
        try:
            server_instance.should_exit = True  # 通知 Uvicorn 退出
        except Exception:
            pass
    os._exit(0)  # 强制退出整个进程


# Programmatically startup the api server
def start_api_server(**kwargs):
    global server_instance
    port = kwargs.get("port", PORT_API)
    try:
        if server_instance is None:
            print("[sidecar] Starting API server...", flush=True)
            config = Config(app, host="0.0.0.0", port=port, log_level="info")
            server_instance = Server(config)
            # Start the ASGI server
            # Use a more robust approach to run the server
            try:
                server_instance.run()
            except Exception as e:
                print(f"[sidecar] API server error: {e}", flush=True)
        else:
            print(
                "[sidecar] Failed to start new server. Server instance already running.",
                flush=True,
            )
    except Exception as e:
        print(f"[sidecar] Error, failed to start API server {e}", flush=True)


# Handle the stdin event loop. This can be used like a CLI.
def stdin_loop():
    print("[sidecar] Waiting for commands...", flush=True)
    try:
        while True:
            # Read input from stdin.
            user_input = sys.stdin.readline().strip()

            # Check if the input matches one of the available functions
            match user_input:
                case "sidecar shutdown":
                    print("[sidecar] Received 'sidecar shutdown' command.", flush=True)
                    kill_process()
                case _:
                    print(
                        f"[sidecar] Invalid command [{user_input}]. Try again.", flush=True
                    )
    except Exception as e:
        print(f"[sidecar] stdin_loop error: {e}", flush=True)


# Start the input loop in a separate thread
def start_input_thread():
    try:
        input_thread = threading.Thread(target=stdin_loop)
        input_thread.daemon = True  # so it exits when the main program exits
        input_thread.start()
    except Exception as e:
        print(f"[sidecar] Failed to start input handler: {e}", flush=True)


if __name__ == "__main__":
    # 启动时自动以子进程方式调用一次 getConcepts
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    # 判断当前时间是否晚于9:15，晚于则不启动getConcepts子进程
    now = datetime.now()
    if now.hour < 9 or (now.hour == 9 and now.minute <= 15):
        try:
            get_concepts_proc = subprocess.Popen([
                sys.executable, "-c", "from concepts import getConcepts; getConcepts()"
            ], cwd=backend_dir)
            print("[sidecar] 启动时已自动调用 getConcepts 子进程", flush=True)
        except Exception as e:
            print(f"[sidecar] 自动调用 getConcepts 失败: {e}", flush=True)
    else:
        print("[sidecar] 当前已晚于9:15，未启动 getConcepts 子进程", flush=True)

    static_path = setup_static_directory()
    
    # Load concepts data at startup
    try:
        concepts_path = get_resource_path("static/concepts.csv")
        concept_df = pd.read_csv(concepts_path)
        print("[sidecar] Successfully loaded concepts data from: " + concepts_path, flush=True)
    except Exception as e:
        print(f"[sidecar] Error loading concepts data: {e}", flush=True)
        concept_df = pd.DataFrame()  # Create empty DataFrame if loading fails

    # 启动 get_changes_worker_queue 进程，实时写入队列
    from get_changes_worker_queue import worker as changes_worker
    get_changes_proc = Process(target=changes_worker, args=(concept_df, buffer_queue, 2), daemon=True)
    get_changes_proc.start()

    # Listen for stdin from parent process
    start_input_thread()

    # Starts API server, blocks further code from execution.
    try:
        start_api_server()
    except Exception as e:
        print(f"[sidecar] Fatal error in main thread: {e}", flush=True)
        sys.exit(1)
