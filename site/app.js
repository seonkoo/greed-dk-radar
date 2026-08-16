// 仪表盘渲染逻辑：读取 ./data.json 并填充各挂载点
// 纯前端、零依赖；所有数据均由后端生成器产出，本文件只负责展示。
// 定位：贪婪指数雷达（arkvol），不含 DK；DK 买卖点在 dk-tracker。
(function () {
  "use strict";

  // ---------- 工具函数 ----------
  function $(id) { return document.getElementById(id); }

  function esc(s) {
    if (s === null || s === undefined) return "";
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function el(tag, cls, html) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (html !== undefined) n.innerHTML = html;
    return n;
  }

  // 数字格式化：保留 2 位，失败回退 —
  function fmtNum(v, digits) {
    if (v === null || v === undefined || isNaN(v)) return "—";
    return Number(v).toFixed(digits === undefined ? 2 : digits);
  }

  // ---------- 告警分级 ----------
  function renderAlerts(list, container) {
    container.innerHTML = "";
    if (!list || !list.length) {
      container.appendChild(el("li", "muted", "暂无告警"));
      return;
    }
    list.forEach(function (a) {
      var lvl = a.level || "info";
      var li = el("li", "alert-" + lvl, esc(a.text || ""));
      container.appendChild(li);
    });
  }

  // ---------- 贪婪机会/风险表 ----------
  function renderGreedTable(rows, container) {
    container.innerHTML = "";
    if (!rows || !rows.length) {
      container.appendChild(el("tr", null,
        '<td colspan="5" class="muted">暂无数据</td>'));
      return;
    }
    rows.forEach(function (r) {
      var tags = "";
      if (r.gold_pit) tags += '<span class="tag tag-gold">黄金坑</span> ';
      if (r.low_sentiment) tags += '<span class="tag tag-low">低情绪</span>';
      if (!tags) tags = '<span class="muted">—</span>';
      var tr = el("tr", null,
        '<td>' + esc(r.code) + '</td>' +
        '<td>' + esc(r.name) + '</td>' +
        '<td>' + fmtNum(r.score) + '</td>' +
        '<td class="muted">' + esc(r.page || "") + '</td>' +
        '<td>' + tags + '</td>');
      container.appendChild(tr);
    });
  }

  // ---------- 来源 ----------
  function renderSources(sources, container) {
    container.innerHTML = "";
    if (!sources || !sources.length) {
      container.appendChild(el("li", "muted", "—"));
      return;
    }
    sources.forEach(function (s) {
      container.appendChild(el("li", null, "· " + esc(s)));
    });
  }

  // ---------- 顶部徽章（市场状态语义色）----------
  function renderBadge(greed) {
    var badge = $("greed-badge");
    if (!greed || greed.available !== true) {
      badge.textContent = "arkvol 不可用";
      badge.className = "badge badge-off";
      return;
    }
    var state = greed.market_state || "";
    badge.textContent = state || "已更新";
    if (state.indexOf("恐慌") >= 0) badge.className = "badge badge-panic";
    else if (state.indexOf("贪婪") >= 0) badge.className = "badge badge-greed";
    else badge.className = "badge badge-neutral";
  }

  // ---------- 主渲染 ----------
  function render(data) {
    if (!data) data = {};
    var greed = data.greed || {};

    // 生成时间
    $("gen-time").textContent = data.generated_at || "—";

    // 市场温度
    renderBadge(greed);
    $("market-state").textContent = (greed.available === true)
      ? (greed.market_state || "—") : "—";
    $("data-date").textContent = greed.data_date || "—";

    // 告警
    renderAlerts(data.alerts, $("alerts"));

    // 贪婪机会/风险
    renderGreedTable(greed.opportunities, $("opp-list"));
    renderGreedTable(greed.risks, $("risk-list"));

    // 来源 + 免责
    renderSources(data.sources, $("sources"));
    $("disclaimer").textContent = data.disclaimer || "";
  }

  // ---------- 启动 ----------
  function showError(msg) {
    var banner = $("compliance-banner");
    if (banner) {
      banner.style.background = "#fdecec";
      banner.style.borderColor = "#f5b5b5";
      banner.style.color = "#a02020";
      banner.textContent = "数据加载失败：" + msg +
        "（若以 file:// 方式打开，请在本地起 HTTP 服务或部署到 GitHub Pages）";
    }
  }

  fetch("./data.json", { cache: "no-store" })
    .then(function (resp) {
      if (!resp.ok) throw new Error("HTTP " + resp.status);
      return resp.json();
    })
    .then(render)
    .catch(function (err) {
      console.error("加载 data.json 失败:", err);
      showError(err.message || String(err));
    });
})();
