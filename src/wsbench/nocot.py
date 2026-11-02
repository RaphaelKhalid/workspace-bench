"""knowledge_cutoff's nocot items (plan 0018): the ids-only obscure bank and the prompt render,
which fetches nocot-bench's pinned zip (sha256-checked, cached as the zip only) at plan time."""

import hashlib
import io
import json
import os
import urllib.request
import zipfile
from functools import cache
from pathlib import Path
from typing import Any

from wsbench.registry import REPO_ROOT

OBSCURE = REPO_ROOT / "evals" / "knowledge_cutoff" / "obscure_items.json"
# nocot publishes this password in its README ("for people, not for crawlers"); the unpacked files
# are never written anywhere by this module
PASSWORD = b"lantern-orchard-pebble"


def load_obscure() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw = json.loads(OBSCURE.read_text(encoding="utf-8"))
    return raw["header"], raw["items"]


def normalised(item: dict[str, Any]) -> dict[str, Any]:
    """An obscure item in the fields the judge reads beside the frozen 109's."""
    return {
        **item,
        "truth": {"canonical": item["truth"]},
        "stratum": "nocot",
        "label_type": f"obscure_{item['kind']}",
        "source": "nocot",
    }


def _cache_dir() -> Path:
    root = os.environ.get("WSB_CACHE")
    return (Path(root) if root else Path.home() / ".cache" / "wsbench") / "nocot"


def fetch_zip(source: dict[str, Any]) -> bytes:
    """nocot's zip at the pinned commit, from the cache or GitHub; refused on a sha256 mismatch."""
    want = source["zip_sha256"]
    path = _cache_dir() / f"{want}.zip"
    if path.exists():
        blob = path.read_bytes()
        if hashlib.sha256(blob).hexdigest() == want:
            return blob
        path.unlink(missing_ok=True)  # a corrupt / partial cache file: drop it and re-fetch once
    url = f"https://github.com/{source['repo']}/raw/{source['commit']}/{source['zip_path']}"
    with urllib.request.urlopen(url, timeout=120) as r:  # a pinned https URL
        blob = bytes(r.read())
    got = hashlib.sha256(blob).hexdigest()
    if got != want:
        raise SystemExit(f"knowledge_cutoff: nocot zip sha256 {got} != pinned {want} ({url})")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".tmp.{os.getpid()}")
    tmp.write_bytes(blob)
    os.replace(tmp, path)  # atomic: concurrent shards never read a partial zip
    return blob


def problems(blob: bytes, domains: set[str]) -> dict[str, str]:
    """``domain:problem_number`` -> nocot's exact ``problem`` text, read in memory."""
    out: dict[str, str] = {}
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        for d in sorted(domains):
            raw = z.read(f"data/knowledge/{d}.jsonl", pwd=PASSWORD).decode("utf-8")
            for line in raw.splitlines():
                if not line.strip():
                    continue
                r = json.loads(line)
                if r.get("split") == "shot" or "problem_number" not in r:
                    continue  # few-shot demonstrations carry no item key
                out[f"{r.get('domain', d)}:{r['problem_number']}"] = r["problem"]
    return out


@cache
def questions() -> dict[str, str]:
    """Obscure id -> rendered user turn (``template.format(question=problem.strip())``, the
    source's exact render), each ``problem_sha256`` checked on the raw problem. Tests replace this
    function (tests/conftest.py) so nothing fetches offline."""
    header, items = load_obscure()
    texts = problems(fetch_zip(header["source"]), {it["domain"] for it in items})
    out = {}
    for it in items:
        p = texts.get(it["id"])
        if p is None:
            raise SystemExit(f"knowledge_cutoff: nocot item {it['id']} not in the pinned zip")
        if hashlib.sha256(p.encode("utf-8")).hexdigest() != it["problem_sha256"]:
            raise SystemExit(f"knowledge_cutoff: nocot item {it['id']} text does not match")
        out[it["id"]] = header["prompt_template"].format(question=p.strip())
    return out
