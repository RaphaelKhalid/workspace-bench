"""``wsbench run``: judge several families concurrently, fail-soft, one preflight per model."""

import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

from wsbench import digest, llm, mc, mcjudge, reads, registry
from wsbench.baselines import text_inversion
from wsbench.family import fail
from wsbench.judge_config import ResolvedJudge, resolve
from wsbench.llm import JudgeConfigError
from wsbench.registry import EvalSpec, JudgeArgs
from wsbench.results import FamilyResult, write_results

Status = Literal["ok", "skipped", "failed"]


@dataclass
class FamilyOutcome:
    family: str
    status: Status
    result: FamilyResult | None = None
    error: str | None = None  # for skipped / failed
    exit_code: int = 0  # 3 JudgeConfigError, 2 SystemExit


class Options(Protocol):
    """The judge options ``wsbench judge`` passes down (``cli.JudgeOptions``)."""

    judge_model: str | None
    layers: list[int] | None
    items: list[str] | None
    limit: int
    allow_missing: bool
    concurrency: int
    rpm: float
    dry_run: bool
    anti_text_inversion: bool
    opt: list[str]


class RunOptions(Options, Protocol):
    """``wsbench run``'s options: the judge options plus the thread count."""

    family_workers: int


def parse_opts(pairs: Sequence[str]) -> dict[str, str]:
    """``opts=KEY=VALUE,...`` -> dict; a malformed pair, or a bad summary-mode option
    (``aggregate`` / ``summ_*``), is a usage error (exit 2). ``aggregate`` defaults to
    ``digest.DEFAULT_AGGREGATE`` (summary, plan 0024); ``opts=aggregate=native`` opts out."""
    out: dict[str, str] = {}
    for p in pairs:
        if "=" not in p:
            fail(f"opts= expects KEY=VALUE pairs, got {p!r}")
        k, v = p.split("=", 1)
        out[k.strip()] = v
    out.setdefault("aggregate", digest.DEFAULT_AGGREGATE)
    digest.validate(out)  # a bad summary-mode option exits 2 before any family starts
    return out


def warn_mode_change(out: Path, aggregate: str, family: str) -> None:
    """Warn (stderr) when ``out`` already holds a ``results.json`` of the other aggregate mode:
    rerunning a pre-0024 native out dir under the summary default overwrites it family by family,
    and the macro then drops the native rows that remain (plan 0024)."""
    prev = out / "results.json"
    if not prev.exists():
        return
    try:
        old = json.loads(prev.read_text(encoding="utf-8")).get("config", {}).get("aggregate")
    except (OSError, ValueError):
        return
    old = old or "native"
    if old != aggregate:
        print(
            f"warning: {family}: {prev} is an aggregate={old} result; this run is "
            f"aggregate={aggregate} and overwrites it (use a separate out= dir to keep both)",
            file=sys.stderr,
        )


def judge_family(
    spec: EvalSpec,
    args: Options,
    readouts: Path,
    out: Path,
    *,
    judge: ResolvedJudge,
    opts: Mapping[str, str],
) -> FamilyResult:
    """Run one family with an already-resolved judge and pre-parsed ``opts=``; write its
    ``results.json`` and print the one-line summary. Under ``anti_text_inversion`` the family's
    items are its frozen subset (``text_inversion.subset``, which exits for an ungated or stale
    family) and the result is stamped with the scope."""
    items, scope, ati = args.items, "", None
    if spec.name not in digest.NATIVE_ONLY:  # those run native under either mode
        warn_mode_change(out, opts.get("aggregate", "native"), spec.name)
    if getattr(args, "anti_text_inversion", False):
        ati = text_inversion.subset_entry(spec.name)
        items, scope = list(ati["ids"]), text_inversion.SCOPE
    jargs = JudgeArgs(
        readouts=readouts,
        out=out,
        judge=judge,
        layers=args.layers,
        items=items,
        limit=args.limit,
        allow_missing=args.allow_missing,
        concurrency=args.concurrency,
        rpm=args.rpm,
        dry_run=args.dry_run,
        aux_models=spec.judge.aux_models,
        extra=dict(opts),
        scope=scope,
    )
    result = spec.run(jargs)
    finalize_reads(jargs, result)
    if opts.get("aggregate") == "summary" and result.config.get("aggregate") != "summary":
        if spec.name not in digest.NATIVE_ONLY:
            fail(f"{spec.name}: aggregate=summary but the family ran native (not hooked)")
        result.config["aggregate"] = "native"
        result.extras["summary_mode_note"] = digest.NATIVE_ONLY[spec.name]
    if ati is not None:
        result.config["scope"] = scope
        result.extras["ati_n_bank"] = ati["n_bank"]
        result.extras["ati_judge_model"] = ati.get("judge_model")
        result.extras["ati_gate"] = ati.get("gate", "plan-0014")
        if ati.get("provisional"):  # a reduced-panel gate (decision R1-ATI): say which readers
            result.extras["ati_provisional"] = True
        if ati.get("provisional") or ati.get("status_order"):  # reduced panel, even if cleared
            result.extras["ati_panel"] = ati.get("panel")
        if "argon_decisive_items" in ati:  # cleared: argon could move no item (R1-ATI argon)
            result.extras["ati_argon_decisive_items"] = ati["argon_decisive_items"]
    path = write_results(out, result)
    spend = result.counts.get("spend_usd", 0.0) or 0.0
    print(
        f"{spec.name}: {result.metric}={result.value} n={result.n_items} "
        f"spend=${spend:.2f} pinned={result.pinned_instrument} complete={result.complete} "
        f"-> {path}"
    )
    return result


def finalize_reads(args: JudgeArgs, result: FamilyResult) -> None:
    """The load's stamps on every result, whatever the family's own config builder (plan 0032
    §2.0 / §2.6): ``config.reads`` / ``sampling`` / ``sampling_source`` / ``reader`` /
    ``reads_checked`` / ``layers_judged``; ``+reads-lite`` on a lite ``prompt_version``; the
    partial ids, missing layers and sampling diag counts in ``extras``; ``complete=False`` when
    the load left items partial or layers missing, or a summary item was truncated (stride)."""
    for k, v in reads.config_stamps(args).items():
        result.config.setdefault(k, v)
    pv = result.config.get("prompt_version")
    if isinstance(pv, str):
        result.config["prompt_version"] = reads.stamp(pv, reads.mode(args))
    result.config.setdefault("token_note_version", mc.TOKEN_NOTE_VERSION)
    for k, v in reads.extras_of(args).items():
        if v:  # only what the load found (a clean load adds nothing, as a direct call)
            result.extras.setdefault(k, v)
    summ = result.extras.get("summary")
    truncated = result.extras.get("summary_complete") is False or (
        isinstance(summ, dict) and summ.get("summary_complete") is False
    )
    if reads.incomplete(args) or truncated:
        result.complete = False
    elif not result.complete and (n := refusals_only(args, result)):
        # audit F3 ("never score a refusal as a fail"; the prompt-only 20% rule applied to lens
        # rows): a summary row whose ONLY shortfall is final digest refusals is measured on its
        # decided items; results.macro then leaves it out as "not measurable" above 20%
        result.complete = True
        result.extras["complete_with_digest_refusals"] = n


def refusals_only(args: JudgeArgs, result: FamilyResult) -> int:
    """The number of items whose digest was finally refused (or too long, or with more than
    ``digest.PARTIAL_UNDECIDED_SHARE`` of its layers unserved), when those are the
    ONLY reason ``result`` is incomplete: a summary-mode, pinned, full (not subset) run with no
    missing cells, every unjudged item a refused digest the family scores as undecided (its
    ``extras.n_items_undecided`` covers them), the shared 5% empty rule met, and no
    family-forced incompleteness (``extras.incomplete_reason``: introspection's ``scope=``
    sub-scopes, jailbreak's sub-grid regimes); else 0. A failed
    judge call (transient, a rerun retries it) keeps a run incomplete."""
    summ = result.extras.get("summary")
    summ = summ if isinstance(summ, dict) else result.extras
    refused = sum(
        int(summ.get(k) or 0)
        for k in ("n_digest_refused", "n_digest_too_long", "n_items_partial_undecided")
    )
    undecided = result.extras.get("n_items_undecided")
    c = result.counts
    ok = (
        refused > 0
        and not result.extras.get("incomplete_reason")  # a family's own sub-scope / regime
        and result.config.get("aggregate") == "summary"
        and result.pinned_instrument
        and not mcjudge.is_subset(args)
        and isinstance(undecided, int)
        and undecided >= refused
        and int(c.get("n_missing_cells") or 0) == 0
        and int(c.get("n_unjudged_cells") or 0) == refused
        and int(c.get("n_empty_cells") or 0) <= 0.05 * result.n_items
    )
    return refused if ok else 0


def readouts_path(root: Path, name: str) -> Path | None:
    """``root/<family>.jsonl`` (or a former family key's file), None when there is none."""
    path = root / f"{name}.jsonl"
    if path.exists():
        return path
    for old in registry.legacy_names(name):
        if (legacy := root / f"{old}.jsonl").exists():
            return legacy
    return None


def file_layers(path: Path) -> list[int]:
    """The layers present in a readouts file (one cheap pass, no parsing beyond the layer)."""
    from wsbench.readouts import load_readouts

    return load_readouts(path)[1].layers


def each_configs(path: Path) -> list[tuple[str, list[int] | None]]:
    """``layers=each``: the all-layer config, then one config per layer in the file."""
    return [("all", None), *((f"L{k}", [k]) for k in file_layers(path))]


def _one(
    spec: EvalSpec,
    args: Options,
    readouts: Path,
    out: Path,
    judge: ResolvedJudge,
    opts: Mapping[str, str],
) -> FamilyOutcome:
    """One family, fail-soft: ``JudgeConfigError`` -> failed/3, ``SystemExit`` (missing cells,
    refused input) -> failed/2. Anything else propagates."""
    try:
        result = judge_family(spec, args, readouts, out, judge=judge, opts=opts)
    except JudgeConfigError as e:
        print(f"{spec.name}: judge config error: {e}", file=sys.stderr)
        return FamilyOutcome(spec.name, "failed", error=str(e), exit_code=3)
    except SystemExit as e:
        text = e.code if isinstance(e.code, str) else f"exit {e.code}"
        print(f"{spec.name}: failed ({text})", file=sys.stderr)
        return FamilyOutcome(spec.name, "failed", error=text, exit_code=2)
    return FamilyOutcome(spec.name, "ok", result=result)


def _seed_preflights(judges: Mapping[str, ResolvedJudge]) -> None:
    """Preflight each distinct (model, reasoning) once, through the module attribute (so one
    monkeypatch counts the runner and the families), and seed ``mcjudge._PREFLIGHTED``."""
    seen: dict[str, ResolvedJudge] = {}
    for j in judges.values():
        seen.setdefault(mcjudge.preflight_key(j.model, j.reasoning), j)
    for k, j in seen.items():
        with mcjudge._PREFLIGHT_LOCK:
            if k in mcjudge._PREFLIGHTED:
                continue
            llm.preflight(j.model, j.reasoning)
            mcjudge._PREFLIGHTED.add(k)


def run_families(
    specs: Sequence[EvalSpec],
    args: RunOptions,
    *,
    readouts_root: Path,
    out: Path,
    env: Mapping[str, str] | None = None,
    out_of: Callable[[str], Path] | None = None,
) -> tuple[list[FamilyOutcome], int]:
    """Judge ``specs`` from ``readouts_root/<family>.jsonl`` into ``out/<family>/``.

    Order of operations: parse ``opts=`` once (a bad pair is one ``SystemExit``, nothing
    started); resolve every judge once; skip families with no readouts file; unless
    ``dry_run=True``, preflight each distinct judge model once (a failure aborts with exit 3
    before any thread starts); then run the rest in a ``ThreadPoolExecutor`` with
    ``min(len(runnable), family_workers)`` workers (1 under ``dry_run`` so printed prompts
    do not interleave). The process-wide pacer is shared, so ``rpm=`` bounds the whole run.

    Returns the outcomes in ``specs`` order and the exit code: 130 if interrupted, else 3 if
    any family hit a ``JudgeConfigError``, else 2 if any raised ``SystemExit``, else 0.
    ``KeyboardInterrupt`` cancels unstarted families (``skipped``, "interrupted") and waits for
    in-flight ones to finish their current batch (they are recorded normally)."""
    env = os.environ if env is None else env
    opts = parse_opts(args.opt)
    judges = {s.name: resolve(s.judge, flag=args.judge_model, env=env) for s in specs}
    outcomes: dict[str, FamilyOutcome] = {}
    runnable: list[tuple[EvalSpec, Path]] = []
    for s in specs:
        readouts = readouts_root / f"{s.name}.jsonl"
        if not readouts.exists():
            # a readout file written under a former family key (registry.LEGACY_FAMILY_NAMES)
            for old in registry.legacy_names(s.name):
                if (legacy := readouts_root / f"{old}.jsonl").exists():
                    print(f"{s.name}: no {readouts.name}, reading legacy {legacy.name}")
                    readouts = legacy
                    break
        if not readouts.exists():
            msg = f"no readouts at {readouts}"
            print(f"{s.name}: skipped ({msg})")
            outcomes[s.name] = FamilyOutcome(s.name, "skipped", error=msg)
            continue
        if getattr(args, "anti_text_inversion", False):
            # checked before any preflight: an out-of-scope family is skipped, a stale or
            # missing subset entry fails (re-gate); neither spends a call
            try:
                text_inversion.subset_entry(s.name)
            except text_inversion.NotInScope as e:
                print(f"{s.name}: skipped ({e.code})")
                outcomes[s.name] = FamilyOutcome(s.name, "skipped", error=str(e.code))
                continue
            except SystemExit as e:
                print(f"{s.name}: failed ({e.code})", file=sys.stderr)
                outcomes[s.name] = FamilyOutcome(s.name, "failed", error=str(e.code), exit_code=2)
                continue
        runnable.append((s, readouts))
    # a family with a deterministic scorer of record makes no call unless opts=judge=mc
    needs_llm = [s for s, _r in runnable if not s.scorer or opts.get("judge") == "mc"]
    to_preflight: dict[str, ResolvedJudge] = {s.name: judges[s.name] for s in needs_llm}
    if opts.get("aggregate") == "summary":  # every family's digest model (plan 0020)
        for s, _r in runnable:
            to_preflight[f"digest:{s.name}"] = digest.preflight_judge(opts, s.judge.aux_models)
    if to_preflight and not args.dry_run:
        try:
            _seed_preflights(to_preflight)
        except JudgeConfigError as e:
            print(f"judge config error: {e}", file=sys.stderr)
            return [], 3

    workers = 1 if args.dry_run else max(1, min(len(runnable), args.family_workers))
    interrupted = False
    executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="wsbench-family")
    futures: dict[Future[FamilyOutcome], str] = {}
    try:
        for s, readouts in runnable:
            dest = out_of(s.name) if out_of is not None else out / s.name
            fut = executor.submit(_one, s, args, readouts, dest, judges[s.name], opts)
            futures[fut] = s.name
        for fut in as_completed(futures):
            oc = fut.result()
            outcomes[oc.family] = oc
    except KeyboardInterrupt:
        interrupted = True
        print("interrupted: cancelling unstarted families", file=sys.stderr)
        # unstarted families are cancelled; in-flight ones cannot be and finish their batch
        executor.shutdown(wait=True, cancel_futures=True)
        for fut, name in futures.items():
            if fut.done() and not fut.cancelled() and fut.exception() is None:
                outcomes[name] = fut.result()
        for s, _readouts in runnable:
            outcomes.setdefault(s.name, FamilyOutcome(s.name, "skipped", error="interrupted"))
    except BaseException:
        # an unexpected worker exception propagates (plan), but must not leave the other
        # families spending in the background
        executor.shutdown(wait=False, cancel_futures=True)
        raise
    else:
        executor.shutdown(wait=True)

    ordered = [outcomes[s.name] for s in specs]
    if interrupted:
        code = 130
    elif any(o.exit_code == 3 for o in ordered):
        code = 3
    elif any(o.exit_code == 2 for o in ordered):
        code = 2
    else:
        code = 0
    return ordered, code


def _iso(t: datetime) -> str:
    return t.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def run_manifest(
    outcomes: Sequence[FamilyOutcome],
    *,
    started: datetime,
    finished: datetime,
    args: Options,
    out: Path,
    readouts_root: Path,
    env: Mapping[str, str] | None = None,
) -> dict:
    """The ``run.json`` payload: per-family status plus the judge overrides in force."""
    env = os.environ if env is None else env
    families: dict[str, dict] = {}
    for o in outcomes:
        d: dict = {"status": o.status}
        if o.error is not None:
            d["error"] = o.error
        if o.result is not None:
            r = o.result
            d.update(
                results_path=str(out / o.family / "results.json"),
                value=r.value,
                complete=r.complete,
                pinned_instrument=r.pinned_instrument,
                spend_usd=r.counts.get("spend_usd"),
            )
            if "n_calls" in r.extras:
                d["n_calls"] = r.extras["n_calls"]
        families[o.family] = d
    manifest: dict = {
        "started": _iso(started),
        "finished": _iso(finished),
        "families": families,
        "judge_overrides": {"flag": args.judge_model, "env": env.get("WSBENCH_JUDGE_MODEL")},
        # the effective aggregate mode (plan 0024: summary unless opts=aggregate=native)
        "aggregate": parse_opts(list(getattr(args, "opt", None) or []))["aggregate"],
        "readouts_root": str(readouts_root),
    }
    if getattr(args, "hb_method", ""):  # plan 0040: `wsbench report` prints its HB index
        manifest["hb_method"] = args.hb_method
    return manifest
