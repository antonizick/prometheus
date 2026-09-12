#!/usr/bin/env python3
"""Phase 0 acceptance tests (docs/04-build-plan.md).

Checks every criterion that can be checked without a human ear or a reboot.
Run with Prometheus powered on:

    prometheus on && experiments/acceptance-phase0.py

Audio will play out loud — that is the point.

Two criteria are deliberately not automated and are reported as MANUAL:
the voice/timbre judgements, and the reboot round-trip.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time

RUNTIME_DIR = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
SOCK = os.path.join(RUNTIME_DIR, "prometheus", "sock")
COLD_BASELINE_TTFS_MS = 310.0  # measured cold-start Piper, docs/02

results: list[tuple[str, bool | None, str]] = []


def record(name: str, ok: bool | None, detail: str) -> None:
    results.append((name, ok, detail))
    tag = {True: "\033[32mPASS\033[0m", False: "\033[31mFAIL\033[0m",
           None: "\033[33mMANUAL\033[0m"}[ok]
    print(f"  [{tag}] {name}: {detail}")


def send(obj, wait=False, timeout=20.0):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect(SOCK)
    try:
        if wait:
            obj = dict(obj, ack=True)
        s.sendall(json.dumps(obj).encode() + b"\n")
        if not wait:
            return None
        buf = b""
        while b"\n" not in buf:
            c = s.recv(4096)
            if not c:
                return None
            buf += c
        return json.loads(buf.split(b"\n", 1)[0])
    finally:
        s.close()


def daemon_pid() -> str | None:
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            argv = open(f"/proc/{pid}/cmdline", "rb").read().split(b"\0")
        except OSError:
            continue
        names = [os.path.basename(a.decode(errors="replace")) for a in argv[:2] if a]
        if "prometheusd" in names:
            return pid
    return None


def children(pid: str, exe: str) -> list[str]:
    out = []
    for p in os.listdir("/proc"):
        if not p.isdigit():
            continue
        try:
            argv = open(f"/proc/{p}/cmdline", "rb").read().split(b"\0")
            stat = open(f"/proc/{p}/stat").read()
            ppid = stat.split(") ", 1)[1].split()[1]
        except (OSError, IndexError):
            continue
        if ppid == pid and argv and argv[0] and \
                os.path.basename(argv[0].decode(errors="replace")) == exe:
            out.append(p)
    return out


class Sampler(threading.Thread):
    """Test-harness only: samples paplay children to prove non-overlap."""

    def __init__(self, pid: str, interval: float = 0.004):
        super().__init__(daemon=True)
        self.pid, self.interval = pid, interval
        self.max_concurrent = 0
        self.samples = 0
        self.stop_flag = threading.Event()
        self.first_silent_at: float | None = None
        self._watch_silence = False
        self._t0 = 0.0

    def watch_silence_from(self, t0: float) -> None:
        self._t0, self._watch_silence, self.first_silent_at = t0, True, None

    def run(self):
        while not self.stop_flag.is_set():
            n = len(children(self.pid, "paplay"))
            self.max_concurrent = max(self.max_concurrent, n)
            self.samples += 1
            if self._watch_silence and n == 0 and self.first_silent_at is None:
                self.first_silent_at = time.monotonic() - self._t0
            time.sleep(self.interval)


LONG = ("Claude is waiting for permission to run a command in the auth "
        "middleware, and has been waiting for quite a while now, so you "
        "probably want to take a look at it before carrying on.")


def main() -> int:
    if not os.path.exists(SOCK):
        print("Daemon not running. Start it with:  prometheus on", file=sys.stderr)
        return 1
    pid = daemon_pid()
    if not pid:
        print("Cannot find prometheusd", file=sys.stderr)
        return 1

    print(f"\nprometheusd pid {pid}\n")

    # -- 1. time to first sound -------------------------------------------
    print("1. Time-to-first-sound vs the 0.31 s cold-start baseline")
    ttfs = []
    for _ in range(5):
        r = send({"text": "Opened Brave browser.", "category": "manual"}, wait=True)
        if r and r.get("status") == "spoken":
            ttfs.append(float(r["detail"].rstrip("ms")))
        time.sleep(0.15)
    best = min(ttfs) if ttfs else 9e9
    avg = sum(ttfs) / len(ttfs) if ttfs else 9e9
    record("time-to-first-sound", avg < COLD_BASELINE_TTFS_MS,
           f"avg {avg:.0f} ms, best {best:.0f} ms (baseline {COLD_BASELINE_TTFS_MS:.0f} ms)")

    # -- 2. ten rapid calls must queue, never overlap ----------------------
    print("\n2. Ten rapid calls queue cleanly and never overlap")
    sampler = Sampler(pid)
    sampler.start()
    replies: list[dict] = []
    lock = threading.Lock()

    def fire(i):
        r = send({"text": f"Message number {i}.", "category": "manual"}, wait=True,
                 timeout=60)
        with lock:
            replies.append(r or {})

    threads = [threading.Thread(target=fire, args=(i,)) for i in range(1, 11)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    time.sleep(0.3)
    sampler.stop_flag.set()
    sampler.join(timeout=1)

    spoken = sum(1 for r in replies if r.get("status") == "spoken")
    record("ten rapid calls all spoken", spoken == 10, f"{spoken}/10 spoken")
    record("never overlap", sampler.max_concurrent <= 1,
           f"max concurrent paplay = {sampler.max_concurrent} "
           f"({sampler.samples} samples)")

    # -- 3. shut-up key ----------------------------------------------------
    print("\n3. Shut-up cuts speech mid-word")
    latencies = []
    for _ in range(3):
        s = Sampler(pid)
        s.start()
        threading.Thread(target=lambda: send({"text": LONG, "category": "manual"}),
                         daemon=True).start()
        time.sleep(1.2)                       # let it get properly going
        if not children(pid, "paplay"):
            s.stop_flag.set()
            continue
        t0 = time.monotonic()
        s.watch_silence_from(t0)
        send({"control": "stop"})
        deadline = time.monotonic() + 3
        while s.first_silent_at is None and time.monotonic() < deadline:
            time.sleep(0.005)
        s.stop_flag.set()
        s.join(timeout=1)
        if s.first_silent_at is not None:
            latencies.append(s.first_silent_at * 1000)
        time.sleep(0.3)
    worst = max(latencies) if latencies else 9e9
    record("shut-up latency", worst < 100,
           f"worst {worst:.0f} ms over {len(latencies)} runs "
           f"({', '.join(f'{l:.0f}' for l in latencies)} ms)")

    # -- 4. mic gate -------------------------------------------------------
    print("\n4. Mic gate: speech stops when voxtype starts recording")
    fake = os.environ.get("PROMETHEUS_VOXTYPE_DIR")
    if not fake:
        record("mic gate", None,
               "run via experiments/run-acceptance.sh to exercise this "
               "against a fake voxtype dir")
    else:
        state = os.path.join(fake, "state")
        lat = []
        for _ in range(3):
            with open(state, "w") as f:
                f.write("idle")
            time.sleep(0.25)
            s = Sampler(pid)
            s.start()
            threading.Thread(target=lambda: send({"text": LONG, "category": "manual"}),
                             daemon=True).start()
            time.sleep(1.2)
            if not children(pid, "paplay"):
                s.stop_flag.set()
                continue
            t0 = time.monotonic()
            s.watch_silence_from(t0)
            with open(state, "w") as f:
                f.write("recording")
            deadline = time.monotonic() + 3
            while s.first_silent_at is None and time.monotonic() < deadline:
                time.sleep(0.005)
            s.stop_flag.set()
            s.join(timeout=1)
            if s.first_silent_at is not None:
                lat.append(s.first_silent_at * 1000)
            with open(state, "w") as f:
                f.write("idle")
            time.sleep(0.4)
        worst_mic = max(lat) if lat else 9e9
        record("mic gate stop latency", worst_mic < 200,
               f"worst {worst_mic:.0f} ms over {len(lat)} runs "
               f"({', '.join(f'{l:.0f}' for l in lat)} ms)")

        # queue held while recording, resumed on idle
        with open(state, "w") as f:
            f.write("recording")
        time.sleep(0.3)
        held = {"done": False}

        def held_call():
            send({"text": "Held while the microphone was live.",
                  "category": "manual"}, wait=True, timeout=30)
            held["done"] = True

        threading.Thread(target=held_call, daemon=True).start()
        time.sleep(1.5)
        spoke_while_recording = held["done"]
        with open(state, "w") as f:
            f.write("idle")
        t0 = time.monotonic()
        while not held["done"] and time.monotonic() - t0 < 10:
            time.sleep(0.02)
        record("queue held during recording, resumed on idle",
               (not spoke_while_recording) and held["done"],
               f"held={not spoke_while_recording}, resumed={held['done']}")

    # -- 5. priority, dedup, TTL, ambient ----------------------------------
    print("\n5. Queue semantics")
    r1 = send({"text": "Deduplicated.", "dedup_key": "t:dedup", "category": "manual"},
              wait=True)
    r2 = send({"text": "Deduplicated.", "dedup_key": "t:dedup", "category": "manual"},
              wait=True, timeout=5)
    record("dedup suppresses a repeat", (r2 or {}).get("detail") == "dedup",
           f"first={(r1 or {}).get('status')}, second={(r2 or {}).get('detail')}")

    send({"text": LONG, "category": "manual"})
    time.sleep(0.4)

    # Submitted while LONG is still speaking, so both are judged against a
    # genuinely busy queue rather than an empty one.
    amb = send({"text": "Ambient chatter.", "priority": "ambient",
                "category": "hypr"}, wait=True, timeout=20)
    record("ambient dropped when something else is queued",
           (amb or {}).get("detail") == "ambient superseded",
           f"{(amb or {}).get('status')}: {(amb or {}).get('detail')}")

    r = send({"text": "This should expire before it is reached.", "ttl_ms": 300,
              "category": "manual"}, wait=True, timeout=20)
    record("TTL expires stale intents", (r or {}).get("detail") == "ttl expired",
           f"{(r or {}).get('status')}: {(r or {}).get('detail')}")

    crit_t0 = time.monotonic()
    r = send({"text": "Claude is waiting for you.", "priority": "critical",
              "category": "manual"}, wait=True, timeout=20)
    crit_wait = time.monotonic() - crit_t0
    record("critical preempts what is speaking",
           (r or {}).get("status") == "spoken" and crit_wait < 4,
           f"spoke after {crit_wait * 1000:.0f} ms")
    send({"control": "stop"})
    time.sleep(0.3)

    # -- 6. config hot reload ---------------------------------------------
    print("\n6. Editing config.json takes effect without a restart")
    cfg_path = os.path.join(os.environ.get("XDG_CONFIG_HOME",
                                           os.path.expanduser("~/.config")),
                            "prometheus", "config.json")
    original = open(cfg_path).read()
    before = subprocess.run(["journalctl", "--user", "-u", "prometheusd.service",
                             "-n", "1", "--no-pager", "-o", "cat"],
                            capture_output=True, text=True).stdout
    try:
        patched = original.replace('"latency_msec": 50', '"latency_msec": 40')
        changed = patched != original
        with open(cfg_path, "w") as f:
            f.write(patched)
        time.sleep(1.0)
        after = subprocess.run(["journalctl", "--user", "-u", "prometheusd.service",
                                "-n", "5", "--no-pager", "-o", "cat"],
                               capture_output=True, text=True).stdout
        reloaded = "config.reloaded" in after and after != before
        record("config.json hot-reloaded via inotify", reloaded and changed,
               "daemon logged a reload without restarting" if reloaded
               else "no reload observed")
    finally:
        with open(cfg_path, "w") as f:
            f.write(original)
        time.sleep(0.6)

    still = send({"control": "ping"}, wait=True, timeout=3)
    record("daemon survived the whole run", (still or {}).get("status") == "ok",
           "still responding" if still else "NOT RESPONDING")

    same_pid = daemon_pid() == pid
    record("no restart during the run", same_pid, f"pid still {pid}" if same_pid
           else "pid changed — the daemon restarted")

    # -- manual ------------------------------------------------------------
    print("\n7. Needs a human")
    record("voice is en_GB-alan-medium at length_scale 0.7", None,
           "locked in config; confirm by ear")
    record("both voices distinguishable and pleasant", None,
           "run: prometheus audition --fetch   (build plan task 0.10)")
    record("toggle survives a full reboot in both directions", None,
           "reboot with it on, then with it off; check `prometheus status`")

    # -- summary -----------------------------------------------------------
    passed = sum(1 for _, ok, _ in results if ok is True)
    failed = sum(1 for _, ok, _ in results if ok is False)
    manual = sum(1 for _, ok, _ in results if ok is None)
    print(f"\n{'=' * 66}\n{passed} passed, {failed} failed, {manual} need a human\n")
    if failed:
        for name, ok, detail in results:
            if ok is False:
                print(f"  FAILED: {name} — {detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
