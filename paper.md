# Abstract

Multi-agent LLM systems promise the parallelism and division of labour of human teams, but whether coding agents can actually coordinate on shared codebases is largely untested. We first replicate CooperBench's "curse of coordination" on our own infrastructure with a stronger, paired design: on 46 matched feature pairs with an identical model (Claude Sonnet 5), a solo agent's pass rate of 44.2% falls to 12.3% when two agents must coordinate via free-text messaging (Wilcoxon p < .001). Per-feature evaluation localises the gap: paired agents pass their own feature's held-out suite exactly as often as solo agents (21/47 vs 20/47), and every jointly-failed pair that was individually solvable was lost to a textual merge conflict — the coordination gap is an integration gap, not a capability or communication deficit. Normalising for computational effort widens the gap further, from 3.6-fold in pass rate to 6.3-fold in passes per dollar. We then extend the benchmark into a controlled scaling study: a solo-achievable workload of K mutually conflicting features is held fixed while only the team size N ∈ {1, 2, 3, 4} varies, with integration performed by the agents themselves. Adding agents buys no correctness — the strict all-pass rate falls monotonically from 89% to 69% — while cost rises near-linearly, so efficiency collapses as a power law, ≈ 1.28·N^−1.61 (R² = 0.996), reaching ~10% of the solo value at four agents. The collapse is universal across all fourteen task pools, including those that integrate perfectly at every N. Coordination overhead in agentic software development is thus super-proportional in team size: a structural tax paid before any message is sent, in redundant context loading and repeated integration.

# Introduction

A large language model (LLM) is, at its core, a stateless predictor. Built on the transformer architecture, when given a sequence of text, it outputs the most likely continuation, token by token, and retains no memory of one call to the next [1]. An AI agent is what emerges when this stateless predictor is wrapped in a loop: the model is given tools (a shell, a file editor, a messaging channel), its outputs are executed against a real environment, and the results are fed back into its context. This construction turns a next-token predictor into a system that can pursue multi-step goals: reading a codebase, editing files, running tests.

Once one agent works, the appeal of several is obvious, and multi-agent systems have risen in popularity accordingly. The intuition borrows directly from human organisations: divide the work, and let them collaborate. In theory, several agents should deliver the parallelism and division of labour that a single context-limited agent cannot. Frameworks built on this premise have proliferated, from conversational multi-agent toolkits such as AutoGen [2] to software-company simulations such as MetaGPT [3] and ChatDev [4], which cast agents as product managers, engineers, and testers cooperating through structured conversations. The premise is seductive because each agent brings its own context window and its own working environment, so a team appears to scale where a single agent saturates.

What this intuition quietly assumes, however, is that LLM agents **can** coordinate and that dividing the work produces a meaningful outcome. For software engineering specifically, that assumption is largely untested, and the little evidence that does exist points the other way. In "CooperBench: Why Coding Agents Cannot be Your Teammates Yet" [5], the authors found that solo agents were far better at solving coding-based tasks than their two- or multi-agent counterparts.

Intuitively, this makes sense. To crudely understand the issue, imagine a single machine is told to complete a task: it is given a fixed compute budget and unlimited time. Now split the compute budget across two machines and give the machines a method of communication. One can ascertain that even if communication is 100% effective (so that the effect of communication may be dismissed), we still expect worse performance, because communication costs compute, and therefore the total compute budget available to solve the task is significantly reduced. In this paper we will refer to this as the "communication efficiency problem".

Why then, one might ask, would we even consider improving a system that is doomed to fail? The answer is that, despite multi-agent systems at times not being as efficient as their solo counterparts, they may also at times be necessary or even more useful than their solo counterparts. For example, multi-agent systems may be useful when there are two agents with contrasting functionality. Or take, for example, a scenario where agents autonomously look after certain parts of a system. Perhaps there are a few lines where their working boundaries overlap, or their functions are called within another agent's working environment. At times, agents will be forced to work together, and when they do, we want to ensure that they can do so to their maximum capability and, efficiently.

# Hypothesis

This paper aims to isolate the failures of multi-agent systems and through our findings, suggest protocol, architecture or schema changes that can be applied to preexisitng multi agents systems. In this paper, we hypothesise that multi agent systems will always be worse than their solo agent counter part in tasks that are solvable by a single agent. To further prove this hypothesis, this paper aims to show the increasing communcation cost by scaling multi agent systems from solo -> 4 agents using CooperBench as our primary benchmarking suite.

## Methodology

"CooperBench: Why Coding Agents Cannot be Your Teammates Yet" [5] introduces a comprehensive benchmarking suite that isolates communcation failures in multi agent systems. CooperBench is a benchmark that tests whether two LLM coding agents can work in parallel on the same codebase. Its headline finding is the "curse of coordination" - agents average ~30% lower success working together than one agent doing both tasks alone. CooperBench works by spinning up two isolated containerised environments from which agents work within. Each agent is given a spec, access to its own copy of the code base and a tool to message with the other agent. (This can be from 1 other, up to a whole team of agents). The two agents are then tasked with individually implementing their own features.

CooperBench provides a built-in evaluation pipeline, applied automatically as each task pair completes. Evaluation takes place in a fresh container, isolated from the agents' working environments. Any modifications to test files are first stripped from the submitted patches, preventing agents from passing by altering the grading tests. Each patch is then applied to its own branch off of the base commit, and the two branches are naively merged (git merge, with no conflict-resolution fallback). If the merge is clean, each feature's test suite is run against the merged tree. A pair succeeds (both_passed) only if both suites pass; a conflicted merge fails outright. Notably, the tests execute only at evaluation time: agents may run the repository's pre-existing tests while working, but never see the grading suites.

Preliminary (pilot) tests were run against the flash dataset to determine a suitable model for our experiments. Problems to consider were cost, individual model capability, and token throughput. claude-sonnet-5 was ultimately selected.

# Replicating the Original Study

To establish that the coordination gap reported by CooperBench reproduces on our infrastructure, the 50-pair flash subset was run under two conditions with an identical model (Claude Sonnet 5): a solo condition, in which a single agent implements both features of a pair, and a cooperative condition, in which two isolated agents implement one feature each and may exchange free-text messages. Because both conditions run on the same feature pairs, the comparison is paired at the pair level, removing task difficulty as a confound. Three pairs could not be evaluated in either condition and are excluded, leaving n = 47.

It is important to state here that "free-msg" is not necessarily a blank canvas. In the free-messaging condition, each agent's instruction is composed of three parts, separated in a single prompt: (1) the feature specification (the agent's own feature.md, never the partner's); (2) a submission protocol instructing the agent to write its final unified diff to patch.txt before exiting; and (3) a cooperation protocol block that names the partner, warns that features may overlap, and documents the messaging commands. "Free" refers to the message content: it is unconstrained plain text, with no required fields, no message types, and no validation. The cooperation block is reproduced verbatim below (as rendered for agent1):

```
## Cooperation protocol

You are **agent1**, working alongside: **agent2**.

Each agent has been assigned a separate feature from the same codebase;
your features may overlap (touch the same files), so coordinate to avoid
clobbering each other's changes.

Available shell commands for cross-agent messaging (Redis-backed inbox,
one inbox per agent):

coop-send <recipient> "message text here"   # send to a specific peer
coop-broadcast "message text here"          # send to every other peer
coop-recv                                   # drain your inbox (prints JSON list)
coop-peek                                   # number of unread messages
coop-agents                                 # list every agent id

Recommended workflow:

1. At the start, `coop-broadcast` a short summary of your feature and
   which files you intend to touch.
2. Periodically `coop-recv` to read what your peers have sent — at
   minimum after major edits and before submitting.
3. If two agents need to modify the same file, coordinate explicitly
   (split the file, agree on one owner, or merge changes).
4. Keep messages short and focused: file names, function names, and
   one-sentence intents are usually enough.

Messages are not magic — your peers only know what you tell them.
```

## The Findings

Consistent with the reported curse of coordination, we observe a substantial drop in task success when agents must coordinate via messaging compared to working solo. Across 46 matched feature pairs (task_id/pair, with typst_task/6554 excluded due to intermittent evaluation-container failures leaving too few scored runs per pair for a reliable estimate), the average pass rate fell from 44.2% under the Solo condition to 12.3% under the Messaging condition. A paired Wilcoxon signed-rank test confirms this difference is statistically significant (W = 2.5, p < .001). This finding replicates the qualitative pattern reported in the original study, in which coordinated (Coop) performance is substantially lower than Solo performance across models.

In the cooperative condition, both agents independently passed their own feature's held-out suite in 21/47 pairs — statistically indistinguishable from the solo condition's 20/47 (discordant pairs: 2 vs 3). Splitting the work across two agents therefore causes no measurable loss of individual capability. The gap arises at patch integration. Of the 20 pairs demonstrably solvable by a single agent, the cooperative system delivered only 5 (25%). All pairs that were independently solved but jointly failed were lost to textual merge conflicts rather than functional incompatibility. The coordination gap is thus, on this data, an integration gap. The agents consistently write working code but cannot place their edits so that the contributions combine.

While the original study establishes a clear coordination gap in task success rates, it does not normalize for the cost of achieving those outcomes. We use total dollar cost — which aggregates input, output, and cache read/write tokens into a single figure — as a proxy for computational effort, and find that the coordination gap is considerably larger once this is accounted for. Cost is taken directly from the `total_cost_usd` field of the Claude Code CLI's terminating result event, computed from token usage (input, output, and cache read/write) priced at Anthropic's published list rates. The reported cost of a run is the sum across its participating agents and reflects API list price. Across the same 46 matched feature pairs, the Solo condition achieved 0.675 passes per dollar spent, compared to 0.107 passes per dollar under Messaging — a roughly 6.3-fold gap, versus the 3.6-fold gap observed in raw pass rate alone. A paired Wilcoxon signed-rank test on per-pair cost efficiency confirms this difference is statistically significant (*W* = 2.0, *p* < .001). This widening indicates that the coordination penalty is not limited to lower success rates: Messaging runs are also less cost-efficient per successful outcome, compounding the disadvantage relative to Solo.

# Growth With Scale

Fu et al. (2026) [6] show that most multi-agent workflows fail to outperform a matched single-agent baseline once evaluation infrastructure is controlled, concluding that agent count does not explain performance and that workflow gains instead depend on task-protocol fit. Their comparison, however, never varies agent count independently of structure, so we build on their protocol by holding workflow structure fixed and varying only N, to directly test the count-performance relationship they were unable to isolate. This alongside our communication efficiency hypothesis aims to isolate a clear relationship between scaling the number of agents in a system and the performance losses due to the communication efficiency problem.

We extend CooperBench from a diagnostic of pairwise mergeability into a controlled study of how coordination cost scales with team size. Whereas the base benchmark measures whether two agents can independently implement a conflicting pair of features and have their patches merge cleanly, our extension fixes the workload — a pool of K mutually interdependent features, drawn as a clique from the task's gold-conflict graph and screened so that a single agent can complete all K — and varies only the number of agents N ∈ {1, 2, 3, 4} across which that workload is deterministically partitioned, under both a communicating and a communication-ablated condition. Each configuration is evaluated with an N-way sequential merge and instrumented by decomposing every agent's execution trace into four token accounts: context (ingesting the shared repository and specification), task (implementing its assigned features), communication (messages sent, received, and re-ingested on each subsequent step), and rework (revising already-edited files in response to an inbound message). These accounts are then converted to a common monetary unit and regressed against N. The design targets a single question: whether the cost of parallel agentic software development is superlinear in the number of agents. Concretely, it isolates the empirical communication tax — the cost gap between the communicating and ablated conditions, and the curvature of the communication account itself — from the unavoidable linear floor imposed by each agent independently loading shared context, quantifies which mechanism (message re-ingestion, merge conflicts, or rework) drives any superlinearity, and characterizes how the dominant failure mode shifts as the team grows.

# The Scaling Study: The Cost of Adding Agents

Every result so far fixes the team size at two. The replication localises the two-agent gap to patch integration, but it leaves a more basic question untouched: as a fixed workload is divided among *more* agents, does the cost of coordinating grow, and how? Answering this requires two changes to the apparatus. The workload must be held constant while only the agent count varies. And, more importantly, the naive two-branch merge used as the coordination oracle throughout the benchmark is unfair to the very thing we are measuring: it conflicts whenever two agents touch the same lines, whether or not they coordinated, conflating genuine coordination failure with incidental overlap that any competent integrator resolves trivially.

## A Fairer Apparatus: Agent-Owned Integration

We therefore built a shared-repository mode. All N agents work against one git remote seeded at the task's base commit; each agent implements its assigned features, then fetches its peers, merges their branches into its own tree, resolves any conflicts, and rebuilds its patch from the *integrated* result. Integration is thus performed by the agents, as part of their coordination work — not imposed by the evaluator. Evaluation no longer merges anything: it scores the single integrated tree the agents produced against every feature's held-out suite. We verified the mechanism directly at N = 2, 3, and 4: in each case every agent fetched and merged all of its peers and the agents converged on the same integrated tree, and a four-agent integration on a conflict-clique task passed all four held-out suites — confirming that the agents genuinely integrate rather than shipping isolated patches.

## Design

The independent variable is the agent count N ∈ {1, 2, 3, 4}; the constant is a pool of K mutually-conflicting features (a clique in the gold conflict graph) split across the N agents by a fixed round-robin partition. N = 1 is one agent implementing all K; higher N deals the same K features across more agents. Every pool is solo-screened — a single agent must complete all K — so that any degradation at higher N is attributable to coordination, not to raw difficulty; this also anchors the curve at a clean solo ceiling. The primary measure is a graded score, the fraction of the K held-out suites passing on the integrated tree, which credits a partially-correct team (three of four features working = 0.75) and treats a merge that breaks the codebase, so tests fail to even run, as 0.

Solo-achievability is the binding constraint. Only ~20% of K = 4 candidate tasks pass screening, so K = 4 pools — the only ones that reach N = 4 — are scarce; the harder repositories become solo-achievable only at K = 3, capping them at N = 3. The final dataset is 14 clique-pools across six repositories, 148 runs under Claude Sonnet 5 (~$410 API-equivalent), six of which reach N = 4.

## Results: Efficiency Collapses as a Power Law

The cleanest and most general result is in efficiency — the fraction of the workload solved per dollar spent.

| N | graded score | cost / run | solved per \$ | vs. solo |
|---|---|---|---|---|
| 1 | 0.96 | $0.78 | 1.24 | 100% |
| 2 | 0.91 | $2.10 | 0.43 | 35% |
| 3 | 0.89 | $3.82 | 0.23 | 19% |
| 4 | 0.92 | $7.21 | 0.13 | 10% |

Efficiency falls as a power law in the agent count, efficiency = 1.28·N^−1.61 (R² = 0.996), reaching ~10% of the solo value at four agents. The relationship is *universal*: fitting each pool separately, all fourteen collapse as power laws with exponents between roughly 1.1 and 2.3 (mean ≈ 1.7, every R² > 0.9). The exponent exceeding 1 everywhere is the substantive point. If dividing the work simply gave each agent a fixed share at a fixed per-agent cost, efficiency would fall as 1/N (b = 1); the observed b ≈ 1.8 means each added agent is *super-proportionally* wasteful — the coordination overhead (re-loading shared context, messaging, re-integration, and repair of botched merges) grows faster than the work is divided. This holds even for pools whose correctness never degrades: pallets_jinja/1621 integrates perfectly at every N, yet its efficiency still falls 1.07 → 0.15, a 7× loss. The efficiency penalty does not require a coordination *failure* — it is the price of coordination itself.

## Correctness and Cost

Correctness degrades more mildly, and less universally. Averaged over all fourteen pools, the graded score falls 0.96 → 0.91 → 0.89 from one to three agents, and the strict all-pass rate — the probability the team ships a fully-correct integration — falls monotonically 89% → 82% → 77% → 69% across all four agent counts. (In an earlier run with only four K = 4 pools the four-agent point spuriously recovered, a composition artifact of the easy pools; adding two more K = 4 pools, one of them a degrader, removes it and restores the monotonic decline.) The degradation is concentrated on the hardest repository, dspy: all four of its cliques degrade (e.g. 0.75 → 0.42, and 0.92 → 0.75), while eight of the fourteen pools integrate cleanly and hold near 1.0. When correctness is lost, the failure mode is specific: the agents merge but botch the integration, producing code that no longer runs, so the held-out suite returns zero passed and zero failed.

Cost, by contrast, rises on every pool and is close to linear in N — each added agent adds a roughly constant $1.7–$2.3 per run (its own context load plus its slice of the work), for a ~10× increase from one to four agents on the same workload. It is this near-linear cost against flat-or-declining correctness that produces the super-linear efficiency collapse.

## What This Shows

Where the replication localised the two-agent gap to patch integration, the scaling study reveals a penalty that no integration fix can remove: the cost of coordination itself. Splitting a task a single agent can already solve across more agents buys no correctness — at best it matches solo, and on hard, conflict-dense tasks it actively destroys it — while the work delivered per dollar falls as roughly N^−1.8, a penalty that appears on every task we measured, including those that remain perfectly correct. For agentic development on interdependent work, adding agents is not merely unhelpful; it is super-proportionally expensive for the same result. This is a limit on parallelism that no messaging protocol can remove, because it is paid before any message is sent — in the redundant context each agent must load and the integration each must redo.

# Conclusion

This work set out to test whether the coordination gap between LLM coding agents is an artifact of any particular benchmark setup, or a systematic cost of dividing work that a single agent can already do. The evidence forms a chain of three results.

First, we replicated the CooperBench finding on our own infrastructure with a stronger design than the original: a paired solo baseline on identical feature pairs with an identical model. The gap reproduced almost exactly — across 46 matched pairs, the solo pass rate of 44.2% fell to 12.3% under free-text messaging (Wilcoxon W = 2.5, p < .001), mirroring the original paper's reported ~30% coordination penalty. Per-feature evaluation then localised it: pairing costs agents nothing in individual capability — agents working alongside a partner passed their own feature's held-out suite in 21/47 pairs, statistically indistinguishable from the solo condition's 20/47 — so the entire gap arises at patch integration. Of the 20 pairs demonstrably solvable by a single agent, the cooperating pair delivered only 5, and every one of those losses was a textual merge conflict rather than a functional incompatibility. The coordination gap is, on this data, an integration gap: the agents consistently write working code but cannot place their edits so that the contributions combine.

Second, we showed that the gap is larger than raw pass rates suggest once computational effort is accounted for. Normalising by total dollar cost, the solo condition achieved 0.675 passes per dollar against 0.107 under messaging — a 6.3-fold efficiency gap, versus the 3.6-fold gap in pass rate alone (Wilcoxon p < .001). Coordination does not merely lower the success rate; it makes each success considerably more expensive.

Third, the scaling study quantified how this penalty grows with team size. Holding a solo-achievable workload of K mutually conflicting features fixed and varying only the agent count N ∈ {1, 2, 3, 4} — with integration performed by the agents themselves rather than imposed by the evaluator, removing the unfairness of the naive merge oracle — adding agents bought no correctness: the graded score at best matched the solo ceiling, the strict all-pass rate fell monotonically from 89% to 69%, and on the hardest, conflict-dense repository correctness actively degraded. Cost, meanwhile, rose near-linearly at roughly $1.7–$2.3 per added agent. The combination produces a universal power-law collapse in efficiency — solved-per-dollar ≈ 1.28·N^−1.61 (R² = 0.996), with all fourteen pools individually collapsing at exponents between 1.1 and 2.3 — reaching about 10% of the solo value at four agents. Because the exponent everywhere exceeds 1, each added agent is super-proportionally wasteful; and because the penalty appears even on pools that integrate perfectly at every N, it cannot be attributed to coordination *failure*. It is the price of coordination itself, paid before any message is sent, in the redundant context each agent must load and the integration each must redo.

Together these results support the hypothesis with which we began, and sharpen it: for tasks solvable by a single agent, splitting the work across a team is at best correctness-neutral and always efficiency-negative, and the efficiency penalty compounds super-linearly with team size — a direct empirical expression of the communication efficiency problem. The decomposition also identifies where any remedy must act. The bottleneck is not the communication channel — individual capability survives pairing intact, and every observed loss at N = 2 was a spatial merge conflict — but integration: agreeing not just on who touches what, but on how contributions combine into one tree. Prompt-level protocols that resolve overlap directly, and beyond them mechanisms for semantic coordination on what the merged code should do, are the natural next step; the extended apparatus introduced here — fixed solo-screened workloads, agent-owned integration, and per-account cost decomposition — provides the instrument for testing them. What no protocol will remove, however, is the structural floor the scaling study exposes: for interdependent work, coordination has a cost that is paid whether or not it succeeds, and it grows faster than the team.

# References

[1] Vaswani, A., Shazeer, N., Parmar, N., Uszkoreit, J., Jones, L., Gomez, A. N., Kaiser, Ł., & Polosukhin, I. (2017). Attention Is All You Need. Advances in Neural Information Processing Systems 30 (NeurIPS 2017). arXiv:1706.03762.

[2] Wu, Q., Bansal, G., Zhang, J., Wu, Y., Li, B., Zhu, E., Jiang, L., Zhang, X., Zhang, S., Liu, J., Awadallah, A. H., White, R. W., Burger, D., & Wang, C. (2023). AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation. arXiv:2308.08155.

[3] Hong, S., Zheng, X., Chen, J., Cheng, Y., Wang, J., Zhang, C., Wang, Z., Yau, S. K. S., Lin, Z., Zhou, L., Ran, C., Xiao, L., Wu, C., & Schmidhuber, J. (2023). MetaGPT: Meta Programming for a Multi-Agent Collaborative Framework. arXiv:2308.00352.

[4] Qian, C., Liu, W., Liu, H., Chen, N., Dang, Y., Li, J., Yang, C., Chen, W., Su, Y., Cong, X., Xu, J., Li, D., Liu, Z., & Sun, M. (2024). ChatDev: Communicative Agents for Software Development. Proceedings of the 62nd Annual Meeting of the Association for Computational Linguistics (ACL 2024). arXiv:2307.07924.

[5] Khatua, A., Zhu, H., Tran, P., Prabhudesai, A., Sadrieh, F., Lieberwirth, J. K., Yu, X., Fu, Y., Ryan, M. J., Pei, J., & Yang, D. (2026). CooperBench: Why Coding Agents Cannot be Your Teammates Yet. Stanford University & SAP Labs US. https://cooperbench.com

[6] Fu, Y., Fang, R., Shao, J., Zheng, H., Zhu, Z., Luo, B., & Lin, T. (2026). Do more agents help? Controlled and protocol-aligned evaluation of LLM agent workflows. arXiv preprint arXiv:2606.05670.