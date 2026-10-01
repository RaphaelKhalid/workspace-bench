"""The port contract: how one WorkspaceBench judge schema becomes Jev typed questions.

A port turns ONE original judge prompt ``(system, user, schema)`` into ONE Jev request
``(state, questions)`` and turns Jev's typed answers back into a dict that satisfies the
original JSON schema, so the family's own code (parsing, verification, pass rules, metrics)
runs unchanged. That is the fidelity principle: the only thing swapped is the model call.

Rules every port follows (see ../../../PORTING.md):
  1. The state carries the ORIGINAL system and user text verbatim (``verbatim_state``).
     Jev sees exactly what the judge of record saw — no more (no gold leakage), no less.
  2. Question instructions and criteria are lifted verbatim from the prompt wherever possible
     (the question sentence, the option lines, the rule sentences for that decision).
  3. Fields Jev cannot produce (free-text quotes, rationales, extracted numbers) are filled
     deterministically from the readout text (see helpers below) or left empty, and the port
     documents what the family does with them.
  4. Every probability Jev returns is kept under ``_jev`` in the result for calibration.
"""

from __future__ import annotations

import difflib
import hashlib
import random
import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass
class JevCall:
    state: dict
    questions: dict
    ctx: dict = field(default_factory=dict)  # whatever parse() needs (options, readout, ...)


@dataclass
class Direct:
    """A result produced without a Jev call (e.g. a deterministic screen or an empty readout)."""

    result: dict | None


class Port:
    """Subclass per judge schema. ``schema_names`` are the ``schema["name"]`` values handled;
    ``required`` (optional) disambiguates two schemas that share a name."""

    name: str = "base"
    schema_names: tuple[str, ...] = ()
    required: frozenset[str] | None = None
    compare_fields: tuple[str, ...] = ()  # results.json row fields to compare with the judge of record

    def matches(self, schema: dict) -> bool:
        if schema.get("name") not in self.schema_names:
            return False
        if self.required is None:
            return True
        req = frozenset(schema.get("schema", {}).get("required", []))
        return req == self.required

    def build(self, system: str, user: str, schema: dict) -> JevCall | Direct:
        raise NotImplementedError

    def parse(self, answers: dict, call: JevCall, schema: dict) -> dict | None:
        raise NotImplementedError


# ---------------------------------------------------------------- state


def verbatim_state(system: str, user: str, **extra: str) -> dict:
    """The judge of record's exact inputs. Keys are stable so the Jev cache is stable."""
    st = {"judge_instructions": system, "judge_input": user}
    st.update(extra)
    return st


# ---------------------------------------------------------------- questions


def choice(instructions: str, options: dict[str, str]) -> dict:
    return {"type": "choice", "instructions": instructions, "criteria": dict(options)}


def noul(instructions: str, true: str, false: str) -> dict:
    return {"type": "noul", "instructions": instructions, "criteria": {"true": true, "false": false}}


def score(instructions: str, levels: Sequence[str]) -> dict:
    return {"type": "score", "instructions": instructions, "criteria": list(levels)}


def _seed(*parts: Any) -> int:
    h = hashlib.sha256("\x1f".join(map(str, parts)).encode("utf-8", "replace")).digest()
    return int.from_bytes(h[:8], "big")


def choice_variants(
    qid: str, instructions: str, options: dict[str, str], k: int = 1, seed: str = ""
) -> dict[str, dict]:
    """``k`` copies of one Choice question with the option ORDER permuted (variant 0 keeps the
    original order). Option keys never change, so answers are averaged by key with
    :func:`merge_choice`. Costs ~80 input tokens per extra variant; the state is billed once."""
    out = {f"{qid}__v0": choice(instructions, options)}
    keys_ = list(options)
    for v in range(1, k):
        order = keys_[:]
        random.Random(_seed(seed, qid, v)).shuffle(order)
        out[f"{qid}__v{v}"] = choice(instructions, {o: options[o] for o in order})
    return out


def merge_choice(answers: dict, qid: str) -> dict[str, float] | None:
    """Average the probability maps of every ``{qid}__v*`` answer. None if none landed."""
    maps = [
        a.get("probabilities") or {}
        for key, a in answers.items()
        if (key == qid or key.startswith(f"{qid}__v")) and isinstance(a, dict)
    ]
    maps = [m for m in maps if m]
    if not maps:
        return None
    opts = set().union(*maps)
    return {o: sum(float(m.get(o, 0.0)) for m in maps) / len(maps) for o in opts}


def merge_noul(answers: dict, qid: str) -> float | None:
    vals = [
        float(a["noul"])
        for key, a in answers.items()
        if (key == qid or key.startswith(f"{qid}__v")) and isinstance(a, dict) and "noul" in a
    ]
    return sum(vals) / len(vals) if vals else None


def merge_score(answers: dict, qid: str) -> dict[str, float] | None:
    return merge_choice(answers, qid)


def argmax(probs: dict[str, float], order: Sequence[str] | None = None) -> str:
    """Highest-probability key; ties broken by ``order`` (the original option order)."""
    keys_ = list(order) if order else sorted(probs)
    return max(keys_, key=lambda k: (probs.get(k, 0.0), -keys_.index(k)))


def expected_level(probs: dict[str, float]) -> float:
    return sum(int(k) * p for k, p in probs.items()) / (sum(probs.values()) or 1.0)


# ---------------------------------------------------------------- parsing the original prompt

_LISTING = re.compile(r"^\s{2}(\d+)\. (.*)$")


def parse_listing(text: str) -> list[str]:
    """Options rendered by ``wsbench.mc.listing`` ("  1. opt" per line), in order. Returns the
    LAST contiguous listing block in ``text`` (the question's options)."""
    blocks: list[list[str]] = []
    cur: list[str] = []
    expect = 1
    for line in text.splitlines():
        m = _LISTING.match(line)
        if m and int(m.group(1)) == expect:
            cur.append(m.group(2))
            expect += 1
            continue
        if m and int(m.group(1)) == 1:
            if cur:
                blocks.append(cur)
            cur, expect = [m.group(2)], 2
            continue
        if cur:
            blocks.append(cur)
            cur, expect = [], 1
    if cur:
        blocks.append(cur)
    return blocks[-1] if blocks else []


def between(text: str, start: str, end: str | None = None) -> str:
    """Substring after the first ``start`` and before the next ``end`` (or to the end)."""
    i = text.find(start)
    if i < 0:
        return ""
    i += len(start)
    if end is None:
        return text[i:]
    j = text.find(end, i)
    return text[i:] if j < 0 else text[i:j]


# ---------------------------------------------------------------- deterministic field fillers


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    for a, b in (("‘", "'"), ("’", "'"), ("“", '"'), ("”", '"')):
        s = s.replace(a, b)
    return "".join(c for c in s if not unicodedata.combining(c)).casefold()


_WORD = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def best_quote(readout: str, target: str, max_words: int = 12) -> str:
    """The verbatim span of ``readout`` (<= ``max_words`` words, within one line) that best
    matches ``target`` by token overlap then difflib ratio. "" if nothing overlaps. Always a
    substring of ``readout`` so verbatim-quote checks in the family code behave as they would
    for a judge that quoted faithfully."""
    if not readout.strip() or not target.strip():
        return ""
    tgt = {_fold(w) for w in re.findall(r"\w+", target) if len(w) > 2}
    best, best_key = "", (0.0, 0.0)
    for line in readout.splitlines():
        spans = [(m.start(), m.end()) for m in re.finditer(r"\S+", line)]
        for i in range(len(spans)):
            for j in range(i, min(len(spans), i + max_words)):
                s = line[spans[i][0] : spans[j][1]]
                words = {_fold(w) for w in re.findall(r"\w+", s)}
                ov = len(words & tgt) / (len(tgt) or 1)
                if ov == 0:
                    continue
                key = (ov, difflib.SequenceMatcher(None, _fold(s), _fold(target)).ratio())
                if key > best_key:
                    best, best_key = s, key
    return best.strip(" \t-*•")


_NUM = re.compile(r"(?<![\d.])-?\d{1,6}(?:\.\d+)?(?![\d.]\d)")
_CN = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def _cn_to_int(s: str) -> int | None:
    """Chinese numerals up to 99 (十四 = 14, 二十三 = 23, 十 = 10)."""
    if not s:
        return None
    if "十" in s:
        a, _, b = s.partition("十")
        tens = _CN.get(a, 1) if a else 1
        ones = _CN.get(b, 0) if b else 0
        if (a and a not in _CN) or (b and b not in _CN):
            return None
        return tens * 10 + ones
    if len(s) == 1 and s in _CN:
        return _CN[s]
    return None


_EN = {
    w: i
    for i, w in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
        "fifteen sixteen seventeen eighteen nineteen twenty".split()
    )
}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}


def numbers_in(text: str, integers_only: bool = False) -> list[float]:
    """Every number the text writes: digits, English number words (to 99), Chinese numerals
    (to 99). Deduplicated, in order of first appearance."""
    seen: list[float] = []

    def add(x: float) -> None:
        if integers_only and x != int(x):
            return
        if x not in seen:
            seen.append(x)

    for m in _NUM.finditer(text):
        try:
            add(float(m.group(0)))
        except ValueError:
            pass
    low = text.lower()
    for m in re.finditer(r"\b(twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)[- ]?(one|two|three|four|five|six|seven|eight|nine)?\b", low):
        add(float(_TENS[m.group(1)] + (_EN[m.group(2)] if m.group(2) else 0)))
    for m in re.finditer(r"\b(" + "|".join(_EN) + r")\b", low):
        add(float(_EN[m.group(1)]))
    for m in re.finditer(r"[零一二两三四五六七八九十]+", text):
        v = _cn_to_int(m.group(0))
        if v is not None:
            add(float(v))
    return seen


def fmt_num(x: float) -> str:
    return str(int(x)) if x == int(x) else str(x)


def jev_meta(answers: dict, **extra: Any) -> dict:
    """What goes under ``_jev`` in a ported result: every raw answer plus port extras."""
    return {"answers": answers, **extra}


def uniq(xs: Iterable[str]) -> list[str]:
    out: list[str] = []
    for x in xs:
        if x not in out:
            out.append(x)
    return out
