"""The shared per-layer digest store (``summ_store=<dir>``, final-run speed, 2026-11-01): each
(item, layer) digest is asked ONCE across a family's layer configs, so a union run of layers
[..., L, ...] reuses the digest a ``layers=[L]`` run asked (and the other way round), the store
never serves a digest of other readouts or settings, and the results equal a run without it."""

import dataclasses
import json

import pytest
from summary_fakes import FakeLLM, summary_args
from test_association_v2 import BD, GRID, LAST, answer, keyword_digest, write_cells
from test_audit_fixes_digest import Scripted, _args, _layers_item, _per_layer_reply

from wsbench import digest, llm
from wsbench.cache import Cache, SharedLog
from wsbench.evals.association import SPEC
from wsbench.llm import Spend
from wsbench.readouts import Cell

FAM = "test_af_union"


def _run(tmp_path, out, cells_by_item, layers=None, store=None, fam=FAM, note="t", **extra):
    opts = {**extra, **({digest.STORE_OPT: str(store)} if store else {})}
    args = dataclasses.replace(_args(tmp_path, **opts), layers=layers)
    with Cache(tmp_path / f"{out}.jsonl") as cache:
        return digest.collapse(
            fam,
            cells_by_item,
            args=args,
            cache=cache,
            spend=Spend(),
            preflight=None,
            task_note=note,
        )


def _at(cells, layer):
    return [c for c in cells if c.layer == layer]


def _layers_in(user: str) -> set[str]:
    return {ln.split()[0] for ln in user.splitlines() if ln.startswith("[L")}


def _same(a: digest.Collapse, b: digest.Collapse) -> None:
    assert a.summaries == b.summaries and a.statements == b.statements
    assert a.layer_hist == b.layer_hist and a.unsummarized == b.unsummarized
    assert a.empty == b.empty and a.partial == b.partial


def test_union_reuses_the_single_layer_digest_and_matches_an_uncached_run(tmp_path, monkeypatch):
    fake = Scripted(monkeypatch, _per_layer_reply)
    cells = _layers_item(3)
    store = tmp_path / "store"
    _run(tmp_path, "single20", {"a": _at(cells, 20)}, layers=[20], store=store)
    assert len(fake.calls) == 1
    n0 = len(fake.calls)
    union = _run(tmp_path, "union", {"a": cells}, store=store)
    new = fake.calls[n0:]
    assert len(new) == 2 and all("[L20" not in u for _s, u in new)  # 0 new L20 calls
    assert union.diag["n_store_rows_adopted"] == 1
    n1 = len(fake.calls)
    fresh = _run(tmp_path, "fresh", {"a": cells})  # no store, its own cache: 3 calls
    assert len(fake.calls) - n1 == 3
    _same(union, fresh)
    # the other way round: a layers=[L] run after the union asks nothing
    n2 = len(fake.calls)
    single = _run(tmp_path, "single24", {"a": _at(cells, 24)}, layers=[24], store=store)
    assert len(fake.calls) == n2
    _same(single, _run(tmp_path, "fresh24", {"a": _at(cells, 24)}, layers=[24]))


def test_union_step_sends_the_single_layer_request_byte_for_byte(tmp_path, monkeypatch):
    fake = Scripted(monkeypatch, _per_layer_reply)
    cells = _layers_item(3)
    _run(tmp_path, "single", {"a": _at(cells, 24)}, layers=[24])
    (single,) = fake.calls
    _run(tmp_path, "union", {"a": cells})
    (from_union,) = [c for c in fake.calls[1:] if _layers_in(c[1]) == {"[L24"}]
    assert from_union == single  # same system (budget, rare tier, task note) and same bundle


def test_store_never_serves_other_readouts_or_settings(tmp_path, monkeypatch):
    fake = Scripted(monkeypatch, _per_layer_reply)
    cells = _layers_item(2)
    store = tmp_path / "store"
    _run(tmp_path, "single", {"a": _at(cells, 20)}, layers=[20], store=store)
    other = [dataclasses.replace(c, samples=(c.samples[0] + " x",)) for c in _at(cells, 20)]
    for k, (cbi, kw) in enumerate(
        [
            ({"a": other}, {}),  # other readouts
            ({"a": _at(cells, 20)}, {"summ_max": "7"}),  # other budget
            ({"a": _at(cells, 20)}, {"summ_rare": "3"}),  # other rare tier
            ({"a": _at(cells, 20)}, {"summ_fallback": "default"}),  # other fallback
            ({"a": _at(cells, 20)}, {"note": "another task"}),  # other task note
            ({"a": _at(cells, 20)}, {"summ_effort": "low"}),  # other effort
        ]
    ):
        n0 = len(fake.calls)
        _run(tmp_path, f"o{k}", cbi, layers=[20], store=store, **kw)
        assert len(fake.calls) == n0 + 1, kw


def test_rerun_of_an_out_dir_adopts_nothing(tmp_path, monkeypatch):
    fake = Scripted(monkeypatch, _per_layer_reply)
    store = tmp_path / "store"
    first = _run(tmp_path, "union", {"a": _layers_item(3)}, store=store)
    n_rows = len((tmp_path / "union.jsonl").read_text().splitlines())
    n0 = len(fake.calls)
    again = _run(tmp_path, "union", {"a": _layers_item(3)}, store=store)
    assert len(fake.calls) == n0 and again.diag["n_store_rows_adopted"] == 0
    assert len((tmp_path / "union.jsonl").read_text().splitlines()) == n_rows
    _same(first, again)


def test_one_layer_item_of_a_multi_layer_run_shares_its_layer(tmp_path, monkeypatch):
    fake = Scripted(monkeypatch, _per_layer_reply)
    store = tmp_path / "store"
    b = _at(_layers_item(1), 20)
    b = [dataclasses.replace(c, id="b") for c in b]
    _run(tmp_path, "single", {"b": b}, layers=[20], store=store)
    n0 = len(fake.calls)
    _run(tmp_path, "union", {"a": _layers_item(2), "b": b}, store=store)
    assert len(fake.calls) - n0 == 3  # a@20, a@24, a@28 (its rare line); b@20 reused
    keys = {json.loads(x)["key"] for x in (tmp_path / "union.jsonl").read_text().splitlines()}
    assert "digest:b|all" in keys  # the run-local key is unchanged (old caches still hit)


def _chunky_reply(system, user):
    lines = [ln[2:] for ln in user.splitlines() if ln.startswith("- ")]
    return {"items": [_entry_of(ln) for ln in lines[:3]], "rare": []}


def _entry_of(ln: str) -> dict:
    return {"statement": f"S {ln}", "key": ln.split()[0], "where": "", "evidence": ln, "count": 1}


def test_chunked_and_refused_layers_share_level_chunks_and_final(tmp_path, monkeypatch):
    """A layer over the cap is chunked (chunk + final calls) and a refused single call persists
    its halving level: a union run re-sends none of them."""
    monkeypatch.setattr(llm, "count_tokens", lambda m, ps, **kw: [len(u) // 4 for _s, u in ps])
    big = [
        Cell("a", layer, p, (f"w{p} {'filler ' * 40}L{layer}",), None, None, None)
        for layer in (20, 24)
        for p in range(12)
    ]
    refuse20 = {"n": 0}

    def reply(system, user):
        if _layers_in(user) == {"[L20"} and "w0 " in user and "w11 " in user:
            refuse20["n"] += 1
            return llm.REFUSED_JSON  # the whole-layer bundle (and its first halving) refused
        return _chunky_reply(system, user)

    fake = Scripted(monkeypatch, reply)
    store = tmp_path / "store"
    kw = {"summ_token_cap": "700"}
    single = _run(tmp_path, "single", {"a": _at(big, 20)}, layers=[20], store=store, **kw)
    assert single.summaries.get("a") and refuse20["n"] >= 1 and single.diag["n_chunk_calls"] > 0
    n0 = len(fake.calls)
    union = _run(tmp_path, "union", {"a": big}, store=store, **kw)
    assert all("[L20" not in u for _s, u in fake.calls[n0:])  # level, chunks, final: reused
    n1 = len(fake.calls)
    fresh = _run(tmp_path, "fresh", {"a": big}, **kw)
    assert any("[L20" in u for _s, u in fake.calls[n1:])
    _same(union, fresh)
    assert union.chunks == fresh.chunks and union.served_by == fresh.served_by
    # review r1: the halving level does not key the cap; another cap must not reuse it
    for cap in ("690000", "100000"):
        n2 = len(fake.calls)
        other = _run(tmp_path, f"cap{cap}", {"a": _at(big, 20)}, layers=[20], store=store,
                     summ_token_cap=cap)  # fmt: skip
        mine = _run(tmp_path, f"cap{cap}-fresh", {"a": _at(big, 20)}, layers=[20],
                    summ_token_cap=cap)  # fmt: skip
        n_store = len(fake.calls[n2:]) // 2
        assert n_store >= 1  # nothing shared across caps
        _same(other, mine)
        assert other.chunks == mine.chunks


def test_numbers_union_family_shares_and_joint_numbers_family_does_not(tmp_path, monkeypatch):
    def reply(system, user):
        nums = [ln[2:] for ln in user.splitlines() if ln.startswith("- ")]
        return {"items": [_entry_of(n) for n in nums[:5]], "rare": []}

    fake = Scripted(monkeypatch, reply)
    cells = [_cell("a", ly, p, f"{ly + p} is it") for ly in (20, 24) for p in range(3)]
    for fam, new_calls in (("arithmetic_intermediates", 1), ("chain_intermediates", 1)):
        store = tmp_path / f"store-{fam}"
        _run(tmp_path, f"{fam}-s", {"a": _at(cells, 20)}, layers=[20], store=store, fam=fam)
        n0 = len(fake.calls)
        u = _run(tmp_path, f"{fam}-u", {"a": cells}, store=store, fam=fam)
        assert len(fake.calls) - n0 == new_calls
        if fam == "arithmetic_intermediates":  # per layer: only L24 is new
            assert _layers_in(fake.calls[-1][1]) == {"[L24"}
            fresh = _run(tmp_path, f"{fam}-f", {"a": cells}, fam=fam)
            _same(u, fresh)
        else:  # joint: one call over both layers, nothing shareable
            assert _layers_in(fake.calls[-1][1]) == {"[L20", "[L24"}


def _cell(i: str, layer: int, pos: int, text: str) -> Cell:
    return Cell(i, layer, pos, (text,), None, None, None)


def test_shared_log_sees_other_writers_and_skips_torn_lines(tmp_path):
    path = tmp_path / "s" / "L20.jsonl"
    a, b = SharedLog(path), SharedLog(path)
    assert b.get("k", "f") is None  # no file yet
    a.put("k", "f", {"result": {"x": 1}})
    with path.open("ab") as fh:
        fh.write(b'{"key": "torn", "fp": "f", "res')  # a writer died mid-line
    a.put("k2", "f", {"result": {"x": 2}})
    assert b.get("k", "f")["result"] == {"x": 1}
    assert b.get("k2", "f")["result"] == {"x": 2}  # the leading newline ended the torn line
    assert b.get("torn", "f") is None and b.get("k", "other") is None
    a.put("k", "f", {"result": None})  # a failed row, seen once b's view is max_age old
    assert b.get("k", "f", include_failed=True)["result"] == {"x": 1}  # within max_age
    b.max_age = 0.0
    assert b.get("k", "f", include_failed=True)["result"] is None
    assert b.get("k", "f")["result"] == {"x": 1}


def test_stride_ignores_the_store(tmp_path, monkeypatch):
    Scripted(monkeypatch, _per_layer_reply)
    store = tmp_path / "store"
    _run(tmp_path, "s", {"a": _at(_layers_item(1), 20)}, layers=[20], store=store,
         summ_overflow="stride")  # fmt: skip
    assert not store.exists()


# ---------------------------------------------------------------- end to end (association)


@pytest.fixture
def _registered(real_families):
    return real_families


def _family(tmp_path, monkeypatch, path, out, layers, store):
    fake = FakeLLM.install(
        monkeypatch,
        judge=lambda s, u, sc: answer(u, "birthday", "a birthday cake"),
        digest=keyword_digest(["cake"]),
    )
    extra = {digest.STORE_OPT: str(store)} if store else {}
    args = summary_args(
        path, tmp_path / out, SPEC.judge.prompt_version, items=[BD], layers=layers, extra=extra
    )
    return SPEC.run(args), fake


def _rows(r) -> list[dict]:
    return [{k: v for k, v in row.items() if k != "elapsed"} for row in r.rows]


def test_family_layers_l_then_all_layers_reuses_l(tmp_path, monkeypatch, _registered):
    path = write_cells(tmp_path / "r.jsonl", {(BD, 44, LAST): "- a birthday cake"}, [BD])
    store = tmp_path / "store"
    r44, f44 = _family(tmp_path, monkeypatch, path, "L44", [44], store)
    assert f44.n("digest") == 1 and r44.rows[0]["pass"] is True
    r_all, f_all = _family(tmp_path, monkeypatch, path, "all", None, store)
    digests = [u for n, _s, u in f_all.calls if n == "digest"]
    assert len(digests) == len(GRID) - 1 and all("[L44 " not in u for u in digests)
    assert r_all.config["digest_store"] == str(store.resolve())
    assert "digest_store" not in r_all.config["summarizer"]  # not instrument identity
    fresh, f_fresh = _family(tmp_path, monkeypatch, path, "fresh", None, None)
    assert f_fresh.n("digest") == len(GRID)
    assert _rows(r_all) == _rows(fresh) and r_all.value == fresh.value
    assert r_all.config["prompt_version"] == fresh.config["prompt_version"]
