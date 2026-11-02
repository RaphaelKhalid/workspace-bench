from wsbench.judge_config import (
    DEFAULT_JUDGE,
    DEFAULT_REASONING,
    ENV_OVERRIDE,
    JudgeConfig,
    resolve,
)


def test_family_default():
    cfg = JudgeConfig()
    r = resolve(cfg, env={})
    assert r.model == DEFAULT_JUDGE
    assert r.source == "family"
    assert r.pinned is True
    assert r.reasoning is None  # the default is Claude Opus 5.5 (plan 0023): no OpenRouter knob


def test_precedence_flag_over_env_over_family():
    cfg = JudgeConfig(model="claude-sonnet-5", reasoning=None)
    r = resolve(cfg, flag="google/gemini-3.8-flash", env={ENV_OVERRIDE: "x/y"})
    assert r.model == "google/gemini-3.8-flash" and r.source == "flag" and not r.pinned
    r = resolve(cfg, env={ENV_OVERRIDE: "x/y"})
    assert r.model == "x/y" and r.source == "env" and not r.pinned
    r = resolve(cfg, env={ENV_OVERRIDE: ""})
    assert r.model == "claude-sonnet-5" and r.source == "family" and r.pinned


def test_override_equal_to_pin_is_pinned():
    cfg = JudgeConfig(model="claude-sonnet-5")
    r = resolve(cfg, flag="claude-sonnet-5", env={ENV_OVERRIDE: "other"})
    assert r.pinned is True and r.source == "flag"
    r = resolve(cfg, env={ENV_OVERRIDE: "claude-sonnet-5"})
    assert r.pinned is True and r.source == "env"


def test_reasoning_defaults_per_route():
    assert resolve(JudgeConfig(model="claude-sonnet-5"), env={}).reasoning is None
    assert (
        resolve(JudgeConfig(model="google/gemini-3.8-flash"), env={}).reasoning == DEFAULT_REASONING
    )
    # an override that changes the route re-derives the default
    r = resolve(JudgeConfig(model="claude-sonnet-5"), flag="google/gemini-3.8-flash", env={})
    assert r.reasoning == DEFAULT_REASONING
    r = resolve(JudgeConfig(model="google/gemini-3.8-flash"), flag="claude-sonnet-5", env={})
    assert r.reasoning is None


def test_reasoning_keys_are_route_keyed():
    """Plan 0023: a family's reasoning keys ride their own route only (`anthropic_effort` the
    Anthropic one, every other key OpenRouter's), whatever route the family model is on."""
    or_low = JudgeConfig(prompt_version="v", reasoning={"effort": "low"})  # knowledge_cutoff
    or_min = JudgeConfig(prompt_version="v", reasoning={"effort": "minimal"})
    ant = JudgeConfig(
        model=DEFAULT_JUDGE, reasoning={"anthropic_effort": "default"}
    )  # introspection
    # an Opus judge of a default family resolves to None: the fingerprint of the cached
    # `judge_model=claude-opus-5-5` override runs (cache reuse)
    for cfg in (JudgeConfig(), or_low, or_min):
        assert resolve(cfg, env={}).reasoning is None
        assert resolve(cfg, flag="claude-opus-5-5", env={}).reasoning is None
    # OpenRouter overrides keep today's knobs
    assert resolve(or_low, flag="google/gemini-3.8-flash", env={}).reasoning == {"effort": "low"}
    assert resolve(or_min, flag="google/gemini-3.8-flash", env={}).reasoning == DEFAULT_REASONING
    assert resolve(JudgeConfig(), flag="x/y", env={}).reasoning == DEFAULT_REASONING
    # the Anthropic-only key stays on its route and never reaches OpenRouter
    assert resolve(ant, env={}).reasoning == {"anthropic_effort": "default"}
    assert resolve(ant, flag="claude-sonnet-5-5", env={}).reasoning == {
        "anthropic_effort": "default"
    }
    assert resolve(ant, flag="google/gemini-3.8-flash", env={}).reasoning == DEFAULT_REASONING
    # an OpenRouter key on a Claude-pinned family is dropped on the Anthropic route
    assert (
        resolve(
            JudgeConfig(model="claude-sonnet-5", reasoning={"effort": "high"}), env={}
        ).reasoning
        is None
    )
    # pinned semantics: an Opus run of a default family is pinned, a Gemini run is an override
    assert resolve(JudgeConfig(), flag="claude-opus-5-5", env={}).pinned is True
    assert resolve(JudgeConfig(), flag="google/gemini-3.8-flash", env={}).pinned is False


def test_aux_models_default_empty():
    assert dict(JudgeConfig().aux_models) == {}
    assert JudgeConfig().prompt_version == "v1"


def test_family_reasoning_applies_only_on_its_own_route():
    cfg = JudgeConfig(model="claude-opus-5-5", reasoning={"anthropic_effort": "default"})
    assert resolve(cfg).reasoning == {"anthropic_effort": "default"}
    over = resolve(cfg, flag="google/gemini-3.8-flash")  # another route: its own defaults
    assert over.reasoning == DEFAULT_REASONING
    assert resolve(cfg, flag="claude-sonnet-5-5").reasoning == {"anthropic_effort": "default"}
