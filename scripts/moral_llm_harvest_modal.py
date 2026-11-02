"""moral_rationale bank v7: ask gpt-6-astra (OpenAI, WIF) and gemini-4-argon (Gemini, WIF) the
bank's dilemmas, run on Modal only (never from the dev box; never OpenRouter).

The box writes the requests (``scripts/moral_v7.py requests``: one JSON row per conversation,
``{key, model, messages, then}``); each Modal CPU container answers a shard and appends every row
to the ``wsb-moral-v7-harvest`` volume as it completes (resumable: keys already on the volume
are skipped, so nothing answered is paid for twice). A row is the conversation's replies: the
reply to ``messages`` and, when ``then`` is set (the free-answer conversations: the model gives
its own one-word answer, then is asked for its reason), the reply to the follow-up turn.
Provider defaults throughout (no temperature, no reasoning setting), as Qwen was sampled at its
default temperature.

Routes: astra = OpenAI chat completions with a workload-identity-federation access token (the
``openai-wif`` secret, ``wsbench.baselines.ati_remote.WifToken``); argon = Gemini on Vertex AI via
Google workload identity federation (Modal workspace safety-sahan-2, environment camila-blank
only; no key).

    MODAL_PROFILE=safety-sahan-2 modal run -e camila-blank scripts/moral_llm_harvest_modal.py \\
        --model astra --requests <dir>/requests_astra.jsonl --out <dir>/astra.jsonl [--shards 16]
"""

import json
import os
from pathlib import Path

import modal

app = modal.App("wsb-moral-v7-harvest")
vol = modal.Volume.from_name("wsb-moral-v7-harvest", create_if_missing=True)
VOL = "/harvest"
SRC = Path(__file__).resolve().parents[1] / "src"
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("openai>=1.60", "httpx", "google-genai>=2.3", "google-auth>=2.40")
    .env({"PYTHONPATH": "/root/wsbench_src"})
    .add_local_dir(str(SRC / "wsbench"), "/root/wsbench_src/wsbench")
)
MODELS = {"astra": "gpt-6-astra", "argon": "gemini-4-argon"}
GCP_PROJECT = "camila-blank"
GCP_AUDIENCE = (
    "//iam.googleapis.com/projects/514946254119/locations/global/workloadIdentityPools/modal/"
    "providers/modal-oidc"
)
CONCURRENCY = 16  # per container
ATTEMPTS = 8
MAX_TOKENS = 16000


def _gemini_client():  # type: ignore[no-untyped-def]
    from google import genai
    from google.auth import identity_pool

    class ModalToken(identity_pool.SubjectTokenSupplier):
        def get_subject_token(self, context, request):  # type: ignore[no-untyped-def]
            return os.environ["MODAL_IDENTITY_TOKEN"]

    creds = identity_pool.Credentials(
        audience=GCP_AUDIENCE,
        subject_token_type="urn:ietf:params:oauth:token-type:jwt",
        token_url="https://sts.googleapis.com/v1/token",
        subject_token_supplier=ModalToken(),
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    return genai.Client(vertexai=True, project=GCP_PROJECT, location="global", credentials=creds)


class Asker:
    """One chat turn for a conversation ``[{role, content}]`` (system / user / assistant)."""

    def __init__(self, which: str) -> None:
        self.which = which
        self.model = MODELS[which]
        if which == "astra":
            from wsbench.baselines import ati_remote as ar

            self.clients = ar.Clients("openai-wif")
        else:
            self.gem = _gemini_client()

    async def turn(self, messages: list[dict]) -> str:
        if self.which == "astra":
            client = await self.clients.get()
            r = await client.chat.completions.create(
                model=self.model, max_completion_tokens=MAX_TOKENS, messages=messages
            )
            c = r.choices[0] if r.choices else None
            if c is not None and getattr(c.message, "refusal", None):
                return "<refused>"
            return ((c.message.content if c else "") or "").strip()
        from google.genai import types

        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        contents = [
            types.Content(
                role="model" if m["role"] == "assistant" else "user",
                parts=[types.Part(text=m["content"])],
            )
            for m in messages
            if m["role"] != "system"
        ]
        cfg = types.GenerateContentConfig(
            max_output_tokens=MAX_TOKENS, **({"system_instruction": system} if system else {})
        )
        r = await self.gem.aio.models.generate_content(
            model=self.model, contents=contents, config=cfg
        )
        return (r.text or "").strip()

    async def turn_retry(self, messages: list[dict]) -> str:
        import asyncio
        import random

        err = ""
        for attempt in range(ATTEMPTS):
            try:
                t = await self.turn(messages)
                if t:
                    return t
                err = "empty"
            except Exception as e:  # rate limits / transient: back off and retry
                err = f"{type(e).__name__}: {str(e)[:200]}"
                if "401" in err and self.which == "astra":
                    self.clients.auth_failed()
            await asyncio.sleep(min(90, 3 * 2**attempt) * (0.5 + random.random()))
        raise RuntimeError(err)


def _run_shard(which: str, shard: int, reqs: list[dict]) -> int:
    import asyncio

    path = Path(VOL) / which / f"shard{shard}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    done = set()  # answered keys in ANY shard file (a re-launch may re-shard the requests)
    vol.reload()
    for p in path.parent.glob("shard*.jsonl"):
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not r.get("error"):
                done.add(r["key"])
    todo = [r for r in reqs if r["key"] not in done]

    async def main() -> int:
        asker = Asker(which)
        sem = asyncio.Semaphore(CONCURRENCY)

        async def one(req: dict) -> dict:
            async with sem:
                try:
                    msgs = list(req["messages"])
                    first = await asker.turn_retry(msgs)
                    replies = [first]
                    if req.get("then"):
                        msgs += [
                            {"role": "assistant", "content": first},
                            {"role": "user", "content": req["then"]},
                        ]
                        replies.append(await asker.turn_retry(msgs))
                    return {"key": req["key"], "model": asker.model, "replies": replies}
                except Exception as e:
                    return {"key": req["key"], "model": asker.model, "error": str(e)[:300]}

        n = 0
        tasks = [asyncio.create_task(one(r)) for r in todo]
        with path.open("a", encoding="utf-8") as fh:
            try:
                for fut in asyncio.as_completed(tasks):
                    fh.write(json.dumps(await fut, ensure_ascii=False) + "\n")
                    fh.flush()
                    n += 1
                    if n % 100 == 0:
                        vol.commit()
            finally:
                for t in tasks:
                    t.cancel()
                vol.commit()
        return n

    return asyncio.run(main())


FN = {"image": image, "volumes": {VOL: vol}, "timeout": 12 * 3600}


@app.function(secrets=[modal.Secret.from_name("openai-wif")], **FN)
def shard_astra(shard: int, reqs: list[dict]) -> int:
    return _run_shard("astra", shard, reqs)


@app.function(**FN)
def shard_argon(shard: int, reqs: list[dict]) -> int:
    return _run_shard("argon", shard, reqs)


@app.function(secrets=[modal.Secret.from_name("openai-wif")], image=image, timeout=600)
def preflight_astra() -> str:
    import asyncio

    return asyncio.run(Asker("astra").turn([{"role": "user", "content": "Say OK."}]))[:40]


@app.function(image=image, timeout=600)
def preflight_argon() -> str:
    import asyncio

    return asyncio.run(Asker("argon").turn([{"role": "user", "content": "Say OK."}]))[:40]


@app.function(image=image, volumes={VOL: vol}, timeout=600)
def collect(which: str) -> list[dict]:
    vol.reload()
    rows = []
    for p in sorted((Path(VOL) / which).glob("shard*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


@app.local_entrypoint()
def main(model: str, requests: str, out: str, shards: int = 16, limit: int = 0) -> None:
    if model not in MODELS:
        raise SystemExit(f"--model must be one of {sorted(MODELS)}")
    reqs = [json.loads(x) for x in Path(requests).read_text(encoding="utf-8").splitlines() if x]
    if limit:
        reqs = reqs[:limit]
    print("preflight:", (preflight_astra if model == "astra" else preflight_argon).remote())
    fn = shard_astra if model == "astra" else shard_argon
    k = max(1, min(shards, len(reqs)))
    # a stable shard assignment (by request order), so a re-launch skips what each shard wrote
    parts = [reqs[i::k] for i in range(k)]
    res = list(fn.starmap([(i, p) for i, p in enumerate(parts)], return_exceptions=True))
    errs = [r for r in res if isinstance(r, BaseException)]
    print(f"{sum(r for r in res if isinstance(r, int))} new rows; {len(errs)} shard(s) failed")
    for e in errs:
        print(f"  shard error: {e!r}"[:400])
    rows = collect.remote(model)
    best: dict[str, dict] = {}
    for r in rows:  # an answered row wins over an error row of the same key
        if r["key"] not in best or (best[r["key"]].get("error") and not r.get("error")):
            best[r["key"]] = r
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in best.values()), encoding="utf-8"
    )
    n_err = sum(bool(r.get("error")) for r in best.values())
    print(f"{len(best)} rows ({n_err} errors) -> {out}")
