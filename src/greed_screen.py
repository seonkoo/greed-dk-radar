"""
greed_screen.py — 按阈值把 arkvol 贪婪 items 分为机会区(低吸) / 风险区(过热) 并排名。

输入：arkvol_client.fetch_greed() 的标准化输出（{page: GreedPage} 或 None）。
输出：(opportunities, risks) 两个列表，按分数排名。

工程铁律落实：
- 配置化：阈值/排除关键词全部来自 config/settings.json，改策略不碰本文件。
- 统计日志：打印「原始 items → 机会 → 风险」。
- 合规：本层只做机会发现/分位提示，绝不输出「推荐买/卖某只」（见 aggregator 免责声明）。
"""

import os


def _classify_one(it, opp_th, risk_th, exclude_kw):
    """对单个 item 判定分区；返回 (bucket, note) 或 (None, None)。"""
    score = it.get("score")
    if score is None:
        return None, None
    name = it.get("name") or it.get("code") or ""
    if any(kw in name for kw in exclude_kw):
        return None, None

    gold = it.get("is_gold_pit")
    low = it.get("is_low_sentiment")

    if score <= opp_th:
        note = f"贪婪分{score} ≤ 机会阈值{opp_th}（低吸区）"
        if gold:
            note += " · 黄金坑"
        if low:
            note += " · 低情绪"
        return "opp", note
    if score >= risk_th:
        note = f"贪婪分{score} ≥ 风险阈值{risk_th}（风险区/过热）"
        return "risk", note
    return None, None


def screen(greed, config):
    """把贪婪数据分为机会区与风险区并排名。

    返回 (opportunities, risks)：
    - opportunities：按 score 升序（越低越值得低吸），含黄金坑/低情绪标记
    - risks：按 score 降序（越高越过热）
    - greed 为 None（key 失效）时返回 ([], [])
    """
    opp_th = (config or {}).get("greed", {}).get("opportunity_threshold", 40)
    risk_th = (config or {}).get("greed", {}).get("risk_threshold", 80)
    exclude_kw = (config or {}).get("greed", {}).get("exclude_keywords", []) or []

    opportunities = []
    risks = []
    total = 0

    if greed:  # None 时跳过，返回空
        for page, gp in greed.items():
            for it in gp.get("items", []) or []:
                total += 1
                bucket, note = _classify_one(it, opp_th, risk_th, exclude_kw)
                if bucket is None:
                    continue
                rec = {
                    "code": it.get("code"),
                    "name": it.get("name") or it.get("code"),
                    "score": it.get("score"),
                    "page": page,
                    "close": it.get("close"),
                    "gold_pit": bool(it.get("is_gold_pit")),
                    "low_sentiment": bool(it.get("is_low_sentiment")),
                    "note": note,
                }
                (opportunities if bucket == "opp" else risks).append(rec)

    # 排名：机会升序（越低越值得低吸），风险降序（越高越过热）
    opportunities.sort(key=lambda r: r["score"])
    risks.sort(key=lambda r: r["score"], reverse=True)

    print(f"[greed_screen] 原始items={total} → 机会={len(opportunities)} → 风险={len(risks)} "
          f"(opp≤{opp_th}, risk≥{risk_th})")
    return opportunities, risks


if __name__ == "__main__":
    import sys
    import json
    sys.path.insert(0, os.path.dirname(__file__))
    from config import load_config
    cfg = load_config()
    # 不真实拉网：用一段构造数据演示筛选
    fake = {
        "funds-greed": {
            "page": "funds-greed", "as_of": "2026-08-15", "sentiment_score": 46.2,
            "sentiment_label": "中立",
            "items": [
                {"code": "510300", "name": "沪深300ETF", "score": 32.0, "close": 4.1, "is_gold_pit": False, "is_low_sentiment": False},
                {"code": "515030", "name": "AI人工智能ETF", "score": 17.36, "close": 1.2, "is_gold_pit": True, "is_low_sentiment": True},
                {"code": "015566", "name": "某混合基金A", "score": 25.0, "close": 1.0, "is_gold_pit": False, "is_low_sentiment": False},
                {"code": "510500", "name": "中证500ETF", "score": 84.0, "close": 6.3, "is_gold_pit": False, "is_low_sentiment": False},
                {"code": "518880", "name": "黄金ETF", "score": 55.0, "close": 5.5, "is_gold_pit": False, "is_low_sentiment": False},
                {"code": "159915", "name": "创业板ETF", "score": None, "close": 2.0, "is_gold_pit": False, "is_low_sentiment": False},
            ],
        }
    }
    opp, risk = screen(fake, cfg)
    print("OPPORTUNITIES:", json.dumps(opp, ensure_ascii=False, indent=2))
    print("RISKS:", json.dumps(risk, ensure_ascii=False, indent=2))
