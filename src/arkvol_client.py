"""arkvol 贪婪指数客户端：直接 request arkvol HTTP API + 标准化 + key 失效优雅降级。

设计原则（用户工程偏好）：
- 单一引擎：直接调用 arkvol REST API（https://arkvol.com），不依赖本地 skill 脚本，
  本地与 GitHub Actions CI 行为完全一致（CI runner 上无 .workbuddy/skills）。
- 先稳后快：key 失效 / 网络失败 / 升级要求(426) / 解析错误 全部捕获，单页失败跳过、
  整体失败返回 None，绝不中断主流程。
- 关键步骤加统计日志：每页成功/失败条数打印。
- 合规：本层只取数 + 标准化，不做任何荐股判断（免责声明在 aggregator 落地）。

数据源：arkvol.com（接口契约来自 arkvol-greed-index skill 的 client.py / pages.py）。
- items 为 ETF/指数样本（非全市场个股）。
- greed 字段为 0-1 比例，标准化为 0-100；部分页面含 is_gold_pit / is_low_sentiment 标记。

鉴权：请求头 X-API-Key + X-Arkvol-Skill-Version；本客户端只取数，不生成任何建议。
"""
import json
import os

import requests

# 页面 -> arkvol API 端点（与 arkvol-greed-index skill pages.py 对齐）
PAGE_ENDPOINTS = {
    "alla": "/api/data/alla",
    "alla-tech": "/api/data/alla-tech",
    "funds-greed": "/api/data/funds-greed",
}

DEFAULT_BASE_URL = "https://arkvol.com"
DEFAULT_SKILL_VERSION = "0.3.1"


def _resolve_api_key(explicit=None):
    """三级解析 API Key：显式参数 -> 环境变量 ARKVOL_API_KEY -> 本地 key 文件。"""
    if explicit and str(explicit).strip():
        return str(explicit).strip()
    env_key = os.environ.get("ARKVOL_API_KEY")
    if env_key and env_key.strip():
        return env_key.strip()
    # 本地兜底：~/.arkvol/arkvol-entry.json（不入库）
    p = os.path.expanduser("~/.arkvol/arkvol-entry.json")
    if os.path.isfile(p):
        try:
            d = json.load(open(p, encoding="utf-8"))
            k = d.get("api_key")
            if k and str(k).strip():
                return str(k).strip()
        except Exception:
            pass
    return None


def _norm_score(raw):
    """greed 字段为 0-1 比例时 ×100；已是 0-100 则不动。无法解析返回 None。"""
    if raw is None:
        return None
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    if v <= 1.0:
        v = v * 100.0
    return round(v, 2)


def _first(*vals):
    for v in vals:
        if v not in (None, "", {}):
            return v
    return None


def _normalize_item(item):
    """多别名容错映射 items 字段（不同页面字段名不同：funds-greed/alla/alla-tech）。"""
    return {
        "code": _first(item.get("fund_code"), item.get("code"), item.get("symbol"), item.get("stock_code")),
        "name": _first(item.get("fund_name"), item.get("etf_name"), item.get("name"),
                     item.get("index_name"), item.get("security_name")),
        "score": _norm_score(_first(item.get("greed"), item.get("greed_index"),
                                       item.get("greed_score"), item.get("score"))),
        "close": _first(item.get("close"), item.get("close_price")),
        "date": _first(item.get("date"), item.get("trade_date")),
        "is_gold_pit": bool(item.get("is_gold_pit", False)),
        "is_low_sentiment": bool(item.get("is_low_sentiment", False)),
    }


def _fetch_one(page, api_key=None, timeout=60, base_url=DEFAULT_BASE_URL,
               skill_version=DEFAULT_SKILL_VERSION):
    """拉取单个 arkvol 页面。成功返回 GreedPage dict；任何失败返回 None（降级）。"""
    key = _resolve_api_key(api_key)
    if not key:
        print(f"[arkvol] 未配置 API Key，跳过页面 {page}")
        return None
    endpoint = PAGE_ENDPOINTS.get(page)
    if not endpoint:
        print(f"[arkvol] 未知页面 {page}（可选：{', '.join(PAGE_ENDPOINTS)}），跳过")
        return None

    url = f"{base_url.rstrip('/')}{endpoint}?view=summary"
    headers = {
        "X-API-Key": key,
        "X-Arkvol-Skill-Version": skill_version,
        "Accept": "application/json",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
    except requests.RequestException as e:
        print(f"[arkvol] 页面 {page} 请求异常：{e}，降级跳过")
        return None

    if resp.status_code != 200:
        # 401=key无效 402/403=禁用 426=需升级；均降级不抛异常
        print(f"[arkvol] 页面 {page} HTTP {resp.status_code}，降级跳过")
        return None

    try:
        payload = resp.json()
    except ValueError:
        print(f"[arkvol] 页面 {page} 响应非 JSON，降级跳过")
        return None

    data = payload.get("data")
    if not isinstance(data, dict):
        print(f"[arkvol] 页面 {page} 缺少 data 对象，降级跳过")
        return None
    # 升级要求：服务端阻断旧版客户端
    skill_update = data.get("skill_update") or {}
    if skill_update.get("update_required"):
        print(f"[arkvol] 页面 {page} 需要升级 Skill，请更新 arkvol-skill 后重试，降级跳过")
        return None

    items_raw = data.get("items") or []
    items = [_normalize_item(it) for it in items_raw if isinstance(it, dict)]
    page_obj = {
        "page": page,
        "as_of": data.get("as_of"),
        "sentiment_score": data.get("sentiment_score"),
        "sentiment_label": data.get("sentiment_label"),
        "items": items,
    }
    print(f"[arkvol] 页面 {page}: 成功 {len(items)} 条 (sentiment={page_obj['sentiment_score']})")
    return page_obj


def fetch_greed(pages, api_key=None, timeout=60, base_url=DEFAULT_BASE_URL,
                skill_version=DEFAULT_SKILL_VERSION):
    """拉取多个 arkvol 页面。

    返回：{page: GreedPage}（仅含成功的页面）；全部失败返回 None（贪婪模块降级）。
    """
    results = {}
    for page in pages:
        gp = _fetch_one(page, api_key=api_key, timeout=timeout,
                        base_url=base_url, skill_version=skill_version)
        if gp:
            results[page] = gp
    if not results:
        print("[arkvol] 所有页面获取失败（key 失效/网络/升级），贪婪模块降级")
        return None
    print(f"[arkvol] 共获取 {len(results)}/{len(pages)} 个页面")
    return results


if __name__ == "__main__":
    out = fetch_greed(["alla", "alla-tech", "funds-greed"])
    if out:
        for page, gp in out.items():
            print(f"\n=== {page} (as_of={gp['as_of']}, score={gp['sentiment_score']}) ===")
            for it in gp["items"][:3]:
                print(" ", it)
    else:
        print("贪婪模块降级：无可用数据")
