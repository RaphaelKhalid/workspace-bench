"""Mirror of Camila's wsbench-viewer with our models added (Modal env `agam`, app wsbench-viewer-agam).

Her frontend and her models' data are proxied live from her app; /data/manifest.json is her
manifest plus our_models.json; our models' files come from per-model zips on the volume wsbench-viewer-agam-data
(written by atlas/export_cb.py + atlas/refresh_cb.sh).

    MODAL_ENVIRONMENT=agam modal deploy atlas/cb_mirror.py
"""

import json
import time
from pathlib import Path

import modal

APP = "wsbench-viewer-agam"
CB_URL = "https://safety-sahan-2-camila-blank--wsbench-viewer-web.modal.run"
VOL = modal.Volume.from_name("wsbench-viewer-agam-data", create_if_missing=True)
ROOT = Path("/vol")

image = modal.Image.debian_slim(python_version="3.12").pip_install(
    "fastapi[standard]==0.115.6", "httpx==0.28.1"
)
app = modal.App(APP, image=image)


@app.function(volumes={str(ROOT): VOL}, timeout=600, scaledown_window=600)
@modal.concurrent(max_inputs=64)
@modal.asgi_app(label="wsbench-viewer-agam")
def web():
    import httpx
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse, Response

    api = FastAPI()
    client = httpx.AsyncClient(timeout=60.0, follow_redirects=True)
    st = {"reloaded": 0.0, "ours": None, "ours_t": 0.0}

    def reload_volume():
        if time.time() - st["reloaded"] > 60:
            try:
                VOL.reload()
            except Exception:
                pass
            st["reloaded"] = time.time()

    def ours() -> dict:
        reload_volume()
        p = ROOT / "our_models.json"
        if st["ours"] is None or time.time() - st["ours_t"] > 60:
            st["ours"] = json.loads(p.read_text()) if p.exists() else {"models": []}
            st["ours_t"] = time.time()
        return st["ours"]

    zips: dict = {}

    def zip_of(model: str):
        """Our model's export zip (re-opened when a refresh uploaded a new one)."""
        import zipfile

        reload_volume()
        p = ROOT / "zips" / f"{model}.zip"
        if not p.exists():
            return None
        mt = p.stat().st_mtime
        hit = zips.get(model)
        if hit is None or hit[0] != mt:
            zips[model] = (mt, zipfile.ZipFile(p))
        return zips[model][1]

    async def proxy(path: str) -> Response:
        r = await client.get(f"{CB_URL}/{path}")
        ct = r.headers.get("content-type", "application/octet-stream")
        return Response(
            r.content,
            status_code=r.status_code,
            media_type=ct.split(";")[0],
            headers={"cache-control": "no-cache"},
        )

    @api.get("/data/manifest.json")
    async def manifest():
        r = await client.get(f"{CB_URL}/data/manifest.json")
        man = r.json()
        o = ours()
        man["models"] = list(man.get("models", [])) + list(o.get("models", []))
        man["about_notes"] = list(man.get("about_notes", [])) + [
            f"Added by Agam's mirror (built {o.get('built_at', '?')}): adaptive-set and 27B-bank-gated models from the "
            "adapt-bank workstream (workspace-bench agam/adapt). Camila's models are served live from her app."
        ]
        return JSONResponse(man, headers={"cache-control": "no-cache"})

    @api.get("/data/{model}/{rest:path}")
    async def data(model: str, rest: str, request: Request):
        keys = {m["key"] for m in ours().get("models", [])}
        if model in keys:
            from urllib.parse import unquote

            z = zip_of(model)
            if z is not None:
                try:
                    body = z.read(unquote(rest))
                except KeyError:
                    return JSONResponse({"error": "not found"}, status_code=404)
                return Response(
                    body, media_type="application/json", headers={"cache-control": "no-cache"}
                )
            return JSONResponse({"error": "not found"}, status_code=404)
        return await proxy(f"data/{model}/{rest}")

    @api.get("/{path:path}")
    async def static(path: str):
        return await proxy(path or "")

    return api
