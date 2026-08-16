"""
dk_loader.py — 解析东方财富导出的 DK 买卖点 CSV，列名容错映射到规范字段。

契约见 spec.md §5.1。输出 DKRow 列表（list[dict]）供 dk_detector 消费。

工程铁律落实：
- 配置化：列别名 / 信号映射可被 config 覆盖（DEFAULT_* 仅兜底）。
- 统计日志：每个文件、整体打印「原始 N → 坏行 X → 有效 Y」。
- 不崩：坏行 / 缺列文件跳过并告警，绝不抛异常中断主流程。
"""

import csv
import os
import sys
from datetime import datetime


# 规范字段 -> 候选列名（小写）。东方财富导出列名不固定，做容错映射。
DEFAULT_COLUMN_ALIASES = {
    "code": ["code", "symbol", "证券代码", "股票代码", "标的代码", "代码", "编号"],
    "name": ["name", "证券名称", "股票名称", "标的名称", "名称", "简称"],
    "date": ["date", "time", "交易日", "信号日期", "信号时间", "日期", "时间", "日期时间"],
    "signal": ["signal", "point", "买卖", "信号", "买卖点", "dk", "dk点", "类型"],
    "close": ["close", "price", "收盘价", "收盘", "最新价", "现价", "价格", "成交价"],
}

# 信号规范化：买点(buy) -> "D"，卖点(sell) -> "K"。
# 注：东方财富 DK 体系中 D=买点、K=卖点（与 spec §5.1 / settings.json signal_map 一致）。
BUY_TOKENS = {"d", "买点", "买入", "buy", "b", "金叉", "多头"}
SELL_TOKENS = {"k", "卖点", "卖出", "sell", "s", "死叉", "空头"}


def _canon_signal(raw, signal_map=None):
    """把各种写法的买卖点归一为 'D'(买) / 'K'(卖) / None(无法识别)。"""
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if not s:
        return None
    if s in BUY_TOKENS:
        return "D"
    if s in SELL_TOKENS:
        return "K"
    # 兼容 config signal_map 的标签（如 {"D":"买点","K":"卖点"}）
    if isinstance(signal_map, dict):
        for canon, label in signal_map.items():
            if str(label).strip().lower() == s:
                return str(canon).upper()
    return None


def _parse_date(raw):
    """把常见日期写法归一成 ISO 'YYYY-MM-DD'；无法解析返回 None。"""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    # 去分隔符歧义 + 去掉时间部分
    s = s.replace("/", "-").replace(".", "-")
    s_date = s.split(" ")[0].split("T")[0]
    # 兼容 20260815 紧凑写法
    if s_date.isdigit() and len(s_date) == 8:
        s_date = f"{s_date[0:4]}-{s_date[4:6]}-{s_date[6:8]}"
    try:
        return datetime.strptime(s_date, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        return None


def _parse_close(raw):
    """收盘价转 float；带千分位/百分号容错；失败返回 None。"""
    if raw is None:
        return None
    s = str(raw).strip().replace(",", "").replace("%", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _read_csv_text(path):
    """编码容错读取：utf-8-sig -> gbk -> utf-8(容错替换)。"""
    for enc in ("utf-8-sig", "gbk", "utf-8"):
        try:
            with open(path, "r", encoding=enc, newline="") as f:
                return f.read()
        except (UnicodeDecodeError, LookupError):
            continue
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
        return f.read()


def _match_columns(headers, aliases):
    """从表头匹配规范字段 -> 实际列名。"""
    lowered = {h.strip().lower(): h for h in (headers or []) if h and h.strip()}
    mapping = {}
    for canon, candidates in aliases.items():
        for cand in candidates:
            if cand in lowered:
                mapping[canon] = lowered[cand]
                break
    return mapping


def load_dk(folder, config=None):
    """遍历 folder 下所有 *.csv，解析为 DKRow 列表。

    返回 list[dict]，每项: {code, name, date, signal, close, source_file}
    - 缺 code/signal 列的文件整体跳过并告警
    - 单行缺 code 或无法识别 signal -> 计为坏行跳过
    - 目录不存在 / 无 CSV -> 返回 []（不崩）
    """
    # 列别名可被 config 覆盖（合并而非替换）
    aliases = DEFAULT_COLUMN_ALIASES
    if isinstance(config, dict):
        user_aliases = config.get("dk", {}).get("column_aliases")
        if isinstance(user_aliases, dict):
            merged = {k: list(v) for k, v in DEFAULT_COLUMN_ALIASES.items()}
            for k, v in user_aliases.items():
                merged[k] = list(v) + merged.get(k, [])
            aliases = merged
        signal_map = config.get("dk", {}).get("signal_map")
    else:
        signal_map = None

    folder = os.path.expanduser(folder)
    if not os.path.isdir(folder):
        print(f"[dk_loader] 目录不存在或不是目录: {folder} -> 返回空列表")
        return []

    csv_files = sorted(f for f in os.listdir(folder) if f.lower().endswith(".csv"))
    if not csv_files:
        print(f"[dk_loader] 未找到 CSV 文件: {folder} -> 返回空列表")
        return []

    total_raw = 0
    bad_rows = 0
    valid = 0
    skipped_files = 0
    rows = []

    for fname in csv_files:
        path = os.path.join(folder, fname)
        try:
            text = _read_csv_text(path)
            reader = csv.DictReader(text.splitlines())
            headers = reader.fieldnames or []
        except Exception as e:
            print(f"[dk_loader] 读取失败，跳过文件: {fname} ({e})")
            skipped_files += 1
            continue

        colmap = _match_columns(headers, aliases)
        if "code" not in colmap or "signal" not in colmap:
            print(f"[dk_loader] 缺少必需列(code/signal)，跳过文件: {fname} (找到列: {list(colmap.keys())})")
            skipped_files += 1
            continue

        file_raw = 0
        file_bad = 0
        file_valid = 0
        for raw in reader:
            file_raw += 1
            total_raw += 1
            code = (raw.get(colmap["code"]) or "").strip()
            sig = _canon_signal(raw.get(colmap["signal"]), None) if signal_map is None \
                else _canon_signal(raw.get(colmap["signal"]), signal_map)
            name = (raw.get(colmap["name"]) or "").strip() if "name" in colmap else ""
            date_iso = _parse_date(raw.get(colmap["date"])) if "date" in colmap else None
            close = _parse_close(raw.get(colmap["close"])) if "close" in colmap else None

            if not code or not sig:
                file_bad += 1
                bad_rows += 1
                continue
            rows.append({
                "code": code,
                "name": name or code,
                "date": date_iso or "",
                "signal": sig,
                "close": close,
                "source_file": fname,
            })
            file_valid += 1
            valid += 1
        print(f"[dk_loader] 文件 {fname}: 原始={file_raw} → 坏行={file_bad} → 有效={file_valid}")

    print(f"[dk_loader] 汇总 原始行={total_raw} → 坏行={bad_rows} → 有效={valid} (文件数={len(csv_files)}, 跳过文件={skipped_files})")
    return rows


if __name__ == "__main__":
    import json

    sys.path.insert(0, os.path.dirname(__file__))  # src/
    try:
        from config import load_config
        cfg = load_config()
    except Exception:
        cfg = None

    folder = sys.argv[1] if len(sys.argv) > 1 else (cfg or {}).get("dk", {}).get("csv_folder", "data/dk")
    result = load_dk(folder, cfg)
    print(json.dumps(result, ensure_ascii=False, indent=2))
