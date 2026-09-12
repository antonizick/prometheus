#!/usr/bin/env python3
"""Phase 2 task 2.3 — benchmark candidate models from docs/03-model-selection.md.

Talks to an already-running `ollama serve` on 127.0.0.1:11434. For each
candidate, stops it first (clean cold-load measurement), runs it cold once,
then warm over every sample in samples.jsonl (task 2.2), and records:

  - load time (from the cold call's `load_duration`)
  - latency p50/p95 (warm calls' `total_duration`)
  - tokens/sec (warm calls, eval_count / eval_duration)
  - VRAM actually used (`ollama ps`, cross-checked against nvidia-smi delta)
  - length discipline (% of outputs <= 30 words)
  - speakability (post-filter simulation: markdown/paths/code/banned openers)
  - the NOTHING escape hatch firing rate

Writes experiments/model-bench.md (summary, for humans) and
experiments/model-bench-raw.jsonl (every response, for task 2.4's blind
listening prep and for future re-analysis).

Point 7 of the benchmark protocol — blind quality ranking by ear — is
deliberately NOT done here. That's Nick's job (task 2.4); this script only
produces the candidates for it.
"""
from __future__ import annotations

import json
import re
import subprocess
import time
import urllib.request
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
SAMPLES_PATH = ROOT / "experiments" / "samples.jsonl"
OUT_MD = ROOT / "experiments" / "model-bench.md"
OUT_RAW = ROOT / "experiments" / "model-bench-raw.jsonl"
OLLAMA_URL = "http://127.0.0.1:11434"

# (tag, role, needs_think_false)
CANDIDATES = [
    ("qwen3:4b-instruct", "runtime — primary candidate", False),
    ("llama3.2:3b", "runtime — fallback if 4b sluggish", False),
    ("qwen3:1.7b", "speed experiment", True),
    ("llama3.2:1b", "speed experiment", False),
    ("qwen3:8b", "authoring / runtime-quality fallback", True),
]

INSTRUCTIONS = """You narrate a developer's computer out loud. You will be given the output
of a command or an AI assistant's message.

Reply with at most two short sentences describing the outcome, written to be
spoken aloud.

Never use: lists, bullet points, markdown, file paths, function names,
code, or identifiers. Say "the auth middleware", not "src/auth/mw.ts".
Never begin with "Here is" or "The output shows". State the outcome directly.
If nothing noteworthy happened, reply exactly: NOTHING"""

NUM_PREDICT = 60
TEMPERATURE = 0.7
TIMEOUT = 20  # generous for benchmarking; the runtime wrapper (2.5) uses 4s


def build_system_prompt() -> str:
    persona = (CONFIG_DIR / "persona.md").read_text()
    about_me = (CONFIG_DIR / "about-me.md").read_text()
    return f"{persona}\n{about_me}\n\n{INSTRUCTIONS}"


def load_samples() -> list[dict]:
    with open(SAMPLES_PATH) as f:
        return [json.loads(line) for line in f if line.strip()]


def ollama_stop(tag: str) -> None:
    subprocess.run(["ollama", "stop", tag], capture_output=True)
    time.sleep(0.5)


def nvidia_vram_used() -> int:
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        capture_output=True, text=True,
    ).stdout.strip()
    return int(out.splitlines()[0])


def ollama_ps_size(tag: str) -> str | None:
    out = subprocess.run(["ollama", "ps"], capture_output=True, text=True).stdout
    for line in out.splitlines()[1:]:
        if line.startswith(tag.split(":")[0]) and tag in line:
            parts = line.split()
            # NAME ID SIZE ... — SIZE is "3.2" then "GB" as two tokens
            for i, p in enumerate(parts):
                if p in ("GB", "MB"):
                    return f"{parts[i-1]} {p}"
    return None


def chat(tag: str, system: str, user: str, think_false: bool) -> dict:
    body = {
        "model": tag,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "options": {"num_predict": NUM_PREDICT, "temperature": TEMPERATURE},
    }
    if think_false:
        body["think"] = False
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            wall = time.monotonic() - t0
            data = json.loads(resp.read())
            data["_wall_secs"] = wall
            return data
    except Exception as e:
        return {"_error": str(e), "_wall_secs": time.monotonic() - t0}


# --------------------------------------------------------------------------
# post-filter simulation (mirrors the design in docs/03 — the real filter
# lands in bin/prometheus-llm, task 2.5)
# --------------------------------------------------------------------------

PATH_RE = re.compile(r"(/[\w.\-]+){2,}|\b\w+\.(py|js|ts|json|md|c|sh|rs|go|toml)\b")
CODE_RE = re.compile(r"`[^`]+`|```")
LIST_RE = re.compile(r"(?m)^\s*([-*]|\d+\.)\s")
BANNED_OPENERS = ("here is", "here's", "the output shows", "the output indicates")


def speakability_issues(text: str) -> list[str]:
    issues = []
    if PATH_RE.search(text):
        issues.append("path-like")
    if CODE_RE.search(text):
        issues.append("code/backtick")
    if LIST_RE.search(text):
        issues.append("list/bullet")
    low = text.strip().lower()
    if low.startswith(BANNED_OPENERS):
        issues.append("banned-opener")
    return issues


def p95(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(len(s) - 1, int(round(0.95 * (len(s) - 1))))
    return s[idx]


def main() -> None:
    system_prompt = build_system_prompt()
    samples = load_samples()
    print(f"loaded {len(samples)} samples")

    results = []
    raw_records = []

    baseline_vram = nvidia_vram_used()
    print(f"baseline VRAM (nothing loaded): {baseline_vram} MiB")

    for tag, role, think_false in CANDIDATES:
        print(f"\n=== {tag} ({role}) ===")
        ollama_stop(tag)
        time.sleep(1)
        vram_before = nvidia_vram_used()

        # cold call — first sample pays the load cost
        first = samples[0]
        cold = chat(tag, system_prompt, first["text"], think_false)
        if "_error" in cold:
            print(f"  COLD CALL FAILED: {cold['_error']}")
            results.append({"tag": tag, "role": role, "error": cold["_error"]})
            continue
        load_secs = cold.get("load_duration", 0) / 1e9
        vram_loaded = nvidia_vram_used()
        ps_size = ollama_ps_size(tag)

        latencies = []
        toks_per_sec = []
        word_counts = []
        issues_count = 0
        nothing_count = 0
        outcome_checks = []

        for i, sample in enumerate(samples):
            if i == 0:
                data = cold  # reuse the cold call instead of repeating sample 0
            else:
                data = chat(tag, system_prompt, sample["text"], think_false)
            if "_error" in data:
                print(f"  sample {sample['id']}: ERROR {data['_error']}")
                continue
            msg = data.get("message", {})
            text = (msg.get("content") or "").strip()
            thinking_leak = bool(msg.get("thinking")) or "<think>" in text
            total = data.get("total_duration", 0) / 1e9
            evalc = data.get("eval_count", 0)
            evald = data.get("eval_duration", 1) / 1e9
            if i > 0:  # exclude the cold call from warm latency stats
                latencies.append(total)
                if evald > 0:
                    toks_per_sec.append(evalc / evald)

            is_nothing = text.strip().upper() == "NOTHING"
            if is_nothing:
                nothing_count += 1
                wc = 0
            else:
                wc = len(text.split())
                word_counts.append(wc)

            issues = speakability_issues(text) if not is_nothing else []
            if thinking_leak:
                issues.append("THINKING-LEAK")
            if issues:
                issues_count += 1

            raw_records.append({
                "model": tag, "sample_id": sample["id"], "category": sample["category"],
                "expected_outcome": sample.get("expected_outcome"),
                "response": text, "word_count": wc, "issues": issues,
                "latency_secs": round(total, 3), "cold": i == 0,
            })

            outcome_checks.append((sample.get("expected_outcome"), text))

        n = max(1, len([r for r in word_counts]) + nothing_count)
        under_30 = sum(1 for wc in word_counts if wc <= 30) + nothing_count
        result = {
            "tag": tag, "role": role,
            "load_secs": round(load_secs, 2),
            "vram_mib": vram_loaded - vram_before,
            "ollama_ps_size": ps_size,
            "p50_latency": round(median(latencies), 2) if latencies else None,
            "p95_latency": round(p95(latencies), 2) if latencies else None,
            "toks_per_sec": round(median(toks_per_sec), 1) if toks_per_sec else None,
            "pct_under_30_words": round(100 * under_30 / n, 1),
            "pct_clean_speakability": round(100 * (n - issues_count) / n, 1),
            "nothing_count": nothing_count,
            "n_samples": n,
        }
        results.append(result)
        print(f"  load {result['load_secs']}s  vram +{result['vram_mib']}MiB  "
              f"p50 {result['p50_latency']}s  p95 {result['p95_latency']}s  "
              f"<=30w {result['pct_under_30_words']}%  clean {result['pct_clean_speakability']}%")

        ollama_stop(tag)
        time.sleep(1)

    final_vram = nvidia_vram_used()
    print(f"\nfinal VRAM after stopping every candidate: {final_vram} MiB "
          f"(baseline was {baseline_vram} MiB)")

    with open(OUT_RAW, "w") as f:
        for r in raw_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    write_markdown(results, baseline_vram, final_vram, len(samples))
    print(f"\nwrote {OUT_MD} and {OUT_RAW}")


def write_markdown(results, baseline_vram, final_vram, n_samples) -> None:
    lines = []
    lines.append("# Model bench — Phase 2 task 2.3\n")
    lines.append(f"Benchmarked against {n_samples} real samples from "
                  f"`samples.jsonl` (task 2.2). Baseline VRAM with nothing "
                  f"loaded: **{baseline_vram} MiB**. After stopping every "
                  f"candidate: **{final_vram} MiB** — "
                  f"{'confirms VRAM returns to baseline' if abs(final_vram - baseline_vram) < 200 else 'DID NOT RETURN TO BASELINE, investigate'}.\n")
    lines.append("| Model | Role | Load | VRAM | ollama ps | p50 | p95 | tok/s | ≤30 words | clean speakability | NOTHING |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in results:
        if "error" in r:
            lines.append(f"| {r['tag']} | {r['role']} | — | — | — | — | — | — | — | — | FAILED: {r['error']} |")
            continue
        lines.append(
            f"| {r['tag']} | {r['role']} | {r['load_secs']}s | {r['vram_mib']} MiB | "
            f"{r['ollama_ps_size']} | {r['p50_latency']}s | {r['p95_latency']}s | "
            f"{r['toks_per_sec']} | {r['pct_under_30_words']}% | "
            f"{r['pct_clean_speakability']}% | {r['nothing_count']}/{r['n_samples']} |"
        )
    lines.append("")
    lines.append("Raw per-sample responses (all models × all samples) are in "
                  "`model-bench-raw.jsonl` — that's the input for task 2.4's "
                  "blind listening test.")
    lines.append("")
    lines.append("**Acceptance targets (docs/04, Phase 2):** p95 < ~2.5s warm, "
                  ">90% under 30 words, no paths/code/markdown/bullets surviving "
                  "the post-filter (columns above simulate the filter check, not "
                  "the actual bin/prometheus-llm post-filter — that always runs "
                  "regardless of what the model does).")
    OUT_MD.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
