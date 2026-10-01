"""OLED live monitor for PREREG_qwen_max.md: teacher labelling -> gate -> pod -> training -> test read -> verdict.

    python wsbjev/dash_q38/server.py 8795
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import time
import urllib.request
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))
VERD = ROOT / "runs/open_teacher/qwen__qwen3.8-27b/verdicts.jsonl"
ADDR = ROOT / "runs/pod_q38_addr.txt"
GATE = ROOT / "runs/open_teacher/qwen_max_gate.json"
RESULT = ROOT / "runs/open_teacher/qwen38_judge_test.json"
STAR = "Qwen3.8-27B + voice note (judge)"
TOTAL = 3529
KEY = str(Path.home() / ".ssh" / "autolabs_runpod")
SSH = next((p for p in (r"C:\Program Files\Git\usr\bin\ssh.exe", r"C:\Windows\System32\OpenSSH\ssh.exe") if Path(p).exists()), "ssh")
REMOTE = r'''f=/workspace/kevft/q38.log; echo "AGE=$(( $(date +%s) - $(stat -c %Y "$f" 2>/dev/null || date +%s) ))"; tr "\r" "\n" < "$f" 2>/dev/null | grep -E "^ep[0-9]+ step |^\[[0-9:]+\] " | tail -400; echo "@@S"; grep -E "^\[" /workspace/setup.log 2>/dev/null | tail -3; ls /workspace/SETUP_DONE 2>/dev/null; echo "@@M"; for x in /workspace/DONE_*; do [ -f "$x" ] && echo "$(basename $x)=$(cat $x)"; done; echo "@@G"; nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader,nounits; echo "@@L"; cat /workspace/wsbjev/runs/live/*test\ items*.json 2>/dev/null | tail -c 600'''
STATE: dict = {"updated": 0}
HIST: list = []  # (t, labels) for a live rate


def labelling() -> dict:
    best, err, usd = {}, 0, 0.0
    if VERD.exists():
        for line in VERD.read_text(encoding="utf-8").splitlines():
            try:
                v = json.loads(line)
            except ValueError:
                continue
            if v.get("run") not in ("smoke", "teacher"):
                continue
            usd += v.get("usd") or 0
            r = v.get("result")
            vs = r.get("verdicts") if isinstance(r, dict) else None
            if isinstance(vs, list) and vs and isinstance(vs[0], dict):
                best[v.get("h_orig") or v["h"]] = str(vs[0].get("label", "?")).strip().lower()
            elif v.get("error"):
                err += 1
    mix = Counter(best.values())
    now = time.time()
    HIST.append((now, len(best)))
    while HIST and now - HIST[0][0] > 90:
        HIST.pop(0)
    rate = (HIST[-1][1] - HIST[0][1]) / max(HIST[-1][0] - HIST[0][0], 1e-6) if len(HIST) > 1 else 0.0
    return {"labels": len(best), "total": TOTAL, "errors": err, "usd": round(usd, 4), "rate": round(rate, 2),
            "mix": {k: mix.get(k, 0) for k in ("recognition", "echo", "topic", "noise")}}


def key_room() -> dict:
    try:
        from wsbjev import keys
        h = {"Authorization": "Bearer " + keys.get("OPENROUTER_API_KEY"), "User-Agent": "wsbjev-dash"}
        d = json.load(urllib.request.urlopen(urllib.request.Request("https://openrouter.ai/api/v1/key", headers=h), timeout=15))["data"]
        return {"limit": d.get("limit"), "remaining": None if d.get("limit") is None else round(d.get("limit_remaining") or 0, 2)}
    except Exception as e:  # noqa: BLE001
        return {"error": type(e).__name__}


def poll_pod() -> dict:
    if not ADDR.exists():
        return {}
    host, port = ADDR.read_text(encoding="utf-8").split()[:2]
    out = subprocess.run([SSH, "-i", KEY, "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null", "-o", "LogLevel=ERROR",
                          "-o", "ConnectTimeout=15", "-p", port, f"root@{host}", REMOTE], capture_output=True, text=True,
                         encoding="utf-8", errors="replace", timeout=45).stdout
    if not out.strip():
        return {"unreachable": True}
    main, _, rest = out.partition("@@S")
    setup, _, rest = rest.partition("@@M")
    marks, _, rest = rest.partition("@@G")
    gpu, _, live = rest.partition("@@L")
    age = re.search(r"AGE=(\d+)", main)
    steps, events = [], []
    for line in main.splitlines():
        m = re.match(r"ep(\d+) step (\d+)/(\d+) loss ([\d.]+) .* ([\d.]+)s/rec", line)
        if m:
            steps.append({"ep": int(m[1]), "step": int(m[2]), "total": int(m[3]), "loss": float(m[4]), "spr": float(m[5])})
        elif re.match(r"^\[[0-9:]+\] ", line):
            events.append(line.strip())
    g = [x.strip() for x in gpu.strip().split(",")] if gpu.strip() else []
    try:
        lv = json.loads(live.strip()) if live.strip() else {}
    except ValueError:
        lv = {}
    return {"age": int(age[1]) if age else None, "steps": steps, "events": events[-10:],
            "setup": [x for x in setup.strip().splitlines() if x], "setup_done": "/workspace/SETUP_DONE" in setup,
            "markers": dict(x.split("=", 1) for x in marks.split() if "=" in x),
            "gpu_util": g[0] if g else None, "gpu_mem": g[1] if len(g) > 1 else None,
            "test_live": {k: lv.get(k) for k in ("done", "total")} if lv else {}}


def local() -> dict:
    d = {"label": labelling()}
    for name, path in (("gate", GATE), ("result", RESULT)):
        try:
            d[name] = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    if "result" in d:
        p = d["result"].get("primary_568", {})
        d["result"] = {n: {k: p[n].get(k) for k in ("kappa_4way", "lb95_4way", "kappa_recognition", "lb95_recognition")} for n in p}
    try:
        w = json.loads((ROOT / "runs/watchdog/status.json").read_text(encoding="utf-8"))
        d["runpod"] = {"spent": round(w.get("total", 0), 2), "cap": w.get("cap"), "alive": w.get("alive")}
    except Exception:  # noqa: BLE001
        pass
    return d


def loop() -> None:
    n = 0
    while True:
        try:
            STATE["local"] = local()
            if n % 6 == 0:
                STATE["key"] = key_room()
            STATE["pod"] = poll_pod()
            STATE["error"] = None
        except Exception as e:  # noqa: BLE001
            STATE["error"] = f"{type(e).__name__}: {e}"[:200]
        STATE["updated"] = time.time()
        n += 1
        time.sleep(5)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a) -> None:
        pass

    def do_GET(self) -> None:
        if self.path.startswith("/api/state"):
            body = json.dumps({**STATE, "star": STAR, "now": time.time()}).encode()
            ctype = "application/json"
        else:
            body = (HERE / "index.html").read_bytes()
            ctype = "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8795
    threading.Thread(target=loop, daemon=True).start()
    print(f"q38 OLED dash on http://127.0.0.1:{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
