# 贪婪指数 + 东方财富 DK 机会雷达（greed-dk-radar）

> ⚠️ **免责声明**：本工具所有信号来自 arkvol 贪婪指数与东方财富 DK 标记，**仅供参考，非投资建议**。arkvol 数据仅用于「机会发现 / 分位提示」，**不构成任何买入 / 卖出推荐，不输出「买哪只」的结论**。据此操作风险自负。

利用多个数据源发现 A股 / ETF 机会、把握买卖点：

1. **arkvol 贪婪指数** —— 发现 ETF / 指数 / 基金样本的「低吸区 / 风险区」，含黄金坑、低情绪标记。
2. **东方财富 DK 买卖点（人工导出 CSV）** —— 通过 K↔D 变换（由卖转买 / 由买转卖）发现个股机会、把握买卖点。

---

## 一、它能做什么 / 不能做什么

| 能做 | 不能做（数据/合规边界） |
|---|---|
| 列出满足贪婪阈值的 ETF/基金（机会区 / 风险区） | arkvol **不提供全市场个股级贪婪分**（只给 ETF/指数/基金样本） |
| 呈现东方财富 DK 的 K↔D 买卖点变换事件 | 不自动荐股、不给「买/卖某只」的下单结论 |
| 跨 run 检测 DK 由卖转买(K→D)/由买转卖(D→K) | DK 买卖点**无法 API 自动取得**，需你从东方财富人工导出 CSV |

> 关键口径：贪婪「机会区 / 风险区」本质是 **ETF/指数/基金样本的贪婪分位，不是个股**。个股机会由 DK 承担。

---

## 二、本地运行

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

## 三、从东方财富导出 DK CSV（核心输入）

> 经核查，东方财富妙想 MCP、通达信 MCP 均未暴露「DK 买卖点」这类东方财富私有图表信号，**无法 API 自动取得**。最稳路径是你从东方财富人工导出，本工具负责解析与变换检测。

**导出目标**：一份 CSV，每行是一只标的在某一日的 DK 信号。建议包含以下列（列名不固定，本工具做了容错映射）：

| 你导出的列（示例） | 映射到规范字段 |
|---|---|
| `代码` / `证券代码` / `600519.SH` | `code` |
| `名称` / `证券名称` | `name` |
| `日期` / `时间` | `date` |
| `D=买点` / `K=卖点` / `买入` / `卖出` | `signal` |
| `收盘` / `收盘价` | `close` |

**常见导出路径（以东方财富 PC 端为准，App 版本路径可能不同）**：
- 个股 K 线图 → 叠加 DK 指标 → 右键 / 数据导出 → 保存为 CSV；
- 或「自选股 / 条件选股」批量导出含 D/K 标记的表格；
- 导出后**确保是 UTF-8 或 GBK 编码**，列名尽量包含上面关键词。

**放入即用**：把 CSV 保存到本仓库 `data/dk/` 目录，然后：

```bash
git add data/dk/你的导出.csv
git commit -m "dk: 更新东方财富 DK 导出"
git push          # 自动触发 Actions 重算并部署
```

> 提交 `data/dk/**` 会立即触发一次重算（「落盘即触发」）。工具会对比上一次状态，自动发现 **K→D（由卖转买）/ D→K（由买转卖）** 事件并高亮。

### CSV 容错说明（你导出不规范也不崩）
- 中文 / 英文表头都能解析；代码/信号缺任一则跳过该行；整文件缺信号列则跳过该文件。
- 日期支持 `2026-08-15` / `2026/08/15` / `20260815`；收盘价支持 `1,452.00` 千分位。
- 信号写法：`买点/买入/D` → 买点；`卖点/卖出/K` → 卖点。

---

## 四、部署到 GitHub Pages（手机可看）

1. **把本仓库推到 GitHub**（新建仓库 `greed-dk-radar`）。
2. **配置 Key**：仓库 `Settings → Secrets and variables → Actions → New repository secret`，
   名称 `ARKVOL_API_KEY`，值填 `arkvol-sk-xxxx`。
3. **启用 Pages**：仓库 `Settings → Pages → Build and deployment → Source` 选 **GitHub Actions**。
4. 之后自动运行：
   - 每个交易日 09:00–15:30（北京时）每 30 分钟跑一次；
   - 你 `git push data/dk/**` 即重算；
   - 手动：`Actions → 更新贪婪+DK雷达 → Run workflow`。

> ⚠️ arkvol Key **2026-08-26 到期**。过期后贪婪模块自动降级（仅显示 DK 部分 + 仪表盘提示），DK 功能不受影响。

---

## 五、配置项（`config/settings.json`，改策略不碰代码）

| 键 | 含义 | 默认 |
|---|---|---|
| `greed.pages` | 拉取的 arkvol 页面 | `alla` / `alla-tech` / `funds-greed` |
| `greed.opportunity_threshold` | 贪婪分 ≤ 此值进机会区（低吸） | `40` |
| `greed.risk_threshold` | 贪婪分 ≥ 此值进风险区（过热） | `80` |
| `greed.exclude_keywords` | 名称命中即剔除（过滤混合/LOF 等噪音） | `混合 / LOF / 联接 / 债券` |
| `arkvol.skill_version` | 上报给服务端的 Skill 版本号 | `0.3.1` |
| `dk.csv_folder` / `dk.state_file` | DK CSV 目录 / 状态持久化文件 | `data/dk` / `data/dk_state.json` |
| `alert.webhook_url` | 留空=仅仪表盘高亮；填了且 channels 含 `webhook` 才投递 | `null` |
| `schedule.cron_minutes` / `trading_hours` | 调度频率（仅文档参考，实际以 workflow cron 为准） | — |

---

## 六、目录结构

```
greed-dk-radar/
├── .github/workflows/update.yml   # cron + push(data/dk) + dispatch → 生成 → 部署
├── src/                           # Python 生成器
│   ├── config.py  arkvol_client.py  dk_loader.py  dk_detector.py
│   ├── greed_screen.py  aggregator.py  alerter.py  main.py
├── config/settings.json           # 用户可调配置
├── data/dk/                       # 你导出的东方财富 DK CSV（入库，push 触发重算）
├── data/dk_state.json             # 跨 run 持久化的 DK 状态（CI 自动回写）
├── site/                          # 静态仪表盘（index.html / styles.css / app.js / data.json）
└── requirements.txt               # 仅 requests
```

---

## 七、已知限制

- **arkvol Key 2026-08-26 到期**；过期后贪婪模块降级，仅 DK 可用。
- **arkvol 不提供个股级贪婪分**：机会区/风险区是 ETF/指数/基金样本，非个股。
- **DK 需人工导出**：无法 API 自动取得，依赖你定期导出 CSV。
- **DK 状态跨 run 持久化**：依赖 `data/dk_state.json` 入库；若你本地/CI 清掉了该文件，会丢失上一次状态（重新建立）。
- 部署依赖 GitHub Pages（需手动开启 Actions 源 + 配置 `ARKVOL_API_KEY` secret）。
