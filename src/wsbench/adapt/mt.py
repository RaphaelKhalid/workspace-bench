"""Stamp the tokenizer-tied fields of a multi-token item from the subject's tokenizer:
``units[].match`` (the flattened forms) and ``probe_token_lens`` (the count the regex scorer
filters on). The count is the source rule (global-workspace ``gen_hard_mt.make_ntok``): the fewest
tokens over bare / leading-space x as-is / lower / title spellings, without special tokens."""

import copy
from typing import Any


def ntok(tok: Any, text: str) -> int:
    spellings = {text, text.lower(), text.title()}
    return min(
        len(tok.encode(v, add_special_tokens=False)) for s in spellings for v in (s, " " + s)
    )


def stamp(item: dict, tok: Any, include_target: bool = False) -> dict:
    item = copy.deepcopy(item)
    lens: dict[str, Any] = {"units": {}}
    for unit in item.get("units") or []:
        forms = unit.get("forms") or {}
        unit["match"] = [f for fs in forms.values() for f in fs]
        lens["units"][unit["role"]] = {
            lang: [ntok(tok, f) for f in fs] for lang, fs in forms.items()
        }
    if include_target:
        lens["target"] = ntok(tok, item["target"])
        lens["target_alts"] = [ntok(tok, a) for a in item.get("target_alts") or []]
    item["probe_token_lens"] = lens
    return item


def creditable(item: dict) -> bool:
    """Every required multi-token unit keeps at least one form longer than one token."""
    lens = (item.get("probe_token_lens") or {}).get("units", {})
    for unit in item.get("units") or []:
        multi = any(n > 1 for ls in lens.get(unit["role"], {}).values() for n in ls)
        if unit.get("required") and unit.get("multi_token", True) and not multi:
            return False
    return True
