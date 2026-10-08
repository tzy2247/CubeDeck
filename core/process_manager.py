"""服务端进程的脱离启动、检测、接管、停止。"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import psutil

STATE_FILE = Path("server_state.json")


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

    启动后 stdin/stdout/stderr 都与管理器断开，
    服务端自己写日志到 logs/latest.log。
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
    在 server_path 目录下查找正在运行的 Java 服务端进程。
    匹配条件：java.exe + 工作目录 == server_path + 命令行包含目录下的 jar。
    返回 dict 或 None。
    """
    target_dir = str(Path(server_path).resolve())
    my_pid = os.getpid()

    jar_names = [j.name.lower() for j in Path(server_path).glob("*.jar")]

    for proc in psutil.process_iter(
            ["pid", "name", "cmdline", "create_time"]):
        try:
            pid = proc.info["pid"]
            if pid == my_pid:
                continue

            name = (proc.info.get("name") or "").lower()
            if "java" not in name:
                continue

            try:
                cwd = proc.cwd()
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                continue
            if os.path.normcase(cwd) != os.path.normcase(target_dir):
                continue

            cmdline = " ".join(proc.info.get("cmdline") or []).lower()
            if jar_names and not any(j in cmdline for j in jar_names):
                continue

            return {
                "pid": pid,
                "create_time": proc.info.get("create_time") or 0.0,
                "cmdline": cmdline[:200],
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        except Exception:
            continue

    return None


# ============================================================
#  进程存活检查
# ============================================================
def is_process_alive(pid, create_time=None):
    """
    检查 pid 是否存活。若传入 create_time，用它防止 PID 复用误判。
    """
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
    """
    先 terminate，超时后 kill。
    返回 True 表示已确认进程退出。
    """
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