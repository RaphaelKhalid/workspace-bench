"""Natural-name screen for new multi-token items: every scored unit must be creditable when a
readout names the latent the everyday way ("carrot", not "carrot root"). Deterministic lint
can't know the everyday name, and authoring keeps padding it (9B audit 95 items, Qwen3-8B 65)."""

import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from . import store

MODEL = "claude-opus-5-5"
PROMPT = (
    "An interpretability benchmark item (family {fam}) has these scored latent units (role -> "
    "accepted forms). For EACH unit, give the single most natural, everyday way a fluent English "
    'speaker would name that latent in a short note (e.g. "carrot", not "carrot root"; '
    '"Microsoft", not "Microsoft Corporation"; "Titanic", not "RMS Titanic"; for a misspelled '
    "word, the correctly spelled word itself; for a person the name people usually use). If the "
    "latent is a non-English word, give the natural form in its own language. Prompt for "
    "context:\n<<<{prompt}>>>\nUnits: {units}\n"
    'Return only JSON: {{"names": {{"<role>": "<natural name>"}}}}'
)


def screen(family: str, items: list[dict]) -> dict[str, list[str]]:
    """``{item_id: problems}`` for items a readout using the everyday name could never pass under
    the family's own regex scorer (``multitoken.regex``). Cached per item content."""
    from wsbench.multitoken.regex import contract_for, layer_unit_hits, scored_units

    from .auth import PUSH, Session, TokenExpired

    header, _ = store.original_bank(family)
    contract = contract_for(header, family)
    path = store.REPO_ROOT / "adapted" / ".grade_cache" / "natural.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    cache: dict[str, dict] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").split("\n"):
            if line.strip():
                rec = json.loads(line)
                cache[rec["k"]] = rec["v"]
    lock, session = threading.Lock(), Session()

    def names_for(it: dict) -> dict[str, str] | None:
        units = {u["role"]: u.get("forms") for u in it.get("units") or []
                 if u.get("role") != "language" and u.get("required", True)}  # fmt: skip
        if not units:
            return {}
        prompt = PROMPT.format(fam=family, prompt=it.get("prompt", ""),
                               units=json.dumps(units, ensure_ascii=False))  # fmt: skip
        key = hashlib.sha256(prompt.encode()).hexdigest()
        with lock:
            if key in cache:
                return cache[key]
        import anthropic

        for _ in range(3):
            seen = session.pushed
            try:
                msg = session.create(model=MODEL, max_tokens=400,
                                     messages=[{"role": "user", "content": prompt}])  # fmt: skip
                text = "".join(b.text for b in msg.content if b.type == "text")
                names = json.loads(text[text.index("{") : text.rindex("}") + 1]).get("names") or {}
                break
            except anthropic.AuthenticationError as e:
                if not session.refresh(seen):
                    raise TokenExpired(PUSH) from e
            except (anthropic.APIError, ValueError):
                continue
        else:
            return None  # undecided: the item is kept (the gate and the audit still check it)
        with lock:
            cache[key] = names
            try:
                with path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"k": key, "v": names}, ensure_ascii=False) + "\n")
            except OSError:
                pass  # cache only
        return names

    def one(it: dict) -> tuple[str, list[str]]:
        names = names_for(it)
        if not names:
            return store.item_id(it), []
        bad = []
        try:
            units = scored_units(it, contract)
        except ValueError:  # no creditable form at all: lint's units: rule rejects it already
            return store.item_id(it), []
        for u in units:
            if not u.required or u.role not in names:
                continue
            if not layer_unit_hits([f"Thinking about {names[u.role]}."], [u]).get(u.role):
                bad.append(f"natural:{u.role} {names[u.role]!r} is not creditable")
        return store.item_id(it), bad

    with ThreadPoolExecutor(16) as pool:
        return dict(pool.map(one, items))


def apply(family: str, items: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Problems for the new items of an MT family (originals are the bank of record)."""
    from .lint import MT

    if family not in MT:
        return {}
    new = [it for it in items if (it.get("adapt") or {}).get("origin", "authored") != "original"]
    return {k: v for k, v in screen(family, new).items() if v} if new else {}
