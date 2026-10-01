"""Free-route response contracts beyond the static JSON schema; no gold-label checks."""

import math
from collections.abc import Callable

from wsbench.free_route import active as policy
from wsbench.mc import letter_index
from wsbench.mcjudge import Call

VERSION = "free-structured-v1"


def free_call_contract(prompt_version: str, validate: Callable[[Call, dict], bool]) -> dict:
    if policy() is None:
        return {"prompt_version": prompt_version}
    return {"prompt_version": f"{prompt_version}/{VERSION}", "validate": validate}


def free_response_config() -> dict:
    return {"free_response_validation": VERSION} if policy() is not None else {}


def valid_choice(call: Call, result: dict) -> bool:
    """n_shown includes the explicit escape option, when the prompt has one."""
    choice = result.get("choice") if isinstance(result, dict) else None
    return type(choice) is int and 1 <= choice <= call.meta["n_shown"]


def valid_modulation(call: Call, result: dict) -> bool:
    if not valid_choice(call, result):
        return False
    overlap = result.get("domain_overlap")
    return (
        isinstance(overlap, list)
        and len(overlap) == call.meta["n_shown"] - 1
        and all(type(v) is bool for v in overlap)
    )


def valid_roles(call: Call, result: dict) -> bool:
    # The frozen role-bound builder displays five content options plus escape per role.
    return isinstance(result, dict) and all(
        type(result.get(f"q{i}_choice")) is int and 1 <= result[f"q{i}_choice"] <= 6
        for i in (1, 2, 3)
    )


def valid_letter(call: Call, result: dict) -> bool:
    return (
        isinstance(result, dict)
        and isinstance(result.get("choice"), str)
        and letter_index(result["choice"], call.meta["options"]) is not None
    )


def valid_picks(call: Call, result: dict) -> bool:
    picks = result.get("picks") if isinstance(result, dict) else None
    # Empty selections are valid negatives; duplicates retain native deduplication semantics.
    return isinstance(picks, list) and all(valid_letter(call, pick) for pick in picks)


def valid_values(call: Call, result: dict) -> bool:
    if not isinstance(result, dict):
        return False
    values = result.get("values")
    return (
        isinstance(values, list)
        and len(values) <= call.meta["max_values"]
        and all(type(v) is int for v in values)
        and type(result.get("states_value")) is bool
        and result["states_value"] == bool(values)
    )


def _finite_number(value: object) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        # Native scoring converts to float; oversized JSON integers cannot score.
        return False


def _numeric_list(call: Call, values: object) -> bool:
    return (
        isinstance(values, list)
        and len(values) <= call.meta["max_values"]
        and all(_finite_number(v) for v in values)
    )


def valid_numeric_values(call: Call, result: dict) -> bool:
    return (
        isinstance(result, dict)
        and _numeric_list(call, result.get("values"))
        and type(result.get("states_value")) is bool
        and result["states_value"] == bool(result["values"])
    )


def valid_numeric_batch(call: Call, result: dict) -> bool:
    entries = result.get("entries") if isinstance(result, dict) else None
    if not isinstance(entries, list) or len(entries) != call.meta["n_entries"]:
        return False
    if not all(
        isinstance(e, dict) and type(e.get("k")) is int and _numeric_list(call, e.get("values"))
        for e in entries
    ):
        return False
    return {e["k"] for e in entries} == set(range(1, call.meta["n_entries"] + 1))
