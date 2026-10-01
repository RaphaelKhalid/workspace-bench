"""Interrupted exports resume verified objects; receipts cannot hide corruption or path escape."""

import io
from copy import deepcopy

import pytest

from wsbench.cell_manifest import digest
from wsbench.produce.export import (
    SnapshotPublisher,
    receive_snapshot,
    relative_output,
    restore_snapshot,
    stage_snapshot,
    validate_snapshot,
)
from wsbench.produce.reference import ARM_IDS

RUN = "export-test-run"
CONTEXT = {
    "capture_manifest_sha256": "a" * 64,
    "reader_manifests": dict.fromkeys(ARM_IDS, "b" * 64),
}


@pytest.fixture
def staged(tmp_path):
    source, export, cache = (tmp_path / name for name in ["source", "export", "cache"])
    (source / "manifests").mkdir(parents=True)
    (source / "manifests/a.json").write_bytes(b'{"version":1}')
    (source / "readouts/jlens").mkdir(parents=True)
    (source / "readouts/jlens/poetry.jsonl").write_bytes(b'{"row":1}\n')
    paths = ["manifests/a.json", "readouts/jlens/poetry.jsonl"]
    snapshot = stage_snapshot(source, export, paths, run_id=RUN, context=CONTEXT)
    return source, export, cache, paths, snapshot


def test_interrupted_transfer_resume_and_restore_are_byte_exact(staged, tmp_path):
    source, export, cache, paths, snapshot = staged
    calls = []

    def remote(sha):
        calls.append(sha)
        if len(calls) == 2:
            raise ConnectionError("link interrupted")
        return (export / "objects" / sha).open("rb")

    with pytest.raises(ConnectionError):
        receive_snapshot(snapshot, cache, remote, run_id=RUN, context=CONTEXT)
    assert not list(cache.glob("receipts/*.json"))
    assert len(list((cache / "objects").iterdir())) == 1
    calls.clear()

    def available(sha):
        calls.append(sha)
        return (export / "objects" / sha).open("rb")

    receipt = receive_snapshot(snapshot, cache, available, run_id=RUN, context=CONTEXT)
    assert receipt["verified"] and receipt["reused_objects"] == 1 and len(calls) == 1
    calls.clear()
    receipt = receive_snapshot(snapshot, cache, available, run_id=RUN, context=CONTEXT)
    assert receipt["transferred_bytes"] == 0 and not calls
    restored = tmp_path / "restored"
    restore_snapshot(snapshot, cache, restored, run_id=RUN, context=CONTEXT)
    assert all((restored / p).read_bytes() == (source / p).read_bytes() for p in paths)
    restore_snapshot(snapshot, cache, restored, run_id=RUN, context=CONTEXT)
    (restored / paths[0]).write_bytes(b"user change")
    with pytest.raises(ValueError, match="mismatch"):
        restore_snapshot(snapshot, cache, restored, run_id=RUN, context=CONTEXT)
    assert (restored / paths[0]).read_bytes() == b"user change"


@pytest.mark.parametrize("data", [b"short", b"x" * 1000, b"x" * 13])
def test_transfer_corruption_never_writes_receipt_or_unverified_object(staged, data):
    _, _, cache, _, snapshot = staged
    with pytest.raises(ValueError, match=r"truncated|oversized|hash mismatch"):
        receive_snapshot(snapshot, cache, lambda sha: io.BytesIO(data), run_id=RUN, context=CONTEXT)
    assert not list(cache.glob("receipts/*.json"))
    assert not list(cache.glob("objects/*"))


def test_existing_corrupt_cache_is_not_silently_redownloaded(staged):
    _, _, cache, _, snapshot = staged
    (cache / "objects").mkdir(parents=True)
    row = snapshot["files"][0]
    (cache / "objects" / row["sha256"]).write_bytes(b"z" * row["size"])
    with pytest.raises(ValueError, match="hash mismatch"):
        receive_snapshot(
            snapshot,
            cache,
            lambda sha: pytest.fail("unexpected transfer"),
            run_id=RUN,
            context=CONTEXT,
        )


@pytest.mark.parametrize(
    "name",
    [
        "../.ssh/id_rsa",
        "captures/../../secret",
        "manifests/.env",
        "/manifests/a.json",
        "manifests//a.json",
        "manifests/CON.json",
        "manifests/a.json:stream",
        "keys.json",
    ],
)
def test_unsafe_or_nonbenchmark_paths_rejected(name):
    with pytest.raises(ValueError):
        relative_output(name)


def test_changed_provenance_and_case_collisions_fail_before_transfer(staged):
    _, _, cache, _, original = staged
    for mutate in [
        lambda s: s.update(run_id="other-run"),
        lambda s: s["files"].append({**s["files"][0], "path": "manifests/A.json"}),
    ]:
        snapshot = deepcopy(original)
        mutate(snapshot)
        snapshot["sha256"] = digest({k: v for k, v in snapshot.items() if k != "sha256"})
        with pytest.raises(ValueError):
            receive_snapshot(
                snapshot,
                cache,
                lambda sha: pytest.fail("unexpected transfer"),
                run_id=RUN,
                context=CONTEXT,
            )


def test_partial_journal_cannot_be_staged_and_expanding_snapshots_reuse_other_files(staged):
    source, export, cache, paths, snapshot = staged

    def open_remote(sha):
        return (export / "objects" / sha).open("rb")

    receive_snapshot(snapshot, cache, open_remote, run_id=RUN, context=CONTEXT)
    journal = source / paths[1]
    journal.write_bytes(journal.read_bytes() + b'{"torn":')
    with pytest.raises(ValueError, match="checkpoint line"):
        stage_snapshot(source, export, paths, run_id=RUN, context=CONTEXT)
    journal.write_bytes(b'{"row":1}\n{"row":2}\n')
    newer = stage_snapshot(source, export, paths, run_id=RUN, context=CONTEXT)
    receipt = receive_snapshot(newer, cache, open_remote, run_id=RUN, context=CONTEXT)
    assert receipt["reused_objects"] == 1
    assert receipt["transferred_bytes"] == journal.stat().st_size


def test_deadline_failure_keeps_valid_objects_and_no_receipt(staged):
    _, export, cache, _, snapshot = staged
    checks = []

    def check():
        checks.append(True)
        if len(checks) == 3:
            raise TimeoutError("deadline")

    with pytest.raises(TimeoutError):
        receive_snapshot(
            snapshot,
            cache,
            lambda sha: (export / "objects" / sha).open("rb"),
            run_id=RUN,
            context=CONTEXT,
            check=check,
        )
    assert len(list(cache.glob("objects/*"))) == 1
    assert not list(cache.glob("receipts/*.json"))


def test_file_and_total_limits_are_checked(staged):
    *_, snapshot = staged
    snapshot = deepcopy(snapshot)
    snapshot["files"][0]["size"] = 11 * 1024**3
    snapshot["sha256"] = digest({k: v for k, v in snapshot.items() if k != "sha256"})
    with pytest.raises(ValueError, match="transfer bound"):
        validate_snapshot(snapshot, run_id=RUN, context=CONTEXT)


def test_publisher_carries_old_files_forward_and_recovers_after_restart(staged):
    source, export, _, paths, _ = staged
    publisher = SnapshotPublisher(source, export, run_id=RUN, context=CONTEXT)
    first = publisher.update([source / paths[0]], force=True)
    assert len(first["files"]) == 1
    restarted = SnapshotPublisher(source, export, run_id=RUN, context=CONTEXT)
    second = restarted.update([source / paths[1]], force=True)
    assert len(second["files"]) == 2
    assert first["files"][0] in second["files"]
    assert len(list(export.glob("objects/*"))) == 2


def test_published_readouts_cannot_change_their_existing_prefix(staged):
    source, export, _, paths, snapshot = staged
    (source / paths[1]).write_bytes(b'{"row":9}\n')
    with pytest.raises(ValueError, match="prefix changed"):
        stage_snapshot(source, export, [paths[1]], run_id=RUN, context=CONTEXT, previous=snapshot)
