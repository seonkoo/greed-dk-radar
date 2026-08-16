"""main.py — 总装编排：取数 → 加载 → 检测 → 筛选 → 聚合 → 写盘 → 告警。

单命令 `python src/main.py` 跑通端到端。原则（用户工程偏好）：
- 配置化：路径/阈值/通道全在 config；本文件只做编排，不藏业务阈值。
- 统计日志：每个环节打印计数，便于调参（原始 N → 有效 Y 之类）。
- 不崩：任一环节失败都降级（greed 取数失败→None；dk 空→无事件；其余模块已内置兜底），
  整体永远产出一份结构完整的 data.json。
- 合规：所有「建议」措辞由 aggregator/alerter 把关，本文件不新增任何荐股表述。
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))

from config import load_config
from arkvol_client import fetch_greed
from dk_loader import load_dk
from dk_detector import detect_and_persist
from greed_screen import screen
from aggregator import build_snapshot, write_snapshot
from alerter import deliver


def _now():
    """带时区的时间字符串（用于启动日志打印）。"""
    try:
        from zoneinfo import ZoneInfo
        from datetime import datetime
        return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
    except Exception:
        from datetime import datetime
        return datetime.now().astimezone().isoformat(timespec="seconds")


def main(config_path="config/settings.json", skip_arkvol=False, api_key=None):
    t0 = time.time()
    print("=" * 64)
    print(f"[main] 启动 greed-dk-radar @ {_now()}")
    print("=" * 64)

    cfg = load_config(config_path)
    out_path = cfg.get("paths", {}).get("output", "site/data.json")
    dk_folder = cfg["dk"]["csv_folder"]
    state_file = cfg["dk"]["state_file"]
    pages = cfg["greed"]["pages"]
    arkvol_cfg = cfg.get("arkvol", {})
    skill_version = arkvol_cfg.get("skill_version", "0.3.1")
    api_key = os.environ.get("ARKVOL_API_KEY") or api_key

    # 1) 取数：arkvol 贪婪指数（内部已逐页降级；key 失效整体返回 None）
    print("\n--- [1/6] 取数：arkvol 贪婪指数 ---")
    if skip_arkvol:
        print("（--skip-arkvol 已启用，greed 降级为空，不触网）")
        greed = None
    else:
        greed = fetch_greed(pages, api_key=api_key, skill_version=skill_version)

    # 2) 加载：东方财富 DK CSV（列名容错；空目录/缺文件返回 []）
    print("\n--- [2/6] 加载：东方财富 DK CSV ---")
    rows = load_dk(dk_folder)

    # 3) 检测：DK 跨 run K↔D 变换（旧日期不回退；未出现 code 保留状态）
    print("\n--- [3/6] 检测：DK K↔D 变换 ---")
    events, dk_state = detect_and_persist(rows, state_file)

    # 4) 筛选：贪婪机会区/风险区（阈值来自 config，改配置即生效）
    print("\n--- [4/6] 筛选：贪婪机会区/风险区 ---")
    opportunities, risks = screen(greed, cfg)

    # 5) 聚合：组装 data.json 快照（含来源标注 + 免责声明合规红线）
    print("\n--- [5/6] 聚合：data.json 快照 ---")
    snapshot = build_snapshot(greed, opportunities, risks, events, dk_state, cfg)
    write_snapshot(snapshot, out_path)

    # 6) 告警：本地汇总 + 按需 webhook 投递（aggregator 已构造 alerts，本步只投递）
    print("\n--- [6/6] 告警：投递 ---")
    result = deliver(snapshot, cfg)

    dt = time.time() - t0
    print("\n" + "=" * 64)
    print(f"[main] 完成 耗时={dt:.1f}s | 输出={out_path}")
    print(f"[main] greed.available={snapshot['greed']['available']} "
          f"机会={len(opportunities)} 风险={len(risks)} "
          f"dk事件={len(events)} dk状态={len(dk_state)} 告警={len(snapshot['alerts'])}")
    print(f"[main] webhook_enabled={result['webhook_enabled']} pushed={result['pushed']}")
    print("=" * 64)
    return snapshot


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="greed-dk-radar 总装")
    ap.add_argument("--config", default="config/settings.json", help="配置文件路径")
    ap.add_argument("--skip-arkvol", action="store_true",
                    help="跳过取数，greed 降级为空（离线调试用）")
    ap.add_argument("--api-key", default=None, help="临时覆盖 arkvol API Key（优先于环境变量/本地文件）")
    args = ap.parse_args()
    main(config_path=args.config, skip_arkvol=args.skip_arkvol, api_key=args.api_key)
