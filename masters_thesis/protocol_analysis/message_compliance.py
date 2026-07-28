"""designated_coder message compliance, straight from the run transcripts.

The designated_coder protocol tells the two agents to (a) SURVEY their files,
(b) CLAIM/DEFER each shared file to a single owner, and (c) hand the deferring
agent's needs over as a spec. The schema allows the spec to travel either as a
separate `type=SPEC` message or inside the `spec` field of the DEFER message.

This script reads the sent-message logs (`agent*_sent.jsonl`) for every
validated designated_coder run and reports, per run, which message types were
sent and how the spec was delivered. It exists so the compliance numbers quoted
in protocol_paper.md are reproducible rather than asserted; endpoint/taxonomy
numbers come from analyze.py, which does not parse message content.

Denominator note: this counts runs that produced a message log (90). The eval
denominator in analyze.py is 88 — two runs logged messages but produced no
eval record, so they are absent from the endpoint tables but present here.
"""

import glob
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# The 18 pairs that survived pre-registered screening, from the frozen study.
KEPT = set(json.loads((HERE / "data" / "nano_study.json").read_text())["kept"])


def pair_key(repo_task: str, num: str, fpair: str) -> str:
    """Turn a log path ('samuelcolvin_dirty_equals_task', '43', 'f5_f7') into the
    'repo/num/5,7' key used in nano_study.json's kept list."""
    repo = repo_task[:-5] if repo_task.endswith("_task") else repo_task
    feats = fpair.replace("f", "").replace("_", ",")
    return f"{repo}/{num}/{feats}"


def main() -> None:
    runs = 0
    have = {"SURVEY": 0, "CLAIM": 0, "DEFER": 0}
    defer_runs = 0
    defer_spec_field = 0  # DEFER message carried a non-empty spec field
    separate_spec_msg = 0  # a distinct type=SPEC message was sent
    spec_any = 0  # spec delivered by either route

    for run_dir in sorted(glob.glob(str(ROOT / "logs/nano_dc_*/coop/*/*/*/"))):
        p = Path(run_dir)
        if pair_key(p.parts[-3], p.parts[-2], p.parts[-1]) not in KEPT:
            continue
        sent = list(p.glob("agent*_sent.jsonl"))
        if not sent:
            continue
        runs += 1

        types: set[str] = set()
        has_defer = has_defer_spec = has_sep_spec = False
        for f in sent:
            for line in f.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    fields = json.loads(line).get("fields") or {}
                except json.JSONDecodeError:
                    continue
                t = (fields.get("type") or "").upper()
                types.add(t)
                spec = (fields.get("spec") or "").strip()
                if t == "DEFER":
                    has_defer = True
                    if spec:
                        has_defer_spec = True
                if t == "SPEC":
                    has_sep_spec = True

        for k in have:
            if k in types:
                have[k] += 1
        if has_defer:
            defer_runs += 1
        if has_defer_spec:
            defer_spec_field += 1
        if has_sep_spec:
            separate_spec_msg += 1
        if has_defer_spec or has_sep_spec:
            spec_any += 1

    def pct(a: int, b: int) -> str:
        return f"{a}/{b} = {a / b:.0%}" if b else "n/a"

    print(f"validated designated_coder runs with a message log: {runs}")
    print(f"  sent >=1 SURVEY: {pct(have['SURVEY'], runs)}")
    print(f"  sent >=1 CLAIM : {pct(have['CLAIM'], runs)}")
    print(f"  sent >=1 DEFER : {pct(have['DEFER'], runs)}")
    print(f"runs that deferred >=1 file: {defer_runs}")
    print(f"  spec in DEFER.spec field   : {pct(defer_spec_field, defer_runs)}")
    print(f"  spec as separate SPEC msg  : {pct(separate_spec_msg, defer_runs)}")
    print(f"  spec delivered either way  : {pct(spec_any, defer_runs)}")


if __name__ == "__main__":
    main()
