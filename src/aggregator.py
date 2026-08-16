"""
aggregator.py — 把 T2–T5 的产出组装成前端消费的 data.json 快照。

契约见 spec.md §5.2。输入为各模块已处理好的结果（main.py 负责编排取数）；
本模块只做组装 + 合规标注，不重新取数、不做任何荐股判断。

工程铁律落实：
- 配置化：阈值类全在 config；本模块不藏阈值（只有合规红线 disclaimer 为硬编码常量，
  因为它属于「不可被用户配置削弱」的合规底线）。
- 统计日志：打印快照关键计数。
- 不崩：各输入为 None / 空 时安全降级（greed 缺失 → available=false；dk 缺失 → 空）。
- 合规：disclaimer 固定文案；alerts 只描述「信号」，绝不给「买/卖某只」的下单建议（落实 §4.1）。
"""

import json
import os
import sys
from datetime import datetime

# 合规红线：固定文案，不可经 config 削弱（详见 product-requirements.md §4.1）。
DISCLAIMER = (
    "信号来自 arkvol 贪婪指数与东方财富 DK 标记，仅供参考，非投资建议；"
    "arkvol 数据仅用于机会发现，不构成买入/卖出推荐。DK 买卖点为东方财富 App 图表信号，"
    "由用户人工导出，工具仅做变换识别，不代表任何交易建议。"
)


def _now_iso():
    """生成带时区的 ISO 时间戳；优先 Asia/Shanghai，否则回退本地时区。"""
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Asia/Shanghai")
        return datetime.now(tz).isoformat()
    except Exception:
        return datetime.now().astimezone().isoformat()


def build_alerts(opportunities, risks, dk_events):
    """把机会区/风险区/DK事件 组装为 alerts[]。

    合规：只描述「信号/区位的出现」，绝不给「建议买/卖某只」的下单动作。
    返回列表，每项 {level, source, text, code, date}。
    """
    alerts = []

    # DK 变换事件：K->D 由卖转买=潜在买点信号；D->K 由买转卖=潜在卖点信号
    for e in dk_events or []:
        if e.get("type") == "K->D":
            level = "opportunity"
            text = f"{e['name']}({e['code']}) 出现 K->D 买点信号（由卖转买） @ {e['date']}"
        else:  # D->K
            level = "risk"
            text = f"{e['name']}({e['code']}) 出现 D->K 卖点信号（由买转卖） @ {e['date']}"
        alerts.append({
            "level": level,
            "source": "dk",
            "text": text,
            "code": e.get("code"),
            "date": e.get("date"),
        })

    # 贪婪机会区（低吸信号）
    for o in opportunities or []:
        alerts.append({
            "level": "info",
            "source": "greed",
            "text": f"{o.get('name')}({o.get('code')}) 贪婪分{o.get('score')} 进入低吸区（{o.get('page')}）",
            "code": o.get("code"),
            "date": None,
        })

    # 贪婪风险区（过热信号）
    for r in risks or []:
        alerts.append({
            "level": "warning",
            "source": "greed",
            "text": f"{r.get('name')}({r.get('code')}) 贪婪分{r.get('score')} 进入风险区/过热（{r.get('page')}）",
            "code": r.get("code"),
            "date": None,
        })

    return alerts


def build_snapshot(greed, opportunities, risks, dk_events, dk_state, config):
    """组装 data.json 快照 dict。

    参数：
      greed         : arkvol_client.fetch_greed() 输出（{page: GreedPage} 或 None）
      opportunities : greed_screen.screen() 的机会区列表
      risks         : greed_screen.screen() 的风险区列表
      dk_events     : dk_detector 的变换事件列表
      dk_state      : dk_detector 的当前状态 {code: {signal,date,close,name}}
      config        : load_config() 结果

    返回：严格对齐 spec §5.2 的 dict。
    """
    # —— greed 区块 ——
    greed_available = bool(greed)
    data_date = None
    market_state = None
    if greed_available:
        # 数据日期取各页 as_of 的最大者；市场状态优先 alla（全市场）页，否则首页
        dates = [gp.get("as_of") for gp in greed.values() if gp.get("as_of")]
        if dates:
            data_date = max(dates)
        market_state = greed.get("alla", {}).get("sentiment_label")
        if not market_state:
            first = next(iter(greed.values()), {})
            market_state = first.get("sentiment_label")

    # —— dk 区块 ——
    dk_latest = {}
    for code, st in (dk_state or {}).items():
        dk_latest[code] = {
            "signal": st.get("signal"),
            "date": st.get("date"),
            "close": st.get("close"),
            "name": st.get("name") or code,
        }

    # —— 来源标注 ——
    sources = []
    if greed_available:
        pages = ", ".join(greed.keys())
        sources.append(f"arkvol 贪婪指数（{pages}）")
    sources.append("东方财富 DK 买卖点（人工导出 CSV）")

    # —— alerts ——
    alerts = build_alerts(opportunities, risks, dk_events)

    snapshot = {
        "generated_at": _now_iso(),
        "greed": {
            "available": greed_available,
            "data_date": data_date,
            "market_state": market_state,
            "opportunities": opportunities or [],
            "risks": risks or [],
        },
        "dk": {
            "events": dk_events or [],
            "latest": dk_latest,
        },
        "alerts": alerts,
        "sources": sources,
        "disclaimer": DISCLAIMER,
    }

    print(f"[aggregator] 快照: greed.available={greed_available} "
          f"机会={len(opportunities or [])} 风险={len(risks or [])} "
          f"dk事件={len(dk_events or [])} dk状态code={len(dk_latest)} 告警={len(alerts)}")
    return snapshot


def write_snapshot(snapshot, out_path):
    """把快照写入 site/data.json（前端消费），自动建父目录。"""
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    print(f"[aggregator] 已写出 {out_path}")


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(__file__))
    from config import load_config

    cfg = load_config()
    # 用构造数据演示组装（不触网）
    fake_greed = {
        "funds-greed": {
            "page": "funds-greed", "as_of": "2026-08-15", "sentiment_score": 46.2,
            "sentiment_label": "中立",
            "items": [
                {"code": "515030", "name": "AI人工智能ETF", "score": 17.36, "close": 1.2, "is_gold_pit": True, "is_low_sentiment": True},
                {"code": "510300", "name": "沪深300ETF", "score": 32.0, "close": 4.1, "is_gold_pit": False, "is_low_sentiment": False},
                {"code": "510500", "name": "中证500ETF", "score": 84.0, "close": 6.3, "is_gold_pit": False, "is_low_sentiment": False},
            ],
        }
    }
    from greed_screen import screen
    opp, risk = screen(fake_greed, cfg)
    fake_events = [{"code": "600519.SH", "name": "贵州茅台", "date": "2026-08-15", "type": "K->D", "price": 1480.0, "note": "由卖转买"}]
    fake_state = {"600519.SH": {"signal": "D", "date": "2026-08-15", "close": 1480.0, "name": "贵州茅台"},
                  "300750.SZ": {"signal": "K", "date": "2026-08-15", "close": 210.0, "name": "宁德时代"}}
    snap = build_snapshot(fake_greed, opp, risk, fake_events, fake_state, cfg)
    print(json.dumps(snap, ensure_ascii=False, indent=2))
