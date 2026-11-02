"""Validate a NEW WorkspaceBench bank end to end, offline: schema, leak and dedupe lint, the
family's own read plan rendered with a real tokenizer, dummy readouts, and the real scorer.

Run from the repo root (needs the dev env plus `transformers` for the tokenizer):

    uv run --with transformers --with jinja2 python \\
        .claude/skills/wsb-new-questions/scripts/validate_bank.py \\
        --family multihop --bank outputs/new_items/multihop/items.json

Exit 0 = every check passed (warnings allowed), 1 = at least one ERROR, 2 = usage error.
Nothing here calls an API; `--live-limit N` opts into a real `wsbench judge limit=N` smoke
(it then needs OPENROUTER_API_KEY / ANTHROPIC_API_KEY in the environment).
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

MT_FAMILIES = {
    "basic_readout_mt",
    "multihop_mt_v2",
    "multilingual_mt",
    "typo_mt",
    "multilingual_multihop",
    "multilingual_typo",
}
NOT_AUTHORABLE = {
    "jlens_concept_pr": "its items are captured activations plus a J-lens reference",
    "agentic_misalignment": "its items are scenarios the model actually misbehaved in",
    "jailbreak_recognition": "its items are verbatim WildChat conversations",
}

# Fields a family's judge, read plan or capability question actually reads (missing = ERROR).
REQUIRED: dict[str, list[str]] = {
    "association": ["name", "prompt", "intermediates", "readout", "eval_render"],
    "basic_readout": [
        "name",
        "subfamily",
        "prompt",
        "target",
        "intermediates",
        "readout",
        "eval_render",
    ],
    "multihop": ["name", "prompt", "target", "intermediates", "readout", "eval_render"],
    "multilingual": ["name", "prompt", "target", "intermediates", "readout", "eval_render"],
    "poetry": ["name", "prompt", "intermediates", "readout", "eval_render"],
    "typo": ["name", "prompt", "intermediates", "readout", "eval_render"],
    "basic_readout_mt": [
        "name",
        "subfamily",
        "prompt",
        "target",
        "target_alts",
        "units",
        "probe_token_lens",
        "readout",
        "eval_render",
        "intermediates",
    ],
    "multihop_mt_v2": [
        "name",
        "subfamily",
        "prompt",
        "target",
        "target_alts",
        "units",
        "bridges",
        "probe_token_lens",
        "readout",
        "eval_render",
        "intermediates",
    ],
    "multilingual_mt": [
        "name",
        "subfamily",
        "prompt",
        "target",
        "target_alts",
        "lang",
        "units",
        "probe_token_lens",
        "readout",
        "eval_render",
        "intermediates",
    ],
    "typo_mt": [
        "name",
        "subfamily",
        "prompt",
        "target",
        "target_alts",
        "typo_word",
        "units",
        "probe_token_lens",
        "readout",
        "eval_render",
        "intermediates",
    ],
    "multilingual_multihop": [
        "name",
        "subfamily",
        "prompt",
        "target",
        "target_alts",
        "lang",
        "units",
        "bridges",
        "probe_token_lens",
        "readout",
        "eval_render",
        "intermediates",
    ],
    "multilingual_typo": [
        "name",
        "subfamily",
        "prompt",
        "target",
        "target_alts",
        "lang",
        "typo_word",
        "units",
        "probe_token_lens",
        "readout",
        "eval_render",
        "intermediates",
    ],
    "directed_modulation": [
        "name",
        "subfamily",
        "pair_id",
        "polarity",
        "concept",
        "carrier",
        "prompt",
        "assistant",
        "units",
    ],
    "user_modeling": [
        "name",
        "subfamily",
        "attr_class",
        "attr",
        "attr_label",
        "messages",
        "target",
        "intermediates",
    ],
    "moral_rationale": [
        "id",
        "topic_id",
        "stimulus",
        "question",
        "reason_class",
        "reasons",
        "look_for_reasons",
        "answer_format",
        "commit_direction",
    ],
    "relational_multihop": [
        "id",
        "scene",
        "stimulus",
        "names",
        "hop1",
        "hop2",
        "gold",
        "gold_alt",
        "flipped",
    ],
    "conjunctive_association": [
        "id",
        "stimulus",
        "gold_label",
        "contrast_label",
        "mc_options",
        "asked_question",
    ],
    "role_bound_association": [
        "id",
        "pair_id",
        "direction",
        "stereotypicality",
        "role_a",
        "role_b",
        "action",
        "names",
        "stimulus",
        "gold_label",
        "contrast_label",
        "asked_question",
        "mc_options",
    ],
    "chain_intermediates": ["name", "prompt", "intermediates", "answer", "start", "depth"],
    "arithmetic_intermediates": [
        "name",
        "prompt",
        "variant",
        "expr",
        "intermediates",
        "answer",
        "cell",
        "null_set",
        "tolerance",
        "role",
    ],
    "buggy_code": [
        "name",
        "src",
        "code",
        "language",
        "lang_group",
        "verified",
        "bug_line",
    ],
    "multi_concept_directed_modulation": ["name", "prompt", "concepts", "stratum"],
}
# Fields only the per-subject gate writes: a CANDIDATE bank (none of them present) is linted
# without them and stops after the guards; validate the gated bank for the full check.
POST_GATE: dict[str, list[str]] = {
    "moral_rationale": ["reason_class", "reasons", "look_for_reasons", "commit_direction"],
}
# Fields required only on buggy items (src != "clean"); clean twins carry none of them.
BUGGY_ONLY = {"bug_line"}  # consequence_class is read with .get() (None = "none")


def is_candidate(family: str, items: list[dict]) -> bool:
    post = POST_GATE.get(family, [])
    return bool(post) and not any(k in it for it in items for k in post)


def required_for(family: str, it: dict, candidate: bool) -> list[str]:
    req = [
        k for k in REQUIRED.get(family, []) if not (candidate and k in POST_GATE.get(family, []))
    ]
    if family == "buggy_code" and it.get("src") == "clean":
        req = [k for k in req if k not in BUGGY_ONLY]
    return req


REQUIRED_HEADER: dict[str, list[str]] = {
    **{f: ["family", "contract", "gate"] for f in MT_FAMILIES},
    "arithmetic_intermediates": ["family", "variants"],
    "buggy_code": ["family", "read_cells"],
    "multi_concept_directed_modulation": ["family", "target_sentence", "layers"],
}
LIST_BANKS = {
    "moral_rationale",
    "relational_multihop",
    "conjunctive_association",
    "role_bound_association",
}

errors: list[str] = []
warnings: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)
    print(f"  ERROR  {msg}")


def warn(msg: str) -> None:
    warnings.append(msg)
    print(f"  warn   {msg}")


def ok(msg: str) -> None:
    print(f"  ok     {msg}")


# ------------------------------------------------------------------ text helpers


def fold(s: str) -> str:
    """NFKD, combining marks dropped, curly apostrophe straightened, casefolded (the regex
    scorer's fold)."""
    s = unicodedata.normalize("NFKD", str(s)).replace("\u2019", "'")
    return "".join(c for c in s if not unicodedata.combining(c)).casefold()


_CJK = re.compile(r"[぀-ヿ㐀-鿿가-힯]")


def occurs(form: str, text: str) -> bool:
    """Word-boundary occurrence of ``form`` in ``text`` after folding (substring for CJK /
    Hangul / non-word forms), i.e. would the regex scorer's matcher fire on the prompt."""
    f, t = fold(form).strip(), fold(text)
    if not f:
        return False
    if _CJK.search(form) or not re.fullmatch(r"[^\W_]+(?:[\s\-'][^\W_]+)*", f):
        return f in t
    parts = [re.escape(w) for w in re.split(r"[\s\-]+", f) if w]
    return bool(re.search(r"(?<![^\W_])" + r"[\s\-]+".join(parts) + r"(?![^\W_])", t))


def stem_occurs(stem: str, text: str) -> bool:
    """role_bound's blocklist rule: the stem as a PREFIX at a word start ('pay' flags
    'payment' and 'pays', not the irregular 'paid': list those yourself). conjunctive lists
    its inflections explicitly and is checked whole-word."""
    f = fold(stem).strip()
    return bool(f) and bool(re.search(r"(?<![^\W_])" + re.escape(f), fold(text)))


def numeral_in(value: Any, text: str) -> bool:
    """A standalone numeral equal to ``value`` (sign-aware: -51 also flags a bare 51)."""
    v = str(value).strip()
    if not re.fullmatch(r"-?\d+(\.\d+)?", v):
        return False
    bare = v.lstrip("-")
    return bool(re.search(r"(?<![\d.])" + re.escape(bare) + r"(?![\d]|\.\d)", text))


EXACT_DEDUPE = {
    "arithmetic_intermediates",
    "chain_intermediates",
    "buggy_code",
    "relational_multihop",
}


def norm_prompt(s: str, family: str = "") -> str:
    """Dedupe key: words after folding; for the symbol-bearing families only whitespace is
    normalised (`(a - b) - c` and `a - (b - c)` are different items)."""
    if family in EXACT_DEDUPE:  # keep line structure and indentation (Python twins differ there)
        return "\n".join(ln.rstrip() for ln in str(s).strip().splitlines() if ln.strip())
    return " ".join(re.findall(r"\w+", fold(s)))


STOPWORDS = {
    "with",
    "from",
    "that",
    "this",
    "were",
    "have",
    "their",
    "which",
    "into",
    "over",
    "under",
    "about",
    "after",
    "before",
    "first",
    "they",
    "them",
    "than",
    "then",
    "what",
    "when",
    "where",
}


def words(s: str) -> set[str]:
    return set(re.findall(r"\w+", fold(s)))


# ------------------------------------------------------------------ bank shape


def load_any(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return {}, raw, True
    if not isinstance(raw, dict) or not isinstance(raw.get("items"), list):
        raise ValueError(f"{path}: a bank is a JSON list of items or an object with 'items'")
    return {k: v for k, v in raw.items() if k != "items"}, raw["items"], False


def item_key(it: dict[str, Any]) -> str:
    return str(it.get("id") or it.get("name"))


def prompt_text(family: str, it: dict[str, Any]) -> str:
    if family == "user_modeling":
        return "\n".join(m.get("content", "") for m in it.get("messages", []))
    if family == "buggy_code":
        return str(it.get("code", ""))
    return str(it.get("prompt") or it.get("stimulus") or "")


def check_schema(
    family: str,
    header: dict,
    items: list[dict],
    is_list: bool,
    f_header: dict,
    f_items: list[dict],
    f_is_list: bool,
) -> None:
    print("[1] schema")
    if is_list != f_is_list:
        err(
            f"bank shape: frozen bank is a {'list' if f_is_list else 'header+items object'}, "
            f"new bank is a {'list' if is_list else 'header+items object'}"
        )
    if not items:
        err("bank has no items")
        return
    for k in REQUIRED_HEADER.get(family, []):
        if k not in header:
            err(f"header lacks {k!r}")
    for k in f_header:
        if k not in header and k not in REQUIRED_HEADER.get(family, []):
            warn(f"header lacks {k!r} (the frozen bank has it; provenance/gate notes)")
    if family in MT_FAMILIES and isinstance(header.get("contract"), dict):
        c = header["contract"]
        fc = f_header.get("contract", {})
        for k in ("multi_token", "include_target", "conjunctive_units"):
            if k not in c:
                err(f"contract block lacks {k!r}")
            elif c.get(k) != fc.get(k):
                warn(
                    f"contract.{k}={c.get(k)} differs from the frozen bank ({fc.get(k)}): "
                    "a different instrument"
                )
        langs = c.get("native_langs")
        if not langs:  # plan 0032 §2.10: measured per subject (references/gating.md §0)
            err("contract block lacks 'native_langs' (ISO codes, English first; gating.md §0)")
        elif not isinstance(langs, list) or langs[0] != "en":
            err(f"contract.native_langs={langs!r}: a list of ISO codes with 'en' first")
        else:  # plan 0040: an L2 the subject itself thinks in is not a foreign-language item
            for it in items:
                if it.get("lang") and it["lang"] in langs:
                    err(
                        f"{item_key(it)}: lang {it['lang']!r} is one of the subject's native "
                        f"languages {langs}; the L2 must not be a native language"
                    )
    candidate = is_candidate(family, items)
    if candidate:
        print(
            f"  note   candidate bank (no {POST_GATE[family]}): those gate-written fields are "
            "not required yet; validate the gated bank for the full check"
        )
    soft_missing: dict[str, int] = {}
    common = set.intersection(*(set(i) for i in f_items)) if f_items else set()
    ref: dict[str, Any] = {}  # field -> first non-null frozen value (its type is the reference)
    for fi in f_items:
        for k, v in fi.items():
            if v is not None:
                ref.setdefault(k, v)
    for it in items:
        req = required_for(family, it, candidate)
        missing = [k for k in req if k not in it]
        if missing:
            err(f"{item_key(it)}: missing required field(s) {missing}")
        for f in sorted(common - set(it) - set(req) - {"id"}):
            soft_missing[f] = soft_missing.get(f, 0) + 1
        for k in req:
            if k in it and it[k] is not None and k in ref:
                a, b = type(it[k]).__name__, type(ref[k]).__name__
                if a != b and not {a, b} <= {"int", "float"}:
                    err(f"{item_key(it)}.{k}: type {a}, frozen bank uses {b}")
    if soft_missing:
        warn(
            f"fields on every frozen item but missing here (provenance/gate records; fill "
            f"what applies): {soft_missing}"
        )
    ids = [item_key(it) for it in items]
    dup = [k for k, n in Counter(ids).items() if n > 1]
    if dup:
        err(f"duplicate ids/names: {dup[:5]}")
    labels = Counter(re.sub(r"[^A-Za-z0-9._-]", "_", i) for i in ids)
    clash = [k for k, n in labels.items() if n > 1]
    if clash:
        err(f"names collide after label_of() sanitisation: {clash[:5]}")
    frozen_ids = {item_key(it) for it in f_items}
    overlap = sorted(set(ids) & frozen_ids)
    if overlap:
        warn(
            f"{len(overlap)} id(s) reuse a frozen-bank id (e.g. {overlap[0]!r}); pick fresh "
            "ids if the banks may ever be merged or compared item by item"
        )
    if not errors:
        ok(f"{len(items)} items, required fields present")


# ------------------------------------------------------------------ leak / guard lint


def gold_forms(family: str, it: dict[str, Any]) -> list[tuple[str, str]]:
    """(what, form) pairs that must NOT occur in the prompt."""
    out: list[tuple[str, str]] = []
    if family in MT_FAMILIES:
        for u in it.get("units", []):
            forms = u.get("forms") or {"": u.get("match", [])}
            for lang, fs in forms.items():
                for f in fs:
                    out.append((f"unit {u.get('role')}[{lang}]", str(f)))
        if family == "multihop_mt_v2":
            out += [("target", str(t)) for t in [it.get("target"), *it.get("target_alts", [])] if t]
        return out
    if family in ("association", "basic_readout", "multihop", "multilingual", "poetry", "typo"):
        for x in it.get("intermediates", []):
            out.append(("intermediate", str(x)))
        for u in it.get("units", []) or []:
            for m in u.get("match", []):
                out.append((f"unit {u.get('role')}", str(m)))
        if family in ("multihop", "multilingual", "basic_readout") and it.get("target"):
            out.append(("target", str(it["target"])))
        return out
    if family == "user_modeling":
        return [("attr", str(it.get("attr", "")))] + [
            ("intermediate", str(x)) for x in it.get("intermediates", [])
        ]
    if family == "conjunctive_association":
        return [("blocklist", str(w)) for w in (it.get("blocklist") or {}).get("block", [])]
    if family == "role_bound_association":
        bl = it.get("blocklist") or {}
        return [("blocklist", str(w)) for w in bl.get("roles", []) + bl.get("action", [])]
    if family == "relational_multihop":
        return [
            ("composed gold", str(it.get("gold", ""))),
            ("composed gold_alt", str(it.get("gold_alt", ""))),
        ]
    return out


def check_guards(
    family: str, items: list[dict], f_items: list[dict], allow_frozen: bool = False
) -> None:
    print("[2] guards (leak / echo / dedupe)")
    n0 = len(errors)
    for it in items:
        k, text = item_key(it), prompt_text(family, it)
        for what, form in gold_forms(family, it):
            typo_fam = family in ("typo_mt", "multilingual_typo", "typo")
            if typo_fam and fold(form) == fold(it.get("typo_word", "")):
                err(f"{k}: the correction equals the typo word")
            if what == "blocklist" and family == "role_bound_association":
                if form and stem_occurs(form, text):
                    err(f"{k}: blocklisted {form!r} (or an inflection) appears in the stimulus")
            elif form and occurs(form, text):
                err(f"{k}: {what} {form!r} appears in the prompt (echo leak)")
        if family in ("chain_intermediates", "arithmetic_intermediates"):
            for x in it.get("intermediates", []):
                if numeral_in(x, text):
                    err(f"{k}: intermediate {x} appears as a numeral in the prompt")
        if family == "directed_modulation" and occurs(
            str(it.get("concept", "")), str(it.get("assistant", ""))
        ):
            err(f"{k}: the held concept appears in the carrier/assistant text")
        if family == "poetry" and "\n" not in str(it.get("prompt", "")):
            err(f"{k}: poetry prompt has no newline (the read site is the line-one newline)")
        if family in ("conjunctive_association", "role_bound_association"):
            opts = it.get("mc_options", [])
            if it.get("gold_label") not in opts:
                err(f"{k}: gold_label not in mc_options")
            if family == "conjunctive_association" and it.get("contrast_label") not in opts:
                err(f"{k}: contrast_label not in mc_options")
            if len(set(opts)) != len(opts):
                err(f"{k}: duplicate mc_options")
        if family == "role_bound_association" and it.get("direction") not in ("ab", "ba"):
            err(f"{k}: direction must be 'ab' or 'ba'")
        if family == "relational_multihop" and not str(it.get("stimulus", "")).rstrip().endswith(
            "'s"
        ):
            err(f"{k}: stimulus must end with the possessive 's (the read site)")
        if family == "moral_rationale" and "reasons" in it:
            sides = {r.get("supports") for r in it.get("reasons", [])}
            if not sides <= {"yes", "no", "either"}:
                err(f"{k}: reasons[].supports must be 'yes', 'no' or 'either'")
            if it.get("reason_class") not in ("committed", "deliberative"):
                err(f"{k}: reason_class must be committed or deliberative")
            texts = [r.get("text") for r in it.get("reasons", [])]
            for lf in it.get("look_for_reasons", []):
                if lf not in texts:
                    err(f"{k}: look_for_reasons entry is not one of reasons[].text")
    if family in MT_FAMILIES:  # the hard tier's LEAK RULE (families.md, "Lint")
        for it in items:
            pw = words(prompt_text(family, it))
            leaked = sorted(
                {
                    w
                    for what, form in gold_forms(family, it)
                    if not what.startswith("unit language")
                    for w in words(form)
                    if len(w) >= 4 and w.isalpha() and w not in STOPWORDS and w in pw
                }
            )
            if leaked:
                err(f"{item_key(it)}: LEAK RULE: target/form word(s) {leaked} occur in the prompt")
    for it in items:  # bridges: self-answering questions, forms that contain the target
        k = item_key(it)
        for br in it.get("bridges") or []:
            for ans in br.get("answers", []):
                if ans and occurs(str(ans), str(br.get("question", ""))):
                    err(f"{k}: bridge answer {ans!r} appears in its own question")
        targets = [str(t) for t in [it.get("target"), *(it.get("target_alts") or [])] if t]
        if family in ("multihop_mt_v2", "multilingual_multihop"):
            for u in it.get("units", []):
                if not str(u.get("role", "")).startswith("bridge"):
                    continue
                for lang, fs in (u.get("forms") or {}).items():
                    for f in fs:
                        hit = [t for t in targets if occurs(t, str(f)) or occurs(str(f), t)]
                        if hit:
                            err(
                                f"{k}: unit {u.get('role')}[{lang}] form {f!r} contains or is "
                                f"contained in the target {hit[0]!r} (a target readout would "
                                "credit the bridge)"
                            )
        if family == "multihop":
            for x in it.get("intermediates", []):
                hit = [t for t in targets if occurs(t, str(x)) or occurs(str(x), t)]
                if hit:
                    err(f"{k}: intermediate {x!r} contains or is contained in target {hit[0]!r}")
    if family == "role_bound_association":
        pairs = Counter(it.get("pair_id") for it in items)
        bad = [p for p, n in pairs.items() if n != 2]
        if bad:
            err(f"pair_id(s) without exactly two items (ab + ba): {bad[:5]}")
    if family == "arithmetic_intermediates":
        by_name = {str(it.get("name")): it for it in items}
        small_null: list[str] = []
        for it in items:
            k = item_key(it)
            outside = [n for n in it.get("null_set", []) if n not in by_name]
            if outside:
                err(f"{k}: null_set names {len(outside)} item(s) not in this bank: {outside[:3]}")
            wrong = [
                n
                for n in it.get("null_set", [])
                if n in by_name and by_name[n].get("variant") != it.get("variant")
            ]
            if wrong:
                err(f"{k}: null_set names items of another variant: {wrong[:3]}")
            if len(it.get("null_set", [])) < 8:
                small_null.append(k)
            if it.get("pair") and it["pair"] not in by_name:
                warn(f"{k}: twin {it['pair']!r} is not in this bank")
        if small_null:
            warn(
                f"{len(small_null)} item(s) have a null_set < 8 (noisy permutation null; "
                f"grow the variant): {small_null[:5]}"
            )
    # dedupe within the new bank and against the frozen one
    seen: dict[str, str] = {}
    frozen = {norm_prompt(prompt_text(family, it), family): item_key(it) for it in f_items}
    frozen_words = [(item_key(it), words(prompt_text(family, it))) for it in f_items]
    for it in items:
        k, p = item_key(it), norm_prompt(prompt_text(family, it), family)
        if not p:
            continue
        if p in seen and family not in ("directed_modulation",):
            err(f"{k}: same prompt as {seen[p]}")
        seen.setdefault(p, k)
        if p in frozen:
            (warn if allow_frozen else err)(f"{k}: identical prompt to frozen item {frozen[p]}")
            continue
        w = words(prompt_text(family, it))
        if len(w) >= 6 and family not in (
            "chain_intermediates",
            "arithmetic_intermediates",
            "relational_multihop",
            "multi_concept_directed_modulation",
        ):
            best = max(
                ((len(w & fw) / len(w | fw), fk) for fk, fw in frozen_words if fw),
                default=(0.0, ""),
            )
            if best[0] >= 0.8:
                warn(f"{k}: near-duplicate of frozen item {best[1]} (word Jaccard {best[0]:.2f})")
    if family in (
        "multihop",
        "multilingual",
        "multihop_mt_v2",
        "basic_readout",
        "basic_readout_mt",
        "typo",
        "typo_mt",
        "association",
        "poetry",
    ):
        tg = Counter(fold(str((it.get("intermediates") or [it.get("target")])[0])) for it in items)
        rep = [t for t, n in tg.items() if n > 1]
        if rep:
            warn(f"the same scored latent is used by several new items: {rep[:5]}")
    if len(errors) == n0:
        ok("no leak, echo or duplicate found")


# ------------------------------------------------------------------ shadow repo


def bank_name(repo: Path, family: str) -> str:
    """The file name of the family's registered bank (``EvalSpec.bank``: ``items.json``, or a
    versioned ``items_v<N>.json`` once the family switched, plan 0032 §2.12; the multilingual
    families judge ``items_v2.json`` since plan 0054)."""
    for name in sorted((repo / "evals" / family).glob("items_v*.json"), reverse=True):
        init = repo / "src" / "wsbench" / "evals" / family / "__init__.py"
        if init.exists() and name.name in init.read_text(encoding="utf-8"):
            return name.name
    return "items.json"


def make_shadow(repo: Path, family: str, bank: Path, work: Path) -> Path:
    """A throwaway checkout whose evals/<family>/items.json is the new bank: src/ is copied (the
    package resolves REPO_ROOT from its own file), everything else is symlinked."""
    shadow = work / "shadow"
    if shadow.exists():
        shutil.rmtree(shadow)
    shadow.mkdir(parents=True)
    shutil.copytree(repo / "src", shadow / "src", ignore=shutil.ignore_patterns("__pycache__"))
    for p in repo.iterdir():
        if p.name in ("src", "evals", ".git", ".venv", "outputs"):
            continue
        (shadow / p.name).symlink_to(p.resolve())
    (shadow / "evals").mkdir()
    for p in (repo / "evals").iterdir():
        if p.name == family:
            shutil.copytree(p, shadow / "evals" / family, symlinks=True)
            shutil.copy(bank, shadow / "evals" / family / bank_name(repo, family))
        else:
            (shadow / "evals" / p.name).symlink_to(p.resolve())
    return shadow


def run_cli(shadow: Path, args: list[str], *, quiet: bool = False) -> tuple[int, str]:
    env = dict(os.environ, PYTHONPATH=str(shadow / "src"))
    env.pop("WSBENCH_JUDGE_MODEL", None)
    p = subprocess.run(
        [sys.executable, "-m", "wsbench", *args],
        cwd=shadow,
        env=env,
        capture_output=True,
        text=True,
    )
    out = (p.stdout or "") + (p.stderr or "")
    if not quiet and p.returncode != 0:
        print("      " + "\n      ".join(out.strip().splitlines()[-15:]))
    return p.returncode, out


# ------------------------------------------------------------------ dummy readouts


def gold_samples(family: str, it: dict[str, Any], units: list[Any] | None) -> list[str]:
    """Prose samples that a perfect lens would write (used only to check the regex scorer's
    wiring, never as evidence)."""
    if units is not None:
        out = []
        for u in units:
            forms = [f for fs in u.forms.values() for f in fs]
            if forms:
                out.append(f"The answer is {forms[0]}")
        return out
    if it.get("gold_label"):  # MC families: the gold relation, named with the scene's people
        return [f"The model is representing that {it['gold_label']}."]
    if it.get("look_for_reasons"):  # moral: the reasons the judge looks for
        return [f"The model is weighing: {r}." for r in it["look_for_reasons"]]
    names = [str(x) for x in (it.get("intermediates") or [it.get("target") or "x"])]
    return [f"The model is thinking about {n}." for n in names]


NULL_SAMPLE = "Light rain is expected over the weekend."


def ntok(tok: Any, s: str) -> int:
    """Strict token count: min over {s, lower, title} x {bare, leading space}."""
    return min(
        len(tok(v, add_special_tokens=False)["input_ids"])
        for c in {s, s.lower(), s.title()}
        for v in (c, " " + c)
    )


def check_multi_token(items: list[dict], tok: Any) -> None:
    """EVERY non-zh form of a required multi-token unit must be multi-token under this
    tokenizer (a 1-token form is never creditable, so it is dead weight that hides a unit
    which might not survive), and each `mc[role].gold` must be one of that unit's forms and
    multi-token (the MC judge shows it as the correct option)."""
    for it in items:
        k = item_key(it)
        units = {u.get("role"): u for u in it.get("units", [])}
        for role, u in units.items():
            if not (u.get("required", True) and u.get("multi_token", True)):
                continue
            for lang, fs in (u.get("forms") or {}).items():
                if lang == "zh":
                    continue
                single = [f for f in fs if ntok(tok, str(f)) <= 1]
                if single:
                    err(f"{k}: unit {role}[{lang}] has single-token form(s) {single[:3]}")
        for role, m in (it.get("mc") or {}).items():
            gold = str((m or {}).get("gold", ""))
            u = units.get(role) or {}
            forms = [str(f) for fs in (u.get("forms") or {}).values() for f in fs]
            if gold not in forms:
                err(f"{k}: mc[{role}].gold {gold!r} is not one of the unit's forms")
            elif ntok(tok, gold) <= 1:
                err(f"{k}: mc[{role}].gold {gold!r} is a single token")


def build_readouts(
    shadow: Path, family: str, tokenizer: str, work: Path, items: list[dict]
) -> tuple[Path, Path] | None:
    print(f"[4] render + read sites with tokenizer {tokenizer}")
    sys.path.insert(0, str(shadow / "src"))
    try:
        from transformers import AutoTokenizer  # type: ignore[import-not-found]
    except ImportError:
        err("transformers is not installed: run with `uv run --with transformers --with jinja2`")
        return None
    from wsbench import readplan
    from wsbench.multitoken import regex
    from wsbench.produce.producer import _positions
    from wsbench.produce.render import render

    tok = AutoTokenizer.from_pretrained(tokenizer)
    specs = readplan.plan(family)
    by_id = {}
    for it in items:
        by_id[re.sub(r"[^A-Za-z0-9._-]", "_", str(it.get("name") or it.get("id")))] = it
        by_id.setdefault(str(it.get("id") or ""), it)
    header = {}
    units_of: dict[str, list[Any]] = {}
    if family in MT_FAMILIES:
        raw = json.loads(
            (shadow / "evals" / family / bank_name(shadow, family)).read_text(encoding="utf-8")
        )
        header = {k: v for k, v in raw.items() if k != "items"}
        contract = regex.contract_for(header, str(header.get("family", family)))
        for sid, it in by_id.items():
            try:
                units_of[sid] = regex.scored_units(it, contract)
            except ValueError as e:
                err(f"scored_units: {e}")
    if family in MT_FAMILIES:
        check_multi_token(items, tok)
    gold_p, null_p = work / "readouts_gold.jsonl", work / "readouts_null.jsonl"
    n_rows = 0
    with gold_p.open("w", encoding="utf-8") as g, null_p.open("w", encoding="utf-8") as z:
        for s in specs:
            try:
                rd = render(s, tok)
            except Exception as e:
                err(f"{s.id}: render {s.render!r} failed: {e}")
                continue
            pos = _positions(s.positions, rd.tokens)
            if not pos:
                err(f"{s.id}: positions rule {s.positions} selects no token of the render")
                continue
            it = by_id.get(s.id, {})
            if family == "relational_multihop" and rd.decoded[pos[-1]] != "'s":
                err(f'{s.id}: last token is {rd.decoded[pos[-1]]!r}, not the blank "\'s"')
            if family == "poetry":
                tail = tok.decode(rd.ids[pos[0] + 1 :]).strip()
                if "\n" in tail:
                    err(f"{s.id}: more than one newline; the read site must end line ONE")
            if family == "multihop":
                last = rd.decoded[pos[0]]
                if not last.strip():
                    err(
                        f"{s.id}: the read position is a bare whitespace token; set "
                        "readout.offsets so it points at the last word"
                    )
            samples = gold_samples(family, it, units_of.get(s.id))
            for layer in s.layers:
                for p in pos:
                    j = p % len(rd.ids)
                    base = {"id": s.id, "layer": layer, "pos": p, "token": rd.decoded[j]}
                    g.write(json.dumps({**base, "samples": samples}, ensure_ascii=False) + "\n")
                    z.write(
                        json.dumps({**base, "samples": [NULL_SAMPLE]}, ensure_ascii=False) + "\n"
                    )
                    n_rows += 1
    ok(f"{len(specs)} plan rows rendered, {n_rows} dummy cells per arm")
    return gold_p, null_p


# ------------------------------------------------------------------ main


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--family", required=True)
    ap.add_argument("--bank", required=True, type=Path, help="the NEW bank JSON")
    ap.add_argument("--repo", type=Path, default=Path.cwd(), help="workspace-bench checkout")
    ap.add_argument(
        "--tokenizer",
        default="Qwen/Qwen3.6-27B",
        help="HF id whose tokenizer + chat template renders the read plan "
        "(the subject model for a per-model bank)",
    )
    ap.add_argument("--work", type=Path, default=None, help="scratch dir (default: a temp dir)")
    ap.add_argument(
        "--allow-frozen-duplicates",
        action="store_true",
        help="self-test only: do not fail on prompts identical to the frozen bank",
    )
    ap.add_argument(
        "--live-limit",
        type=int,
        default=0,
        help="also run a LIVE `wsbench judge limit=N` on the gold arm (spends)",
    )
    a = ap.parse_args()
    fam, repo = a.family, a.repo.resolve()
    if fam in NOT_AUTHORABLE:
        print(f"{fam}: not authorable as a text bank: {NOT_AUTHORABLE[fam]}", file=sys.stderr)
        return 2
    if fam not in REQUIRED:
        print(f"unknown family {fam!r}; known: {sorted(REQUIRED)}", file=sys.stderr)
        return 2
    frozen_path = repo / "evals" / fam / bank_name(repo, fam)
    if not frozen_path.exists():
        print(f"{frozen_path} not found: run from the repo root or pass --repo", file=sys.stderr)
        return 2
    work = (a.work or Path(tempfile.mkdtemp(prefix=f"wsb-validate-{fam}-"))).resolve()
    work.mkdir(parents=True, exist_ok=True)
    print(f"validating {a.bank} as {fam}  (scratch: {work})")

    header, items, is_list = load_any(a.bank)
    f_header, f_items, f_is_list = load_any(frozen_path)
    check_schema(fam, header, items, is_list, f_header, f_items, f_is_list)
    check_guards(fam, items, f_items, a.allow_frozen_duplicates)
    if errors:
        print(f"\nFAIL: {len(errors)} error(s) before the scorer stage; fix them first.")
        return 1
    if is_candidate(fam, items):
        print(
            f"\nPASS (candidate stage): {len(warnings)} warning(s). The read plan, judge and "
            "capability checks need the gate-written fields: re-run on the gated bank."
        )
        return 0

    print("[3] shadow checkout + loaders")
    shadow = make_shadow(repo, fam, a.bank.resolve(), work)
    rc, out = run_cli(shadow, ["plan", f"families={fam}", f"out={work / 'plan'}"])
    if rc != 0:
        err("`wsbench plan` failed on the new bank")
        return 1
    ok(out.strip().splitlines()[-1])
    if fam in MT_FAMILIES:
        sys.path.insert(0, str(shadow / "src"))
        from wsbench.banks import load_bank
        from wsbench.multitoken.options import option_sets

        _h, its = load_bank(shadow / "evals" / fam / bank_name(shadow, fam))
        try:
            option_sets(its)
            ok("MC option sets build (opts=judge=mc and the lucky-guessing floor)")
        except (KeyError, ValueError) as e:
            err(
                f"MC option sets fail ({type(e).__name__}: {e}); every item needs an `mc` block "
                "per required non-language unit, and `lang` must be a LANG_CONFUSABLES key"
            )

    paths = build_readouts(shadow, fam, a.tokenizer, work, items)
    if paths is None or errors:
        print(f"\nFAIL: {len(errors)} error(s).")
        return 1
    gold, null = paths

    print("[5] real scorer on dummy readouts")
    mt = fam in MT_FAMILIES
    for arm, path in (("gold", gold), ("null", null)):
        out_dir = work / "judged" / arm
        argv = ["judge", f"family={fam}", f"readouts={path}", f"out={out_dir}"]
        if not mt:
            argv.append("dry_run=True")
        rc, out = run_cli(shadow, argv)
        if rc != 0:
            err(f"`wsbench judge` ({arm} arm{'' if mt else ', dry run'}) exited {rc}")
            continue
        res = (
            json.loads((out_dir / fam / "results.json").read_text())
            if (out_dir / fam / "results.json").exists()
            else json.loads((out_dir / "results.json").read_text())
        )
        n = res["n_items"]
        counts = res["counts"]
        if counts.get("n_missing_cells"):
            err(
                f"{arm}: {counts['n_missing_cells']} expected cells missing from the dummy "
                "readouts (read plan and judge disagree)"
            )
        if mt:
            v = res["numbers"]["value"]
            want = 1.0 if arm == "gold" else 0.0
            if v != want:
                fails = [r["id"] for r in res["rows"] if bool(r.get("pass")) != (arm == "gold")]
                err(f"regex scorer: {arm} arm pass_rate {v} != {want} (items {fails[:5]})")
            else:
                ok(f"regex scorer: {arm} arm pass_rate {v} over {n} items")
        else:
            ok(f"dry run ({arm} arm): {n} items loaded, every judge prompt rendered, no call")
            if arm == "gold":
                print(
                    "      first prompt preview: "
                    + " ".join(out.split())[:300].replace(str(work), "<work>")
                )
    if fam in ("directed_modulation", "multi_concept_directed_modulation"):
        pass  # no capability question (compliance gate); see SKILL.md
    else:
        rc, out = run_cli(
            shadow,
            [
                "capable",
                "model=dry/run",
                f"families={fam}",
                "dry_run=True",
                f"out={work / 'capable'}",
            ],
        )
        if rc != 0:
            err("`wsbench capable dry_run=True` failed: the gate question cannot be built")
        else:
            ok("`wsbench capable` builds the capability question for every item")
    if a.live_limit:
        print(f"[6] LIVE judge smoke, limit={a.live_limit} (spends)")
        rc, out = run_cli(
            shadow,
            [
                "judge",
                f"family={fam}",
                f"readouts={gold}",
                f"out={work / 'judged' / 'live'}",
                f"limit={a.live_limit}",
                "allow_missing=True",
            ],
        )
        print("      " + "\n      ".join(out.strip().splitlines()[-8:]))
        if rc != 0:
            err(f"live judge exited {rc}")

    print(
        f"\n{'FAIL' if errors else 'PASS'}: {len(errors)} error(s), {len(warnings)} warning(s)."
        f"  scratch: {work}"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
