"""Pilot execution preserves full expectations and resumes into all eight complete outputs."""

import copy
import json
from types import SimpleNamespace

import pytest
from test_compute_worker import compute, snapshot  # noqa: F401
from test_reader_run import Guard
from test_reader_run import setup as reader_setup  # noqa: F401

from wsbench.cell_manifest import digest
from wsbench.produce import completeness, pilot, reader_run, worker
from wsbench.produce.reference import ARM_IDS


@pytest.fixture
def prepared(request, monkeypatch):
    c = request.getfixturevalue("compute")
    monkeypatch.setattr(pilot, "load_lock", reader_run.load_lock)
    keys = {(i.family, i.id) for i in c.manifests[ARM_IDS[0]].items}
    monkeypatch.setattr(completeness, "original_items", lambda: keys)
    plan = pilot.build_plan(c.manifests, batch_size=1)
    c.root = c.root.parent / "pilot"
    return c, plan


def execute(c, plan):
    return worker.run_compute(
        c.manifests,
        c.root,
        c.export,
        run_id="pilot-test",
        guard=Guard(),
        batch_size=1,
        pilot_plan=plan,
    )


@pytest.mark.parametrize("reader_setup", [8], indirect=True)
@pytest.mark.usefixtures("reader_setup")
def test_pilot_resume_then_full_preserves_coverage_and_reuses_work(prepared):
    c, plan = prepared
    result = execute(c, plan)
    assert result["status"] == result["readers"]["status"] == "pilot_complete"
    assert result["scope"] == "operational_pilot"
    assert result["pilot_plan_sha256"] == plan["sha256"]
    assert result["capture"]["captured_items"] == plan["summary"]["capture_items"]
    assert result["capture"]["captured_items"] < plan["summary"]["full_capture_items"]
    for families in result["readers"]["arms"].values():
        assert all(s["selection_complete"] and not s["complete"] for s in families.values())
    assert c.loads == c.releases == list(ARM_IDS)
    saved = snapshot(c)
    assert "manifests/operational-pilot.json" in {r["path"] for r in saved["files"]}
    logs = list((c.root / "measurements").glob("*.jsonl"))
    assert len(logs) == 1
    original_log = logs[0].read_bytes()
    events = [json.loads(line) for line in original_log.splitlines()]
    assert events[0]["data"]["pilot_plan_sha256"] == plan["sha256"]
    assert events[-1]["event"] == "attempt_complete"
    assert events[-1]["data"]["status"] == "pilot_complete"
    assert sum(e["event"] == "capture_item_checkpointed" for e in events) == len(c.forwards)
    report = completeness.verify_export(
        saved, c.root, c.manifests, run_id="pilot-test", batch_size=1
    )
    assert not report["physical_complete"]
    counts = len(c.forwards), len(c.loads)
    again = execute(c, plan)
    assert again["capture"]["captured_items"] == again["readers"]["model_loads"] == 0
    assert (len(c.forwards), len(c.loads)) == counts
    assert logs[0].read_bytes() == original_log
    assert len(list((c.root / "measurements").glob("*.jsonl"))) == 2
    c.export = c.root.parent / "continued-export"
    completed = execute(c, None)
    assert completed["status"] == "complete"
    assert len(c.forwards) == plan["summary"]["full_capture_items"]
    assert completed["readers"]["new_cells"] == (
        plan["summary"]["full_reader_cells"] - plan["summary"]["pilot_reader_cells"]
    )
    report = completeness.verify_export(
        snapshot(c), c.root, c.manifests, run_id="pilot-test", batch_size=1
    )
    assert report["physical_complete"] and not report["benchmark_fidelity_validated"]
    assert len(list((c.root / "measurements").glob("*.jsonl"))) == 3
    names = {r["path"] for r in snapshot(c)["files"]}
    assert "manifests/operational-pilot.json" in names
    assert sum(name.startswith("measurements/") for name in names) == 3


@pytest.mark.parametrize("damage", ["capture", "block", "source", "settings"])
def test_plan_drift_fails_before_model_or_export(prepared, damage):
    c, original = prepared
    plan = copy.deepcopy(original)
    if damage == "capture":
        plan["captures"].pop()
    elif damage == "block":
        plan["readers"][ARM_IDS[-1]]["blocks"].pop()
    elif damage == "source":
        plan["source_sha256"]["worker.py"] = "0" * 64
    else:
        plan["seed"] = 2
    plan["sha256"] = digest({k: v for k, v in plan.items() if k != "sha256"})
    with pytest.raises(ValueError, match="pilot"):
        execute(c, plan)
    assert not c.loads and not c.base_loads and not c.export.exists()


def test_missing_selected_output_cannot_report_pilot_complete(prepared, monkeypatch):
    c, plan = prepared
    original = reader_run.Producer.load_cached

    def broken(*args, **kwargs):
        producer = original(*args, **kwargs)
        producer.run_cached = lambda *a, **kw: None
        return producer

    monkeypatch.setattr(reader_run.Producer, "load_cached", broken)
    with pytest.raises(ValueError, match="incomplete output"):
        execute(c, plan)
    assert c.loads == c.releases == [ARM_IDS[0]]


@pytest.mark.parametrize("prior,session,storage", [(0, 2.01, 0), (1, 1, 0.01), (1.5, 0.51, 0)])
def test_pod_pilot_cap_includes_prior_spending_and_storage(
    prepared, monkeypatch, prior, session, storage
):
    c, plan = prepared
    monkeypatch.setenv("RUNPOD_POD_ID", "testpod123")
    monkeypatch.setenv("WSBENCH_RUN_ID", "testrun123")
    events = []
    monkeypatch.setattr(
        worker,
        "arm_deadline",
        lambda *a: SimpleNamespace(
            check=lambda: None,
            mark_terminal=events.append,
        ),
    )
    guard = Guard()
    guard.budget = SimpleNamespace(
        spent_before_usd=prior,
        session_cap_usd=session,
        retained_storage_reserve_usd=storage,
    )
    with pytest.raises(ValueError, match=r"fit \$2"):
        worker.run_pod_compute(
            c.manifests,
            c.root,
            c.export,
            run_id="testrun123",
            guard=guard,
            stopper=SimpleNamespace(pod_id="testpod123", run_id="testrun123"),
            deadline_journal=c.root.parent / "deadline",
            batch_size=1,
            pilot_plan=plan,
        )
    assert events == ["failed"] and not c.loads and not c.base_loads


def test_plan_file_requires_matching_bound_digest(prepared, tmp_path):
    _, plan = prepared
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan))
    assert pilot.load_plan(path, plan["sha256"]) == plan
    with pytest.raises(ValueError, match="digest"):
        pilot.load_plan(path, "0" * 64)
    plan["captures"].pop()
    path.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="digest"):
        pilot.load_plan(path, plan["sha256"])


def test_pod_pilot_success_arms_deadline_and_marks_process_complete(prepared, monkeypatch):
    c, plan = prepared
    monkeypatch.setenv("RUNPOD_POD_ID", "testpod123")
    monkeypatch.setenv("WSBENCH_RUN_ID", "testrun123")
    events = []

    def arm(*args):
        events.append("armed")
        return SimpleNamespace(check=lambda: events.append("checked"), mark_terminal=events.append)

    monkeypatch.setattr(worker, "arm_deadline", arm)
    guard = Guard()
    guard.budget = SimpleNamespace(
        spent_before_usd=0, session_cap_usd=1.9, retained_storage_reserve_usd=0.1
    )
    result = worker.run_pod_compute(
        c.manifests,
        c.root,
        c.export,
        run_id="testrun123",
        guard=guard,
        stopper=SimpleNamespace(pod_id="testpod123", run_id="testrun123"),
        deadline_journal=c.root.parent / "deadline",
        batch_size=1,
        pilot_plan=plan,
    )
    assert result["status"] == "pilot_complete"
    assert events[0] == "armed" and "checked" in events and events[-1] == "complete"
