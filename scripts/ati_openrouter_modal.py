"""ATI panel answers from a hosted frontier reader (astra / argon), run on Modal only (plan 0019).

The hosted readers are never called from the dev box. The box builds the prompts
(``text_inversion.pending_requests``), Modal CPU containers call the reader and write every row
to the ``wsb-ati-answers`` volume as it completes (so a client disconnect loses no paid answer),
and the box then appends the rows to ``<out>/answers/<answerer>/draw{d}.jsonl``. Resumable:
every launch first pulls the rows already on the volume into the local answers files, so nothing
answered is asked (or paid for) again. Every row carries the ``prompt_sha`` of its question and
its ``route``. Launch with ``--detach`` for long runs (a client disconnect then does not stop the
containers); rerun to collect.

Routes (``wsbench.baselines.ati_remote``; same question, same parameters):
``--route openrouter`` (default; the ``openrouter`` secret); for astra only,
``--route openai-wif``: OpenAI directly via workload identity federation (the ``openai-wif``
secret holds OPENAI_IDENTITY_PROVIDER_ID_MODAL / OPENAI_SERVICE_ACCOUNT_ID / OPENAI_PROJECT_ID;
the container's MODAL_IDENTITY_TOKEN is exchanged for a short-lived access token kept in memory);
for argon only, ``--route gemini-wif``: Gemini on Vertex AI via Google workload identity
federation (no secret: the container's MODAL_IDENTITY_TOKEN is the subject token; works only in
Modal workspace safety-sahan-2, environment camila-blank, so run with ``-e camila-blank``).

    PYTHONPATH=src modal run [-e camila-blank] scripts/ati_openrouter_modal.py --answerer astra \\
        [--route openai-wif|gemini-wif] [--out outputs/baselines/text_inversion] \\
        [--families a,b] [--shards 8] [--limit-items 3] [--smoke]
"""

import json
from pathlib import Path

import modal

from wsbench.baselines import ati_remote as ar

app = modal.App("wsb-ati-openrouter")
answers_vol = modal.Volume.from_name("wsb-ati-answers", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("openai>=1.60", "httpx", "google-genai>=2.3", "google-auth>=2.40")
    .add_local_python_source("wsbench")
)
VOL = "/answers"
CONCURRENCY = 16  # per container
SECRETS = {"openrouter": "openrouter", "openai-wif": "openai-wif"}  # route -> Modal secret
# gemini-wif needs no secret: Modal injects MODAL_IDENTITY_TOKEN into every container


def _run_shard(
    run: str, answerer: str, model: str, shard: int, reqs: list[dict], route: str
) -> int:
    """Answer one shard; rows are appended to ``/answers/<run>/<answerer>/<shard file>`` as
    they complete. Keys already present there are skipped. Returns the number of new rows."""
    import asyncio

    name = f"shard{shard}.jsonl" if route == "openrouter" else f"shard-{route}{shard}.jsonl"
    path = Path(VOL) / run / answerer / name
    path.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:  # a partial last line from a killed container
                continue
            if not r["error"] or r.get("refused"):
                done.add((r["family"], r["id"], r["draw"], r.get("prompt_sha")))
    todo = [r for r in reqs if (r["family"], r["id"], r["draw"], r["prompt_sha"]) not in done]

    async def main() -> int:
        clients = ar.Clients(route)
        sem = asyncio.Semaphore(CONCURRENCY)
        n = 0
        tasks = [asyncio.create_task(ar.answer_one(clients, sem, model, r)) for r in todo]
        with path.open("a", encoding="utf-8") as fh:
            try:
                for fut in asyncio.as_completed(tasks):
                    row = await fut
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                    fh.flush()
                    n += 1
                    if n % 200 == 0:
                        answers_vol.commit()
            finally:
                for t in tasks:
                    t.cancel()
                answers_vol.commit()
        return n

    return asyncio.run(main())


def _secrets(route: str) -> list[modal.Secret]:
    return [modal.Secret.from_name(SECRETS[route])]


FN = {"image": image, "volumes": {VOL: answers_vol}, "timeout": 24 * 3600}


@app.function(secrets=_secrets("openrouter"), **FN)
def answer_shard(run: str, answerer: str, model: str, shard: int, reqs: list[dict]) -> int:
    return _run_shard(run, answerer, model, shard, reqs, "openrouter")


@app.function(secrets=_secrets("openai-wif"), **FN)
def answer_shard_wif(run: str, answerer: str, model: str, shard: int, reqs: list[dict]) -> int:
    return _run_shard(run, answerer, model, shard, reqs, "openai-wif")


@app.function(**FN)
def answer_shard_gemini(run: str, answerer: str, model: str, shard: int, reqs: list[dict]) -> int:
    return _run_shard(run, answerer, model, shard, reqs, "gemini-wif")


def _preflight(model: str, route: str) -> str:
    """One neutral call outside the bank, so a dead key never looks like a refusal."""
    import asyncio

    async def go() -> str:
        clients = ar.Clients(route)
        kw = ar.completion_kwargs(route, model, "Say OK.")
        if route == "gemini-wif":
            kw["config"] = {"max_output_tokens": 2000}
            r = ar._gemini_reply(
                await (await clients.get()).aio.models.generate_content(**kw), kw["model"]
            )
            return f"{route} {r['model']}: {r['text'][:40]!r} (finish {r['finish']})"
        kw["max_completion_tokens" if route == "openai-wif" else "max_tokens"] = 2000
        r = await (await clients.get()).chat.completions.create(**kw)
        text = (r.choices[0].message.content or "") if r.choices else "<no choices>"
        return f"{route} {r.model}: {text[:40]!r}"

    return asyncio.run(go())


@app.function(image=image, secrets=_secrets("openrouter"), timeout=600)
def preflight(model: str) -> str:
    return _preflight(model, "openrouter")


@app.function(image=image, secrets=_secrets("openai-wif"), timeout=600)
def preflight_wif(model: str) -> str:
    return _preflight(model, "openai-wif")


@app.function(image=image, timeout=600)
def preflight_gemini(model: str) -> str:
    return _preflight(model, "gemini-wif")


ROUTE_FNS = {
    "openrouter": (preflight, answer_shard),
    "openai-wif": (preflight_wif, answer_shard_wif),
    "gemini-wif": (preflight_gemini, answer_shard_gemini),
}


@app.local_entrypoint()
def main(
    answerer: str,
    out: str = "outputs/baselines/text_inversion",
    families: str = "",
    shards: int = 8,
    draws: int = 3,
    route: str = "openrouter",
    limit_items: int = 0,
    smoke: bool = False,
) -> None:
    from wsbench.baselines import text_inversion as ti

    if answerer not in ti.OPENROUTER_ANSWERERS:
        raise SystemExit(f"answerer must be one of {sorted(ti.OPENROUTER_ANSWERERS)}")
    if route not in ar.ROUTES:
        raise SystemExit(f"route must be one of {ar.ROUTES}")
    if route in ar.ROUTE_ANSWERERS and answerer not in ar.ROUTE_ANSWERERS[route]:
        raise SystemExit(f"route {route} serves {sorted(ar.ROUTE_ANSWERERS[route])} only")
    model = ti.PANEL[answerer]
    if smoke:  # the preflight alone ("Say OK."), no bank question
        print("preflight:", ROUTE_FNS[route][0].remote(model), flush=True)
        return
    out_p = Path(out)
    fams = {f for f in families.split(",") if f} or None
    run = ti.run_key(out_p)
    prefix = f"{run}/{answerer}"
    # collect first: rows already paid for on the volume are never asked again
    print(ti.append_answers(out_p, answerer, ti.download_volume_rows("wsb-ati-answers", prefix)))
    reqs = ti.pending_requests(out_p, answerer, draws, fams)
    if limit_items:  # a smoke: every pending draw of the first N items
        keep = list(dict.fromkeys((r["family"], r["id"]) for r in reqs))[:limit_items]
        reqs = [r for r in reqs if (r["family"], r["id"]) in set(keep)]
    print(f"{answerer} ({model}, {route}): {len(reqs)} requests pending, run {run}", flush=True)
    if reqs:
        pre, shard_fn = ROUTE_FNS[route]
        print("preflight:", pre.remote(model), flush=True)
        k = max(1, min(shards, len(reqs)))
        parts = [reqs[i::k] for i in range(k)]
        results = list(
            shard_fn.starmap(
                [(run, answerer, model, i, p) for i, p in enumerate(parts)],
                return_exceptions=True,
            )
        )
        errs = [r for r in results if isinstance(r, BaseException)]
        n = sum(r for r in results if isinstance(r, int))
        print(f"{n} new rows written to the volume; {len(errs)} shard(s) failed", flush=True)
        for e in errs:
            print(f"  shard error: {e!r}"[:500], flush=True)
    rows = ti.download_volume_rows("wsb-ati-answers", prefix)
    print(ti.append_answers(out_p, answerer, rows), flush=True)
