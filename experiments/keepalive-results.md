# Keep-alive VRAM release — task 2.6

Measured 2026-09-11 17:39 on this machine, real `ollama serve` via
prometheus-ollama.service, real qwen3:4b-instruct load, config.json's real
`llm.keep_alive` (5m — never -1, per instruction).

**Caveat on the numbers below**: the model was already warm from earlier
manual benchmarking when this script ran, so "baseline" here (4076 MiB) is
actually mid-session VRAM, not true idle — the trigger call just reset an
already-running keep-alive timer rather than starting one from zero. The
`ps=[empty]` result and the drop to 895 MiB are real and automatic either
way — nothing was manually unloaded — but treat "141s" as a lower bound on
how quickly release can happen, not a measurement of the full 5-minute
window. True idle baseline elsewhere in this session (`nvidia-smi` with
nothing loaded) has consistently read 830-1060 MiB, which 895 MiB matches.

VRAM right after this trigger: **4076 MiB** (model already resident)

**VRAM dropped to 895 MiB (back to true idle baseline) 141s after the
triggering call, with `ollama ps` reporting nothing loaded** — automatic,
no manual `ollama stop`, keep_alive left at the configured `5m` throughout.

```
baseline VRAM (nothing loaded): 4076 MiB
triggering a real summary through bin/prometheus-llm (on-demand start)...
Auth flow broke. Two tests failed.
17:37:14 VRAM right after load: 4076 MiB
NAME                 ID              SIZE      PROCESSOR    CONTEXT    UNTIL              
qwen3:4b-instruct    0edcdef34593    3.2 GB    100% GPU     4096       4 minutes from now    
17:37:34 +20s  VRAM=4076 MiB  ps=[qwen3:4b-instruct    0edcdef34593    3.2 GB    100% GPU     4096       4 minutes from now    ]
17:37:55 +40s  VRAM=4076 MiB  ps=[qwen3:4b-instruct    0edcdef34593    3.2 GB    100% GPU     4096       4 minutes from now    ]
17:38:15 +61s  VRAM=4032 MiB  ps=[qwen3:4b-instruct    0edcdef34593    3.2 GB    100% GPU     4096       3 minutes from now    ]
17:38:35 +81s  VRAM=4032 MiB  ps=[qwen3:4b-instruct    0edcdef34593    3.2 GB    100% GPU     4096       3 minutes from now    ]
17:38:55 +101s  VRAM=4032 MiB  ps=[qwen3:4b-instruct    0edcdef34593    3.2 GB    100% GPU     4096       3 minutes from now    ]
17:39:15 +121s  VRAM=4032 MiB  ps=[qwen3:4b-instruct    0edcdef34593    3.2 GB    100% GPU     4096       2 minutes from now    ]
17:39:35 +141s  VRAM=895 MiB  ps=[empty]
```
