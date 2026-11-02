"""Draft ``evals/role_bound_association/roles_v1.json`` with Opus 5.5 (role_bound plan 0055 C2.1).

One call: every bank role, with the gold sentences and blocklisted role words of the items that
use it, goes to Opus, which writes ``{role: {"terms": [...], "near": [...]}}``. The draft is then
reviewed by hand and must pass ``tests/test_role_bound_lexicon.py``; this script is provenance,
not part of the judge. No API key: run with the keyless ant profile token, e.g.

    TOK=$(ant auth print-credentials --access-token) && \\
      env -u ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN=$TOK \\
      .venv/bin/python scripts/author_roles_lexicon.py --out /tmp/roles_draft.json
"""

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BANK = REPO / "evals/role_bound_association/items.json"
MODEL = "claude-opus-5-5"

SYSTEM = """You build a role lexicon for a benchmark judge. Each benchmark item is a short story \
in which one person (with a ROLE such as "grandparent" or "police officer") does something to \
another. A judge later reads noisy free text decoded from a language model and must decide \
whether a statement refers to the person holding a given role. It does so mechanically: a role is \
referred to iff one of its TERMS occurs in the statement as a whole word (Latin script, \
case-insensitive, word-bounded; a hyphen is a word boundary) or, for Chinese, as an exact \
substring.

For EVERY role you are given, write:
- "terms": English and Chinese forms that name the SAME person in such a scene: the role word, \
its plural, true synonyms, gendered forms (policeman / policewoman), informal forms (cop, mom), \
and scene-generic hyponyms that clearly denote the same person (an athlete in a swimming scene \
may be called a "swimmer"). Include 2-6 common Chinese forms (simplified). Lower case except \
acronyms. Never include a word that names a DIFFERENT, neighbouring role: "parent" must not list \
"grandmother", "grandparent" must not list "mother" or "parent", "mother" must not list \
"grandmother" or "stepmother", "teacher" must not list "principal" or "social worker". Never \
include a word so generic it would name almost anyone (person, man, woman, someone, he, she). \
Avoid words that are also common words with another meaning in such scenes ("star" for a \
celebrity is fine only if unavoidable; prefer leaving it out).
- "near": 2-4 OTHER roles (singular English role nouns) that a noisy reader plausibly confuses \
with this one but that are different people: kinship neighbours (parent: grandparent, \
stepparent, guardian), rank or job neighbours (teacher: principal, professor, tutor, social \
worker; doctor: nurse, paramedic, surgeon-in-training; police officer: detective, security \
guard). A near role must share no term with this role: none of its own words may occur, as a \
whole word, inside any of this role's terms, and vice versa.

Return ONLY a JSON object mapping each given role string exactly as given to \
{"terms": [...], "near": [...]}, with no commentary."""


def roles_context() -> dict[str, dict]:
    items = json.loads(BANK.read_text(encoding="utf-8"))
    ctx: dict[str, dict] = defaultdict(lambda: {"scenes": set(), "blocked": set()})
    for it in items:
        for r in (it["role_a"], it["role_b"]):
            ctx[r]["scenes"].add(it["gold_label"])
            ctx[r]["blocked"].update(it["blocklist"]["roles"])
    return {
        r: {"scenes": sorted(v["scenes"]), "words_used_in_these_scenes": sorted(v["blocked"])}
        for r, v in sorted(ctx.items())
    }


def main() -> None:
    import anthropic

    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    ctx = roles_context()
    user = (
        f"ROLES ({len(ctx)}), each with the gold sentences of its items and the role words "
        "(of BOTH people) blocked from those stories:\n" + json.dumps(ctx, indent=1)
    )
    client = anthropic.Anthropic()
    with client.messages.stream(
        model=MODEL,
        max_tokens=64000,
        system=SYSTEM,
        messages=[{"role": "user", "content": user}],
    ) as stream:
        msg = stream.get_final_message()
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    m = re.search(r"\{.*\}", text, re.S)
    if m is None:
        raise SystemExit(f"no JSON object in the reply: {text[:400]!r}")
    lex = json.loads(m.group(0))
    missing = sorted(set(ctx) - set(lex))
    a.out.write_text(json.dumps(lex, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {a.out}: {len(lex)} roles, missing {missing}, usage {msg.usage}")


if __name__ == "__main__":
    main()
