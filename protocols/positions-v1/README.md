# Archived position-reduction candidate

Status: parked, empirical validation pending. See [project status](../../docs/project-status.md).

- `positions-v1-candidate.json`: resolved 3,356-item, 48,981-cell common manifest, including
  original input IDs, positions, layers, bank hashes, and tokenizer provenance. Its internal
  manifest digest is `4bf0826229976d94c6a31b634a3be45514dcd9b15cad87bd706aa81d43f8decc`.
- `draft-selection.jsonl`: the original position selection before compilation.
- `fidelity-preregistration-v1.json`: frozen grouped split (1,677 calibration / 1,679 audit
  items), thresholds and limitations. It is a plan, not a passed validation result.
- `census.csv`: historical dense-grid census; its caveats describe evidence available when
  written. Precision inputs were subsequently recovered into the resolved manifest.
- Calibration and fusion reports and their JSON records preserve the small diagnostics.
  Their references to local scripts/output paths are historical; they are not turnkey
  commands or evidence of a full benchmark run. Model replies inside JSON are untrusted data.
- `checksums.json`: byte lengths and SHA-256 hashes of these copied artifacts. The archive's `.gitattributes`
  preserves payload bytes across checkouts, including original line endings.

The subject is Qwen/Qwen3.6-27B at revision
`6a9e13bd6fc8f0983b9b99948120bc37f49c13e9`. Reader locks are tracked in
`src/wsbench/produce/reference_readers.json`. Derive compatible reader manifests locally:

```sh
uv run python -m wsbench.produce.reference \
  --manifest protocols/positions-v1/positions-v1-candidate.json \
  --out outputs/manifests/readers
```

This command derives plans; it does not load model weights or authorize a GPU run. The
common manifest contains unsupported layers for some readers, so do not run every reader
against it directly. Generated readouts, model weights, and external research caches are
not included. No held-out fidelity results or completed cloud baseline are claimed.
