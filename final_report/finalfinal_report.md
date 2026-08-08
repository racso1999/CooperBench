# Introduction

Large language models (LLMs), when given a sequence of text, predict the continuation token by token. LLMs retain no memory from one run to the next - they are stateless. An AI agent is what emerges when a LLM is wrapped in a loop - given a "harness". The agent is provided with access to tools, allowing it to execute against a real environment. The resulting output is fed back into into the agent's context, giving it a working memory across steps - a state. This infrastructure turns a next token predictor into a system that can persue multi-step goals such as editing files and reading a codebase [16], surfing the internet [17] or managing databases [18].

The concept of a multi agent system itself is not novel; discussion of such systems goes as far back as the late 1970s, and can be seen in Hewitt's model of intelligence as a "society" of communicating problem-solving experts (Artificial Intelligence, 1977) [21]. For the sake of simplicity, in this paper, we will always be referring to an LLM based agent.

After one has realized the benfits of a single agent, the appeal for a team of several is obvious. Multi agent systems have risen in popularity accordingly. The intuition borrows from human organisations: divide the work and let multiple workers share the load and collaborate: in theory, several agents should provide the parallelism that a single model instance cannot. Frameworks built on this premise have proliferated, from conversational multi-agent toolkits such as AutoGen [2] to software company simulations such as MetaGPT [3] and ChatDev [4] which spawn teams of agents with focused tasks such as engineers, testers and product managers.

Popular frameworks for orchestrating these agents have risen in popularity alongside them, and they differ mainly in how coordination is expressed. Google's Agent Development Kit (ADK) [7] arranges agents into a hierarchical tree, while LangChain [8] and its graph-based successor LangGraph [9] provide infrastructure for building complex multi-agent systems with explicit state management. CrewAI [10] assigns agents named roles within a "crew", closely mirroring the divide-the-work intuition described above. The OpenAI Agents SDK [11] instead coordinates through explicit handoffs, and the Claude Agent SDK [12] through delegation to sub-agents. Parallel to these engineering efforts, a research line has studied agent collaboration directly, including CAMEL [14] on role-playing communication and AgentVerse [15] on emergent behaviour in agent groups.

Each of these, however, rely on the same intuition - dividing the work provides additional benefit. In "CooperBench: Why Coding Agents Cannot be Your Teammates Yet" [5], Khatua et al. found that solo agents solved coding tasks at substantially higher rates than their multiagent counterparts. "The curse of coordination" suggests agents average ~30% lower success working together than one agent doing both tasks alone. Similarly, Cemri et al. (2025) observe that multi-agent systems performance gains, across popular benchmarks, remain minimal when compared to single-agent frameworks. The authors analyse over 200 tasks across seven popular multi-agent frameworks and identify fourteen recurring failure modes. The failures demonstrate structural consequences of coordination, suggesting that the overhead introduced by dividing work between agents can actively erode the capability of the underlying model. [19] Comparable findings emerge even in the narrower setting of multi-agent debate, one of the most widely adopted collaboration patterns. Smit et al. (2024) benchmark a range of debate protocols against single-model prompting strategies and find that debating systems, in their current form, do not reliably outperform simpler alternatives such as self-consistency, despite incurring considerably greater cost in tokens and latency. Where debate protocols did recover performance, it was only after careful hyperparameter tuning [20].

To understand the cost of team scaling, one must consider two fundamental properties of communication. Firstly, the re ingestion of context: sharing information with another agent means compounding the context size. Secondly, and to further compound, messages may be overworded, inconclusive or incorrect. Decisions that a solo agent would make alone against a coherent whole are instead made against a fragmented many. Consequently a multi-agent system will often spend more to reach the same outcome and surely no ammount of additional tuning or structural design can recover the coherence a single context provides. In this paper, we refer to the compound communication overhead as the "Communication Tax".

Why then would we consider improving a system that is doomed to underperform? Ultimately, efficiency and success rate are not the only measures of value. Multi agent systems despite being less effective, may at times be more useful or perhaps neccessary. Some tasks pair agents with contrasting abilities, and in other settings, agents may be forced to work together whether or not collaboration is optimal. When they do, we want to make sure they do so to their maximum capability while paying as little of the "communication tax" as possible.

# Hypothesis

In this paper, we aim measure the commincation overhead ("Communication Tax") in multi-agent systems and, through protocol and scaling studies, quantify how changes in protocol and structure affect the tax paid. We hypothesise that multi-agent systems will typically underperform their solo-counterparts in terms of efficiency primarily due to the growing communication tax as systems scale - but that focused protocol changes can significantly reduce this gap.

** In this paper we will refer to a "task" — a set of features from one real repository; a "feature" — one unit of that repositories functions, given to an agent as a natural-language spec; a "pair of features" — any two features from the same task. **

## Replicating the Curse of Coordination

 In "CooperBench: Why Coding Agents Cannot be Your Teammates Yet", Khatua et al. introduce a comprehensive benchmarking suite that isolates communication failures in multi-agent systems, testing whether two LLM coding agents can work in parallel on the same codebase. CooperBench works by sequentially running two isolated, containerised environments within which agents can work. Each agent is given a spec, access to its own copy of the codebase, and a tool for messaging other agents (from one up to a whole team). The agents can also read files and edit code. They are then tasked with individually implementing their own features.

After the agents have finished working on their features, or the step or time cap has been reached, the features are naively merged. A naive merge is a pure textual merge: it combines changes based on the lines of code each agent modified, without any understanding of the code's structure or logic. Overlapping edits are flagged as conflicts, while non-overlapping edits are merged automatically (even if they break each other semantically). The merge is performed by CooperBench automatically, in a fresh container isolated from the agents. A clean merge is then run against both features' test suites resulting in a 'both_passed' **success** only if both suites pass. If either suite fails we record a **failure**.

# Replicating the Curse of Coordination - Extending the Evaluation

Evaluation at post merge fails to seperate instances where an agent never solved it's feature, from one whose work didn't successfully merge. In such cases the original evaluation pipeline does not descriminate between an agents ability to code and an agents ability to write code that integrates. We fix this with the addition of pre-merge function testing. Each agent's individual feature is tested against it's own suite in isolation prior to merging with the other agents. Capability and integration are therefore reported separately giving us finer granularity.

# Replicating the Curse of Coordination - Methodology

To establish that the coordination gap report in "CooperBench: Why Coding Agents Cannot be Your Teammates Yet" reproduces, we opted to use the 50-pair flash subset of tasks. Preliminary pilot tests were run to determine a suitable model. Factors to consider were cost, individual model capability, and token throughput. Claude Sonnet-5 was ultimately selected. The experiment was run under two conditions: a Solo condition, in which a single agent implements both features of a pair, and a Co-op condition, in which two isolated agents implement one feature each, optionally exchanging messages a Redis backed communication channel. /footnote. Both conditions are run on the identical set of feature pairs - every feature pair has one Solo result and one Co-op result. This yields a matched design in which the two settings are compared within each feature pair rather than across aggregate scores, removing variance in task difficulty as a confound.

For our replication of the original study, we opted to use the same 'free-msg" protocol - the same default protocol that is both shipped with CooperBench and used in the orignal study. The protocol, and further protocols used in this paper, are prompt level only. Each agent's instruction is a single prompt composed of three parts: (1) the feature specification; (2) the submission protocol; (3) the cooperation protocol (The section we can vary). In "free-msg" the agent is informed of it's partner, is warned of overlapping features and taught messaging commands. These commands allow the agents to message using shell commands through a Redis-backed communication channel. \footnote

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

Consistent with the reported "Curse of coordination", we observe a substantial drop in task success from the solo agent to it's two agent counterpart. Across 46 matched feature pairs the average pass rate fell from 44.2% under the Solo condition to 12.3% under the Co-op condition. \footnote (See Calculation 1 in the appendix). This finding replicates those of the original study, in which Co-op performance is substantially lower than Solo performance. Recall "agents average ~30% lower success working together than one agent doing both tasks alone." [5]

In the Co-op condition, both agents' independent work passed their own test suites in 62 of 138 runs (44.9%) — statistically indistinguishable from the 61 of 138 runs (44.2%) passed by the Solo condition. Splitting the work across agents therefore causes no measurable loss of individual capability. The gap instead arises at patch integration. The agents consistently write working code but cannot place their edits so that contributions cleanly merge with other agents' work.

## Replicating the Curse of Coordination - Accounting for Cost

"CooperBench: Why Coding Agents Cannot Be Your Teammates Yet" [5], as well as our replication, demonstrate a clear coordination gap in teams of agents. Earlier we hypothesized that not only would solo agents be more successful, wbut that they would be more efficient. To investigate this secion of the hypothesis, we normalise the results of our replication study for the cost of achieveing a given outcome. We use total dollar cost, aggregating input, output and cache read/write tokens into a single measurable figure as a proxy for computational effort. The cost is taken directly from total_cost_usd field of the Claude Code CLI's terminating result event and cost calculated using Anthropic's published API list prices. \footnote [see appendix]

Across the same 46 matched feature pairs, the Solo condition achieves 0.675 passes per dollar spent, compared to 0.107 passes per dollar under the Co-op condition — a 6.3-fold gap, versus the 3.6-fold gap observed in raw pass rate alone. A paired Wilcoxon signed-rank test on per-pair cost efficiency confirms this difference is statistically significant (W = 2.0, p < .001). This widening indicates that the coordination penalty is not limited to lower success rates: Co-op runs are also less cost-efficient per successful outcome, compounding the disadvantage relative to Solo.

\figure [cooperbench replication]


## Scaling The Team - Too Many Cooks

Here's the full passage with the new closing paragraph appended:

---

In "Do more agents help? Controlled and protocol-aligned evaluation of LLM agent workflows." [6], Fu et al. find that most multi-agent workflows fail to reliably outperform a matched single-agent baseline once evaluation infrastructure is controlled. They attribute the overall performance to task-protocol fit rather than the number of agents. Their comparison, however, never directly varies agent count independently of communication protocol, prompt, and topology.

Similarly, as shown in CooperBench (Khatua et al., 2026), coordination performance degrades sharply as the number of cooperating agents increases. In a controlled experiment scaling from 2 to 4 concurrently cooperating agents on 46 tasks drawn from 3 task sets, success rates declined monotonically: from 68.6% with 2 agents, to 46.5% with 3 agents, to 30.0% with 4 agents. This trend reinforces the "curse of coordination" observed in the two-agent setting, suggesting that adding more agents to a shared workspace compounds rather than alleviates coordination difficulty.

Again however, their experiment fails to isolate the number of agents and varies two things at once. Agent count is set to the number of features assigned, so a three- or four-agent run carries three or four features — the decline confounds coordination overhead with a workload that has grown.

We therefore built PoolBench - an extension to CooperBench. \footnote[poolbench] In PoolBench, the workload is arranged into "Pools" comprised of a K-feature clique. Each individual pool may be solved by any number of agents N ∈ {1,2,3,4,...,K}, allowing us to fix the workload and vary only N. All N agents work against one git remote seeded at the feature pool's base commit. Each agent implements its own features, fetches and merges its peers' branches, resolves any conflicts, and rebuilds the patch. Integration is therefore part of the agents' coordination work. The evaluator scores the single integrated tree against each feature's test suite.

To measure where how the coordination overhead is comprised, we cost each run at the dollar level. Every reported cost is Claude Code CLI's own billed `total_cost_usd`, summed across agents, and apportioned into four accounts: context, communication, rework, and task. We do so by reconstructing each agent's per-turn history from the harness'  execution stream and weighting each account by its token-type list price, so the four figures sum exactly to the run's cost. 



## Scaling The Team - Experimental Design

The independant variable is N; the constant is the K-feature pool. The pool of features is split across the agents using a round robin distribution as default. Every pool is solo screened (Every pool must be solvable by the solo agent) so that performance losses at higher N can be contributed to coordination cost rather than raw pool difficulty. Primarily we measure a graded score; the fraction of K feature test-suites that pass on the integrated tree, allowing us to credit partially correct teams (3/4 features = 0.75). The final dataset consists of 14 pools across 6 repositories and 148 total runs using Claude Sonnet 5 (~$410 API-equivalent cost).


\diagram [pool bench]


## Results: Efficiency Collapses

Efficiency - the fraction of the workload solved per dollar spent.

\Table 3 Efficiency by agent Count N, averaged over all pools.

As the number of agents grows, the work solved per dollar collapses, falling as a power law in agent count. Efficiency (cost.run) =  1.28N^-1.61, reaching ~10% of the solo value at four agents (Figure 3). The relationship is universal: fitting each pool seperately, all fourteen collapse as power laws with exponents between 1.1 and 2.3. The exponent exceeding 1 across all pools is the substantive point: if dividing the work simply gave each agent a fixed share at a fixed per-agent cost, efficiency would fall as 1/N (ro = 1). The observed (ro = 1.8) means that each added agent is super-proportionally wasteful. 

The coordination tax grows faster than the team grows. This is true even for pools where the correctness never degrades: pallets_jinja/1621 integrates perfectly at every N, yet the efficiency falls 1.07 -> 0.15, a 7x loss. The Communication Tax therefore does not require a coordination failure. In this instance, it is the price of coordination itself.

 ## Correctness

Correctness falls more gradually and less universally. The graded score, averaged over all fourteen pools, declines from 0.96 to 0.91 to 0.89 as agent count increases from one to three. Similarly, the strict all-pass rate (the probability the team ships a fully correct integration) falls monotonically from 89% to 82% to 77% to 69% across one to four agents (Figure 4). The degradation is concentrated in the hardest repository, dspy: all four of its cliques degrade (e.g. 0.75 → 0.42 and 0.92 → 0.75), while eight of the fourteen pools integrate cleanly and remain near 1.0.

/figure 4

## Cost

Cost rises on every pool. It increases from $0.78 for a solo run to $7.21 at four agents for the same K features (Figure 5). Decomposing cost into four accounts shows redundant context ingestion grows roughly linearly (Figure 6): $0.50, $0.92, $1.47, $2.27. Per-agent, work inflates super-linearly ($0.27 to $2.37). Each agent does more work, as the team grows. Coordination adds an extra cost on top of that.

The messaging channel, measured as tokens sent, received, and re-ingested, accounts for 23–25% of every multi-agent run. Messaging also provokes rework, meaning files are re-edited in response to inbound messages. When that message-triggered rework is included, the messaging-related share rises to 31–36% ($0.48 communication + $0.16 rework at N = 2, rising to $1.82 + $0.75 at N = 4).

/figure 5, figure 6

# A Supervisor is all They need

Dividing a workload a single agent can already complete buys no correctness: the strict all-pass rate falls from 89% to 69% as the team scales. Each agent does more work, with per-agent task cost rising from $0.27 solo to $2.37 at four agents. In a parallel execution space, the allocation of features is fixed before any agent runs, and no single agent is responsible for governing the pool of tasks — so each reconstructs the shared picture privately and then reconciles it with its peers. Making one supervisor agent responsible for the division of labour, and for the final assembly of features, replaces a decision the peers negotiate collectively with a single, focused decision node.

If the tax we have measured is coordination based, centralising it should reduce the price. If the tax is intrinsic to purely dividing work, it will not help. 

## A Supervisor is all They need - Design

The apparatus, workload, and evaluation are held fixed at the values used in Section 5: the same 14 solo-screened clique-pools, shared git remote and the same graded scoring of one integrated tree against all K held-out suites.

The only change is the architecture. In the supervised arm, a leader agent (Claude Opus 5) is the only participant that receives the K feature specifications. It writes a decomposition plan. It materialises each specification into a shared scratchpad and assigns features to workers (Claude Sonnet 5) through a shared task list. It monitors progress. It is the designated integrator whose tree the benchmark scores. Workers begin with no specification at all. They implement only what they are assigned. The round-robin partition — a fixed, benchmark-imposed allocation in the flat arm — is thus replaced by an allocation the leader chooses.

Across 148 runs the leader delegated 3.2 features on average and kept 0.3, and it never once kept the whole workload for itself. Above one worker it delegated everything in all but two of 104 runs. Only at a single worker, where there is little to supervise, does it routinely implement a feature itself (it kept one in 29 of 44 such runs). 

The communication channel is deliberately not among the things that change: as in the flat arm, every container receives the full team roster and can address any other participant directly. Workers therefore retain the ability to message one another rather than routing through the leader. The hierarchy is a property of the prompt, not of the infrastructure — a topology the agents are free to defect from at any point - allowing us to remove messaging infrastructure as a confound.


Because the leader is a real agent consuming real tokens and real time, a supervised run with N
workers is reported at N + 1 agents. This is what makes the arms comparable: “four agents” means
four peers in the flat arm and one supervisor plus three workers in the supervised arm. Reporting the
supervised arm at worker-count would conceal the cost of supervision, which is the quantity under
test. The dataset is 148 supervised runs (∼$721 list-price-equivalent) against the 148 flat runs of the
scaling study — a complete matched design. Coverage differs by construction: the flat arm spans
1–4 agents and the supervised arm 2–5 (a leader with zero workers is not a team), so only 2–4 agents
are directly comparable, and the endpoints of each curve — the 4-agent flat and 5-agent supervised
columns — rest on the six K = 4 pools alone.


# References

[1] A. Vaswani, N. Shazeer, N. Parmar, J. Uszkoreit, L. Jones, A. N. Gomez, Ł. Kaiser, and I. Polosukhin. "Attention Is All You Need." Advances in Neural Information Processing Systems 30 (NeurIPS), 2017. arXiv:1706.03762.

[2] Q. Wu, G. Bansal, J. Zhang, Y. Wu, B. Li, E. Zhu, L. Jiang, X. Zhang, S. Zhang, J. Liu, A. H. Awadallah, R. W. White, D. Burger, and C. Wang. "AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation." 2023. arXiv:2308.08155.

[3] S. Hong, X. Zheng, J. Chen, Y. Cheng, J. Wang, C. Zhang, Z. Wang, S. K. S. Yau, Z. Lin, L. Zhou, C. Ran, L. Xiao, C. Wu, and J. Schmidhuber. "MetaGPT: Meta Programming for a Multi-Agent Collaborative Framework." 2023. arXiv:2308.00352.

[4] C. Qian, W. Liu, H. Liu, N. Chen, Y. Dang, J. Li, C. Yang, W. Chen, Y. Su, X. Cong, J. Xu, D. Li, Z. Liu, and M. Sun. "ChatDev: Communicative Agents for Software Development." Proceedings of the 62nd Annual Meeting of the Association for Computational Linguistics (ACL), 2024. arXiv:2307.07924.

[5] A. Khatua, H. Zhu, P. Tran, A. Prabhudesai, F. Sadrieh, J. K. Lieberwirth, X. Yu, Y. Fu, M. J. Ryan, J. Pei, and D. Yang. "CooperBench: Why Coding Agents Cannot be Your Teammates Yet." Stanford University & SAP Labs US, 2026. https://cooperbench.com

[6] Y. Fu, R. Fang, J. Shao, H. Zheng, Z. Zhu, B. Luo, and T. Lin. "Do more agents help? Controlled and protocol-aligned evaluation of LLM agent workflows." arXiv preprint, 2026. arXiv:2606.05670.

[7] Google. Agent Development Kit (ADK). https://github.com/google/adk-python, 2025.

[8] H. Chase. LangChain. https://github.com/langchain-ai/langchain, 2022.

[9] LangChain. LangGraph. https://github.com/langchain-ai/langgraph, 2024.

[10] CrewAI. CrewAI Documentation. https://docs.crewai.com

[11] OpenAI. OpenAI Agents SDK. https://github.com/openai/openai-agents-python, 2025.

[12] Anthropic. Claude Agent SDK. https://github.com/anthropics/claude-agent-sdk-python, 2025.

[13] Microsoft. Microsoft Agent Framework. https://github.com/microsoft/agent-framework, 2026.

[14] G. Li, H. A. A. K. Hammoud, H. Itani, D. Khizbullin, and B. Ghanem. "CAMEL: Communicative Agents for 'Mind' Exploration of Large Language Model Society." Advances in Neural Information Processing Systems 36 (NeurIPS), 2023. arXiv:2303.17760.

[15] W. Chen, Y. Su, J. Zuo, C. Yang, C. Yuan, C. Qian, C. Chan, Y. Qin, Y. Lu, R. Xie, Z. Liu, M. Sun, and J. Zhou. "AgentVerse: Facilitating Multi-Agent Collaboration and Exploring Emergent Behaviors in Agents." arXiv:2308.10848, 2023.

[16] Yang, J., Jimenez, C.E., Wettig, A., Lieret, K., Yao, S., Narasimhan, K. and Press, O. (2024) 'SWE-agent: agent-computer interfaces enable automated software engineering', Advances in Neural Information Processing Systems, 37.

[17] Yao, S., Chen, H., Yang, J. and Narasimhan, K. (2022) 'WebShop: towards scalable real-world web interaction with grounded language agents', Advances in Neural Information Processing Systems, 35.

[18] Pourreza, M. and Rafiei, D. (2023) 'DIN-SQL: decomposed in-context learning of text-to-SQL with self-correction', Advances in Neural Information Processing Systems, 36.

[19] Cemri, M., Pan, M.Z., Yang, S., Agrawal, L.A., Chopra, B., Tiwari, R., Keutzer, K., Parameswaran, A., Klein, D., Ramchandran, K., Zaharia, M., Gonzalez, J.E. and Stoica, I., 2025. Why do multi-agent LLM systems fail? In: Advances in Neural Information Processing Systems 38 (NeurIPS 2025), Datasets and Benchmarks Track.

[20] Smit, A.P., Grinsztajn, N., Duckworth, P., Barrett, T.D. and Pretorius, A., 2024. Should we be going MAD? A look at multi-agent debate strategies for LLMs. In: Proceedings of the 41st International Conference on Machine Learning, PMLR 235, pp.45883–45905.

[21] Smith, R. G. (1980). The Contract Net Protocol: High-level communication and control in a distributed problem solver. IEEE Transactions on Computers, C-29(12), 1104–1113. doi:10.1109/TC.1980.1675516
