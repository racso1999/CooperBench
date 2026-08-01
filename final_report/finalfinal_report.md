# Introduction

Large language models (LLMs) are stateless predictors. When given a sequence of text, they predict the continuation, token by token. Built on the transformer architecture introduced in "Attention is all you need" [1], LLMs retain no memory from one run to the next. An AI agent is what emerges when a stateless LLM is wrapped in a loop. The agent is given tools, allowing it to execute against a real environment, and the resulting output is fed back into its context, giving it a working memory across steps. This infrastructure turns a next token predictor into a system that can persue multi-step goals such as editing files, reading a codebase and running tests.

After one has realized the benfits of a single agent, the appeal for a team of several is obvious. Multi agent systems have risen in popularity accordingly. The intuition borrows from human organisations: divide the work and let multiple workers share the load and collaborate - in theory, several agents should provide the parallelism that a single model instance cannot. Frameworks built on this premise have proliferated, from conversational multi-agent toolkits such as AutoGen [2] to software company simulations such as MetaGPT [3] and ChatDev [4] which spawn teams of agents with focused tasks such as engineers, testers and product managers.

What this intuition quietly assumes, however, is that dividing the work provides additional benefit. For code editing specifically that intuition is largely untested and the little evidence that does exist, raises some concerns. In "CooperBench: Why Coding Agents Cannot be Your Teammates Yet" [5], the authors found that solo agents solved coding tasks at substantially higher rates than their multiagent counterparts. This result is surprising, given the increased compute budget and context provided by a larger team.

To understand the issue with team scaling, one must understand two fatal flaws of communication. First of all, the re ingestion of context: sharing context with another agent means compounding the context size. Secondly, and to further compound the cost, messages may be overworded, inconclusive or incorrect. Decisions that a solo agent would make alone against a coherent whole are instead made against a fragmented many. Consequently a multi-agent system will spend more to reach the same outcome and surely no ammount of additional spending can recover the coherence a single context provides. In this paper, we refer to the compound communication overhead as the "Communication Tax".

Why then would we consider improving a system that is doomed to underperform? Ultimately, efficiency and success rate are not the only measures of value. Multi agent systems despite being less effective, may at times be more useful or perhaps neccessary. Some tasks pair agents with contrasting abilities, and in other settings, agents may be forced to work together whether or not collaboration is optimal. When they do, we want to make sure they do so to their maximum capability while paying as little of the "communication tax" as possible.

# Hypothesis

In this paper, we aim measure the commincation overhead ("Communication Tax") in multi-agent systems and, through protocol and scaling studies, quantify how changes in protocol and structure affect the tax paid. We hypothesise that multi-agent systems will typically underperform their solo-counterparts in terms of efficiency primarily due to the growing communication tax as systems scale - but that focused protocol changes can significantly reduce this gap. 

# CooperBench

"CooperBench: Why Coding Agents Cannot Be Your Teammates Yet" [5] intrdouces a comprehensive benchmarking suite that isolates communication failures in multi-agent systems. The benchmark tests whether two LLM coding agents can work in parallel on the same codebase. A paper was published alongside the benchmark with the headline finding - "The curse of coordination" - agents average ~30% lower success working together than one agent doing both tasks alone. 

In this paper we will refer to a "task" — a set of features from one real repository; a "feature" — one unit of that repositories functions, given to an agent as a natural-language spec; a "pair of features" — any two features from the same task.

CooperBench works by spinning up two isolated, containerised environments within which agents work. Each agent is given a spec, access to its own copy of the code base and a tool to message with the other agent/s. (This can be from 1, up to a whole team of agents). The agents are then tasked with individually implementing their own features. 

After the agents have finished working on their features, or the step or time cap has been reached, the features are naively merged. A naive merge is a pure textual merge: it combines changes based on the lines of code each agent modified, without any understanding of the code's structure or logic. Overlapping edits are flagged as conflicts, while non-overlapping edits are merged automatically (even if they break each other semantically). The merge is performed by CooperBench automatically, in a fresh container isolated from the agents. A clean merge is then run against both features' test suites resulting in a 'both_passed' **success** only if both suites pass. If either suite fails we record a **failure**.

# Extending the evaluation

Evaluation at post merge fails to seperate instances where an agent never solved it's feature, from one whose work didn't successfully merge. In such cases the original evaluation pipeline does not descriminate between an agents ability to code and an agents ability to write code that integrates. We fix this through with the addition pre-merge testing to CooperBench Each agent's individual feature is tested against it's own suite in isolation, in the same sandbox. We still measure post the post merge signal - the original evaluation metric. Capability and integration are therefore reported separately giving us finer granularity. 

To establish that the coordination gap report in "CooperBench: Why Coding Agents Cannot be Your Teammates Yet" reproduces, we opted to use the 50-pair flash subset of tasks. Preliminary pilot tests were run to determine a suitable model for our experiments. Problems to consider were cost, individual model capability, and token throughput. Claude Sonnet-5 was ultimately selected. The experiment was run under two conditions: a Solo condition, in which a single agent implements both features of a pair, and a Co-op condition, in which two isolated agents implement one feature each, optionally exchanging messages via the built-in "free-msg" protocol. Both conditions are run on the identical set of feature pairs - every feature pair has one Solo result and one Co-op result. This yields a matched design in which the two settings are compared within each feature pair rather than across aggregate scores, removing variance in task difficulty as a confound.

For our replication of the original study, we opted to use the same 'free-msg" protocol - the same default protocol that is both shipped with CooperBench and used in the orignal study. "CooperBench: Why Coding Agents Cannot be Your Teammates Yet" [5] The protocol, and further protocols used in this paper, are prompt level only. Each agent's instruction is a single prompt composed of three parts: (1) the feature specification; (2) the submission protocol; (3) the cooperation protocol (The section we can vary). In "free-msg" the agent is informed of it's partner, is warned of overlapping features and taught messaging commands. These commands allow the agents to message using shell commands through a Redis-backed communication channel. 

```
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

# Replicating the Curse of Coordination - The Findings

Consistent with the reported "Curse of coordination", we observe a substantial drop in task success from the solo agent to it's two agent counterpart. Across 46 matched feature pairs the average pass rate fell from 44.2% under the Solo condition to 12.3% under the Co-op condition. (See Calculation 1 in the appendix). This finding replicates those of the original study, in which Co-op performance is substantially lower than Solo performance. Recall "agents average ~30% lower success working together than one agent doing both tasks alone." [5]

In the Co-op condition, both agents' independent work passed their own test suites in 62 of 138 runs (44.9%) — statistically indistinguishable from the 61 of 138 runs (44.2%) passed by the Solo condition. Splitting the work across agents therefore causes no measurable loss of individual capability. The gap instead arises at patch integration. The agents consistently write working code but cannot place their edits so that contributions cleanly merge with other agents' work.

# Replicating the Curse of Coordination - Accounting for Cost

"CooperBench: Why Coding Agents Cannot Be Your Teammates Yet" [5] as well as our replication demonstrate a clear coordination gap in teams of agents. Earlier we hypothesized that not only would solo agents be more successful, we also hypothesized they were likely to be more efficient. In order to investigate this hypothesis, we normalise the results of our replication study for the cost of achieveing a given outcome. We use total dollar cost, aggreagting input, output and cache read/write tokens into a single measurable figure as a proxy for computational efffort. The cost is taken directly from total_cost_usd field of the Claude Code CLI's terminating result event and cost calculated using Anthropic's published API list prices. [see appendix]

Across the same 46 matched feature pairs, the Solo condition achieved 0.675 passes per dollar spent, compared to 0.107 passes per dollar under the Co-op condition — a roughly 6.3-fold gap, versus the 3.6-fold gap observed in raw pass rate alone. A paired Wilcoxon signed-rank test on per-pair cost efficiency confirms this difference is statistically significant (W = 2.0, p < .001). This widening indicates that the coordination penalty is not limited to lower success rates: Co-op runs are also less cost-efficient per successful outcome, compounding the disadvantage relative to Solo.

When adjusting for compute, the gap grows substantially. Across the same 46 features pairs, the Solo condition averages 0.675 passes (both_passed) per dollar spent, compared to 0.107 passes per dollar from the Co-op condition. That's a 6.29-fold gap versus the original 3.59-fold gap calculated using pass rate alone. A paired Wilcoxon signed-rank test on per-pair cost efficiency confirms this difference is statistically significant (W=2.0, p < .001).