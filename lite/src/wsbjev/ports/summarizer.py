"""The shared J-lens summarizer (interp-v1): token bag -> 1-2 sentences of prose, free text.

Two modes:

- Default (Jev cannot write text): the "interpretation" IS the rendered bag
  (``tok (score) | tok (score) | ...``), so the family's judge prompt shows the bag where it would
  have shown the summary. This is a PROTOCOL DEVIATION (flagged high risk by the Astra review).
- ``WSBJEV_INTERP_FROM=<vllm-cache.jsonl>:<served model name>``: replay the OFFICIAL summarizer
  output that an LLM already produced from the unchanged interp prompt (e.g. Qwen3.6-27B via
  vLLM). The summarizer prompt is looked up by its hash; the judge then sees exactly the
  official two-stage input. A missing summary returns None (cell unjudged), never the raw bag,
  so the two modes can never mix silently.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .base import Direct, JevCall, Port, between

_TABLE: dict[str, dict] | None = None


def _replay_table() -> tuple[dict[str, dict], str] | None:
    global _TABLE
    spec = os.environ.get("WSBJEV_INTERP_FROM", "")
    if not spec:
        return None
    path, _, model = spec.rpartition(":")
    if _TABLE is None:
        _TABLE = {}
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            k = row.get("k", "")
            if k.startswith(f"{model}|interp|") and isinstance(row.get("r"), dict):
                _TABLE[k.rsplit("|", 1)[1]] = row["r"]
    return _TABLE, model


class Summarizer(Port):
    name = "summarizer"
    schema_names = ("interp",)

    def build(self, system: str, user: str, schema: dict) -> JevCall | Direct:
        rep = _replay_table()
        if rep is not None:
            from ..alt_routes import prompt_hash

            r = rep[0].get(prompt_hash(system, user))
            txt = (r or {}).get("interpretation", "")
            return Direct({"interpretation": txt} if isinstance(txt, str) and txt.strip() else None)
        bag = between(user, "TOKEN READOUTS:\n").strip()
        return Direct({"interpretation": bag} if bag else None)

    def parse(self, answers: dict, call: JevCall, schema: dict) -> dict | None:  # never called
        return None


PORTS = [Summarizer()]
