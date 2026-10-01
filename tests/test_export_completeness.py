"""A byte-valid export can still have missing, duplicated or incorrectly bound benchmark data."""

import hashlib
import json
from dataclasses import replace

import pytest
from test_compute_worker import compute as compute_setup  # noqa: F401
from test_compute_worker import execute, snapshot
from test_reader_run import setup as reader_setup  # noqa: F401

from wsbench.cell_manifest import digest
from wsbench.produce import completeness
from wsbench.produce.export import restore_snapshot
from wsbench.produce.reference import ARM_IDS


@pytest.fixture
def exported(request, monkeypatch):
    c = request.getfixturevalue("compute_setup")
    execute(c)
    c.snap = snapshot(c)
    restored = c.root.parent / "audit-restored"
    restore_snapshot(c.snap, c.export, restored, run_id="compute-test", context=c.snap["context"])
    c.root = restored
    keys = {(i.family, i.id) for i in c.original.manifest.items}
    monkeypatch.setattr(completeness, "original_items", lambda: keys)
    c.loads.clear()
    return c


def check(c):
    return completeness.verify_export(c.snap, c.root, c.manifests, run_id="compute-test")


def hashes(root):
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


def rebind(c, name):
    data = (c.root / name).read_bytes()
    for row in c.snap["files"]:
        if row["path"] == name:
            row.update(size=len(data), sha256=hashlib.sha256(data).hexdigest())
    c.snap["sha256"] = digest({k: v for k, v in c.snap.items() if k != "sha256"})


def test_complete_restored_outputs_are_verified_without_writes_or_model_loads(exported):
    c = exported
    before = hashes(c.root)
    result = check(c)
    assert result["physical_complete"] and result["export_bytes_verified"]
    assert result["expected_reader_cells"] == sum(m.n_cells for m in c.manifests.values())
    assert result["present_reader_cells"] == result["expected_reader_cells"]
    assert result["captures"]["present_items"] == len(c.original.manifest.items)
    assert result["captures"]["present_vectors"] == c.original.manifest.n_cells
    assert not result["judging_complete"] and not result["benchmark_fidelity_validated"]
    assert hashes(c.root) == before and not c.loads and not c.base_loads


@pytest.mark.parametrize("kind", ["capture", "readout"])
def test_transport_valid_snapshot_can_be_physically_incomplete(exported, kind):
    c = exported
    if kind == "capture":
        name = next(r["path"] for r in c.snap["files"] if r["path"].endswith(".npz"))
    else:
        name = f"readouts/{ARM_IDS[-1]}/b.jsonl"
    (c.root / name).unlink()
    c.snap["files"] = [r for r in c.snap["files"] if r["path"] != name]
    c.snap["sha256"] = digest({k: v for k, v in c.snap.items() if k != "sha256"})
    before = hashes(c.root)
    result = check(c)
    assert not result["physical_complete"] and name in result["missing_files"]
    assert result["export_bytes_verified"] and hashes(c.root) == before


def test_missing_cell_is_counted_even_when_report_claims_complete(exported):
    c = exported
    name = f"readouts/{ARM_IDS[-1]}/b.jsonl"
    path = c.root / name
    lines = path.read_bytes().splitlines(keepends=True)
    path.write_bytes(b"".join(lines[1:]))
    rebind(c, name)
    result = check(c)
    assert result["missing_reader_cells"] == 1 and not result["physical_complete"]
    assert not result["missing_files"]  # File counts alone would falsely pass.


@pytest.mark.parametrize(
    "corruption", ["duplicate", "foreign", "token", "torn", "sidecar", "capture"]
)
def test_content_invalidity_is_not_hidden_by_valid_transport_hashes(exported, corruption):
    c = exported
    name = f"readouts/{ARM_IDS[0]}/a.jsonl"
    path = c.root / name
    lines = path.read_bytes().splitlines(keepends=True)
    if corruption == "duplicate":
        path.write_bytes(b"".join([*lines, lines[0]]))
    elif corruption == "torn":
        path.write_bytes(b"".join(lines) + b'{"id":')
    elif corruption in {"token", "foreign"}:
        row = json.loads(lines[0])
        row["token" if corruption == "token" else "id"] = "different"
        path.write_bytes(json.dumps(row).encode() + b"\n" + b"".join(lines[1:]))
    elif corruption == "sidecar":
        name += ".run.json"
        data = json.loads((c.root / name).read_text())
        data["execution"]["seed"] += 1
        (c.root / name).write_text(json.dumps(data), encoding="utf-8")
    else:
        name = next(r["path"] for r in c.snap["files"] if r["path"].endswith(".npz"))
        (c.root / name).write_bytes(b"invalid npz")
    rebind(c, name)
    before = hashes(c.root)
    with pytest.raises(ValueError):
        check(c)
    assert hashes(c.root) == before and not c.loads


def test_modified_restored_bytes_rejected_before_semantic_validation(exported):
    c = exported
    name = f"readouts/{ARM_IDS[0]}/a.jsonl"
    with (c.root / name).open("ab") as stream:
        stream.write(b"tamper")
    with pytest.raises(ValueError, match="export object"):
        check(c)


def test_unlisted_extra_data_cannot_be_used_by_later_judging(exported):
    c = exported
    (c.root / f"readouts/{ARM_IDS[0]}/unknown.jsonl").write_text("{}\n")
    with pytest.raises(ValueError, match="not bound"):
        check(c)


def test_unlisted_existing_output_cannot_fill_snapshot_gap(exported):
    c = exported
    name = f"readouts/{ARM_IDS[0]}/a.jsonl"
    c.snap["files"] = [r for r in c.snap["files"] if r["path"] != name]
    c.snap["sha256"] = digest({k: v for k, v in c.snap.items() if k != "sha256"})
    with pytest.raises(ValueError, match="unlisted local"):
        check(c)


def test_subset_or_missing_reader_cannot_claim_full_completion(exported):
    c = exported
    original = c.manifests[ARM_IDS[0]]
    c.manifests[ARM_IDS[0]] = replace(original, items=original.items[:-1])
    with pytest.raises(ValueError, match="original benchmark items"):
        check(c)
    c.manifests.pop(ARM_IDS[0])
    with pytest.raises(ValueError, match="all eight"):
        check(c)
