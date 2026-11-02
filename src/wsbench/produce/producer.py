"""The producer: one model, one method, readouts in the benchmark's contract. Read a single
cell, a prompt over positions and layers, a plan row, or a whole eval set."""

import json
from collections.abc import Iterable, Iterator
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Self

from wsbench import readplan
from wsbench.readplan import GRID, ReadSpec
from wsbench.registry import REPO_ROOT

from .backend import DEFAULT_MODEL, Backend
from .methods import Method, Readout, method
from .render import Rendered, render, render_text

Positions = int | list[int] | dict[str, Any] | str  # -1 | [3, 5] | {"kind": ...} | "all"
STEERING_TYPES = ("concept", "gaussian")  # the introspection bank's injections (plan 0045)


@dataclass(frozen=True)
class Row:
    """One readouts-contract row plus the token it was read at."""

    id: str
    layer: int
    pos: int
    token: str
    readout: Readout

    def contract(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "layer": self.layer,
            "pos": self.pos,
            "token": self.token,
            **self.readout.row(),
        }


def _positions(rule: Positions, tokens: list[str]) -> list[int]:
    """Indices a positions rule selects. Plain ints count from the end when negative and are
    reported as absolute indices; a plan rule is reported as the plan resolves it (negative for
    ``offset_from_end`` and ``all_from_end``, the convention of the banks that use them)."""
    n = len(tokens)
    if isinstance(rule, int | list):
        want = [rule] if isinstance(rule, int) else list(rule)
        bad = [p for p in want if not -n <= p < n]
        if bad:
            raise ValueError(f"positions {bad} out of range for a {n}-token render")
        return [p % n for p in want]
    if isinstance(rule, str):
        rule = {"kind": rule}
    return readplan.resolve(rule, tokens)


@dataclass
class Producer:
    """``Producer.load(model, method)`` once, then ``read`` / ``read_prompt`` / ``read_spec`` /
    ``run_family``; ``use`` swaps the method without reloading the model. Every method returns
    rows in the readouts contract; ``write`` saves them."""

    backend: Backend
    method: Method
    _vectors: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def load(
        cls,
        model: str = DEFAULT_MODEL,
        method_spec: str | Method = "logit_lens",
        *,
        device: str = "cuda",
        **method_kw: Any,
    ) -> Self:
        m = method(method_spec, **method_kw)  # before the model load, so a typo fails fast
        backend = Backend.load(model, device=device)
        m.bind(backend)
        return cls(backend=backend, method=m)

    def use(self, method_spec: str | Method, **method_kw: Any) -> Self:
        """Switch method on the loaded model (``p.use("jlens")``); returns self."""
        m = method(method_spec, **method_kw)
        m.bind(self.backend)
        self.method = m
        return self

    # ---- the four entry points

    def read(
        self, text: str, pos: int = -1, layer: int | None = None, *, chat: bool = False
    ) -> Row:
        """One cell of one prompt: the readout at ``pos`` (negative counts from the end) after
        block ``layer`` (default: the method's own layer if it has one, else 44)."""
        layers = [layer] if layer is not None else (self.method.layers or [44])
        return self.read_prompt(text, positions=pos, layers=layers, chat=chat)[0]

    def read_prompt(
        self,
        text: str,
        *,
        positions: Positions = -1,
        layers: Iterable[int] | None = None,
        chat: bool = False,
        system: str | None = None,
        item_id: str = "adhoc",
    ) -> list[Row]:
        """A prompt outside any bank, over a positions rule and a layer list (default: the
        method's own layers, else the benchmark grid)."""
        rendered = render_text(text, self.backend.tokenizer, chat=chat, system=system)
        return list(self._read_rendered(item_id, rendered, positions, self._layers(layers, GRID)))

    def read_spec(self, spec: ReadSpec, *, layers: Iterable[int] | None = None) -> list[Row]:
        """A read-plan row: its own render and positions rule; its layers unless the method has
        fixed ones or the caller overrides. A row whose ``extra.steering`` injects a shipped
        vector (introspection, plan 0045 §2.3) is read under that steer (``steering``)."""
        rendered = render(spec, self.backend.tokenizer)
        with self.steering(spec):
            return list(
                self._read_rendered(
                    spec.id, rendered, spec.positions, self._layers(layers, spec.layers)
                )
            )

    def steering(self, spec: ReadSpec) -> AbstractContextManager[None]:
        """The steer a plan row asks for: ``type: none`` (or no steering) is a plain forward;
        ``concept`` / ``gaussian`` inject ``vector_file[vector_row]`` at ``inject_layer`` over the
        inclusive absolute ``token_span`` with dose ``beta`` (the bank's recipe, one definition
        for every arm). Any other type, or a steered row without a shipped vector, is refused."""
        steer = (spec.extra or {}).get("steering") or {}
        kind = steer.get("type", "none")
        if kind == "none":
            return nullcontext()
        if kind not in STEERING_TYPES:
            raise ValueError(
                f"{spec.family}/{spec.id}: unknown steering type {kind!r} (wsbench produce "
                f"applies {', '.join(STEERING_TYPES)}); produce these readouts with your own "
                "steered forward"
            )
        if "vector_file" not in steer or "vector_row" not in steer:
            raise ValueError(
                f"{spec.family}/{spec.id}: a {kind} steer without vector_file / vector_row "
                "(the bank ships no vector for it)"
            )
        a, b = (int(x) for x in steer["token_span"])
        vec = self._vector(str(steer["vector_file"]), int(steer["vector_row"]))
        return self.backend.steered(
            int(steer["inject_layer"]), range(a, b + 1), vec, float(steer["beta"])
        )

    def _vector(self, path: str, row: int) -> Any:
        import numpy as np

        if path not in self._vectors:
            p = Path(path)
            self._vectors[path] = np.load(p if p.is_absolute() else REPO_ROOT / p)
        arr = self._vectors[path]
        if not 0 <= row < len(arr):
            raise ValueError(f"vector_row {row} out of range for {path} ({len(arr)} rows)")
        return arr[row]

    def run_family(
        self,
        family: str,
        out: Path | str,
        *,
        limit: int = 0,
        layers: Iterable[int] | str | None = None,
        items: Iterable[str] | None = None,
        reads: str = "full",
    ) -> Path:
        """Every item of a family into one readouts JSONL, resumable: an item whose rows are
        already in ``out`` is skipped; each item's rows are written in one call. ``layers``:
        None = the plan's, ``"all"`` = every model layer (one forward captures them all), or a
        list. ``reads="lite"`` reads only the lite sites. Writes the sidecar
        ``<out>.meta.json`` declaring reads, sampling, reader and plan_sha (plan 0032 §2.9)."""
        from wsbench import reads as reads_mod
        from wsbench.readouts import write_sidecar

        from .methods import sampling_of

        out = Path(out)
        plan_layers: Any = layers if layers == "all" else None
        specs = readplan.plan(family, layers=plan_layers, reads=reads)
        if layers is not None and layers != "all":
            specs = [replace(s, layers=list(layers)) for s in specs]  # type: ignore[arg-type]
        if items is not None:
            want = set(items)
            specs = [s for s in specs if s.id in want]
        specs = specs[: limit or None]
        done = set()
        if out.exists():
            for line in out.read_text(encoding="utf-8").split("\n"):
                if line.strip():
                    done.add(json.loads(line)["id"])
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("a", encoding="utf-8") as fh:
            for spec in specs:
                if spec.id in done:
                    continue
                rows = self.read_spec(spec)
                fh.write("".join(json.dumps(r.contract(), ensure_ascii=False) + "\n" for r in rows))
                fh.flush()
        name = getattr(self.method, "name", "method")
        write_sidecar(
            out,
            reads=reads,
            sampling=sampling_of(self.method),
            reader=name,
            arm=name,
            layers=sorted({x for s in specs for x in s.layers}),
            plan_sha=reads_mod.plan_sha(family),
        )
        return out

    # ---- internals

    def _layers(self, given: Iterable[int] | None, default: Iterable[int]) -> list[int]:
        if given is not None:
            return list(given)
        return list(self.method.layers or default)

    def _read_rendered(
        self, item_id: str, rendered: Rendered, positions: Positions, layers: list[int]
    ) -> Iterator[Row]:
        pos = _positions(positions, rendered.tokens)
        if not pos:
            return
        idx = [p % len(rendered) for p in pos]  # a plan may report negative offsets
        acts = self.backend.capture(rendered.ids, layers, idx)
        for layer in layers:
            h_all = acts[layer]
            for i, (p, j) in enumerate(zip(pos, idx, strict=True)):
                yield Row(item_id, layer, p, rendered.decoded[j], self.method.read(h_all[i], layer))


def write(rows: Iterable[Row], path: Path | str) -> Path:
    """Rows to a readouts JSONL (one contract row per line)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r.contract(), ensure_ascii=False) + "\n")
    return path
