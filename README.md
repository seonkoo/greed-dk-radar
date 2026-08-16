# 贪婪指数雷达（greed-dk-radar）

> ⚠️ **免责声明**：本工具所有信号来自 arkvol 贪婪指数，**仅供参考，非投资建议**。arkvol 数据仅用于「机会发现 / 分位提示」，**不构成任何买入 / 卖出推荐**。据此操作风险自负。

基于 arkvol 贪婪指数，发现 **ETF / 指数 / 基金样本** 的「低吸区 / 风险区」，含黄金坑、低情绪标记。

> 关键口径：机会区 / 风险区本质是 **ETF/指数/基金样本的贪婪分位，不是个股**。
> 个股 DK 买卖点（K↔D 变换）由独立项目 **[dk-tracker](https://seonkoo.github.io/dk-tracker/)** 承担，本工具不做。

## 它能做什么 / 不能做什么

| 能做 | 不能做（数据/合规边界） |
|---|---|
| 列出满足贪婪阈值的 ETF/基金（机会区 / 风险区） | arkvol **不提供全市场个股级贪婪分**（只给 ETF/指数/基金样本） |
| 标注黄金坑、低情绪等情绪标记 | 不自动荐股、不给「买/卖某只」的下单结论 |
| 跨交易日定时刷新（GitHub Actions） | 个股 DK 买卖点请去 dk-tracker 看 |

---

## 本地运行

```bash
# 1) 准备 Python 3.11+ 与依赖
pip install -r requirements.txt

# 2) 配置 arkvol Key（本地用文件，不入库）
#    把 Key 写入 ~/.arkvol/arkvol-entry.json：
#    {"api_key": "arkvol-sk-xxxx"}
#    或运行时用环境变量： export ARKVOL_API_KEY=arkvol-sk-xxxx

# 3) 跑一次（生成 site/data.json）
python src/main.py

#    离线调试（不触网，greed 降级为空）：
python src/main.py --skip-arkvol

# 4) 预览仪表盘（必须用 http 方式打开，不能直接双击 file://）
cd site && python -m http.server 8123
#    浏览器打开 http://127.0.0.1:8123/index.html
```

---

## 部署到 GitHub Pages（手机可看）

1. **把本仓库推到 GitHub**（仓库名 `greed-dk-radar`）。
2. **配置 Key**：仓库 `Settings → Secrets and variables → Actions → New repository secret`，
   名称 `ARKVOL_API_KEY`，值填 `arkvol-sk-xxxx`。
3. **启用 Pages**：仓库 `Settings → Pages → Build and deployment → Source` 选 **GitHub Actions**。
4. 之后自动运行：
   - 每个交易日 09:00–15:30（北京时）每 30 分钟跑一次；
   - 手动：`Actions → 更新贪婪指数雷达 → Run workflow`。

> ⚠️ arkvol Key **2026-08-26 到期**。过期后贪婪模块自动降级（仪表盘提示 arkvol 不可用），其余不受影响。

---

## 配置项（`config/settings.json`，改策略不碰代码）

| 键 | 含义 | 默认 |
|---|---|---|
| `greed.pages` | 拉取的 arkvol 页面 | `alla` / `alla-tech` / `funds-greed` |
| `greed.opportunity_threshold` | 贪婪分 ≤ 此值进机会区（低吸） | `40` |
| `greed.risk_threshold` | 贪婪分 ≥ 此值进风险区（过热） | `80` |
| `greed.exclude_keywords` | 名称命中即剔除（过滤混合/LOF 等噪音） | `混合 / LOF / 联接 / 债券` |
| `arkvol.skill_version` | 上报给服务端的 Skill 版本号 | `0.3.1` |
| `alert.webhook_url` | 留空=仅仪表盘高亮；填了且 channels 含 `webhook` 才投递 | `null` |
| `schedule.cron_minutes` / `trading_hours` | 调度频率（仅文档参考，实际以 workflow cron 为准） | — |

---

## 目录结构

```
greed-dk-radar/
├── .github/workflows/update.yml   # cron + dispatch → 生成 → 部署
├── src/                           # Python 生成器
│   ├── config.py  arkvol_client.py  greed_screen.py
│   ├── aggregator.py  alerter.py  main.py
├── config/settings.json           # 用户可调配置
├── site/                          # 静态仪表盘（index.html / styles.css / app.js / data.json）
└── requirements.txt               # 仅 requests
```

---

## 已知限制

- **arkvol Key 2026-08-26 到期**；过期后贪婪模块降级（仪表盘提示 arkvol 不可用）。
- **arkvol 不提供个股级贪婪分**：机会区/风险区是 ETF/指数/基金样本，非个股。
- **部署依赖 GitHub Pages**（需手动开启 Actions 源 + 配置 `ARKVOL_API_KEY` secret）。
- 个股 DK 买卖点不在本仓库范围，请使用 dk-tracker。
