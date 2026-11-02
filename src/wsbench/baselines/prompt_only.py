"""Prompt-only floor: stock Qwen3.6-27B given the prompt text (no activation) is asked what the
model is thinking; its summaries are judged by each family's own instrument (``wsbench judge``)
and ``freeze`` records the rates. See ``evals/baselines/README.md``."""

import datetime as dt
import json
from pathlib import Path
from typing import Any

from wsbench.registry import REPO_ROOT
from wsbench.results import decided_outcomes, read_results

FROZEN = REPO_ROOT / "evals" / "baselines" / "prompt_only.json"
# summary-mode floors (plan 0024): the same prompt-only readouts judged with aggregate=summary
FROZEN_SUMMARY = REPO_ROOT / "evals" / "baselines" / "prompt_only_summary.json"
# plan 0032 §2.11.7: the stock-Qwen summary floors, archived verbatim before the first Opus
# (po-opus-v1) freeze writes FROZEN_SUMMARY; history, never drawn
ARCHIVE_QWEN_SUMMARY = (
    REPO_ROOT / "evals" / "baselines" / "archive" / "prompt_only_summary.qwen-2026-10-29.json"
)
NOT_MEASURABLE_REFUSAL_SHARE = 0.20  # more refused ids than this: frozen as not_measurable
PO_OPUS = "po-opus-v1"
# Fable 2026-10-31: the ids Opus refused re-asked on a Sonnet fallback
# (prompt_only_opus.FALLBACK_*):
# Sonnet 5.5 for every run since 2026-11-01 (Camila); the Sonnet 5 protocol is the frozen history,
# still read and labelled, never written by a new fallback run
PO_FALLBACK = "po-opus-v1+sonnet55-fallback"
PO_FALLBACK_SONNET5 = "po-opus-v1+sonnet5-fallback"
# fallback protocol -> the fallback model's name in a floor label
PO_FALLBACKS: dict[str, str] = {PO_FALLBACK: "Sonnet 5.5", PO_FALLBACK_SONNET5: "Sonnet 5"}
# summarizer settings that do not change the instrument (throughput only)
_SUMMARIZER_IGNORED = ("concurrency", "timeout")
# Families where the prompt states the answer outright, so the stock model's summary names it
# every time (multi-concept DM scored 1.0): not a floor, never frozen or shown (Agam, 2026-09-16).
# Plan 0032 §2.11.9 ("all categories"): only jlens_concept_pr is excluded; DM and MCDM are
# measured and frozen as saturated.
EXCLUDED: dict[str, str] = {
    "jlens_concept_pr": "precision against the J-lens top-10, not a bar a lens clears",
}
SOURCE_KEYS = (
    "model",
    "base_model",
    "adapter",
    "prompt_kind",
    "prompt_template",
    "sampling",
    "layers",
)
# Families whose prompt text states or dictates the answer, so the rate is pinned high and
# bounds what the text gives away, not what a lens must clear. `report` marks these instead of
# drawing them as a bar; the comparison there is the family's own null (see the README).
SATURATED: dict[str, str] = {
    "multi_concept_directed_modulation": "the prompt dictates the concepts",
    "directed_modulation": "the instruction names the concept, and narrating it counts",
    "role_bound_association": "the scene states who did what to whom",
    "relational_multihop": "the cloze states both hops",
    "typo": "the correction is recoverable from the misspelling",
}


def judge_models() -> dict[str, str]:
    from wsbench import registry

    registry.load_all()
    return {name: spec.judge.model for name, spec in registry.FAMILIES.items()}


def summary_bases(family: str, base: str | None) -> tuple[str, ...]:
    """The prefixes a summary-mode stamp of ``family`` may start with: its judge
    ``prompt_version`` and, for a family whose summary stamp has its own base (agentic's
    ``SUMMARY_STAMP_VERSION``: Stage C reads the digest, so ``summ-c3`` replaces the native
    narrative stage), that base too. Empty for a family the registry does not know."""
    import importlib

    if base is None:
        return ()
    try:
        mod = importlib.import_module(f"wsbench.evals.{family}.prompts")
    except ImportError:
        return (base,)
    extra = getattr(mod, "SUMMARY_STAMP_VERSION", None)
    return (base, extra) if isinstance(extra, str) and extra != base else (base,)


def instrument_versions() -> dict[str, str]:
    from wsbench import registry

    registry.load_all()
    return {name: spec.judge.prompt_version for name, spec in registry.FAMILIES.items()}


def summarizer_key(config: dict[str, Any]) -> dict[str, Any] | None:
    """A result's digest settings minus the throughput-only keys: what a summary floor must share
    with the row it is drawn beside (plan 0024)."""
    summ = config.get("summarizer")
    if not isinstance(summ, dict):
        return None
    return {k: v for k, v in summ.items() if k not in _SUMMARIZER_IGNORED}


def _floor_match_key(summ: object) -> object:
    """A summarizer key as :func:`summary_floor_matches` compares it: the refusal fallback's
    *mode* is kept (``none`` / ``default`` / ``default+<model>`` decide which digests exist at
    all), only the name of the client-side refusal model after ``+`` is dropped. That model only
    re-serves digests the primary declined, and the digest cache fingerprint does not key it
    either, so the committed Sonnet 5 floors still apply to a row run with the Sonnet 5.5
    fallback (decision 2026-11-01). The stored entry keeps the full ``fallback`` string."""
    if not isinstance(summ, dict):
        return summ
    # summ_lang was removed 2026-11-01 (#208): a live row's summarizer has no ``lang`` key, while
    # the floors frozen before it carry ``lang: False``. An off label is the same instrument as
    # no label, so a falsy ``lang`` is dropped; a ``lang: True`` (labelled) digest still differs.
    if not summ.get("lang", False):
        summ = {k: v for k, v in summ.items() if k != "lang"}
    fb = summ.get("fallback")
    if not isinstance(fb, str):
        return summ
    head, sep, _model = fb.partition("+")
    return {**summ, "fallback": f"{head}+<refusal model>" if sep else head}


def default_dst(run_dir: Path) -> Path:
    """Where ``freeze`` writes ``run_dir`` by default: ``FROZEN_SUMMARY`` for a summary-mode run,
    else ``FROZEN``."""
    from wsbench import digest

    for p in sorted(run_dir.glob("*/results.json")):
        r = read_results(p.parent)
        if r.family in EXCLUDED or r.family in digest.NATIVE_ONLY:
            continue
        if r.config.get("aggregate") == "summary":
            return FROZEN_SUMMARY
    return FROZEN


def freeze(
    run_dir: Path,
    dst: Path | None = None,
    *,
    source: Path | None = None,
) -> dict[str, Any]:
    """Fold ``run_dir/<family>/results.json`` (each family's judge run on the prompt-only
    readouts) into ``dst`` as ``{family: entry}``, stamped with the judge model and prompt
    version the rate belongs to. ``source`` is the generation's ``run_config.json`` (model,
    template, sampling), copied under ``_source``. A subset run (``items`` / ``limit``) or a
    run with no value is refused (ValueError); families not in ``run_dir`` keep their entry.

    Plan 0024: the run's ``config.aggregate`` routes it. Native results go to ``FROZEN`` with
    the checks above; summary results go to ``FROZEN_SUMMARY`` (``dst`` overrides either), each
    entry also recording ``aggregate``, ``summarizer`` (:func:`summarizer_key`) and its
    ``instrument`` = the summary ``prompt_version`` as run. A ``run_dir`` mixing modes is
    refused."""
    versions = instrument_versions()
    frozen: dict[str, Any] = {}
    paths = sorted(run_dir.glob("*/results.json"))
    runs = {p: read_results(p.parent) for p in paths}
    # skip what is never frozen before the mode check: under the summary default a prompt-only
    # `run all=True` leaves the NATIVE_ONLY families native (plan 0024)
    runs = {p: r for p, r in runs.items() if r.family not in EXCLUDED}
    if any(r.config.get("aggregate") == "summary" for r in runs.values()):
        from wsbench import digest

        runs = {p: r for p, r in runs.items() if r.family not in digest.NATIVE_ONLY}
    paths = list(runs)
    modes = {r.config.get("aggregate") or "native" for r in runs.values()}
    if len(modes) > 1:
        raise ValueError(f"freeze: {run_dir} mixes aggregate modes {sorted(modes)}; freeze each")
    summary = modes == {"summary"}
    if dst is None:
        dst = default_dst(run_dir)
    # a summary run must not overwrite the native floors, nor a native run the summary ones
    other = FROZEN if summary else FROZEN_SUMMARY
    if Path(dst).resolve() == other.resolve():
        mode = "summary" if summary else "native"
        raise ValueError(f"freeze: {run_dir} is a {mode}-mode run; {dst} holds the other mode's")
    for path in paths:
        r = runs[path]
        if r.family in EXCLUDED:
            continue
        if r.config.get("items") or r.config.get("limit"):
            raise ValueError(f"freeze: {path} is a subset run, not a baseline")
        if r.value is None:
            raise ValueError(f"freeze: {path} has no value")
        if summary:
            # the instrument is the summary prompt_version as run; a summary row draws this
            # floor only when its own prompt_version and summarizer match (summary_floor_for)
            pv = str(r.config.get("prompt_version") or "")
            bases = summary_bases(r.family, versions.get(r.family))
            if "+digest-" not in pv or (bases and not any(pv.startswith(f"{b}+") for b in bases)):
                raise ValueError(
                    f"freeze: {path} was judged with prompt_version {pv!r}; the family's "
                    f"summary instrument starts with {' or '.join(map(repr, bases))}+…+digest-; "
                    "re-judge first"
                )
        elif versions.get(r.family) != r.config.get("prompt_version"):
            raise ValueError(
                f"freeze: {path} was judged with prompt_version "
                f"{r.config.get('prompt_version')!r}, the family's instrument is "
                f"{versions.get(r.family)!r}; re-judge first"
            )
        frozen[r.family] = {
            "rate": r.value,
            "saturated": r.family in SATURATED,
            "ci95": list(r.ci95) if r.ci95 else None,
            "metric": r.metric,
            "higher_is_better": r.higher_is_better,
            "n_items": r.n_items,
            "n_items_decided": r.extras.get("n_items_decided"),
            "counts": {
                k: r.counts.get(k)
                for k in (
                    "n_expected_cells",
                    "n_missing_cells",
                    "n_unjudged_cells",
                    "n_empty_cells",
                )
            },
            "judge_model": r.config.get("judge_model"),
            # plan 0032 §2.11.7: one floor serves full and lite rows (and every layer config)
            "instrument": _strip_reads(str(r.config.get("prompt_version") or "")),
            "layers_judged": r.config.get("layers_judged") or r.config.get("layers"),
            "complete": r.complete,
            **({"aggregate": "summary", "summarizer": summarizer_key(r.config)} if summary else {}),
            # audit F3: the ids decided (lens rows draw the floor on the ids both decided) and
            # the ids whose digest was never served (they count toward the refusal share)
            "decided": decided_outcomes(r.rows, r.n_items),
            "digest_unserved": sorted(
                str(row.get("id", row.get("item")))
                for row in r.rows
                if row.get("summary_state") == "unsummarized"
            ),
            "written": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        }
    if not frozen:
        raise ValueError(f"freeze: no <family>/results.json under {run_dir}")
    cfg = json.loads(Path(source).read_text(encoding="utf-8")) if source is not None else {}
    protocol = cfg.get("protocol")
    if protocol == PO_OPUS and summary and Path(dst).resolve() == FROZEN_SUMMARY.resolve():
        archive_qwen_summary()
    merged = json.loads(dst.read_text(encoding="utf-8")) if dst.exists() else {}
    if protocol == PO_OPUS:
        _po_opus_entries(frozen, cfg)
        # the entries of another reader (stock Qwen; archived above) are never kept beside the
        # Opus ones: a family the Opus run lacks has no floor rather than a stale one
        merged = {
            k: v
            for k, v in merged.items()
            if not k.startswith("_")
            and isinstance(v, dict)
            and (v.get("protocol") == PO_OPUS or v.get("protocol") in PO_FALLBACKS)
        }
        merged["_source"] = {
            k: cfg.get(k) for k in ("model", "framing", "template_sha", "draws", "protocol")
        }
        merged["_source"]["framing"] = "open_model"
    elif protocol in PO_FALLBACKS:
        _po_fallback_entries(frozen, cfg, merged)
        src = merged.get("_source") if isinstance(merged.get("_source"), dict) else {}
        merged["_source"] = {
            **src,
            "fallback": {
                k: cfg.get(k) for k in ("protocol", "reader", "primary", "fallback", "framing")
            },
        }
    elif source is not None:
        merged["_source"] = {k: cfg.get(k) for k in SOURCE_KEYS if k in cfg}
    merged.update(frozen)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(merged, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return merged


def floors(dst: Path = FROZEN) -> dict[str, dict[str, Any]]:
    """Frozen prompt-only entries whose ``instrument`` matches the family's current judge
    prompt version AND whose ``judge_model`` is the family's judge (a regex entry or one with
    no stamp passes); stale entries are dropped, so a judge change needs a re-measured floor."""
    if not dst.exists():
        return {}
    versions = instrument_versions()
    models = judge_models()
    frozen = json.loads(dst.read_text(encoding="utf-8"))
    return {
        fam: e
        for fam, e in frozen.items()
        if not fam.startswith("_")
        and fam not in EXCLUDED
        and versions.get(fam) is not None
        and e.get("instrument") == versions.get(fam)
        and e.get("judge_model") in (None, "regex", models.get(fam))
    }


def summary_floors(dst: Path = FROZEN_SUMMARY) -> dict[str, dict[str, Any]]:
    """The frozen summary-mode prompt-only entries (plan 0024). Which row an entry is drawn beside
    is decided per row by :func:`summary_floor_applies`, not here: a summary instrument is the
    prompt_version and digest settings the row actually ran with."""
    if not dst.exists():
        return {}
    frozen = json.loads(dst.read_text(encoding="utf-8"))
    return {
        fam: e
        for fam, e in frozen.items()
        if not fam.startswith("_") and fam not in EXCLUDED and isinstance(e, dict)
    }


def summary_floor_matches(entry: dict[str, Any], config: dict[str, Any]) -> bool:
    """Whether a summary row ran the floor's instrument: the same ``prompt_version``, the same
    digest settings (:func:`summarizer_key`, refusal-fallback model aside: :func:`_floor_match_key`)
    and the same judge model (plan 0024 Rev 1 #5)."""
    return (
        config.get("aggregate") == "summary"
        and entry.get("instrument") == _strip_reads(str(config.get("prompt_version") or ""))
        and _floor_match_key(entry.get("summarizer")) == _floor_match_key(summarizer_key(config))
        and entry.get("judge_model") == config.get("judge_model")
    )


def summary_floor_applies(entry: dict[str, Any], config: dict[str, Any]) -> bool:
    """A summary floor is drawn beside a summary row only when the row ran the floor's
    instrument (:func:`summary_floor_matches`) and the floor is measurable; a matching
    ``not_measurable`` floor is shown as such (:func:`floor_label`), never as a rate."""
    return summary_floor_matches(entry, config) and not entry.get("not_measurable")


def _pct(x: object) -> str:
    return f"{float(x):.0%}" if isinstance(x, int | float) else "?"


def floor_label(entry: dict[str, Any]) -> str:
    """The reader and refusal note of a prompt-only entry, as the report prints it ("" for an
    entry with no Opus protocol, e.g. a stock-Qwen one): who answered, the refusal shares, and
    for the fallback floor the Opus-alone rate when that one is measurable."""
    proto = entry.get("protocol")
    if proto == PO_OPUS:
        return f"Opus 5.5; {entry.get('n_refused', 0)} refused"
    if proto not in PO_FALLBACKS:
        return ""
    n_ids = entry.get("n_ids") or 0
    text = (
        f"Opus 5.5 + {PO_FALLBACKS[str(proto)]} fallback; "
        f"Opus refused {_pct(entry.get('refusal_rate_opus'))}, "
        f"both {entry.get('n_refused_ask', 0)}/{n_ids}"
    )
    oo = entry.get("opus_only")
    if isinstance(oo, dict):
        v = oo.get("value")
        if oo.get("not_measurable"):
            text += f"; Opus alone not measurable ({_pct(oo.get('refusal_share'))} refused)"
        elif isinstance(v, int | float):
            text += f"; Opus alone {float(v):.3f}"
    return text


def _strip_reads(pv: str) -> str:
    from wsbench.reads import strip_reads

    return strip_reads(pv)


def archive_qwen_summary() -> bool:
    """Copy the stock-Qwen ``prompt_only_summary.json`` verbatim to :data:`ARCHIVE_QWEN_SUMMARY`
    once, before the first ``po-opus-v1`` freeze overwrites it; False when already archived."""
    if ARCHIVE_QWEN_SUMMARY.exists() or not FROZEN_SUMMARY.exists():
        return False
    ARCHIVE_QWEN_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    ARCHIVE_QWEN_SUMMARY.write_bytes(FROZEN_SUMMARY.read_bytes())
    return True


def _po_opus_entries(frozen: dict[str, Any], cfg: dict[str, Any]) -> None:
    """The ``po-opus-v1`` fields of each entry: ``value`` / ``n`` / ``ci``, the refusal count
    and share, and ``not_measurable`` when more than 20% of the ids were refused. A refusal is
    an ask the model declined OR an answer whose digest was never served (audit F3: the digest
    refusals count too; one id counts once)."""
    fams = cfg.get("families") or {}
    for fam, e in frozen.items():
        st = fams.get(fam) or {}
        n_ids = int(st.get("n_ids") or 0)
        refused = {str(i) for i in st.get("refused") or []}
        digest_refused = set(e.get("digest_unserved") or []) - refused
        n_ref = len(refused) + len(digest_refused)
        share = n_ref / n_ids if n_ids else 0.0
        e.update(
            value=e["rate"],
            n=e.get("n_items_decided") if e.get("n_items_decided") is not None else e["n_items"],
            ci=e["ci95"],
            n_refused=n_ref,
            n_refused_ask=len(refused),
            n_refused_digest=len(digest_refused),
            refusal_share=share,
            protocol=PO_OPUS,
            label=f"Opus 5.5 ({n_ref} refused)",
            not_measurable=share > NOT_MEASURABLE_REFUSAL_SHARE,
        )


def _po_fallback_entries(frozen: dict[str, Any], cfg: dict[str, Any], prior: dict) -> None:
    """The fallback-protocol fields (:data:`PO_FALLBACKS`; the run's own ``cfg["protocol"]``):
    what :func:`_po_opus_entries` records, with
    the refusal share taken over the ids refused by BOTH readers plus the ids whose digest was
    never served (``not_measurable`` above 20%), the Opus-alone counts beside it, the label
    the report prints, and ``opus_only``: the ``po-opus-v1`` entry of the same family and
    instrument already in the file (freeze the Opus run first), compacted."""
    fams = cfg.get("families") or {}
    proto = str(cfg.get("protocol") or PO_FALLBACK)
    for fam, e in frozen.items():
        st = fams.get(fam) or {}
        n_ids = int(st.get("n_ids") or 0)
        both = {str(i) for i in st.get("refused_both") or []}
        digest_refused = set(e.get("digest_unserved") or []) - both
        n_ref = len(both) + len(digest_refused)
        share = n_ref / n_ids if n_ids else 0.0
        n_opus = len(st.get("refused_opus") or [])
        e.update(
            value=e["rate"],
            n=e.get("n_items_decided") if e.get("n_items_decided") is not None else e["n_items"],
            ci=e["ci95"],
            n_refused=n_ref,
            n_refused_ask=len(both),
            n_refused_digest=len(digest_refused),
            refusal_share=share,
            n_ids=n_ids,
            n_refused_opus=n_opus,
            n_served_by_fallback=len(st.get("served_by_sonnet") or []),
            refusal_rate_opus=n_opus / n_ids if n_ids else 0.0,
            protocol=proto,
            reader=cfg.get("reader"),
            label=f"Opus 5.5 + {PO_FALLBACKS[proto]} fallback ({len(both)} refused by both)",
            not_measurable=share > NOT_MEASURABLE_REFUSAL_SHARE,
        )
        old = prior.get(fam)
        if (
            isinstance(old, dict)
            and old.get("protocol") == PO_OPUS
            and old.get("instrument") == e.get("instrument")
        ):
            e["opus_only"] = {
                k: old.get(k)
                for k in ("value", "n", "ci", "refusal_share", "not_measurable", "label")
            }
            e["opus_only"]["not_measurable"] = bool(old.get("not_measurable"))
