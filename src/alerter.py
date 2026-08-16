"""
alerter.py — 告警外部投递（P1，可选通道）。

职责切分（已在 T6 锁定）：
- aggregator 负责「构造」alerts[]（只描述信号，绝不下单建议）。
- 本模块只负责「投递」：把已建好的 alerts 汇总成可读文本 + 可选推送到 webhook。
  不重复构造告警，避免与 aggregator 职责重叠。

工程铁律落实：
- 配置化：通道/URL/过滤级别全部来自 config/settings.json 的 `alert` 块，缺省给默认值，不崩。
- 统计日志：打印「选中/跳过/已推送」计数。
- 不崩：webhook_url 未配置 / 网络失败 / 非 2xx → 捕获并降级为「仅本地汇总」，绝不中断主流程。
- 合规：本模块只转发信号文本，不新增任何「买/卖建议」措辞。

默认行为：webhook_url 为 null（占位未启用）→ 仅打印本地「告警汇总」，不做任何外部请求。
"""

import json
import sys
import urllib.request
import urllib.error

# 各 level 的中文展示名（仅用于汇总文本）
_LEVEL_LABEL = {
    "info": "ℹ️ 信息",
    "warning": "⚠️ 风险",
    "opportunity": "🟢 机会",
    "risk": "🔴 风险",
}


def summarize_alerts(alerts):
    """把 alerts 转成可读汇总文本列表（CI 日志可见，也供 webhook 文案）。"""
    lines = []
    for a in alerts or []:
        label = _LEVEL_LABEL.get(a.get("level"), a.get("level", "?"))
        lines.append(f"[{label}] {a.get('text', '')}")
    return lines


def _select(alerts, cfg_alert):
    """按 config 过滤要投递的告警。"""
    levels = cfg_alert.get("webhook_levels") or ["opportunity", "risk", "warning", "info"]
    only_dk = bool(cfg_alert.get("only_dk", False))
    selected = []
    skipped = 0
    for a in alerts or []:
        if a.get("level") not in levels:
            skipped += 1
            continue
        if only_dk and a.get("source") != "dk":
            skipped += 1
            continue
        selected.append(a)
    return selected, skipped


def post_webhook(payload, url, timeout=10):
    """POST JSON 到 webhook。成功(2xx)返回 True；任何失败返回 False（不抛）。"""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "greed-dk-radar/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ok = 200 <= resp.status < 300
            if not ok:
                print(f"[alerter] webhook 返回非 2xx 状态：{resp.status}")
            return ok
    except urllib.error.URLError as e:
        print(f"[alerter] webhook 请求失败（网络/不可达）：{e}，降级跳过")
        return False
    except Exception as e:
        print(f"[alerter] webhook 异常：{e}，降级跳过")
        return False


def deliver(snapshot, config):
    """汇总告警并可选推送到 webhook。返回 {selected, skipped, pushed, webhook_enabled}。

    - 始终打印本地「告警汇总」（CI 日志可见）。
    - 仅当 config.alert.channels 含 'webhook' 且 webhook_url 非空时才发起外部请求。
    - webhook 失败不影响主流程。
    """
    cfg_alert = (config or {}).get("alert", {})
    alerts = (snapshot or {}).get("alerts", [])
    channels = cfg_alert.get("channels") or []
    webhook_url = cfg_alert.get("webhook_url")

    selected, skipped = _select(alerts, cfg_alert)

    # 本地汇总（始终执行）
    print(f"\n[alerter] ===== 告警汇总（共 {len(alerts)} 条，选中投递 {len(selected)} 条，跳过 {skipped} 条）=====")
    if not selected:
        print("[alerter] （无满足条件的告警）")
    for line in summarize_alerts(selected):
        print("[alerter]  " + line)

    webhook_enabled = ("webhook" in channels) and bool(webhook_url)
    pushed = False
    if not webhook_enabled:
        if "webhook" in channels and not webhook_url:
            print("[alerter] webhook 通道已声明但未配置 webhook_url（占位），仅本地汇总，不发起外部请求")
        else:
            print("[alerter] 外部 webhook 未启用（仅仪表盘高亮），跳过投递")
        return {"selected": len(selected), "skipped": skipped, "pushed": False, "webhook_enabled": False}

    # 发起外部请求
    payload = {
        "generated_at": snapshot.get("generated_at"),
        "alerts": selected,
    }
    pushed = post_webhook(payload, webhook_url)
    print(f"[alerter] webhook 投递{'成功' if pushed else '失败'} -> {webhook_url}")
    return {"selected": len(selected), "skipped": skipped, "pushed": pushed, "webhook_enabled": True}


if __name__ == "__main__":
    sys.path.insert(0, __import__("os").path.dirname(__file__))
    from config import load_config
    # 构造演示快照
    snap = {
        "generated_at": "2026-08-16T08:58:00+08:00",
        "alerts": [
            {"level": "opportunity", "source": "dk", "text": "贵州茅台(600519.SH) 出现 K->D 买点信号（由卖转买） @ 2026-08-15", "code": "600519.SH", "date": "2026-08-15"},
            {"level": "risk", "source": "dk", "text": "宁德时代(300750.SZ) 出现 D->K 卖点信号（由买转卖） @ 2026-08-15", "code": "300750.SZ", "date": "2026-08-15"},
            {"level": "info", "source": "greed", "text": "AI人工智能ETF(515030) 贪婪分17.36 进入低吸区（funds-greed）", "code": "515030", "date": None},
            {"level": "warning", "source": "greed", "text": "中证500ETF(510500) 贪婪分84.0 进入风险区/过热（funds-greed）", "code": "510500", "date": None},
        ],
    }
    cfg = load_config()
    deliver(snap, cfg)
