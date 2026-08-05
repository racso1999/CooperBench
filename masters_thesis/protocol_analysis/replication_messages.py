#!/usr/bin/env python3
"""Thematic + forensic analysis of the replication arm's inter-agent messages.

Motivates the six-arm protocol study: it reads every message the *replication*
free-text arm (``logs/flash_msg_*``) actually sent, codes it against nine
themes, and joins the dialogue to the patch-level outcome of the same run.

The headline the protocol arms were designed against: agents coordinate
exhaustively at *file* granularity, self-certify a clean merge in 63% of runs,
and then collide **below** the file level anyway --- 90% of conflicts start at
the byte-identical same line.

    uv run python masters_thesis/protocol_analysis/replication_messages.py
"""

from __future__ import annotations

import collections
import glob
import json
import os
import re

MSG_GLOB = "logs/flash_msg_*/coop/*/*/*/agent*_sent.jsonl"
EVAL_GLOB = "logs/flash_msg_*/coop/*/*/*/eval.json"

# Nine themes, coded by regex over the concatenated dialogue of each pair-run.
# Ordered as they appear in the write-up: what agents *do* say, what they never
# say, and the two beliefs (sequencing, clean-merge) that the harness falsifies.
THEMES: dict[str, str] = {
    "T1 file-scoped declaration": r"[\w/]+\.(py|go|rs|js|ts|tsx|typ)\b",
    "T2 explicit ownership proposal": r"\byou (take|own)\b|\bi(?:'ll| will) own\b|you'd own|i claim",
    "T3 both-append-last-param": (
        r"last param|append (your|yours|mine|my param)|after (mine|my param|yours|your param)"
        r"|layer (your|yours|mine|it) on top|go(es)? (first|after)|end of the signature"
    ),
    "T4 sequencing / handoff illusion": (
        r"layer .* on top|i'll go first|ping me when|before you edit|pull latest"
        r"|rebase (your|on)|wait instead|let me know when.*done"
    ),
    "T5 isolation discovered": (
        r"separate (cop|checkout|sandbox|worktree|repo)|isolated (workspace|sandbox|working cop)"
        r"|own (isolated|sandbox)|don'?t see your|can'?t see your|not visible in my"
    ),
    "T6 self-certified clean merge": (
        r"should merge (clean|fine)|merges? cleanly|no conflict|won'?t conflict"
        r"|shouldn'?t conflict|additive|non-overlapping|no clobbering|safe for you"
    ),
    "T7 question asked": r"\?",
    "T8 verbatim code exchanged": r"```|^\+|def \w+\([^)]*\)\s*(->|:)",
    "T9 terminal 'done/submitting'": r"\b(done|finished|complete)\b.*(submit|patch\.txt)|submitting (my|now)|patch\.txt (now|written)",
}

RunKey = tuple[str, str, str, str]


def load_messages() -> dict[RunKey, list[dict]]:
    """-> {(rep, repo, task, pair): [message, ...]} sorted by send time."""
    runs: dict[RunKey, list[dict]] = collections.defaultdict(list)
    for path in sorted(glob.glob(MSG_GLOB, recursive=True)):
        p = path.split("/")
        key = (p[1], p[3], p[4], p[5])
        for line in open(path):
            if line.strip():
                runs[key].append(json.loads(line))
    for ms in runs.values():
        ms.sort(key=lambda m: m["timestamp"])
    return runs


def load_evals() -> dict[RunKey, dict]:
    out = {}
    for path in glob.glob(EVAL_GLOB):
        p = path.split("/")
        out[(p[1], p[3], p[4], p[5])] = json.load(open(path))
    return out


def hunks(patch: str) -> dict[str, list[tuple[int, int]]]:
    """-> {file: [(start_line, length)]} from a unified diff."""
    out: dict[str, list[tuple[int, int]]] = collections.defaultdict(list)
    cur: str | None = None
    for ln in open(patch, errors="replace"):
        if ln.startswith("diff --git"):
            m = re.search(r" b/(\S+)", ln)
            cur = m.group(1) if m else None
        elif ln.startswith("+++ "):
            f = ln[4:].strip()
            if f.startswith("b/"):
                cur = f[2:]
        elif ln.startswith("@@") and cur:
            m = re.match(r"@@ -(\d+)(?:,(\d+))?", ln)
            if m:
                out[cur].append((int(m.group(1)), int(m.group(2) or 1)))
    return out


def overlaps(a: tuple[int, int], b: tuple[int, int], pad: int = 3) -> bool:
    """Do two hunks touch, allowing `pad` lines of diff context either side?"""
    return not (a[0] + a[1] + pad < b[0] or b[0] + b[1] + pad < a[0])


def is_clean(ev: dict) -> bool:
    return ev.get("merge", {}).get("status") in ("clean", "identical")


def main() -> None:
    runs, evals = load_messages(), load_evals()
    joined = sorted(set(runs) & set(evals))
    n_msg = sum(len(v) for v in runs.values())
    print(f"== replication messaging: {n_msg} messages over {len(runs)} pair-runs "
          f"({len(joined)} joined to an eval record) ==\n")

    per_run = sorted(len(v) for v in runs.values())
    spans = sorted(v[-1]["timestamp"] - v[0]["timestamp"] for v in runs.values())
    print(f"  messages/run: median {per_run[len(per_run) // 2]}, max {per_run[-1]}")
    print(f"  first->last message: median {spans[len(spans) // 2]:.0f}s, "
          f"p90 {spans[int(0.9 * len(spans))]:.0f}s\n")

    print("-- theme prevalence (share of pair-runs whose dialogue matches) --")
    coded: dict[str, set[RunKey]] = {}
    for name, pat in THEMES.items():
        hits = {k for k, ms in runs.items()
                if re.search(pat, "\n".join(m["content"] for m in ms), re.I | re.M)}
        coded[name] = hits
        print(f"  {name:<34} {len(hits):3d} / {len(runs)} = {100 * len(hits) / len(runs):3.0f}%")

    print("\n-- does the theme predict the merge outcome? --")
    for name in ("T3 both-append-last-param", "T4 sequencing / handoff illusion",
                 "T6 self-certified clean merge"):
        hits = [k for k in joined if k in coded[name]]
        bad = sum(1 for k in hits if not is_clean(evals[k]))
        print(f"  {name:<34} {len(hits):3d} runs -> {bad:3d} conflicted "
              f"({100 * bad / len(hits):3.0f}%)")

    status = collections.Counter(evals[k].get("merge", {}).get("status") for k in joined)
    passed = sum(1 for k in joined if evals[k].get("both_passed"))
    print(f"\n  arm baseline: merge {dict(status)}; "
          f"both_passed {passed}/{len(joined)} = {100 * passed / len(joined):.0f}%")

    print("\n-- patch forensics on the conflicting runs --")
    shared_file = same_line = same_def = named_in_chat = 0
    conflicting = 0
    for k in joined:
        if is_clean(evals[k]):
            continue
        d = f"logs/{k[0]}/coop/{k[1]}/{k[2]}/{k[3]}"
        patches = sorted(glob.glob(d + "/agent*.patch"))
        if len(patches) != 2:
            continue
        conflicting += 1
        h1, h2 = hunks(patches[0]), hunks(patches[1])
        shared = set(h1) & set(h2)
        if not shared:
            continue
        shared_file += 1
        if any(a[0] == b[0] for f in shared for a in h1[f] for b in h2[f]):
            same_line += 1
        t1, t2 = (open(p, errors="replace").read() for p in patches)
        defs = (set(re.findall(r"^[-+]\s*def (\w+)\(", t1, re.M))
                & set(re.findall(r"^[-+]\s*def (\w+)\(", t2, re.M)))
        if defs:
            same_def += 1
        chat = "\n".join(m["content"] for m in runs[k])
        collided = {f for f in shared for a in h1[f] for b in h2[f] if overlaps(a, b)}
        if any(f in chat or os.path.basename(f) in chat for f in collided):
            named_in_chat += 1

    def pct(x: int) -> str:
        return f"{x:3d} / {conflicting} = {100 * x / conflicting:3.0f}%"

    print(f"  conflicting runs with two patches      {conflicting}")
    print(f"  ...patches share >=1 file              {pct(shared_file)}")
    print(f"  ...collide at the EXACT same line      {pct(same_line)}")
    print(f"  ...both rewrite the same `def`         {pct(same_def)}")
    print(f"  ...colliding file was NAMED in chat    {pct(named_in_chat)}")


if __name__ == "__main__":
    main()
