"""Pilot batches retain full-run cells/seeds; costs cannot be inferred from omitted arms."""

import copy
from dataclasses import replace

import pytest
from test_reader_run import setup as reader_setup  # noqa: F401

from wsbench.cell_manifest import digest
from wsbench.produce import completeness, pilot, reader_run
from wsbench.produce.batches import blocks
from wsbench.produce.reference import ARM_IDS


@pytest.fixture
def manifests(request, monkeypatch):
    manifests, _, _, _, _ = request.getfixturevalue("reader_setup")
    keys = {(i.family, i.id) for i in manifests[ARM_IDS[0]].items}
    monkeypatch.setattr(completeness, "original_items", lambda: keys)
    old = reader_run.load_lock()
    lock = {**old, "arms": {a: {**v, "open_questions": []} for a, v in old["arms"].items()}}
    monkeypatch.setattr(pilot, "load_lock", lambda: lock)
    return {
        a: replace(
            m, metadata={**m.metadata, "reader_reference": {"arm": a, "lock_sha256": digest(lock)}}
        )
        for a, m in manifests.items()
    }


def test_selection_contains_exact_full_run_batches_and_capture_closure(manifests):
    plan = pilot.build_plan(manifests, batch_size=2, seed=7)
    capture_keys = {(i["family"], i["id"]) for i in plan["captures"]}
    assert set(plan["readers"]) == set(ARM_IDS)
    for arm, record in plan["readers"].items():
        assert record["pilot_cells"] > 0
        full = [
            (family, block)
            for family in sorted({i.family for i in manifests[arm].items})
            for block in blocks(manifests[arm], family, 2, 7)
        ]
        assert {r["family"] for r in record["blocks"]} == {f for f, b in full}
        assert {(r["layer"], len(r["cells"])) for r in record["blocks"]} == {
            (b.layer, len(b.cells)) for f, b in full
        }
        for row in record["blocks"]:
            expected = blocks(manifests[arm], row["family"], 2, 7)[row["index"]]
            assert row["layer"] == expected.layer and row["seed"] == expected.seed
            assert row["cells"] == [list(c) for c in expected.cells]
            assert all((row["family"], i) in capture_keys for i, p in row["cells"])
    assert {s["family"] for s in plan["strata"]} == {i.family for i in manifests[ARM_IDS[0]].items}
    assert not plan["launch_authorized_by_plan"] and not plan["cost_measured"]
    pilot.validate_plan(plan, manifests)


def test_anchors_cover_longest_context_in_each_stratum(manifests):
    plan = pilot.build_plan(manifests)
    source = manifests[ARM_IDS[0]]
    for row in plan["strata"]:
        lengths = [
            len(i.input_ids)
            for i in source.items
            if i.family == row["family"]
            and pilot.upper_bin(len(i.input_ids)) == row["input_length_upper"]
            and pilot.upper_bin(len(i.positions)) == row["position_count_upper"]
        ]
        assert row["anchor_input_tokens"] == max(lengths)


@pytest.mark.parametrize("damage", ["omit_arm", "seed", "block", "source", "hash"])
def test_plan_drift_rejected_even_if_rehashed(manifests, damage):
    plan = copy.deepcopy(pilot.build_plan(manifests))
    if damage == "omit_arm":
        plan["readers"].pop(ARM_IDS[-1])
    elif damage == "seed":
        plan["seed"] += 1
    elif damage == "block":
        plan["readers"][ARM_IDS[0]]["blocks"][0]["cells"].pop()
    elif damage == "source":
        plan["source_sha256"]["backend.py"] = "0" * 64
    else:
        plan["sha256"] = "0" * 64
    if damage != "hash":
        plan["sha256"] = digest({k: v for k, v in plan.items() if k != "sha256"})
    with pytest.raises(ValueError, match="plan differs"):
        pilot.validate_plan(plan, manifests)


def test_missing_arm_cannot_become_a_cheaper_plan(manifests):
    manifests.pop(ARM_IDS[-1])
    with pytest.raises(ValueError, match="all eight"):
        pilot.build_plan(manifests)


def test_batch_planning_hashes_manifest_once_without_changing_seeds(manifests):
    manifest = manifests[ARM_IDS[0]]
    family = manifest.items[0].family

    class CountingManifest:
        reads = 0

        def family(self, name):
            return manifest.family(name)

        @property
        def fingerprint(self):
            self.reads += 1
            return manifest.fingerprint

    counted = CountingManifest()
    plan = blocks(counted, family, 1, 7)
    assert len(plan) > 1 and counted.reads == 1
    for block in plan:
        original = digest(
            ["reader-batches-v1", manifest.fingerprint, family, block.layer, block.cells, 7]
        )
        assert block.seed == int(original[:15], 16)


def test_reader_selection_does_not_expand_every_batch_touching_an_anchor():
    rows = [
        {"family": "a", "index": i, "layer": 2, "seed": i, "cells": [["one", i]]}
        for i in range(100)
    ]
    selected = pilot.select_reader_blocks(rows, {("a", "one")})
    assert len(selected) == 1
    assert selected == pilot.select_reader_blocks(rows, {("a", "one")})
    # Different reader-specific seeds must not force extra subject captures.
    other = [{**row, "seed": row["seed"] + 100} for row in rows]
    assert selected[0]["index"] == pilot.select_reader_blocks(other, {("a", "one")})[0]["index"]
