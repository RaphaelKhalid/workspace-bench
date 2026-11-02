"""Live WorkspaceBench viewer (FastHTML + htmx): scores per model x family, family item lists,
and per-item readouts with judge verdicts. Run: python app.py [--port 5077]."""

import argparse
import json
import math
import os
import sys
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).parent))

import index as ix
from fasthtml.common import (
    H1,
    H2,
    H3,
    A,
    Button,
    Code,
    Details,
    Div,
    Form,
    Input,
    Label,
    Main,
    Nav,
    Option,
    P,
    Pre,
    Select,
    Small,
    Span,
    Style,
    Summary,
    Table,
    Tbody,
    Td,
    Th,
    Thead,
    Title,
    Tr,
    fast_app,
)

HERE = Path(__file__).parent
(HERE / "static").mkdir(exist_ok=True)

CSS = """
:root{--ink:#16161a;--ink2:#4a4a52;--muted:#8a8a93;--grid:#e4e4e8;--surf:#fff;--page:#f6f6f4;
--acc:#2a62c9;--pass:#1d8a4e;--fail:#c2410c;--na:#9a9aa3}
*{box-sizing:border-box}
body{font:13.5px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif;background:var(--page);color:var(--ink);margin:0}
nav.top{display:flex;gap:18px;align-items:center;padding:10px 22px;background:#1f2330;color:#fff;position:sticky;top:0;z-index:10}
nav.top a{color:#dfe6ff;text-decoration:none;font-weight:500} nav.top .sp{flex:1}
nav.top .meta{color:#9aa3b8;font-size:12px}
nav.top button{background:#3a4258;color:#fff;border:0;border-radius:5px;padding:4px 10px;cursor:pointer}
main{padding:14px 22px 60px;max-width:2200px}
h1{font-size:20px;margin:6px 0 4px} h2{font-size:16px;margin:22px 0 6px} h3{font-size:14px;margin:14px 0 4px}
a{color:var(--acc)} .muted{color:var(--muted)} .small{font-size:12px}
form.filters{display:flex;flex-wrap:wrap;gap:10px 16px;align-items:end;background:var(--surf);border:1px solid var(--grid);
border-radius:8px;padding:10px 12px;margin:8px 0 12px}
form.filters label{display:flex;flex-direction:column;font-size:11.5px;color:var(--ink2);gap:2px}
form.filters label.cb{flex-direction:row;align-items:center;gap:5px}
select,input[type=text],input[type=search]{font:inherit;padding:3px 6px;border:1px solid #c9c9d1;border-radius:5px;background:#fff}
.tw{overflow:auto;border:1px solid var(--grid);border-radius:8px;background:var(--surf)}
table{border-collapse:collapse;font-variant-numeric:tabular-nums}
th,td{border-bottom:1px solid var(--grid);padding:4px 7px;text-align:left;vertical-align:top}
thead th{background:#fafafa;position:sticky;top:0;z-index:2}
table.scores td.v{text-align:center;min-width:44px;white-space:nowrap}
table.scores th.rot{height:150px;white-space:nowrap;vertical-align:bottom;padding:0 2px}
table.scores th.rot>div{transform:rotate(-58deg);transform-origin:left bottom;width:26px;margin-left:16px;font-weight:500;font-size:11.5px}
table.scores td.run,table.scores th.run{position:sticky;left:0;background:var(--surf);z-index:1;min-width:250px;max-width:330px}
thead th.run{z-index:3}
.v a{color:inherit;text-decoration:none;display:block}
.v .n{display:block;font-size:10px;color:var(--ink2);opacity:.8}
tr.floor td.run{font-style:italic}
.badge{display:inline-block;min-width:18px;padding:0 5px;border-radius:9px;font-size:11.5px;font-weight:600;text-align:center;color:#fff}
.b-pass{background:var(--pass)} .b-fail{background:var(--fail)} .b-mid{background:#b08600} .b-na{background:#d5d5db;color:#555}
.b-stage{background:#e8ecf7;color:#2a3d73;font-weight:500}
.pill{display:inline-block;padding:0 6px;border-radius:9px;background:#eef0f4;color:var(--ink2);font-size:11.5px;margin:0 3px 2px 0}
.gold{background:#e6f4ea;color:#14532d}
pre{white-space:pre-wrap;word-break:break-word;background:#fbfbfa;border:1px solid var(--grid);border-radius:6px;padding:8px;margin:4px 0;font:12.5px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;max-height:420px;overflow:auto}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(380px,1fr));gap:12px}
.card{background:var(--surf);border:1px solid var(--grid);border-radius:8px;padding:8px 10px;max-height:900px;overflow:auto}
.card h3{margin:0 0 4px;font-size:13.5px}
.ro{border-top:1px solid var(--grid);padding:5px 0}
.ro .hd{font-size:11.5px;color:var(--ink2);display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.ro .tx{white-space:pre-wrap;word-break:break-word;font-size:12.5px;margin-top:2px}
.ro .tx.tok{font-family:ui-monospace,Menlo,monospace;font-size:12px}
.strip{display:inline-flex;gap:1px;vertical-align:middle}
.strip span{width:13px;height:13px;font-size:8px;line-height:13px;text-align:center;color:#fff;border-radius:2px}
.kv td:first-child{color:var(--ink2);white-space:nowrap;width:150px}
.pager{display:flex;gap:10px;align-items:center;margin:10px 0}
.grid2{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1fr);gap:16px}
@media (max-width:1100px){.grid2{grid-template-columns:1fr}}
.note{background:#fff8e6;border:1px solid #f1dfa8;border-radius:6px;padding:6px 10px;font-size:12px;color:#6b5310;margin:6px 0}
"""

AUTO = "this.form.requestSubmit()"

app, rt = fast_app(
    pico=False,
    hdrs=(Style(CSS),),
    secret_key=os.urandom(24).hex(),
    static_path=str(HERE / "static"),
    title="WorkspaceBench viewer",
    bodykw={"hx-boost": "true"},
)
INDEX = ix.Index()


def D():
    return INDEX.data


# --------------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------------


def url(path: str, **params) -> str:
    q = []
    for k, v in params.items():
        if v is None or v == "" or v == []:
            continue
        if isinstance(v, list | tuple):
            q += [(k, x) for x in v]
        else:
            q.append((k, v))
    return path + ("?" + urlencode(q) if q else "")


def fmt(v, metric=None) -> str:
    if not isinstance(v, int | float) or (isinstance(v, float) and math.isnan(v)):
        return "—"
    if metric == "score":
        return f"{v:.2f}"
    return f"{v:.2f}" if abs(v) < 10 else f"{v:.1f}"


def heat(norm) -> str:
    if not isinstance(norm, int | float):
        return ""
    a = 0.06 + 0.62 * max(0.0, min(1.0, norm))
    col = "#fff" if a > 0.5 else "inherit"
    return f"background:rgba(42,98,201,{a:.2f});color:{col}"


def badge_for(v: dict | None, layer=None):
    """Item-level verdict badge from a compact verdict ({pass, n_pass, n_judged, score, by_layer})."""
    if not v:
        return Span("·", cls="badge b-na", title="no verdict")
    if layer is not None and v.get("by_layer"):
        bl = v["by_layer"]
        if layer in bl:
            ok = bl[layer]
            return Span(
                "✓" if ok else "✗", cls=f"badge {'b-pass' if ok else 'b-fail'}", title=f"L{layer}"
            )
        return Span("·", cls="badge b-na", title=f"no verdict at L{layer}")
    if v.get("pass") is not None:
        ok = v["pass"]
        return Span(
            "✓" if ok else "✗",
            cls=f"badge {'b-pass' if ok else 'b-fail'}",
            title="item pass" if ok else "item fail",
        )
    if v.get("n_judged"):
        k, n = v["n_pass"], v["n_judged"]
        cls = "b-pass" if k == n else "b-fail" if k == 0 else "b-mid"
        return Span(f"{k}/{n}", cls=f"badge {cls}", title=f"{k} of {n} judged rows pass")
    if v.get("score") is not None:
        return Span(f"{v['score']:.1f}", cls="badge b-mid", title="mean score")
    return Span("?", cls="badge b-na", title=json.dumps(v)[:200])


def strip_for(v: dict | None):
    if not v or not v.get("by_layer"):
        return ""
    cells = []
    for lay in sorted(v["by_layer"]):
        ok = v["by_layer"][lay]
        cells.append(
            Span(
                str(lay),
                style=f"background:{'var(--pass)' if ok else 'var(--fail)'}",
                title=f"L{lay}: {'pass' if ok else 'fail'}",
            )
        )
    return Span(*cells, cls="strip")


def verdict_pass_value(v: dict | None, layer=None):
    if not v:
        return None
    if layer is not None and v.get("by_layer"):
        return v["by_layer"].get(layer)
    if v.get("pass") is not None:
        return v["pass"]
    if v.get("n_judged"):
        return v["n_pass"] > 0
    return None


def run_link_label(r: dict):
    return Span(
        A(ix.model_label(r["subject"]), href=url("/", model=r["subject"])),
        " ",
        Span(ix.STAGE_LABEL.get(r["stage"], r["stage"]), cls="badge b-stage"),
        Div(
            Small(
                r["tag"] if r["tag"] != ix.STAGE_LABEL.get(r["stage"]) else r["bank"] + " bank",
                cls="muted",
            ),
            title=r.get("notes", ""),
        ),
    )


def score_title(e: dict) -> str:
    bits = [f"{e.get('metric') or 'value'} = {fmt(e.get('value'))}"]
    if e.get("ci95"):
        try:
            bits.append(f"95% CI [{e['ci95'][0]:.3f}, {e['ci95'][1]:.3f}]")
        except Exception:
            pass
    if e.get("n") is not None:
        bits.append(f"n = {e['n']}")
    if e.get("higher_is_better") is False:
        bits.append("lower is better")
    if e.get("chance") is not None:
        bits.append(f"chance {fmt(e['chance'])}")
    if e.get("judge"):
        bits.append(f"judge {e['judge']}")
    if e.get("complete") is not None:
        bits.append("complete" if e["complete"] else "NOT complete")
    for k in ("n_missing", "n_unjudged", "n_no_readouts"):
        if e.get(k):
            bits.append(f"{k} {e[k]}")
    return " · ".join(bits)


def select(name, options, value, label, auto=True):
    opts = [Option(lab, value=val, selected=(str(val) == str(value))) for val, lab in options]
    return Label(label, Select(*opts, name=name, onchange=AUTO if auto else None))


def page(title, *content):
    d = D()
    st = d["stats"]
    nav = Nav(
        A("WSB viewer", href="/", style="font-weight:700;color:#fff"),
        A("Overview", href="/"),
        A("Banks", href="/banks"),
        A("Runs", href="/runs"),
        Span(cls="sp"),
        Span(
            f"{st['models']} models · {st['runs']} runs · {st['readout_files']} readout files · indexed {d['built_at']}",
            cls="meta",
        ),
        Form(
            Button(
                "Rescan",
                type="submit",
                title="re-walk the data dirs; only changed files are re-read",
            ),
            method="post",
            action="/rescan",
            style="margin:0",
        ),
        cls="top",
    )
    return Title(f"{title} · WSB viewer"), nav, Main(*content)


def q1(req, k, default=None):
    v = req.query_params.get(k)
    return default if v in (None, "") else v


def qint(req, k, default=None):
    v = q1(req, k)
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------------------------
# overview
# --------------------------------------------------------------------------------------------


def runs_filtered(model=None, stage=None, bank=None, diag=False):
    out = []
    for r in D()["runs"]:
        if model and r["subject"] != model:
            continue
        if stage and r["stage"] != stage:
            continue
        if bank and r["bank"] != bank:
            continue
        if not diag and r["stage"] in ix.DIAGNOSTIC_STAGES and r["stage"] != stage:
            continue
        out.append(r)
    stage_rank = {s: i for i, (s, _) in enumerate(ix.STAGES)}
    out.sort(
        key=lambda r: (
            ix.model_label(r["subject"]).lower(),
            r["bank"] != r["subject"] and r["bank"] != ix.ORIGINAL,
            r["bank"],
            stage_rank.get(r["stage"], 99),
            r["tag"],
        )
    )
    return out


@rt("/")
def get(req):
    d = D()
    model, stage, bank = q1(req, "model"), q1(req, "stage"), q1(req, "bank")
    group, fam_sel = q1(req, "group"), q1(req, "family")
    diag = q1(req, "diag") == "1"
    view = q1(req, "view", "value")
    runs = runs_filtered(model, stage, bank, diag)
    fams = [f for f in d["families"] if any(f in r["scores"] for r in runs)]
    if group:
        fams = [f for f in fams if ix.FAMILY_GROUP.get(f, "Other") == group]
    if fam_sel:
        fams = [f for f in fams if f == fam_sel]
    groups = []
    for f in d["families"]:
        g = ix.FAMILY_GROUP.get(f, "Other")
        if g not in groups:
            groups.append(g)

    filters = Form(
        select(
            "model",
            [("", "all models")] + [(m, ix.model_label(m)) for m in d["models"]],
            model,
            "model (subject)",
        ),
        select(
            "stage",
            [("", "all stages")] + [(s, ix.STAGE_LABEL[s]) for s in d["stages"]],
            stage,
            "stage",
        ),
        select(
            "bank",
            [("", "all banks")] + [(b, d["banks"][b]["label"]) for b in d["banks"]],
            bank,
            "bank (item set)",
        ),
        select("group", [("", "all groups")] + [(g, g) for g in groups], group, "family group"),
        select(
            "family", [("", "all families")] + [(f, f) for f in d["families"]], fam_sel, "family"
        ),
        select(
            "view",
            [("value", "raw value"), ("norm", "normalized (0-1, higher=better)")],
            view,
            "cell shows",
        ),
        Label(
            Input(type="checkbox", name="diag", value="1", checked=diag, onchange=AUTO),
            "show smoke + judge-audit runs",
            cls="cb",
        ),
        method="get",
        action="/",
        cls="filters",
    )

    head = [
        Th("run (subject · stage · tag)", cls="run"),
        Th("bank"),
        Th("headline", title="headline_23 (or the run's macro) with 95% CI"),
    ]
    head += [
        Th(
            Div(A(f, href=url("/family", bank=bank or ix.ORIGINAL, fam=f))),
            cls="rot",
            title=f"{f} ({ix.FAMILY_GROUP.get(f, 'Other')})",
        )
        for f in fams
    ]
    if group or fam_sel:
        runs = [r for r in runs if any(f in r["scores"] or f in r["readouts"] for f in fams)]
    rows = []
    for r in runs:
        tds = [Td(run_link_label(r), cls="run"), Td(Small(r["bank"]))]
        h = r.get("headline")
        hci = r.get("headline_ci")
        tds.append(
            Td(
                fmt(h),
                title=(f"95% CI [{hci[0]:.3f}, {hci[1]:.3f}]" if hci else "")
                + (" " + r["headline_note"] if r.get("headline_note") else "")
                + (
                    " headline not computed; missing/incomplete: "
                    + ", ".join((r.get("head") or {}).get("missing_for_headline") or [])
                    if h is None and (r.get("head") or {}).get("missing_for_headline")
                    else ""
                ),
                cls="v",
                style=heat(h),
            )
        )
        for f in fams:
            e = r["scores"].get(f)
            if not e:
                tds.append(Td("", cls="v"))
                continue
            shown = e.get("norm") if view == "norm" else e.get("value")
            has_items = f in r["verdicts"] or f in r["readouts"]
            link = url("/family", bank=r["bank"], fam=f, run=r["id"])
            inner = [fmt(shown, None if view == "norm" else e.get("metric"))]
            if e.get("n") is not None:
                inner.append(Span(f"n={e['n']}", cls="n"))
            if e.get("complete") is False and r["stage"] != "floor":
                inner.append(Span("incomplete", cls="n"))
            tds.append(
                Td(
                    A(*inner, href=link) if has_items or r["bank"] in d["banks"] else Span(*inner),
                    cls="v",
                    style=heat(e.get("norm")),
                    title=score_title(e)
                    + ("" if has_items else " · scores only (no per-item data on this box)"),
                )
            )
        rows.append(Tr(*tds, cls="floor" if r["stage"] == "floor" else ""))

    explain = Div(
        P(
            "Each row is a run: one subject model read at one stage (prompt-only floor, inverter, distill = student/SFT, RL, J-lens, ...). "
            "Cells are the family's ",
            Code("numbers.value"),
            " (pass rate; ",
            Code("buggy_code"),
            " is a 1-10 score) with n; hover for the CI, judge and completeness. "
            "Colour = normalized score. Click a cell for the family's items with this run's verdicts and readouts.",
            cls="small muted",
        ),
        P(
            "Bank = the item set the run read: ",
            Code("qwen3.6-27b"),
            " = the frozen banks in ",
            Code("evals/"),
            " (OLens subjects other than the 4B adaptive tags were scored on these, ported), otherwise ",
            Code("adapted/<model>/"),
            ". Floors (italic) are on the adapted bank of the same model.",
            cls="small muted",
        ),
    )
    return page(
        "Overview",
        H1("WorkspaceBench scores"),
        explain,
        filters,
        Div(Table(Thead(Tr(*head)), Tbody(*rows), cls="scores"), cls="tw")
        if rows
        else P("No runs match."),
        P(Small(f"{len(runs)} runs × {len(fams)} families shown."), cls="muted"),
    )


# --------------------------------------------------------------------------------------------
# banks + runs pages
# --------------------------------------------------------------------------------------------


@rt("/banks")
def get(req):
    d = D()
    banks = list(d["banks"].values())
    fams = [f for f in d["families"] if any(f in b["families"] for b in banks)]
    head = [Th("bank", cls="run")] + [Th(Div(f), cls="rot") for f in fams]
    rows = []
    for b in banks:
        tds = [Td(Div(b["label"]), Small(b["root"], cls="muted"), cls="run")]
        for f in fams:
            e = b["families"].get(f)
            if not e:
                tds.append(Td("", cls="v"))
                continue
            n = e.get("n_items", 0)
            st = e.get("status") or ("frozen" if e.get("frozen") else "candidates")
            tds.append(
                Td(
                    A(str(n), Span(st, cls="n"), href=url("/family", bank=b["key"], fam=f)),
                    cls="v",
                    title=f"{f}: {n} items · status {st}"
                    + ("" if e.get("frozen") else " · not frozen (gate candidates shown)"),
                )
            )
        rows.append(Tr(*tds))
    return page(
        "Banks",
        H1("Item banks"),
        P(
            "Items per family per bank (status from adapted/<model>/report.json). Click a count for the family's items.",
            cls="small muted",
        ),
        Div(Table(Thead(Tr(*head)), Tbody(*rows), cls="scores"), cls="tw"),
    )


@rt("/runs")
def get(req):
    d = D()
    rows = []
    for r in runs_filtered(diag=True):
        rows.append(
            Tr(
                Td(run_link_label(r)),
                Td(Small(r["bank"])),
                Td(str(len(r["scores"]))),
                Td(str(len(r["verdicts"]))),
                Td(str(len(r["readouts"]))),
                Td(str(sum(x["n"] for x in r["readouts"].values()))),
                Td(Small(r.get("judge") or "—")),
                Td(Small(r.get("notes", "")), Div(Small(Code(r["source"])))),
            )
        )
    return page(
        "Runs",
        H1("All indexed runs"),
        Div(
            Table(
                Thead(
                    Tr(
                        Th("run"),
                        Th("bank"),
                        Th("families scored"),
                        Th("families w/ item verdicts"),
                        Th("families w/ readouts"),
                        Th("readout rows"),
                        Th("judge"),
                        Th("source"),
                    )
                ),
                Tbody(*rows),
            ),
            cls="tw",
        ),
    )


@rt("/rescan")
def post(req):
    new = INDEX.rescan()
    return page(
        "Rescan",
        H1("Rescanned"),
        P(
            f"Index rebuilt in {new['build_s']} s ({new['n_parsed']} files re-read, {new['n_files']} cached)."
        ),
        Pre(json.dumps(new["stats"], indent=1)),
        A("back to overview", href="/"),
    )


@rt("/rescan")
def get(req):
    return post(req)


# --------------------------------------------------------------------------------------------
# family page
# --------------------------------------------------------------------------------------------


def runs_for(bank: str, fam: str, diag=True):
    return [
        r
        for r in runs_filtered(bank=bank, diag=diag)
        if fam in r["scores"] or fam in r["verdicts"] or fam in r["readouts"]
    ]


@rt("/family")
def get(req):
    d = D()
    bank, fam = q1(req, "bank", ix.ORIGINAL), q1(req, "fam")
    b = d["banks"].get(bank)
    if not b or not fam:
        return page("Not found", H1("Unknown bank/family"), P(f"bank={bank} fam={fam}"))
    be = b["families"].get(fam) or {"items": [], "n_items": 0}
    diag = q1(req, "diag") == "1"
    all_runs = runs_for(bank, fam, diag=True)
    shown_pool = [r for r in all_runs if diag or r["stage"] not in ix.DIAGNOSTIC_STAGES]
    sel = req.query_params.getlist("run")
    if sel:
        cols = [r for r in all_runs if r["id"] in sel]
    else:
        cols = [r for r in shown_pool if fam in r["verdicts"] or fam in r["readouts"]]
    stage_f = q1(req, "stage")
    if stage_f:
        cols = [r for r in cols if r["stage"] == stage_f]
    model_f = q1(req, "model")
    if model_f:
        cols = [r for r in cols if r["subject"] == model_f]
    layer = qint(req, "layer")
    qtext = (q1(req, "q") or "").lower()
    vrun, vval = q1(req, "vrun"), q1(req, "v")
    show_all = q1(req, "cand") == "1"
    per = qint(req, "per", 50)
    pg = max(1, qint(req, "page", 1))

    items = [it for it in be["items"] if it["selected"] or show_all]
    # items referenced by runs but missing from the bank (e.g. bank changed since the run)
    known = {it["id"] for it in be["items"]}
    extra_ids = sorted(
        {
            i
            for r in cols
            for i in list(r["verdicts"].get(fam, {}))
            + list((r["readouts"].get(fam) or {}).get("items", {}))
            if i not in known
        }
    )
    items += [
        {
            "id": i,
            "selected": False,
            "origin": "not in bank",
            "subfamily": None,
            "target": [],
            "latent": [],
            "stim": "",
        }
        for i in extra_ids
    ]
    if qtext:
        items = [
            it
            for it in items
            if qtext in it["id"].lower()
            or qtext in " ".join(it["target"]).lower()
            or qtext in it["stim"].lower()
            or qtext in str(it.get("subfamily") or "").lower()
        ]
    if vrun and vval in ("pass", "fail", "none") and vrun in d["runs_by_id"]:
        vr = d["runs_by_id"][vrun]["verdicts"].get(fam, {})
        want = {"pass": True, "fail": False, "none": None}[vval]
        items = [it for it in items if verdict_pass_value(vr.get(it["id"]), layer) is want]
    total = len(items)
    npages = max(1, math.ceil(total / per))
    pg = min(pg, npages)
    chunk = items[(pg - 1) * per : pg * per]

    layers = sorted(
        {
            lay
            for r in cols
            for v in r["verdicts"].get(fam, {}).values()
            for lay in (v.get("by_layer") or {})
        }
        | {lay for r in cols for lay in (r["readouts"].get(fam) or {}).get("layers", [])}
    )

    # score summary
    srows = []
    for r in all_runs:
        e = r["scores"].get(fam)
        srows.append(
            Tr(
                Td(
                    Input(
                        type="checkbox",
                        name="run",
                        value=r["id"],
                        checked=r in cols,
                        form="ff",
                        onchange="document.getElementById('ff').requestSubmit()",
                    )
                ),
                Td(run_link_label(r)),
                Td(
                    fmt(e.get("value"), e.get("metric")) if e else "—",
                    style=heat(e.get("norm")) if e else "",
                    cls="v",
                ),
                Td(str(e.get("n")) if e and e.get("n") is not None else "—"),
                Td(Small(score_title(e)) if e else Small("no score", cls="muted")),
                Td(("✓" if fam in r["verdicts"] else ""), title="per-item verdicts"),
                Td(
                    ("✓ " + str(r["readouts"][fam]["n"]) if fam in r["readouts"] else ""),
                    title="readout rows",
                ),
            )
        )

    keep = dict(
        bank=bank,
        fam=fam,
        run=sel,
        stage=stage_f,
        model=model_f,
        layer=layer,
        q=q1(req, "q"),
        vrun=vrun,
        v=vval,
        cand="1" if show_all else None,
        diag="1" if diag else None,
        per=per if per != 50 else None,
    )
    filters = Form(
        Input(type="hidden", name="bank", value=bank),
        Input(type="hidden", name="fam", value=fam),
        *[Input(type="hidden", name="run", value=s) for s in sel],
        Label(
            "search (id / gold / prompt)",
            Input(type="search", name="q", value=q1(req, "q") or "", placeholder="text…"),
        ),
        select(
            "layer",
            [("", "item-level")] + [(lay, f"L{lay}") for lay in layers],
            layer if layer is not None else "",
            "verdict at layer",
        ),
        select(
            "vrun",
            [("", "— run —")]
            + [
                (r["id"], f"{ix.model_label(r['subject'])} · {r['stage']} · {r['tag'][:40]}")
                for r in cols
                if fam in r["verdicts"]
            ],
            vrun or "",
            "filter by run…",
        ),
        select(
            "v",
            [("", "any verdict"), ("pass", "pass"), ("fail", "fail"), ("none", "no verdict")],
            vval or "",
            "…verdict",
        ),
        select("per", [(25, "25"), (50, "50"), (100, "100"), (250, "250")], per, "per page"),
        Label(
            Input(type="checkbox", name="cand", value="1", checked=show_all, onchange=AUTO),
            "include non-selected candidates",
            cls="cb",
        ),
        Label(
            Input(type="checkbox", name="diag", value="1", checked=diag, onchange=AUTO),
            "smoke + judge-audit runs",
            cls="cb",
        ),
        Button("apply", type="submit"),
        method="get",
        action="/family",
        cls="filters",
        id="ff",
    )

    head = [Th("#"), Th("item"), Th("gold / latent"), Th("prompt (start)")]
    for r in cols:
        head.append(
            Th(
                Div(
                    Small(ix.model_label(r["subject"])),
                    Div(Span(r["stage"], cls="badge b-stage")),
                    Small(r["tag"][:28], cls="muted"),
                ),
                title=f"{r['label']} · {r['tag']}",
                style="min-width:70px;font-weight:normal",
            )
        )
    body = []
    for n, it in enumerate(chunk, start=(pg - 1) * per + 1):
        href = url("/item", bank=bank, fam=fam, id=it["id"], run=sel, layer=layer)
        tds = [
            Td(Small(str(n), cls="muted")),
            Td(
                A(it["id"], href=href),
                Div(
                    *([Span(str(it["subfamily"]), cls="pill")] if it.get("subfamily") else []),
                    *(
                        [Span(it["origin"], cls="pill")]
                        if it.get("origin") not in (None, "original")
                        else []
                    ),
                ),
            ),
            Td(
                *[Span(t, cls="pill gold") for t in it["target"][:3]],
                *[Span(t, cls="pill") for t in it["latent"][:2]],
            ),
            Td(Small(it["stim"][:160]), style="max-width:380px"),
        ]
        for r in cols:
            v = r["verdicts"].get(fam, {}).get(it["id"])
            has_ro = it["id"] in (r["readouts"].get(fam) or {}).get("items", {})
            tds.append(
                Td(
                    badge_for(v, layer) if fam in r["verdicts"] else "",
                    " ",
                    Span("R", cls="pill", title="readouts available") if has_ro else "",
                    cls="v",
                )
            )
        body.append(Tr(*tds))

    def plink(p, lab):
        return A(lab, href=url("/family", **{**keep, "page": p}))

    pager = Div(
        plink(1, "« first") if pg > 1 else Span("« first", cls="muted"),
        plink(pg - 1, "‹ prev") if pg > 1 else Span("‹ prev", cls="muted"),
        Span(f"page {pg} / {npages} · {total} items"),
        plink(pg + 1, "next ›") if pg < npages else Span("next ›", cls="muted"),
        plink(npages, "last »") if pg < npages else Span("last »", cls="muted"),
        cls="pager",
    )
    rep = ((b["report"].get("families") or {}).get(fam)) or {}
    return page(
        f"{fam} · {bank}",
        Div(
            A("overview", href=url("/", bank=bank)),
            " / ",
            A(b["label"], href="/banks"),
            " / ",
            Span(fam),
            cls="small",
        ),
        H1(fam, " ", Small(f"· {b['label']}", cls="muted")),
        Div(
            Span(f"{be.get('n_items', 0)} items in bank", cls="pill"),
            *([Span(f"status {rep['status']}", cls="pill")] if rep.get("status") else []),
            *(
                [
                    Span(f"{k} {rep[k]}", cls="pill")
                    for k in ("n_original", "n_original_pass", "n_new")
                    if k in rep
                ]
            ),
            *(
                [Div(Small(rep.get("change") or rep.get("note") or ""), cls="muted")]
                if (rep.get("change") or rep.get("note"))
                else []
            ),
            *(
                []
                if be.get("frozen", True)
                else [
                    Div(
                        "This family has no frozen bank for this model; showing gate candidates.",
                        cls="note",
                    )
                ]
            ),
        ),
        H2("Runs on this bank × family"),
        P(
            Small(
                "Tick runs to choose the verdict columns below (default: every run with per-item verdicts or readouts)."
            ),
            cls="muted",
        ),
        Div(
            Table(
                Thead(
                    Tr(
                        Th(""),
                        Th("run"),
                        Th("value"),
                        Th("n"),
                        Th("details"),
                        Th("item verdicts"),
                        Th("readouts"),
                    )
                ),
                Tbody(*srows),
            ),
            cls="tw",
        ),
        H2("Items"),
        filters,
        pager,
        Div(Table(Thead(Tr(*head)), Tbody(*body), cls="scores"), cls="tw"),
        pager,
    )


# --------------------------------------------------------------------------------------------
# item page
# --------------------------------------------------------------------------------------------


def item_view(b: dict, fam: str, iid: str):
    e = b["families"].get(fam) or {}
    if e.get("bank"):
        by_id, header = ix.bank_full(e["bank"])
        if iid in by_id:
            n, it = by_id[iid]
            return ix.view_item_full(it, n), header
    if e.get("gate"):
        gates = ix.gate_full(e["gate"])
        if iid in gates:
            rec = gates[iid]
            return ix.view_item_full(rec["item"], 0, rec.get("gate")), {}
    return None, {}


def summarize_cell(res) -> tuple[str, str]:
    """(short label, css class) for one cached judge cell result."""
    if not isinstance(res, dict):
        return ("—", "b-na")
    if isinstance(res.get("expressed"), bool):
        t = res.get("target") or res.get("quote") or ""
        return (
            ("✓ " + str(t)[:30]) if res["expressed"] else "✗",
            "b-pass" if res["expressed"] else "b-fail",
        )
    if isinstance(res.get("states_value"), bool):
        return (
            ("✓ " + ",".join(map(str, res.get("values") or []))) if res["states_value"] else "✗",
            "b-pass" if res["states_value"] else "b-fail",
        )
    if "claim" in res:
        return (f"claim: {res['claim']}", "b-mid")
    if "choice" in res:
        return (f"choice {res['choice']}", "b-mid")
    if "picks" in res:
        return (
            "picks " + ",".join(str(p.get("choice")) for p in res["picks"] if isinstance(p, dict)),
            "b-mid",
        )
    if "verdicts" in res and isinstance(res["verdicts"], list):
        labs = [v.get("label") for v in res["verdicts"] if isinstance(v, dict)]
        return (", ".join(map(str, labs))[:40] or "verdicts", "b-mid")
    if "samples" in res and isinstance(res["samples"], list):
        kinds = [s.get("kind") or s.get("class") for s in res["samples"] if isinstance(s, dict)]
        return (", ".join(map(str, kinds))[:40] or "samples", "b-mid")
    return ("judged", "b-mid")


def readout_text(rec: dict, field: str | None):
    if field:
        toks = rec.get(field)
        if isinstance(toks, list):
            return " · ".join(repr(t)[1:-1] for t in toks), True
        return "", True
    s = rec.get("samples")
    if isinstance(s, list):
        if s and all(isinstance(x, str) for x in s):
            return ("\n— — —\n".join(s) if len(s) > 1 else s[0]), False
        return json.dumps(s, ensure_ascii=False)[:4000], True
    return json.dumps({k: v for k, v in rec.items() if k not in ("id",)}, ensure_ascii=False)[
        :2000
    ], True


@rt("/item")
def get(req):
    d = D()
    bank, fam, iid = q1(req, "bank", ix.ORIGINAL), q1(req, "fam"), q1(req, "id")
    b = d["banks"].get(bank)
    if not b or not fam or iid is None:
        return page("Not found", H1("Unknown item"))
    layer = qint(req, "layer")
    pos_f = q1(req, "pos")
    diag = q1(req, "diag") == "1"
    maxlen = qint(req, "maxlen", 1500)
    sel = req.query_params.getlist("run")
    all_runs = runs_for(bank, fam, diag=True)
    relevant = [
        r
        for r in all_runs
        if iid in r["verdicts"].get(fam, {})
        or iid in (r["readouts"].get(fam) or {}).get("items", {})
    ]
    if sel:
        cols = [r for r in relevant if r["id"] in sel]
    else:
        cols = [r for r in relevant if diag or r["stage"] not in ix.DIAGNOSTIC_STAGES]

    view, header = item_view(b, fam, iid)

    # prev / next within bank order
    ids = [it["id"] for it in (b["families"].get(fam) or {}).get("items", []) if it["selected"]]
    nav_links = []
    if iid in ids:
        k = ids.index(iid)
        if k > 0:
            nav_links.append(
                A(
                    "‹ prev item",
                    href=url("/item", bank=bank, fam=fam, id=ids[k - 1], run=sel, layer=layer),
                )
            )
        nav_links.append(Span(f"item {k + 1} / {len(ids)}", cls="muted"))
        if k + 1 < len(ids):
            nav_links.append(
                A(
                    "next item ›",
                    href=url("/item", bank=bank, fam=fam, id=ids[k + 1], run=sel, layer=layer),
                )
            )

    # left column: the item
    left = []
    if view is None:
        left.append(
            Div(
                f"Item {iid} is not in {b['label']} / {fam} (bank may have changed since the run).",
                cls="note",
            )
        )
    else:
        plan = None
        if fam in b.get("plans", {}):
            plan = ix.plan_full(b["plans"][fam]).get(iid)
        kv = [
            (
                "origin",
                view["origin"]
                + (f" · tier {view['tier']}" if view.get("tier") is not None else ""),
            ),
            ("subfamily", view.get("subfamily")),
            (
                "gate",
                json.dumps(view["gate"], ensure_ascii=False)[:300] if view.get("gate") else None,
            ),
            ("note", view.get("note")),
            ("render (plan)", plan.get("render") if plan else header.get("eval_render_note")),
            (
                "positions (plan)",
                json.dumps(plan.get("positions"), ensure_ascii=False)[:300] if plan else None,
            ),
            ("layers (plan)", ", ".join(map(str, plan.get("layers") or [])) if plan else None),
        ]
        left += [
            H2("Gold"),
            Table(
                Tbody(
                    Tr(
                        Td("answer / target"),
                        Td(
                            *[Span(t, cls="pill gold") for t in view["target"]]
                            or [Span("—", cls="muted")]
                        ),
                    ),
                    Tr(
                        Td("latent (intermediates, bridges, concepts)"),
                        Td(
                            *[Span(t, cls="pill gold") for t in view["latent"]]
                            or [Span("—", cls="muted")]
                        ),
                    ),
                ),
                cls="kv",
            ),
            H2("Prompt / render"),
            Pre(view["stimulus"] or "(no stimulus field; see raw fields)"),
            *(
                [H3("Planned read text"), Pre(plan["text"])]
                if plan and plan.get("text") and plan.get("text") != view["stimulus"]
                else []
            ),
            Table(
                Tbody(*[Tr(Td(k), Td(str(v))) for k, v in kv if v not in (None, "", "None")]),
                cls="kv",
            ),
            Details(
                Summary("raw item fields"),
                Pre(json.dumps(view["raw"], ensure_ascii=False, indent=1)[:60000]),
            ),
        ]

    # right column: verdict table
    vrows = []
    for r in relevant:
        v = r["verdicts"].get(fam, {}).get(iid)
        if fam not in r["verdicts"]:
            continue
        rows_json = ""
        files = r["files"].get(fam) or {}
        try:
            if files.get("results"):
                rows_json = json.dumps(
                    ix.result_rows(files["results"]).get(iid, []), ensure_ascii=False, indent=1
                )
            elif files.get("audit_res"):
                rows_json = json.dumps(
                    ix.audit_rows(files["audit_res"], files["audit_key"]).get(iid, []),
                    ensure_ascii=False,
                    indent=1,
                )
        except Exception as exc:  # unreadable file: show the error, keep the page
            rows_json = f"error reading rows: {type(exc).__name__}"
        vrows.append(
            Tr(
                Td(run_link_label(r)),
                Td(badge_for(v)),
                Td(strip_for(v)),
                Td(
                    Small(
                        f"earliest L{v['earliest']}" if v and v.get("earliest") is not None else ""
                    )
                ),
                Td(Small(r["scores"].get(fam, {}).get("judge") or r.get("judge") or "")),
                Td(Details(Summary(Small("rows")), Pre(rows_json[:30000])) if rows_json else ""),
            )
        )
    right = [
        H2("Judge verdicts"),
        Div(
            Table(
                Thead(Tr(Th("run"), Th("item"), Th("per layer"), Th(""), Th("judge"), Th(""))),
                Tbody(*vrows),
            ),
            cls="tw",
        )
        if vrows
        else P("No per-item verdicts for this item on this box.", cls="muted"),
    ]

    # readouts
    all_layers, all_pos = set(), set()
    for r in cols:
        for off, ln, lay, pos in (r["readouts"].get(fam) or {}).get("items", {}).get(iid, []):
            if lay is not None:
                all_layers.add(lay)
            if pos is not None:
                all_pos.add(pos)
    cards = []
    for r in cols:
        ro = r["readouts"].get(fam)
        spans = (ro or {}).get("items", {}).get(iid, [])
        cells_idx = (r["cells"].get(fam) or {}).get("items", {}).get(iid, [])
        sp = [
            s
            for s in spans
            if (layer is None or s[2] == layer) and (pos_f in (None, "") or str(s[3]) == pos_f)
        ]
        cel = [
            c
            for c in cells_idx
            if (layer is None or c[2] == layer)
            and (pos_f in (None, "") or c[3] is None or str(c[3]) == pos_f)
        ]
        recs = ix.read_lines(ro["path"], sp[:400]) if ro else []
        crecs = ix.read_lines(r["cells"][fam]["path"], cel[:800]) if cel else []
        by_lp: dict = {}
        for c, (off, ln, lay, pos) in zip(crecs, cel[: len(crecs)]):
            by_lp.setdefault((lay, pos), []).append(c)
            by_lp.setdefault((lay, None), []).append(c)
        blocks = []
        for rec in sorted(
            recs,
            key=lambda x: (
                x.get("layer") if isinstance(x.get("layer"), int) else 0,
                x.get("pos") if isinstance(x.get("pos"), int) else 0,
            ),
        ):
            lay, pos = rec.get("layer"), rec.get("pos")
            txt, tok = readout_text(rec, ro.get("field") if ro else None)
            cl = by_lp.get((lay, pos)) or by_lp.get((lay, None)) or []
            seen, bad = set(), []
            for c in cl:
                if c.get("key") in seen:
                    continue
                seen.add(c.get("key"))
                lab, cls_ = summarize_cell(c.get("result"))
                bad.append(
                    Span(
                        lab,
                        cls=f"badge {cls_}",
                        title=json.dumps(c.get("result"), ensure_ascii=False)[:1500]
                        + f"  [{c.get('key')}]",
                    )
                )
            long_ = len(txt) > maxlen
            blocks.append(
                Div(
                    Div(
                        Span(f"L{lay}", cls="badge b-stage"),
                        Span(f"pos {pos}"),
                        *([Code(repr(rec.get("token")))] if rec.get("token") is not None else []),
                        *bad[:6],
                        cls="hd",
                    ),
                    Div(txt[:maxlen] + (" …" if long_ else ""), cls="tx tok" if tok else "tx"),
                    Details(Summary(Small("full")), Pre(txt)) if long_ else "",
                    cls="ro",
                )
            )
        if not recs and cel:
            # verdicts without readouts on the box: show the cells alone
            for c in crecs[:60]:
                lab, cls_ = summarize_cell(c.get("result"))
                blocks.append(
                    Div(
                        Div(Code(c.get("key")), Span(lab, cls=f"badge {cls_}"), cls="hd"),
                        Div(json.dumps(c.get("result"), ensure_ascii=False)[:600], cls="tx tok"),
                        cls="ro",
                    )
                )
        v = r["verdicts"].get(fam, {}).get(iid)
        cards.append(
            Div(
                H3(
                    ix.model_label(r["subject"]),
                    " ",
                    Span(ix.STAGE_LABEL.get(r["stage"], r["stage"]), cls="badge b-stage"),
                    " ",
                    badge_for(v, layer) if fam in r["verdicts"] else "",
                ),
                Div(Small(r["tag"], cls="muted")),
                *(
                    blocks
                    or [
                        P(
                            Small(
                                "no readouts at this filter"
                                if spans
                                else "no readouts on the box for this run"
                            ),
                            cls="muted",
                        )
                    ]
                ),
                Small(
                    f"{len(sp)} readout rows" + (" (first 400 shown)" if len(sp) > 400 else ""),
                    cls="muted",
                ),
                cls="card",
            )
        )

    keep = dict(bank=bank, fam=fam, id=iid)
    rfilter = Form(
        Input(type="hidden", name="bank", value=bank),
        Input(type="hidden", name="fam", value=fam),
        Input(type="hidden", name="id", value=iid),
        select(
            "layer",
            [("", "all layers")] + [(lay, f"L{lay}") for lay in sorted(all_layers)],
            layer if layer is not None else "",
            "layer",
        ),
        select(
            "pos",
            [("", "all positions")] + [(p, str(p)) for p in sorted(all_pos)],
            pos_f or "",
            "position",
        ),
        select(
            "maxlen",
            [(400, "400 chars"), (1500, "1500 chars"), (100000, "full")],
            maxlen,
            "sample length",
        ),
        Div(
            *[
                Label(
                    Input(
                        type="checkbox", name="run", value=r["id"], checked=r in cols, onchange=AUTO
                    ),
                    f"{ix.model_label(r['subject'])} · {r['stage']} · {r['tag'][:36]}",
                    cls="cb",
                )
                for r in relevant
            ],
            style="display:flex;flex-wrap:wrap;gap:4px 14px",
        ),
        Label(
            Input(type="checkbox", name="diag", value="1", checked=diag, onchange=AUTO),
            "smoke + judge-audit",
            cls="cb",
        ),
        method="get",
        action="/item",
        cls="filters",
    )

    return page(
        f"{iid} · {fam}",
        Div(
            A("overview", href=url("/", bank=bank)),
            " / ",
            A(fam, href=url("/family", bank=bank, fam=fam, run=sel, layer=layer)),
            " / ",
            Span(iid),
            " · ",
            *nav_links,
            cls="small",
        ),
        H1(iid, " ", Small(f"· {fam} · {b['label']}", cls="muted")),
        Div(Div(*left), Div(*right), cls="grid2"),
        H2("Readouts side by side"),
        P(
            Small(
                "One card per run (stage/model). Badges after the position are that cell's cached judge verdict (hover for the full judge JSON); "
                "the badge in the card title is the item-level verdict (at the chosen layer if set)."
            ),
            cls="muted",
        ),
        rfilter,
        Div(*cards, cls="cards")
        if cards
        else P("No runs with readouts or verdicts for this item.", cls="muted"),
    )


def main():
    import uvicorn

    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5077)
    a = ap.parse_args()
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
