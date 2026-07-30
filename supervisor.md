# Study 3: Does a Supervisor Scale Better Than Peers?

*Companion to `paper.md`, which it extends: the apparatus, the 14 solo-screened
clique-pools, the graded score, and Studies 1–2 are defined there. Analysis package:
`masters_thesis/leader_analysis/`.*

Every result above concerns one coordination topology: N *peers*, each handed a slice of the workload up front, negotiating integration among themselves. That topology is the one the multi-agent literature most often assumes, but it is not the only one available. The obvious alternative is hierarchy — put one agent in charge of deciding who does what, and of assembling the result. If the tax we have measured is the price of *mutual* coordination, centralising it should reduce that price; if the tax is intrinsic to dividing interdependent work at all, hierarchy will not help. This study runs the comparison directly.

## Design

The apparatus, workload, and evaluation are held fixed at the values used above — the same 14 solo-screened clique-pools, the same N levels, the same trial counts, the same shared git remote, the same graded scoring of one integrated tree against all K held-out suites. Exactly one thing changes: **who decides the division of labour**.

In the **supervised** arm, a leader agent (Claude Opus 5) is the only participant that receives the K feature specifications. It writes a decomposition plan, materialises each specification into a shared scratchpad, assigns features to workers (Claude Sonnet 5) through a shared task list, monitors progress, and performs the integration itself. Workers begin with no specification at all and implement only what they are assigned. The round-robin partition — a fixed, benchmark-imposed allocation in the flat arm — is thus replaced by an allocation the leader chooses. Its choices are recorded: across 148 runs the leader delegated 3.2 features on average and kept 0.3, and it never once kept the whole workload for itself. Above one worker it delegated *everything* in all but two of 104 runs, so this is genuine supervision rather than a leader quietly doing the work alone; only at a single worker — where there is little to supervise — does it routinely implement a feature itself (it kept one in 29 of 44 such runs).

Because the leader is a real agent consuming real tokens and real time, a supervised run with N workers is reported at **N + 1 agents**. This is what makes the arms comparable: "four agents" means four peers in the flat arm and one supervisor plus three workers in the supervised arm. Reporting the supervised arm at worker-count would conceal the cost of supervision, which is the quantity under test. The dataset is 148 supervised runs (~$721 list-price-equivalent) against the 148 flat runs already described — a complete matched design.

## Results: Supervision Changes the Exponent, Not the Level

The supervised topology is *not* cheaper. At small team sizes it is markedly more expensive: paired within pools, a supervised run costs 43% more than a flat run of the same total size at two agents, and 12% more at three. What changes is not the level of the coordination penalty but its **scaling**.

| agents | flat score | flat \$ | flat solved/\$ | supervised score | supervised \$ | supervised solved/\$ |
|---|---|---|---|---|---|---|
| 1 | 0.96 | $0.78 | 1.24 | — | — | — |
| 2 | 0.91 | $2.10 | 0.43 | 0.88 | $3.01 | 0.29 |
| 3 | 0.89 | $3.82 | 0.23 | 0.87 | $4.23 | 0.21 |
| 4 | 0.92 | $7.21 | 0.13 | 0.87 | $5.81 | 0.15 |
| 5 | — | — | — | 0.97 | $9.16 | 0.11 |

Both topologies collapse as power laws in team size, but with materially different exponents: flat peers at efficiency = 1.28·N^−1.61 (R² = 0.996), supervision at 0.65·N^−1.09 (R² = 0.982) (Figure 3a). The exponent is the result, and its interpretation is sharp. For a fixed workload divided among N agents at fixed per-agent cost, efficiency *must* fall as 1/N — one is paying N agents to do one pool's work — so **b = 1 is the floor**, the value at which coordination itself costs nothing extra. The flat arm's b = 1.61 is the super-proportional waste reported above. Supervision's b = 1.09 sits almost exactly at the floor: it very nearly eliminates the *scaling* component of the coordination tax, leaving little beyond the unavoidable cost of employing more agents.

Because supervision starts lower — it pays a fixed overhead that is dead weight on a small team — but decays more slowly, the two curves cross at approximately **3.7 agents**. Below the crossover the supervisor's overhead dominates; above it, the peers' superlinear renegotiation cost does. The cost accounts locate the mechanism (Figure 3c): the messaging-related tax (comm + rework) is consistently *smaller* under supervision — 21% versus 31% of the run at two agents, 21% versus 32% at three, 25% versus 36% at four — while the context and task accounts grow similarly in both arms. Supervision does not reduce the message-independent floor; each agent still re-loads the shared repository. It reduces the part that *scales*, because workers coordinate with one supervisor rather than with every peer. The supervisor's own share of run cost falls from 61% at two agents to 32% at five, which is the same fixed-overhead-amortised-over-a-larger-team story seen from the other side.

## Correctness: Opposite Directions, and a Different Failure Mode

The more striking result is qualitative. On the strict all-pass rate — the probability the team ships a fully-correct integration — the two topologies move in **opposite directions** as the team grows (Figure 3b). Flat peers degrade monotonically across one to four agents: 89%, 82%, 77%, 69%. Supervision improves across the two to five agents it spans: 77%, 80%, 84%, 88%. The curves cross between two and three agents, and at four agents — the largest size both arms reach — the ordering has reversed decisively, 84% supervised against 69% flat.

The mechanism is visible in the distribution of outcomes rather than in their mean. Flat peers fail **gracefully**: as N grows, the share of runs landing in partial credit swells (11%, 14%, 20%, 31% at one to four agents) — some features work, others do not. Supervision is **bimodal**: partial outcomes thin out (16%, 11%, 5% at two to four agents), replaced by either total success or total failure. The pattern is not perfectly monotone — at five agents the supervised partial share rebounds to 12.5% — but across the range where both arms can be compared it runs firmly against the flat trend. This follows from the structure. Centralising integration makes the supervisor a single point of success — if its merge lands, everything lands; if it botches, everything is lost — whereas in the flat arm each agent merges independently, so partial contributions survive a peer's failure. That trade is a liability on small teams, where it converts would-be partial credit into zeros, and an asset on large ones, where the flat arm's partial-credit share is precisely what is growing.

## Wall-Clock: Hierarchy Is Slower Still

Supervision buys none of its advantage back in time. It is slower than flat peers at every team size — 9.5 versus 5.6 minutes at two agents, 12.3 versus 8.3 at four — and the gap widens (Figure 3d). Measured against the solo baseline, parallel speedup is 0.38× at two agents falling to 0.32× at five, worse than the flat arm's already sub-unity 0.67× → 0.56×. The supervisor lengthens the critical path twice: workers idle while the leader plans and allocates (time-to-first-claim averages 3.5 minutes, median 3.2), and integration runs serially at the end, after every worker has finished. The per-agent runtimes tell us the parallelism is real — summed agent time grows roughly linearly with team size while wall-clock grows far more slowly — but it is swamped by coordination sitting on the critical path. The finding of Study 2, that sharing the work does not make it faster, survives the change of topology and is amplified by it.

## What This Shows

Hierarchy is not a cure for the communication tax; it is a different trade. Supervision makes a small team more expensive, slower, and slightly less correct, and it converts graceful partial degradation into all-or-nothing outcomes. What it buys is a **better exponent**: coordination waste falls from super-proportional (N^−1.61) to almost exactly proportional (N^−1.10), and the correctness trend reverses from falling to rising. Past roughly four agents both changes favour the supervisor. Below that, they do not.

Two limits bound this conclusion. The five-agent column rests on the six K = 4 pools alone (16 runs), which are by construction the pools a single agent could already solve, so it is both the thinnest and the most favourably-composed evidence here. And the region where the fitted curves say the supervisor's advantage becomes large — six agents and beyond — is exactly the region a workload capped at K = 4 cannot test. Whether the exponent gap continues to hold, and where the two topologies' correctness curves ultimately settle, requires pools of six to eight interdependent features: the natural next experiment, and one the apparatus described here is already able to run.
