"""Per-family judge configuration and the flag > env > family-pin override resolution."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from wsbench.llm import route

DEFAULT_JUDGE = "claude-opus-5-5"  # plan 0023 (Camila 2026-10-29)
DEFAULT_REASONING = {"effort": "minimal"}  # OpenRouter judges: Gemini cannot turn reasoning off
ANTHROPIC_REASONING_KEYS = frozenset({"anthropic_effort"})  # every other key is OpenRouter's
ENV_OVERRIDE = "WSBENCH_JUDGE_MODEL"


@dataclass(frozen=True)
class JudgeConfig:
    model: str = DEFAULT_JUDGE
    prompt_version: str = "v1"
    reasoning: dict | None = None  # route-keyed; see resolve()
    aux_models: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ResolvedJudge:
    model: str
    reasoning: dict | None
    pinned: bool  # True iff model == config.model (no override took effect)
    source: Literal["flag", "env", "family"]


def resolve(
    config: JudgeConfig, *, flag: str | None = None, env: Mapping[str, str] | None = None
) -> ResolvedJudge:
    env = env or {}
    env_model = env.get(ENV_OVERRIDE, "")
    if flag:
        model, source = flag, "flag"
    elif env_model:
        model, source = env_model, "env"
    else:
        model, source = config.model, "family"
    # a family's reasoning keys are route-specific: `anthropic_effort` rides the Anthropic route,
    # every other key the OpenRouter one; keys for the other route are dropped, so an Opus judge
    # of a family with an OpenRouter-only setting resolves to None (plan 0023)
    is_anthropic = route(model) == "anthropic"
    kept = {
        k: v
        for k, v in (config.reasoning or {}).items()
        if (k in ANTHROPIC_REASONING_KEYS) == is_anthropic
    }
    reasoning: dict | None = kept or (None if is_anthropic else dict(DEFAULT_REASONING))
    return ResolvedJudge(
        model=model, reasoning=reasoning, pinned=model == config.model, source=source
    )
