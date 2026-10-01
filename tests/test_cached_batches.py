"""CPU execution proves interrupted stochastic batches replay without new subject forwards."""

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

torch = pytest.importorskip("torch")

from test_capture_store import fill, fixture  # noqa: E402

from wsbench.produce.batches import blocks  # noqa: E402
from wsbench.produce.captures import CaptureStore, capture_all  # noqa: E402
from wsbench.produce.journal import ReadoutJournal  # noqa: E402
from wsbench.produce.methods import Readout  # noqa: E402
from wsbench.produce.producer import Producer  # noqa: E402


@dataclass
class RandomReader:
    name: str = "random"
    layers: list | None = None
    _calls: int = 0

    def read_batch(self, vectors, layer):
        self._calls += 1
        return [Readout(samples=[str(float(x))]) for x in torch.rand(len(vectors))]


def test_interrupted_block_replays_exactly_without_global_rng_changes(tmp_path, monkeypatch):
    first, _, union = fixture()
    runtime = {"dtype": "bfloat16"}
    backend = SimpleNamespace(
        model_id="toy", revision="rev", device="cpu", capture_runtime=lambda: runtime
    )
    producer = Producer(backend, RandomReader())
    with CaptureStore(tmp_path / "cache", union, runtime, 3) as store:
        fill(store)
        before = torch.random.get_rng_state()
        full = producer.run_cached(first, "a", tmp_path / "full", store, batch_size=3, seed=42)
        assert torch.equal(before, torch.random.get_rng_state())
        original_append = ReadoutJournal.append
        count = 0

        def interrupted(self, row):
            nonlocal count
            original_append(self, row)
            count += 1
            if count == 1:
                raise RuntimeError("power loss after one row of a batch")

        monkeypatch.setattr(ReadoutJournal, "append", interrupted)
        with pytest.raises(RuntimeError, match="power loss"):
            producer.run_cached(first, "a", tmp_path / "resumed", store, batch_size=3, seed=42)
        monkeypatch.setattr(ReadoutJournal, "append", original_append)
        resumed = producer.run_cached(
            first, "a", tmp_path / "resumed", store, batch_size=3, seed=42
        )
        assert resumed.read_bytes() == full.read_bytes()
        calls = producer.method._calls
        producer.run_cached(first, "a", resumed, store, batch_size=3, seed=42)
        assert producer.method._calls == calls
        with pytest.raises(ValueError, match="configuration changed"):
            producer.run_cached(first, "a", resumed, store, batch_size=2, seed=42)


def test_capture_resume_skips_complete_items_and_validates_backend(tmp_path):
    _, _, union = fixture()
    calls = []
    runtime = {"dtype": "bfloat16"}

    def capture(ids, layers, positions):
        calls.append((ids, layers, positions))
        return {layer: torch.ones(len(positions), 3) * layer for layer in layers}

    backend = SimpleNamespace(
        model_id="toy",
        revision="rev",
        capture_runtime=lambda: runtime,
        tokenizer=SimpleNamespace(decode=lambda ids: str(ids[0])),
        capture=capture,
    )
    with CaptureStore(tmp_path, union, runtime, 3) as store:
        assert capture_all(backend, store)["captured_items"] == 2
        assert capture_all(backend, store)["reused_items"] == 2
        assert len(calls) == 2
        backend.revision = "other"
        with pytest.raises(ValueError, match="subject/revision"):
            capture_all(backend, store)


def test_capture_export_failure_keeps_item_and_budget_stops_next_forward(tmp_path):
    _, _, union = fixture()
    runtime = {"dtype": "bfloat16"}
    calls, events = [], []

    def capture(ids, layers, positions):
        calls.append(ids)
        return {layer: torch.ones(len(positions), 3) for layer in layers}

    backend = SimpleNamespace(
        model_id="toy",
        revision="rev",
        capture_runtime=lambda: runtime,
        tokenizer=SimpleNamespace(decode=lambda ids: str(ids[0])),
        capture=capture,
    )
    with CaptureStore(tmp_path, union, runtime, 3) as store:

        def interrupted_export(event):
            events.append(event)
            assert store.get(union.items[0]) is not None
            from pathlib import Path

            assert Path(event["path"]).is_file()
            raise OSError("export unavailable")

        with pytest.raises(OSError, match="export unavailable"):
            capture_all(backend, store, on_item=interrupted_export)
        assert len(calls) == len(events) == 1

        def expired_budget():
            raise TimeoutError("budget deadline")

        with pytest.raises(TimeoutError, match="budget deadline"):
            capture_all(backend, store, before_item=expired_budget)
        assert len(calls) == 1
        report = capture_all(backend, store, on_item=events.append)
        assert report["reused_items"] == report["captured_items"] == 1
        assert len(calls) == len(events) == 2
        assert events[0]["id"] != events[1]["id"]


def test_block_plan_is_independent_of_progress():
    first, _, _ = fixture()
    plan = blocks(first, "a", 3, 0)
    assert [b.layer for b in plan] == [0, 1]
    assert plan[0].cells == (("one", -2), ("one", -1), ("two", 0))
    assert len({b.seed for b in plan}) == len(plan)


def test_cached_nla_never_loads_subject_and_cannot_recapture(monkeypatch):
    from wsbench.produce.backend import Backend
    from wsbench.produce.methods import NLA

    def never(*args, **kwargs):
        pytest.fail("cached NLA loaded subject weights")

    def bind(reader, backend):
        assert backend.model is None
        reader._reader = object()
        reader._tok = object()

    monkeypatch.setattr(Backend, "load", never)
    monkeypatch.setattr(NLA, "bind", bind)
    producer = Producer.load_cached("subject", NLA(), device="cpu", revision="rev")
    assert producer.backend.model is producer.method._reader
    with pytest.raises(ValueError, match="reader-only"):
        producer.backend.capture([1], [0], [0])
    with pytest.raises(ValueError, match="reader-only"):
        producer.use("logit_lens")


def test_budget_callback_runs_before_generation_and_progress_follows_durable_batch(tmp_path):
    first, _, union = fixture()
    runtime = {"dtype": "bfloat16"}
    backend = SimpleNamespace(
        model_id="toy", revision="rev", device="cpu", capture_runtime=lambda: runtime
    )
    producer = Producer(backend, RandomReader())
    events = []
    path = tmp_path / "readouts.jsonl"

    def stop():
        raise RuntimeError("budget deadline")

    with CaptureStore(tmp_path / "cache", union, runtime, 3) as store:
        fill(store)
        with pytest.raises(RuntimeError, match="budget deadline"):
            producer.run_cached(first, "a", path, store, before_batch=stop)
        assert producer.method._calls == 0 and path.read_bytes() == b""

        def progress(event):
            assert len(path.read_text().splitlines()) >= event["new_cells"]
            events.append(event)

        producer.run_cached(first, "a", path, store, on_batch=progress)
        assert sum(e["new_cells"] for e in events) == first.n_cells


def test_pilot_blocks_resume_into_identical_full_run_without_replaying_complete_blocks(tmp_path):
    first, _, union = fixture()
    runtime = {"dtype": "bfloat16"}
    backend = SimpleNamespace(
        model_id="toy", revision="rev", device="cpu", capture_runtime=lambda: runtime
    )
    producer = Producer(backend, RandomReader())
    events = []
    with CaptureStore(tmp_path / "cache", union, runtime, 3) as store:
        fill(store)
        producer.run_cached(first, "a", tmp_path / "full", store, batch_size=2, seed=7)
        producer.method._calls = 0
        producer.run_cached(
            first,
            "a",
            tmp_path / "pilot",
            store,
            batch_size=2,
            seed=7,
            block_indices=[1],
            on_batch=events.append,
        )
        assert producer.method._calls == 1
        assert len(events) == 1 and events[0]["index"] == 1
        assert events[0]["elapsed_seconds"] > 0
        producer.run_cached(
            first,
            "a",
            tmp_path / "pilot",
            store,
            batch_size=2,
            seed=7,
            block_indices=[1],
            on_batch=events.append,
        )
        assert producer.method._calls == 1 and len(events) == 1
        producer.run_cached(first, "a", tmp_path / "pilot", store, batch_size=2, seed=7)
        # Journal order may differ; compare keyed stochastic outputs and exact provenance.
        assert sorted((tmp_path / "pilot").read_bytes().splitlines()) == sorted(
            (tmp_path / "full").read_bytes().splitlines()
        )
        assert (tmp_path / "pilot.run.json").read_bytes() == (
            tmp_path / "full.run.json"
        ).read_bytes()
        assert producer.method._calls == len(blocks(first, "a", 2, 7))


def test_partial_capture_selection_does_not_mark_full_reader_verified(tmp_path):
    first, _, union = fixture()
    runtime = {"dtype": "bfloat16"}
    backend = SimpleNamespace(
        model_id="toy",
        revision="rev",
        capture_runtime=lambda: runtime,
        tokenizer=SimpleNamespace(decode=lambda ids: str(ids[0])),
        capture=lambda ids, layers, positions: {
            layer: torch.ones(len(positions), 3) for layer in layers
        },
    )
    events = []
    with CaptureStore(tmp_path / "cache", union, runtime, 3) as store:
        report = capture_all(backend, store, item_keys={("a", "one")}, on_item=events.append)
        assert report["scope"] == "selected_items" and report["captured_items"] == 1
        assert len(events) == 1 and events[0]["elapsed_seconds"] > 0
        store.check_reader(first, item_keys={("a", "one")})
        with pytest.raises(ValueError, match="capture missing"):
            store.check_reader(first, reuse_verified=True)
        # A pilot block can use only its required capture, with full-run binding unchanged.
        reader_backend = SimpleNamespace(
            model_id="toy", revision="rev", device="cpu", capture_runtime=lambda: runtime
        )
        producer = Producer(reader_backend, RandomReader())
        producer.run_cached(
            first, "a", tmp_path / "partial", store, batch_size=2, seed=0, block_indices=[0]
        )
        with pytest.raises(ValueError, match="capture missing"):
            producer.run_cached(first, "a", tmp_path / "partial", store, batch_size=2, seed=0)
        report = capture_all(backend, store, on_item=events.append)
        assert report["captured_items"] == report["reused_items"] == 1
        assert report["scope"] == "full_manifest"


@pytest.mark.parametrize("indices", [[], [0, 0], [1, 0], [99], [-1], [True], "0"])
def test_bad_pilot_indices_fail_before_generation(tmp_path, indices):
    from wsbench.produce.batches import indexed_blocks

    first, _, _ = fixture()
    with pytest.raises(ValueError, match="indices"):
        indexed_blocks(blocks(first, "a", 2, 0), indices)
