"""Gate a candidate bank on an open-weights subject model (HF transformers): greedy + K samples
with thinking off, deterministic sign-aware grading (optional LLM grader for the misses),
model-specific golds, tokenizer re-stamping, and the out-of-capability verdict.

    uv run --extra gpu python .claude/skills/wsb-new-questions/scripts/gate_hf.py \\
        --family multihop --bank cand/multihop.json --model Qwen/Qwen3.5-0.8B \\
        --out gated/multihop

Writes <out>/gate.json (every question, answer and verdict), <out>/items.json (the passers,
stamped for this subject) and <out>/summary.json (rates, OOC verdict). Needs a GPU for anything
bigger than ~2B parameters (--device cpu works for tiny models, slowly).
"""

import argparse
import json
import math
import random
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_bank import LIST_BANKS, MT_FAMILIES, load_any, make_shadow

ANSWER_STEM = "My one-word answer is:"  # single-token answers; basic_readout implicit prefill
MT_STEM = "My answer is:"  # the multi-token tier and its bridge questions
FINAL_ANSWER = {"arithmetic_intermediates", "chain_intermediates"}
STRICT = {"chain_intermediates"}  # 10/10 at T=0.8, top_p=0.95
MC = {"conjunctive_association", "role_bound_association"}
GREEDY_ONLY = {"relational_multihop"}
# the answer must be in the prompt's (L2) language: an English gloss is wrong, never graded up
L2_ANSWER = {"multilingual", "multilingual_mt", "multilingual_multihop", "multilingual_typo"}
L2_GRADE_NOTE = (
    "\n\nThis question is in a language other than English and its answer must be in that "
    "same language. An answer in another language (e.g. an English translation of the "
    "correct word) is INCORRECT."
)
# also gated as a raw continuation of the prompt (their read render is plain); typo families
# are excluded (the continuation of a misspelling is not its correction)
PLAIN_VARIANT = {
    "poetry",
    "multihop",
    "multilingual",
    "multihop_mt_v2",
    "multilingual_mt",
    "multilingual_multihop",
    "basic_readout_mt",
}
# stamped as `gate_variant` (how the item was gated); every gate_hf.py gate is a chat render
GATE_VARIANT = {"directed_modulation": "chat_dm"}  # greedy-correct, both items of a scene
UNSUPPORTED = {
    "moral_rationale": "its golds are elicited from the subject: use moral_gate.py",
    "buggy_code": "needs execution checks and the volunteering gate: use buggy_gate.py",
    "multi_concept_directed_modulation": "no capability gate: the sentence is prefilled",
    "user_modeling": "kept as-is in the reference recipe; use `wsbench capable` to check",
}
_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")
NUM = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w])")


# ------------------------------------------------------------------ grading


def norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", text.casefold())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^\w]+", " ", t).strip()


def string_match(answer: str, golds: list[str]) -> bool:
    """Word-aligned containment after folding (drops punctuation AND the minus sign)."""
    a = f" {norm(answer)} "
    return any(g and f" {norm(g)} " in a for g in map(str, golds))


def as_num(text: str) -> float | None:
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


LEAD_IN = re.compile(
    r"^(?:my (?:one-word )?answer is|the answer is|answer|it is|it's|that is|this is)\s*:?\s*",
    re.I,
)
ARTICLE = re.compile(r"^(?:the|a|an)\s+", re.I)


def answer_span(answer: str) -> str:
    """The span a free-form answer commits to: its first sentence of its first line, markdown
    bold removed. Later sentences (asides, 'While X and Y ...') never count."""
    first = answer.replace("**", "").strip().split("\n", 1)[0]
    return re.split(r"(?<=[^A-Z0-9.][.!?;])\s", first, maxsplit=1)[0]


def anchored_match(answer: str, golds: list[str], ask: str = "") -> bool:
    """A gold, word-aligned, inside the answer span. A gold that also occurs in the question
    (an echo: 'built the Eiffel Tower' -> 'Eiffel') only counts when the whole span IS that
    gold, so a wrong answer that repeats the question's words never passes."""
    span = LEAD_IN.sub("", answer_span(answer).strip()).strip(" .,:;!?\"'*")
    bare = norm(ARTICLE.sub("", span))
    padded, q = f" {norm(span)} ", f" {norm(ask)} "
    for g in map(str, golds):
        ng = norm(g)
        if not ng:
            continue
        if bare == norm(ARTICLE.sub("", g)):
            return True
        if f" {ng} " in padded and f" {ng} " not in q:
            return True
    return False


def quick_match(answer: str, golds: list[str], final: bool, ask: str = "") -> bool:
    """``final`` families: a numeric gold must be the answer's LAST number, sign included
    (plain string_match would accept 1386 for -1386); a word gold is a whole-word match.
    Others: ``anchored_match`` (first-sentence span, echo-aware), not bare containment."""
    if not final:
        return anchored_match(answer, golds, ask)
    nums = NUM.findall(answer.replace(",", ""))
    for g in map(str, golds):
        gv = as_num(g)
        if gv is None:
            if string_match(answer, [g]):
                return True
        elif nums and as_num(nums[-1]) == gv:
            return True
    return False


def stopped_at_first(item: dict[str, Any], answer: str) -> bool:
    """The answer's only number is the FIRST intermediate: it stopped after step 1 (a wrong
    answer, labelled apart from a chain-of-thought leak, which writes steps on the way)."""
    inters = [str(x) for x in item.get("intermediates", [])]
    nums = [as_num(n) for n in NUM.findall(answer.replace(",", ""))]
    first = as_num(inters[0]) if inters else None
    return first is not None and len(nums) == 1 and nums[0] is not None and nums[0] == first


def english_glosses(item: dict[str, Any]) -> list[str]:
    """English renderings of an L2 answer (multilingual intermediates, concept/correction en
    forms) that must NOT count as the answer to an L2 prompt."""
    out = [str(x) for x in item.get("intermediates", []) if str(x)]
    for u in item.get("units", []) or []:
        if u.get("role") in ("concept", "correction", "readout"):
            out += [str(f) for f in (u.get("forms") or {}).get("en", [])]
    tg = {norm(str(t)) for t in [item.get("target"), *(item.get("target_alts") or [])] if t}
    return [g for g in dict.fromkeys(out) if norm(g) not in tg]


def states_intermediate(item: dict[str, Any], answer: str) -> bool:
    """Computational families: does the answer write an intermediate (the source gates'
    max_leak = 0)? Numbers: a standalone numeral equal to it (sign-aware, within 1e-6);
    a word intermediate: the committed (first) word is the intermediate."""
    inters = [str(x) for x in item.get("intermediates", [])]
    nums = [as_num(n) for n in NUM.findall(answer.replace(",", ""))]
    for x in inters:
        xv = as_num(x)
        if xv is None:
            words = re.findall(r"[a-z]+", answer.lower())
            if words and words[0] == x.lower():
                return True
        elif any(v is not None and abs(v - xv) <= 1e-6 * max(1.0, abs(xv)) for v in nums):
            return True
    return False


ECHO = re.compile(r"^(?:\s*</?think>\s*)+|^\s*my (?:one-word )?answer is:?\s*", re.I)


def clean_answer(text: str) -> str:
    """Strip a literal leftover `</think>` (some small models emit it as text after the empty
    think block) and an echo of the answer stem, both of which would hide the answer."""
    prev = None
    while prev != text:
        prev, text = text, ECHO.sub("", text.strip())
    return text.strip()


PLAIN_SPAN = 4  # words of the continuation's first line a plain gold may sit in


def plain_match(answer: str, golds: list[str]) -> bool:
    """Raw-continuation grading: the continuation starts with a gold (CJK golds by prefix),
    or a gold is a whole word among the first PLAIN_SPAN words of its first line. A gold
    later in the text is a different continuation, not the answer."""
    a = norm(answer)
    head = " " + " ".join(norm(answer.split("\n", 1)[0]).split()[:PLAIN_SPAN]) + " "
    for g in map(norm, map(str, golds)):
        if not g:
            continue
        if a == g or a.startswith(g + " ") or (_CJK.search(g) and a.startswith(g)):
            return True
        if f" {g} " in head:  # "Indian Rupee" for "rupee": a whole word in the first words
            return True
    return False


def first_word(text: str) -> str:
    m = re.search(r"[^\W\d_][\w'-]*|\d+", text)
    return m.group(0).casefold().strip("'-") if m else ""


def mc_letter(text: str) -> str:
    """The option letter: a bare letter (``B``, ``(B)``, ``B.``) or a letter followed by its own
    bracket/colon/period (``B) envy``, ``B: envy``); a pronoun ("I think ...", "A tree")
    is not a letter."""
    t = text.strip()
    m = re.fullmatch(r"\(?([A-P])\)?[.:]?", t) or re.match(r"\(?([A-P])(?:\)|[.:])\s", t)
    return m.group(1) if m else ""


def rhymes(a: str, b: str) -> bool:
    """CMU rhyming part shared (any pronunciation), else the same final two letters."""
    if a == b:
        return True
    try:
        import pronouncing  # type: ignore[import-not-found]
    except ImportError:
        return a[-2:] == b[-2:]
    pa, pb = pronouncing.phones_for_word(a), pronouncing.phones_for_word(b)
    if pa and pb:
        return bool(
            {pronouncing.rhyming_part(p) for p in pa} & {pronouncing.rhyming_part(p) for p in pb}
        )
    return a[-2:] == b[-2:]


def line_one_end(prompt: str) -> str:
    lines = [ln for ln in prompt.split("\n") if ln.strip()]
    words = re.findall(r"[A-Za-z']+", lines[-2] if len(lines) >= 2 else lines[0])
    return words[-1].casefold() if words else ""


# ------------------------------------------------------------------ questions


def key_of(family: str, it: dict[str, Any]) -> str:
    return (
        str(it["id"]) if family in LIST_BANKS else re.sub(r"[^A-Za-z0-9._-]", "_", str(it["name"]))
    )


def mc_ask(it: dict[str, Any], reverse: bool = False) -> tuple[str, str]:
    """Lettered MC ask (seeded shuffle per id); `reverse` asks the same options in the reverse
    order, so a position-biased subject ("always B") cannot pass both."""
    opts = list(it.get("mc_options") or [it["gold_label"], it["contrast_label"]])
    if it["gold_label"] not in opts:
        opts = [it["gold_label"], *opts]
    random.Random(f"pm-mc|{it['id']}").shuffle(opts)
    if reverse:
        opts.reverse()
    letters = "ABCDEFGHIJKLMNOP"
    listing = "\n".join(f"({letters[i]}) {o}" for i, o in enumerate(opts))
    ask = (
        f"{it['stimulus']}\n\nWhich option best describes what the text implies?\n{listing}"
        "\n\nReply with the letter only."
    )
    return ask, letters[opts.index(it["gold_label"])]


def build_questions(
    family: str, items: dict[str, dict[str, Any]], stem: str | None = None
) -> list[dict[str, Any]]:
    from wsbench.capable.questions import build

    out: list[dict[str, Any]] = []

    def q(
        qid: str, ask: str, golds: list[str], mode: str, prefill: str = "", max_new: int = 64
    ) -> None:
        out.append(
            {
                "qid": qid,
                "item": qid.split(":bridge")[0],
                "ask": ask,
                "golds": golds,
                "mode": mode,
                "prefill": prefill,
                "max_new": max_new,
            }
        )

    if family in MC:
        for k, it in items.items():
            ask, gold = mc_ask(it)
            q(k, ask, [gold], "mc", max_new=8)
            ask, gold = mc_ask(it, reverse=True)  # a second leg: both orders must pass
            q(f"{k}:mc_reversed", ask, [gold], "mc", max_new=8)
            out[-1]["item"] = k
    elif family == "poetry":
        for c in build(family):
            q(c.id, c.ask, [], "own_poetry", max_new=16)
    elif family == "directed_modulation":
        for k, it in items.items():
            q(k, it["prompt"], [it["carrier"]], "dm", max_new=64)
    else:
        # answer stems as in the source gates: "My answer is:" for the multi-token tier and
        # its bridge questions, "My one-word answer is:" for single-token answers, none for the
        # computational families (they say "Reply with only the final number")
        if stem is None:
            stem_ = (
                ""
                if family in FINAL_ANSWER
                else MT_STEM
                if family in MT_FAMILIES or family in GREEDY_ONLY
                else ANSWER_STEM
            )
        else:
            stem_ = stem
        for c in build(family):
            golds = list(c.golds)
            if family in FINAL_ANSWER:  # capable's golds are the intermediates for these
                golds = [str(items[c.id.split(":bridge")[0]]["answer"])]
            mode = "greedy" if family in GREEDY_ONLY else "standard"
            leg_stem = MT_STEM if ":bridge" in c.id and stem is None else stem_
            q(
                c.id,
                c.ask,
                golds,
                mode,
                prefill=leg_stem,
                max_new=32 if family in FINAL_ANSWER else 96,
            )
        if family == "basic_readout":
            for k, it in items.items():
                if it.get("subfamily") == "implicit":
                    q(k, it["prompt"], [], "own_implicit", prefill=ANSWER_STEM, max_new=16)
    if family in PLAIN_VARIANT:
        # the frozen banks' first gate variant: a raw continuation of the prompt, the same
        # render the lens reads (eval_render "plain"); an item passes on plain OR chat
        golds_of = {x["item"]: x["golds"] for x in out if ":bridge" not in x["qid"]}
        for k, it in items.items():
            mode = "own_poetry_plain" if family == "poetry" else "plain"
            # a trailing space makes the next token a bare-space continuation (small models
            # then emit digits); like the frozen gate's plain_stripped, ask without it
            text = str(it["prompt"])
            q(f"{k}:plain", text.rstrip(), golds_of.get(k, []), mode, max_new=8)
            out[-1].update(item=k, raw=True, stripped=text != text.rstrip())
    return out


# ------------------------------------------------------------------ generation


class Subject:
    def __init__(self, model_id: str, device: str, dtype: str) -> None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.torch = torch
        self.tok = AutoTokenizer.from_pretrained(model_id)
        self.tok.padding_side = "left"
        if self.tok.pad_token is None:
            self.tok.pad_token = self.tok.eos_token
        self.model = AutoModelForCausalLM.from_pretrained(
            model_id, dtype=getattr(torch, dtype), device_map=device
        )
        self.model.eval()
        self.device = device
        stops = {self.tok.eos_token_id}
        for t in ("<|im_end|>", "<|endoftext|>", "<end_of_turn>", "<turn|>"):
            i = self.tok.convert_tokens_to_ids(t)
            if isinstance(i, int) and i >= 0 and i != self.tok.unk_token_id:
                stops.add(i)
        self.stops = sorted(s for s in stops if s is not None)

    def render(self, ask: str, prefill: str) -> list[int]:
        """The benchmark's chat render: user turn only, thinking OFF, optional prefill."""
        out = self.tok.apply_chat_template(
            [{"role": "user", "content": ask}],
            tokenize=True,
            add_generation_prompt=True,
            enable_thinking=False,
        )
        ids = list(out["input_ids"] if hasattr(out, "keys") else out)
        if prefill:
            ids += self.tok(prefill, add_special_tokens=False)["input_ids"]
        return ids

    def render_raw(self, text: str) -> list[int]:
        """A raw continuation render (no chat template; BOS as the tokenizer adds it)."""
        return list(self.tok(text)["input_ids"])

    def generate(
        self,
        prompts: list[list[int]],
        *,
        n: int,
        temperature: float,
        top_p: float,
        max_new: int,
        batch: int,
        seed: int,
    ) -> list[list[str]]:
        torch = self.torch
        torch.manual_seed(seed)
        order = sorted(range(len(prompts)), key=lambda i: len(prompts[i]))
        res: list[list[str]] = [[] for _ in prompts]
        # per prompt, per output: True when no stop token came within max_new (cut off)
        self.truncated: list[list[bool]] = [[] for _ in prompts]
        bs = max(1, batch // max(1, n))
        for s in range(0, len(order), bs):
            idx = order[s : s + bs]
            enc = self.tok.pad({"input_ids": [prompts[i] for i in idx]}, return_tensors="pt")
            enc = {k: v.to(self.model.device) for k, v in enc.items()}
            kw: dict[str, Any] = {
                "max_new_tokens": max_new,
                "eos_token_id": self.stops,
                "pad_token_id": self.tok.pad_token_id,
            }
            if temperature > 0:
                kw |= {
                    "do_sample": True,
                    "temperature": temperature,
                    "top_p": top_p,
                    "top_k": 0,
                    "num_return_sequences": n,
                }
            else:
                kw |= {"do_sample": False}
            with torch.no_grad():
                gen = self.model.generate(**enc, **kw)
            width = enc["input_ids"].shape[1]
            for j, row in enumerate(gen[:, width:].tolist()):
                cut = next((p for p, t in enumerate(row) if t in self.stops), len(row))
                text = clean_answer(self.tok.decode(row[:cut], skip_special_tokens=True))
                res[idx[j // (n if temperature > 0 else 1)]].append(text)
                self.truncated[idx[j // (n if temperature > 0 else 1)]].append(cut == len(row))
        return res


def render_q(subj: "Subject", q: dict[str, Any]) -> list[int]:
    return subj.render_raw(q["ask"]) if q.get("raw") else subj.render(q["ask"], q["prefill"])


def greedy_pass(subj: "Subject", qs: list[dict[str, Any]], batch: int) -> None:
    """Greedy answer (and truncation flag) for every question, batched by max_new."""
    for mx in sorted({q["max_new"] for q in qs}):
        group = [q for q in qs if q["max_new"] == mx]
        outs = subj.generate(
            [render_q(subj, q) for q in group],
            n=1,
            temperature=0.0,
            top_p=1.0,
            max_new=mx,
            batch=batch,
            seed=0,
        )
        for q, o, tr in zip(group, outs, subj.truncated, strict=True):
            q["greedy"] = o[0]
            q["truncated_greedy"] = tr[0]


# ------------------------------------------------------------------ per-subject stamping


def ntok(tok: Any, s: str) -> int:
    """Strict token count: min over {s, lower, title} x {bare, leading space}."""
    return min(
        len(tok(v, add_special_tokens=False)["input_ids"])
        for c in {s, s.lower(), s.title()}
        for v in (c, " " + c)
    )


def stamp_mt(it: dict[str, Any], tok: Any, family: str) -> bool:
    """Re-stamp probe_token_lens with the subject tokenizer; False when a required multi-token
    unit keeps no multi-token form in some non-zh language (the item is then ineligible)."""
    units: dict[str, dict[str, list[int]]] = {}
    ok = True
    for u in it.get("units", []):
        forms = u.get("forms") or {}
        units[u["role"]] = {lang: [ntok(tok, f) for f in fs] for lang, fs in forms.items()}
        if u.get("required", True) and u.get("multi_token", True):
            for lang, counts in units[u["role"]].items():
                if lang != "zh" and not any(c > 1 for c in counts):
                    ok = False
    ptl: dict[str, Any] = {"units": units, "target": ntok(tok, str(it.get("target", "")))}
    if family == "multihop_mt_v2":
        ptl["target_alts"] = [ntok(tok, str(a)) for a in it.get("target_alts", [])]
    it["probe_token_lens"] = ptl
    return ok


def multihop_offsets(it: dict[str, Any], tok: Any) -> None:
    ids = tok(it["prompt"], add_special_tokens=False)["input_ids"]
    last = tok.decode(ids[-1:])
    it["readout"] = {"kind": "last_word_token", "offsets": [-2 if not last.strip() else -1]}


# ------------------------------------------------------------------ main


def ooc_status(n_eval: int, rate: float, capacity: int = 0) -> str:
    """The OOC rule (gating.md section 6): < 3% over >= min(200, capacity) gated candidates.
    Pool waves with merge_gated.py before deciding; one small wave is never enough."""
    floor = min(200, capacity) if capacity else 200
    if rate >= 0.03:
        return "in-capability"
    if n_eval >= floor:
        return "ooc"
    return "undetermined (gate >= min(200, capacity) candidates before calling OOC)"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--family", required=True)
    ap.add_argument("--bank", required=True, type=Path)
    ap.add_argument("--model", required=True, help="HF id of the subject model")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--repo", type=Path, default=Path.cwd())
    ap.add_argument("--k", type=int, default=10, help="sampled draws per question")
    ap.add_argument("--min-pass", type=int, default=8, help="of K (STRICT families: K)")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--dtype", default="bfloat16")
    ap.add_argument("--batch", type=int, default=256, help="sequences per generate call")
    ap.add_argument(
        "--grader",
        default="",
        help="optional LLM grader for answers the string match rejects, e.g. "
        "google/gemini-3.8-flash (OPENROUTER_API_KEY) or a claude-* id "
        "(ANTHROPIC_API_KEY); empty = deterministic grading only",
    )
    ap.add_argument(
        "--answer-stem",
        default=None,
        help="override the answer-stem prefill (default: the family's stem; '' = none)",
    )
    ap.add_argument(
        "--reuse",
        type=Path,
        default=None,
        help="an earlier gate.json of the SAME bank: reuse its decoded answers (greedy and "
        "samples, by question id) and only generate what is missing; re-grades everything",
    )
    ap.add_argument(
        "--capacity",
        type=int,
        default=0,
        help="how many candidates this family could ever supply (for the OOC rule)",
    )
    a = ap.parse_args()
    fam = a.family
    if fam in UNSUPPORTED:
        print(f"{fam}: not gated by this script: {UNSUPPORTED[fam]}", file=sys.stderr)
        return 2
    a.out.mkdir(parents=True, exist_ok=True)
    header, raw_items, is_list = load_any(a.bank)
    shadow = make_shadow(a.repo.resolve(), fam, a.bank.resolve(), a.out.resolve() / "work")
    sys.path.insert(0, str(shadow / "src"))
    from wsbench.banks import load_bank

    items_l = raw_items if is_list else load_bank(shadow / "evals" / fam / "items.json")[1]
    items = {key_of(fam, it): it for it in items_l}
    qs = build_questions(fam, items, a.answer_stem)
    print(f"{fam}: {len(items)} items, {len(qs)} questions; loading {a.model}")
    final = fam in FINAL_ANSWER
    old: dict[str, dict[str, Any]] = {}
    if a.reuse is not None:
        old = {q["qid"]: q for q in json.loads(a.reuse.read_text(encoding="utf-8"))}
    _subj: list[Subject] = []

    def get_subj() -> Subject:  # loaded only when something must be generated
        if not _subj:
            _subj.append(Subject(a.model, a.device, a.dtype))
        return _subj[0]

    # 1. greedy; a stem that makes the subject stop at once (empty answer: small models end
    # the turn after "My answer is:") is dropped for that question, which is re-asked bare
    gen_g = []
    for q in qs:
        o = old.get(q["qid"])
        if o is not None and "greedy" in o and o.get("ask") == q["ask"]:
            for f in ("greedy", "truncated_greedy", "prefill", "stem_dropped"):
                if f in o:
                    q[f] = o[f]
        else:
            gen_g.append(q)
    if gen_g:
        greedy_pass(get_subj(), gen_g, a.batch)
    empty = [q for q in gen_g if not q["greedy"] and q["prefill"]]
    for q in empty:
        q["prefill"], q["stem_dropped"] = "", True
    if empty:
        greedy_pass(get_subj(), empty, a.batch)

    def hit(q: dict[str, Any], ans: str) -> bool | None:
        m = q["mode"]
        if m == "mc":
            return mc_letter(ans) == q["golds"][0]
        if m == "dm":
            it = items[q["item"]]
            return norm(ans) == norm(it["carrier"]) and not string_match(ans, [it["concept"]])
        if m in ("own_poetry", "own_poetry_plain", "own_implicit"):
            return None  # decided after sampling, against the greedy word
        if m == "plain":
            return plain_match(ans, q["golds"])
        if final and states_intermediate(items[q["item"]], ans):
            if stopped_at_first(items[q["item"]], ans):
                q["stopped"] = q.get("stopped", 0) + 1  # answered step 1: wrong, not a leak
            else:
                q["leaks"] = q.get("leaks", 0) + 1
            return False  # it wrote the latent: a chain-of-thought rollout, never a pass
        if quick_match(ans, q["golds"], final, q["ask"]):
            return True
        if fam in L2_ANSWER and ":bridge" not in q["qid"]:
            glosses = english_glosses(items[q["item"]])
            if glosses and anchored_match(ans, glosses, q["ask"]):
                return False  # answered in English, not in the prompt's language
        return None if a.grader and not final else False

    for q in qs:
        q["greedy_ok"] = hit(q, q["greedy"])
    # 2. samples (only where greedy can still pass)
    strict = fam in STRICT
    temp, top_p = (0.8, 0.95) if strict else (0.7, 1.0)
    need = a.k if strict else a.min_pass
    todo = [q for q in qs if q["mode"] != "greedy" and q["greedy_ok"] is not False]
    for q in todo:  # --reuse: samples already decoded for this question
        o = old.get(q["qid"])
        if o is not None and o.get("samples") and o.get("ask") == q["ask"]:
            q["samples"], q["truncated_samples"] = o["samples"], o.get("truncated_samples", 0)
    todo = [q for q in todo if "samples" not in q]
    subj = get_subj() if todo else None
    for mx in sorted({q["max_new"] for q in todo}):
        group = [q for q in todo if q["max_new"] == mx]
        outs = subj.generate(
            [render_q(subj, q) for q in group],
            n=a.k,
            temperature=temp,
            top_p=top_p,
            max_new=mx,
            batch=a.batch,
            seed=7,
        )
        for q, o, tr in zip(group, outs, subj.truncated, strict=True):
            q["samples"] = o
            q["truncated_samples"] = sum(tr)
    # 3. optional LLM grading of undecided answers
    if a.grader:
        from wsbench.capable.questions import Question
        from wsbench.capable.run import GRADE_SCHEMA, GRADE_SYSTEM, render_grade
        from wsbench.llm import stream_json

        pend: list[tuple[dict[str, Any], int, str]] = []
        for q in qs:
            if q["mode"] not in ("standard", "greedy"):
                continue
            for i, ans in enumerate([q["greedy"], *q.get("samples", [])]):
                if ans and not quick_match(ans, q["golds"], final, q["ask"]):
                    pend.append((q, i, ans))
        verdicts: dict[tuple[str, int], bool] = {}
        prompts = [
            (
                GRADE_SYSTEM
                + (L2_GRADE_NOTE if fam in L2_ANSWER and ":bridge" not in q["qid"] else ""),
                render_grade(Question(q["qid"], q["ask"], q["golds"]), ans),
            )
            for q, _i, ans in pend
        ]

        def on(i: int, r: dict[str, Any] | None) -> None:
            verdicts[(pend[i][0]["qid"], pend[i][1])] = bool(r and r.get("correct"))

        if prompts:
            stream_json(prompts, schema=GRADE_SCHEMA, model=a.grader, on_result=on, temperature=0.0)
        for q in qs:
            if q["mode"] in ("standard", "greedy"):
                q["llm"] = {str(i): v for (qid, i), v in verdicts.items() if qid == q["qid"]}
    # 4. verdicts
    for q in qs:
        m, answers = q["mode"], [q["greedy"], *q.get("samples", [])]
        if m in ("own_poetry", "own_poetry_plain", "own_implicit"):
            # raw continuations: the first word of the FIRST line only (".\nThe ..." is no word)
            fw = (lambda t: first_word(t.split("\n", 1)[0])) if q.get("raw") else first_word
            w = fw(q["greedy"])
            hits = sum(fw(s) == w for s in q.get("samples", []))
            q["word"] = w
            ok_w = bool(w)
            if m.startswith("own_poetry"):
                q["line_one_end"] = line_one_end(q["ask"])
                # an identity "rhyme" (repeating line one's last word) is not a rhyme
                q["rhymes"] = ok_w and w != q["line_one_end"] and rhymes(w, q["line_one_end"])
                ok_w = q["rhymes"]
            q["hits"], q["pass"] = hits, ok_w and hits >= need
            continue

        def ok(i: int, ans: str, q: dict[str, Any] = q) -> bool:
            v = hit(q, ans)
            return bool(v) if v is not None else bool(q.get("llm", {}).get(str(i)))

        q["greedy_ok"] = ok(0, answers[0])
        if m == "greedy":
            q["hits"], q["pass"] = None, q["greedy_ok"]
            continue
        # strict = the deterministic matcher alone (no LLM grader rescue)
        q["hits_strict"] = sum(bool(hit(q, s)) for s in q.get("samples", []))
        q["leaks"], q["stopped"] = (
            0,
            0,
        )  # recount over greedy + samples (hit() was also called on the greedy)
        hits = sum(ok(i + 1, s) for i, s in enumerate(q.get("samples", [])))
        q["greedy_ok"] = ok(0, answers[0])
        q["hits"] = hits
        q["pass"] = q["greedy_ok"] and hits >= need and (not final or q["leaks"] == 0)
    # 5. item verdicts (every leg must pass; relational: both items of a scene)
    by_item: dict[str, list[dict[str, Any]]] = {}
    for q in qs:
        by_item.setdefault(q["item"], []).append(q)

    def variant_legs(k: str, legs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [q for q in legs if q["qid"] in (k, f"{k}:plain")]

    passed = {  # one gate variant (chat or plain) must pass, and every other leg
        k: any(q["pass"] for q in variant_legs(k, v))
        and all(q["pass"] for q in v if q not in variant_legs(k, v))
        for k, v in by_item.items()
    }
    if fam in GREEDY_ONLY:
        scenes: dict[str, list[str]] = {}
        for k, it in items.items():
            scenes.setdefault(str(it.get("scene")), []).append(k)
        for ks in scenes.values():
            both = all(passed.get(k) for k in ks)
            for k in ks:
                passed[k] = both
    if fam == "role_bound_association":  # atomic pairs: both directions or neither
        by_pair: dict[str, list[str]] = {}
        for k, it in items.items():
            by_pair.setdefault(str(it.get("pair_id")), []).append(k)
        for ks in by_pair.values():
            both = len(ks) == 2 and all(passed.get(k) for k in ks)
            for k in ks:
                passed[k] = both
    if fam == "arithmetic_intermediates":  # twins survive together
        for k, it in items.items():
            tw = re.sub(r"[^A-Za-z0-9._-]", "_", str(it.get("pair") or ""))
            if tw in items and not passed.get(tw):
                passed[k] = False
    # 6. stamp passers for this subject
    if _subj:
        tok = _subj[0].tok
    else:
        from transformers import AutoTokenizer

        tok = AutoTokenizer.from_pretrained(a.model)
    kept, dropped = [], {}
    for k, it in items.items():
        if not passed.get(k):
            continue
        it = dict(it)
        if not is_list:
            it.pop("id", None)
        legs = by_item.get(k, [])
        plain = next((q for q in legs if q["qid"] == f"{k}:plain" and q["pass"]), None)
        main = plain or next((q for q in legs if q["qid"] == k), legs[0] if legs else None)
        if main and main.get("hits") is not None:
            it["consistency"] = main["hits"] / a.k
        if main:
            it["consistency_greedy"] = int(bool(main["greedy_ok"]))
        if main and fam in MT_FAMILIES and main.get("hits_strict") is not None:
            it["consistency_strict"] = main["hits_strict"] / a.k
        if not is_list and fam not in FINAL_ANSWER:
            it["gate_variant"] = (
                ("plain_stripped" if plain.get("stripped") else "plain")
                if plain
                else GATE_VARIANT.get(fam, "chat")
            )
        if fam in ("multihop_mt_v2", "multilingual_multihop"):
            it["bridge_consistency"] = {
                q["qid"].split(":")[1]: q["hits"] / a.k for q in legs if ":bridge" in q["qid"]
            }
        if fam == "poetry":
            it["intermediates"] = [main["word"]]
        if fam == "basic_readout" and it.get("subfamily") == "implicit":
            w = next(q["word"] for q in legs if q["mode"] == "own_implicit")
            it["target"], it["intermediates"] = w, [w]
            it["units"] = [{"role": "readout", "lang": "en", "headline": True, "match": [w]}]
        if fam in MT_FAMILIES and not stamp_mt(it, tok, fam):
            dropped[k] = "a required unit has no multi-token form under this tokenizer"
            continue
        if fam == "multihop":
            multihop_offsets(it, tok)
        kept.append(it)
    if fam == "arithmetic_intermediates":  # null sets may only point at surviving items
        names = {re.sub(r"[^A-Za-z0-9._-]", "_", it["name"]) for it in kept}
        for it in kept:
            it["null_set"] = [n for n in it.get("null_set", []) if n in names]
            it["pair_survived"] = it.get("pair") in names
    rate = sum(passed.values()) / max(1, len(passed))
    n_eval = len(passed)
    status = ooc_status(n_eval, rate, a.capacity)
    gate_note = (
        f"{a.model} behavioral, chat template (enable_thinking=False)"
        + (" or raw plain continuation (per item: gate_variant)" if fam in PLAIN_VARIANT else "")
        + f": greedy-correct AND >= {need}/{a.k} @ T={temp} top_p={top_p}"
        + ("; MC asked in both option orders" if fam in MC else "")
        + "; gate_hf.py"
    )
    out_bank: Any = kept if is_list else {**header, "gate": gate_note, "items": kept}
    (a.out / "items.json").write_text(
        json.dumps(out_bank, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (a.out / "gate.json").write_text(json.dumps(qs, ensure_ascii=False, indent=1), encoding="utf-8")
    summary = {
        "family": fam,
        "model": a.model,
        "n_items": n_eval,
        "n_pass": sum(passed.values()),
        "pass_rate": round(rate, 4),
        "n_kept": len(kept),
        "dropped_after_gate": dropped,
        "status": status,
        "want_more_candidates_for_100": math.ceil(max(0, 100 - len(kept)) / max(rate, 0.03) * 1.3),
        "rule": gate_note,
    }
    (a.out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
