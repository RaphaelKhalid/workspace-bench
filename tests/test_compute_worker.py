"""Capture-to-reader orchestration preserves resumability and checks every arm before loading."""

import json
import shutil
from types import SimpleNamespace

import numpy as np
import pytest
from test_reader_run import Guard
from test_reader_run import setup as reader_setup  # noqa: F401

from wsbench.produce import worker
from wsbench.produce.budget import BudgetExceededError
from wsbench.produce.captures import CaptureStore
from wsbench.produce.export import restore_snapshot
from wsbench.produce.reference import ARM_IDS


@pytest.fixture
def compute(request, tmp_path, monkeypatch):
    manifests, _, original, loads, releases = request.getfixturevalue("reader_setup")
    root = tmp_path / "compute"
    shutil.copytree(original.root, root / "captures", ignore=shutil.ignore_patterns("*.lock"))
    export = tmp_path / "export"
    forwards, base_loads, base_releases = [], [], []

    class Tensor:
        def __init__(self, array):
            self.array = array

        def detach(self):
            return self

        float = cpu = detach

        def numpy(self):
            return self.array

    class Backend:
        model_id, revision = "toy", "rev"
        unembed = SimpleNamespace(shape=(10, 3))
        tokenizer = SimpleNamespace(decode=lambda ids: str(ids[0]))

        def capture_runtime(self):
            return original.binding["runtime"]

        def capture(self, ids, layers, positions):
            forwards.append(ids)
            return {
                layer: Tensor(np.ones((len(positions), 3), dtype=np.float32)) for layer in layers
            }

    def load(*args, **kwargs):
        assert kwargs["dtype"] == "bfloat16" and kwargs["revision"] == "rev"
        base_loads.append(True)
        return Backend()

    monkeypatch.setattr(worker.Backend, "load", load)
    monkeypatch.setattr(worker, "release_backend", lambda b: base_releases.append(True))
    return SimpleNamespace(
        manifests=manifests,
        root=root,
        export=export,
        original=original,
        loads=loads,
        releases=releases,
        forwards=forwards,
        base_loads=base_loads,
        base_releases=base_releases,
    )


def execute(c, guard=None):
    return worker.run_compute(
        c.manifests, c.root, c.export, run_id="compute-test", guard=guard or Guard()
    )


def snapshot(c):
    pointer = json.loads((c.export / "latest.json").read_text())
    return json.loads((c.export / "snapshots" / (pointer["sha256"] + ".json")).read_text())


def test_complete_capture_then_all_readers_export_restore_and_zero_load_resume(compute):
    c = compute
    result = execute(c)
    assert result["status"] == "complete" and not result["benchmark_fidelity_validated"]
    assert not c.base_loads and not c.forwards
    assert c.loads == c.releases == list(ARM_IDS)
    snap = snapshot(c)
    assert {r["path"] for r in snap["files"]} >= {
        "captures/manifest.json",
        "captures/capture-run.json",
        "manifests/capture.json",
        *[f"readouts/{arm}/a.jsonl" for arm in ARM_IDS],
        *[f"manifests/{arm}.json" for arm in ARM_IDS],
    }
    restored = c.root.parent / "restored"
    restore_snapshot(snap, c.export, restored, run_id="compute-test", context=snap["context"])
    c.root = restored
    c.export = c.root.parent / "restored-export"
    c.loads.clear()
    again = execute(c)
    assert again["capture"]["captured_items"] == again["readers"]["model_loads"] == 0
    assert not c.base_loads and not c.loads
    assert sum(r["path"].endswith(".npz") for r in snapshot(c)["files"]) == len(
        c.original.manifest.items
    )


def test_missing_capture_reuses_other_items_and_releases_base_before_readers(compute, monkeypatch):
    c = compute
    next((c.root / "captures").glob("*.npz")).unlink()
    original = worker.reader_run.run_readers

    def readers(*args, **kwargs):
        assert c.base_releases == [True]
        return original(*args, **kwargs)

    monkeypatch.setattr(worker.reader_run, "run_readers", readers)
    result = execute(c)
    assert result["capture"]["captured_items"] == 1
    assert result["capture"]["reused_items"] == len(c.original.manifest.items) - 1
    assert c.base_loads == c.base_releases == [True] and len(c.forwards) == 1


def test_capture_interruption_forces_export_and_resumes_without_repeating_forward(compute):
    c = compute
    for path in (c.root / "captures").glob("*.npz"):
        path.unlink()

    class Interrupt(Guard):
        def check(self):
            if c.forwards:
                raise BudgetExceededError("after first durable capture")

    with pytest.raises(BudgetExceededError):
        execute(c, Interrupt())
    assert not c.loads and c.base_releases == [True]
    assert sum(r["path"].endswith(".npz") for r in snapshot(c)["files"]) == 1
    result = execute(c)
    assert result["capture"]["reused_items"] == 1
    assert len(c.forwards) == len(c.original.manifest.items)


def test_corrupt_capture_prevents_any_model_load(compute):
    c = compute
    paths = list((c.root / "captures").glob("*.npz"))
    paths[0].unlink()
    paths[-1].write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="invalid capture"):
        execute(c)
    assert not c.base_loads and not c.loads


def test_unresolved_last_arm_prevents_base_capture(compute, monkeypatch):
    c = compute
    original = worker.reader_run.reference_method

    def reader(arm):
        if arm == ARM_IDS[-1]:
            raise ValueError("unresolved checkpoint")
        return original(arm)

    monkeypatch.setattr(worker.reader_run, "reference_method", reader)
    with pytest.raises(ValueError, match="unresolved"):
        execute(c)
    assert not c.base_loads and not c.loads and not c.export.exists()


def test_late_readout_corruption_prevents_recapturing_missing_item(compute):
    c = compute
    execute(c)
    next((c.root / "captures").glob("*.npz")).unlink()
    (c.root / "readouts" / ARM_IDS[-1] / "b.jsonl").write_bytes(b"broken\n")
    c.loads.clear()
    with pytest.raises(ValueError):
        execute(c)
    assert not c.base_loads and not c.loads


def test_fresh_capture_store_gets_runtime_binding_and_export(compute):
    c = compute
    # Use a fresh output directory; no deletion of retained artifacts.
    c.root = c.root.parent / "fresh"
    result = execute(c)
    assert result["capture"]["captured_items"] == len(c.original.manifest.items)
    with CaptureStore.existing(c.root / "captures") as store:
        assert store.binding["runtime"] == c.original.binding["runtime"]
        assert all(store.get(item) is not None for item in store.manifest.items)


@pytest.mark.parametrize("batch_size,seed", [(0, 0), (True, 0), (16, -1), (16, False)])
def test_bad_execution_settings_fail_before_capture_or_export(compute, batch_size, seed):
    c = compute
    with pytest.raises(ValueError, match="integers"):
        worker.run_compute(
            c.manifests,
            c.root,
            c.export,
            run_id="compute-test",
            guard=Guard(),
            batch_size=batch_size,
            seed=seed,
        )
    assert not c.base_loads and not c.loads and not c.export.exists()


def test_expired_budget_does_not_load_or_publish(compute):
    c = compute
    with pytest.raises(BudgetExceededError):
        execute(c, Guard(fail_at=1))
    assert not c.base_loads and not c.loads and not c.export.exists()


@pytest.mark.parametrize("dead", [False, True])
def test_pod_worker_requires_live_deadline_and_always_marks_terminal(compute, monkeypatch, dead):
    c = compute
    monkeypatch.setenv("RUNPOD_POD_ID", "testpod123")
    monkeypatch.setenv("WSBENCH_RUN_ID", "testrun123")
    events = []

    class Handle:
        def check(self):
            if dead:
                raise RuntimeError("deadline exited")

        def mark_terminal(self, status):
            events.append(status)

    def arm(*args):
        events.append("armed")
        return Handle()

    monkeypatch.setattr(worker, "arm_deadline", arm)

    def invoke():
        return worker.run_pod_compute(
            c.manifests,
            c.root,
            c.export,
            run_id="testrun123",
            guard=Guard(),
            stopper=SimpleNamespace(pod_id="testpod123", run_id="testrun123"),
            deadline_journal=c.root.parent / "deadline",
        )

    if dead:
        with pytest.raises(RuntimeError, match="deadline exited"):
            invoke()
        assert events == ["armed", "failed"] and not c.loads and not c.base_loads
    else:
        assert invoke()["status"] == "complete"
        assert events == ["armed", "complete"] and c.loads == list(ARM_IDS)


def test_pod_cli_bad_spec_attempts_owned_shutdown_before_any_model_load(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNPOD_POD_ID", "testpod123")
    monkeypatch.setenv("WSBENCH_RUN_ID", "testrun123")
    monkeypatch.setattr("sys.argv", ["worker", "--spec", str(tmp_path / "missing.json")])
    stopped = []
    monkeypatch.setattr(worker, "request_shutdown", lambda stopper: stopped.append(stopper.pod_id))
    with pytest.raises(FileNotFoundError):
        worker.main()
    assert stopped == ["testpod123"]
