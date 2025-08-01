import os
import sys
import asyncio
import threading
from fastapi import FastAPI, Body, WebSocket
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from uvicorn import Config, Server
import subprocess
import sys
import pandas as pd
from collections import deque
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager
from fluctuation import getChanges

PORT_API = 61125

# Global variables
server_instance = None  # Global reference to the Uvicorn server instance
concept_df = None  # Global variable for concepts data
log_messages = deque(maxlen=1000)  # Store last 1000 log messages
active_websockets = set()  # Store active WebSocket connections

# --- Move lifespan definition above app creation ---
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start the fluctuation watch
    global watch_process
    try:
        backend_dir = os.path.dirname(os.path.abspath(__file__))
        fluctuation_path = os.path.join(backend_dir, "fluctuation.py")
        watch_process = subprocess.Popen(
            [sys.executable, fluctuation_path],
            cwd=backend_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # 行缓冲
            universal_newlines=True
        )
        print(f"Started fluctuation watch with PID: {watch_process.pid}")

        # 启动输出读取线程
        import threading
        threading.Thread(
            target=output_reader,
            args=(watch_process.stdout, "fluctuation"),
            daemon=True
        ).start()

        # 启动错误输出读取线程
        threading.Thread(
            target=output_reader,
            args=(watch_process.stderr, "fluctuation-err"),
            daemon=True
        ).start()

        yield
    finally:
        # Shutdown: Stop the fluctuation watch
        if watch_process:
            watch_process.terminate()
            try:
                watch_process.wait(timeout=5)
                print("Fluctuation watch stopped gracefully")
            except subprocess.TimeoutExpired:
                watch_process.kill()
                print("Fluctuation watch was force stopped")

app = FastAPI(
    title="API server",
    version="0.1.0",
    lifespan=lifespan,  # 加上这一行
)

# Configure CORS settings
origins = [
    "http://localhost:1420",  # for Tauri dev
    "tauri://localhost",      # for Tauri prod
    "http://localhost:61125"  # for API server
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,  # Required for WebSocket
    allow_methods=["*"],
    allow_headers=["*"],
)

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

@app.post("/api/watch/restart")
async def restart_watch():
    """Restart the fluctuation watch process"""
    global watch_process

    # Stop existing process if running
    if watch_process:
        watch_process.terminate()
        try:
            watch_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            watch_process.kill()

    # Start new process
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    fluctuation_path = os.path.join(backend_dir, "fluctuation.py")
    watch_process = subprocess.Popen(
        [sys.executable, fluctuation_path],
        cwd=backend_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    return {"status": "restarted", "pid": watch_process.pid}

@app.get("/api/changes/json")
async def get_changes_json():
    """Get changes data in JSON format"""
    global concept_df
    # csv_path = get_resource_path("static/changes.csv")
    # if not os.path.exists(csv_path):
    #     raise HTTPException(status_code=404, detail="Changes not found")

    try:
        # Use global concept_df to get changes
        df = getChanges(concept_df)
        # Convert DataFrame to list of dicts, replacing NaN with None
        data = df.where(pd.notnull(df), None).to_dict(orient="records")
        return JSONResponse(content=data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading CSV: {str(e)}")

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
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller 创建临时文件夹 _MEIpass，并将路径存储在 _MEIPASS 中
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)

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

# Global variable to store the subprocess reference
watch_process: Optional[subprocess.Popen] = None

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

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start the fluctuation watch
    global watch_process
    try:
        watch_process = subprocess.Popen(
            [sys.executable, "fluctuation.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # 行缓冲
            universal_newlines=True
        )
        print(f"Started fluctuation watch with PID: {watch_process.pid}")

        # 启动输出读取线程
        import threading
        threading.Thread(
            target=output_reader,
            args=(watch_process.stdout, "fluctuation"),
            daemon=True
        ).start()

        # 启动错误输出读取线程
        threading.Thread(
            target=output_reader,
            args=(watch_process.stderr, "fluctuation-err"),
            daemon=True
        ).start()

        yield
    finally:
        # Shutdown: Stop the fluctuation watch
        if watch_process:
            watch_process.terminate()
            try:
                watch_process.wait(timeout=5)
                print("Fluctuation watch stopped gracefully")
            except subprocess.TimeoutExpired:
                watch_process.kill()
                print("Fluctuation watch was force stopped")

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
            asyncio.run(server_instance.serve())
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


# Start the input loop in a separate thread
def start_input_thread():
    try:
        input_thread = threading.Thread(target=stdin_loop)
        input_thread.daemon = True  # so it exits when the main program exits
        input_thread.start()
    except:
        print("[sidecar] Failed to start input handler.", flush=True)


if __name__ == "__main__":
    # You can spawn sub-processes here before the main process.
    # new_command = ["python", "-m", "some_script", "--arg", "argValue"]
    # subprocess.Popen(new_command)
    static_path = setup_static_directory()
    
    # Load concepts data at startup
    try:
        concepts_path = get_resource_path("static/concepts.csv")
        concept_df = pd.read_csv(concepts_path)
        print("[sidecar] Successfully loaded concepts data from: " + concepts_path, flush=True)
    except Exception as e:
        print(f"[sidecar] Error loading concepts data: {e}", flush=True)
        concept_df = pd.DataFrame()  # Create empty DataFrame if loading fails
    
    # Listen for stdin from parent process
    start_input_thread()

    # Starts API server, blocks further code from execution.
    start_api_server()
