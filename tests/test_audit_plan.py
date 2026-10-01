"""Audit grouping holds related scenarios together and never reads outcome fields."""

from wsbench.audit_plan import group_key


def test_related_agentic_variants_and_controls_share_group():
    ids = [
        "am-blackmail-full",
        "am-blackmail_explicit-america_none",
        "am-blackmail_none-none_restriction",
    ]
    assert {group_key("agentic_misalignment", name, {}) for name in ids} == {"agentic/blackmail"}


def test_topic_and_conversation_groups_ignore_labels():
    for family, metadata in [
        ("moral_rationale", {"topic_id": "topic"}),
        ("jailbreak_recognition", {"source_id": "conversation"}),
    ]:
        a = group_key(family, "a", {**metadata, "pass": True, "gold": "A"})
        b = group_key(family, "b", {**metadata, "pass": False, "gold": "B"})
        assert a == b
    assert group_key("hallucination", "chat-1", {}) == group_key("jlens_concept_pr", "chat-1", {})
