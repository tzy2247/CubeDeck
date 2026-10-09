"""模组安装器：递归解析并安装依赖。

参考 PCL 的 LoaderCombo 思路：
1. 解析目标项目的文件
2. 找出所有 required 依赖
3. 逐个递归解析（防止循环）
4. 按依赖顺序下载
"""
import threading
from pathlib import Path
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class InstallTask:
    """单个待安装任务。"""
    project_id: str
    project_title: str
    file: object          # StoreFile
    target_dir: Path
    source: str = ""


@dataclass
class InstallPlan:
    """安装计划。"""
    tasks: list = field(default_factory=list)      # [InstallTask]
    skipped: list = field(default_factory=list)    # 已有 / 冲突


class ModInstaller:
    """
    递归安装项目及其依赖。
    用法：
        installer = ModInstaller(store_manager, log_cb)
        plan = installer.build_plan(project_id, game_version, loader)
        installer.execute(plan, target_dir, progress_cb)
    """

    def __init__(self, store, log_callback=None):
        """
        store: StoreManager（提供 search / get_project / get_files）
        log_callback: (msg, tag) -> None
        """
        self.store = store
        self.log = log_callback or (lambda m, t="info": None)

    # ========================================================
    #  构建安装计划（递归解析依赖）
    # ========================================================
    def build_plan(self, root_project_id, root_title,
                   game_version=None, loader=None,
                   max_depth=3):
        """
        递归解析根项目及其依赖，返回 InstallPlan。
        max_depth 防止依赖树爆炸。
        """
        plan = InstallPlan()
        visited = set()      # 已访问的 project_id，避免循环

        def _resolve(project_id, title, depth):
            if not project_id or project_id in visited:
                return
            if depth > max_depth:
                self.log(f"  ⚠ 依赖层级过深，跳过 {title}", "warn")
                return

            visited.add(project_id)

            # 获取该项目的文件
            try:
                files = self.store.get_files(
                    project_id,
                    game_version=game_version,
                    loader=loader)
            except Exception as e:
                self.log(f"  ✖ 无法获取 {title} 的文件：{e}", "error")
                return

            if not files:
                self.log(f"  ⚠ {title} 没有兼容版本", "warn")
                plan.skipped.append((project_id, title, "无兼容版本"))
                return

            # 选 release 优先
            release_files = [
                f for f in files if f.release_type == "release"]
            chosen = release_files[0] if release_files else files[0]

            plan.tasks.append(InstallTask(
                project_id=project_id,
                project_title=title,
                file=chosen,
                target_dir=None,        # 稍后统一填
                source=self.store.get_source(),
            ))

            # 递归处理 required 依赖
            for dep in chosen.dependencies:
                if dep.dependency_type != "required":
                    continue
                dep_id = dep.project_id

                if not dep_id:
                    self.log(f"  ⚠ {title} 的依赖缺少 project_id", "warn")
                    continue

                # 获取依赖项目的名称（用于显示）
                dep_title = dep_id
                try:
                    p = self.store.get_project(dep_id)
                    if p:
                        dep_title = p.title
                except Exception:
                    pass

                self.log(f"  → 解析依赖：{dep_title}", "info")
                _resolve(dep_id, dep_title, depth + 1)

        _resolve(root_project_id, root_title, 0)
        return plan

    # ========================================================
    #  执行安装
    # ========================================================
    def execute(self, plan: InstallPlan, target_dir,
                progress_callback=None, skip_existing=True):
        """
        按依赖顺序下载并放入 target_dir。
        progress_callback(current, total, title)
        返回 (成功数, 失败数, 跳过数)
        """
        target_dir = Path(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        total = len(plan.tasks)
        succeeded = 0
        failed = 0
        skipped = 0

        # 依赖在先，根项目在后（build_plan 已按此顺序添加）
        for i, task in enumerate(plan.tasks):
            if progress_callback:
                try:
                    progress_callback(i + 1, total, task.project_title)
                except Exception:
                    pass

            file = task.file
            dest = target_dir / file.filename

            # 已存在则跳过
            if skip_existing and dest.exists():
                self.log(f"  ↷ 跳过已存在：{file.filename}", "info")
                skipped += 1
                continue

            # 下载（支持多 URL 回退）
            urls = file.fallback_urls or [file.download_url]
            self.log(f"  ↓ 下载 {task.project_title}：{file.filename}", "info")

            try:
                result = self.store.download(
                    urls[0] if len(urls) == 1 else urls,
                    dest)
                # store.download 返回路径或抛异常
                succeeded += 1
                self.log(f"  ✔ {task.project_title} 安装完成", "ok")
            except Exception as e:
                failed += 1
                self.log(f"  ✖ {task.project_title} 失败：{e}", "error")

        return succeeded, failed, skipped

    # ========================================================
    #  一步到位：解析 + 安装
    # ========================================================
    def install_with_dependencies(self, project_id, title,
                                   target_dir,
                                   game_version=None, loader=None,
                                   progress_callback=None):
        """
        完整流程：构建计划 → 执行安装。
        返回 (成功数, 失败数, 跳过数, 计划详情)。
        """
        self.log(f"━━━ 开始安装「{title}」━━━", "info")

        plan = self.build_plan(
            project_id, title,
            game_version=game_version, loader=loader)

        if not plan.tasks:
            self.log("没有可安装的内容", "warn")
            return 0, 0, 0, plan

        self.log(
            f"共 {len(plan.tasks)} 个待安装项"
            f"（含 {len(plan.tasks) - 1} 个依赖）", "info")

        result = self.execute(
            plan, target_dir, progress_callback=progress_callback)

        return result[0], result[1], result[2], plan