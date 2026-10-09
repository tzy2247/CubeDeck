"""服务端进程的脱离启动、检测、接管、停止。"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import psutil

from core import paths


STATE_FILE = paths.STATE_FILE


# ============================================================
#  状态持久化
# ============================================================
def load_state():
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_state(data):
    try:
        paths.ensure_userdata_root()
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        return True
    except Exception:
        return False


def clear_state():
    try:
        if STATE_FILE.exists():
            STATE_FILE.unlink()
    except Exception:
        pass


# ============================================================
#  脱离启动
# ============================================================
def launch_detached(cmd, cwd):
    """
    以脱离父进程的方式启动 Java 服务端。
    - Windows: DETACHED_PROCESS + CREATE_NO_WINDOW
    - Linux/Mac: start_new_session=True
    """
    if sys.platform == "win32":
        flags = (
            subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.DETACHED_PROCESS
            | subprocess.CREATE_NO_WINDOW
        )
        proc = subprocess.Popen(
            cmd, cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
            close_fds=True,
        )
    else:
        proc = subprocess.Popen(
            cmd, cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    return proc


# ============================================================
#  查找正在运行的服务端
# ============================================================
def find_running_server(server_path):
    """
    查找正在运行的服务端。
    优先从状态文件读取 PID，避免遍历所有进程（性能 + 稳定性）。
    返回 dict 或 None。
    """
    # ---------- 1. 优先读状态文件 ----------
    state = load_state()
    pid = state.get("pid")
    create_time = state.get("create_time")

    if pid and is_process_alive(pid, create_time):
        try:
            p = psutil.Process(pid)
            pname = (p.name() or "").lower()
            if "java" in pname:
                return {
                    "pid": pid,
                    "create_time": create_time or 0.0,
                    "cmdline": " ".join(p.cmdline() or [])[:200],
                }
        except Exception:
            pass

    # ---------- 2. 状态文件不可信，遍历进程（兜底）----------
    try:
        target_dir = str(Path(server_path).resolve())
    except Exception:
        return None

    try:
        jar_names = [
            j.name.lower()
            for j in Path(server_path).glob("*.jar")
        ]
    except Exception:
        jar_names = []

    for proc in psutil.process_iter(
            ["pid", "name", "cmdline", "create_time"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if "java" not in name:
                continue

            # ★ 捕获所有异常，不再只捕两种
            try:
                cwd = proc.cwd()
            except Exception:
                continue

            if os.path.normcase(cwd) != os.path.normcase(target_dir):
                continue

            cmdline = " ".join(proc.info.get("cmdline") or []).lower()
            if jar_names and not any(j in cmdline for j in jar_names):
                continue

            return {
                "pid": proc.info["pid"],
                "create_time": proc.info.get("create_time") or 0.0,
                "cmdline": cmdline[:200],
            }
        except Exception:
            # ★ 单个进程出错不影响整体
            continue

    return None


# ============================================================
#  进程存活检查
# ============================================================
def is_process_alive(pid, create_time=None):
    """检查 pid 是否存活。若传入 create_time，用它防止 PID 复用误判。"""
    if not pid:
        return False
    try:
        p = psutil.Process(pid)
        if create_time:
            ct = p.create_time()
            if abs(ct - create_time) > 1.0:
                return False
        return True
    except psutil.NoSuchProcess:
        return False
    except Exception:
        return False


def get_create_time(pid):
    """返回进程创建时间；进程不存在返回 None。"""
    try:
        return psutil.Process(pid).create_time()
    except Exception:
        return None


# ============================================================
#  停止进程
# ============================================================
def kill_process(pid, create_time=None, timeout=10):
    """先 terminate，超时后 kill。返回 True 表示已确认进程退出。"""
    if not is_process_alive(pid, create_time):
        return True
    try:
        p = psutil.Process(pid)
        p.terminate()
        try:
            p.wait(timeout=timeout)
            return True
        except psutil.TimeoutExpired:
            p.kill()
            try:
                p.wait(timeout=3)
            except Exception:
                pass
            return not p.is_running()
    except psutil.NoSuchProcess:
        return True
    except Exception:
        return False


def wait_for_exit(pid, create_time=None, timeout=30, interval=0.5):
    """轮询等待进程退出。返回 True 表示已退出。"""
    start = time.time()
    while time.time() - start < timeout:
        if not is_process_alive(pid, create_time):
            return True
        time.sleep(interval)
    return False