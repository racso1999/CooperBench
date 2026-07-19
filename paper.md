# Introduction

AI agents are becoming an increasingly central part of how large language models (LLMs) are used. The architecture underlying these models, the transformer, was introduced by Vaswani et al. in 2017 [1]. A transformer is stateless: given a sequence of tokens, it predicts the next, and it retains no memory between calls — everything the model "knows" about an ongoing interaction must be re-supplied in its context window. An AI agent is what emerges when this stateless predictor is wrapped in a loop: the model is given tools (a shell, a file editor, a messaging channel), its outputs are executed against a real environment, and the results are fed back into its context. State, in other words, lives in the environment rather than in the model. This construction turns a next-token predictor into a system that can pursue multi-step goals — reading a codebase, editing files, running tests — and it is the construction studied throughout this work.

Once one agent works, the appeal of several is immediate, and multi-agent systems have risen in popularity accordingly. The intuition borrows directly from human organisations: divide the work, assign specialists, and let them collaborate — several agents should deliver the parallelism and division of labour that a single context-limited agent cannot. Frameworks built on this premise have proliferated, from conversational multi-agent toolkits such as AutoGen [2] to software-company simulations such as MetaGPT [3] and ChatDev [4], which cast agents as product managers, engineers, and testers cooperating through structured conversations. The premise is seductive because each agent brings its own context window and its own working environment, so a team appears to scale where a single agent saturates. What this intuition quietly assumes, however, is that LLM agents can coordinate — that dividing the work costs less than it returns. For software engineering specifically, that assumption is largely untested, and the evidence that does exist points the other way: it is precisely the gap this work investigates.

# Methodology

## The Problem

The key problem I seek to solve is the communication gap between agents. The original CooperBench paper [5] found that solo agents were far better at solving coding-based tasks than their two- or multi-agent counterparts.

The main issue appears to be a communication gap. Systems with two or more agents must communicate successfully in order to produce code that both works and is compatible with the other agent's code.

My hypothesis is that multi-agent systems fail in tangible failure modes. If we can isolate these modes through benchmarking, we can iteratively produce a protocol that seeks to fix these failures.

## How CooperBench Works

CooperBench works by spinning up two isolated containerised environments from which agents work within. Each agent is given a spec, access to its own copy of the code base and a tool to message with the other agent. (This can be from 1 other up to a whole team of agents). The two agents are then tasked with individually implementing their own features. After which an eval script is run to score each run.

CooperBench provides a built-in evaluation pipeline, applied automatically as each task pair completes. Evaluation takes place in a fresh container, isolated from the agents' working environments. Any modifications to test files are first stripped from the submitted patches, preventing agents from passing by altering the grading tests. Each patch is then applied to its own branch off the base commit, and the two branches are naively merged (git merge, with no conflict-resolution fallback). If the merge is clean, each feature's held-out test suite — extracted from the original pull request and never shown to the agents — is run against the merged tree. A pair succeeds (both_passed) only if both suites pass; a conflicted merge fails outright. Notably, the held-out tests execute only at evaluation time: agents may run the repository's pre-existing tests while working, but never see the grading suites.

## Extending the Pipeline

I extended this pipeline in place, so that it produces a strict superset of its original output. First, I added a pre-merge independent evaluation stage: before merging, each agent's patch is tested in isolation against its own feature's held-out suite. This distinguishes capability failures (an agent never solved its feature) from coordination failures (a working implementation broken by the merge) — a decomposition the post-merge signal alone cannot make, and the central quantity of interest in this study.

## The Datasets

CooperBench ships several subsets ranging from a 10-pair smoke set (core) to a 100-pair curated evaluation set (lite), alongside the full 652-pair enumeration. The flash dataset contains 50 feature pairs drawn from 20 tasks across 11 open-source repositories, sampled uniformly at the pair level from the benchmark's lite subset (seed = 42), and is intended as a development set for rapid iteration. Nano is our 20-pair capability-screened subset introduced for the protocol study.

## Choosing a Model

Preliminary (pilot) tests were run against the flash dataset to determine a suitable model for our experiments. Key problems to consider were cost, individual model capability, and token throughput. Local models were tested but ultimately not used due to their limited token throughput: with single locally hosted models we were restricted to sequential model calls, and this lack of concurrency added a large time overhead. Secondly, a variety of cloud API models were tested; several were capable, but the cost overhead was too high. Finally, I settled on the Claude Code wrapper, through which agents authenticate against a Claude Max (20×) subscription. This allowed access to multiple models at a fixed subscription cost, offering excellent value per token relative to per-call API billing. I decided to use Claude Sonnet 5 for the model.

## Design Rationale: Fully Isolated Agents

Here the experiment can take one of two directions. We give the agents a shared git workspace. This way, it more closely represents a realistic development setting, whereby developers work together on a shared codebase. Alternatively, we limit their scope so that all they have is their messaging. This way, any improvements in performance can be attributed to communication alone.

From a design perspective, it makes more sense to keep agents in the dark from one another and to NOT allow them to share git workspaces. This in turn isolates an increase in performance metrics to communication alone and arguably gives us a more meaningful signal to determine what improves communication between two agents. To further explain, in a "real-life" setting, perhaps it would make more sense to allow agents to have access to each other's workspace. However, for the sake of isolating failure modes specific to communication issues and for the sake of this experiment, we decided to keep both agents completely isolated.

## The Plan

1. Replicate initial study using flash data set and Sonnet 5.
2. Evaluate whether our replication displays similar behavior.
3. Isolate common failure modes.
4. Build protocols through structured messaging and system prompt modification to help reduce these failure modes.

# Replicating the Original Study

In order to begin, I wanted to replicate the original study. It is first important to test whether we see the same issues with our own system. I expect to see that increasing difficulty of the tasks results in more failures. The original study also points to the largest communication gap arising with medium-level tasks.

The original study also tested the effect of allowing agents to freely communicate with each other, although found that communication alone has no benefit to overall success rates. In order to build on this, we must first replicate the study and extract as much data as possible.

The first task was to begin naively searching for failure modes. In order to do so, we started by running the flash dataset. To establish that the coordination gap reported by CooperBench reproduces on our infrastructure, we ran the 50-pair flash subset under two conditions with an identical model (Claude Sonnet 5): a solo condition, in which a single agent implements both features of a pair, and a cooperative condition, in which two isolated agents implement one feature each and may exchange free-text messages. Because both conditions run on the same feature pairs, the comparison is paired at the pair level, removing task difficulty as a confound. Three pairs could not be evaluated in either condition and are excluded, leaving n = 47.

## Results

The solo agent solved 20/47 pairs (42.6%), while the cooperative system solved 6/47 (12.8%). The paired contrast is decisive: 15 pairs were solved solo-only against 1 coop-only (exact McNemar test, two-sided p = 0.0005). The gap is therefore not an artifact of task selection or model capability drift — it emerges on identical tasks with an identical model, and its magnitude (a 3.3× reduction in solve rate) closely mirrors the original CooperBench finding.

## Locating the Gap

Our pre-merge independent evaluation stage allows a decomposition unavailable in the original benchmark. In the cooperative condition, both agents independently passed their own feature's held-out suite in 21/47 pairs — statistically indistinguishable from the solo condition's 20/47 (discordant pairs: 2 vs 3). Splitting the work across two agents therefore causes no measurable loss of individual capability: an agent working alongside a partner solves its own feature exactly as often as a solo agent does. The entire gap arises downstream, at patch integration. Of the 20 pairs demonstrably solvable by a single agent, the cooperative system delivered only 5 (25%); all pairs that were independently solved but jointly failed were lost to textual merge conflicts rather than functional incompatibility. The coordination gap is thus, on this data, an integration gap: the agents write working code but cannot place their edits so that the contributions combine.

## Cost

Cooperation is also uneconomical. The cooperative condition averaged $1.12 per pair against $0.68 solo (API-equivalent pricing); per solved pair this is $8.80 versus $1.60 — a 5.5× penalty for coordinating.

## Implications

These results validate the two design decisions underlying our protocol study. First, because the gap is concentrated entirely in pairs that a solo agent can already solve, benchmarking coordination on unscreened pairs wastes most of its signal on capability failures (26 of 47 pairs here); our capability-screened nano subset addresses this directly. Second, because information exchange demonstrably occurs — agents in the cooperative condition messaged in every evaluated pair — while conflicts persist, protocol interventions must target how edits are placed and combined, not merely whether agents communicate.

# Understanding the Failures

The initial paper fails in many ways to distinguish the difference between genuinely finding common failure modes in coding partners and simply showing that certain methods may improve performance of agents on the CooperBench benchmark alone. Furthermore, the only failure mode measured is either pre-merge (individually incapable) or post-merge (individually capable but they fail to correctly work together). The issue is not only finding these conflicts, but understanding why these conflicts happen.

## The Conversations

Manually reading through the conversations of the agents, we can start to unpack why these agents are failing and where the communication is breaking down. Of all 50 feature pairs tested in the flash dataset, all 50 agent pairs show evidence of attempting to resolve overlap. This behavior arises from the system prompt.

## The Free-Messaging System Prompt

In the free-messaging condition, each agent's instruction is composed of three parts, separated in a single prompt: (1) the feature specification (the agent's own feature.md, never the partner's); (2) a submission protocol instructing the agent to write its final unified diff to patch.txt before exiting; and (3) a cooperation protocol block that names the partner, warns that features may overlap, and documents the messaging commands. "Free" refers to the message content: it is unconstrained plain text, with no required fields, no message types, and no validation — in contrast to the structured arms, where messages missing required fields are rejected. The cooperation block is reproduced verbatim below (as rendered for agent1):

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

Two properties of this prompt matter for interpreting the failures. First, the coordination behaviour we observe in the transcripts is prompt-compliant: agents declare their feature and intended files at the start, acknowledge each other, and keep messages short — precisely the recommended workflow. The failures therefore occur while the agents are following the protocol they were given, not because they ignore it. Second, the prompt says nothing about how the two contributions are ultimately combined. It does not mention that the two patches will be naively git-merged at evaluation time, nor that two textually overlapping edits conflict even when the agents have agreed they are semantically compatible. Its step 3 even suggests agents "merge changes" — an action that is impossible in isolated workspaces, and transcripts show agents discovering this mid-run and reasoning incorrectly about its consequences. The prompt's mental model of the environment ends exactly where the observed failures begin, which makes it the natural site for protocol interventions.

## The Failure Modes

Combining the mechanical evidence (patches, merge diffs, gold reference patches) with the transcripts yields five failure-mode findings, each verified programmatically on the 15 coordination failures:

| # | Finding | Count | Evidence |
|---|---|---|---|
| F1 | **Failure is spatial, not semantic.** Every coordination failure is a textual merge conflict; zero capability-clean pairs failed on incompatible semantics after a clean merge | 15/15 | eval merge status |
| F2 | **The overlap is task-inherent.** The gold reference patches for the two features also collide (same file, overlapping hunks) in every failing pair — by construction, since benchmark pairs are selected for gold-patch conflict | 15/15 | gold-patch hunk comparison |
| F3 | **Information exchange is not the deficit.** The eventually-conflicting file was named in the conversation in every failure, and every agent declared the overlapping files it touched | 15/15 | conversation vs patch files |
| F4 | **Agreement without resolution.** Agents identify the collision precisely, agree a plan ("let's each add our own param"), and still emit textually colliding edits | dominant pattern | transcripts |
| F5 | **Wrong merge model.** Agents reason as if sharing a workspace ("your changes aren't present in my copy… you hadn't touched the files yet — go ahead"); nothing in the prompt describes the naive-merge evaluation | recurring | transcripts |

The six passing pairs did something the failures did not: they negotiated placement at sub-file granularity (methods, line ranges), put new code in disjoint regions of the shared file, and confirmed disjointness before submitting. File-level overlap did not predict failure — 45 of 47 evaluated pairs overlapped on files, and 14 of those merged cleanly. The discriminating behaviour is resolving the overlap, not knowing about it.

Read against the original CooperBench taxonomy [5], our failures concentrate in their *expectation failures* (information shared but never integrated into the partner's actions), with clear instances of their *trust paradox* (F5). Their *communication failures* — vague, unanswered, ill-timed messages — are nearly absent in our transcripts. Most strikingly, their finding that agents are "decent at spatial coordination but fail at semantic coordination" inverts on these conflict-selected Python pairs: here, spatial failure is the entire story.

# Streamlining the Dataset

The original dataset is highly inefficient. Many of the tasks fail not due to poor communication, but due to model performance. In these instances, no level of communication would solve our issue and so the signal we receive is void. In order to solve this issue, I ran the feature pairs iteratively using Sonnet 5 on a solo agent to isolate feature pairs that are solo-capable. One of the big issues with AI research is cost. Everything must be streamlined, including the dataset.

## How This Moves the Baseline

This moves the baseline from potentially solvable to "solvable individually". Any changes to performance metrics in further repeats of the experiment using multi agents are therefore due to communication errors alone.

# The Protocol Study: From Failure Modes to Interventions

The failure modes identified on flash generate testable predictions about which messaging protocols should and should not help. We evaluated six arms on the capability-screened nano set (20 pairs, 18 after pre-registered exclusions), all with the same model (Claude Sonnet 5), the same scaffold, and no shared git workspace. Critically, every protocol is implemented purely as a system prompt plus message-field validation — nothing else about the system changes between arms.

## The Arms as Targeted Interventions

| Arm | Protocol mechanism | Failure mode targeted | Prediction from the flash analysis |
|---|---|---|---|
| control | no messaging | — (floor) | conflicts dominate |
| free-text | unconstrained messages | F3 (exchange information) | no effect — information already flows |
| semi_structured | every message carries type (CLAIM/INTENT/…) + files + summary | F3 (declare more clearly) | no effect — declarations were already made, and accurate |
| plan_handshake | two-phase PROPOSE/ACCEPT of a disjoint file split before editing | F1 at file granularity | no effect — F2 shows the overlap is *within* files, so no disjoint file split exists |
| designated_coder | for each shared file, one agent owns and writes the union; the other defers and sends a spec | F4 (eliminate dual authorship) | should work *if* the deferring agent actually defers |
| coauthor_overlap | for each overlapping construct, both agents co-author and emit byte-identical merged code | F4 + F5 (resolve the collision itself) | should work — git merges identical hunks cleanly |

## Results of the Pre-Registered Comparison

The primary endpoint is the merge-clean rate; inference is Cochran–Mantel–Haenszel stratified by pair, Holm-corrected across the contrast family.

| Arm | runs | merge-clean | vs control (CMH OR) | Holm p | verdict |
|---|---|---|---|---|---|
| control | 270 | 13% | — | — | floor |
| free-text | 270 | 21% | 1.79 | 0.105 | ns — as predicted |
| semi_structured | 270 | 16% | 1.24 | 1.000 | ns — as predicted |
| plan_handshake | 270 | 20% | 1.63 | 0.159 | ns — as predicted |
| designated_coder | 88 | 18% | 1.43 | 1.000 | ns — see below |
| **coauthor_overlap** | 89 | **78%** | **27.7** | **<0.0001** | **improved — as predicted** |

The failure taxonomy makes the mechanism visible directly. Under control, 87% of pair-runs end in textual conflict; the talk-only and plan-only arms leave that essentially untouched (79–84%). coauthor_overlap collapses it to 17%, and it is the only arm that produces *identical* merges (29% of its runs) — both agents emitting the same merged code, which is precisely the protocol's intended fingerprint.

Two arms deserve individual comment. First, designated_coder fails for a diagnosable reason: the negotiation itself succeeds (CLAIM, DEFER, and spec messages are exchanged correctly), but the deferring agent then edits the shared file anyway, so 39% of its runs still hard-conflict, and its high secondary endpoint (58% both_passed) is an evaluation artifact (solo_rescue: the owning agent's union patch passes both suites alone). This is a textbook instance of the original paper's *commitment failure* [5], reproduced under a protocol explicitly designed to exploit commitment. Second, the suggestive-but-uncorrected gains of free-text (raw p = 0.021) and plan_handshake (raw p = 0.040) fall out under Holm — consistent with the intrinsic-collision floor implied by F2: no amount of talking about or planning around a single shared signature line can partition it.

## What This Shows

The chain closes. The flash analysis says two-agent failure on this benchmark is overwhelmingly spatial (F1) and unavoidable by placement alone (F2), that information exchange is not the bottleneck (F3), and that agents agree about overlap without resolving it (F4) under a wrong model of how their work combines (F5). The protocol study confirms every prediction this generates: structuring the communication channel does nothing; planning around the overlap does nothing; the single arm that *resolves the overlap* — co-authoring byte-identical text for the shared construct — lifts the primary endpoint from 13% to 78% (a ~6× improvement, OR 27.7, p < 0.0001).

Because every arm differs only in its system prompt and message validation, this constitutes direct evidence for the central claim of this work: prompt-level protocol design alone is sufficient to produce substantial coordination improvement. The residual failures of the best arm (17% textual conflict, 10% functional failure) mark where the next problem begins: once the spatial collision is solved, the semantic coordination failures that dominate the original paper's taxonomy finally become visible.

# The Scaling Study: The Cost of Adding Agents

Every result so far fixes the team size at two. The protocol study shows the two-agent integration gap is solvable at the prompt level, but it leaves the more basic question untouched: as a fixed workload is divided among *more* agents, does the cost of coordinating grow, and how? Answering this requires two changes to the apparatus. The workload must be held constant while only the agent count varies. And, more importantly, the naive two-branch merge used as the coordination oracle throughout the benchmark is unfair to the very thing we are measuring: it conflicts whenever two agents touch the same lines, whether or not they coordinated, conflating genuine coordination failure with incidental overlap that any competent integrator resolves trivially.

## A Fairer Apparatus: Agent-Owned Integration

We therefore built a shared-repository mode. All N agents work against one git remote seeded at the task's base commit; each agent implements its assigned features, then fetches its peers, merges their branches into its own tree, resolves any conflicts, and rebuilds its patch from the *integrated* result. Integration is thus performed by the agents, as part of their coordination work — not imposed by the evaluator. Evaluation no longer merges anything: it scores the single integrated tree the agents produced against every feature's held-out suite. We verified the mechanism directly at N = 2, 3, and 4: in each case every agent fetched and merged all of its peers and the agents converged on the same integrated tree, and a four-agent integration on a conflict-clique task passed all four held-out suites — confirming that the agents genuinely integrate rather than shipping isolated patches.

## Design

The independent variable is the agent count N ∈ {1, 2, 3, 4}; the constant is a pool of K mutually-conflicting features (a clique in the gold conflict graph) split across the N agents by a fixed round-robin partition. N = 1 is one agent implementing all K; higher N deals the same K features across more agents. Every pool is solo-screened — a single agent must complete all K — so that any degradation at higher N is attributable to coordination, not to raw difficulty; this also anchors the curve at a clean solo ceiling. The primary measure is a graded score, the fraction of the K held-out suites passing on the integrated tree, which credits a partially-correct team (three of four features working = 0.75) and treats a merge that breaks the codebase, so tests fail to even run, as 0.

Solo-achievability is the binding constraint. Only ~24% of K = 4 candidate tasks pass screening (4 of 17 flash tasks), so the four-agent sweep is limited to four pools; the harder repositories become solo-achievable only at K = 3, capping them at N = 3. The final dataset is 10 pools across six repositories, 118 runs under Claude Sonnet 5 (~$300 API-equivalent).

## Results: Efficiency Collapses as a Power Law

The cleanest and most general result is in efficiency — the fraction of the workload solved per dollar spent.

| N | graded score | cost / run | solved per \$ | vs. solo |
|---|---|---|---|---|
| 1 | 0.96 | $0.68 | 1.40 | 100% |
| 2 | 0.92 | $1.93 | 0.48 | 34% |
| 3 | 0.88 | $3.59 | 0.24 | 17% |
| 4 | 0.94 | $7.02 | 0.13 | 10% |

Efficiency falls as a power law in the agent count, efficiency = 1.45·N^−1.67 (R² = 0.996), reaching ~10% of the solo value at four agents. The relationship is *universal*: fitting each pool separately, all ten collapse as power laws with exponents between 1.1 and 2.3 (mean 1.76, every R² > 0.9). The exponent exceeding 1 everywhere is the substantive point. If dividing the work simply gave each agent a fixed share at a fixed per-agent cost, efficiency would fall as 1/N (b = 1); the observed b ≈ 1.8 means each added agent is *super-proportionally* wasteful — the coordination overhead (re-loading shared context, messaging, re-integration, and repair of botched merges) grows faster than the work is divided. This holds even for pools whose correctness never degrades: pallets_jinja/1621 integrates perfectly at every N, yet its efficiency still falls 1.07 → 0.15, a 7× loss. The efficiency penalty does not require a coordination *failure* — it is the price of coordination itself.

## Correctness and Cost

Correctness degrades more mildly, and less universally. Averaged over all ten pools, the graded score falls 0.96 → 0.92 → 0.88 from one to three agents, and the strict all-pass rate — the probability the team ships a fully-correct integration — falls 86% → 75%. The four-agent point recovers to 0.94, but only because just the four cleaner K = 4 pools reach it; this is a composition artifact, not a genuine recovery, and cannot be compared to the N ≤ 3 means, which span all ten pools. The degradation is concentrated on the hardest repository, dspy, whose two tasks fall 0.92 → 0.75 and 0.75 → 0.42, while six of the ten pools integrate cleanly and hold near 1.0. When correctness is lost, the failure mode is specific: the agents merge but botch the integration, producing code that no longer runs, so the held-out suite returns zero passed and zero failed.

Cost, by contrast, rises on every pool and is close to linear in N — each added agent adds a roughly constant $1.7–$2.3 per run (its own context load plus its slice of the work), for a ~10× increase from one to four agents on the same workload. It is this near-linear cost against flat-or-declining correctness that produces the super-linear efficiency collapse.

## What This Shows

Where the protocol study showed that the two-agent integration gap is fixable, the scaling study shows what prompt design does *not* fix: the cost of coordination itself. Splitting a task a single agent can already solve across more agents buys no correctness — at best it matches solo, and on hard, conflict-dense tasks it actively destroys it — while the work delivered per dollar falls as roughly N^−1.8, a penalty that appears on every task we measured, including those that remain perfectly correct. For agentic development on interdependent work, adding agents is not merely unhelpful; it is super-proportionally expensive for the same result. This is a limit on parallelism that no messaging protocol can remove, because it is paid before any message is sent — in the redundant context each agent must load and the integration each must redo.

# Conclusion

This work set out to test whether the coordination gap between LLM coding agents is a fixed cost of working in parallel, or a failure with identifiable, addressable causes. The answer is the latter, and the evidence forms a closed chain.

First, we replicated the CooperBench finding on our own infrastructure with a stronger design than the original: a paired solo baseline on identical tasks with an identical model. The gap reproduced almost exactly — a solo agent solved 42.6% of pairs where the cooperating pair solved 12.8% (McNemar p = 0.0005), mirroring the original paper's reported ~30% coordination penalty. Our pre-merge evaluation stage then localised it: pairing costs agents nothing in individual capability — an agent alongside a partner solves its own feature exactly as often as a solo agent does — so the entire gap arises at patch integration.

Second, we identified why. Every coordination failure in the free-messaging condition was a textual merge conflict on an overlap the task itself makes unavoidable; in every one of them the agents had exchanged accurate information about the collision, and in the dominant pattern had explicitly agreed a plan for it. The failure is not communication. It is that agents agree about overlap without resolving it, under a mistaken model of how their contributions combine — a model the system prompt itself never corrects.

Third, we showed the diagnosis is actionable at the cheapest possible level of intervention. Six messaging protocols, differing only in system prompt and message validation, behave exactly as the failure analysis predicts: adding structure or planning to the communication channel yields no significant improvement, because the channel was never the bottleneck; the one protocol that resolves the overlap itself — both agents co-authoring byte-identical code for any construct they share — lifts the merge-clean rate from 13% to 78% (CMH OR 27.7, Holm p < 0.0001). No model change, no fine-tuning, no shared workspace: a six-fold improvement from instructions alone.

The contribution is therefore threefold: a replication that decomposes the coordination gap into capability and integration components; a mechanically verified failure-mode taxonomy that revises the original paper's account for conflict-selected tasks — spatial failure dominates, and information exchange is not the deficit; and a demonstration that prompt-level protocol design is sufficient for substantial coordination improvement. The residual failures of the best protocol point to the next problem: once the spatial collision is solved, semantic coordination — agreeing on what the merged code should do, not merely where it should live — becomes the binding constraint. That is where this line of work goes next.

# References

[1] Vaswani, A., Shazeer, N., Parmar, N., Uszkoreit, J., Jones, L., Gomez, A. N., Kaiser, Ł., & Polosukhin, I. (2017). Attention Is All You Need. Advances in Neural Information Processing Systems 30 (NeurIPS 2017). arXiv:1706.03762.

[2] Wu, Q., Bansal, G., Zhang, J., Wu, Y., Li, B., Zhu, E., Jiang, L., Zhang, X., Zhang, S., Liu, J., Awadallah, A. H., White, R. W., Burger, D., & Wang, C. (2023). AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation. arXiv:2308.08155.

[3] Hong, S., Zheng, X., Chen, J., Cheng, Y., Wang, J., Zhang, C., Wang, Z., Yau, S. K. S., Lin, Z., Zhou, L., Ran, C., Xiao, L., Wu, C., & Schmidhuber, J. (2023). MetaGPT: Meta Programming for a Multi-Agent Collaborative Framework. arXiv:2308.00352.

[4] Qian, C., Liu, W., Liu, H., Chen, N., Dang, Y., Li, J., Yang, C., Chen, W., Su, Y., Cong, X., Xu, J., Li, D., Liu, Z., & Sun, M. (2024). ChatDev: Communicative Agents for Software Development. Proceedings of the 62nd Annual Meeting of the Association for Computational Linguistics (ACL 2024). arXiv:2307.07924.

[5] Khatua, A., Zhu, H., Tran, P., Prabhudesai, A., Sadrieh, F., Lieberwirth, J. K., Yu, X., Fu, Y., Ryan, M. J., Pei, J., & Yang, D. (2026). CooperBench: Why Coding Agents Cannot be Your Teammates Yet. Stanford University & SAP Labs US. https://cooperbench.com
