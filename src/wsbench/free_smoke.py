"""Tiny public-input free-route checks; persist each outcome before the next request."""

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path

from wsbench import llm
from wsbench.free_route import active


def run(out: Path, formats: tuple[str, ...] = ("json", "text")) -> dict:
    policy = active()
    if policy is None:
        raise llm.JudgeConfigError("free smoke requires WSBENCH_FREE_ONLY=1")
    report = {"started": time.time(), "route": policy.config, "tests": []}

    def save() -> None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    save()
    for format_ in formats:
        if format_ not in ("json", "text", "thinking_text"):
            raise ValueError(f"unknown smoke format: {format_}")
        results = []
        spend = llm.Spend()
        entry = {"format": format_}
        try:
            if format_ == "json":
                expected = {"ok": True, "labels": ["neutral"]}
                schema = llm.schema_block(
                    "smoke",
                    {
                        "ok": {"type": "boolean"},
                        "labels": {"type": "array", "items": {"type": "string"}},
                    },
                    ["ok", "labels"],
                )
                llm.stream_json(
                    [("Follow the JSON schema exactly.", 'Return ok=true and labels=["neutral"].')],
                    schema=schema,
                    model=policy.model,
                    reasoning={"effort": "minimal"},
                    temperature=0,
                    max_tokens=512,
                    concurrency=1,
                    rpm=10,
                    spend=spend,
                    on_result=lambda i, r, sink=results: sink.append(r),
                )
            else:
                expected = "a neutral account"
                llm.stream_text(
                    ["Reply with exactly the words: a neutral account"],
                    model=policy.model,
                    thinking=format_ == "thinking_text",
                    max_tokens=512,
                    concurrency=1,
                    rpm=10,
                    spend=spend,
                    on_result=lambda i, r, sink=results: sink.append(r),
                )
            entry["pass"] = results == [expected]
        except llm.JudgeConfigError as e:
            entry.update({"pass": False, "error": str(e)})
        entry.update({"results": results, "spend": asdict(spend)})
        report["tests"].append(entry)
        save()
        if "error" in entry:
            break
    report["finished"] = time.time()
    save()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--formats", default="json,text,thinking_text")
    args = parser.parse_args()
    report = run(args.out, tuple(args.formats.split(",")))
    print(json.dumps(report))
    if not all(row["pass"] for row in report["tests"]):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
