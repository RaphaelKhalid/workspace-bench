"""jlens_concept_pr on a new subject (references/porting.md): the subject's own rollouts, read
positions and J-lens top-10. Port of global-workspace ``scripts/oracle_lens_evals/jlens_pr/
modal_pipeline.py`` run locally: the frozen bank's 299 seed prompts (exact ids; the Qwen3.5 sizes
share the 27B's tokenizer and template), HF generate T=1.0 / top-p 1 / top-k 0 / 512 new tokens,
seed 7, batches of 16; one read position per rollout by ``pick_read_position`` (same rng);
``capture_acts.py`` at the remapped grid; ``jlens_eval.py`` with the subject's neuronpedia n1000
lens (tied embeddings: W_U = embed_tokens). Writes ``adapted/<model>/jlens_concept_pr/``.

Run with the adapt venv + PYTHONPATH=<gw>/src:<gw>/scripts/oracle_lens_evals/olens_sglang:
    /workspace/agam/envs/adapt/bin/python scripts/adapt_jlens.py \\
        --model Qwen/Qwen3.5-4B --tag qwen3.5-4b --layers 10:31:2 \\
        --lens qwen3.5-4b/jlens/Salesforce-wikitext/Qwen3.5-4B_jacobian_lens_n1000.pt
"""

import argparse
import json
import random
import shutil
import subprocess
import sys
from pathlib import Path

WSB = Path(__file__).resolve().parents[1]
if str(WSB / "src") not in sys.path:  # wsbench.adapt.template (BOS prefix), also inside Modal
    sys.path.insert(0, str(WSB / "src"))
GW = Path("/workspace/agam/global-workspace")
OLS = GW / "scripts/oracle_lens_evals/olens_sglang"
SRC_ITEMS = GW / "evals/workspace-bench/jlens_pr/items.json"


QWEN = "Qwen/Qwen3.6-27B"  # the tokenizer the frozen seeds' ids are in


def seed_ids(row: dict, tok) -> list[int]:
    """The seed prompt for THIS subject. Same tokenizer as the bank (Qwen3.5/3.6): the exact ids.
    Otherwise the seed text is rebuilt from the Qwen ids and re-rendered with the subject's own
    template (chat) or re-truncated to 128 of its own tokens (pt), never fed as Qwen ids."""
    ids = row["input_ids"][: row["prompt_len"]]
    if getattr(tok, "name_or_path", "").startswith("Qwen/Qwen3.") or _same_vocab(tok):
        return ids
    from transformers import AutoTokenizer

    qtok = AutoTokenizer.from_pretrained(QWEN)
    text = qtok.decode(ids, skip_special_tokens=False)
    if row["family"] == "chat":  # the user message between the ChatML user header and its end
        body = text.split("<|im_start|>user\n", 1)[-1].split("<|im_end|>", 1)[0]
        out = tok.apply_chat_template(
            [{"role": "user", "content": body}],
            tokenize=True,
            add_generation_prompt=True,
            enable_thinking=False,
        )
        return list(out["input_ids"] if hasattr(out, "keys") else out)
    from wsbench.adapt.template import bos_prefix

    return bos_prefix(tok) + tok(text, add_special_tokens=False)["input_ids"][:128]


def _same_vocab(tok) -> bool:
    return len(tok) == 248077 and tok.convert_tokens_to_ids("<|im_end|>") == 248046


def rollouts(model_id: str, out_items: Path, max_new: int, seed: int, batch: int) -> dict:
    import torch

    sys.path.insert(0, str(GW / "scripts/oracle_lens_evals"))
    from global_workspace.model import ModelBackend
    from jlens_pr.items import pick_read_position

    src = json.loads(SRC_ITEMS.read_text())
    be = ModelBackend(model_id, device="cuda", dtype=torch.bfloat16)
    model, tok = be.model, be.tokenizer
    model.eval()
    tok.padding_side = "left"
    gc = model.generation_config.eos_token_id
    stop = {
        int(tok.eos_token_id),
        *([int(x) for x in gc] if isinstance(gc, list) else [int(gc)] if gc is not None else []),
    }
    if tok.pad_token_id is not None:
        stop.add(int(tok.pad_token_id))
    torch.manual_seed(seed)
    rng = random.Random(seed)
    rows, n_empty, per_source = [], 0, {}
    for b0 in range(0, len(src), batch):
        part = src[b0 : b0 + batch]
        pids = [seed_ids(r, tok) for r in part]
        enc = tok.pad({"input_ids": pids}, return_tensors="pt").to("cuda")
        with torch.no_grad():
            out = model.generate(
                **enc,
                do_sample=True,
                temperature=1.0,
                top_p=1.0,
                top_k=0,
                max_new_tokens=max_new,
                pad_token_id=tok.eos_token_id,
            )
        for r, p, row in zip(part, pids, out, strict=True):
            oids = []
            for t in row[enc["input_ids"].shape[1] :].tolist():
                if int(t) in stop:
                    break
                oids.append(int(t))
            if not oids:
                n_empty += 1
                continue
            per_source[r["source"]] = per_source.get(r["source"], 0) + 1
            pos = pick_read_position(len(p), len(oids), rng)
            rows.append(
                {
                    **{k: r[k] for k in ("label", "family", "source", "source_id", "seed_key")},
                    "input_ids": [*p, *oids],
                    "prompt_len": len(p),
                    "eval_positions": [pos],
                    "targets": [],
                    "look_for": "",
                    "render": "plain",
                }
            )
        print(f"[rollout] {min(b0 + batch, len(src))}/{len(src)}", flush=True)
    out_items.write_text(json.dumps(rows))
    return {
        "n_items": len(rows),
        "n_empty_rollouts": n_empty,
        "per_source": per_source,
        "read_region": "generated_only",
        "rollout_sampling": {
            "temperature": 1.0,
            "top_p": 1.0,
            "top_k": 0,
            "max_new": max_new,
            "seed": seed,
            "engine": "hf-transformers",
        },
    }


def jlens(
    model_id: str,
    lens: str,
    acts: Path,
    gen: Path,
    layers: str,
    k: int,
    lens_repo: str = "neuronpedia/jacobian-lens",
    readout: str = "cosine",
) -> None:
    """jlens_eval.py with the subject's own W_U: lm_head, or the embedding table when tied.
    ``readout="norm_centered"`` (Gemma-4): apply the model's final RMSNorm (x/rms * w, as the
    official jlens ``unembed`` does) to J*h before W_U, then subtract a fixed per-layer mean
    direction (estimated over all positions of 40 of the bank's own captures).
    Gemma-4's final-norm weights reach 510 and one position-constant direction
    dominates the raw cosine readout (sanity 0.00-0.03 raw vs 0.17-0.30 this way)."""
    sys.path.insert(0, str(OLS))
    import common
    import jlens_eval
    from huggingface_hub import snapshot_download

    snap = Path(model_id) if Path(model_id).exists() else Path(snapshot_download(model_id))
    cfg = json.loads((snap / "config.json").read_text())
    tied = cfg.get("tie_word_embeddings", (cfg.get("text_config") or {}).get("tie_word_embeddings"))
    jlens_eval._load_w_u = lambda _mid: (
        common.load_embed_table(snap)
        if tied
        else common.load_weight(snap, "lm_head.weight").float()
    )
    if readout == "norm_centered":
        import torch
        from global_workspace.lens import stacked_jacobians
        from jlens import JacobianLens
        from safetensors import safe_open

        dev = "cuda" if torch.cuda.is_available() else "cpu"
        nw = common.load_weight(snap, "language_model.norm.weight").float().to(dev)
        stack = stacked_jacobians(JacobianLens.from_pretrained(lens_repo, filename=lens),
                                  device=dev, dtype=torch.float32)  # fmt: skip
        # per-layer mean of the normalized transported vector over ALL positions of a sample of
        # the bank's own captures (a fixed direction: the bank reads one position per rollout,
        # so a within-prompt mean would cancel everything)
        man = json.loads((acts / "manifest.json").read_text())
        cap_layers = man["layers"]
        sums = {layer: torch.zeros(stack.shape[1], device=dev) for layer in cap_layers}
        cnt = 0
        for p in man["prompts"][:40]:
            with safe_open(str(acts / p["file"]), framework="pt", device="cpu") as f:
                a = f.get_tensor("acts").float().to(dev)  # [layers, pos, d]
            for li, layer in enumerate(cap_layers):
                jh = a[li] @ stack[layer].T
                sums[layer] += (jh / jh.pow(2).mean(-1, keepdim=True).sqrt() * nw).sum(0)
            cnt += a.shape[1]
        mean_dir = {layer: v / cnt for layer, v in sums.items()}
        # identify which layer a J slice is (jlens_eval passes slices, not layer ids)
        keys = {layer: float(stack[layer, 0, :8].sum()) for layer in cap_layers}

        def _norm_centered(jac, resid, w_u, *, denom=None):  # same signature as cosine_readout
            out = []
            for jm, h in zip(jac, resid, strict=True):
                layer = min(keys, key=lambda k: abs(keys[k] - float(jm[0, :8].sum())))
                jh = h @ jm.T
                jh = jh / jh.pow(2).mean(-1, keepdim=True).sqrt() * nw
                out.append((jh - mean_dir[layer]) @ w_u.T)
            return torch.stack(out)

        import global_workspace.lens as gl  # jlens_eval imports it inside main()

        gl.cosine_readout = _norm_centered
    sys.argv = [
        "jlens_eval.py",
        f"model_id={model_id}",
        f"lens_repo={lens_repo}",
        f"lens_file={lens}",
        f"acts_dir={acts}",
        f"out_dir={gen}",
        f"k={k}",
        f"layers={layers}",
    ]
    jlens_eval.main()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--layers", required=True, help="remapped grid, e.g. 10:31:2")
    ap.add_argument("--lens", required=True)
    ap.add_argument(
        "--stage", default="all", choices=["all", "rollout", "capture", "jlens", "assemble"]
    )
    ap.add_argument("--max-new", type=int, default=512)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--revision", default=None, help="pin the subject's HF revision")
    ap.add_argument("--readout", default="cosine", choices=["cosine", "norm_centered"])
    ap.add_argument(
        "--lens-repo",
        default="neuronpedia/jacobian-lens",
        help="HF repo, or a local lens file (e.g. one fitted by fit_jlens_modal.py)",
    )
    a = ap.parse_args()
    if a.revision:  # every stage reads the pinned snapshot (local path), never "latest"
        from huggingface_hub import snapshot_download

        a.model = snapshot_download(a.model, revision=a.revision, local_files_only=True)
    work = WSB / "adapted" / a.tag / "jlens_work"
    work.mkdir(parents=True, exist_ok=True)
    items, acts, gen = work / "items.json", work / "acts", work / "gen"
    if a.stage in ("all", "rollout"):
        meta = rollouts(a.model, items, a.max_new, a.seed, a.batch)
        (work / "items_manifest.json").write_text(json.dumps(meta, indent=1))
    if a.stage in ("all", "capture"):
        subprocess.run(
            [
                sys.executable,
                str(OLS / "capture_acts.py"),
                f"model_id={a.model}",
                f"prompts_json={items}",
                f"out_dir={acts}",
                f"layers={a.layers}",
                "max_positions=2048",
            ],
            check=True,
            cwd=GW,
        )
    if a.stage in ("all", "jlens"):
        jlens(a.model, a.lens, acts, gen, a.layers, 10, a.lens_repo, a.readout)
    if a.stage in ("all", "assemble"):
        dst = WSB / "adapted" / a.tag / "jlens_concept_pr"
        man = json.loads((acts / "manifest.json").read_text())
        for p in man.get("prompts", []):
            p.pop("tokens", None)  # the frozen bank strips the decoded tokens too
        man["adapt"] = {
            "model": a.model,
            "lens": a.lens,
            "layers": a.layers,
            "items_manifest": json.loads((work / "items_manifest.json").read_text()),
        }
        dst.mkdir(parents=True, exist_ok=True)
        (dst / "manifest.json").write_text(json.dumps(man, indent=1))
        if (dst / "gen-jlens-pr-jlens").exists():
            shutil.rmtree(dst / "gen-jlens-pr-jlens")
        shutil.copytree(gen, dst / "gen-jlens-pr-jlens")
        shutil.copy(items, dst / "items.json")  # the subject's rollout ids: the plan carries them
        print(f"[assemble] {len(man.get('prompts', []))} items -> {dst}")


if __name__ == "__main__":
    main()
