"""
dk_detector.py — 基于 dk_state.json 跨 run 比对，检测 DK 买卖点变换。

契约见 spec.md §5.2。输入为 dk_loader 的 DKRow 列表；输出变换事件 + 新状态。

工程铁律落实：
- 配置化：本模块无阈值，纯状态机；日期/信号语义来自上游（D=买点/K=卖点）。
- 统计日志：打印「原始 code 数 → 状态 code 数 → 事件数」。
- 不崩：state 文件缺失/损坏 → 视为空状态；IO 异常捕获。
- 不回退：当前日期早于已知日期则保留旧状态，避免旧导出误触发变换。
"""

import json
import os


def _to_stored(r):
    """把一行 DKRow 收敛为持久化状态记录。"""
    return {
        "signal": r.get("signal"),
        "date": r.get("date") or "",
        "close": r.get("close"),
        "name": r.get("name") or r.get("code"),
    }


def _latest_per_code(rows):
    """每个 code 取其最新日期的信号行；日期空视为最旧。"""
    latest = {}
    for r in rows:
        code = r.get("code")
        if not code:
            continue
        cur_date = r.get("date") or ""
        if code not in latest:
            latest[code] = r
        else:
            prev_date = latest[code].get("date") or ""
            # ISO 'YYYY-MM-DD' 字符串可字典序比较；空日期视为最旧
            if (cur_date and (not prev_date or cur_date >= prev_date)) or (not cur_date and not prev_date):
                latest[code] = r
    return latest


def _transition_note(prev_sig, cur_sig):
    if prev_sig == "K" and cur_sig == "D":
        return "由卖转买"
    if prev_sig == "D" and cur_sig == "K":
        return "由买转卖"
    return ""


def detect_transitions(rows, prev_state):
    """纯函数：比对当前 rows 与上一状态，产出 (events, new_state)。

    - 每个 code 取最新日期信号
    - 仅 D<->K 互变记为事件；同信号不报；缺失/未知信号不报
    - 不回退：当前日期 < 已知日期则保留旧状态
    - 未出现在本次 rows 的 code 保留上一状态（不丢持仓）
    """
    current = _latest_per_code(rows)
    events = []
    new_state = dict(prev_state)  # 保留未在本次导出中出现的 code

    for code, r in current.items():
        sig = r.get("signal")
        date = r.get("date") or ""
        prev = prev_state.get(code)

        if prev is None:
            # 新纳入：仅记录状态，不发变换事件（变换需有上一状态）
            new_state[code] = _to_stored(r)
            continue

        prev_sig = prev.get("signal")
        prev_date = prev.get("date") or ""

        # 不回退：当前日期早于已知日期，保留旧状态
        if date and prev_date and date < prev_date:
            continue

        if sig != prev_sig and sig in ("D", "K") and prev_sig in ("D", "K"):
            events.append({
                "code": code,
                "name": r.get("name") or code,
                "date": date,
                "type": f"{prev_sig}->{sig}",
                "price": r.get("close"),
                "note": _transition_note(prev_sig, sig),
            })
        new_state[code] = _to_stored(r)

    return events, new_state


def load_state(state_file):
    """读 dk_state.json；缺失/损坏 → 返回 {}。"""
    try:
        with open(state_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return {}


def save_state(state_file, state):
    """写 dk_state.json；自动建父目录。"""
    os.makedirs(os.path.dirname(os.path.abspath(state_file)), exist_ok=True)
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def detect_and_persist(rows, state_file):
    """便捷封装：load → detect → save，返回 (events, new_state) 并打印统计。"""
    prev = load_state(state_file)
    events, new_state = detect_transitions(rows, prev)
    save_state(state_file, new_state)
    print(f"[dk_detector] 原始code={len({r['code'] for r in rows}) if rows else 0} → "
          f"状态code={len(new_state)} → 事件={len(events)} (state_file={state_file})")
    for e in events:
        print(f"[dk_detector] 事件 {e['code']} {e['name']} {e['type']} {e['note']} @ {e['date']} price={e['price']}")
    return events, new_state


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from dk_loader import load_dk
    try:
        from config import load_config
        cfg = load_config()
    except Exception:
        cfg = None
    folder = sys.argv[1] if len(sys.argv) > 1 else (cfg or {}).get("dk", {}).get("csv_folder", "data/dk")
    state_file = (cfg or {}).get("dk", {}).get("state_file", "data/dk_state.json")
    rows = load_dk(folder, cfg)
    events, new_state = detect_and_persist(rows, state_file)
    print(json.dumps({"events": events, "state_keys": list(new_state.keys())}, ensure_ascii=False, indent=2))
