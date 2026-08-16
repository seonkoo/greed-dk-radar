"""
aggregator.py — 把筛选结果组装成前端消费的 data.json 快照。

契约：输入为各模块已处理好的结果（main.py 负责编排取数）；
本模块只做组装 + 合规标注，不重新取数、不做任何荐股判断。

工程铁律落实：
- 配置化：阈值类全在 config；本模块不藏阈值（只有合规红线 disclaimer 为硬编码常量，
  因为它属于「不可被用户配置削弱」的合规底线）。
- 统计日志：打印快照关键计数。
- 不崩：greed 缺失 → available=false 安全降级。
- 合规：disclaimer 固定文案；alerts 只描述「信号」，绝不给「买/卖某只」的下单建议。

定位：本工具为「贪婪指数雷达」——仅基于 arkvol 贪婪指数发现 ETF/指数/基金样本的机会/
风险区；个股 DK 买卖点由独立的 dk-tracker 项目承担，故本模块不含 DK 逻辑。
"""

import json
import os
import sys
from datetime import datetime

# 合规红线：固定文案，不可经 config 削弱。
DISCLAIMER = (
    "信号来自 arkvol 贪婪指数，仅供参考，非投资建议；"
    "arkvol 数据仅用于机会发现（ETF/指数/基金样本分位），不构成买入/卖出推荐。"
)


def _now_iso():
    """生成带时区的 ISO 时间戳；优先 Asia/Shanghai，否则回退本地时区。"""
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Asia/Shanghai")
        return datetime.now(tz).isoformat()
    except Exception:
        return datetime.now().astimezone().isoformat()


def build_alerts(opportunities, risks):
    """把机会区/风险区组装为 alerts[]。

    合规：只描述「信号/区位的出现」，绝不给「建议买/卖某只」的下单动作。
    返回列表，每项 {level, source, text, code, date}。
    """
    alerts = []

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


def build_snapshot(greed, opportunities, risks, config):
    """组装 data.json 快照 dict。

    参数：
      greed         : arkvol_client.fetch_greed() 输出（{page: GreedPage} 或 None）
      opportunities : greed_screen.screen() 的机会区列表
      risks         : greed_screen.screen() 的风险区列表
      config        : load_config() 结果

    返回：严格对齐前端消费契约的 dict。
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

    # —— 来源标注 ——
    sources = []
    if greed_available:
        pages = ", ".join(greed.keys())
        sources.append(f"arkvol 贪婪指数（{pages}）")

    # —— alerts ——
    alerts = build_alerts(opportunities, risks)

    snapshot = {
        "generated_at": _now_iso(),
        "greed": {
            "available": greed_available,
            "data_date": data_date,
            "market_state": market_state,
            "opportunities": opportunities or [],
            "risks": risks or [],
        },
        "alerts": alerts,
        "sources": sources,
        "disclaimer": DISCLAIMER,
    }

    print(f"[aggregator] 快照: greed.available={greed_available} "
          f"机会={len(opportunities or [])} 风险={len(risks or [])} 告警={len(alerts)}")
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
    snap = build_snapshot(fake_greed, opp, risk, cfg)
    print(json.dumps(snap, ensure_ascii=False, indent=2))
