/* WorkspaceBench Atlas: static viewer over data/ (built by atlas/build.py). No dependencies. */
"use strict";
const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fmt = v => v == null ? "—" : (+v).toFixed(2).replace(/^0\./, ".");
const TC = k => `var(--t-${k}, #8695a2)`;
const SHORT = { floor: "Floor", inverter: "Inverter", student: "Student", rl: "RL 600", jlens: "J-lens", jlens_pp: "J-lens++", jhead_ar: "J-head AR" };
const FAMLABEL = f => f.replace(/_/g, " ");

let IDX = null;
const S = { v: "overview", m: null, f: null, i: null, pos: null, hm: "rl", flt: "all", q: "", clamp: true };
const cache = new Map();
async function getJSON(url) {
  if (!cache.has(url)) cache.set(url, fetch(url).then(r => r.ok ? r.json() : null).catch(() => null));
  return cache.get(url);
}

/* ---------------- routing ---------------- */
function readHash() {
  const h = new URLSearchParams(location.hash.slice(1));
  S.v = h.get("v") || "overview"; S.m = h.get("m") || S.m; S.f = h.get("f") || S.f; S.i = h.get("i");
}
function go(patch, push = true) {
  Object.assign(S, patch);
  const h = new URLSearchParams({ v: S.v });
  if (S.v === "explore") { if (S.m) h.set("m", S.m); if (S.f) h.set("f", S.f); if (S.i) h.set("i", S.i); }
  const s = "#" + h.toString();
  if (push && location.hash !== s) history.pushState(null, "", s); else history.replaceState(null, "", s);
  render();
}
window.addEventListener("popstate", () => { readHash(); render(); });

/* ---------------- tooltip ---------------- */
const tip = $("#tip");
function showTip(e, html) { tip.innerHTML = html; tip.hidden = false; moveTip(e); }
function moveTip(e) {
  const w = tip.offsetWidth, h = tip.offsetHeight;
  let x = e.clientX + 14, y = e.clientY + 14;
  if (x + w > innerWidth - 8) x = e.clientX - w - 14;
  if (y + h > innerHeight - 8) y = e.clientY - h - 14;
  tip.style.left = x + "px"; tip.style.top = y + "px";
}
document.addEventListener("mouseover", e => { const t = e.target.closest("[data-tip]"); if (t) showTip(e, t.dataset.tip); });
document.addEventListener("mousemove", e => { if (!tip.hidden) { if (e.target.closest("[data-tip]")) moveTip(e); else tip.hidden = true; } });

/* ---------------- boot ---------------- */
(async function boot() {
  IDX = await getJSON("data/index.json");
  if (!IDX) { document.body.innerHTML = "<p style='padding:40px'>data/index.json missing: run atlas/build.py</p>"; return; }
  $("#built").textContent = "built " + IDX.built;
  for (const b of document.querySelectorAll("#views button")) b.onclick = () => go({ v: b.dataset.v });
  readHash();
  if (!S.m) S.m = "qwen3.5-9b";
  render();
})();

function render() {
  for (const b of document.querySelectorAll("#views button")) b.classList.toggle("on", b.dataset.v === S.v);
  for (const v of ["overview", "explore", "method"]) $("#v-" + v).hidden = S.v !== v;
  if (S.v === "overview") renderOverview();
  else if (S.v === "explore") renderExplore();
  else renderMethod();
}

/* ================= OVERVIEW ================= */
function famScore(m, f, t) {
  const e = IDX.models[m]?.families?.[f]; return e?.scores?.[t]?.v ?? null;
}
function renderOverview() {
  const ms = IDX.order.map(k => IDX.models[k]);
  const adapted = ms.filter(m => m.key !== "qwen3.6-27b");
  const nItems = adapted.reduce((a, m) => a + m.n_items, 0), nNew = adapted.reduce((a, m) => a + m.n_new, 0);
  const drops = adapted.reduce((a, m) => a + (m.drops || 0), 0);
  $("#tiles").innerHTML = [
    [`${adapted.length}/${adapted.length}`, "subject sets built and independently audited"],
    [nItems.toLocaleString(), "questions across the adaptive sets"],
    [nNew.toLocaleString(), "new items written or generated at an easier tier"],
    [drops.toLocaleString(), "items dropped by the audits (wrong gold, leak, uncreditable)"],
  ].map(([b, l]) => `<div class="tile"><div class="big">${b}</div><div class="lab">${l}</div></div>`).join("");
  renderScoreboard();
  renderNormalGated();
  renderHeatmap();
}

function renderNormalGated() {
  const ng = IDX.normal_gated || {}, el = $("#ngated");
  if (!el) return;
  const subj = Object.keys(ng);
  if (!subj.length) { el.innerHTML = `<p class="faint small">pending</p>`; return; }
  const lab = { "olmo-3.1-32b": "OLMo-3.1-32B", "qwen3.6-35b-a3b": "Qwen3.6-35B-A3B", "kimi-k2": "Kimi-K2", "glm-5.3-flash": "GLM-5.3-Flash" };
  let h = `<table class="ngt"><tr><th>subject</th><th>stage</th><th>normal bank, 23 fams</th><th>same fams, ungated</th><th>gated + own golds</th><th>Δ</th><th>families counted</th><th>dropped (&lt; 10 items the subject answers)</th></tr>`;
  for (const s of subj) for (const [st, r] of Object.entries(ng[s])) {
    const d = r.gated - r.full_same_fams;
    h += `<tr data-m="${s}@27b"><td>${esc(lab[s] || s)}</td><td>${esc(SHORT[st] || st)}</td><td class="num">${fmt(r.full_23)}</td><td class="num">${fmt(r.full_same_fams)}</td>
      <td class="num"><b>${fmt(r.gated)}</b></td><td class="num ${d >= 0 ? "up" : "down"}">${d >= 0 ? "+" : "−"}${Math.abs(d).toFixed(3).replace(/^0\./, ".")}</td><td class="num">${r.n}/23</td><td class="small dim">${esc(r.dropped.join(", ").replace(/_/g, " "))}</td></tr>`;
  }
  el.innerHTML = h + `</table>`;
  for (const tr of el.querySelectorAll("tr[data-m]")) tr.onclick = () => go({ v: "explore", m: tr.dataset.m, f: null, i: null });
}

function renderScoreboard() {
  const rows = IDX.scoreboard;
  const T = [["inverter", "Inverter"], ["student", "Student (distill)"], ["rl", "RL 600"]];
  $("#sb-legend").innerHTML = T.map(([k, l]) => `<span><i class="dot" style="background:${TC(k)}"></i>${l}</span>`).join("") +
    `<span><i class="tick"></i>Prompt-only floor</span>`;
  const W = 1000, L = 230, R = 30, rh = 26, top = 28;
  const groups = [["adaptive", "Own adaptive set"], ["normal", "Normal (27B-gated) bank"]];
  let y = top, body = "";
  const x0 = .2, x1 = .8, X = v => L + (v - x0) / (x1 - x0) * (W - L - R);
  for (const [g, gl] of groups) {
    body += `<text x="0" y="${y + 4}" font-size="10.5" font-weight="600" fill="#8695a2" letter-spacing=".07em">${gl.toUpperCase()}</text>`;
    y += 14;
    for (const r of rows.filter(r => r.set === g)) {
      const vals = T.map(([k]) => r[k]).filter(v => v != null);
      const cy = y + rh / 2;
      const tipHtml = `<b>${esc(r.name)}</b> · ${r.set} set, ${r.n_fams} families<br>` +
        T.map(([k, l]) => `${l}: <b>${fmt(r[k])}</b>${r.prov && l.toLowerCase().startsWith(r.prov.toLowerCase()) ? " (provisional)" : ""}`).join("<br>") +
        (r.floor != null ? `<br>Floor: <b>${fmt(r.floor)}</b>` : "") + (r.model ? "<br><i>click to explore</i>" : "");
      body += `<g class="row" data-m="${r.model || ""}" data-tip="${esc(tipHtml)}" style="cursor:${r.model ? "pointer" : "default"}">
        <rect class="hl" x="0" y="${y}" width="${W}" height="${rh}" rx="5" fill="transparent"/>
        <text x="${L - 14}" y="${cy + 4}" text-anchor="end" font-size="13" fill="#152230">${esc(r.name)} <tspan fill="#8695a2" font-size="11">(${r.n_fams})</tspan></text>`;
      if (vals.length > 1) body += `<line x1="${X(Math.min(...vals))}" x2="${X(Math.max(...vals))}" y1="${cy}" y2="${cy}" stroke="#d5dde3" stroke-width="2"/>`;
      if (r.floor != null) body += `<line x1="${X(r.floor)}" x2="${X(r.floor)}" y1="${cy - 8}" y2="${cy + 8}" stroke="#152230" stroke-width="2"/>`;
      for (const [k] of T) if (r[k] != null) {
        const prov = r.prov && ((r.prov === "RL" && k === "rl") || (r.prov === "inv" && k === "inverter"));
        body += `<circle cx="${X(r[k])}" cy="${cy}" r="5.5" fill="${prov ? "#fff" : `var(--t-${k})`}" stroke="${prov ? `var(--t-${k})` : "#fff"}" stroke-width="2"/>`;
      }
      if (r.rl != null) body += `<text x="${X(r.rl) + 10}" y="${cy + 4}" font-size="11" fill="#55677a" font-family="IBM Plex Mono">${fmt(r.rl)}</text>`;
      body += `</g>`;
      y += rh;
    }
    y += 12;
  }
  let axis = "";
  for (let v = .2; v <= .801; v += .1) {
    axis += `<line x1="${X(v)}" x2="${X(v)}" y1="${top - 6}" y2="${y - 10}" stroke="#eef1f4"/>` +
      `<text x="${X(v)}" y="${top - 12}" text-anchor="middle" font-size="11" fill="#8695a2" font-family="IBM Plex Mono">${v.toFixed(1)}</text>`;
  }
  $("#scoreboard").innerHTML = `<svg viewBox="0 0 ${W} ${y}" role="img" aria-label="Scoreboard">${axis}${body}</svg>`;
  for (const g of document.querySelectorAll("#scoreboard g.row")) if (g.dataset.m) g.onclick = () => go({ v: "explore", m: g.dataset.m, f: null, i: null });
}

const RAMP = ["#f1f6fd", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"];
function rampColor(v) {
  const t = Math.max(0, Math.min(.9999, v)) * (RAMP.length - 1), i = Math.floor(t), f = t - i;
  const a = RAMP[i], b = RAMP[i + 1], h = (s, o) => parseInt(s.slice(o, o + 2), 16);
  const c = [1, 3, 5].map(o => Math.round(h(a, o) + (h(b, o) - h(a, o)) * f));
  return `rgb(${c.join(",")})`;
}
function renderHeatmap() {
  const techs = [["floor", "Prompt-only floor"], ["inverter", "Inverter"], ["student", "Student"], ["rl", "RL 600"]];
  $("#hm-tech").innerHTML = techs.map(([k, l]) => `<button data-k="${k}" class="${S.hm === k ? "on" : ""}"><i class="dot" style="background:${TC(k)}"></i>${l}</button>`).join("");
  for (const b of document.querySelectorAll("#hm-tech button")) b.onclick = () => { S.hm = b.dataset.k; renderHeatmap(); };
  $("#hm-title").textContent = techs.find(t => t[0] === S.hm)[1];
  const fams = IDX.families.filter(f => IDX.order.some(m => IDX.models[m].families[f.key]));
  let groupRow = "<tr><th></th>", famRow = "<tr><th></th>";
  let g = null, span = 0;
  const groupCells = [];
  for (const f of fams) { if (f.group !== g) { if (g) groupCells.push([g, span]); g = f.group; span = 0; } span++; }
  groupCells.push([g, span]);
  const GS = { "Bag of words": "BoW", "Model-specific": "Model", "Precision": "Prec.", "Safety": "Safety" };
  groupRow += groupCells.map(([g, n]) => `<th class="grp" colspan="${n}" title="${esc(g)}">${esc(n < 3 ? (GS[g] || g) : g)}</th>`).join("") + "</tr>";
  famRow += fams.map(f => `<th class="fh" data-tip="${esc(`<b>${FAMLABEL(f.key)}</b><br>${f.desc}`)}"><span>${FAMLABEL(f.key)}</span></th>`).join("") + "</tr>";
  let rows = "";
  for (const m of IDX.order) {
    const M = IDX.models[m];
    rows += `<tr><th class="m">${esc(M.label)}</th>`;
    for (const f of fams) {
      const e = M.families[f.key];
      let sc = e?.scores?.[S.hm], combo = false;
      if (sc?.v == null && m === "qwen3.6-27b" && S.hm === "rl") {  // 27B RL lens: wsbench_combos pass rates
        const c = IDX.combos27?.["OLens · RL (combos)"]?.fams?.[f.key];
        if (c != null) { sc = { v: c, n: "common items" }; combo = true; }
      }
      const v = sc?.v;
      if (v == null) { rows += `<td class="na"></td>`; continue; }
      const tipH = `<b>${esc(M.label)}</b> · ${FAMLABEL(f.key)}<br>${esc(techs.find(t => t[0] === S.hm)[1])}: <b>${fmt(v)}</b> (n=${sc.n ?? e.n})` +
        `${sc.complete === false ? "<br>incomplete (some judge cells missing)" : ""}${combo ? "<br>27B RL arm from the wsbench_combos study (pass rate on items common to all techniques)" : ""}<br>set: ${e.n} items, ${e.n_new} new · ${e.status || ""}${e.exclude ? " · <i>out of macro</i>" : ""}`;
      rows += `<td class="${v > .55 ? "dark" : ""} ${e.exclude ? "ex" : ""}" style="background:${rampColor(v)}" data-m="${m}" data-f="${f.key}" data-tip="${esc(tipH)}">${Math.round(v * 100)}</td>`;
    }
    rows += "</tr>";
  }
  $("#heatmap").innerHTML = `<table class="hm">${groupRow}${famRow}${rows}</table>
    <div class="hmkey"><span>0</span><span class="ramp"></span><span>100</span><span style="margin-left:14px">hatched = out of that subject's macro</span></div>`;
  for (const td of document.querySelectorAll("#heatmap td[data-m]")) td.onclick = () => go({ v: "explore", m: td.dataset.m, f: td.dataset.f, i: null });
}

/* ================= EXPLORE ================= */
let FAM = null;   // loaded family payload
function techsOf(m) { return IDX.models[m].techs; }

async function renderExplore() {
  const M = IDX.models[S.m] || IDX.models[IDX.order[0]];
  S.m = M.key;
  const sel = $("#model");
  if (!sel.options.length) {
    sel.innerHTML = IDX.order.map(k => `<option value="${k}">${esc(IDX.models[k].label)}</option>`).join("");
    sel.onchange = () => go({ m: sel.value, i: null });
  }
  sel.value = S.m;
  $("#modelmeta").innerHTML = `${M.n_items.toLocaleString()} questions · ${M.n_new.toLocaleString()} new<br><code>${esc(M.bank)}</code>`;
  const fams = IDX.families.filter(f => M.families[f.key]);
  if (!S.f || !M.families[S.f]) S.f = fams[0].key;
  const headTech = M.techs.some(t => t.key === "rl") ? "rl" : M.techs[0]?.key;
  let html = "", g = null;
  for (const f of fams) {
    if (f.group !== g) { g = f.group; html += `<div class="fgrp">${esc(g)}</div>`; }
    const e = M.families[f.key], v = e.scores?.[headTech]?.v;
    html += `<div class="fam ${f.key === S.f ? "on" : ""}" data-f="${f.key}" data-tip="${esc(`<b>${FAMLABEL(f.key)}</b><br>${f.desc}<br>${e.n} items (${e.n_new} new) · ${e.status || "—"}${e.exclude ? " · out of macro" : ""}`)}">
      <span class="nm">${FAMLABEL(f.key)}</span><span class="n">${e.n}</span><span class="sc">${fmt(v)}</span></div>`;
  }
  $("#famlist").innerHTML = html;
  for (const el of document.querySelectorAll("#famlist .fam")) el.onclick = () => go({ f: el.dataset.f, i: null });
  const key = `data/${S.m}/${S.f}.json`;
  if (!FAM || FAM._key !== key) {
    $("#items").innerHTML = `<div class="more">loading…</div>`;
    const d = await getJSON(key);
    if (!d) { $("#items").innerHTML = `<div class="more">no data</div>`; return; }
    FAM = d; FAM._key = key; S.flt = "all"; S.pos = null;
    FAM._byId = new Map([...d.items, ...d.dropped].map((it, n) => [it.id, it]));
    FAM._idx = new Map(d.items.map((it, n) => [it.id, n]));
  }
  renderFamHead(M);
  renderItems();
  renderDetail();
}

function renderFamHead(M) {
  const e = M.families[S.f], fdesc = IDX.families.find(f => f.key === S.f)?.desc || "";
  const meta = FAM.meta || {};
  const scs = M.techs.filter(t => e.scores?.[t.key]?.v != null).map(t => {
    const s = e.scores[t.key];
    return `<span class="dim">${SHORT[t.key] || t.label}</span><span class="bar"><i style="width:${(s.v * 100).toFixed(1)}%;background:${TC(t.key)}"></i></span><span class="v">${fmt(s.v)} <span class="faint">n=${s.n ?? "?"}</span></span>`;
  }).join("");
  $("#famhead").innerHTML = `<div class="t">${FAMLABEL(S.f)}</div><div class="d">${esc(fdesc)}</div>
    ${scs ? `<div class="fscores">${scs}</div>` : ""}
    ${meta.note || meta.change ? `<div class="note">${esc(meta.status || "")}${meta.status ? " · " : ""}${esc(meta.note || meta.change)}</div>` : ""}`;
}

function itemPass(it, t) {
  const v = it.v?.[t]; if (!v) return null;
  if (v.p === 0 || v.p === 1) return v.p;
  if (typeof v.p === "number") return v.p >= .5 ? 1 : 0;
  if (v.s != null) return v.s >= 7 ? 1 : 0;
  return null;
}
function sqHtml(it) {
  return `<span class="sq">${techsOf(S.m).map(t => {
    const p = itemPass(it, t.key);
    return `<i class="${p === 1 ? "p" : p === 0 ? "f" : ""}" title="${esc(t.label)}: ${p === 1 ? "pass" : p === 0 ? "fail" : "no verdict"}"></i>`;
  }).join("")}</span>`;
}
function filtered() {
  const q = S.q.trim().toLowerCase();
  let list = S.flt === "dropped" ? FAM.dropped : FAM.items;
  if (S.flt === "new") list = list.filter(it => it.origin !== "original");
  if (S.flt === "orig") list = list.filter(it => it.origin === "original");
  if (S.flt === "ng1") list = list.filter(it => it.ng === true);
  if (S.flt === "ng0") list = list.filter(it => it.ng === false);
  if (S.flt.startsWith("t:")) { const [, t, w] = S.flt.split(":"); list = list.filter(it => itemPass(it, t) === (w === "p" ? 1 : 0)); }
  if (q) list = list.filter(it => (it.id + " " + it.q + " " + it.gold.join(" ") + " " + it.latent.join(" ")).toLowerCase().includes(q));
  return list;
}
function renderItems() {
  const techs = techsOf(S.m).filter(t => FAM.techs.some(x => x.key === t.key));
  const nNew = FAM.items.filter(it => it.origin !== "original").length;
  const lens = techs.find(t => t.key === "rl") || techs[techs.length - 1];
  const pills = IDX.models[S.m].gated
    ? [["all", "All", FAM.items.length], ["ng1", "Subject answers", FAM.items.filter(it => it.ng === true).length], ["ng0", "Fails gate", FAM.items.filter(it => it.ng === false).length]]
    : [["all", "All", FAM.items.length], ["new", "New", nNew], ["orig", "Original", FAM.items.length - nNew]];
  if (lens) {
    pills.push([`t:${lens.key}:p`, `${SHORT[lens.key]} ✓`, FAM.items.filter(it => itemPass(it, lens.key) === 1).length]);
    pills.push([`t:${lens.key}:f`, `${SHORT[lens.key]} ✗`, FAM.items.filter(it => itemPass(it, lens.key) === 0).length]);
  }
  if (FAM.dropped.length) pills.push(["dropped", "Replaced originals", FAM.dropped.length]);
  $("#filters").innerHTML = pills.map(([k, l, n]) => `<span class="pill ${S.flt === k ? "on" : ""}" data-k="${k}">${l}<span class="n">${n}</span></span>`).join("");
  for (const p of document.querySelectorAll("#filters .pill")) p.onclick = () => { S.flt = p.dataset.k; renderItems(); };
  const s = $("#search");
  s.value = S.q;
  s.oninput = () => { S.q = s.value; renderItems(); };
  const list = filtered(), CAP = 400;
  $("#items").innerHTML = list.slice(0, CAP).map(it => {
    const tag = it.ng === true ? `<span class="tag ok">answers</span>` : it.ng === false ? `<span class="tag drop">fails gate</span>` : it.ng === null && IDX.models[S.m].gated ? `<span class="tag orig">ungated</span>` :
      it.dropped ? `<span class="tag drop">replaced</span>` : it.origin === "original" ? `<span class="tag orig">original</span>` : `<span class="tag new">new · ${esc(it.tier || it.origin)}</span>`;
    const tgt = (it.gold.length ? it.gold : it.latent.filter(x => !x.startsWith("{"))).slice(0, 3).join(" · ");
    return `<div class="it ${it.id === S.i ? "on" : ""}" data-id="${esc(it.id)}">
      <div class="top"><span class="id">${esc(it.id)}</span>${tag}${it.dropped ? "" : sqHtml(it)}</div>
      <div class="q">${esc(it.q.slice(0, 260))}</div>${tgt ? `<div class="g">→ ${esc(tgt)}</div>` : ""}</div>`;
  }).join("") + (list.length > CAP ? `<div class="more">showing ${CAP} of ${list.length}; search to narrow</div>` : list.length ? "" : `<div class="more">nothing matches</div>`);
  for (const el of document.querySelectorAll("#items .it")) el.onclick = () => go({ i: el.dataset.id });
  if (!S.i && list.length) { S.i = list[0].id; go({ i: S.i }, false); return; }
  $("#items .it.on")?.scrollIntoView({ block: "nearest" });
}

function step(d) {
  const list = filtered(); const k = list.findIndex(it => it.id === S.i);
  const nx = list[Math.max(0, Math.min(list.length - 1, k + d))]; if (nx) go({ i: nx.id, pos: null });
}

async function renderDetail() {
  const it = FAM._byId.get(S.i);
  const D = $("#detail");
  if (!it) { D.innerHTML = `<div class="empty">Pick a question.</div>`; return; }
  const tgt = it.gold, lat = it.latent.filter(x => !x.startsWith("{") && !x.trim().endsWith("?") && !tgt.includes(x));
  const tag = it.dropped ? `<span class="tag drop">replaced: the subject failed it at the gate</span>` : it.origin === "original" ? `<span class="tag orig">original item, kept</span>` : `<span class="tag new">new · ${esc(it.origin)} · ${esc(it.tier || "")}</span>`;
  let html = `<div class="dhead"><span class="id">${esc(it.id)}</span>${tag}${it.sub ? `<span class="chip plain">${esc(it.sub)}</span>` : ""}
    <span class="nav"><button class="btn" id="prev">↑ prev</button><button class="btn" id="next">next ↓</button></span></div>
    <div class="qcard"><h3 style="margin-bottom:6px">Question · what the subject reads${it.render ? ` <span class="faint" style="text-transform:none;letter-spacing:0">(${esc(it.render)} render)</span>` : ""}</h3>
    <div class="prompt ${it.q.length > 800 ? "long" : ""}">${esc(it.q)}</div>
    <div class="kv">
      ${tgt.length ? `<div><span class="lbl">Gold</span><span class="chips">${tgt.map(t => `<span class="chip">${esc(t)}</span>`).join("")}</span></div>` : ""}
      ${lat.length ? `<div><span class="lbl">${tgt.length ? "Latent / aliases" : "Latent (never written)"}</span><span class="chips">${lat.map(t => `<span class="chip lat">${esc(t)}</span>`).join("")}</span></div>` : ""}
    </div></div>`;
  html += adaptHtml(it);
  html += `<div id="ro"></div>`;
  D.innerHTML = html;
  $("#prev").onclick = () => step(-1); $("#next").onclick = () => step(1);
  if (!it.dropped) await renderReadouts(it);
  else $("#ro").innerHTML = `<p class="note">Replaced originals were never read by the lenses: they are shown so you can see what the subject got wrong and what replaced it.</p>`;
}

function adaptHtml(it) {
  const g = it.gate;
  const knobs = Object.entries(it.knobs || {});
  let left = `<div class="mini"><h3>Why this item is here</h3>`;
  if (IDX.models[S.m].gated) {
    const own = ["poetry", "basic_readout", "moral_rationale"].includes(S.f);
    left += own ? `<p>A 27B-bank item re-golded on this subject: the gold is <b>its own</b> rhyme / favourite / side and reasons, and the lens readouts were re-judged against it. Items it has no consistent answer for are dropped.</p>`
      : it.ng === true ? `<p>A 27B-bank item that <b>this subject answers</b> at the gate (greedy right AND ≥ 8/10, every leg), so it counts in the gated score.</p>`
      : it.ng === false ? `<p>A 27B-bank item this subject <b>does not answer</b> at the gate, so it is left out of the gated score: a silent lens here isn't wrong.</p>`
      : `<p>Family without a checkable answer (directed modulation): scored on every item.</p>`;
  } else if (it.dropped) left += `<p>An original 27B-bank item. The subject did not pass the gate (greedy right AND ≥ 8/10 samples), so this family was refilled with easier items of the same kind.</p>`;
  else if (it.origin === "original") left += `<p>An original 27B-bank item that this subject also computes, so it was kept unchanged.</p>`;
  else left += `<p>Written for this subject at tier <b>${esc(it.tier || "?")}</b> (${esc(it.origin)}), then gated on the subject like every other item.</p>`;
  if (knobs.length) left += knobs.map(([k, v]) => `<div class="small"><span class="faint">${esc(k)}:</span> ${esc(v)}</div>`).join("");
  if (it.note) left += `<div class="small dim">${esc(it.note)}</div>`;
  left += `</div>`;
  let right = `<div class="mini"><h3>Gate · the subject's own answer</h3>`;
  if (!g) right += `<p class="faint">No gate record for this bank (the 27B frozen banks were gated in the original repo).</p>`;
  else {
    const leg = (x, name) => x && x.greedy != null ? `<div style="margin:4px 0">${name ? `<span class="faint small">${esc(name)}${x.passed === false ? " ✗" : x.passed ? " ✓" : ""}</span><br>` : ""}<span class="ans">${esc(x.greedy || "∅")}</span>
      <span class="samples" data-tip="${esc(`${x.k}/${x.n} samples right<br>` + (x.samples || []).map(s => `${s[1] ? "✓" : "✗"} ${esc(s[0])}`).join("<br>"))}">${(x.samples || []).map(s => `<i class="${s[1] ? "ok" : ""}"></i>`).join("")}</span>
      <span class="small ${x.ok ? "dim" : "warn"}">${x.ok ? "greedy ✓" : "greedy ✗"} · ${x.k}/${x.n}</span></div>` : "";
    const legs = Object.entries(g.legs || {});
    if (legs.length > 1) right += legs.map(([n, x]) => leg(x, n)).join("");
    else right += leg(legs[0]?.[1] || g, legs[0]?.[0]);
    if (g.rate != null) right += `<div class="small dim">gate rate ${fmt(g.rate)} · ${g.pass ? "passed" : "failed"}</div>`;
    if (g.lint?.length) right += `<div class="small warn">lint: ${esc(g.lint.join("; "))}</div>`;
    if (g.question) right += `<details><summary>question the gate asked</summary><pre>${esc(g.question)}</pre></details>`;
  }
  right += `</div>`;
  return `<div class="adapt">${left}${right}</div>`;
}

function hl(text, quote) {
  let h = esc(text);
  const q = (quote || "").trim();
  if (q.length >= 2) {
    const eq = esc(q); const i = h.toLowerCase().indexOf(eq.toLowerCase());
    if (i >= 0) h = h.slice(0, i) + "<mark>" + h.slice(i, i + eq.length) + "</mark>" + h.slice(i + eq.length);
  }
  return h;
}

async function renderReadouts(it) {
  const techs = techsOf(S.m).filter(t => FAM.techs.some(x => x.key === t.key));
  const idx = FAM._idx.get(it.id), k = Math.floor(idx / FAM.chunk);
  const data = {};
  await Promise.all(techs.map(async t => {
    const has = FAM.techs.find(x => x.key === t.key)?.readouts;
    data[t.key] = has ? ((await getJSON(`data/${S.m}/${S.f}/${t.key}.${k}.json`)) || {})[it.id] || [] : [];
  }));
  if (S.i !== it.id) return;
  // read positions (token chips) across lens techniques; floor reads one position only
  const posTok = new Map(), posPass = new Map();
  for (const t of techs) for (const r of data[t.key]) {
    if (t.key === "floor" || r[1] == null) continue;
    if (!posTok.has(r[1])) posTok.set(r[1], r[2]);
    if (r[4] === 1) posPass.set(r[1], (posPass.get(r[1]) || 0) + 1);
  }
  const poss = [...posTok.keys()].sort((a, b) => a - b);
  if (S.pos == null || !posTok.has(S.pos)) {
    S.pos = poss.length ? poss.reduce((b, p) => (posPass.get(p) || 0) > (posPass.get(b) || 0) ? p : b, poss[poss.length - 1]) : null;
  }
  const layers = [...new Set(techs.flatMap(t => data[t.key].filter(r => t.key === "floor" || poss.length < 2 || r[1] === S.pos).map(r => r[0])))].sort((a, b) => a - b);
  const cols = techs.length;
  let h = `<div class="rohead"><h3>Readouts · layer × technique</h3>
    <span class="seg"><button id="clampbtn" class="${S.clamp ? "" : "on"}">${S.clamp ? "Expand all" : "Collapse"}</button></span></div>`;
  if (poss.length > 1) {
    h += `<div class="posbar"><span>Read position (token):</span>${poss.map(p => `<span class="tok ${p === S.pos ? "on" : ""}" data-p="${p}" data-tip="position ${p}${posPass.get(p) ? `<br>${posPass.get(p)} credited readouts` : ""}">${esc(posTok.get(p) ?? p)}${posPass.get(p) ? `<span class="c">${posPass.get(p)}</span>` : ""}</span>`).join("")}</div>`;
  } else if (poss.length === 1) h += `<div class="posbar">Read at token <span class="tok on">${esc(posTok.get(poss[0]) ?? poss[0])}</span> (position ${poss[0]})</div>`;
  h += `<div class="grid" style="grid-template-columns:34px repeat(${cols}, minmax(180px,1fr))"><div></div>`;
  for (const t of techs) {
    const v = it.v?.[t.key], p = itemPass(it, t.key);
    const fs = IDX.models[S.m].families[S.f].scores?.[t.key];
    const verdict = p === 1 ? "item passes" : p === 0 ? "item fails" : "no item verdict";
    const extra = v?.k != null ? `${v.k}/${v.n} rows pass` : v?.s != null ? `score ${v.s}/10` : v?.e != null ? `earliest credited layer L${v.e}` : "";
    const badge = p === 1 ? `<span class="pb p">✓ pass</span>` : p === 0 ? `<span class="pb f">✗ fail</span>` : "";
    h += `<div class="ch" data-tip="${esc(`<b>${esc(t.label)}</b><br>${esc(t.desc)}<br>this item: ${verdict}${extra ? " · " + extra : ""}${fs?.v != null ? `<br>family score ${fmt(fs.v)} (n=${fs.n})` : ""}`)}"><i class="dot" style="background:${TC(t.key)}"></i>${esc(SHORT[t.key] || t.label)}<span class="s">${badge}</span></div>`;
  }
  for (const L of layers) {
    h += `<div class="lh">L${L}</div>`;
    for (const t of techs) {
      const rows = data[t.key].filter(r => r[0] === L && (t.key === "floor" || poss.length < 2 || r[1] === S.pos));
      if (!rows.length) {
        const lv = it.v?.[t.key]?.L?.[L];
        h += `<div class="ro none">${lv === 1 ? "✓ credited" : lv === 0 ? "✗ not credited" : ""}</div>`;
        continue;
      }
      const r = rows[0], cls = r[4] === 1 ? "p" : r[4] === 0 ? "f" : "";
      const isTok = t.key.startsWith("jlens") || t.key === "jhead_ar";
      h += `<div class="ro ${cls} ${S.clamp ? "clamp" : ""} ${isTok ? "tokens" : ""}" ${r[5] ? `data-tip="${esc("judge quote: " + esc(r[5]))}"` : ""}>${r[4] === 1 ? `<span class="vb p">✓</span>` : r[4] === 0 ? `<span class="vb f">✗</span>` : ""}${hl(r[3], r[5]) || `<span class="faint">(empty readout)</span>`}</div>`;
    }
  }
  h += `</div>`;
  const anyRo = techs.some(t => data[t.key].length);
  if (!anyRo) h += `<p class="note">No per-readout text stored for this family (jailbreak_recognition and agentic_misalignment readouts are hundreds of MB; scores only).</p>`;
  h += `<p class="note">Green edge = the judge credited that readout with the latent; orange = judged and not credited; no edge = not judged at that cell. Highlight = the judge's quote. Click a readout to expand it. Keys: j/k item, ←/→ position, e expand.</p>`;
  $("#ro").innerHTML = h;
  $("#clampbtn").onclick = () => { S.clamp = !S.clamp; renderReadouts(it); };
  for (const el of document.querySelectorAll("#ro .tok[data-p]")) el.onclick = () => { S.pos = +el.dataset.p; renderReadouts(it); };
  for (const el of document.querySelectorAll("#ro .ro:not(.none)")) el.onclick = () => el.classList.toggle("clamp");
  S._poss = poss;
}

document.addEventListener("keydown", e => {
  if (e.target.matches("input,select,textarea")) { if (e.key === "Escape") e.target.blur(); return; }
  if (e.key === "1") go({ v: "overview" }); else if (e.key === "2") go({ v: "explore" }); else if (e.key === "3") go({ v: "method" });
  if (S.v !== "explore") return;
  if (e.key === "j" || e.key === "ArrowDown") { e.preventDefault(); step(1); }
  else if (e.key === "k" || e.key === "ArrowUp") { e.preventDefault(); step(-1); }
  else if ((e.key === "ArrowRight" || e.key === "ArrowLeft") && S._poss?.length > 1) {
    const i = S._poss.indexOf(S.pos) + (e.key === "ArrowRight" ? 1 : -1);
    if (S._poss[i] != null) { S.pos = S._poss[i]; renderReadouts(FAM._byId.get(S.i)); }
  } else if (e.key === "e") { S.clamp = !S.clamp; renderReadouts(FAM._byId.get(S.i)); }
  else if (e.key === "/") { e.preventDefault(); $("#search").focus(); }
});

/* ================= METHOD ================= */
function renderMethod() {
  if ($("#method").dataset.done) return;
  const rows = IDX.order.filter(k => k !== "qwen3.6-27b").map(k => {
    const M = IDX.models[k], st = {};
    for (const e of Object.values(M.families)) st[e.status || "—"] = (st[e.status || "—"] || 0) + 1;
    const sb = IDX.scoreboard.find(r => r.model === k);
    return `<tr><td>${esc(M.label)}</td><td class="num">${Object.keys(M.families).length}</td><td class="num">${M.n_items.toLocaleString()}</td><td class="num">${M.n_new.toLocaleString()}</td>
      <td class="num">${M.drops}</td><td class="small">${["full", "partial", "untried", "ooc", "blocked"].filter(s => st[s]).map(s => `${s} ${st[s]}`).join(" · ")}</td>
      <td class="num" style="white-space:nowrap">${sb ? `${fmt(sb.inverter)} / ${fmt(sb.student)} / ${fmt(sb.rl)}${sb.set === "normal" ? ` <span class="faint">normal bank</span>` : ""}` : "—"}</td><td class="num">${sb?.floor != null ? fmt(sb.floor) : "—"}</td></tr>`;
  }).join("");
  $("#method").innerHTML = `
  <h2>How the adaptive benchmark is built</h2>
  <p class="sub">WorkspaceBench asks whether a lens surfaces something a model <i>computes but never writes</i>. Its banks were gated on Qwen3.6-27B, so on a smaller model many items test a latent the model never computed — a lens that stays silent there isn't wrong. The <code>adapt-bank</code> agent skill rebuilds the bank for each subject.</p>
  <div class="callout"><b>The rule:</b> change the <i>difficulty</i> of what is asked, never the construction rules, the gate, or the scorer. Easier is fine; a different kind of latent is not.</div>

  <h4>What makes it adaptive</h4>
  <ol class="steps">
    <li><b>Profile.</b> Every original item is asked to the subject itself (its own chat template, thinking off): greedy + 10 samples. An item is kept only if the greedy answer is right <i>and</i> ≥ 8/10 samples are (10/10 for chain). Multihop-style families also gate the hidden bridge, because that's the scored latent.</li>
    <li><b>Rebuild what is model-specific.</b> Poetry uses the subject's own rhyme, basic_readout its own favourite, moral_rationale its own side and reasons, agentic its own misaligned rollouts, jlens_concept_pr its own J-lens (where neuronpedia has no lens for the subject we fitted one with its recipe). Layers are remapped by depth.</li>
    <li><b>Refill down a difficulty ladder.</b> Each family has ordered tiers (tier 0 = original difficulty, each later tier easier on the knob that matters). Deterministic families (chain, arithmetic, relational) are regenerated; the rest are written by Opus against a per-family brief, with items the subject passed as few-shots. Each wave is steered by the last wave's misses.</li>
    <li><b>Lint, then gate.</b> Every candidate is linted before any GPU time (leak of the answer into the prompt, format, single-/multi-token constraints with the subject's tokenizer, family invariants), then gated on the subject exactly like the originals.</li>
    <li><b>Stop honestly.</b> <i>full</i> = target reached; <i>partial</i> = easiest tier exhausted; <i>ooc</i> = &lt; 3% yield on ≥ 60 candidates at the easiest tier that still carries the latent; <i>blocked</i> = something missing. Never pad.</li>
    <li><b>Freeze, audit, publish.</b> An independent agent audits each set; its drops are applied and the set re-frozen. Prompt-only floors are measured on the final items.</li>
  </ol>

  <h4>The checks</h4>
  <ul>
    <li><b>Gate fidelity:</b> the subject grades by answering; a deterministic grader or the repo grader checks the answer. Opus authors but never grades its own items. Grading misses (a valid alias) are fixed in the grader, never by lowering the bar.</li>
    <li><b>Lint:</b> answer leaks (exact and stem), numeric leaks, token-count rules per family, bridge/target overlap, pair atomicity (twins, ab/ba pass or drop together), ≤ 20% of a family from any one template/topic.</li>
    <li><b>Independent audit per set</b> (<code>adapted/&lt;model&gt;/AUDIT.md</code>): Opus blind-solves ~25 items per family and compares to gold; all arithmetic and chain items recomputed; buggy_code programs executed; read sites re-tokenised; a natural-name credit test on every multi-token item; and a <b>judge test</b> with synthetic gold / near-miss foil / irrelevant readouts. Across all 9 audits the Opus judge credited 100% of gold readouts and 0% of foil / irrelevant ones, and blind-solves found no wrong golds left in the kept items.</li>
    <li><b>Prompt-only floors:</b> the stock subject reads the prompt and describes what it thinks the model is computing, scored by the same Opus judges. Easier items can raise a floor, so every lens score should be read against its own floor.</li>
  </ul>

  <h4>Per subject</h4>
  <table><tr><th>subject</th><th>families</th><th>items</th><th>new</th><th>audit drops</th><th>family status</th><th>inv / student / RL</th><th>floor</th></tr>${rows}</table>
  <p class="small dim">Macro = mean normalized score over the families the set holds (excluding ooc/blocked/out-of-macro ones). OLMo-3.1-32B and Qwen3.6-35B-A3B have audited sets and floors, but their OLens are scored on the normal bank (≥ 32B), so their per-item readouts here are the floor only.</p>

  <h4>What the scores say</h4>
  <ul>
    <li>Re-gating helps most where the 27B bank asked things small models can't do: e.g. Qwen3.5-9B multihop_mt inverter .09 → .48, RL .23 → .64; the 2B and 0.8B gain ~+.15 macro over the same families on the normal bank.</li>
    <li>Every subject with a measured floor has its RL lens above it, except Gemma-4-31B (RL .626 vs floor .668, floor measured before a BOS fix). The Qwen3.5-9B inverter is <i>below</i> its floor (.554 vs .600 over the same 21 families).</li>
    <li>Arithmetic stays near 0 for every lens even on easier items, while its floor is ~.3–.4: the lenses don't surface intermediate values there.</li>
  </ul>
  <p class="small faint">Sources: <code>/workspace/agam/workspace-bench/adapted/README.md</code>, <code>.claude/skills/adapt-bank/SKILL.md</code>, <code>/workspace/agam/olens_report/adaptive_scores_*.md</code>, <code>/workspace/agam/experiments/olens-train/combined_scoreboard/</code>.</p>`;
  $("#method").dataset.done = 1;
}
