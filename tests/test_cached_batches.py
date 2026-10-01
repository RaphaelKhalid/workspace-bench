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
