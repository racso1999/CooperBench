Methodology

The key problem I seek to solve is the communication gap between agents. The original CooperBench paper found that solo agents were far better at solving coding based tasked than their two or multi agent counterparts.

The main issue appears to be a communication gap. System with two or more agents must communicate successfully in order to produce code that both works and is compatible with the other agents code.

My hypothesis is that multiagent systems fail or tangibile failure modes. If we can isolate these modes through benchmarking, we can iteratively produce a protocol that can seek to fix these failures.

How CooperBench Works

CooperBench works by spinning up two isolated containerised environments from which agents work within. Each agent is given a spec, access to it's own copy of the code base and a tool to message with the other agent. (This can be from 1 other up to a whole team of agents). The two agents are then tasked with individually implementing their own features. After which an eval script is run to score the each run.

CooperBench provides a built-in evaluation pipeline, applied automatically as each task pair completes. Evaluation takes place in a fresh container, isolated from the agents' working environments. Any modifications to test files are first stripped from the submitted patches, preventing agents from passing by altering the grading tests. Each patch is then applied to its own branch off the base commit, and the two branches are naively merged (git merge, with no conflict-resolution fallback). If the merge is clean, each feature's held-out test suite — extracted from the original pull request and never shown to the agents — is run against the merged tree. A pair succeeds (both_passed) only if both suites pass; a conflicted merge fails outright. Notably, the held-out tests execute only at evaluation time: agents may run the repository's pre-existing tests while working, but never see the grading suites.

Extending the pipeline

I extended this pipeline in place, so that it produces a strict superset of its original output. First, I added a pre-merge independent evaluation stage: before merging, each agent's patch is tested in isolation against its own feature's held-out suite. This distinguishes capability failures (an agent never solved its feature) from coordination failures (a working implementation broken by the merge) — a decomposition the post-merge signal alone cannot make, and the central quantity of interest in this study.

To first task was to begin naively searching for failure modes. In order to do so, we started by running the flash dataset. The flash dataset contains 50 feature pairs drawn from 20 tasks across 11 open-source repositories — a development subset sampled uniformly at the pair level from the benchmark's 100-pair lite set (seed = 42). I decided to use Claude Sonnet 5 for the model. Preliminary (pilot) tests were run against the flash dataset to determine a suitable model for our experiments. Key problems to consider were cost, individual model capability, and token throughput. Local models were tested but ultimately not used due to their limited token throughput: with single locally hosted models we were restricted to sequential model calls, and this lack of concurrency added a large time overhead. Secondly, a variety of cloud API models were tested; several were capable, but the cost overhead was too high. Finally, I settled on the Claude Code wrapper, through which agents authenticate against a Claude Max (20×) subscription. This allowed access to multiple models at a fixed subscription cost, offering excellent value per token relative to per-call API billing.

Replication of the Original Study

In order to begin, I wanted to replicate the original study. It is first important to test whether we see the same issues with out own system. I expect to see that increasing difficulty of the tasks results in more failures. The original study also points to the largest communication gap arising with medium level tasks.

The orignal study also tested the effect of allowing agents to freely communicate between each other. Although found that communication alone has no benefit to overall sucess rates. In order to build on this, we must first replicate the study and extract as much data as possible.

To replicate the study, I decided to use the flash dataset. The flash dataset contains 50 feature pairs drawn from 20 tasks across 11 open-source repositories, sampled uniformly at the pair level from the benchmark's lite subset (seed = 42), and is intended as a development set for rapid iteration. CooperBench ships several subsets ranging from a 10-pair smoke set (core) to a 100-pair curated evaluation set (lite), alongside the full 652-pair enumeration; flash is a 50-pair development sample of lite, and nano is our 20-pair capability-screened subset introduced for the protocol study.

To establish that the coordination gap reported by CooperBench reproduces on our infrastructure, we ran the 50-pair flash subset under two conditions with an identical model (Claude Sonnet 5): a solo condition, in which a single agent implements both features of a pair, and a cooperative condition, in which two isolated agents implement one feature each and may exchange free-text messages. Because both conditions run on the same feature pairs, the comparison is paired at the pair level, removing task difficulty as a confound. Three pairs could not be evaluated in either condition and are excluded, leaving n = 47.

Results. The solo agent solved 20/47 pairs (42.6%), while the cooperative system solved 6/47 (12.8%). The paired contrast is decisive: 15 pairs were solved solo-only against 1 coop-only (exact McNemar test, two-sided p = 0.0005). The gap is therefore not an artifact of task selection or model capability drift — it emerges on identical tasks with an identical model, and its magnitude (a 3.3× reduction in solve rate) closely mirrors the original CooperBench finding.

Locating the gap. Our pre-merge independent evaluation stage allows a decomposition unavailable in the original benchmark. In the cooperative condition, both agents independently passed their own feature's held-out suite in 21/47 pairs — statistically indistinguishable from the solo condition's 20/47 (discordant pairs: 2 vs 3). Splitting the work across two agents therefore causes no measurable loss of individual capability: an agent working alongside a partner solves its own feature exactly as often as a solo agent does. The entire gap arises downstream, at patch integration. Of the 20 pairs demonstrably solvable by a single agent, the cooperative system delivered only 5 (25%); all pairs that were independently solved but jointly failed were lost to textual merge conflicts rather than functional incompatibility. The coordination gap is thus, on this data, an integration gap: the agents write working code but cannot place their edits so that the contributions combine.

Cost. Cooperation is also uneconomical. The cooperative condition averaged $1.12 per pair against $0.68 solo (API-equivalent pricing); per solved pair this is $8.80 versus $1.60 — a 5.5× penalty for coordinating.

Implications. These results validate the two design decisions underlying our protocol study. First, because the gap is concentrated entirely in pairs that a solo agent can already solve, benchmarking coordination on unscreened pairs wastes most of its signal on capability failures (26 of 47 pairs here); our capability-screened nano subset addresses this directly. Second, because information exchange demonstrably occurs — agents in the cooperative condition messaged in every evaluated pair — while conflicts persist, protocol interventions must target how edits are placed and combined, not merely whether agents communicate.

The Plan

1. Replicate inital study using flash data set and sonnet 5.
2. Evaluate whether our replication displays similar behavior.
3. Isolate common failure modes.
4. Build protocols through structured messaging and system prompt modification to help reduce these failure modes.

Our Contributions

Out initial flash data set run confirms the hypothesis provided by CooperBench. Multi agent systems are worse than their solo counterparts. The number one reason for failures was due to agents writing over the same lines.

Here the experiment can take one of two directions. We give the agents a shared git workspace. This way, it more closely represents a realistic development setting. Whereby developers work together on a shared codebase. Alternatively, we limit their scope so that all they have is their messaging. This way, any improvments in performance can be contributed to communication alone.

The inital paper fails in many ways to distinguish the difference between genuinely finding common failure modes in coding partners and simply showing that certain methods may improve performance of agents on the CooperBench benchmark alone. Furthmore the only failure mode measured is either pre merge (individually incapable) or post merge (indivudally capable but they fail to correctly work together). The issue is not only funding these conflicts, but understanding why these conflicts happen.

The Conversations

Manually reading through the conversations of the agents we can start to unpack why these agents are failing and where the communcation is breaking down. Of all 50 feature pairs tested in the flash dataset, all 50 agent pairs show evidence of attempting to resolve overlap. These behavior arises from the system prompt.

The system basic system prompt for the --free msg mode:

From a design perspective, it makes more sense to keep agents in the dark from one another and to NOT allow them to share git workspaces. This in turn isolates an increase in performance metrics to communication alone and arguably gives us a more meaningful signal to determine what improves communcation between two agents. To further explain, in a 'real_life" setting, perhaps it would make more sense to allow agents to have access to each others work space. However for the sake of isolating failure modes specific to communication issues and for the sake of this experiment. We decided to keep both agents completely isolated.

Futhermore, the original dataset is highly inefficient. Many of the tasks fail not due to poor communcation, but due to model performance. In these instances, no level of communcation would solve our issue and so the signal we recieve is void. In order to solve this issue, I ran the feature pairs iteratively using sonnet - 5 on a solo agent to isolate feature pairs that are solo capable. One of the big issues with AI research is cost. Everything must be streamlined including the dataset.

How this moves the baseline?

This moves the baseline from potentially solvable to "solvable individually". Any changes to performance metric in further repeats of the experiement using multi agents is therefore due to communication errors alone.
