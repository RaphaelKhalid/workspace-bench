"""Bank judge: one call per (item, layer) through ``mcjudge.run_calls``, verbatim-quote gate."""

from dataclasses import dataclass
from typing import Any

from wsbench.basic.prompts import (
    KIND_NOTE_TOKENS,
    PROMPT_VERSION,
    SCHEMA,
    SYSTEM,
    SYSTEM_SUMMARY,
    cell_lines,
    render_user,
    render_user_summary,
)
from wsbench.cache import Cache
from wsbench.digest import Collapse, gate_texts
from wsbench.family import span_in
from wsbench.judge_config import ResolvedJudge
from wsbench.llm import JudgeConfigError, Spend
from wsbench.mcjudge import Call, Preflighter, run_calls
from wsbench.readouts import Cell, Kind

CellKey = tuple[str, int]  # (item id, layer)


@dataclass(frozen=True)
class Verdict:
    expressed: bool
    target: str
    quote: str
    quote_ok: bool

    def to_json(self) -> dict[str, Any]:
        return {
            "expressed": self.expressed,
            "target": self.target,
            "quote": self.quote,
            "quote_ok": self.quote_ok,
        }


EMPTY_VERDICT = Verdict(expressed=False, target="", quote="", quote_ok=False)


@dataclass
class JudgeOutcome:
    verdicts: dict[CellKey, Verdict]
    n_unjudged: int
    n_empty: int
    n_calls: int


def quote_verified(quote: str, samples: list[str]) -> bool:
    """A positive's quote must be a span of ONE readout sample: exact, then whitespace- and
    case-normalised, then folded (punctuation, markdown and accents ignored). A quote that only
    exists across two samples never verifies; an empty quote never verifies."""
    if not quote.strip():
        return False
    return any(span_in(quote, s) for s in samples)


def _verdict(result: dict[str, Any], samples: list[str]) -> Verdict:
    quote = str(result.get("quote") or "")
    quote_ok = quote_verified(quote, samples)
    return Verdict(
        expressed=bool(result.get("expressed")) and quote_ok,
        target=str(result.get("target") or ""),
        quote=quote,
        quote_ok=quote_ok,
    )


def cell_key(key: CellKey) -> str:
    return f"{key[0]}|L{key[1]}"


def judge_cells(
    groups: dict[CellKey, list[Cell]],
    targets: dict[str, list[str]],
    *,
    family_rule: str,
    forbidden: dict[str, str],
    kind: Kind,
    judge: ResolvedJudge,
    cache: Cache,
    spend: Spend,
    preflight: Preflighter,
    concurrency: int,
    rpm: float,
    dry_run: bool,
    summary: Collapse | None = None,
    summary_note: str = "",
    prompt_version: str | None = None,
    token_note: str = KIND_NOTE_TOKENS,
) -> JudgeOutcome:
    """Judge every (item, layer) group. A group with no text is a negative without a call.
    Unjudged cells (failed calls, or every call under ``dry_run``) are counted, never scored;
    a run where every call fails raises ``JudgeConfigError``. Summary mode (``summary`` set):
    each group is one item's synthetic digest cell, judged under ``SYSTEM_SUMMARY`` with the
    quote verified against the evidence samples only (``digest.gate_texts``)."""
    verdicts: dict[CellKey, Verdict] = {}
    calls: list[Call] = []
    samples_of: dict[str, list[str]] = {}
    n_empty = 0
    for key, cells in groups.items():
        if summary is not None:
            samples = gate_texts(cells[0], summary)
        else:
            samples = [s for c in cells for s in cell_lines(c)]
        if not any(s.strip() for s in samples):
            verdicts[key] = EMPTY_VERDICT
            n_empty += 1
            continue
        k = cell_key(key)
        samples_of[k] = samples
        if summary is not None:
            user = render_user_summary(
                targets[key[0]],
                summary_note,
                cells[0],
                family_rule=family_rule,
                forbidden=forbidden.get(key[0], ""),
            )
            calls.append(Call(key=k, system=SYSTEM_SUMMARY, user=user))
            continue
        user = render_user(
            targets[key[0]],
            kind,
            cells,
            family_rule=family_rule,
            forbidden=forbidden.get(key[0], ""),
            token_note=token_note,
        )
        calls.append(Call(key=k, system=SYSTEM, user=user))
    results = run_calls(
        calls,
        schema=SCHEMA,
        judge=judge,
        prompt_version=PROMPT_VERSION if prompt_version is None else prompt_version,
        cache=cache,
        spend=spend,
        concurrency=concurrency,
        rpm=rpm,
        dry_run=dry_run,
        preflight=preflight.for_judge(judge),
        temperature=0.0,
    )
    n_unjudged = 0
    for c in calls:
        r = results.get(c.key)
        if r is None:
            n_unjudged += 1
            continue
        item_id, layer = c.key.rsplit("|L", 1)
        verdicts[(item_id, int(layer))] = _verdict(r, samples_of[c.key])
    if calls and not dry_run and n_unjudged == len(calls):
        raise JudgeConfigError(f"all {len(calls)} judge calls failed; nothing was scored")
    return JudgeOutcome(verdicts, n_unjudged=n_unjudged, n_empty=n_empty, n_calls=len(calls))
