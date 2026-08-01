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

**Pre-merge capability (our extension).** Merge-first evaluation cannot separate an agent that never solved its feature from one whose work the merge destroyed. We add a pre-merge pass: each agent's patch against its own suite, in isolation, in the same sandbox, enabled by default. We also still measure post-merger - the original evaluation metric. Capability and integration are therefore reported separately giving us finer granularity - so a failed pair can be attributed to an agent's inability to write the code, or to the team's inability to write code that composes.


# Replicating the Curse of Coordination

To establish that the coordination gap report in "CooperBench: Why Coding Agents Cannot be Your Teammates Yet" reproduces, we opted to use the 50-pair flash subset of tasks. 

Preliminary pilot tests were run to determine a suitable model for our experiments. Problems to consider were cost, individual model capability, and token throughput. Claude Sonnet-5 was ultimately selected.

The experiment was run under two conditions: a solo condition, in which a single agent implements both features of a pair, and a cooperative condition, in which two isolated agents implement one feature each, optionally exchanging messages via the built-in "free-msg" protocol. Both conditions are run on the identical set of feature pairs - every feature pair has one solo result and one cooperative result. This yields a matched design in which the two settings are compared within each feature pair rather than across aggregate scores, removing variance in task difficulty as a confound.

For our replication we use the "free-msg" protocol - the same default protocol shipped with CooperBench and used in the original study. The protocol is prompt-level only but uses a Redis backed communication channel that fascilitates a messaging tool accessible by each Agent. Each agent's instruction is a single prompt composed of three parts: (1) the feature specification; (2) a submission protocol instructing the agent to write its final unified diff to `patch.txt` before exiting; and (3) a cooperation protocol block that names the partner, warns that features may overlap, and documents the messaging commands. "Free" refers to the message content - unconstrained plain text, with no required fields. The cooperation block is reproduced verbatim below (as rendered for agent1).

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

