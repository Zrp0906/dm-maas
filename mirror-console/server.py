"""Loopback-only browser console for a Mirror running DexOS Lite."""

from __future__ import annotations

import argparse
from collections import deque
from contextlib import ExitStack
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
import logging
import os
from pathlib import Path
import signal
import socket
from threading import Event, Lock, Thread
from time import monotonic, sleep, strftime


DIRECTORY = Path(__file__).resolve().parent
CAMERAS = ("cam_high", "cam_left_wrist", "cam_right_wrist")
FRAME_MAX_AGE = 2
ACTIVE_PHASES = {"starting", "running", "stopping", "homing"}
LOGGER = logging.getLogger("mirror-console")


class CameraPreview:
    """Own the RealSense streams and share their latest JPEGs with the UI and SDK."""

    def __init__(self, sensors):
        self.sensors = sensors
        self.frames = {}
        self.lock = Lock()
        self.stop = Event()
        self.thread = Thread(target=self.capture, name="mirror-cameras")
        self.failed = False

    def capture(self):
        try:
            from PIL import Image

            with ExitStack() as streams:
                for sensor in self.sensors.values():
                    sensor.start()
                    streams.callback(sensor.close)
                while not self.stop.is_set():
                    for name, sensor in self.sensors.items():
                        ok, frame = sensor.get(timeout=0.2)
                        if not ok:
                            continue
                        output = BytesIO()
                        Image.fromarray(frame["rgb"]["data"]).save(output, "JPEG", quality=85)
                        with self.lock:
                            self.frames[name] = (monotonic(), output.getvalue())
                    self.stop.wait(0.10)
        except Exception:
            with self.lock:
                self.failed = True
            LOGGER.exception("相机预览已退出。请检查相机连接或退出占用相机的程序。")

    def snapshot(self):
        with self.lock:
            now = monotonic()
            return {
                name: jpeg
                for name, (captured, jpeg) in self.frames.items()
                if not self.failed and now - captured < FRAME_MAX_AGE
            }


class CameraForInference:
    """Adapter for MirrorRobot.get(); the preview thread owns the camera lifecycle."""

    started = True

    def __init__(self, preview, name):
        self.preview = preview
        self.name = name

    def get(self, timeout=1.0):
        jpeg = self.preview.snapshot().get(self.name)
        if jpeg is None:
            raise RuntimeError(f"相机 {self.name} 无有效画面")
        return True, {"rgb": {"data": jpeg}}

    def close(self):
        # MirrorRobot closes its adapters between jobs. The preview keeps streaming.
        pass


class MirrorBackend:
    def __init__(self, config_path):
        from dexos_lite.robot import MirrorRobot, load_robot_config

        self.robot = load_robot_config(str(config_path))
        if not isinstance(self.robot, MirrorRobot) or not set(CAMERAS).issubset(self.robot.sensors):
            raise ValueError("请使用包含主视角、左腕和右腕的 MirrorRobot 配置。")
        sensors = {name: self.robot.sensors[name] for name in CAMERAS}
        self.serials = {name: sensor.serial_number for name, sensor in sensors.items()}
        self.preview = CameraPreview(sensors)
        self.robot.sensors = {name: CameraForInference(self.preview, name) for name in sensors}
        self.preview.thread.start()

    def frames(self):
        return self.preview.snapshot()

    def check_arm_services(self):
        for port in (50051, 50053):
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                pass

    def run(self, prompt, seconds, abort, running, received):
        from dexos_lite.inference import infer_robot_continuous
        from dexos_lite.utils.client import DexosClient

        self.check_arm_services()
        # A stop request should not wait through SDK retries.
        client = DexosClient(timeout=20, max_retries=0)
        if abort.is_set() or len(self.frames()) != len(CAMERAS):
            return
        self.robot.start()
        if abort.is_set():
            return
        self.robot.reset_to_home()
        if abort.is_set():
            return
        running()
        deadline = monotonic() + seconds
        infer_robot_continuous(
            self.robot,
            client,
            model_id="dm05",
            prompt=prompt,
            should_stop=lambda: (
                abort.is_set() or monotonic() >= deadline or len(self.frames()) != len(CAMERAS)
            ),
            actions_received_callback=received,
        )

    def close_run(self):
        self.robot.close()

    def return_home(self):
        self.check_arm_services()
        try:
            self.robot.start()
            self.robot.reset_to_home()
        finally:
            self.close_run()

    def close(self):
        self.preview.stop.set()
        self.preview.thread.join()


class DemoBackend:
    serials = {
        "cam_high": "demo-high",
        "cam_left_wrist": "demo-left-wrist",
        "cam_right_wrist": "demo-right-wrist",
    }

    def __init__(self):
        photos = DIRECTORY.parent / "mirror-cameras"
        self.images = {
            name: (photos / f"{label}.jpg").read_bytes() for name, label in self.serials.items()
        }

    def frames(self):
        return self.images

    def run(self, prompt, seconds, abort, running, received):
        if abort.wait(0.6):
            return
        running()
        deadline = monotonic() + seconds
        while not abort.is_set() and monotonic() < deadline:
            received(20)
            abort.wait(min(1.5, max(0, deadline - monotonic())))

    def close_run(self):
        pass

    def return_home(self):
        pass

    def close(self):
        pass


class Console:
    def __init__(self, backend, demo):
        self.backend = backend
        self.demo = demo
        self.lock = Lock()
        self.abort = Event()
        self.phase = "idle"
        self.events = deque(maxlen=6)
        self.horizons = 0
        self.worker = None
        self.closed = False
        self.home_requested = False
        self.needs_home = False
        self.record("模拟控制台已打开" if demo else "控制台已打开，正在读取相机")

    def record(self, message):
        """Called with the console lock held, or during construction."""
        self.events.appendleft({"time": strftime("%H:%M:%S"), "message": message})

    def status(self):
        frames = self.backend.frames()
        with self.lock:
            return {
                "demo": self.demo,
                "phase": self.phase,
                "closing": self.closed,
                "cameras": {
                    name: {"serial": serial, "available": name in frames}
                    for name, serial in self.backend.serials.items()
                },
                "horizons": self.horizons,
                "events": list(self.events),
            }

    def start(self, prompt, seconds):
        with self.lock:
            if self.closed:
                raise ValueError("控制台正在关闭。")
            if self.phase in ACTIVE_PHASES:
                raise ValueError("已有任务在运行或停止中。")
            if self.phase == "locked":
                raise ValueError("检查工控机终端的清理报错后，重启控制台。")
            if len(self.backend.frames()) != len(CAMERAS):
                raise ValueError("等待三路相机画面就绪。")
            self.abort.clear()
            self.home_requested = False
            self.phase = "starting"
            self.horizons = 0
            self.record("正在启动模拟任务" if self.demo else "正在连接双臂并回零")
            self.worker = Thread(target=self.run, args=(prompt, seconds), name="mirror-inference")
            self.worker.start()

    def running(self):
        with self.lock:
            if not self.abort.is_set():
                self.needs_home = True
                self.phase = "running"
                self.record("正在模拟推理" if self.demo else "已开始 DM0.5 推理")

    def received(self, action_count):
        with self.lock:
            self.horizons += 1
            if self.horizons == 1:
                self.record(f"{'模拟' if self.demo else '收到'}首批动作 · {action_count} 步")

    def run(self, prompt, seconds):
        phase = "idle"
        message = "任务结束"
        try:
            self.backend.run(prompt, seconds, self.abort, self.running, self.received)
            if not self.abort.is_set() and len(self.backend.frames()) != len(CAMERAS):
                phase = "error"
                message = "相机画面中断，任务已退出"
        except (ConnectionRefusedError, TimeoutError):
            phase = "error"
            message = "连接超时或被拒绝，请检查双臂服务和工控机网络"
            LOGGER.exception(message)
        except Exception:
            phase = "error"
            message = "任务失败，请查看工控机终端日志"
            LOGGER.exception(message)
        finally:
            try:
                self.backend.close_run()
            except Exception:
                phase = "locked"
                message = "控制连接清理失败，请现场检查后重启控制台"
                LOGGER.exception(message)
            with self.lock:
                home = phase == "idle" and self.home_requested and self.needs_home
                self.phase = "homing" if home else phase
                if not home:
                    if phase == "idle" and self.abort.is_set():
                        message = "推理已停止"
                    self.record(message)
            if home:
                self.return_home()

    def return_home(self):
        """Complete a home operation reserved by setting the phase to homing."""
        with self.lock:
            self.record("推理已结束，正在回零")
        LOGGER.info("正在回零。")
        try:
            self.backend.return_home()
        except Exception:
            with self.lock:
                self.phase = "locked"
                self.record("回零失败，请现场检查和查看工控机日志")
            LOGGER.exception("回零失败。")
        else:
            message = "模拟回零完成。" if self.demo else "回零指令已执行，请现场确认双臂停稳。"
            LOGGER.info(message)
            with self.lock:
                self.needs_home = False
                self.phase = "idle"
                self.record(message)

    def stop(self, *, return_home=False):
        with self.lock:
            if return_home and self.closed:
                return
            if self.phase in {"starting", "running", "stopping"}:
                if return_home:
                    self.home_requested = True
                if self.phase != "stopping":
                    self.abort.set()
                    self.phase = "stopping"
                    self.record("已请求停止，正在等待当前操作结束")
            elif return_home and self.phase == "idle" and self.needs_home:
                # The task can reach its time limit just before the stop request arrives.
                self.phase = "homing"
                self.worker = Thread(target=self.return_home, name="mirror-homing")
                self.worker.start()

    def close(self, *, return_home=False):
        with self.lock:
            self.closed = True
        self.stop()
        try:
            if self.worker is not None:
                self.worker.join()
            if return_home:
                with self.lock:
                    failed = self.phase in {"error", "locked"}
                    home = self.phase == "idle" and self.needs_home
                    if home:
                        self.phase = "homing"
                if failed:
                    LOGGER.warning("任务或控制连接发生故障，退出时跳过回零。")
                if home:
                    self.return_home()
        finally:
            self.backend.close()


class Handler(BaseHTTPRequestHandler):
    def allowed_hosts(self):
        port = self.server.server_port
        return (f"127.0.0.1:{port}", f"localhost:{port}")

    def respond(self, code, data, mime="application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' blob:; "
            "frame-ancestors 'none'; form-action 'none'",
        )
        self.end_headers()
        self.wfile.write(data)

    def json_response(self, code, data):
        self.respond(code, json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def do_GET(self):
        if self.headers.get("Host") not in self.allowed_hosts():
            self.json_response(HTTPStatus.FORBIDDEN, {"error": "请使用本机地址访问。"})
            return
        path = self.path.partition("?")[0]
        if path == "/":
            self.respond(HTTPStatus.OK, (DIRECTORY / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif path == "/api/status":
            self.json_response(HTTPStatus.OK, self.server.console.status())
        elif path.startswith("/camera/") and path.endswith(".jpg"):
            name = path.removeprefix("/camera/").removesuffix(".jpg")
            frame = self.server.console.backend.frames().get(name)
            if frame is None:
                self.json_response(HTTPStatus.NOT_FOUND, {"error": "暂无相机画面。"})
            else:
                self.respond(HTTPStatus.OK, frame, "image/jpeg")
        else:
            self.json_response(HTTPStatus.NOT_FOUND, {"error": "页面不存在。"})

    def do_POST(self):
        host = self.headers.get("Host")
        if host not in self.allowed_hosts() or self.headers.get("Origin") != f"http://{host}":
            self.json_response(HTTPStatus.FORBIDDEN, {"error": "操作请求必须来自控制台。"})
            return
        console = self.server.console
        if self.path == "/api/stop":
            console.stop(return_home=True)
            self.json_response(HTTPStatus.ACCEPTED, console.status())
            return
        if self.path != "/api/start":
            self.json_response(HTTPStatus.NOT_FOUND, {"error": "操作不存在。"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 65536 or self.headers.get_content_type() != "application/json":
                raise ValueError
            body = json.loads(self.rfile.read(length))
            prompt = body.get("prompt")
            seconds = body.get("seconds")
            if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 8192:
                raise ValueError
            if type(seconds) is not int or not 1 <= seconds <= 600:
                raise ValueError
        except (ValueError, AttributeError):
            self.json_response(HTTPStatus.BAD_REQUEST, {"error": "请填写抓取指令和 1–600 秒的时限。"})
            return
        try:
            console.start(prompt.strip(), seconds)
        except ValueError as error:
            self.json_response(HTTPStatus.CONFLICT, {"error": str(error)})
            return
        self.json_response(HTTPStatus.ACCEPTED, console.status())

    def log_request(self, code="-", size="-"):
        # Status and camera polling would otherwise dominate the terminal log.
        if not self.path.startswith(("/api/status", "/camera/")):
            super().log_request(code, size)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--robot-config", type=Path, default=Path.home() / "mirror_config.py")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    if not args.demo and not os.environ.get("DEXOS_API_KEY"):
        parser.error("请先在工控机的当前终端设置 DEXOS_API_KEY。")
    logging.basicConfig(level=logging.INFO)

    shutdown_signal = None

    def interrupt(signum, frame):
        nonlocal shutdown_signal
        if shutdown_signal is None:
            shutdown_signal = signum

    signal.signal(signal.SIGINT, interrupt)
    signal.signal(signal.SIGTERM, interrupt)
    with ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as server:
        backend = DemoBackend() if args.demo else MirrorBackend(args.robot_config.expanduser())
        server.console = Console(backend, args.demo)
        # Keep the status endpoint available during shutdown so the browser can stop polling.
        listener = Thread(
            target=server.serve_forever, kwargs={"poll_interval": 0.2}, name="mirror-http"
        )
        listener.start()
        try:
            print(f"Mirror 控制台 · http://127.0.0.1:{server.server_port}", flush=True)
            while shutdown_signal is None and listener.is_alive():
                sleep(0.1)
        finally:
            try:
                LOGGER.info("正在关闭控制台，等待当前任务退出。")
                server.console.close(return_home=shutdown_signal == signal.SIGINT)
            finally:
                server.shutdown()
                listener.join()


if __name__ == "__main__":
    main()
