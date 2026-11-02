"""The model grader for answers a deterministic match cannot decide (aliases, translations, prose
golds). Same rubric as ``capable`` (``GRADE_SYSTEM``); it reads only the subject's answer."""

import hashlib
import json
import time
from collections.abc import Callable

from wsbench.capable.run import GRADE_SYSTEM

from . import store
from .gate import Ask

ATTEMPTS = 4
# families whose latent IS the form (an L2 word, a correct spelling): the shared rubric's
# "a faithful translation is correct" would pass an English answer to an L2 prompt
STRICT_FORM = (
    " EXCEPTION for this question: the expected answer's language, script and spelling are what "
    "is being tested. An answer in a different language (a translation), a transliteration, or a "
    "misspelling of the expected word is NOT correct, even if it means the same thing. Missing "
    "diacritics count as a misspelling. When the expected answer has several words, an answer "
    "giving only some of them (e.g. 'gigi' for 'dokter gigi') is NOT correct."
)


def grader(model: str) -> Callable[[Ask, list[str]], list[bool | None]]:
    """``model`` is a Claude id; the client is ``auth.client()`` (the judges' keyless OAuth token).
    A refused or unparsable grade is ``None``: undecided, never a pass; a 401 stops the run.
    Grades are cached per (question, golds, answer), so repeated samples cost one call."""
    import threading

    import anthropic

    from .auth import PUSH, Session, TokenExpired

    session = Session()
    cache: dict[str, bool | None] = {}
    lock = threading.Lock()
    # persisted across runs (a 401 or a crash no longer redoes every grade): decided verdicts
    # only, so an undecided one is asked again next time
    path = store.REPO_ROOT / "adapted" / ".grade_cache" / f"{model}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        for line in path.read_text(encoding="utf-8").split("\n"):
            if line.strip():
                rec = json.loads(line)
                cache[rec["k"]] = rec["v"]

    def one(ask: Ask, answer: str) -> bool | None:
        strict = bool(ask.meta.get("strict_form"))
        key = hashlib.sha256(  # the rubric is part of the key: a lenient verdict is not reused
            json.dumps(
                [ask.question(), list(ask.golds), answer.strip()] + (["strict2"] if strict else [])
            ).encode()
        ).hexdigest()
        with lock:
            if key in cache:
                return cache[key]
        verdict = _call(ask, answer)
        with lock:
            cache[key] = verdict
            if verdict is not None:
                try:  # the cache is an optimisation: a network-volume I/O error must not kill a run
                    with path.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps({"k": key, "v": verdict}) + "\n")
                except OSError as e:
                    print(f"[grade-cache] write failed ({e}); continuing uncached")
        return verdict

    def _call(ask: Ask, answer: str) -> bool | None:
        expected = "\n".join(f"- {g}" for g in ask.golds)
        user = (
            f"QUESTION:\n{ask.question()}\n\nEXPECTED (any one of):\n{expected}\n\n"
            f'ANSWER:\n{answer}\n\nReply with JSON only: {{"correct": true|false, "why": "..."}}'
        )
        # a transient error or an unparsable reply is retried: an undecided grade fails a strict
        # leak screen (max_rate 0 needs every sample decided), so None must mean "really unsure"
        attempt = 0
        while attempt < ATTEMPTS:
            seen = session.pushed
            try:
                msg = session.create(
                    model=model,
                    max_tokens=200,
                    system=GRADE_SYSTEM + (STRICT_FORM if ask.meta.get("strict_form") else ""),
                    messages=[{"role": "user", "content": user}],
                )
                text = "".join(b.text for b in msg.content if b.type == "text").strip()
                return bool(json.loads(text[text.index("{") : text.rindex("}") + 1])["correct"])
            except anthropic.AuthenticationError as e:
                if not session.refresh(seen):  # no newer token in the Dict
                    raise TokenExpired(PUSH) from e
            except (anthropic.APIError, ValueError, KeyError):
                time.sleep(2**attempt)
                attempt += 1
        return None

    def grade(ask: Ask, answers: list[str]) -> list[bool | None]:
        return [one(ask, a) for a in answers]

    grade.cache = cache  # type: ignore[attr-defined]
    return grade
