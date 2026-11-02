"""The HallucinationBench index, reported in WorkspaceBench (plan 0040).

The ``hallucination`` family left WorkspaceBench: HallucinationBench
(github.com/camila-blank/hallucination-bench) replaced it. WSB reports HB's index instead, from
a frozen vendored copy, ``evals/hallucinationbench/index.json``. That file is written only by
``scripts/vendor_hb_index.py``, and only from an ``hindex-v6`` index (HB's official ``hbench
index``, plan 0022) built at the pinned HB sha.

- The index is a weighted share of claims hallucinated, so lower is better.
- One number per (method, layer) (decision Q6): ``full`` when the method has it (every HB
  family), else ``matched`` (every family but sibling), labelled ``matched (no sibling)``.
- It is a separate number. It never enters the WSB macro.

``evals/hallucinationbench/methods.json`` maps a WSB arm label to an HB method. An arm whose
checkpoint is not verified identical to an HB method is listed under ``not_measured`` with the
reason. It is never aliased.
"""

import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from wsbench.registry import REPO_ROOT

HB_DIR = REPO_ROOT / "evals" / "hallucinationbench"
INDEX = HB_DIR / "index.json"
METHODS = HB_DIR / "methods.json"
# plan 0057: HB's official index (the `hbench index` default since HB plan 0022). Q6 still
# holds: benign_roleplay is not an index family; v6 changed the overrefusal unit, not the
# family set.
VERSION = "hindex-v6"
NOT_MEASURED = "not measured on HallucinationBench"
FULL = "full"
MATCHED = "matched (no sibling)"
# the campaign arms (SHARED_API "Producer / run"): the only keys methods.json may carry
CAMPAIGN_ARMS = ("s3d-rl600", "jlens", "mlnla-rl2-2000", "final-olens-rl600-x4")


def load(path: Path | None = None) -> dict[str, Any]:
    """The vendored index (``evals/hallucinationbench/index.json``)."""
    d: dict[str, Any] = json.loads((path or INDEX).read_text(encoding="utf-8"))
    return d


def methods(path: Path | None = None) -> dict[str, Any]:
    """``{"methods": {arm: hb method}, "not_measured": {arm: reason}}`` from methods.json."""
    d = json.loads((path or METHODS).read_text(encoding="utf-8"))
    return {"methods": dict(d.get("methods", {})), "not_measured": dict(d.get("not_measured", {}))}


def headline(row: Mapping[str, Any]) -> tuple[str, float, tuple[float, float]]:
    """The row's one number (decision Q6): ``("full", v, ci)`` when the row has ``full``, else
    ``("matched (no sibling)", v, ci)``. A row with neither raises ``ValueError``."""
    for key, kind in (("full", FULL), ("matched", MATCHED)):
        cell = row.get(key)
        if isinstance(cell, Mapping) and cell.get("v") is not None:
            lo, hi = cell["ci"]
            return kind, float(cell["v"]), (float(lo), float(hi))
    raise ValueError(f"{row.get('method')} L{row.get('layer')}: no full or matched index value")


def _has_headline(row: Mapping[str, Any]) -> bool:
    try:
        headline(row)
    except ValueError:
        return False
    return True


def lookup(
    method: str, layers: Iterable[int], *, index: Mapping[str, Any] | None = None
) -> dict[str, Any] | None:
    """The HB rows of ``method`` at ``layers``, each with its :func:`headline`.

    Returns ``None`` when the method is unknown or none of the layers has an index value (the
    caller prints :data:`NOT_MEASURED`; :func:`missing_reason` says why). Layers the method does
    not have are listed under ``missing_layers`` and left out of the mean. With more than one
    layer found, ``layer_mean`` holds, per headline kind, the unweighted mean of the per-layer
    values over the layers of that kind (no CI), computed here from the vendored rows."""
    idx = load() if index is None else index
    want = sorted({int(x) for x in layers})
    by_layer = {int(r["layer"]): r for r in idx.get("rows", []) if r.get("method") == method}
    found, missing = [], []
    for layer in want:
        row = by_layer.get(layer)
        if row is None or not _has_headline(row):
            missing.append(layer)
            continue
        kind, v, ci = headline(row)
        found.append({"layer": layer, "kind": kind, "value": v, "ci": list(ci)})
    if not found:
        return None
    out: dict[str, Any] = {
        "method": method,
        "version": idx.get("version"),
        "hb_sha": idx.get("hb_sha"),
        "rows": found,
        "missing_layers": missing,
    }
    if len(found) > 1:
        means = []
        for kind in (FULL, MATCHED):
            vals = [r["value"] for r in found if r["kind"] == kind]
            if vals:
                means.append({"kind": kind, "value": sum(vals) / len(vals), "n_layers": len(vals)})
        out["layer_mean"] = means
    return out


def missing_reason(
    method: str, layers: Iterable[int], *, index: Mapping[str, Any] | None = None
) -> str:
    """Why :func:`lookup` found nothing: an unknown method, or none of the layers measured."""
    idx = load() if index is None else index
    have = sorted(int(r["layer"]) for r in idx.get("rows", []) if r.get("method") == method)
    if not have:
        return f"{NOT_MEASURED} (no method {method!r} in hindex @ {idx.get('hb_sha')})"
    want = ",".join(str(x) for x in sorted(set(layers))) or "none"
    return f"{NOT_MEASURED} (method {method!r} has layers {have}, the run judged {want})"


def _pct(v: float) -> str:
    return f"{100 * v:.1f}%"


def _ci(ci: Sequence[float]) -> str:
    return f"[{100 * ci[0]:.1f}, {100 * ci[1]:.1f}]"


def resolve_method(
    *,
    arg: str = "",
    run_json: Mapping[str, Any] | None = None,
    mapping: Mapping[str, Any] | None = None,
) -> tuple[str | None, str]:
    """The run's HB method, in order: the ``hb_method=`` argument, then ``run.json["hb_method"]``,
    then ``methods.json[basename of run.json["readouts_root"]]``. Returns ``(method, source)``;
    ``(None, reason)`` for an arm listed as not measured, ``(None, "")`` when nothing applies."""
    if arg:
        return arg, "hb_method="
    rj = run_json or {}
    if rj.get("hb_method"):
        return str(rj["hb_method"]), "run.json"
    root = rj.get("readouts_root")
    if not root:
        return None, ""
    arm = Path(str(root)).name
    m = methods() if mapping is None else mapping
    if arm in m["methods"]:
        return str(m["methods"][arm]), f"methods.json[{arm}]"
    if arm in m["not_measured"]:
        return None, f"{arm}: {NOT_MEASURED} ({m['not_measured'][arm]})"
    return None, ""


def report_block(
    method: str | None,
    layers: Sequence[int],
    *,
    reason: str = "",
    index: Mapping[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """The ``summary.md`` block and the ``"hallucinationbench"`` JSON payload of one run."""
    idx = load() if index is None else index
    head = f"HallucinationBench index ({idx.get('version')} @ {str(idx.get('hb_sha'))[:7]}, "
    head += "lower is better)"
    base: dict[str, Any] = {
        "version": idx.get("version"),
        "hb_sha": idx.get("hb_sha"),
        "hb_repo": idx.get("hb_repo"),
        "method": method,
        "layers": list(layers),
        "in_macro": False,
    }
    if method is None:
        text = f"{head}: {reason or NOT_MEASURED}"
        return text + "\n", {**base, "measured": False, "reason": reason or NOT_MEASURED}
    if not layers:
        why = "the run's results carry no config.layers_judged"
        return f"{head}: {method}: {why}\n", {**base, "measured": False, "reason": why}
    got = lookup(method, layers, index=idx)
    if got is None:
        why = missing_reason(method, layers, index=idx)
        return f"{head}: {method}: {why}\n", {**base, "measured": False, "reason": why}
    rows = got["rows"]
    if len(layers) == 1:
        r = rows[0]
        text = f"{head}: {method} {r['kind']} {_pct(r['value'])} {_ci(r['ci'])} at L{r['layer']}"
        return text + "\n", {**base, "measured": True, **got}
    lines = [f"{head}, {method}:"]
    lines += [f"- L{r['layer']}: {r['kind']} {_pct(r['value'])} {_ci(r['ci'])}" for r in rows]
    for m in got.get("layer_mean", []):
        lines.append(
            f"- layer mean ({m['n_layers']} layers, {m['kind']}, unweighted, no CI): "
            f"{_pct(m['value'])}"
        )
    if got["missing_layers"]:
        lines.append(f"- {NOT_MEASURED} at L" + ", L".join(map(str, got["missing_layers"])))
    return "\n".join(lines) + "\n", {**base, "measured": True, **got}


def run_layers(configs: Iterable[Mapping[str, Any]]) -> list[int]:
    """The run's layers: the union of its results' ``config.layers_judged``."""
    out: set[int] = set()
    for cfg in configs:
        for x in cfg.get("layers_judged") or []:
            out.add(int(x))
    return sorted(out)
