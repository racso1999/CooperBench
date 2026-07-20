"""Overnight autonomous pipeline: screen a prioritised candidate set, then
git-benchmark every qualified pool. Resumable (cached cells skip). Run in tmux.
Priority: K=4 pools first (scarce N=4 data), then K=3."""
from itertools import combinations
from cooperbench.scaling import pools, experiment
from cooperbench.scaling.pools import Pool

graph = pools.load_conflict_graph()
def is_clique(adj, sub): return all(b in adj.get(a, ()) for a, b in combinations(sub, 2))
def cliques(adj, k): return [tuple(s) for s in combinations(sorted(adj), k) if is_clique(adj, s)]

DONE = {
  ("openai_tiktoken_task",0,(1,2,3,4)),("dspy_task",8394,(1,2,4,5)),
  ("pallets_jinja_task",1465,(1,2,3,4)),("pallets_jinja_task",1621,(1,5,6,9)),
  ("dottxt_ai_outlines_task",1371,(1,2,3)),("dottxt_ai_outlines_task",1655,(2,4,5)),
  ("dspy_task",8635,(1,3,4)),("llama_index_task",17070,(1,2,3)),
  ("llama_index_task",17244,(1,2,3)),("pillow_task",25,(2,3,4)),
}
SKIP = {"typst_task"}

def firsts(k):
    out=[]
    for (repo,tid),adj in sorted(graph.items()):
        if repo in SKIP: continue
        cs=cliques(adj,k)
        if cs and (repo,tid,cs[0]) not in DONE:
            out.append(Pool(repo,tid,cs[0]))
    return out

# K=4: every task's first clique (scarce resource → screen them all) + dspy alt cliques.
cand4 = firsts(4)
for repo,tid in [("dspy_task",8394),("dspy_task",8635),("dspy_task",8587)]:
    for f in cliques(graph[(repo,tid)],4)[1:2]:
        if (repo,tid,f) not in DONE: cand4.append(Pool(repo,tid,f))
# K=3: cap to 14 first cliques (secondary priority).
cand3 = firsts(3)[:14]
print(f"[driver] K=4 candidates: {len(cand4)} | K=3 candidates: {len(cand3)}", flush=True)

common=dict(agent_name="claude_code", model_name="claude-sonnet-5", backend="docker", timeout=900)

print("[driver] === SCREEN K=4 ===", flush=True)
q4 = experiment.screen_pools(cand4, r_screen=1, threshold=1, **common)
print(f"[driver] qualified K=4 ({len(q4)}): {[p.pool_id for p in q4]}", flush=True)
if q4:
    print("[driver] === SWEEP K=4 (N=1..4, trials=2, git) ===", flush=True)
    experiment.run_experiment(q4, agents=[1,2,3,4], conditions=("comm",), trials=2,
        git_enabled=True, out_dir="results_overnight_k4", **common)

print("[driver] === SCREEN K=3 ===", flush=True)
q3 = experiment.screen_pools(cand3, r_screen=1, threshold=1, **common)
print(f"[driver] qualified K=3 ({len(q3)}): {[p.pool_id for p in q3]}", flush=True)
if q3:
    print("[driver] === SWEEP K=3 (N=1..3, trials=2, git) ===", flush=True)
    experiment.run_experiment(q3, agents=[1,2,3], conditions=("comm",), trials=2,
        git_enabled=True, out_dir="results_overnight_k3", **common)
print("[driver] === ALL DONE ===", flush=True)
