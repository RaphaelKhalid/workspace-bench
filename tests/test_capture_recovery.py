"""Historical capture recovery must never guess token IDs or replace the frozen bank."""

from copy import deepcopy

import pytest

from wsbench.capture_recovery import recover


def inputs():
    item = {"label": "a", "n_pos": 3, "eval_positions": [1], "family": "chat"}
    current = {"model_id": "qwen", "layers": [20], "prompts": [item]}
    historical = deepcopy(current)
    historical["prompts"][0]["tokens"] = ["<start>", " hello", "Ċ"]
    tokenizer = {
        "model": {"vocab": {"Ġhello": 7, "Ċ": 9}},
        "added_tokens": [{"content": "<start>", "id": 12}],
    }
    return historical, current, tokenizer


def test_unique_inverse_preserves_exact_ids_and_metadata():
    historical, current, tokenizer = inputs()
    original = deepcopy(current)
    assert recover(historical, current, tokenizer) == [
        {"id": "a", "input_ids": [12, 7, 9], "read_positions": [1]}
    ]
    assert current == original


@pytest.mark.parametrize("change", ["ambiguous", "unknown", "length", "metadata", "duplicate"])
def test_recovery_fails_closed(change):
    historical, current, tokenizer = inputs()
    if change == "ambiguous":
        tokenizer["model"]["vocab"][" hello"] = 10
    elif change == "unknown":
        historical["prompts"][0]["tokens"][1] = "absent"
    elif change == "length":
        historical["prompts"][0]["tokens"].pop()
    elif change == "metadata":
        historical["prompts"][0]["eval_positions"] = [0]
    else:
        historical["prompts"].append(deepcopy(historical["prompts"][0]))
    with pytest.raises(ValueError):
        recover(historical, current, tokenizer)
