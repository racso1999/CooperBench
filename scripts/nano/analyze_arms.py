#!/usr/bin/env python3
"""Recompute both_passed% and merge-status breakdown for the overlap-protocol study.

Reads every logs/<arm>_<rep>/**/eval.json and prints per-arm totals + per-rep detail.
Rerunnable at any time (during or after the run) with no dependencies:

    python3 scripts/nano/analyze_arms.py

Arms: nano_dc / nano_dc_b2  = designated_coder ; nano_coauthor / nano_coauthor_b2 = coauthor_overlap.
"""
import json, glob, collections, sys

ARMS = {
    "designated_coder": ["nano_dc", "nano_dc_b2"],
    "coauthor_overlap": ["nano_coauthor", "nano_coauthor_b2"],
}


def collect(prefixes):
    tot = bp = 0
    merge = collections.Counter()
    byrep = {}
    for pref in prefixes:
        for d in sorted(glob.glob(f"logs/{pref}_*")):
            rt = rbp = 0
            for f in glob.glob(f"{d}/**/eval.json", recursive=True):
                e = json.load(open(f))
                tot += 1
                rt += 1
                merge[e.get("merge", {}).get("status", "?")] += 1
                if e.get("both_passed"):
                    bp += 1
                    rbp += 1
            if rt:
                byrep[d.split("logs/")[-1]] = f"{100*rbp//rt}% ({rbp}/{rt})"
    return tot, bp, merge, byrep


def main():
    print("== overlap-protocol study — both_passed% and merge outcomes ==\n")
    print("baselines (no-git): no-msg 10% | free-text 10% | plan_handshake 18%\n")
    for name, prefixes in ARMS.items():
        tot, bp, merge, byrep = collect(prefixes)
        if not tot:
            print(f"{name}: (no evals yet)\n")
            continue
        clean = merge.get("clean", 0) + merge.get("identical", 0)
        print(f"{name}: both_passed {bp}/{tot} = {100*bp/tot:.0f}%")
        print(f"   merge: {dict(merge)}  -> clean+identical {clean}/{tot} = {100*clean/tot:.0f}% (rest = lead-alone rescue)")
        for k, v in byrep.items():
            print(f"     {k}: {v}")
        print()


if __name__ == "__main__":
    sys.exit(main())
