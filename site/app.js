/* 物理AI实验场 · 榜单站前端（内部工单）。只渲染 data/leaderboard.json（由 tools/build_site.py 自 episodes/ CSV 生成），不含任何手填数字。 */
(async function () {
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const state = { lang: "zh", ui: {}, data: null, build: null, edition: null };

  function pickLang() {
    const q = new URLSearchParams(location.search).get("lang");
    if (q === "zh" || q === "en") return q;
    try { const s = localStorage.getItem("pg.lang"); if (s === "zh" || s === "en") return s; } catch (e) { /* 私密窗口等 */ }
    return /^zh/i.test(navigator.language || "") ? "zh" : "en";
  }
  const t = (k) => (state.ui[k] && state.ui[k][state.lang]) || k;
  const isNum = (v) => v !== null && v !== undefined && v !== "" && !Number.isNaN(Number(v));
  const fmt = {
    num: (v, d = 2) => (isNum(v) ? Number(v).toFixed(d) : null),
    pct: (v) => (isNum(v) ? Math.round(Number(v) * 100) + "%" : null),
    usd: (v) => (isNum(v) ? "$" + Number(v).toFixed(Number(v) < 0.1 && Number(v) > 0 ? 3 : 2) : null),
    sec: (v) => (isNum(v) ? Number(v).toFixed(2) : null),
    int: (v) => (isNum(v) ? String(Math.round(Number(v))) : null),
  };
  const na = () => `<span class="na">${t("na")}</span>`;
  const fmtCny = (v) => (isNum(v) ? "¥" + Number(v).toFixed(Number(v) < 1 && Number(v) > 0 ? 3 : 2) : null);
  const zeroSuccess = (x) => !!x && isNum(x.success_rate) && Number(x.success_rate) === 0 && !isNum(x.usd_per_success);
  const money = (x) => {
    if (!x) return t("na");
    if (zeroSuccess(x)) return `<abbr class="na help" title="${esc(t("cost.zero.help"))}">${t("na")}¹</abbr>`;   // 成功数 0 → 每次成功成本无定义
    return `${cell(fmtCny(x.cny_per_success))} / ${cell(fmt.usd(x.usd_per_success))}`;
  };
  const cell = (v) => (v === null ? na() : esc(v));
  const pair = (a, b, f) => `<span class="pair"><b>${a == null ? t("na") : cell(f(a))}</b> / <b>${b == null ? t("na") : cell(f(b))}</b></span>`;
  const shortSha = (s) => (s ? `<code title="${esc(s)}">${esc(String(s).slice(0, 12))}…</code>` : na());
  const blob = (p) => (state.data.repo_url ? `${state.data.repo_url}/blob/main/${p}` : p);
  const link = (p, label) => `<a href="${esc(blob(p))}" target="_blank" rel="noopener">${esc(label || p)}</a>`;

  function applyI18n() {
    document.documentElement.lang = state.lang === "zh" ? "zh-CN" : "en";
    document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
    document.querySelectorAll(".lang button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.lang === state.lang)));
  }

  function renderSelect() {
    const sel = $("#edition");
    sel.innerHTML = state.data.editions.map((e) => `<option value="${esc(e.id)}"${e.id === state.edition.id ? " selected" : ""}>${esc(e.id)} · ${esc(t("status." + e.status))}</option>`).join("");
  }

  function kpi(label, help, value, unit, sub, subClass) {
    return `<div class="kpi"><div class="k">${esc(label)}${help ? ` <abbr class="help" title="${esc(help)}">?</abbr>` : ""}</div>
      <div class="v">${value === null ? na() : esc(value)}${value !== null && unit ? `<small>${esc(unit)}</small>` : ""}</div>
      ${sub ? `<div class="s ${subClass || ""}">${esc(sub)}</div>` : ""}</div>`;
  }

  function renderHero(e) {
    $("#ed-title").textContent = e.title[state.lang] || e.title.zh || e.id;
    const badge = $("#ed-status"); badge.textContent = t("status." + e.status); badge.className = "badge " + e.status;
    $("#ed-notes").textContent = e.notes[state.lang] || e.notes.zh || "";
    const f = e.fidelity;
    const hours = e.hours_to_publish;
    let hSub = "", hCls = "";
    if (isNum(hours)) { if (hours > 72) { hSub = t("over72"); hCls = "bad"; } else if (hours > 48) { hSub = t("over48"); hCls = "warn"; } else { hSub = t("within48"); hCls = "good"; } }
    const simN = e.models.map((m) => m.sim && m.sim.n).filter(isNum), realN = e.models.map((m) => m.real && m.real.n).filter(isNum);
    const nSim = simN.length ? Math.max(...simN) : e.n_sim, nReal = realN.length ? Math.max(...realN) : e.n_real;
    const hasRuns = e.models.some((m) => m.sim || m.real);
    $("#kpis").innerHTML = [
      kpi(t("kpi.fidelity"), t("kpi.fidelity.help"), f ? fmt.num(f.mean_abs_gap) : null, t("unit.pts"),
        f ? `${f.n_models} ${state.lang === "zh" ? "个模型" : "models"}${isNum(f.spearman) ? ` · ${t("kpi.spearman")} ${fmt.num(f.spearman)}` : ""}` : (hasRuns ? t("pending") : t("status.planned"))),
      kpi(t("kpi.hours"), t("kpi.hours.help"), isNum(hours) ? fmt.num(hours, 1) : null, t("unit.h"), hSub, hCls),
      kpi(t("kpi.human"), t("kpi.human.help"), isNum(e.human_hours) ? fmt.num(e.human_hours, 1) : null, t("unit.h"), ""),
      kpi(t("kpi.cost"), t("kpi.cost.help"), hasRuns ? fmt.usd(e.usd_total) : null, "", ""),
      kpi(t("kpi.n"), "", isNum(nSim) || isNum(nReal) ? `${isNum(nSim) ? fmt.int(nSim) : t("na")} / ${isNum(nReal) ? fmt.int(nReal) : t("na")}` : null, "", hasRuns ? "" : (state.lang === "zh" ? "计划值" : "planned")),
      kpi(t("kpi.trigger"), "", e.trigger_model || null, "", e.trigger_released_at || ""),
    ].join("");
  }

  function gapCell(g) {
    if (!g) return `<td class="gap na">${t("pending")}</td>`;
    const v = Number(g.score), cls = v < 0 ? "neg" : v > 0 ? "pos" : "";
    const arrow = v < 0 ? "▼" : v > 0 ? "▲" : "";
    return `<td class="gap ${cls}" title="${esc(t("col.success"))}: ${esc((g.success_rate >= 0 ? "+" : "") + Math.round(g.success_rate * 100) + " pp")}">${arrow} ${v > 0 ? "+" : ""}${v.toFixed(2)}</td>`;
  }

  function renderBoard(e) {
    const tbl = $("#board"), empty = $("#board-empty");
    const sc = state.data.score_col || "sim_score_mean";
    const cols = ["col.rank", "col.model", "col.verified", "col.sim", "col.real", "col.gap", "col.success", "col.reached", "col.events", "col.pathratio", "col.cost", "col.latency", "col.n"];
    const rows = [...e.models].sort((a, b) => {
      const ka = a.real ? Number(a.real[sc]) : a.sim ? Number(a.sim[sc]) - 1e6 : -1e9;
      const kb = b.real ? Number(b.real[sc]) : b.sim ? Number(b.sim[sc]) - 1e6 : -1e9;
      return kb - ka;
    });
    // 名次：竞赛排法——同分同名次、标「并列」、不排先后（10-20：首期 qwen／deepseek sim_score 精确并列）
    const keyOf = (m) => (m.real ? Number(m.real[sc]) : m.sim ? Number(m.sim[sc]) : NaN);
    const rankOf = (m) => { const k = keyOf(m); if (!Number.isFinite(k)) return null; const r = 1 + rows.filter((x) => Number.isFinite(keyOf(x)) && keyOf(x) > k).length; const tie = rows.filter((x) => keyOf(x) === k).length > 1; return { r, tie }; };
    tbl.innerHTML = `<thead><tr>${cols.map((c) => `<th>${esc(t(c))}</th>`).join("")}</tr></thead><tbody>` + rows.map((m) => {
      const s = m.sim, r = m.real;
      const rk = rankOf(m);
      const rankCell = rk ? `<b>${rk.r}</b>${rk.tie ? `<br><small class="ident">${esc(t("rank.tie"))}</small>` : ""}` : `<span class="na">${t("na")}</span>`;
      const score = (x) => (x ? `<span title="±${esc(fmt.num(x.sim_score_ci95, 3) || "?")} (95% CI)">${cell(fmt.num(x[sc], 3))}</span>` : `<span class="na">${t("pending")}</span>`);
      const lat = (x) => (x ? `<span title="P95 ${fmt.sec(x.api_latency_p95_s)} s">${cell(fmt.sec(x.api_latency_mean_s))}</span>` : t("na"));
      const ident = [m.vendor, m.thinking ? `${t("ident.thinking")} ${m.thinking}` : "", m.endpoint ? `${t("ident.endpoint")} ${t("endpoint." + m.endpoint) === "endpoint." + m.endpoint ? m.endpoint : t("endpoint." + m.endpoint)}` : ""].filter(Boolean).join(" · ");
      const ver = `<span class="badge ${m.verified === "rerun" ? "formal" : "planned"}">${esc(t("verified." + (m.verified === "rerun" ? "rerun" : "self")))}</span>`;
      return `<tr><td>${rankCell}</td><td class="model">${esc(m.model)}${m.note ? ` <abbr class="help" title="${esc(m.note)}">?</abbr>` : ""}${ident ? `<br><small class="ident">${esc(ident)}</small>` : ""}</td>
        <td>${ver}</td><td>${score(s)}</td><td>${score(r)}</td>${gapCell(m.gap)}
        <td>${pair(s && s.success_rate, r && r.success_rate, fmt.pct)}</td>
        <td>${pair(s && s.reached_frac_mean, r && r.reached_frac_mean, fmt.pct)}</td>
        <td>${pair(s && s.collision_events_mean, r && r.collision_events_mean, (v) => fmt.num(v, 1))}</td>
        <td>${pair(s && s.path_ratio_mean_success, r && r.path_ratio_mean_success, fmt.num)}</td>
        <td><span class="pair"><b>${money(s)}</b> / <b>${money(r)}</b></span>${s && s.price_tier ? `<br><small class="ident">${esc(t("ident.tier"))} ${esc(s.price_tier)}</small>` : ""}</td>
        <td><span class="pair"><b>${lat(s)}</b> / <b>${lat(r)}</b></span></td>
        <td>${pair(s && s.n, r && r.n, fmt.int)}</td></tr>`;
    }).join("") + "</tbody>";
    empty.hidden = e.models.some((m) => m.sim || m.real);
    const fn = $("#board-fn");
    fn.hidden = !e.models.some((m) => zeroSuccess(m.sim) || zeroSuccess(m.real));
    fn.textContent = t("cost.zero.fn");
  }

  function renderBaselines(e) {
    const tbl = $("#baselines");
    if (!e.baselines.length) { tbl.innerHTML = `<tbody><tr><td class="na">${t("na")}</td></tr></tbody>`; return; }
    const sc = state.data.score_col || "sim_score_mean";
    const cols = ["col.agent", "col.kind", "col.gt", "col.score", "col.success1", "col.reached1", "col.cps", "col.events1", "col.pathratio1", "col.steps"];
    const order = { astar: 0, greedy: 1, oracle: 1, random: 2 };
    const rows = [...e.baselines].sort((a, b) => (order[a.agent] ?? 9) - (order[b.agent] ?? 9));
    tbl.innerHTML = `<thead><tr>${cols.map((c) => `<th>${esc(t(c))}</th>`).join("")}</tr></thead><tbody>` + rows.map((b) => `<tr>
      <td class="model">${esc(b.agent)}</td><td style="text-align:left">${esc(state.ui["kind." + b.agent] ? t("kind." + b.agent) : b.model_id || "")}</td>
      <td>${esc(b.agent === "random" ? t("gt.no") : t("gt.yes"))}</td>
      <td><b>${cell(fmt.num(b[sc], 3))}</b>${isNum(b.sim_score_ci95) ? `<small class="ident"> ±${esc(fmt.num(b.sim_score_ci95, 3))}</small>` : ""}</td>
      <td>${cell(fmt.pct(b.success_rate))}</td><td>${cell(fmt.pct(b.reached_frac_mean))}</td><td>${cell(fmt.num(b.checkpoint_score_mean))}</td><td>${cell(fmt.num(b.collision_events_mean, 1))}</td>
      <td>${cell(fmt.num(b.path_ratio_mean_success))}</td><td>${cell(fmt.num(b.steps_mean, 1))}</td></tr>`).join("") + "</tbody>";
  }

  function renderMethod(e) {
    const metas = Object.values(state.data.runs_meta || {});
    const meta = e.baseline_meta || metas[0] || {};
    const rej = isNum(meta.rejection_rate) ? `${(meta.rejection_rate * 100).toFixed(1)}%（${meta.seeds_rejected ?? "?"}/${meta.seeds_screened ?? "?"}）` : null;
    const dd = (k, v) => `<dt>${esc(t(k))}</dt><dd>${v}</dd>`;
    $("#method").innerHTML = [
      dd("method.protocol", esc(e.protocol_version || t("na"))),
      dd("method.prompt", shortSha(meta.prompt_sha256)),
      dd("method.config", shortSha(meta.config_sha256)),
      dd("method.reject", cell(rej)),
      dd("method.seeds", isNum(meta.seed0) ? `${esc(meta.seed0)} / ${esc(meta.seeds_screened ?? t("na"))}` : na()),
      dd("method.score", esc(t("method.score.v"))),
      dd("method.gap", esc(t("method.gap.v"))),
      dd("method.links", `${link("protocol/v0.md", t("method.zh"))} · ${link("protocol/v0.en.md", t("method.en"))}`),
    ].join("");
  }

  function renderLinks(e) {
    const runs = new Set();
    e.models.forEach((m) => { if (m.sim_run) runs.add(m.sim_run); if (m.real_run) runs.add(m.real_run); });
    if (e.baseline_run) runs.add(e.baseline_run);
    const runLinks = [...runs].map((r) => {
      const meta = state.data.runs_meta[r] || {};
      const local = meta.copy ? `<a href="${esc(meta.copy)}summary.csv">summary.csv</a>` : "";
      return `<li><span class="k">${esc(meta.platform || "")}</span>${link("episodes/" + r)} ${local}</li>`;
    }).join("");
    $("#datalinks").innerHTML = [
      `<li><span class="k">${esc(t("data.dir"))}</span>${link(e.paths.dir)}</li>`,
      `<li><span class="k">${esc(t("data.logs"))}</span>${link(e.paths.logs)}</li>`,
      `<li><span class="k">${esc(t("data.video"))}</span>${link(e.paths.video_index)} · ${e.video.length} ${esc(t("data.videos.n"))}</li>`,
      `<li><span class="k">${esc(t("data.manifest"))}</span>${link(e.paths.manifest)}</li>`,
      `<li><span class="k">${esc(t("data.runs"))}</span></li>`, runLinks,
    ].join("");
  }

  function renderFooter() {
    const b = state.build || {};
    $("#foot").innerHTML = `${esc(t("foot"))} <code>${esc(b.git_commit || "?")}</code> · ${esc(b.generated_at || "")}${state.data.repo_url ? ` · <a href="${esc(state.data.repo_url)}" target="_blank" rel="noopener">${esc(t("foot.repo"))}</a>` : ""}`;
  }

  function render() {
    applyI18n(); renderSelect();
    const e = state.edition;
    renderHero(e); renderBoard(e); renderBaselines(e); renderMethod(e); renderLinks(e); renderFooter();
    document.title = `${t("site.title")} · ${e.id}`;
  }

  try {
    const [ui, data, build] = await Promise.all([
      fetch("i18n/ui.json").then((r) => r.json()),
      fetch("data/leaderboard.json").then((r) => r.json()),
      fetch("data/build-info.json").then((r) => (r.ok ? r.json() : null)).catch(() => null),
    ]);
    state.ui = ui; state.data = data; state.build = build; state.lang = pickLang();
    const want = new URLSearchParams(location.search).get("edition");
    state.edition = data.editions.find((e) => e.id === want) || data.editions.find((e) => e.id === data.latest) || data.editions[0];
    if (!state.edition) throw new Error("no editions");
    $("#edition").addEventListener("change", (ev) => { state.edition = data.editions.find((e) => e.id === ev.target.value); render(); });
    document.querySelectorAll(".lang button").forEach((b) => b.addEventListener("click", () => {
      state.lang = b.dataset.lang; try { localStorage.setItem("pg.lang", state.lang); } catch (e) { /* ignore */ } render();
    }));
    render();
  } catch (err) {
    document.querySelector("main").innerHTML = `<p class="note">Failed to load data (${esc(err.message)}). Serve this folder over HTTP: <code>python3 -m http.server -d site 8000</code>, then open http://localhost:8000/.</p>`;
  }
})();
