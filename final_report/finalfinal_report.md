# Introduction

Large language models (LLMs) are stateless predictors. When given a sequence of text, they predict the continuation, token by token. Built on the transformer architecture introduced in "Attention is all you need" [1], LLMs retain no memory from one run to the next. An AI agent is what emerges when a stateless LLM is wrapped in a loop. The agent is given tools, allowing it to execute against a real environment. The resulting output is fed back into its context, giving it a working memory across steps. This infrastructure turns a next token predictor into a system that can persue multi-step goals such as editing files, reading a codebase [16], surfing the internet [17] or managing databases [18].

After one has realized the benfits of a single agent, the appeal for a team of several is obvious. Multi agent systems have risen in popularity accordingly. The intuition borrows from human organisations: divide the work and let multiple workers share the load and collaborate: in theory, several agents should provide the parallelism that a single model instance cannot. Frameworks built on this premise have proliferated, from conversational multi-agent toolkits such as AutoGen [2] to software company simulations such as MetaGPT [3] and ChatDev [4] which spawn teams of agents with focused tasks such as engineers, testers and product managers.

Popular frameworks for orchestrating these agents have risen in popularity alongside them, and they differ mainly in how coordination is expressed. Google's Agent Development Kit (ADK) [7] arranges agents into a hierarchical tree, while LangChain [8] and its graph-based successor LangGraph [9] provide infrastructure for building complex multi-agent systems with explicit state management. CrewAI [10] assigns agents named roles within a "crew", closely mirroring the divide-the-work intuition described above. The OpenAI Agents SDK [11] instead coordinates through explicit handoffs, and the Claude Agent SDK [12] through delegation to sub-agents. AutoGen [2] has since been absorbed into the Microsoft Agent Framework [13]. Parallel to these engineering efforts, a research line has studied agent collaboration directly, including CAMEL [14] on role-playing communication and AgentVerse [15] on emergent behaviour in agent groups.

What this intuition quietly assumes, however, is that dividing the work provides additional benefit. For software engineering specifically that intuition is largely untested and the little evidence that does exist, raises some concerns. In "CooperBench: Why Coding Agents Cannot be Your Teammates Yet" [5], the authors found that solo agents solved coding tasks at substantially higher rates than their multiagent counterparts. This result is surprising, given the increased compute budget and context provided by a larger team.

Similarly, Cemri et al. (2025) observe that despite growing enthusiasm for multi-agent systems, their performance gains across popular benchmarks remain minimal when compared to single-agent frameworks. The authors analyse over 200 tasks across seven popular multi-agent frameworks and identify fourteen recurring failure modes. The failures demonstrate structural consequences of coordination, suggesting that the overhead introduced by dividing work between agents can actively erode the capability of the underlying model. Comparable findings emerge even in the narrower setting of multi-agent debate, one of the most widely adopted collaboration patterns. Smit et al. (2024) benchmark a range of debate protocols against single-model prompting strategies and find that debating systems, in their current form, do not reliably outperform simpler alternatives such as self-consistency, despite incurring considerably greater cost in tokens and latency; where debate protocols did recover performance, it was only after careful hyperparameter tuning, indicating fragility rather than robust benefit.

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

# Replicating the Curse of Coordination

To establish that the coordination gap report in "CooperBench: Why Coding Agents Cannot be Your Teammates Yet" reproduces, we opted to use the 50-pair flash subset of tasks. Preliminary pilot tests were run to determine a suitable model for our experiments. Problems to consider were cost, individual model capability, and token throughput. Claude Sonnet-5 was ultimately selected. The experiment was run under two conditions: a Solo condition, in which a single agent implements both features of a pair, and a Co-op condition, in which two isolated agents implement one feature each, optionally exchanging messages via the built-in "free-msg" protocol. Both conditions are run on the identical set of feature pairs - every feature pair has one Solo result and one Co-op result. This yields a matched design in which the two settings are compared within each feature pair rather than across aggregate scores, removing variance in task difficulty as a confound.

For our replication of the original study, we opted to use the same 'free-msg" protocol - the same default protocol that is both shipped with CooperBench and used in the orignal study. "CooperBench: Why Coding Agents Cannot be Your Teammates Yet" [5] The protocol, and further protocols used in this paper, are prompt level only. Each agent's instruction is a single prompt composed of three parts: (1) the feature specification; (2) the submission protocol; (3) the cooperation protocol (The section we can vary). In "free-msg" the agent is informed of it's partner, is warned of overlapping features and taught messaging commands. These commands allow the agents to message using shell commands through a Redis-backed communication channel.

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

Consistent with the reported "Curse of coordination", we observe a substantial drop in task success from the solo agent to it's two agent counterpart. Across 46 matched feature pairs the average pass rate fell from 44.2% under the Solo condition to 12.3% under the Co-op condition. (See Calculation 1 in the appendix). This finding replicates those of the original study, in which Co-op performance is substantially lower than Solo performance. Recall "agents average ~30% lower success working together than one agent doing both tasks alone." [5]

In the Co-op condition, both agents' independent work passed their own test suites in 62 of 138 runs (44.9%) — statistically indistinguishable from the 61 of 138 runs (44.2%) passed by the Solo condition. Splitting the work across agents therefore causes no measurable loss of individual capability. The gap instead arises at patch integration. The agents consistently write working code but cannot place their edits so that contributions cleanly merge with other agents' work.

## Replicating the Curse of Coordination - Accounting for Cost

"CooperBench: Why Coding Agents Cannot Be Your Teammates Yet" [5] as well as our replication demonstrate a clear coordination gap in teams of agents. Earlier we hypothesized that not only would solo agents be more successful, we also hypothesized they were likely to be more efficient. In order to investigate this hypothesis, we normalise the results of our replication study for the cost of achieveing a given outcome. We use total dollar cost, aggreagting input, output and cache read/write tokens into a single measurable figure as a proxy for computational efffort. The cost is taken directly from total_cost_usd field of the Claude Code CLI's terminating result event and cost calculated using Anthropic's published API list prices. [see appendix]

Across the same 46 matched feature pairs, the Solo condition achieved 0.675 passes per dollar spent, compared to 0.107 passes per dollar under the Co-op condition — a 6.3-fold gap, versus the 3.6-fold gap observed in raw pass rate alone. A paired Wilcoxon signed-rank test on per-pair cost efficiency confirms this difference is statistically significant (W = 2.0, p < .001). This widening indicates that the coordination penalty is not limited to lower success rates: Co-op runs are also less cost-efficient per successful outcome, compounding the disadvantage relative to Solo.

When adjusting for compute, the gap grows substantially. Across the same 46 features pairs, the Solo condition averages 0.675 passes (both_passed) per dollar spent, compared to 0.107 passes per dollar from the Co-op condition. That's a 6.29-fold gap versus the original 3.59-fold gap calculated using pass rate alone. A paired Wilcoxon signed-rank test on per-pair cost efficiency confirms this difference is statistically significant (W=2.0, p < .001).

# Bridging the Gap - Reducing Communication Overhead with Focused Prompts

Our replication successfully reproduced the "coordination gap" and further localised it to patch-integration failures: paired agents write working code, but fail to write code that integrates cleanly at the merge. This raises a direct question, can the coordination protocol itself close the gap? To investigate, we ran a comparison of six cooperation protocols. Each protocol comprises the cooperation block of the agent's prompt and, in the structured arms, the message-field validation the container enforces. \footnote

**Adjusting the dataset.** To sharpen the signal and reduce token wastage, we screened the full feature set shipped with CooperBench for pairs that are both highly conflicting and solvable by a single Claude Sonnet 5 agent. The resulting capability-screened dataset consists of 20 feature pairs. \footnote

## Bridging the Gap - The Protocols

The six arms span from interventions

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
