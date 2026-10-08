"""备份与轮转工具（与 UI 解耦，纯函数）。"""
import datetime
import shutil
import time
from pathlib import Path


def format_size(num_bytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} PB"


def perform_backup(server_path: Path, rcon=None, log=None):
    """
    执行一次完整备份。返回 (ok, dest_path, summary)。
    rcon 若已连接，会先冻结世界保存再复制。
    """
    if log is None:
        log = lambda m, t="info": None

    if not server_path.exists() or not server_path.is_dir():
        log(f"备份失败：服务器目录无效 → {server_path}", "error")
        return False, None, "服务器目录无效"

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_root = server_path.parent / "backups"
    dest = backup_root / f"backup_{ts}"

    try:
        dest.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        log(f"备份失败：无法创建目录 → {e}", "error")
        return False, None, str(e)

    log(f"备份源：{server_path}", "info")
    log(f"备份到：{dest}", "info")

    frozen = False
    if rcon and getattr(rcon, "connected", False):
        try:
            rcon.command("save-off")
            rcon.command("save-all flush")
            frozen = True
            time.sleep(2)
            log("已冻结世界保存，开始复制…", "info")
        except Exception as e:
            log(f"冻结保存失败（继续复制）：{e}", "warn")

    skip_names = {"logs", "backups"}
    copied_files = 0
    copied_dirs = 0
    errors = []

    try:
        items = list(server_path.iterdir())
        log(f"发现 {len(items)} 个待处理条目", "info")
        for item in items:
            if item.name in skip_names:
                continue
            target = dest / item.name
            if item.is_dir():
                try:
                    shutil.copytree(item, target, dirs_exist_ok=True)
                    copied_dirs += 1
                except Exception as e:
                    errors.append(item.name)
                    log(f"跳过目录 {item.name}/：{e}", "warn")
            else:
                try:
                    shutil.copy2(item, target)
                    copied_files += 1
                except Exception as e:
                    errors.append(item.name)
                    log(f"跳过文件 {item.name}：{e}", "warn")
    finally:
        if frozen and rcon and getattr(rcon, "connected", False):
            try:
                rcon.command("save-on")
                log("已恢复世界保存", "ok")
            except Exception:
                pass

    if copied_files == 0 and copied_dirs == 0:
        log("备份失败：没有复制任何内容", "error")
        try:
            if not any(dest.iterdir()):
                dest.rmdir()
                log("已清理空备份目录", "info")
        except Exception:
            pass
        return False, None, "没有复制任何内容"

    total_bytes = 0
    try:
        for p in dest.rglob("*"):
            if p.is_file():
                try:
                    total_bytes += p.stat().st_size
                except OSError:
                    pass
    except Exception:
        pass

    size_str = format_size(total_bytes)
    summary = f"{dest.name}（{copied_dirs} 目录 / {copied_files} 文件 / {size_str}）"
    if errors:
        log(f"备份完成：{summary}，跳过 {len(errors)} 个条目", "warn")
    else:
        log(f"备份完成：{summary}", "ok")
    return True, dest, summary


def rotate_backups(server_path: Path, keep: int, log=None):
    """只保留最新的 keep 个备份。"""
    if log is None:
        log = lambda m, t="info": None
    try:
        root = server_path.parent / "backups"
        if not root.exists():
            return
        backups = sorted(root.glob("backup_*"), key=lambda p: p.name)
        keep = max(1, int(keep))
        for old in backups[:-keep]:
            shutil.rmtree(old, ignore_errors=True)
            log(f"🗑 轮转清理：{old.name}", "info")
    except Exception as e:
        log(f"轮转失败：{e}", "warn")