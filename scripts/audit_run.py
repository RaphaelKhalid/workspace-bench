"""Mechanical audit of a judged run (gpu.md G9; plan 0032 late fix 2: the frozen lite rule).

    python scripts/audit_run.py --judged <run dir> [--json]

Per ``<run dir>/<family>/results.json`` it checks, and prints a table:
- ``config.aggregate == "summary"`` (``jlens_concept_pr``: native);
- ``config.sampling_source == "declared"`` and ``config.reads_checked`` is ``sidecar`` (or
  ``prompt_only`` for the floor run); a ``-dmo-*`` dir is a diagnostic control arm, exempt;
- ``prompt_version`` equals ``digest.prompt_version(<registry PV>, …)`` plus ``+reads-lite`` for
  a lite run (a superseded instrument never reaches the site);
- a lite run's ``config.lite_rule`` equals the frozen lite rule of the plan (``reads.lite_rule_of``
  over ``reads.specs``; ``scripts/lite_site_table.py --write`` freezes it);
- ``n_readouts_in == n_readouts_bundled`` and ``n_truncated_items == 0`` (no readout dropped);
- ``complete`` for a ``layers=<L>`` run.
It prints ``extras.digest_served_by``, ``n_unverified_bullet`` and ``n_bare_mention_pass``, and
(round 3; plan 0046 moral) the two instrument matches, reported, never failed (a PV change after
gpu R6 / R8 means "no floor" / "re-gate", not a broken run): ``floor`` = whether the frozen
summary prompt-only floor's ``instrument`` equals ``strip_reads(prompt_version)``
(``prompt_only.summary_floor_applies``), ``ati`` = whether a native row's ``prompt_version``
equals the frozen ATI entry's ``instrument``.
Exit 1 when any check fails."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

NATIVE = {"jlens_concept_pr"}


def _probe(cfg: dict[str, Any]) -> Any:
    from wsbench import digest

    keys = ("variant", "render", "max_items", "max_rare", "numbers", "overflow", "lang")
    summ = cfg.get("summarizer") or {}
    extra = {"aggregate": "summary"}
    names = {
        "variant": "summ_variant",
        "render": "summ_render",
        "max_items": "summ_max",
        "max_rare": "summ_rare",
        "numbers": "summ_numbers",
        "overflow": "summ_overflow",
    }
    for k in keys:
        if k in names and k in summ and summ[k] not in (None, ""):
            extra[names[k]] = str(summ[k])
    # an old run's summ_lang=1 is not replayed: the option was removed on 2026-11-01
    return digest._probe(extra)


def audit_family(fam_dir: Path) -> dict[str, Any]:
    from wsbench import digest, reads, registry

    res = json.loads((fam_dir / "results.json").read_text(encoding="utf-8"))
    family = registry.canonical(res["family"])
    cfg = res.get("config", {})
    extras = (res.get("numbers") or {}).get("extras", {}) or {}
    summ = extras.get("summary") if isinstance(extras.get("summary"), dict) else extras
    diag = "-dmo-" in str(fam_dir)
    problems: list[str] = []
    try:
        spec = registry._spec_for_bank(family)  # also with an emptied registry
    except SystemExit:
        spec = None
    mode = cfg.get("reads", "full")
    if family not in NATIVE and cfg.get("aggregate") != "summary":
        problems.append(f"aggregate={cfg.get('aggregate')!r}")
    if not diag:
        if cfg.get("reads_checked") not in ("sidecar", "prompt_only"):
            problems.append(f"reads_checked={cfg.get('reads_checked')!r}")
        if cfg.get("sampling_source") != "declared" and cfg.get("reads_checked") != "prompt_only":
            problems.append(f"sampling_source={cfg.get('sampling_source')!r}")
    if spec is not None and cfg.get("aggregate") == "summary":
        want = reads.stamp(digest.prompt_version(spec.judge.prompt_version, _probe(cfg)), mode)
        if not str(cfg.get("prompt_version", "")).startswith(spec.judge.prompt_version):
            problems.append(f"prompt_version {cfg.get('prompt_version')!r} != registry")
        elif cfg.get("prompt_version") != want:
            problems.append(f"prompt_version {cfg.get('prompt_version')!r} != {want!r}")
    if mode == "lite":
        want_rule = reads.lite_rule_of(reads.specs(family))
        got = cfg.get("lite_rule")
        if got is None:
            problems.append("lite run without config.lite_rule")
        elif json.loads(got) and not set(map(json.dumps, json.loads(got))) <= set(
            map(json.dumps, json.loads(want_rule))
        ):
            problems.append(f"lite_rule {got} is not the frozen plan rule {want_rule}")
    if isinstance(summ, dict) and "n_readouts_in" in summ:
        if summ["n_readouts_in"] != summ.get("n_readouts_bundled"):
            problems.append("readouts dropped from the digest")
        if summ.get("n_truncated_items"):
            problems.append(f"n_truncated_items={summ['n_truncated_items']}")
    if cfg.get("layers") and not res.get("complete"):
        problems.append("a layers= run is incomplete")
    floor, ati = _instrument_matches(family, cfg)
    return {
        "family": family,
        "dir": str(fam_dir),
        "diagnostic": diag,
        "ok": not problems,
        "problems": problems,
        "digest_served_by": (summ or {}).get("digest_served_by")
        if isinstance(summ, dict)
        else None,
        "n_unverified_bullet": extras.get("n_unverified_bullet"),
        "n_bare_mention_pass": extras.get("n_bare_mention_pass"),
        "floor": floor,
        "ati": ati,
    }


def _instrument_matches(family: str, cfg: dict[str, Any]) -> tuple[str, str]:
    """(floor, ati) status strings: ``applies`` / ``no floor (<instrument>)`` / ``none`` for a
    summary row; ``ok`` / ``re-gate (<instrument>)`` / ``none`` for a native row's ATI entry."""
    from wsbench import reads
    from wsbench.baselines import prompt_only, text_inversion

    pv = str(cfg.get("prompt_version") or "")
    floor = ati = "n/a"
    if cfg.get("aggregate") == "summary":
        e = prompt_only.summary_floors().get(family)
        if e is None:
            floor = "none"
        elif prompt_only.summary_floor_applies(e, cfg):
            floor = "applies"
        else:
            floor = f"no floor ({e.get('instrument')} != {reads.strip_reads(pv)})"
    else:
        frozen = json.loads(text_inversion.FROZEN.read_text(encoding="utf-8"))
        e = frozen.get(family) if isinstance(frozen.get(family), dict) else None
        if e is None:
            ati = "none"
        else:
            ati = "ok" if e.get("instrument") == pv else f"re-gate ({e.get('instrument')} != {pv})"
    return floor, ati


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--judged", required=True, nargs="+")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    rows = [
        audit_family(p.parent) for d in a.judged for p in sorted(Path(d).glob("**/results.json"))
    ]
    if a.json:
        print(json.dumps(rows, indent=1))
    else:
        for r in rows:
            mark = "ok  " if r["ok"] else "FAIL"
            tag = " (diagnostic control arm)" if r["diagnostic"] else ""
            print(f"{mark} {r['family']}{tag}: {'; '.join(r['problems']) or '—'}")
            print(f"     floor: {r['floor']}; ati: {r['ati']}; "
                  f"n_unverified_bullet: {r['n_unverified_bullet']}")  # fmt: skip
    return 0 if all(r["ok"] for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
