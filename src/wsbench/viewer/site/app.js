// WorkspaceBench bank viewer. Routes: #/<model>  and  #/<model>/<family>
"use strict";

const app = document.getElementById("app");
const cache = new Map();
let INDEX = null;
const PAGE = 100;

const STATUS = {
  original: ["✓", "Original bank"],
  full: ["✓", "Filled"],
  partial: ["!", "Partial"],
  ooc: ["✕", "Out of capability"],
  blocked: ["✕", "Blocked"],
  todo: ["○", "Not run"],
  profiled: ["◔", "Profiled, not filled"],
};

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const pct = (x) => (x == null ? "—" : `${Math.round(x * 100)}%`);
const title = (f) => f.replace(/_/g, " ").replace(/\bmt\b/, "(multi-token)").replace(/^./, (c) => c.toUpperCase());
const fmt = (n) => (n == null ? "—" : Number(n).toLocaleString());

async function getJSON(path) {
  if (!cache.has(path)) cache.set(path, fetch(path).then((r) => (r.ok ? r.json() : Promise.reject(r.status))));
  return cache.get(path);
}

function parseRoute() {
  const [path, query] = location.hash.replace(/^#\/?/, "").split("?");
  const [model, family] = path.split("/").filter(Boolean).map(decodeURIComponent);
  return { model: model || INDEX.models.at(-1).key, family, q: new URLSearchParams(query || "") };
}

function setQuery(params) {
  const { model, family } = parseRoute();
  const q = new URLSearchParams(params);
  for (const [k, v] of [...q]) if (!v || v === "all") q.delete(k);
  const s = q.toString();
  history.replaceState(null, "", `#/${model}/${family}${s ? "?" + s : ""}`);
}

function renderModels(current) {
  document.getElementById("models").innerHTML = INDEX.models
    .map((m) => `<a class="pill" href="#/${m.key}" aria-current="${m.key === current}">${esc(m.label)}</a>`)
    .join("");
}

function statusCell(s) {
  const [icon, label] = STATUS[s] || ["○", s || "—"];
  return `<span class="status s-${esc(s)}"><b aria-hidden="true">${icon}</b> ${esc(label)}</span>`;
}

function meter(fam) {
  const target = fam.target || fam.n_original || fam.n_items || 1;
  const kept = fam.n_items - (fam.n_new || 0);
  const w = (n) => `${Math.min(100, (100 * n) / target)}%`;
  const tip = `${kept} original + ${fam.n_new || 0} new of ${target}`;
  return `<div class="meter-wrap" title="${esc(tip)}"><div class="meter" role="img" aria-label="${esc(tip)}">
    ${kept ? `<i class="o" style="width:${w(kept)}"></i>` : ""}${fam.n_new ? `<i class="n" style="width:${w(fam.n_new)}"></i>` : ""}
  </div><span class="mono">${fam.n_items}${fam.target ? ` / ${fam.target}` : ""}</span></div>`;
}

function overview(model) {
  const isOrig = model.key === INDEX.models[0].key;
  const fams = model.families;
  const vals = Object.values(fams);
  const nItems = vals.reduce((a, f) => a + (f.n_items || 0), 0);
  const nNew = vals.reduce((a, f) => a + (f.n_new || 0), 0);
  const filled = vals.filter((f) => f.status === "full").length;
  const meta = model.meta || {};

  const tiles = isOrig
    ? [[vals.length, "families"], [fmt(nItems), "items"], ["Qwen3.6-27B", "gated on"]]
    : [
        [`${filled} / ${vals.length}`, "families filled"],
        [fmt(nItems), "items in adapted bank"],
        [fmt(nNew), "new items, gated on this model"],
        ...(meta.gate ? [[esc(meta.gate.rule || ""), "gate rule"]] : []),
      ];

  let html = `<h1>${esc(model.label)}</h1>
    <p class="secondary">${
      isOrig
        ? "The frozen banks as published. Every item was gated on Qwen3.6-27B. Pick an adapted model above to see its own bank."
        : `Every item below is one this model answers correctly (greedy, and in at least 8 of 10 samples). Items it failed were replaced by new items of the same kind, made easier until it passes.${meta.note ? " " + esc(meta.note) : ""}`
    }</p>
    <div class="tiles">${tiles.map(([v, l]) => `<div class="tile"><div class="v">${v}</div><div class="l">${l}</div></div>`).join("")}</div>
    ${isOrig ? "" : `<div class="legend"><span><i style="background:var(--series-1)"></i>original item kept</span><span><i style="background:var(--series-2)"></i>new item</span></div>`}`;

  for (const g of INDEX.groups) {
    const rows = g.families.filter((f) => fams[f]);
    if (!rows.length) continue;
    const cols = isOrig ? ["28%", "32%", "14%", "26%"] : ["20%", "22%", "14%", "10%", "14%", "20%"];
    html += `<h2>${esc(g.title)}</h2><table class="fam"><colgroup>${cols.map((w) => `<col style="width:${w}">`).join("")}</colgroup><thead><tr>
      <th>Family</th><th>Items</th>
      ${isOrig ? `<th class="num">Bank rate</th><th>Subfamilies</th>` : `<th class="num">Original bank passed</th><th class="num">Mean gate rate</th><th>Status</th><th>What changed</th>`}
      </tr></thead><tbody>`;
    for (const f of rows) {
      const s = fams[f];
      const passed = s.n_original ? `${s.n_original_pass ?? "—"} / ${s.n_original} <span class="muted">(${pct((s.n_original_pass ?? 0) / s.n_original)})</span>` : "—";
      html += `<tr tabindex="0" data-href="#/${model.key}/${f}">
        <td class="name">${esc(title(f))}</td><td>${meter(s)}</td>
        ${isOrig
          ? `<td class="num">${pct(s.mean_rate)}</td><td class="knobs">${esc((s.subfamilies || []).join(" · "))}</td>`
          : `<td class="num">${passed}</td><td class="num">${pct(s.mean_rate)}</td><td>${statusCell(s.status)}</td><td class="knobs">${esc(s.change || s.note || "")}</td>`}
        </tr>`;
    }
    html += "</tbody></table>";
  }
  app.innerHTML = html;
  app.querySelectorAll("tr[data-href]").forEach((tr) => {
    const go = () => (location.hash = tr.dataset.href);
    tr.addEventListener("click", go);
    tr.addEventListener("keydown", (e) => e.key === "Enter" && go());
  });
}

function gateMark(g) {
  if (g && g.lint) return `<span class="mark no" title="rejected by lint">⊘</span>`;
  if (!g || g.pass == null) return `<span class="mark na" title="no gate record">–</span>`;
  return g.pass ? `<span class="mark ok" title="passes the gate">✓</span>` : `<span class="mark no" title="fails the gate">✕</span>`;
}

function rateText(g) {
  if (!g) return "";
  const s = g.samples;
  if (Array.isArray(s) && s.length) return `${s.filter((x) => x.ok).length}/${s.length}`;
  return g.rate != null ? pct(g.rate) : "";
}

function answers(g) {
  if (!g || (!g.greedy && !g.samples)) return "";
  const groups = new Map();
  for (const s of g.samples || []) {
    const key = (s.text ?? "∅").trim();
    const cur = groups.get(key) || { ok: s.ok, n: 0 };
    cur.n += 1;
    groups.set(key, cur);
  }
  const mk = (ok) => (ok == null ? `<span class="mark na">–</span>` : ok ? `<span class="mark ok">✓</span>` : `<span class="mark no">✕</span>`);
  let rows = "";
  if (g.greedy) rows += `${mk(g.greedy.ok)}<span class="a">${esc(g.greedy.text)}</span><span class="c">greedy</span>`;
  for (const [t, v] of [...groups].sort((a, b) => b[1].n - a[1].n)) rows += `${mk(v.ok)}<span class="a">${esc(t)}</span><span class="c">×${v.n}</span>`;
  const legs = Object.entries(g.legs || {});
  const LEG = { surface: "chat question", "surface:plain": "plain continuation" };
  const legRows = legs.length > 1
    ? `<div class="legs">${legs.map(([name, l]) => `<div class="leg">${mk(l.passed)}<span class="k">${esc(LEG[name] || name.replace("bridge", "bridge question "))}</span><span class="rate">${l.samples.filter((x) => x.ok).length}/${l.samples.length}</span><span class="a">${esc((l.greedy.text || "").split("\n")[0].slice(0, 80))}</span></div>`).join("")}</div>`
    : "";
  const shown = legs.length > 1 ? `<p class="muted small">Answers below: ${esc(LEG[g.render] || g.render || "")}. ${g.pass ? "Passed" : "Failed"}: every question must pass; either render of the same question is enough.</p>` : "";
  return `<div><h3>Model answers</h3>${legRows}${shown}<div class="answers">${rows}</div>${g.question ? `<details class="raw"><summary>question asked</summary><pre>${esc(g.question)}</pre></details>` : ""}</div>`;
}

function itemCard(it) {
  const preview = it.stimulus.replace(/\s+/g, " ").slice(0, 220);
  const knobs = Object.entries(it.knobs || {});
  return `<details class="item" data-id="${esc(it.id)}">
    <summary>${gateMark(it.gate)}<span class="iid" title="${esc(it.id)}">${esc(it.id)}</span>
      <span class="preview">${esc(preview)}</span>
      <span class="tags">${it.origin !== "original" ? `<span class="tag new">new</span>` : ""}${it.subfamily ? `<span class="tag">${esc(it.subfamily)}</span>` : ""}${!it.selected ? `<span class="tag">not in bank</span>` : ""}<span class="rate">${rateText(it.gate)}</span></span>
    </summary>
    <div class="body">
      <div><h3>What the model sees</h3><pre class="stim">${esc(it.stimulus)}</pre></div>
      ${it.target.length ? `<div><h3>Expected answer</h3><div class="chips">${it.target.map((t, i) => `<span class="chip${i ? "" : " t"}">${esc(t)}</span>`).join("")}</div></div>` : ""}
      ${it.latent.length ? `<div><h3>Hidden latent (what the lens should surface)</h3><div class="chips">${it.latent.map((t) => `<span class="chip">${esc(t)}</span>`).join("")}</div></div>` : ""}
      ${it.gate && it.gate.lint ? `<div><h3>Rejected before gating</h3><div class="chips">${it.gate.lint.map((p) => `<span class="chip">${esc(p)}</span>`).join("")}</div></div>` : ""}
      ${answers(it.gate)}
      ${knobs.length || it.note ? `<div><h3>How it was adapted</h3><div class="chips">${knobs.map(([k, v]) => `<span class="chip">${esc(k)}: ${esc(typeof v === "object" ? JSON.stringify(v) : v)}</span>`).join("")}</div>${it.note ? `<p class="secondary">${esc(it.note)}</p>` : ""}</div>` : ""}
      <details class="raw"><summary>all fields</summary><pre>${esc(JSON.stringify(it.raw, null, 1))}</pre></details>
    </div></details>`;
}

async function familyView(model, family, q) {
  const s = model.families[family];
  if (!s) return (app.innerHTML = `<p class="empty">No ${esc(family)} for ${esc(model.label)}.</p>`);
  app.innerHTML = `<p class="muted">Loading ${esc(family)}…</p>`;
  const data = await getJSON(`data/${model.key}/${family}.json`);
  const items = data.items;
  const hasCands = items.some((i) => !i.selected);
  const hasNew = items.some((i) => i.origin !== "original");
  const subs = [...new Set(items.map((i) => i.subfamily).filter(Boolean))].sort();
  const state = { pass: q.get("pass") || "all", origin: q.get("origin") || "all", set: q.get("set") || (hasCands ? "bank" : "all"), sub: q.get("sub") || "all", text: q.get("text") || "", open: q.get("open") || "", shown: PAGE };

  const seg = (key, opts) => `<div class="seg" role="group">${opts.map(([v, l]) => `<button type="button" data-k="${key}" data-v="${v}" aria-pressed="${state[key] === v}">${l}</button>`).join("")}</div>`;

  app.innerHTML = `<div class="crumb"><a href="#/${model.key}">${esc(model.label)}</a> / ${esc(title(family))}</div>
    <h1>${esc(title(family))}</h1>
    <div class="tiles">
      <div class="tile"><div class="v">${s.n_items}${s.target ? ` / ${s.target}` : ""}</div><div class="l">items in bank</div></div>
      ${hasNew ? `<div class="tile"><div class="v">${s.n_new}</div><div class="l">new items</div></div>` : ""}
      ${s.n_original ? `<div class="tile"><div class="v">${pct((s.n_original_pass ?? 0) / s.n_original)}</div><div class="l">of the original bank passed</div></div>` : ""}
      <div class="tile"><div class="v">${pct(s.mean_rate)}</div><div class="l">mean gate rate</div></div>
      ${s.status !== "original" ? `<div class="tile"><div class="v" style="font-size:15px">${statusCell(s.status)}</div><div class="l">status</div></div>` : ""}
    </div>
    ${s.change ? `<p class="secondary"><b>What changed:</b> ${esc(s.change)}</p>` : ""}
    ${s.gate_rule ? `<p class="muted"><b>Gate:</b> ${esc(s.gate_rule)}</p>` : ""}
    ${s.note ? `<p class="secondary">${esc(s.note)}</p>` : ""}
    <div class="filters">
      ${hasCands ? seg("set", [["bank", "In bank"], ["all", "All gated"]]) : ""}
      ${seg("pass", [["all", "All"], ["pass", "✓ Passed"], ["fail", "✕ Failed"]])}
      ${hasNew ? seg("origin", [["all", "Any origin"], ["original", "Original"], ["new", "New"]]) : ""}
      ${subs.length > 1 ? `<select data-k="sub"><option value="all">All subfamilies</option>${subs.map((x) => `<option ${state.sub === x ? "selected" : ""}>${esc(x)}</option>`).join("")}</select>` : ""}
      <input type="search" placeholder="Search id, prompt, answer…" value="${esc(state.text)}">
      <span class="count"></span>
    </div>
    <div class="items"></div>`;

  const list = app.querySelector(".items");
  const count = app.querySelector(".count");
  const draw = () => {
    const t = state.text.toLowerCase();
    const rows = items.filter((i) =>
      (state.set === "all" || i.selected) &&
      (state.pass === "all" || (state.pass === "pass" ? i.gate?.pass === true : i.gate?.pass === false)) &&
      (state.origin === "all" || (state.origin === "new" ? i.origin !== "original" : i.origin === "original")) &&
      (state.sub === "all" || i.subfamily === state.sub) &&
      (!t || `${i.id} ${i.stimulus} ${i.target.join(" ")} ${i.latent.join(" ")}`.toLowerCase().includes(t)));
    count.textContent = `${rows.length} of ${items.length}`;
    list.innerHTML = rows.length
      ? rows.slice(0, state.shown).map(itemCard).join("") + (rows.length > state.shown ? `<button class="pill more" type="button">Show ${Math.min(PAGE, rows.length - state.shown)} more</button>` : "")
      : `<p class="empty">No items match.</p>`;
    list.querySelector(".more")?.addEventListener("click", () => { state.shown += PAGE; draw(); });
    list.querySelectorAll("details.item").forEach((d) => {
      if (d.dataset.id === state.open) { d.open = true; requestAnimationFrame(() => d.scrollIntoView({ block: "start" })); }
      d.addEventListener("toggle", () => { if (d.open) { state.open = d.dataset.id; sync(); } else if (state.open === d.dataset.id) { state.open = ""; sync(); } });
    });
    sync();
  };
  const sync = () => setQuery({ pass: state.pass, origin: state.origin, set: hasCands ? state.set : "", sub: state.sub, text: state.text, open: state.open });
  app.querySelectorAll(".seg button").forEach((b) => b.addEventListener("click", () => {
    state[b.dataset.k] = b.dataset.v; state.shown = PAGE;
    app.querySelectorAll(`.seg button[data-k="${b.dataset.k}"]`).forEach((x) => x.setAttribute("aria-pressed", x === b));
    draw();
  }));
  app.querySelector("select[data-k]")?.addEventListener("change", (e) => { state.sub = e.target.value; draw(); });
  let timer;
  app.querySelector("input[type=search]").addEventListener("input", (e) => { clearTimeout(timer); timer = setTimeout(() => { state.text = e.target.value; state.shown = PAGE; draw(); }, 150); });
  draw();
}

async function route() {
  const { model: key, family, q } = parseRoute();
  const model = INDEX.models.find((m) => m.key === key) || INDEX.models[0];
  renderModels(model.key);
  if (family) await familyView(model, family, q);
  else overview(model);
  window.scrollTo(0, 0);
}

document.getElementById("theme").addEventListener("click", () => {
  const root = document.documentElement;
  const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  root.dataset.theme = dark ? "light" : "dark";
  localStorage.setItem("wsb-theme", root.dataset.theme);
});
if (localStorage.getItem("wsb-theme")) document.documentElement.dataset.theme = localStorage.getItem("wsb-theme");

getJSON("data/index.json")
  .then((idx) => { INDEX = idx; window.addEventListener("hashchange", route); route(); })
  .catch(() => (app.innerHTML = `<p class="empty">Could not load data/index.json. Build it with <code>python -m wsbench.viewer.build</code> and serve the folder over http.</p>`));
