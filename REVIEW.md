# 阶段5 自测评审报告 — greed-dk-radar

> 评审时间：2026-08-16 ｜ 评审范围：T1–T11 全部交付物 ｜ 结论：**可交付，存在若干已知限制（非缺陷）需你知晓**。

## 一、端到端复核结论

| 核查项 | 结果 | 证据 |
|---|---|---|
| 贪婪取数（真实 arkvol API） | ✅ | 直连 `/api/data/{alla,alla-tech,funds-greed}`，本回合拉到 15 条机会区、0 风险 |
| Key 失效降级 | ✅ | `--skip-arkvol` / 错 key → `greed.available=false`、结构完整、不崩 |
| DK CSV 容错加载 | ✅ | 中文/英文表头、日期归一、千分位、坏行跳过、整文件缺列跳过 |
| DK 跨 run 变换检测 | ✅（构造数据） | K→D / D→K 正确、旧日期不回退、未出现 code 保留状态 |
| 贪婪筛选（阈值/排除） | ✅ | `≤40 机会 / ≥80 风险`；`exclude_keywords` 净化 54→15 条 |
| 聚合 + 合规 | ✅ | `data.json` 对齐 spec §5.2；`DISCLAIMER` 硬编码（含「非投资建议」）；arkvol 仅机会发现 |
| 告警分级 + webhook 占位 | ✅ | 分级 class 正确；webhook 真实 POST 收包通过；死 URL 降级 |
| 编排主控 | ✅ | 单命令跑通；`--skip-arkvol` 离线；统计日志 |
| 仪表盘渲染 | ✅ | DOM 桩 + fetch 桩端到端断言全过；红=机会/买点、绿=风险/卖点 |
| CI 结构 | ✅ | YAML 合法；cron+push+dispatch；并发锁；permissions 三项；build→deploy；DK 状态回写 |
| 双端可用 | ✅ | 本地 `http.server` 预览；Pages 部署链路就位 |
| 关键改造：arkvol 直连 | ✅ | 去掉对 skill 脚本的子进程依赖，CI runner 无 `.workbuddy/skills` 也能跑 |

## 二、存在的问题 / 已知限制（按优先级）

### P0 — 必须在用之前知晓
1. **arkvol Key 2026-08-26 到期（距今约 10 天）**。过期后贪婪模块自动降级（仅 DK 可用）。如需长期用，须续 key 并改 `config/settings.json` 的 `arkvol.skill_version`（若服务端要求更高版本）。
2. **DK 真实链路尚未端到端验证**。`data/dk/` 目前为空（无你真实的东方财富导出 CSV），DK 事件流、状态持久化、变换检测**只在构造数据上验证过逻辑**，未在真实导出上跑过。你给一份真实 CSV 放入 `data/dk/` 重跑即可验证。

### P1 — 功能边界（已设计内处理，非缺陷）
3. **arkvol 不提供全市场个股级贪婪分**。机会区/风险区本质是 **ETF/指数/基金样本**的贪婪分位，**不是个股**。个股机会只能靠 DK（已在仪表盘标注「ETF/指数/基金样本，非个股」）。
4. **DK 买卖点无法 API 自动取得**，依赖你定期从东方财富人工导出 CSV（已文档化导出契约与容错规则）。
5. **部署非开箱即用**：需手动两步——仓库 `Settings→Pages→Source` 选 `GitHub Actions`；`Settings→Secrets` 配 `ARKVOL_API_KEY`。

### P2 — 可优化项（配置或后续迭代）
6. **噪音过滤仍有少量残留**：`exclude_keywords` 已过滤 混合/LOF/联接/债券，但个别「股票型/发起式C」指数基金（如「中欧高端装备股票发起C」）会残留。可在 config 继续加关键词，或接受。
7. **DK「新买点 D」不单独告警**：T4 仅发 K↔D 变换事件，首次出现的新 D 买点不进告警（spec 范围如此）。若想让「新纳入的买点」也高亮，可后续加开关。
8. **cron 窗口略宽**：`0,30 1-7 * * 1-5` = 北京 09:00–15:30，含开盘前 09:00、收盘后 15:30 各一次多余运行（无害）。
9. **无固化单元测试**：各模块均有 ad-hoc 断言验证但没沉淀为 `tests/` pytest 套件；回归保障靠人工。
10. **webhook 真实通道未验证**：T7 用本地 HTTP 桩验证了真实 POST 收包，但企业微信/飞书等真实 webhook 的 payload 格式未约定（默认 `webhook_url=null` 未启用）。

### P3 — 架构备注
11. **单一引擎**：arkvol 取数从「子进程调 query.py」改为「直连 HTTP API」，本地/CI 行为一致，无双份逻辑（符合你「单一引擎不双镜像」原则）。
12. **DK 状态跨 run 持久化依赖 `data/dk_state.json` 入库 + CI 回写步骤**；若清掉该文件会丢失上次状态（重新建立，不影响结构）。

## 三、给出去之前你该做的 3 件事
1. 把 `greed-dk-radar/` 推到 GitHub 新仓库。
2. 配 `ARKVOL_API_KEY` secret + 开启 Pages（GitHub Actions 源）。
3. 导出一份东方财富 DK CSV 放进 `data/dk/` 推上去，验证 DK 事件流真正跑起来。

> 以上 P0/P1 为已知边界，非实现缺陷；P2 为后续可选项。工具在 key 有效期内、配合人工 DK 导出，可正常服务于「发现 ETF 机会 + 把握 DK 买卖点」。
