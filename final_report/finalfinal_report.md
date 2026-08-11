# Introduction and Related Literature

Large language models (LLMs), when given a sequence of text, predict the continuation token by token. LLMs retain no memory from one run to the next - they are stateless. An AI agent is what emerges when an LLM is wrapped in a loop - given a "harness". The agent is provided with access to tools, allowing it to execute against a real environment. The resulting output is fed back into into the agent's context /footnote, giving it a working memory across steps - a state. This infrastructure turns a next token predictor into a system that can persue multi-step goals such as editing files and reading a codebase [1], surfing the internet [2] or managing databases [3].

The concept of a multi agent systems itself is not novel; discussion of such systems goes as far back as the late 1970s, and can be seen in Hewitt's model of intelligence as a "society" of communicating problem-solving experts (Artificial Intelligence, 1977) [4]. For the sake of simplicity, in this paper, an "agent" will always be referring to an LLM based agent.

After one has realized the benfits of a single agent, the appeal for a team of several is obvious and multi agent systems have risen in popularity accordingly. The intuition borrows from human organisations: divide the work, letting multiple workers share the load and collaborate. In theory, several agents should provide the parallelism that a single model instance cannot. Frameworks built on this premise have proliferated, from conversational multi-agent toolkits such as AutoGen [5] to software company simulations such as MetaGPT [6] and ChatDev [7] which spawn teams of agents with focused tasks such as engineers, testers and product managers.

Popular frameworks for orchestrating these agents have risen in popularity alongside them, differing mainly in how coordination is expressed. Google's Agent Development Kit (ADK) [8] arranges agents into a hierarchical tree, while LangChain [9] and its graph-based successor LangGraph [10] provide infrastructure for building complex multi-agent systems with explicit state management and graph based architectures. CrewAI [11] assigns agents named roles within a "crew", closely mirroring the divide-the-work intuition described above. The OpenAI Agents SDK [12] instead coordinates through explicit handoffs, and the Claude Agent SDK [13] through delegation to sub-agents. Parallel to these engineering efforts, a new research line has emerged,  studying agent collaboration directly, including CAMEL [14] on role-playing communication and AgentVerse [15] on emergent behaviour in agent groups.

Each of these, however, rely on the same intuition - dividing work provides additional benefit. In "CooperBench: Why Coding Agents Cannot be Your Teammates Yet" [16], Khatua et al. found that solo agents solved coding tasks at substantially higher rates than their multiagent counterparts. "The curse of coordination" (fittingly named by the authors) suggests agents average ~30% lower success working together than one agent doing both tasks alone. Similarly, Cemri et al. (2025) [17] observe that multi-agent system performance gains, across popular benchmarks, remain minimal when compared to single-agent frameworks. The authors analyse over 200 tasks across seven popular multi-agent frameworks and identify fourteen recurring failure modes. The failures demonstrate structural consequences of coordination, suggesting that the overhead introduced by dividing work between agents can actively erode the capability of the underlying model. Comparable findings emerge even in the narrower setting of multi-agent debate, one of the most widely adopted collaboration patterns. Smit et al. (2024) benchmark a range of debate protocols against single-model prompting strategies and find that debating systems, in their current form, do not reliably outperform simpler alternatives such as self-consistency, despite incurring considerably greater cost in tokens and latency. Where debate protocols did recover performance, it was only after careful hyperparameter tuning [18].

So where are they going wrong? To crudley understand the cost of team scaling, one must consider two fundamental properties of communication. Firstly, the re-ingestion of context - sharing information with another agent means compounding the total system context size. Secondly, and to further compound, messages may be overworded, inconclusive or incorrect - a greater proportion of messaging increases the chance for misinformation to be spread. Decisions that a solo agent would make alone against a coherent whole are instead made against a fragmented many. Consequently a multi-agent system will often spend more to reach the same outcome. Surely no ammount of additional tuning or structural design can recover the coherence a single context provides. In this paper, we refer to the compound communication overhead as the "Communication Tax".

Why then would we consider improving a system that is doomed to underperform? Ultimately, efficiency and success rate are not the only measures of value. Multi agent systems, despite being less effective, may at times be more useful or perhaps neccessary. Some tasks pair agents with contrasting abilities [19], and in other settings, agents may be forced to work together whether or not collaboration is optimal [20]. When they do, we want to make sure they do so to their maximum capability while paying as little of the "communication tax" as possible.

# Our Aims

In this paper, we aim to isolate and measure the commincation overhead ("Communication Tax") in multi-agent systems and, through contributions to benchmarking apparatus and additional experiments, quantify how changes in team size and structure affect the tax. We hypothesise that multi-agent systems will typically underperform their solo-counterparts in terms of efficiency primarily due to the growing communication tax as systems scale - but that focused topology changes could significantly reduce this gap.


## Replicating the Curse of Coordination

** In this paper we will refer to a "task" — a set of features from one real repository; a "feature" — one unit of that repositories functions, given to an agent as a natural-language spec; a "pair of features" — any two features from the same task. A "pool" - A collection of features.**

 In "CooperBench: Why Coding Agents Cannot be Your Teammates Yet", Khatua et al. - alongside their headline finding of "The Curse of Coordination" [16] -  introduce a comprehensive benchmarking suite that isolates communication failures in multi-agent systems, testing whether multiple LLM coding agents can work in parallel on the same codebase. CooperBench works by sequentially running multiple containerised environments within which agents can work in isolation. Each agent is given a spec, access to its own copy of the codebase, and a tool for messaging other agents (from one up to a whole team). The agents can also read files and edit code. They are then tasked with individually implementing their own features.

After the agents have finished working on their features, or the step or time cap has been reached, the features are naively merged. A naive merge is a textual merge: it combines changes based on the lines of code each agent modified, without any understanding any of the code's structure or logic. Overlapping edits are flagged as conflicts, while non-overlapping edits are merged automatically (even if they break each other semantically). The merge is performed by CooperBench automatically, in a fresh container isolated from the agents. 

An evaluation is then performed - a clean merge is run against both features' test suites resulting in a 'both_passed' **success** only if both suites pass. If either suite fails we record a **failure**.

# Replicating the Curse of Coordination - Extending the Evaluation

Our first contribution to the benchmark - an extended evaluation suite. Testing only after a clean merge fails to seperate instances where an agent never solved it's feature, from one whose work didn't successfully merge. In such cases the original evaluation pipeline does not descriminate between an agents ability to code and an agents ability to write code that integrates. We fix this with the addition of pre-merge function testing. Each agent's individual feature is tested against it's own test suite in isolation prior to merging with the other agents. Capability and integration are therefore reported separately giving us finer granularity. Secondly we introduce improved cost metrics. Cost is taken directly from the total_cost_usd field of the Claude Code CLI's terminating result event — a single figure the CLI computes from the run's input, output, and cache read/write tokens at Anthropic's published list prices. A run's cost is the sum across its participating agents, which we use as a proxy for computational effort. This gives the first of two cost metrics we add to CooperBench's evaluation - scoring every condition in passes per dollar alongside pass rate. The second metric: each run's total is decomposed into four additive dollar accounts — context (loading the shared repository and specification), task (implementing), communication (messages sent, received, and re-ingested), and rework (revisions messages provoke) — so that the coordination overhead can be located. We do so by reconstructing each agent's per-turn history from the harness'  execution stream and weighting each account by its token-type list price, so the four figures sum exactly to the run's cost.

/footnote [explain the breakdown calculations] /footnote [explain how to use new evaluation]

/figure evaluation diagram

# Replicating the Curse of Coordination - Methodology

To establish that the coordination gap report in "CooperBench: Why Coding Agents Cannot be Your Teammates Yet" reproduces, we opted to use the 50-pair flash subset of tasks. This subset accounts for 50 of the "full" CooperBench dataset's 652 feature pairs, spanning 20 of its 30 tasks and 11 of its 12 repositories. A smaller dataset is selected over a larger one allowing us to perform multiple passes over the same N, feature-pair pairs and thus reducing the effect of LLM stochastisticity /footnote. Preliminary pilot tests were run to determine a suitable model. Factors to consider were cost, individual model capability, and token throughput - Claude Sonnet 5 was ultimately selected. The model is accessed through the Claude Code CLI, which CooperBench launches headless inside of each agent's container. /footnote [describe headless] The experiment was run under two conditions: a Solo condition, in which a single agent implements both features of a pair, and a Co-op condition, in which two isolated agents implement one feature each. The agents may optionally exchange messages via a Redis-backed communication channel. \footnote [explain redis backed] Both conditions are run on the identical set of feature pairs - every feature pair has one Solo result and one Co-op result. This yields a matched design in which the two settings are compared within each feature pair rather than across aggregate scores, removing variance in task difficulty as a confound.

For our replication of the original study, we opted to use the same 'free-msg" protocol - the same default protocol that is both shipped with CooperBench and used in the orignal 'Curse of Coordination" study. Each agent's instruction is a single prompt composed of three parts: (1) the feature specification; (2) the submission protocol; (3) the cooperation protocol. In "free-msg" the agent is informed of it's partner, warned of overlapping features and taught messaging commands. These commands allow the agents to message using shell commands through the Redis-backed communication channel. 

```text
## free-msg

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
2. Periodically `coop-recv` to read what your peers have sent -- at
   minimum after major edits and before submitting.
3. If two agents need to modify the same file, coordinate explicitly
   (split the file, agree on one owner, or merge changes).
4. Keep messages short and focused: file names, function names, and
   one-sentence intents are usually enough.

Messages are not magic -- your peers only know what you tell them.
```

## Replicating the Curse of Coordination - The Findings

Consistent with the reported "Curse of coordination", we observe a substantial drop in task success from the solo agent to it's two agent counterpart. Across 46 matched feature pairs (4 runs removed - intermittent evaluation-container failures left too few scored runs for a reliable estimate) the average pass rate fell from 44.2% under the Solo condition to 12.3% under the Co-op condition - a reduction of 31.9%. \footnote (See Calculation 1 in the appendix). This finding replicates those of the original study, in which Co-op performance is substantially lower than Solo performance. Recall "agents average ~30% lower success working together than one agent doing both tasks alone." [16]

In the Co-op condition, both agents' independent work passed their own test suites in 62 of 138 runs (44.9%) — statistically indistinguishable from the 61 of 138 runs (44.2%) passed by the Solo condition. Splitting the work across agents therefore causes no measurable loss of individual capability in the replication. The gap instead arises at patch integration. The agents consistently write working code but cannot place their edits so that contributions cleanly merge with other agents' work. of the 62 runs where both agents individual test-suites passed, only 17 survived integration with 45/45 losses due to textual merge conflict.

## Replicating the Curse of Coordination - Accounting for Cost

"CooperBench" [16], as well as our replication, demonstrates a clear coordination gap in pairs of agents. Earlier we hypothesised that solo agents would be not only more successful but more efficient. We therefore normalise the replication's results by the cost using the new evaluation metric.

Across the same 46 matched feature pairs, the Solo condition achieves 0.675 passes per dollar spent, compared to 0.107 passes per dollar under the Co-op condition — a 6.3-fold gap, versus the 3.6-fold gap observed in raw pass rate alone. A paired Wilcoxon signed-rank test on per-pair cost efficiency confirms this difference is statistically significant (W = 2.0, p < .001). This widening indicates that the coordination penalty is not limited to lower success rates: Co-op teams are also less cost-efficient per successful outcome, compounding the disadvantage relative to Solo.

\figure [cooperbench replication]


## Scaling The Team - Too Many Cooks

In "Do more agents help? Controlled and protocol-aligned evaluation of LLM agent workflows." [21], Fu et al. find that most multi-agent workflows fail to reliably outperform a matched single-agent baseline once evaluation infrastructure is controlled. They attribute the overall performance to task-protocol fit rather than the number of agents. Their comparison, however, never directly varies agent count independently of communication protocol, prompt, and topology. Similarly, as shown in CooperBench (Khatua et al., 2026), coordination performance degrades sharply as the number of cooperating agents increases. In a controlled experiment scaling from 2 to 4 concurrently cooperating agents on 46 tasks drawn from 3 task sets, success rates declined monotonically: from 68.6% with 2 agents, to 46.5% with 3 agents, to 30.0% with 4 agents. This trend reinforces the "curse of coordination" observed in the two-agent setting, suggesting that adding more agents to a shared workspace compounds rather than alleviates coordination difficulty.

Again however, their experiment fails to isolate the effect - Agent count is set to the number of features assigned, so a three or four-agent run carries three or four features. The decline observed therefore confounds coordination overhead with a workload that has grown.

We therefore built PoolBench - an extension to CooperBench. \footnote[poolbench] In PoolBench, the workload is arranged into "Pools" comprised of a K-feature clique. Each individual pool may be solved by any number of agents N ∈ {1,2,3,4,...,K}, allowing us to fix the workload and vary only N. All N agents work against one git remote seeded at the feature pool's base commit. Each agent implements its own features, fetches and merges its peers' branches, resolves any conflicts, and rebuilds the patch. Integration is therefore part of the agents' coordination work. The evaluator scores the single integrated tree against each feature's test suite.



## Scaling The Team - Experimental Design

The agents are arranged in a flat-peers topology - there is no hierarchy between agents. The independant variable is N (the number of agents in the team); the constant is the K-feature pool. The pool of features is split across the agents using a round robin distribution as default. Every pool is solo screened (Every pool must be solvable by the solo agent) so that performance losses at higher N can be contributed to coordination cost rather than raw pool difficulty. Primarily we measure a graded score; the fraction of K feature test-suites that pass on the integrated tree, allowing us to credit partially correct teams (3/4 features = 0.75). The final dataset consists of 14 pools across 6 repositories and 148 total runs using Claude Sonnet 5 (~$410 API-equivalent cost).


\diagram [pool bench]


## Results: Efficiency Collapses

Efficiency - the fraction of the workload solved per dollar spent.

\Table 3 Efficiency by agent Count N, averaged over all pools.

As the number of agents grows, the work solved per dollar collapses, falling as a power law in agent count. Efficiency (cost/run) =  1.28N^-1.61, reaching ~10% of the solo value at four agents (Figure 3). The relationship is universal: fitting each pool seperately, all fourteen collapse as power laws with exponents between 1.1 and 2.3. The exponent exceeding 1 across all pools is the substantive point: if dividing the work simply gave each agent a fixed share at a fixed per-agent cost, efficiency would fall as 1/N (ro = 1). The observed (ro = 1.8) means that each added agent is super-proportionally wasteful. The coordination tax grows faster than the team grows. This is true even for pools where the correctness never degrades: pallets_jinja/1621 integrates perfectly at every N, yet the efficiency falls 1.07 -> 0.15, a 7x loss. The Communication Tax therefore does not require a coordination failure. In this instance, it is the price of coordination itself.

 ## Correctness

Correctness falls more gradually and less universally. The graded score, averaged over all fourteen pools, declines from 0.96 to 0.91 to 0.89 as agent count increases from one to three. Similarly, the strict all-pass rate (the probability the team ships a fully correct integration) falls monotonically from 89% to 82% to 77% to 69% across one to four agents (Figure 4). The degradation is concentrated in the hardest repository, dspy: all four of its cliques degrade (e.g. 0.75 → 0.42 and 0.92 → 0.75), while eight of the fourteen pools integrate cleanly and remain near 1.0.

/figure 4

## Cost

Cost rises on every pool. It increases from $0.78 for a solo run to $7.21 at four agents for the same K features (Figure 5). Decomposing cost into four accounts shows redundant context ingestion grows roughly linearly (Figure 6): $0.50, $0.92, $1.47, $2.27. Per-agent, work inflates super-linearly ($0.27 to $2.37). Each agent does more work, as the team grows. Coordination adds an extra cost on top of that. The messaging channel, measured as tokens sent, received, and re-ingested, accounts for 23–25% of every multi-agent run. Messaging also provokes rework, meaning files are re-edited in response to inbound messages. When that message-triggered rework is included, the messaging-related share rises to 31–36% ($0.48 communication + $0.16 rework at N = 2, rising to $1.82 + $0.75 at N = 4).

/figure 5, figure 6

# A Supervisor is all They need

 In a flat-peer topology, no single agent is responsible for governing the pool of tasks. Therefore each reconstructs the shared picture privately and then reconciles it with its peers. Making one supervisor agent responsible for the division of labour, and for the final assembly of features, replaces a decision the peers negotiate collectively, with a single focused decision node.

If the tax we have measured is based on mutual coordination, centralising it should therefore reduce it. 

## A Supervisor is all They need - Design

The apparatus, workload, and evaluation are held fixed at the values used in Section ___: the same 14 pools, shared git remote and the same graded scoring of one integrated tree against all K test suites.

The only change is the topology. In the supervised arm, a leader agent (Claude Sonnet 5) is the only participant that receives the K feature specifications. It writes a decomposition plan. It materialises each specification into a shared scratchpad and assigns features to workers (Claude Sonnet 5) through a shared task list. It monitors progress and is the designated integrator whose tree the evaluation scores. Worker agents begin with no specification at all. Instead, they are instructed to poll the shared task list, claim their assigned-task location and collect it. They are instructed to implement only what they are assigned. The round-robin partition — a fixed, benchmark-imposed allocation in the flat arm — is thus replaced by an allocation the leader chooses. Integration is also centralised. Workers are instucted to commit their own feature, push their own branch and exit. Finally, the supervisor is instructed to assemble the team's single tree and submit it for evaluation. The Redis messaging channel does not change. Workers are still able to communicate freely between other workers. They are never however instructed to do so. Every isolated container recieves a roster of the adresses of the other participants. The hierarchy is therefore a property of the agents' system prompt, not infrastructure - this allows us to consider ONLY a change in topology in an attempt to remove all other aspects of variability. In practice, workers do not message other workers. Across the 144 runs, the agents exhanged 384 messages, of which 286 (74.5%) ran supervisor-to-worker and 97 (25.3%) worker-to-supervisor. The supervisor is considered an additional agent: comparisons are therefore made at A = N (flat-peers) versus A = N + 1 (supervised) at matched A. (where N is the number of workers). A flat-peers run of 3 agents is comparible to a single supervisor and N = 2 worker agents. The dataset is 144 total runs (~446 API equivalent) -  r = 3 trials over 48 cells (14 pools × N ∈ {1, 2, 3}, plus the six K=4 pools at N = 4). 

## A Supervisor is all They need - Cost

Matched pool-for-pool — comparing only the pools both arms ran, so the mix of easy and hard workloads is identical on each side — the supervisor topology costs 1.05× flat peers at two agents, 0.72× at three and 0.51× at four. Efficiency — work solved per dollar — follows: 0.93×, 1.38× and 1.81×. The gap has a single mechanism: a flat team pays its coordination once per agent — every peer merges every other and messages every other, so the bill grows with each agent added — while the supervised team pays it once in total, one integration and one hub of messages, leaving little in a supervised run's cost to grow beyond the workers themselves. The Efficiency collapse as a power law again - efficiency = 0.61N-0.69. Recall flat-peers - efficiency =  1.28N^-1.61  (Figure 5). For a fixed workload divided among N agents, one would expect efficiency to fall as 1/N. Where we pay for N agents to do a pool of work. b = 1 is therefore the reference, the value at which coordination itself costs nothing extra. Supervision's b = 0.69 sits comfortably below that reference. As the team grows, each worker impliments fewer features while the supervisor's overhead is increased over more of them, so total cost grows sublinearly in N. The cost accounts locate the mechanism. The communication and rework accounts together is 5.4%, 10.1%, 8.3% and 15.4% of the supervised run across two to five agents, versus 30.6%, 32.5% and 35.7% of the flat-peer-to-peer arm at two to four agents. Taken together, the three views say the same thing: under flat peers, coordination is a cost that compounds — a super-proportional exponent fed by a messaging share that grows toward a third of every run — while under supervision it behaves almost as a fixed fee, paid once and amortised as workers are added. From three agents upward, hierarchy is simply the cheaper way to divide the same work. Neither topology, however, reduces the context floor beneath both, which is why no team of any shape beats the solo agent.


## A Supervisor is all They need - Correctness

On Correctness, the two topologies diverge. Under the supervision topology, the graded score (number of test suites passed / total features) is 0.883, 0.903, 0.895 and 0.917 across two to five agents. Recall the flat-peer-to-peer 0.907, 0.892, 0.922. On the strict all-pass rate, the supervised arm runs 79%, 81%, 76% and 83%. Recall the flat-peer-to-peers monotone decline of 89%, 82%, 77%, 69% from one to four agents. Therfore, at four agents, supervision is ahead on the strict all-pass rate (76% versus 69%) and behind on the graded score (0.895 versus 0.922). The key takeaway here is that supervision maintains the correctness where as flat-peers reduces it as the teams scales. The flat-peer-to-peer loses 20 points of all-pass rate across its range wheras the supervised arm ends where it began. Neither arm approaches the solo baseline value of 0.964 and 89%. The data distribution can explain why the two arms diverge. The flat-peers fail monotonically and increasingly. The share of partial success grows 11%, 14%, 21%, 31% from one to four agents. Supervision on the other hand holds its share of partial successes (14%, 14%, 19%, 11% across two to five). It carries a consistent floor of total failures (7%, 5%, 5%, 6%). Centralising integration therefore makes the supervisor a single point of success. If its merge lands, everything lands and if it fails, everything is lost. No partial contribution survives. 

## A Supervisor is all They need - What This Shows

Hierarchy is not a cure for the communication tax, but it is a substantially better trade-off than flat-peers once a team exceeds two agents. Centralising both allocation of features and the integration of code cuts the messaging-related share of a run from roughly a third to under a sixth. It also flattens the efficiency exponent from N^-1.61 to N^-0.69. It holds correctness where flat peers degrade. Albeit at the cost of converting some partial successes into total failure, it still, however, is not favoured over a single model instance. The solo agent remains better than every configuration of every topology measured here, scoring 0.964 at $0.78. No supervised cell comes within a factor of three of the solo efficiency.




# Wall-Clock Time: Sharing the Work Does Not Make It Faster

One of the main benefits of sharing work is the potential for decreased wall-clock time. Sharing work across more workers should theoretically reduce the total time spent working. A system that has to sequentially run tasks will take longer than one that can run the tasks in parallel. A perfect parallel execution would therefore present itself as T1/N where T is the time to completion and N is the number of agents. This uses data collected from the flat-peers study as well as the supervisor study - 148 flat-peer runs and 144 supervised runs. No new appartus is required. A run's wall-clock time is calculated when the final agent stops.

## Wall-Clock Time - Flat Peers

Flat peers does not deliver the T1/N parallelism. A solo agent completes the full K-feature pool in 3.0 minutes on average; two agents take 5.6, three take 6.5, and four take 8.3. Wall-clock time therefore rises with team size. Coordination lengthens the overall time an agent spends completing their work. They must spend time reading replies, waiting on replies, writing and sending messages. We suspect however that this inversion is likely an artifact of scale. Increasing the time spent solving features could see a different result. At the current small scale, agents spend a considerable ammount of time messaging. For larger individual tasks where a greater proportion of time is spent impleneting the feature - a genuine wall-clock speed up could emerge. Locating the task size at which parallism starts to pay is a natural target for future work.

## Wall-Clock Time - Hierarchy

A supervised team is slower than a flat-peers team at every size: 7.3 versus 5.6 minutes at two agents, 8.2 versus 6.5 at three agents, and 8.8 versus 8.3 at four agents. The gap, however closes as the team scales — supervision is 30% slower at two agents but only 6% at four (Figure 3d).

Both topologies still remain slower than their solo counterpart. The supervised arm realizes 0.52× speed at two agents compared to solo, falling to 0.43× speed at five. The flat arm realizes a slightly improved 0.66× speed at two agents and a 0.56× speed at four.

The reason is the shape of a supervised run, which is like book-ends: a serial opening, a parallel middle, and a serial close — with the supervisor alone on the clock at both ends. In all 144 runs the supervisor finished last. The opening is allocation: every worker sits idle while the supervisor reads the K specifications, writes the plan, and creates the tasks, taking 2.7 minutes at one worker and 3.2 at four. The close is integration: the supervisor merging alone after the last worker has stopped, taking 2.5 minutes rising to 4.3. The two serial segments sum to 5.3–7.5 minutes — 65–73% of the entire run, and on their own already as long as a complete flat-arm run. The middle, by contrast, is genuinely parallel: summed agent time grows from 12.0 to 33.5 minutes across two to five agents while wall-clock grows only from 7.3 to 11.1, so on average 1.65 to 3.03 agents are working at once. Adding workers therefore shrinks only the middle between the book-ends; the serial ends barely move, and they are most of the run.

Flat peers pay the same coordination in the opposite currency. Each peer receives its specification in its opening prompt, so no one starts idle; and each merges its peers concurrently, so integration — performed N redundant times — runs on N clocks at once rather than extending the critical path. That is cheap in time and ruinous in dollars; the supervised arm is the reverse. The flat arm's finding survives the change of topology — sharing the work does not make it faster — but where the flat arm's time penalty grows with the team, the supervisor's shrinks, so the two topologies converge as teams grow.

## Wall-Clock Time - What This Shows

Parallelism is the one benefit a team ought to deliver for free, and neither topology delivers it. Take the solo agent's speed as 1.0. Flat peers manage 0.66× that speed at two agents, falling to 0.56× at four. Supervision is slower still: 0.52× at two agents, down to 0.43× at five. Every one of those numbers is below one, and adding agents never buys them back. A team here is not an imperfect parallel machine but a slower serial one. The division of labour is real; the coordination laid on top of it simply eats more clock than the division saves. One caveat bounds both arms equally. A solo agent completes the entire pool in 4.0 minutes on average, so coordination takes up a large share of every run and swamps whatever the split saves. A longer task would leave more room for parallelism to pay for itself. How much longer, these pools cannot say.
 

# Conclusion

This work asked whether the coordination gap between LLM coding agents is an artifact of benchmark design or a systematic cost of dividing work a single agent can already do. Four results answer it.

First, the gap replicates under a stronger, paired design. On 46 matched feature pairs with an identical model, the solo pass rate of 44.2% fell to 12.3% under free-text messaging (Wilcoxon W = 2.5, p < .001). Per-feature evaluation localises the loss: paired agents pass their own feature's held-out suite as often as solo agents (21/47 vs 20/47), so pairing costs nothing in individual capability. Of the 20 pairs demonstrably solvable by one agent, cooperating pairs delivered only 5, and every loss was a textual merge conflict rather than a functional incompatibility. The coordination gap is, on this data, an integration gap.

Second, the gap widens once computational effort is normalised: 0.675 passes per dollar solo against 0.107 under messaging (p < .001) — a 6.3-fold efficiency penalty against the 3.6-fold gap in raw pass rate. Coordination does not merely lower success; it makes each success more expensive.

Third, the scaling study shows the penalty compounds with team size. Holding a solo-achievable workload of K mutually conflicting features fixed while varying only N ∈ {1, 2, 3, 4}, with integration performed by the agents themselves, adding agents bought no correctness — the strict all-pass rate fell monotonically from 89% to 69% — while cost rose near-linearly (mean ≈$2.04 per added agent). Efficiency therefore collapses as a power law, ≈1.28·N^-1.61 (R² = 0.996), with all fourteen pools individually fitting exponents between 1.1 and 2.3; at four agents, work delivered per dollar is ~10% of the solo value. Because the exponent exceeds 1 everywhere — including on pools that integrate perfectly at every N — the penalty cannot be attributed to coordination *failure*. It is the price of coordination itself: a structural floor of redundant context loading, paid before any message is sent, beneath the stacked overhead of task, messaging, and rework — the last two of which account for roughly a third of every multi-agent run.

Fourth, topology reshapes the tax without removing it. Replacing flat peers with a supervisor–worker hierarchy — a supervisor that plans the decomposition, allocates features to workers, and performs the team's single integration — is marginally more expensive at two agents and slower at every size, and it converts some graceful partial degradation into total failure. What it buys is the exponent: supervised efficiency falls as 0.63·N^-0.69 (R² = 0.856) against the flat arm's 1.28·N^-1.61 (R² = 0.996), so the curves cross at ≈2.1 agents and supervision is cheaper on 13 of 14 pools at three agents and all six at four. On strict correctness supervision holds between 76% and 83% across two to five agents while flat peers fall monotonically 89% → 69%. The mechanism is centralisation, and one half of it is adopted rather than imposed: the same fully connected channel is available in both arms, yet every supervised message passes through the supervisor and none between workers, while integration is centralised by instruction — together cutting the messaging-related share of a run from roughly a third to under a sixth. The context floor does not move — every agent still loads the shared repository in both arms — so what supervision removes is the redundant integration and the peer-to-peer negotiation, not the structural cost of employing more contexts.

Together these results confirm and sharpen our hypothesis: for tasks solvable by a single agent, splitting work across a team is at best correctness-neutral and always efficiency-negative, with a super-linear communication tax in team size under the standard peer topology. The decomposition also identifies where remedies must act. Individual capability survives pairing intact; the bottleneck is integration — agreeing not just on who touches what, but on how contributions combine into one tree. The topology study shows one lever that works at scale: centralising both allocation and integration in a supervisor nearly eliminates the scaling component of the tax and arrests the correctness decline, at the price of slower delivery and an all-or-nothing failure mode. Protocols that resolve overlap explicitly, and mechanisms for semantic coordination on merged behaviour, remain the complementary lever, and the apparatus introduced here — solo-screened fixed workloads, agent-owned integration, per-account cost decomposition, and matched topology arms — provides the instrument for testing both; pools of six to eight interdependent features, where the fitted curves say supervision's advantage should widen, are the natural next experiment. What no protocol or topology will remove is the structural floor this study exposes: for interdependent work, each agent must independently reconstruct the shared context, a redundant cost paid whether or not coordination succeeds. A protocol can trim the removable third that messaging and rework add on top, and a supervisor can stop that third from growing with the team; neither can erase the floor — and the floor alone is enough to make dividing a solo-achievable task efficiency-negative.

# References

[1] Yang, J., Jimenez, C.E., Wettig, A., Lieret, K., Yao, S., Narasimhan, K. and Press, O. (2024) 'SWE-agent: agent-computer interfaces enable automated software engineering', Advances in Neural Information Processing Systems, 37.

[2] Yao, S., Chen, H., Yang, J. and Narasimhan, K. (2022) 'WebShop: towards scalable real-world web interaction with grounded language agents', Advances in Neural Information Processing Systems, 35.

[3] Pourreza, M. and Rafiei, D. (2023) 'DIN-SQL: decomposed in-context learning of text-to-SQL with self-correction', Advances in Neural Information Processing Systems, 36.

[4] Smith, R. G. (1980). The Contract Net Protocol: High-level communication and control in a distributed problem solver. IEEE Transactions on Computers, C-29(12), 1104–1113. doi:10.1109/TC.1980.1675516

[5] Q. Wu, G. Bansal, J. Zhang, Y. Wu, B. Li, E. Zhu, L. Jiang, X. Zhang, S. Zhang, J. Liu, A. H. Awadallah, R. W. White, D. Burger, and C. Wang. "AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation." 2023. arXiv:2308.08155.

[6] S. Hong, X. Zheng, J. Chen, Y. Cheng, J. Wang, C. Zhang, Z. Wang, S. K. S. Yau, Z. Lin, L. Zhou, C. Ran, L. Xiao, C. Wu, and J. Schmidhuber. "MetaGPT: Meta Programming for a Multi-Agent Collaborative Framework." 2023. arXiv:2308.00352.

[7] C. Qian, W. Liu, H. Liu, N. Chen, Y. Dang, J. Li, C. Yang, W. Chen, Y. Su, X. Cong, J. Xu, D. Li, Z. Liu, and M. Sun. "ChatDev: Communicative Agents for Software Development." Proceedings of the 62nd Annual Meeting of the Association for Computational Linguistics (ACL), 2024. arXiv:2307.07924.

[8] Google. Agent Development Kit (ADK). https://github.com/google/adk-python, 2025.

[9] H. Chase. LangChain. https://github.com/langchain-ai/langchain, 2022.

[10] LangChain. LangGraph. https://github.com/langchain-ai/langgraph, 2024.

[11] CrewAI. CrewAI Documentation. https://docs.crewai.com

[12] OpenAI. OpenAI Agents SDK. https://github.com/openai/openai-agents-python, 2025.

[13] Anthropic. Claude Agent SDK. https://github.com/anthropics/claude-agent-sdk-python, 2025.

[14] G. Li, H. A. A. K. Hammoud, H. Itani, D. Khizbullin, and B. Ghanem. "CAMEL: Communicative Agents for 'Mind' Exploration of Large Language Model Society." Advances in Neural Information Processing Systems 36 (NeurIPS), 2023. arXiv:2303.17760.

[15] W. Chen, Y. Su, J. Zuo, C. Yang, C. Yuan, C. Qian, C. Chan, Y. Qin, Y. Lu, R. Xie, Z. Liu, M. Sun, and J. Zhou. "AgentVerse: Facilitating Multi-Agent Collaboration and Exploring Emergent Behaviors in Agents." arXiv:2308.10848, 2023.

[16] A. Khatua, H. Zhu, P. Tran, A. Prabhudesai, F. Sadrieh, J. K. Lieberwirth, X. Yu, Y. Fu, M. J. Ryan, J. Pei, and D. Yang. "CooperBench: Why Coding Agents Cannot be Your Teammates Yet." Stanford University & SAP Labs US, 2026. https://cooperbench.com

[17] Cemri, M., Pan, M.Z., Yang, S., Agrawal, L.A., Chopra, B., Tiwari, R., Keutzer, K., Parameswaran, A., Klein, D., Ramchandran, K., Zaharia, M., Gonzalez, J.E. and Stoica, I., 2025. Why do multi-agent LLM systems fail? In: Advances in Neural Information Processing Systems 38 (NeurIPS 2025), Datasets and Benchmarks Track.

[18] Smit, A.P., Grinsztajn, N., Duckworth, P., Barrett, T.D. and Pretorius, A., 2024. Should we be going MAD? A look at multi-agent debate strategies for LLMs. In: Proceedings of the 41st International Conference on Machine Learning, PMLR 235, pp.45883–45905.

[19] Lowe, R., Wu, Y., Tamar, A., Harb, J., Abbeel, P., & Mordatch, I. (2017). Multi-agent actor-critic for mixed cooperative-competitive environments. Advances in Neural Information Processing Systems (NeurIPS), 30.

[20] Stone, P., Kaminka, G. A., Kraus, S., & Rosenschein, J. S. (2010). Ad hoc autonomous agent teams: Collaboration without pre-coordination. Proceedings of the 24th AAAI Conference on Artificial Intelligence, 1504–1509

[21] Y. Fu, R. Fang, J. Shao, H. Zheng, Z. Zhu, B. Luo, and T. Lin. "Do more agents help? Controlled and protocol-aligned evaluation of LLM agent workflows." arXiv preprint, 2026. arXiv:2606.05670.

[22] A. Vaswani, N. Shazeer, N. Parmar, J. Uszkoreit, L. Jones, A. N. Gomez, Ł. Kaiser, and I. Polosukhin. "Attention Is All You Need." Advances in Neural Information Processing Systems 30 (NeurIPS), 2017. arXiv:1706.03762.

[23] Microsoft. Microsoft Agent Framework. https://github.com/microsoft/agent-framework, 2026.