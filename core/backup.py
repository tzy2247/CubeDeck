"""备份与轮转工具（与 UI 解耦，纯函数）。"""
import datetime
import shutil
import time
from pathlib import Path

# 这些文件是运行时锁 / 缓存，无需备份
SKIP_FILES = {
    "session.lock",
}
# ============================================================
#  打开文件夹（跨平台）
# ============================================================
def open_folder(path):
    """跨平台打开文件夹。"""
    import os
    import subprocess
    import sys

    path = str(path)
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception:
        return False


# ============================================================
#  恢复备份
# ============================================================
def restore_backup(server_path, backup_path, log=None, progress=None):
    """
    从备份恢复世界。

    流程：
    1. 安全检查
    2. 保存当前状态到 restore_backups/before_restore_xxx
    3. 清空服务器目录（保留 logs / backups）
    4. 从备份复制回服务器目录

    返回 (ok, result)。
    ok=True 时 result 是快照目录路径；
    ok=False 时 result 是错误信息。
    """
    import shutil
    import datetime

    if log is None:
        log = lambda m, t="info": None

    server_path = Path(server_path).resolve()
    backup_path = Path(backup_path).resolve()

    # ---------- 1. 安全检查 ----------
    if not backup_path.exists() or not backup_path.is_dir():
        return False, f"备份不存在：{backup_path}"

    if not server_path.exists() or not server_path.is_dir():
        return False, f"服务器目录不存在：{server_path}"

    # 防止把备份目录恢复到自己
    try:
        backup_path.relative_to(server_path)
        return False, "备份目录位于服务器目录内，无法恢复（会造成死循环）"
    except ValueError:
        pass

    contents = list(backup_path.iterdir())
    if not contents:
        return False, "备份目录为空"

    # 检查是否像一份 MC 服务器备份
    markers = {"level.dat", "server.properties", "world"}
    if not any(m in {c.name for c in contents} for m in markers):
        log("⚠ 备份内容看起来不完整（缺少 level.dat / server.properties / world）",
            "warn")

    # ---------- 2. 保存当前状态 ----------
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_dir = (server_path.parent / "restore_backups"
                    / f"before_restore_{ts}")

    try:
        snapshot_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return False, f"无法创建恢复前快照目录：{e}"

    log(f"保存当前状态到 {snapshot_dir.name}…", "info")
    skip_names = {"logs", "backups"}

    try:
        for item in server_path.iterdir():
            if item.name in skip_names:
                continue
            target = snapshot_dir / item.name
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
            else:
                shutil.copy2(item, target)
    except Exception as e:
        return False, f"保存当前状态失败：{e}"

    log(f"当前状态已保存到：{snapshot_dir}", "ok")

    # ---------- 3. 清空服务器目录 ----------
    log("正在清空服务器目录…", "info")
    try:
        for item in server_path.iterdir():
            if item.name in skip_names:
                continue
            try:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            except Exception as e:
                log(f"  无法删除 {item.name}：{e}", "warn")
    except Exception as e:
        return False, f"清空服务器目录失败：{e}"

    # ---------- 4. 从备份复制 ----------
    log("正在从备份复制文件…", "info")
    items = list(backup_path.iterdir())
    total = len(items)
    copied = 0

    for i, item in enumerate(items):
        if progress:
            try:
                progress(i + 1, total, item.name)
            except Exception:
                pass

        target = server_path / item.name
        try:
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
            else:
                shutil.copy2(item, target)
            copied += 1
        except Exception as e:
            log(f"  复制 {item.name} 失败：{e}", "warn")

    log(f"恢复完成，共复制 {copied}/{total} 个条目", "ok")
    log(f"（恢复前的状态保存在 {snapshot_dir.name}，可手动回滚）", "info")

    return True, str(snapshot_dir)


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
    skipped_files = 0
    errors = []

    try:
        items = list(server_path.iterdir())
        log(f"发现 {len(items)} 个待处理条目", "info")
        for item in items:
            if item.name in skip_names:
                continue
            target = dest / item.name
            if item.is_dir():
                # 递归复制目录，逐文件处理
                files, dirs, skipped, errs = _copy_tree(
                    item, target, log)
                copied_files += files
                copied_dirs += 1
                skipped_files += skipped
                errors.extend(errs)
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
    extra = []
    if skipped_files:
        extra.append(f"跳过 {skipped_files} 个锁定文件")
    if errors:
        extra.append(f"{len(errors)} 个错误")
    extra_str = "，" + "，".join(extra) if extra else ""

    summary = (f"备份完成：{dest.name}"
               f"（{copied_dirs} 目录 / {copied_files} 文件 / {size_str}{extra_str}）")
    if errors:
        log(summary, "warn")
    else:
        log(summary, "ok")
    return True, dest, summary

def _copy_tree(src_dir: Path, dst_dir: Path, log):
    """
    递归复制目录，逐文件 try。
    锁定文件 / 忽略列表文件会跳过，不影响整个目录。
    返回 (copied_files, copied_dirs, skipped_files, errors)。
    """
    copied_files = 0
    copied_dirs = 0
    skipped = 0
    errors = []

    try:
        dst_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return 0, 0, 0, [f"{dst_dir.name}: {e}"]

    for item in src_dir.iterdir():
        target = dst_dir / item.name

        if item.is_dir():
            f, d, s, e = _copy_tree(item, target, log)
            copied_files += f
            copied_dirs += d
            skipped += s
            errors.extend(e)
            continue

        # 文件
        if item.name in SKIP_FILES:
            skipped += 1
            continue

        try:
            shutil.copy2(item, target)
            copied_files += 1
        except (PermissionError, OSError) as e:
            # 常见于 Minecraft 运行时锁：session.lock
            skipped += 1
            log(f"  跳过锁定文件 {item.name}（运行时锁，无需备份）", "info")
        except Exception as e:
            skipped += 1
            errors.append(f"{item.name}: {e}")
            log(f"  跳过文件 {item.name}：{e}", "warn")

    return copied_files, copied_dirs, skipped, errors


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