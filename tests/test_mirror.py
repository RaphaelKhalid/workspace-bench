"""Verified export progress ignores reports; transfer deadlines cannot stall pod shutdown."""

import json
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from wsbench.produce.export import stage_snapshot
from wsbench.produce.mirror import ExportMirror, MirrorError, pull_once, require_extension
from wsbench.produce.reference import ARM_IDS
from wsbench.produce.watchdog import supervise

RUN = "mirror-test-run"
CONTEXT = {
    "capture_manifest_sha256": "a" * 64,
    "reader_manifests": dict.fromkeys(ARM_IDS, "b" * 64),
}


@pytest.fixture
def remote(tmp_path):
    source, export, destination = [tmp_path / k for k in ("source", "export", "cache")]
    (source / "readouts/jlens").mkdir(parents=True)
    data = source / "readouts/jlens/poetry.jsonl"
    data.write_bytes(b'{"value":1}\n')
    report = source / "readers-run.json"
    report.write_text('{"time":1}')
    paths = ["readouts/jlens/poetry.jsonl", "readers-run.json"]
    latest = [None]

    def publish():
        latest[0] = stage_snapshot(source, export, paths, run_id=RUN, context=CONTEXT)

    publish()

    class Source:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def check(self):
            pass

        def latest(self, run_id):
            assert run_id == RUN
            return latest[0]["sha256"]

        def snapshot(self, sha):
            assert sha == latest[0]["sha256"]
            return latest[0]

        def open_object(self, sha):
            return (export / "objects" / sha).open("rb")

    spec = {"source": {}, "destination": str(destination), "run_id": RUN, "context": CONTEXT}
    return SimpleNamespace(spec=spec, factory=Source, data=data, report=report, publish=publish)


def test_report_churn_is_not_progress_but_appended_readouts_are(remote):
    first = pull_once(remote.spec, source_factory=remote.factory)
    assert first["receipt"]["verified"] and not first["benchmark_coverage_validated"]
    remote.spec["previous_snapshot"] = first["snapshot_sha256"]
    remote.report.write_text('{"time":2}')
    remote.publish()
    second = pull_once(remote.spec, source_factory=remote.factory)
    assert second["snapshot_sha256"] != first["snapshot_sha256"]
    assert second["progress_identity"] == first["progress_identity"]
    remote.spec["previous_snapshot"] = second["snapshot_sha256"]
    remote.data.write_bytes(remote.data.read_bytes() + b'{"value":2}\n')
    remote.publish()
    third = pull_once(remote.spec, source_factory=remote.factory)
    assert third["progress_identity"] != first["progress_identity"]
    assert third["data_bytes"] == 2 * first["data_bytes"]


@pytest.mark.parametrize("replacement", [b"", b'{"value":9}\n', b'{"value":9}\n{"value":2}\n'])
def test_valid_new_snapshot_cannot_rewrite_or_shrink_readouts(remote, replacement):
    first = pull_once(remote.spec, source_factory=remote.factory)
    remote.spec["previous_snapshot"] = first["snapshot_sha256"]
    remote.data.write_bytes(replacement)
    remote.publish()  # A new internally valid snapshot, but an invalid history transition.
    with pytest.raises(ValueError, match=r"shrank|rewrote"):
        pull_once(remote.spec, source_factory=remote.factory)


@pytest.mark.parametrize(
    "path",
    [
        "captures/manifest.json",
        "readouts/jlens/poetry.jsonl.run.json",
        "manifests/jlens.json",
        "captures/" + "a" * 64 + ".npz",
    ],
)
def test_history_protects_capture_and_reader_bindings(tmp_path, path):
    old = {"path": path, "size": 3, "sha256": "a" * 64}
    new = {**old, "sha256": "b" * 64}
    with pytest.raises(ValueError, match="immutable"):
        require_extension({"files": [old]}, {"files": [new]}, tmp_path, lambda: None)


def mirror(tmp_path, **kwargs):
    return ExportMirror(
        source_options={},
        destination=tmp_path / "cache",
        journal=tmp_path / "jobs",
        run_id=RUN,
        context=CONTEXT,
        **kwargs,
    )


def test_periodic_controller_is_nonblocking_and_final_pull_is_fresh(tmp_path):
    clock, processes, automatic = [0.0], [], [False]

    class Process:
        def __init__(self, command, **kwargs):
            assert kwargs["shell"] is False
            assert kwargs["stdout"] == kwargs["stderr"] == subprocess.DEVNULL
            self.path = Path(command[command.index("--result") + 1])
            spec = json.loads(Path(command[command.index("--spec") + 1]).read_text())
            assert spec["source"]["deadline_epoch"] > clock[0]
            self.code, self.killed = None, False
            processes.append(self)
            if automatic[0]:
                self.complete()

        def complete(self):
            self.path.write_text(
                json.dumps(
                    {
                        "status": "verified",
                        "snapshot_sha256": "c" * 64,
                        "progress_identity": "d" * 64,
                        "receipt": {"run_id": RUN, "snapshot_sha256": "c" * 64, "verified": True},
                    }
                )
            )
            self.code = 0

        def poll(self):
            return self.code

        def kill(self):
            self.killed, self.code = True, -9

        def wait(self, timeout):
            assert timeout == 1
            return self.code

    task = mirror(tmp_path, popen=Process, monotonic=lambda: clock[0], wall=lambda: clock[0])
    assert task.tick() is None and len(processes) == 1
    assert task.tick() is None and len(processes) == 1
    processes[0].complete()
    assert task.tick() == "d" * 64
    clock[0] += 30
    task.tick()
    assert len(processes) == 2
    automatic[0] = True
    result = task.finish(10)
    assert processes[1].killed and len(processes) == 3
    assert result["status"] == "verified" and task.closed
    resumed = mirror(tmp_path, popen=Process, monotonic=lambda: clock[0], wall=lambda: clock[0])
    assert resumed.previous == "c" * 64 and resumed.progress == "d" * 64
    resumed.tick()
    resumed.close()


def test_actual_hung_helper_is_killed_and_reaped(tmp_path):
    processes = []

    def start(_command, **kwargs):
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], **kwargs)
        processes.append(process)
        return process

    task = mirror(tmp_path, popen=start, attempt_seconds=0.2)
    try:
        task.tick()
        time.sleep(0.25)
        started = time.monotonic()
        with pytest.raises(MirrorError, match="deadline"):
            task.tick()
        assert time.monotonic() - started < 2
        assert processes[0].poll() is not None and task.process is None
    finally:
        task.close()


def test_no_final_time_means_no_new_transfer(tmp_path):
    task = mirror(tmp_path, popen=lambda *a, **k: pytest.fail("no budget for transfer"))
    assert task.finish(0)["status"] == "not_attempted" and task.closed


def test_report_only_snapshots_cannot_keep_supervised_worker_running(tmp_path, remote):
    clock, events, snapshots = [0.0], [], []

    class Process:
        def __init__(self, command, **kwargs):
            spec_path = Path(command[command.index("--spec") + 1])
            spec = json.loads(spec_path.read_text())
            remote.report.write_text(json.dumps({"time": clock[0]}))
            remote.publish()
            result = pull_once(spec, source_factory=remote.factory)
            snapshots.append(result["snapshot_sha256"])
            Path(command[command.index("--result") + 1]).write_text(json.dumps(result))

        def poll(self):
            return 0

        def wait(self, timeout):
            return 0

    class Worker:
        def poll(self):
            return None

        def kill(self):
            events.append("kill")

    class Guard:
        def check(self):
            pass

        def snapshot(self):
            return {"seconds_until_stop": 100}

    class Stopper:
        pod_id = "testpod123"

        def inspect(self):
            return {"status": "RUNNING"}

        def stop_verified(self, **kwargs):
            events.append("stop")
            return {"verified": True}

    def advance(seconds):
        clock[0] += seconds

    task = mirror(
        tmp_path,
        popen=Process,
        monotonic=lambda: clock[0],
        wall=lambda: clock[0],
        interval_seconds=1,
    )
    result = supervise(
        Worker(),
        Guard(),
        Stopper(),
        mirror=task,
        inactivity_seconds=4,
        poll_seconds=1,
        monotonic=lambda: clock[0],
        sleep=advance,
    )
    assert len(set(snapshots)) >= 2  # Real snapshots and byte receipts changed.
    assert clock[0] == 5 and result["reason"] == "inactivity"
    assert events == ["kill", "stop"] and task.closed


def test_resume_rejects_foreign_journal(tmp_path):
    task = mirror(tmp_path)
    task.accepted_path.write_text(json.dumps({"run_id": "other-run", "context": CONTEXT}))
    with pytest.raises(MirrorError, match="another run"):
        mirror(tmp_path)


def test_final_allowance_includes_cancelling_previous_helper(tmp_path):
    clock, started = [10.0], []

    class Process:
        def poll(self):
            return None

        def kill(self):
            pass

        def wait(self, timeout):
            clock[0] += 1

    task = mirror(tmp_path, monotonic=lambda: clock[0], popen=lambda *a, **k: started.append(k))
    task.process = Process()
    result = task.finish(2)
    assert result["status"] == "not_attempted" and not started
    assert clock[0] == 11 and task.closed
