"""Agent-count scaling experiment (opt-in, flag-gated).

Measures how coordination COST scales as the number of agents N grows while
the WORKLOAD (a fixed set of K interdependent features) is held constant.
Nothing in this package runs unless the ``scaling`` subcommand is invoked; the
base benchmark (``run`` / ``eval``) is untouched.

See ``README.md`` in this directory for the design and usage.
"""

from cooperbench.scaling.partition import PARTITION_POLICIES, partition_features

__all__ = ["partition_features", "PARTITION_POLICIES"]
