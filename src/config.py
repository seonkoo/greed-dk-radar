"""配置加载：读取 config/settings.json，缺失键给默认值兜底（不崩）。

设计原则（用户工程偏好）：
- 配置化不硬编码：阈值/ETF范围/调度频率全在 settings.json，改策略不碰 src/ 代码。
- 兜底默认值：文件缺失或 JSON 损坏时，仍返回完整可用配置，绝不抛异常退出主流程。
"""
import json
import os

# 默认配置（与 settings.json 结构一致，作为兜底基准）
DEFAULTS = {
    "greed": {
        "pages": ["alla", "alla-tech", "funds-greed"],
        "opportunity_threshold": 40,
        "risk_threshold": 80,
        "etf_pages": ["funds-greed"],
        "etf_scope": "宽基+行业+主题",
    },
    "alert": {
        "channels": ["dashboard"],
        "webhook_url": None,
    },
    "schedule": {
        "cron_minutes": 30,
        "trading_hours": [9, 10, 11, 13, 14, 15],
        "timezone": "Asia/Shanghai",
    },
    "paths": {
        "output": "site/data.json",
    },
}


def _deep_merge(base, override):
    """递归合并：override 中的值覆盖 base；缺失键保留默认值。"""
    result = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load_config(path="config/settings.json"):
    """加载配置。

    返回：合并默认值后的完整配置 dict。
    容错：文件缺失 / JSON 损坏 → 打印告警并返回全部默认值，不抛异常。
    """
    cfg = json.loads(json.dumps(DEFAULTS))  # 深拷贝默认，避免被后续修改污染
    try:
        with open(path, "r", encoding="utf-8") as f:
            user = json.load(f)
        cfg = _deep_merge(cfg, user)
        print(f"[config] 已加载配置: {path}")
    except FileNotFoundError:
        print(f"[config] 未找到 {path}，使用全部默认值")
    except json.JSONDecodeError as e:
        print(f"[config] {path} JSON 解析失败({e})，使用全部默认值")
    return cfg


if __name__ == "__main__":
    import pprint

    pprint.pprint(load_config())
