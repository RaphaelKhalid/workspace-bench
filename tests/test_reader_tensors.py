"""CPU tensor checks for exact reader math and safe activation capture."""

import json
import sys
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

torch = pytest.importorskip("torch")
safetensors = pytest.importorskip("safetensors.torch")

from wsbench.produce import reference  # noqa: E402
from wsbench.produce.backend import Backend  # noqa: E402
from wsbench.produce.methods import (  # noqa: E402
    NLA,
    JLens,
    LogitLens,
    OLens,
    RLens,
    Sampling,
    TemplateLens,
    _load_jacobians,
)


def test_template_phrase_ranking_uses_layer_specific_cosine(tmp_path, monkeypatch):
    path = tmp_path / "templates.safetensors"
    directions = torch.tensor(
        [[[20.0, 0.0], [1.0, 1.0], [0.0, 2.0]], [[0.0, 20.0], [1.0, -1.0], [2.0, 0.0]]]
    )
    safetensors.save_file(
        {
            "templates": directions,
            "layers": torch.tensor([20, 44]),
            "word_ids": torch.tensor([51, 63, 89]),
        },
        path,
        metadata={"model_id": "toy"},
    )
    words = tmp_path / "words.txt"
    words.write_text("0\tice cream\n1\tNew Zealand\n2\tsecret plan\n", encoding="utf-8")
    monkeypatch.setattr(
        reference, "locked_file", lambda r, f, v: words if f.endswith(".txt") else path
    )
    reader = TemplateLens(k=2)
    reader.bind(SimpleNamespace(model_id="toy", device="cpu", unembed=torch.zeros(3, 2)))
    first = reader.read(torch.tensor([1.0, 1.0]), 20)
    assert first.tokens[0] == "New Zealand"  # vector magnitude must not determine ranking
    assert first.scores[0] == pytest.approx(1)
    second = reader.read(torch.tensor([1.0, 0.0]), 44)
    assert second.tokens == ["secret plan", "New Zealand"]
    assert second.scores == pytest.approx([1.0, 0.7071])
    with pytest.raises(ValueError):
        reader.read(torch.ones(2), 63)


def test_jacobian_loader_rejects_mislabeled_layers(tmp_path, monkeypatch):
    path = tmp_path / "lens.pt"
    monkeypatch.setattr(reference, "locked_file", lambda *args: path)
    torch.save({"J": {0: torch.eye(2), 1: 2 * torch.eye(2)}, "source_layers": [0, 1]}, path)
    actual = _load_jacobians("r", "f", "cpu", "pinned")
    assert actual.shape == (2, 2, 2)
    assert torch.equal(actual[1], 2 * torch.eye(2))
    torch.save({"J": {0: torch.eye(2)}, "source_layers": [1]}, path)
    with pytest.raises(ValueError, match="disagree"):
        _load_jacobians("r", "f", "cpu", "pinned")
    torch.save({"jacobians": torch.ones(2, 2, 2), "source_layers": [1, 2]}, path)
    with pytest.raises(ValueError, match="not contiguous"):
        _load_jacobians("r", "f", "cpu", "pinned")


class TinyModel(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.model = SimpleNamespace(
            layers=torch.nn.ModuleList([torch.nn.Identity(), torch.nn.Identity()])
        )
        self.adapter_disabled = False
        self.calls = 0
        self.fail = False

    @contextmanager
    def disable_adapter(self):
        self.adapter_disabled = True
        try:
            yield
        finally:
            self.adapter_disabled = False

    def forward(self, ids, logits_to_keep, use_cache):
        assert self.adapter_disabled and use_cache is False and logits_to_keep == 1
        self.calls += 1
        value = ids.float().unsqueeze(-1).repeat(1, 1, 2)
        for block in self.model.layers:
            value = block(value + 1)
        if self.fail:
            raise TypeError("internal model error")
        return value


def test_capture_disables_adapters_and_cache_and_always_removes_hooks():
    model = TinyModel()
    backend = Backend(model, None, "cpu", "toy")
    with pytest.raises(ValueError, match="layer out of range"):
        backend.capture([3, 7], [0, 9], [1])
    assert not model.calls and all(not b._forward_hooks for b in model.model.layers)
    captured = backend.capture([3, 7], [0, 1], [1])
    assert captured[0].tolist() == [[8.0, 8.0]]
    assert captured[1].tolist() == [[9.0, 9.0]]
    assert not model.adapter_disabled and all(not b._forward_hooks for b in model.model.layers)
    model.fail = True
    with pytest.raises(TypeError, match="internal model error"):
        backend.capture([3, 7], [0, 1], [1])
    assert model.calls == 2  # an unrelated TypeError must not cause a second forward
    assert not model.adapter_disabled and all(not b._forward_hooks for b in model.model.layers)


def test_nla_hook_matches_upstream_bf16_add_and_skips_cached_decode(tmp_path, monkeypatch):
    meta = {
        "prompt_templates": {"actor": "<concept>{injection_char}</concept>"},
        "tokens": {
            "injection_char": "x",
            "injection_token_id": 7,
            "injection_left_neighbor_id": 29,
            "injection_right_neighbor_id": 510,
        },
    }
    (tmp_path / "nla_meta.yaml").write_text(json.dumps(meta), encoding="utf-8")
    monkeypatch.setattr(reference, "locked_directory", lambda *args: tmp_path)
    reader_model = torch.nn.Module()
    reader_model.model = torch.nn.Module()
    reader_model.model.layers = torch.nn.ModuleList([torch.nn.Identity(), torch.nn.Identity()])
    tok = SimpleNamespace(apply_chat_template=lambda *a, **k: [29, 7, 510])
    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(
            AutoTokenizer=SimpleNamespace(from_pretrained=lambda *a, **k: tok),
            AutoModelForCausalLM=SimpleNamespace(from_pretrained=lambda *a, **k: reader_model),
        ),
    )
    monkeypatch.setitem(sys.modules, "peft", SimpleNamespace(PeftModel=object))
    lens = NLA(adapter="none")
    lens.bind(SimpleNamespace(device="cpu"))
    vector = torch.tensor([3.14159, 1.2345])
    lens._vec["v"] = vector
    residual = torch.tensor([[[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]]], dtype=torch.bfloat16)
    expected = residual.clone()
    unit = vector.to(torch.bfloat16)
    unit = unit / (unit.norm() + 1e-9)
    expected[:, 1] += expected[:, 1].norm(dim=-1, keepdim=True) * unit
    result = reader_model.model.layers[1](residual.clone())
    assert torch.equal(result, expected)
    single = residual[:, :1].clone()
    assert torch.equal(reader_model.model.layers[1](single.clone()), single)
    tok.apply_chat_template = lambda *a, **k: [28, 7, 510]
    with pytest.raises(ValueError, match="marker neighbors"):
        NLA(adapter="none").bind(SimpleNamespace(device="cpu"))


@pytest.mark.parametrize("reader_type", [LogitLens, JLens, RLens])
def test_vector_batch_matches_individual_readouts(reader_type):
    rng = torch.Generator().manual_seed(40)
    unembed = torch.randn(8, 3, generator=rng)
    tok = SimpleNamespace(convert_ids_to_tokens=lambda ids: [f"token{i}" for i in ids])
    backend = SimpleNamespace(device="cpu", tokenizer=tok, final_norm=torch.nn.LayerNorm(3))
    lens = reader_type(k=3)
    lens._b, lens._w_u = backend, unembed
    if reader_type is not LogitLens:
        lens._jac = torch.randn(2, 3, 3, generator=rng)
    vectors = torch.randn(4, 3, generator=rng)
    single = [lens.read(h, 1) for h in vectors]
    batch = lens.read_batch(vectors, 1)
    assert [r.tokens for r in batch] == [r.tokens for r in single]
    for a, b in zip(single, batch, strict=True):
        assert a.scores == pytest.approx(b.scores, abs=0.0001)


def test_oracle_batch_normalizes_each_vector_and_groups_samples():
    class Model:
        def get_input_embeddings(self):
            return lambda ids: torch.zeros(*ids.shape, 2)

        def generate(self, **kwargs):
            embedded = kwargs["inputs_embeds"]
            assert embedded.shape == (2, 3, 2)
            assert torch.allclose(embedded[:, 1].norm(dim=-1), torch.full((2,), 16000.0))
            assert embedded[0, 1, 1] == 0 and embedded[1, 1, 0] == 0
            return torch.arange(4).reshape(4, 1)

    tok = SimpleNamespace(
        pad_token_id=0,
        eos_token_id=9,
        batch_decode=lambda out, **k: [f"sample{int(row[0])}" for row in out],
    )
    lens = OLens(sampling=Sampling(k=2))
    lens._b = SimpleNamespace(model=Model(), tokenizer=tok, device="cpu")
    lens._slots[20] = ([1, 2, 3], 1)
    readouts = lens.read_batch(torch.tensor([[5.0, 0.0], [0.0, 9.0]]), 20)
    assert [r.samples for r in readouts] == [["sample0", "sample1"], ["sample2", "sample3"]]


def test_nla_batch_repeats_vectors_in_sample_order_and_clears_on_failure():
    lens = NLA(sampling=Sampling(k=2))
    lens._b = SimpleNamespace(device="cpu")
    lens._ids = [1, 7, 3]
    lens._tok = SimpleNamespace(
        pad_token_id=0,
        eos_token_id=9,
        batch_decode=lambda out, **k: [str(int(row[0])) for row in out],
    )

    def generate(ids, **kwargs):
        assert ids.shape == (2, 3)
        assert lens._vec["v"].tolist() == [[1.0, 2.0], [1.0, 2.0], [3.0, 4.0], [3.0, 4.0]]
        return torch.cat([ids.repeat_interleave(2, 0), torch.arange(4).reshape(4, 1)], dim=1)

    lens._reader = SimpleNamespace(generate=generate)
    vectors = torch.tensor([[1.0, 2.0], [3.0, 4.0]])
    assert [r.samples for r in lens.read_batch(vectors, 42)] == [["0", "1"], ["2", "3"]]
    assert lens._vec["v"] is None

    def fail(*args, **kwargs):
        raise RuntimeError("generation failed")

    lens._reader.generate = fail
    with pytest.raises(RuntimeError, match="generation failed"):
        lens.read_batch(vectors, 42)
    assert lens._vec["v"] is None
