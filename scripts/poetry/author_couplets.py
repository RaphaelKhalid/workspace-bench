"""Candidate couplets for poetry bank v2's refill (plan 0038 §3), authored by Opus 5.5.

Each call asks for a batch of couplets in the v1 format
``"A rhyming couplet:\\n<line 1>,\\n<stub> "``
whose line-one end word has many common perfect rhymes. Since the read-site rule (Fable's decision
on review r7/r8) the gold is the rhyme Qwen3.6-27B commits to FROM LINE ONE (``qwen_gate.py``: the
modal line-final word of 11 free line twos written from line one's newline, >= 4/11, and the
plain leg after the stub must commit to the same word), so the brief (:data:`USER`) asks for a
line one that calls for ONE natural rhyme and a stub that leads to that same word. The authored
rhyme is only a hypothesis: the Qwen gate sets the gold. Deterministic filters: the v1 format
(``adapt.lint``), the rhyme rhymes with line one's end (CMU) and is absent from the stub, and a
line-one end word used at most :data:`MAX_PER_END` times across the bank and earlier candidates.

:data:`USER_V1` is the r0-r6 brief, kept only as the provenance of the first 153 candidates: its
"NOT the most obvious rhyme" rule decorrelated the gold from the read site (review r7) and is
never used for a new batch.

    ANTHROPIC_AUTH_TOKEN=... python scripts/poetry/author_couplets.py --n-calls 16 --per-call 12 \\
        --out candidates.json
"""

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from wsbench import llm
from wsbench.adapt.gate import fold, words
from wsbench.adapt.lint import lint
from wsbench.adapt.rhyme import known, rhymes
from wsbench.banks import label_of, load_bank
from wsbench.llm import Spend

MODEL = "claude-opus-5-5"
THEMES = [
    "the sea and sailors",
    "farm life and seasons",
    "a city at night",
    "school and teachers",
    "cooking and kitchens",
    "sports and games",
    "travel by train",
    "weather and storms",
    "animals in the forest",
    "music and dancing",
    "family and home",
    "war and soldiers",
    "magic and fairy tales",
    "work and money",
    "gardens and flowers",
    "mountains and climbing",
    "kings and castles",
    "science and machines",
    "love and friendship",
    "winter holidays",
]
SYSTEM = (
    "You write test items for a language-model interpretability benchmark. Follow the format "
    "exactly and return JSON only."
)
USER_V1 = """Write {k} rhyming couplets about {theme}, each cut right before its final rhyme word.

Format of each prompt, exactly three lines:
A rhyming couplet:
<line 1, ending in a comma>
<line 2 without its last word, followed by ONE trailing space>

Rules:
- Line 1 ends in a common one-syllable English word that has AT LEAST SIX common perfect \
rhymes (e.g. "day", "night", "light", "town", "rain", "go", "bright", "fair", "sky", \
"call").
- Line 2's wording must make ONE rhyme word the natural, near-certain completion (an idiom, \
a collocation, or a forced meaning), but that word should NOT be the most obvious rhyme \
someone would guess from line 1 alone: a reader who sees only line 1 should find several \
rhymes equally plausible.
- The rhyme word is a common English word, a perfect rhyme with line 1's last word, a \
different word from it, and does NOT appear anywhere in line 2's stub.
- Use a different line-1 end word for every couplet, and none of these: {used}.
- Natural, simple English, roughly ten syllables per line.

Return JSON {{"couplets": [{{"prompt": "...", "rhyme": "..."}}]}}."""
USER = """Write {k} rhyming couplets about {theme}, each cut right before its final rhyme word.

Format of each prompt, exactly three lines:
A rhyming couplet:
<line 1, ending in a comma>
<line 2 without its last word, followed by ONE trailing space>

Rules:
- Line 1 ends in a common English word that has AT LEAST SIX common perfect rhymes \
(e.g. "day", "night", "light", "town", "rain", "go", "bright", "fair", "sky", "call").
- Line 1 must CALL FOR one rhyme word: a poet who reads only line 1 and writes the second \
line would, nearly every time, end it on that same word, because line 1's idea, image or \
idiom points straight at it (a classic pairing, a set phrase, a natural conclusion). Other \
rhymes of line 1's last word should feel clearly worse fits.
- Line 2's stub continues naturally and leads to that SAME word, without containing it.
- The rhyme word is a common English word, a perfect rhyme with line 1's last word, and a \
different word from it.
- Line 1's last word starts with one of these letters: {letters}.
- Use a different line-1 end word for every couplet, and none of these: {used}.
- Natural, simple English, roughly ten syllables per line.

Return JSON {{"couplets": [{{"prompt": "...", "rhyme": "..."}}]}}."""
LETTERS = ["b, c", "d, f, g", "h, l", "m, n, p", "r, s", "t, w, and any other letter"]
NAME_PREFIX, SOURCE = "v3-po", "opus55_v3"  # read-site brief; v2-po / opus55_v2 = USER_V1
MAX_PER_END = 2  # couplets per line-one end word across the bank and all candidate rounds
SCHEMA = {
    "name": "couplets",
    "schema": {
        "type": "object",
        "properties": {
            "couplets": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"prompt": {"type": "string"}, "rhyme": {"type": "string"}},
                    "required": ["prompt", "rhyme"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["couplets"],
        "additionalProperties": False,
    },
}


def end_word(prompt: str) -> str:
    ws = words(prompt.split("\n")[1]) if prompt.count("\n") >= 2 else []
    return ws[-1] if ws else ""


def check(prompt: str, rhyme: str) -> str:
    """'' when the couplet passes the deterministic filters, else the reason."""
    item = {
        "name": "x",
        "prompt": prompt,
        "intermediates": [rhyme],
        "eval_render": "plain",
        "readout": {"kind": "line_one_tail"},
    }
    bad = [p for p in lint("poetry", item) if p.startswith("format")]
    if bad:
        return bad[0]
    lines = prompt.split("\n")
    end = end_word(prompt)
    if not lines[1].endswith(","):
        return "line one must end with a comma"
    if not (known(end) and known(rhyme) and rhymes(rhyme, end)):
        return f"{rhyme!r} does not rhyme with {end!r} (CMU)"
    if fold(rhyme) in {fold(w) for w in words(lines[2])}:
        return "rhyme in stub"
    return ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-calls", type=int, default=16)
    ap.add_argument("--per-call", type=int, default=12)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--bank", type=Path, default=Path("evals/poetry/items.json"))
    ap.add_argument("--seed-offset", type=int, default=0)
    ap.add_argument("--also-used", type=Path, nargs="*", default=[])
    a = ap.parse_args()
    _h, items = load_bank(a.bank)
    n_end: Counter[str] = Counter(fold(end_word(it["prompt"])) for it in items)
    prev: list[dict[str, Any]] = []
    if a.out.exists():
        prev = json.loads(a.out.read_text())["candidates"]
    names = {c["name"] for c in prev}
    for path in a.also_used:  # earlier candidate rounds: their end words count too
        earlier = json.loads(path.read_text())["candidates"]
        n_end.update(fold(end_word(c["prompt"])) for c in earlier)
        names |= {c["name"] for c in earlier}
    n_end.update(fold(end_word(c["prompt"])) for c in prev)
    used_list = ", ".join(sorted(w for w, n in n_end.items() if n >= MAX_PER_END))
    prompts = [
        (
            SYSTEM,
            USER.format(
                k=a.per_call,
                theme=THEMES[(i + a.seed_offset) % len(THEMES)],
                letters=LETTERS[((i + a.seed_offset) // len(THEMES)) % len(LETTERS)],
                used=used_list,
            ),
        )
        for i in range(a.n_calls)
    ]
    results: list[Any] = [None] * len(prompts)

    def on_result(i: int, r: dict | None) -> None:
        results[i] = r

    spend = Spend()
    llm.stream_json(
        prompts,
        schema=SCHEMA,
        model=MODEL,
        reasoning={"anthropic_effort": "default"},
        on_result=on_result,
        concurrency=16,
        rpm=240,
        max_tokens=16000,
        spend=spend,
    )
    kept = list(prev)
    drops: dict[str, int] = {}
    for r in results:
        for c in (r or {}).get("couplets", []):
            p, rh = str(c.get("prompt", "")), fold(str(c.get("rhyme", "")).strip())
            if not p.endswith(" "):
                p = p.rstrip() + " "
            why = check(p, rh)
            e = fold(end_word(p))
            name = f"{NAME_PREFIX}-{e}-{rh}"
            if not why and n_end[e] >= MAX_PER_END:
                why = "line-one end word already used"
            if not why and name in names:
                why = "duplicate end word / rhyme pair"
            if why:
                drops[why.split(" (")[0][:40]] = drops.get(why.split(" (")[0][:40], 0) + 1
                continue
            n_end[e] += 1
            names.add(name)
            kept.append(
                {
                    "name": name,
                    "id": label_of(name),
                    "prompt": p,
                    "authored_rhyme": rh,
                    "source": SOURCE,
                }
            )
    a.out.write_text(
        json.dumps({"candidates": kept, "drops": drops}, indent=1, ensure_ascii=False) + "\n"
    )
    print(f"{len(kept)} candidates ({len(kept) - len(prev)} new); drops {drops}; ${spend.usd:.2f}")


if __name__ == "__main__":
    main()
