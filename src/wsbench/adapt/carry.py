"""Families that carry over to a subject without a gate (references/porting.md), verified rather
than assumed: ``jailbreak_recognition`` (every read position re-rendered with the subject's
tokenizer + template must decode to the bank's token) and ``multi_concept_directed_modulation``
(the prefilled sentence must still be ``last_n`` tokens; header layers remapped by depth). A
mismatch stops with what to re-stamp instead of writing a wrong bank.
``python -m wsbench.adapt carry model=<m> [families=jailbreak_recognition,...]``."""

import datetime as dt
import json

from wsbench.registry import frozen_bank_path

from . import store
from .template import markers

CARRY = ("jailbreak_recognition", "multi_concept_directed_modulation")


def _tok(model: str):
    from .author import tokenizer

    return tokenizer(model)


def restamp_read(tok, messages: list[dict]) -> dict:
    """``read`` for the subject's own render (porting.md; the bank's rule): span = first content
    token of the last user turn .. its closing turn marker; tokens = every span position decoded;
    positions = 12 evenly spaced content tokens + turn_end; n_tokens closes an empty assistant
    turn (two tokens past the generation prompt)."""
    from wsbench.evals.jailbreak_recognition.judge import prefix_to_last_user

    out = tok.apply_chat_template(
        prefix_to_last_user(messages),
        tokenize=True,
        add_generation_prompt=True,
        enable_thinking=False,
    )
    ids = list(out["input_ids"] if hasattr(out, "keys") else out)
    mk = markers(tok)  # the subject's own turn markers (ChatML, Gemma's <|turn>, ...)
    end_id, start_id = mk["turn_end_id"], mk["turn_start_id"]
    turn_end = max(i for i, t in enumerate(ids) if t == end_id)
    head = max(i for i, t in enumerate(ids[:turn_end]) if t == start_id)
    start = head + 1
    while start < turn_end and tok.decode([ids[start]]).strip() in ("user", ""):
        start += 1  # skip the role name and the newline after it
    n = turn_end - start
    picks = (
        [start + round(k * (n - 1) / 11) for k in range(12)]
        if n >= 12
        else list(range(start, turn_end))
    )
    return {
        "positions": sorted({*picks, turn_end}),
        "turn_end": turn_end,
        "n_tokens": len(ids) + 2,
        "span": [start, turn_end],
        "tokens": {
            str(i): tok.decode([ids[i]], skip_special_tokens=False)
            for i in range(start, turn_end + 1)
        },
    }


def jailbreak(model: str) -> dict:
    from wsbench.evals.jailbreak_recognition.judge import prefix_to_last_user

    tok, bank = (
        _tok(model),
        json.loads(frozen_bank_path("jailbreak_recognition").read_text()),
    )
    bad = []
    for it in bank["items"]:
        out = tok.apply_chat_template(
            prefix_to_last_user(it["messages"]),
            tokenize=True,
            add_generation_prompt=True,
            enable_thinking=False,
        )
        ids = list(out["input_ids"] if hasattr(out, "keys") else out)
        r = it["read"]
        ok = all(
            int(p) < len(ids) and tok.decode([ids[int(p)]], skip_special_tokens=False) == t
            for p, t in r["tokens"].items()
        )
        end = markers(tok)["turn_end"]
        ok = ok and r["turn_end"] < len(ids) and tok.decode([ids[r["turn_end"]]]) == end
        if not ok:
            bad.append(it["id"])
    restamped = 0
    if bad:  # another tokenizer / template: re-stamp every item from the subject's own render
        for it in bank["items"]:
            it["read"] = restamp_read(tok, it["messages"])
        restamped = len(bank["items"])
    bank["adapt"] = {
        "model": model,
        "frozen": str(dt.date.today()),
        "positions": (
            f"re-stamped from the subject's own render (read.* recomputed for all {restamped} "
            "items; the rule reproduces the frozen bank exactly under the Qwen tokenizer)"
            if restamped
            else f"carried over unchanged: all {len(bank['items'])} items re-rendered with the "
            "subject's tokenizer + chat template, every read token and turn_end matches"
        ),
        "layers": "judge-side grid in 27B layers; wsbench plan remaps by depth",
    }
    store.write_json(store.model_dir(model) / "jailbreak_recognition.json", bank)
    return {"n": len(bank["items"]), "restamped": restamped}


def mcdm(model: str) -> dict:
    from wsbench.produce.render import _chat

    fam = "multi_concept_directed_modulation"
    tok, bank = _tok(model), json.loads(frozen_bank_path(fam).read_text())
    sent = bank["target_sentence"]
    n_sent = len(tok(sent, add_special_tokens=False)["input_ids"])
    for it in bank["items"]:  # every prompt, the bank v2 entity items included (plan 0034)
        ids = _chat(tok, [{"role": "user", "content": it["prompt"]}], prefill=sent)
        if tok.decode(ids[-n_sent:]) != sent:
            raise SystemExit(
                f"mcdm: {it['name']}: the render's last {n_sent} tokens are not the target sentence"
            )
    bank["last_n"] = n_sent  # read every token of the prefilled sentence (12 under Qwen)
    # plan 0032 §2.1.2 / 0034 G2: the family reads readplan.GRID, remapped by depth in `plan`;
    # the bank stores no layers of its own
    bank.pop("layers", None)
    bank["adapt"] = {
        "model": model,
        "frozen": str(dt.date.today()),
        "render": "re-rendered with "
        f"the subject's tokenizer + template: the prefilled sentence is {n_sent} tokens, "
        f"read offsets -{n_sent}..-1",
    }
    store.write_json(store.model_dir(model) / f"{fam}.json", bank)
    return {"n": len(bank["items"]), "last_n": n_sent}


def carry(model: str, families: list[str] | None = None) -> None:
    for fam in families or CARRY:
        res = (jailbreak if fam == "jailbreak_recognition" else mcdm)(model)
        print(f"carry {fam}: {res}")
        if res.get("restamped"):
            change = f"read positions re-stamped from the subject's render ({res['restamped']})"
        elif fam == "jailbreak_recognition":
            change = "carried over unchanged; read positions verified on the subject's render"
        else:
            change = (
                f"carried over; the {res.get('last_n')}-token prefilled sentence verified on the "
                "subject's render for every prompt (layers: readplan.GRID, remapped by depth)"
            )
        store.update_report(model, lambda r, fam=fam, res=res, change=change: r.setdefault(
            "families", {}).setdefault(fam, {}).update(
            status="full", n_items=res["n"], target=res["n"], change=change))  # fmt: skip
