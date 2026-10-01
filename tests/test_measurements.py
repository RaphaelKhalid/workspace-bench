"""Operational evidence survives failed attempts without treating lost records as free work."""

import json

import pytest

from wsbench.produce.measurements import MeasurementLog, recover_history


class Publisher:
    def __init__(self):
        self.updates = []

    def update(self, paths, **kwargs):
        assert all(p.read_bytes().endswith(b"\n") for p in paths)
        self.updates.extend(paths)


def test_failed_attempt_records_error_type_and_durable_elapsed_time(tmp_path):
    publisher = Publisher()
    with (
        pytest.raises(RuntimeError),
        MeasurementLog(tmp_path, publisher, {"run_id": "test"}) as log,
    ):
        log.record("capture_loading", {})
        raise RuntimeError("arbitrary error text must not be exported")
    events = [json.loads(line) for line in log.path.read_bytes().splitlines()]
    assert [r["sequence"] for r in events] == [0, 1, 2]
    assert events[-1]["event"] == "attempt_failed"
    assert events[-1]["data"] == {"error_type": "RuntimeError"}
    assert events[-1]["attempt_elapsed_seconds"] >= events[0]["attempt_elapsed_seconds"]
    assert b"arbitrary error" not in log.path.read_bytes()


def test_torn_tail_preserved_byte_exactly_before_new_attempt(tmp_path):
    with MeasurementLog(tmp_path, Publisher(), {}) as log:
        log.finish("attempt_complete", {})
    prefix = log.path.read_bytes()
    tail = b'{"schema_version":1,"sequence":'
    with log.path.open("ab") as handle:
        handle.write(tail)
    paths = recover_history(log.path.parent)
    assert log.path.read_bytes() == prefix
    assert log.path.with_suffix(".jsonl.recovered-tail.bin").read_bytes() == tail
    assert len(paths) == 2
    assert recover_history(log.path.parent) == paths


def test_committed_corruption_is_not_repaired(tmp_path):
    with MeasurementLog(tmp_path, Publisher(), {}) as log:
        log.finish("attempt_complete", {})
    rows = [json.loads(line) for line in log.path.read_bytes().splitlines()]
    rows[-1]["sequence"] = 0
    broken = b"".join((json.dumps(row) + "\n").encode() for row in rows)
    log.path.write_bytes(broken)
    with pytest.raises(ValueError, match="committed measurement"):
        recover_history(log.path.parent)
    assert log.path.read_bytes() == broken
