"""The one readout contract every family reads, plus the in-house gen-dir converter.

One JSONL row per cell::

    {"id": "<item id>", "layer": 36, "pos": 33, "samples": ["...", "..."]}
    {"id": "<item id>", "layer": 36, "pos": 33, "tokens": ["Ġword", "..."], "scores": [10.8, 9.9]}

Either row may carry an optional ``"token": "<read-site token>"`` string. A file is
all-prose or all-tokens. Malformed lines are counted, never fatal. ``tokens`` are decoded from
byte-level BPE to text here, once (``wsbench.bpe``); the read-site ``token`` is already text.
"""

import json
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

from wsbench.bpe import decode_token

Kind = Literal["prose", "tokens"]
SKIP_CATEGORIES = (
    "malformed",
    "duplicate",
    "mixed_kind",
    "unknown_id",
    "layer_not_selected",
    "pos_not_selected",
)


@dataclass(frozen=True)
class Cell:
    id: str
    layer: int
    pos: int
    samples: tuple[str, ...] | None  # prose lens
    tokens: tuple[str, ...] | None  # top-k token lens (decoded text, best first)
    scores: tuple[float, ...] | None
    token: str | None = None  # the read-site token string, when the producer recorded it

    @property
    def kind(self) -> Kind:
        return "prose" if self.samples is not None else "tokens"

    @property
    def key(self) -> str:
        return f"{self.id}__L{self.layer:03d}__p{self.pos}"

    @property
    def empty(self) -> bool:
        if self.samples is not None:
            return not any(s.strip() for s in self.samples)
        return not self.tokens


@dataclass
class LoadReport:
    kind: Kind | None = None
    n_rows: int = 0
    skipped: dict[str, int] = field(default_factory=lambda: dict.fromkeys(SKIP_CATEGORIES, 0))
    n_empty: int = 0
    layers: list[int] = field(default_factory=list)
    # plan 0032 §2.0 (filled by reads.load; empty / defaults when load_readouts is called alone)
    meta: dict[str, Any] | None = None  # the sidecar, None when the file has none
    partial_ids: list[str] = field(default_factory=list)
    partial_ids_unenforced: list[str] = field(default_factory=list)
    layers_missing: list[int] = field(default_factory=list)
    reads_checked: str = ""  # sidecar | no_sidecar | prompt_only
    reads: str = "full"
    sampling: str = ""
    sampling_source: str = ""  # declared | override | default
    reader: str = ""
    layers_requested: list[int] | None = None
    lite_rule: str = ""  # reads=lite: the frozen lite rule(s) the selection applied (json)
    n_samples_trimmed: int = 0
    n_packed_ambiguous: int = 0
    n_cells_short: int = 0
    # reads.load: item -> pos -> the read-site token of EVERY loaded row, recorded before the
    # reads=lite selection (a judge's read-context window spans unselected positions too)
    site_tokens: dict[str, dict[int, str]] = field(default_factory=dict)


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_num(x: Any) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool)


def _str_list(x: Any) -> bool:
    return isinstance(x, list) and all(isinstance(s, str) for s in x)


def _parse_row(row: Any) -> Cell | None:
    """A validated Cell, or None if the row is malformed."""
    if not isinstance(row, dict):
        return None
    id_, layer, pos = row.get("id"), row.get("layer"), row.get("pos")
    if not isinstance(id_, str) or not _is_int(layer) or not _is_int(pos):
        return None
    has_samples, has_tokens = "samples" in row, "tokens" in row
    if has_samples == has_tokens:
        return None
    token = row.get("token")
    if token is not None and not isinstance(token, str):
        return None
    if has_samples:
        if "scores" in row or not _str_list(row["samples"]):
            return None
        return Cell(id_, layer, pos, tuple(row["samples"]), None, None, token)
    tokens = row["tokens"]
    if not _str_list(tokens):
        return None
    scores: tuple[float, ...] | None = None
    if "scores" in row:
        sc = row["scores"]
        if not isinstance(sc, list) or len(sc) != len(tokens) or not all(_is_num(v) for v in sc):
            return None
        scores = tuple(float(v) for v in sc)
    return Cell(id_, layer, pos, None, tuple(decode_token(t) for t in tokens), scores, token)


def load_readouts(
    path: Path,
    *,
    ids: Collection[str] | None = None,
    layers: Collection[int] | None = None,
    positions: Mapping[str, Collection[int]] | None = None,
) -> tuple[list[Cell], LoadReport]:
    rep = LoadReport()
    id_set = set(ids) if ids is not None else None
    layer_set = set(layers) if layers is not None else None
    pos_sets = {k: set(v) for k, v in positions.items()} if positions is not None else None
    cells: list[Cell] = []
    seen: set[tuple[str, int, int]] = set()
    for line in Path(path).read_bytes().decode("utf-8", "replace").split("\n"):
        if not line.strip():
            continue
        rep.n_rows += 1
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            rep.skipped["malformed"] += 1
            continue
        cell = _parse_row(row)
        if cell is None:
            rep.skipped["malformed"] += 1
            continue
        if rep.kind is None:
            rep.kind = cell.kind
        elif cell.kind != rep.kind:
            rep.skipped["mixed_kind"] += 1
            continue
        if id_set is not None:
            if cell.id not in id_set:
                rep.skipped["unknown_id"] += 1
                continue
        elif pos_sets is not None and cell.id not in pos_sets:
            rep.skipped["unknown_id"] += 1
            continue
        if layer_set is not None and cell.layer not in layer_set:
            rep.skipped["layer_not_selected"] += 1
            continue
        if pos_sets is not None and cell.id in pos_sets and cell.pos not in pos_sets[cell.id]:
            rep.skipped["pos_not_selected"] += 1
            continue
        k = (cell.id, cell.layer, cell.pos)
        if k in seen:
            rep.skipped["duplicate"] += 1
            continue
        seen.add(k)
        if cell.empty:
            rep.n_empty += 1
        cells.append(cell)
    rep.layers = sorted({c.layer for c in cells})
    return cells, rep


def expected_cells(
    positions: Mapping[str, Collection[int]], layers: Collection[int]
) -> set[tuple[str, int, int]]:
    return {(id_, layer, pos) for id_, ps in positions.items() for layer in layers for pos in ps}


def missing_cells(
    cells: Iterable[Cell], expected: set[tuple[str, int, int]]
) -> list[tuple[str, int, int]]:
    present = {(c.id, c.layer, c.pos) for c in cells}
    return sorted(expected - present)


def _layer_from_name(path: Path) -> int | None:
    stem = path.stem  # "L036"
    if not stem.startswith("L") or not stem[1:].isdigit():
        return None
    return int(stem[1:])


def convert_gen_dir(
    gen_dir: Path,
    out: Path,
    *,
    kind: Kind,
    layers: Collection[int] | None = None,
) -> LoadReport:
    """``<gen_dir>/<label>/L<layer:03d>.jsonl`` -> one contract file. ``id`` is the directory
    name, the layer comes from the filename, samples are written raw."""
    gen_dir, out = Path(gen_dir), Path(out)
    layer_set = set(layers) if layers is not None else None
    n_malformed = 0
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for f in sorted(gen_dir.glob("*/L*.jsonl")):
            layer = _layer_from_name(f)
            if layer is None or (layer_set is not None and layer not in layer_set):
                continue
            id_ = f.parent.name
            for line in f.read_bytes().decode("utf-8", "replace").split("\n"):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    n_malformed += 1
                    continue
                if not isinstance(row, dict) or "pos" not in row or "samples" not in row:
                    n_malformed += 1
                    continue
                new: dict[str, Any] = {"id": id_, "layer": layer, "pos": row["pos"]}
                if isinstance(row.get("token"), str):
                    new["token"] = row["token"]
                if kind == "prose":
                    new["samples"] = row["samples"]
                else:
                    new["tokens"] = row["samples"]
                    if "scores" in row:
                        new["scores"] = row["scores"]
                fh.write(json.dumps(new, ensure_ascii=False) + "\n")
    _, rep = load_readouts(out)
    rep.skipped["malformed"] += n_malformed
    return rep


def convert_read_json(path: Path, out: Path) -> LoadReport:
    """The source repo's write-cell read (``{"layers": [...], "records": [{"name", "rels",
    "tokens", "ao": {"<layer>": [[sample, ...] per rel]}}]}``) -> one contract file: ``id`` is
    the item label, ``pos`` the cell's offset from the last completion token (``rels`` are
    stored nearest-last first), ``token`` the token read at that cell."""
    from wsbench.banks import label_of

    path, out = Path(path), Path(out)
    d = json.loads(path.read_bytes().decode("utf-8", "replace"))
    if (
        not isinstance(d, dict)
        or not isinstance(d.get("layers"), list)
        or not isinstance(d.get("records"), list)
    ):
        raise ValueError(f"{path}: expected an object with 'layers' and 'records' lists")
    layers = [int(x) for x in d["layers"]]
    n_malformed = 0
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for rec in d["records"]:
            if not isinstance(rec, dict) or not isinstance(rec.get("name"), str):
                n_malformed += 1
                continue
            rels, tokens, ao = rec.get("rels"), rec.get("tokens"), rec.get("ao")
            if not (isinstance(rels, list) and isinstance(tokens, list) and isinstance(ao, dict)):
                n_malformed += 1
                continue
            if len(rels) != len(tokens) or not all(_is_int(r) for r in rels):
                n_malformed += 1
                continue
            id_ = label_of(rec["name"])
            for layer in layers:
                per_rel = ao.get(str(layer))
                if not isinstance(per_rel, list) or len(per_rel) != len(rels):
                    n_malformed += 1
                    continue
                for rel, token, samples in zip(rels, tokens, per_rel, strict=True):
                    if not isinstance(samples, list):
                        n_malformed += 1
                        continue
                    row = {
                        "id": id_,
                        "layer": layer,
                        "pos": int(rel),
                        "token": str(token),
                        "samples": [str(x) for x in samples],
                    }
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    _, rep = load_readouts(out)
    rep.skipped["malformed"] += n_malformed
    return rep


# ---------------------------------------------------------------- sampling (plan 0032 §2.9, Q1)

SAMPLINGS = ("bullet4", "prose1", "tokens10")
SIDECAR_SUFFIX = ".meta.json"
SIDECAR_KEYS = ("reads", "sampling", "reader", "arm", "layers", "plan_sha", "producer_sha")


def sidecar_path(path: Path) -> Path:
    """``<family>.jsonl.meta.json``: the producer's declaration beside a readouts file."""
    return Path(str(path) + SIDECAR_SUFFIX)


def read_sidecar(path: Path) -> dict[str, Any] | None:
    """The sidecar of ``path`` (``{reads, sampling, reader, arm, layers, [plan_sha,
    producer_sha, protocol]}``), or None when the file has none. A malformed sidecar or an
    unknown ``sampling`` / ``reads`` value is an error (exit 2), never a silent default."""
    p = sidecar_path(Path(path))
    if not p.exists():
        return None
    try:
        meta = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as e:
        raise SystemExit(f"{p}: unreadable sidecar ({e})") from None
    if not isinstance(meta, dict):
        raise SystemExit(f"{p}: the sidecar must be a JSON object")
    if meta.get("sampling") not in (None, *SAMPLINGS):
        raise SystemExit(f"{p}: sampling={meta.get('sampling')!r}; expected one of {SAMPLINGS}")
    if meta.get("reads") not in (None, "full", "lite"):
        raise SystemExit(f"{p}: reads={meta.get('reads')!r}; expected full or lite")
    return meta


def write_sidecar(path: Path, **meta: Any) -> Path:
    """Write ``<path>.meta.json`` (producers, converters, the prompt-only writer)."""
    if meta.get("sampling") not in SAMPLINGS:
        raise ValueError(f"sampling={meta.get('sampling')!r}; expected one of {SAMPLINGS}")
    meta.setdefault("reads", "full")
    p = sidecar_path(Path(path))
    p.write_text(json.dumps(meta, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def _bullets(s: str) -> list[str]:
    """The top-level ``- `` bullets of one packed sample (continuation lines join their bullet,
    KEEPING their line breaks: a packed x4 generation is often several lines of verse, and
    poetry's line-ending gate reads them; plan 0038)."""
    out: list[str] = []
    for line in s.split("\n"):
        if line.startswith("- "):
            out.append(line[2:].strip())
        elif out and line.strip():
            out[-1] = (out[-1] + "\n" + line.strip()).strip()
    return out


def normalize(cells: Sequence[Cell], sampling: str) -> tuple[list[Cell], dict[str, int]]:
    """The declared sampling rule applied in memory (decision Q1), never inferred from shape:
    ``tokens10`` keeps the top 10 tokens (score order); ``prose1`` keeps the first sample (one
    s3d generation with several concept bullets stays ONE sample); ``bullet4`` holds 4 separate
    samples (a cached packed ``- g1\\n- g2…`` string is split on its top-level bullets: exactly
    4 -> 4 samples, else the first 4 and ``n_packed_ambiguous``; fewer -> kept and
    ``n_cells_short``)."""
    if sampling not in SAMPLINGS:
        raise SystemExit(f"sampling={sampling!r}; expected one of {', '.join(SAMPLINGS)}")
    diag = {"n_samples_trimmed": 0, "n_packed_ambiguous": 0, "n_cells_short": 0}
    out: list[Cell] = []
    for c in cells:
        if c.tokens is not None:
            if len(c.tokens) > 10:
                idx = list(range(len(c.tokens)))
                if c.scores is not None:
                    idx.sort(key=lambda i: -c.scores[i])  # type: ignore[index]
                idx = sorted(idx[:10]) if c.scores is None else idx[:10]
                toks = tuple(c.tokens[i] for i in idx)
                sc = None if c.scores is None else tuple(c.scores[i] for i in idx)
                diag["n_samples_trimmed"] += 1
                c = replace(c, tokens=toks, scores=sc)
            out.append(c)
            continue
        samples = tuple(c.samples or ())
        if sampling == "bullet4":
            if len(samples) == 1 and len(b := _bullets(samples[0])) >= 2:
                if len(b) != 4:
                    diag["n_packed_ambiguous"] += 1
                samples = tuple(b[:4])
            elif len(samples) > 4:
                diag["n_samples_trimmed"] += 1
                samples = samples[:4]
            if len(samples) < 4:
                diag["n_cells_short"] += 1
        elif len(samples) > 1:  # prose1 (and a prose file declared tokens10, kept whole)
            if sampling == "prose1":
                diag["n_samples_trimmed"] += 1
                samples = samples[:1]
        out.append(replace(c, samples=samples))
    return out, diag


def bulleted(samples: Sequence[str]) -> str:
    """ONE string for a native judge that needs one text per cell: ``"- g1\\n- g2…"``."""
    return "\n".join("- " + s.strip().removeprefix("- ").strip() for s in samples if s.strip())
