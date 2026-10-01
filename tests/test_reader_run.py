"""Complete outputs avoid model loads; corruption and unresolved arms fail before any GPU work."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_capture_store import fill, fixture

from wsbench.cell_manifest import CellManifest, digest
from wsbench.produce import reader_run as run
from wsbench.produce.batches import binding_for
from wsbench.produce.budget import BudgetExceededError
from wsbench.produce.captures import CaptureStore, capture_union
from wsbench.produce.journal import ReadoutJournal


class Guard:
    def __init__(self, fail_at=None):
        self.checks, self.fail_at = 0, fail_at

    def check(self):
        self.checks += 1
        if self.checks == self.fail_at:
            raise BudgetExceededError("test deadline")

    def snapshot(self):
        return {"checks": self.checks}


@pytest.fixture
def setup(tmp_path, monkeypatch):
    base, _, _ = fixture()
    base = replace(base, items=base.items + tuple(replace(i, family="b") for i in base.items))
    lock = {
        "subject": {"model": "toy", "revision": "rev"},
        "arms": {
            arm: {"layer_policy": "intersection", "supported_layers": [0, 1]} for arm in run.ARM_IDS
        },
    }
    manifests = {
        arm: replace(
            base,
            metadata={
                **base.metadata,
                "reader_reference": {"arm": arm, "lock_sha256": digest(lock)},
            },
        )
        for arm in run.ARM_IDS
    }
    union = capture_union(list(manifests.values()))
    monkeypatch.setattr(CellManifest, "verify_banks", lambda self: None)
    monkeypatch.setattr(run, "load_lock", lambda: lock)
    monkeypatch.setattr(run, "reference_method", lambda arm: SimpleNamespace(name=arm, k=1))
    loads, releases = [], []
    runtime = {
        "dtype": "bfloat16",
        "backend_source_sha256": hashlib.sha256(
            Path(run.__file__).with_name("backend.py").read_bytes()
        ).hexdigest(),
    }

    class FakeProducer:
        def __init__(self, reader):
            self.method = reader

        def run_cached(
            self, manifest, family, path, store, *, batch_size, seed, before_batch, on_batch
        ):
            before_batch()
            binding = binding_for(
                manifest,
                family,
                run.public_config(self.method),
                store.binding,
                runtime,
                batch_size=batch_size,
                seed=seed,
            )
            with ReadoutJournal(path, binding=binding, expected=manifest.expected(family)) as j:
                before = len(j.present)
                for item in manifest.family(family):
                    for _, layer, pos in sorted(item.cells):
                        if (item.id, layer, pos) not in j.present:
                            j.append(
                                {
                                    "id": item.id,
                                    "layer": layer,
                                    "pos": pos,
                                    "token": item.tokens[item.positions.index(pos)],
                                    "tokens": ["x"],
                                    "scores": [1.0],
                                }
                            )
                j.checkpoint()
                on_batch(
                    {
                        "family": family,
                        "generated_cells": len(j.present) - before,
                        "new_cells": len(j.present) - before,
                    }
                )

    def load(model, reader, **kwargs):
        loads.append(reader.name)
        return FakeProducer(reader)

    monkeypatch.setattr(run.Producer, "load_cached", load)
    monkeypatch.setattr(run, "release", lambda producer: releases.append(producer.method.name))
    with CaptureStore(tmp_path / "store", union, runtime, 3) as store:
        fill(store)
        yield manifests, tmp_path / "out", store, loads, releases


def test_one_load_per_arm_and_zero_loads_for_complete_resume(setup):
    manifests, out, store, loads, releases = setup
    result = run.run_readers(manifests, out, store, guard=Guard())
    assert result["status"] == "complete"
    assert result["model_loads"] == len(run.ARM_IDS)
    assert result["new_cells"] == sum(m.n_cells for m in manifests.values())
    assert loads == releases == list(run.ARM_IDS)  # Two families per one model load.
    again = run.run_readers(manifests, out, store, guard=Guard())
    assert again["model_loads"] == again["new_cells"] == 0
    assert loads == list(run.ARM_IDS)


@pytest.mark.parametrize("corruption", ["token", "duplicate", "provenance", "samples", "nan"])
def test_late_corruption_rejected_before_loading_earlier_pending_arm(setup, corruption):
    manifests, out, store, loads, _ = setup
    run.run_readers(manifests, out, store, guard=Guard())
    (out / run.ARM_IDS[0] / "a.jsonl").unlink()
    path = out / run.ARM_IDS[-1] / "b.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    if corruption == "token":
        rows[-1]["token"] = "wrong"
    elif corruption == "duplicate":
        rows.append(rows[-1])
    elif corruption == "samples":
        rows[-1].pop("tokens")
        rows[-1].pop("scores")
        rows[-1]["samples"] = ["wrong kind"]
    elif corruption == "nan":
        rows[-1]["scores"] = [float("nan")]
    else:
        sidecar = path.with_suffix(".jsonl.run.json")
        value = json.loads(sidecar.read_text())
        value["execution"]["seed"] = 99
        sidecar.write_text(json.dumps(value))
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    loads.clear()
    with pytest.raises(ValueError):
        run.run_readers(manifests, out, store, guard=Guard())
    assert not loads


def test_budget_interruption_keeps_completed_family_and_releases_reader(setup):
    manifests, out, store, loads, releases = setup
    with pytest.raises(BudgetExceededError):
        run.run_readers(manifests, out, store, guard=Guard(fail_at=4))
    report = json.loads((out / "readers-run.json").read_text())
    assert report["status"] == "interrupted"
    assert report["arms"][run.ARM_IDS[0]]["a"]["complete"]
    assert not report["arms"][run.ARM_IDS[0]]["b"]["complete"]
    assert loads == releases == [run.ARM_IDS[0]]
    result = run.run_readers(manifests, out, store, guard=Guard())
    assert result["status"] == "complete"
    assert result["new_cells"] == sum(m.n_cells for m in manifests.values()) - 5


def test_unresolved_last_reader_stops_before_any_model_load(setup, monkeypatch):
    manifests, out, store, loads, _ = setup
    original = run.reference_method

    def factory(arm):
        if arm == run.ARM_IDS[-1]:
            raise ValueError("unresolved checkpoint")
        return original(arm)

    monkeypatch.setattr(run, "reference_method", factory)
    with pytest.raises(ValueError, match="unresolved"):
        run.run_readers(manifests, out, store, guard=Guard())
    assert not loads


def test_all_arms_required_even_when_some_are_expensive(setup):
    manifests, out, store, loads, _ = setup
    del manifests["oracle_sft"]
    with pytest.raises(ValueError, match="eight-arm"):
        run.run_readers(manifests, out, store, guard=Guard())
    assert not loads


@pytest.mark.parametrize("change", ["subject", "layers"])
def test_subject_and_layer_contracts_checked_before_loading(setup, change):
    manifests, out, store, loads, _ = setup
    arm = run.ARM_IDS[-1]
    original = manifests[arm]
    manifests[arm] = (
        replace(original, metadata={**original.metadata, "model": "wrong"})
        if change == "subject"
        else replace(original, items=tuple(replace(i, layers=(63,)) for i in original.items))
    )
    with pytest.raises(ValueError, match=r"subject|unsupported layers"):
        run.run_readers(manifests, out, store, guard=Guard())
    assert not loads
