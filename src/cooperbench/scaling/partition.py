"""Deterministic feature→agent partitioning.

The partition is a *controlled variable*, not an agent choice: for a fixed set
of K features and N agents, the assignment is fully determined by the policy and
is identical at every N (only the number of buckets changes).  Same inputs →
same assignment, always (no seed enters here — determinism is structural).

Policies are registered in ``PARTITION_POLICIES`` so ``--partition`` stays
extensible; ``round-robin`` is the only policy for now.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence


def _round_robin(features: Sequence[int], n_agents: int) -> dict[str, list[int]]:
    """Deal features round-robin to ``agent1..agentN`` after a stable sort.

    Feature ``sorted(features)[i]`` goes to agent ``i % n_agents``.  With K
    features and N agents (K >= N) each agent owns ``ceil`` or ``floor`` of K/N
    contiguous-in-rank features.  At N=1 the single agent owns all K.
    """
    feats = sorted(features)
    buckets: list[list[int]] = [[] for _ in range(n_agents)]
    for i, f in enumerate(feats):
        buckets[i % n_agents].append(f)
    return {f"agent{j + 1}": buckets[j] for j in range(n_agents)}


# name -> policy fn.  Add new policies here; the CLI validates against the keys.
PARTITION_POLICIES: dict[str, Callable[[Sequence[int], int], dict[str, list[int]]]] = {
    "round-robin": _round_robin,
}


def partition_features(
    features: Sequence[int],
    n_agents: int,
    policy: str = "round-robin",
) -> dict[str, list[int]]:
    """Partition ``features`` across ``n_agents`` using the named ``policy``.

    Returns a mapping ``{"agent1": [...], ..., "agentN": [...]}``.  Raises on an
    unknown policy or when there are fewer features than agents (every agent
    must own at least one feature — a scaling cell with an idle agent is not a
    valid controlled comparison).
    """
    if policy not in PARTITION_POLICIES:
        raise ValueError(f"unknown partition policy {policy!r}; known: {sorted(PARTITION_POLICIES)}")
    if n_agents < 1:
        raise ValueError(f"n_agents must be >= 1, got {n_agents}")
    if len(features) < n_agents:
        raise ValueError(
            f"cannot split {len(features)} features across {n_agents} agents (need K >= N so no agent is idle)"
        )
    if len(set(features)) != len(features):
        raise ValueError(f"duplicate feature ids in {list(features)!r}")
    return PARTITION_POLICIES[policy](features, n_agents)
