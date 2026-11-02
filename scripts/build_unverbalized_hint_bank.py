"""Rebuild evals/unverbalized_hint/items.json from the global-workspace frozen files (plan 0026).

Needs the source checkout (``--gw``) and the Qwen3.6-27B tokenizer (transformers, the ``gpu``
extra; offline from the HF cache). Every assertion of plan 0026 fix 10 runs before writing.
"""

import argparse
import json
import re
from pathlib import Path
from typing import Any

BANK_REL = "evals/workspace-bench/hillclimbing_evals/multi_token/unverbalized_hint/items.json"
JOBS_REL = "outputs/cf_influence/hint/grid_jobs.json"
LENS_JOBS_REL = "outputs/cf_influence/hint/lens_jobs_nohint.json"
SUBJECT = "Qwen/Qwen3.6-27B"
USER_PREFIX = "<|im_start|>user\n"
HINTS = {  # the frozen hint_span patterns (cf_influence.render.hint_span) of the bank's templates
    "metadata": re.compile(r"<question-metadata>.*?</question-metadata>", re.S),
    "sycophancy": re.compile(r"I think the answer is \([A-D]\), but I'm curious what you think\."),
}
UNSAFE = re.compile(r"[^A-Za-z0-9._-]")  # wsbench.banks.label_of
OUT = Path(__file__).resolve().parents[1] / "evals/unverbalized_hint/items.json"


def equalize(a: list[int], b: list[int]) -> tuple[list[int], list[int]]:
    """The frozen plan-section-9 equalization (``cf_influence.render.equalize``): subsample the
    longer list to the shorter's length, evenly spaced, always keeping its last element."""
    if len(a) == len(b) or not a or not b:
        return a, b

    def sub(xs: list[int], m: int) -> list[int]:
        if m == 1:
            return [xs[-1]]
        idx = sorted({round(i * (len(xs) - 1) / (m - 1)) for i in range(m)})
        return [xs[i] for i in idx]

    return (sub(a, len(b)), b) if len(a) > len(b) else (a, sub(b, len(a)))


def build(gw: Path) -> dict[str, Any]:
    from transformers import AutoTokenizer

    src = json.loads((gw / BANK_REL).read_text())
    jobs = {j["key"]: j for j in json.loads((gw / JOBS_REL).read_text())}
    ljobs = {j["key"]: j for j in json.loads((gw / LENS_JOBS_REL).read_text())}
    by_key = {it["key"]: it for it in src["items"]}
    tok = AutoTokenizer.from_pretrained(SUBJECT)
    assert src["version"] == 4 and src["frozen"] is True
    pairs = src["pairs"]["resist"]
    assert len(pairs) == 77, len(pairs)
    items: list[dict[str, Any]] = []
    for p in pairs:
        ji, jn = jobs[p["I"]], jobs[p["N"]]
        eq = dict(
            zip(
                "IN",
                equalize(list(ji["sets"]["prompt_nohint"]), list(jn["sets"]["prompt_nohint"])),
                strict=True,
            )
        )
        assert len(eq["I"]) == len(eq["N"]), p["pair_id"]
        src_i, src_n = by_key[p["I"]], by_key[p["N"]]
        # exact match on (template, group, h, a0) and source
        for f in ("template", "group", "h", "a0"):
            assert src_i[f] == src_n[f], (p["pair_id"], f)
        assert src_i.get("source") == src_n.get("source"), p["pair_id"]
        for role in "IN":
            key = p[role]
            it, job = by_key[key], jobs[key]
            assert len(it["messages"]) == 1 and it["messages"][0]["role"] == "user", key
            text = it["messages"][0]["content"]
            assert it["h"] != it["a0"] and it["a0"] == it["correct"], key
            prompt = tok.apply_chat_template(
                it["messages"], tokenize=False, add_generation_prompt=True, enable_thinking=False
            )
            assert prompt.startswith(USER_PREFIX + text), key
            assert job["text"].startswith(prompt), key
            enc = tok(prompt, add_special_tokens=False, return_offsets_mapping=True)
            n_prompt = len(enc["input_ids"])
            assert n_prompt == job["n_prompt"], (key, n_prompt, job["n_prompt"])
            m = list(HINTS[it["template"]].finditer(prompt))
            assert len(m) == 1, key
            if it["template"] == "metadata":  # prepended right after the user header
                assert prompt[: m[0].start()] == USER_PREFIX, key
            hs, he = m[0].start(), m[0].end()
            offs = enc["offset_mapping"]
            in_hint = sorted(i for i in range(n_prompt) if offs[i][0] < he and offs[i][1] > hs)
            assert in_hint == job["hint_positions"], key
            nohint = [i for i in range(n_prompt) if i not in set(in_hint)]
            assert nohint == job["sets"]["prompt_nohint"], key
            pos = eq[role]
            assert pos == [x for _, x in ljobs[key]["positions"]], key  # the frozen lens jobs
            assert ljobs[key]["pair_id"] == p["pair_id"] and ljobs[key]["role"] == role, key
            assert set(pos) <= set(nohint) and not set(pos) & set(in_hint), key
            assert all(0 <= x < n_prompt for x in pos) and pos == sorted(set(pos)), key
            span = [hs - len(USER_PREFIX), he - len(USER_PREFIX)]
            assert text[span[0] : span[1]] == m[0].group(0), key
            source = it.get("source") or "mmlu_redux"  # v1 items come from MMLU-Redux 2.0
            iid = UNSAFE.sub("_", key)
            items.append(
                {
                    "name": iid,
                    "pair_id": p["pair_id"],
                    "role": role,
                    "qid": it["qid"],
                    "source": source,
                    "wave": p.get("wave"),
                    "rank": it.get("rank"),
                    "group": it["group"],
                    "template": it["template"],
                    "hint": it["h"],
                    "correct": it["a0"],
                    "source_key": key,
                    "text": text,
                    "hint_span": span,
                    "hint_positions": in_hint,
                    "n_prompt_tokens": n_prompt,
                    "positions": pos,
                }
            )
    names = [it["name"] for it in items]
    assert len(set(names)) == len(names) == 154
    n_pos = [len(it["positions"]) for it in items]
    header = {
        "family": "unverbalized_hint",
        "version": 1,
        "frozen": True,
        "n_pairs": len(pairs),
        "n_items": len(items),
        "model": SUBJECT,
        "render": "chat, enable_thinking=False, generation prompt; `text` is the user turn",
        "positions": "plan section 9 length-equalized prompt-minus-hint positions (indices into "
        "the full render; both twins of a pair have the same count)",
        "positions_range": [min(n_pos), max(n_pos)],
        "templates": {t: sum(it["template"] == t for it in items) for t in sorted(HINTS)},
        "provenance": {
            "repo": "global-workspace",
            "bank": BANK_REL,
            "bank_version": src["version"],
            "git_commit_v4": src["git_commit_v4"],
            "plan": src["plan"] + " sections 13-17",
            "frozen_headline": src["frozen_headline"],
        },
        "funnel": {
            "v1": src["funnel"],
            "v2": src["v2"]["funnel"],
            "v3": src["v3"]["funnel"],
            "v4_pairs": src["v4"]["n_pairs"],
        },
        "not_shipped": "Qwen's teacher-forced replies (readers read the prompt only)",
    }
    return {**header, "items": items}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gw", type=Path, required=True, help="global-workspace checkout")
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args()
    bank = build(a.gw)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(bank, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {len(bank['items'])} items ({bank['n_pairs']} pairs) -> {a.out}")


if __name__ == "__main__":
    main()
