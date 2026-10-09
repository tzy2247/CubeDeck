"""从整合包 mods 目录导出语言文件。

优先级：zh_cn.json > en_us.json
输出目录结构：<输出目录>/<modid>/<lang>.json
"""
import json
import zipfile
from pathlib import Path


# 语言文件在 JAR 内的路径模式
LANG_PATTERN = "assets/{modid}/lang/{locale}.json"


def scan_mods(mods_dir, log=None, progress=None):
    """
    扫描 mods 目录下的所有 .jar，提取语言文件。
    返回 {
        "mods": [
            {"name": "create-0.5.1.jar", "modid": "create",
             "zh_cn": {...} or None, "en_us": {...} or None},
            ...
        ],
        "total": N, "with_zh": M, "with_en": K
    }
    """
    if log is None:
        log = lambda m, t="info": None

    mods_dir = Path(mods_dir)
    if not mods_dir.is_dir():
        log(f"mods 目录不存在：{mods_dir}", "error")
        return {"mods": [], "total": 0, "with_zh": 0, "with_en": 0}

    jars = sorted(mods_dir.glob("*.jar"))
    if not jars:
        log("mods 目录下没有 .jar 文件", "warn")
        return {"mods": [], "total": 0, "with_zh": 0, "with_en": 0}

    results = []
    total = len(jars)

    for i, jar_path in enumerate(jars):
        if progress:
            progress(i + 1, total, jar_path.name)

        try:
            info = _scan_jar(jar_path)
            if info:
                results.append(info)
        except Exception as e:
            log(f"  跳过 {jar_path.name}：{e}", "warn")

    with_zh = sum(1 for r in results if r["zh_cn"])
    with_en = sum(1 for r in results if r["en_us"])

    log(f"扫描完成：共 {total} 个模组，"
        f"{len(results)} 个含语言文件，"
        f"{with_zh} 个有汉化，{with_en} 个有英语", "ok")

    return {
        "mods": results,
        "total": total,
        "with_zh": with_zh,
        "with_en": with_en,
    }


def _scan_jar(jar_path):
    """扫描单个 JAR，返回 {
        name, modid, zh_cn (dict or None), en_us (dict or None)
    }"""
    zh = None
    en = None
    modid = None

    with zipfile.ZipFile(jar_path, "r") as zf:
        # 找所有 assets/<modid>/lang/*.json
        lang_entries = {}
        for name in zf.namelist():
            parts = name.split("/")
            # 期望结构：assets/<modid>/lang/<locale>.json
            if (len(parts) == 4
                    and parts[0] == "assets"
                    and parts[2] == "lang"
                    and parts[3].endswith(".json")):
                current_modid = parts[1]
                locale = parts[3][:-5]  # 去掉 .json

                # 优先保留第一个 modid（通常 JAR 只有一个）
                if modid is None:
                    modid = current_modid

                if locale in ("zh_cn", "en_us"):
                    try:
                        raw = zf.read(name).decode("utf-8")
                        data = json.loads(raw)
                        if isinstance(data, dict) and data:
                            lang_entries[locale] = data
                    except Exception:
                        pass

    if modid is None or not lang_entries:
        return None

    return {
        "name": jar_path.name,
        "modid": modid,
        "zh_cn": lang_entries.get("zh_cn"),
        "en_us": lang_entries.get("en_us"),
    }


def export_languages(scan_result, output_dir, prefer_zh=True,
                     log=None, progress=None):
    """
    把扫描结果导出到目录。

    输出结构：
        <output_dir>/
            <modid>/
                zh_cn.json    (如果有汉化)
                en_us.json    (如果没有汉化，导出英语作为模板)

    prefer_zh=True 时，有汉化就只导出汉化；否则英语和汉化都导出。
    返回 {"zh": N, "en": M, "skipped": K}
    """
    if log is None:
        log = lambda m, t="info": None

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    mods = scan_result.get("mods", [])
    total = len(mods)
    zh_count = 0
    en_count = 0
    skipped = 0

    for i, m in enumerate(mods):
        if progress:
            progress(i + 1, total, m["modid"])

        modid = m["modid"]
        zh = m.get("zh_cn")
        en = m.get("en_us")

        if not zh and not en:
            skipped += 1
            continue

        mod_dir = output_dir / modid
        mod_dir.mkdir(exist_ok=True)

        wrote = False

        # 有汉化 → 导出汉化
        if zh:
            try:
                _write_json(mod_dir / "zh_cn.json", zh)
                zh_count += 1
                wrote = True
            except Exception as e:
                log(f"  写入 {modid}/zh_cn.json 失败：{e}", "warn")

        # 没有汉化 → 导出英语作为翻译模板
        # 或 prefer_zh=False 时两者都导
        if en and (not zh or not prefer_zh):
            try:
                _write_json(mod_dir / "en_us.json", en)
                en_count += 1
                wrote = True
            except Exception as e:
                log(f"  写入 {modid}/en_us.json 失败：{e}", "warn")

        if not wrote:
            skipped += 1

    log(f"导出完成：汉化 {zh_count} 个，英语 {en_count} 个，"
        f"跳过 {skipped} 个", "ok")

    return {"zh": zh_count, "en": en_count, "skipped": skipped}


def _write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def count_entries(scan_result):
    """统计待翻译条目数。"""
    total_zh = 0
    total_en = 0
    untranslated = 0  # 有英语但没汉化的模组数

    for m in scan_result.get("mods", []):
        zh = m.get("zh_cn") or {}
        en = m.get("en_us") or {}
        total_zh += len(zh)
        total_en += len(en)
        if en and not zh:
            untranslated += 1

    return {
        "total_zh": total_zh,
        "total_en": total_en,
        "untranslated_mods": untranslated,
    }