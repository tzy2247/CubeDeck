"""服务端进程的脱离启动、检测、接管、停止。

多服务器适配：
- 状态文件按服务器隔离（set_state_dir 由 AppState 切换时调用）
- 新增 find_running_java_by_cwd，兼容 Forge/NeoForge 脚本启动
- 新增 detect_startup_method，支持 jar / run.bat / run.sh
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import psutil

# ============================================================
#  状态文件（按服务器隔离）
# ============================================================
_STATE_FILE_NAME = "server_state.json"
_default_state_dir = Path(".")

def set_state_dir(d):
    """由 AppState 在切换服务器时更新，让状态文件按服务器独立保存。"""
    global _default_state_dir
    _default_state_dir = Path(d) if d else Path(".")

def _state_file():
    return _default_state_dir / _STATE_FILE_NAME

# ============================================================
#  状态持久化
# ============================================================
def load_state():
    path = _state_file()
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_state(data):
    try:
        path = _state_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        return True
    except Exception:
        return False

def clear_state():
    try:
        path = _state_file()
        if path.exists():
            path.unlink()
    except Exception:
        pass

# ============================================================
#  启动方式检测
# ============================================================
def detect_startup_method(server_path):
    """
    检测服务器启动方式。
    返回 (method_type, target) 或 None。

    method_type:
      "bat" — Windows 启动脚本
      "sh"  — Linux/Mac 启动脚本
      "jar" — 直接 jar
    """
    p = Path(server_path)
    if not p.exists():
        return None

    # 1. Windows 脚本
    for name in ("run.bat", "start.bat", "launch.bat"):
        f = p / name
        if f.exists():
            return ("bat", f)

    # 2. Unix 脚本
    for name in ("run.sh", "start.sh", "launch.sh"):
        f = p / name
        if f.exists():
            return ("sh", f)

    # 3. jar 文件
    jars = sorted(p.glob("*.jar"))
    # 优先选包含 server / paper / purpur / forge / fabric 字样的
    for j in jars:
        low = j.name.lower()
        if any(k in low for k in
               ("server", "paper", "purpur", "forge", "fabric", "neoforge")):
            return ("jar", j)
    if jars:
        return ("jar", jars[0])

    return None

# ============================================================
#  脱离启动
# ============================================================
def launch_detached(cmd, cwd, env=None):
    """
    以脱离父进程的方式启动服务端。
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
            cmd, cwd=str(cwd), env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
            close_fds=True,
        )
    else:
        proc = subprocess.Popen(
            cmd, cwd=str(cwd), env=env,
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
    严格匹配：工作目录 == server_path 且 命令行包含目录下的 jar 名。
    适用于直接 java -jar server.jar 启动的进程。
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

def find_running_java_by_cwd(server_path):
    """
    宽松匹配：只按工作目录匹配 Java 进程。
    适用于 Forge / NeoForge 脚本启动（java @user_jvm_args.txt @libraries/...）。
    """
    target_dir = str(Path(server_path).resolve())
    my_pid = os.getpid()

    for proc in psutil.process_iter(["pid", "name", "create_time"]):
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

            return {
                "pid": pid,
                "create_time": proc.info.get("create_time") or 0.0,
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
    try:
        return psutil.Process(pid).create_time()
    except Exception:
        return None

# ============================================================
#  停止进程
# ============================================================
def kill_process(pid, create_time=None, timeout=10):
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
    start = time.time()
    while time.time() - start < timeout:
        if not is_process_alive(pid, create_time):
            return True
        time.sleep(interval)
    return False