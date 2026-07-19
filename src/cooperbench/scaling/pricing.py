"""Dollar-denomination of the token buckets.

The four buckets are raw token counts of **mixed types** (``context`` is
input/cache-read side; ``task``/``rework`` are output-side; ``comm`` mixes
generated-send and read-in payloads), so summing raw tokens across them is not
meaningful — and per the project's own methodology conclusion, *price* is the only
denominator that is fair across differing token-type compositions.

This module converts each bucket to dollars at published list prices, then
**apportions the run's actual ``total_cost_usd`` across the buckets in proportion
to their price-weighted token footprint**.  That makes the per-bucket dollars
(a) comparable across buckets and runs, and (b) sum exactly to the run's real cost
— an additive-in-dollars decomposition.

Caveat (documented, not hidden): the buckets are *proxies* and do not enumerate
every token the run paid for (e.g. per-step carried context beyond turn 0 is not
its own bucket).  Apportioning the true cost folds that residual into the buckets
proportionally.  The raw token buckets and the true ``dollar_cost`` are always
kept alongside so nothing is obscured.
"""

from __future__ import annotations

# Published list prices, USD per token (NOT per million).  Used only to *weight*
# buckets for apportioning the run's real cost — the headline cost is always the
# CLI's own ``total_cost_usd``.  Extend as models are added.
LIST_PRICES: dict[str, dict[str, float]] = {
    "claude-sonnet-5": {
        "input": 3.0e-6,
        "output": 15.0e-6,
        "cache_read": 0.30e-6,
        "cache_write": 3.75e-6,
    },
}


def prices_for(model: str) -> dict[str, float] | None:
    """Per-token price table for ``model`` (exact, then prefix match), or None."""
    if model in LIST_PRICES:
        return LIST_PRICES[model]
    for name, table in LIST_PRICES.items():
        if model.startswith(name) or name.startswith(model):
            return table
    return None


def _bucket_weights(run_total: dict, p: dict[str, float]) -> dict[str, float]:
    """Price-weighted token footprint per bucket (the apportioning weights).

    * context — resident context, dominated by cached reads → cache_read rate.
    * task / rework — generation → output rate.
    * comm — generated sends at output rate; received + re-ingested payloads are
      read into context at cache_read rate.
    """
    return {
        "context": run_total.get("context_tokens", 0) * p["cache_read"],
        "task": run_total.get("task_tokens", 0) * p["output"],
        "rework": run_total.get("rework_tokens", 0) * p["output"],
        "comm": (
            run_total.get("comm_sent_gen_tokens", 0) * p["output"]
            + (run_total.get("comm_recv_tokens", 0) + run_total.get("comm_reingest_tokens", 0)) * p["cache_read"]
        ),
    }


def apportion_bucket_dollars(run_total: dict, total_cost: float, model: str) -> dict[str, float] | None:
    """Split ``total_cost`` across buckets by price-weighted token share.

    Returns ``{context_usd, task_usd, comm_usd, rework_usd}`` summing to
    ``total_cost`` (additive in dollars), or ``None`` when the model has no price
    table or the weights are all zero (nothing to apportion).
    """
    p = prices_for(model)
    if p is None:
        return None
    w = _bucket_weights(run_total, p)
    total_w = sum(w.values())
    if total_w <= 0:
        return None
    return {f"{name}_usd": total_cost * (weight / total_w) for name, weight in w.items()}
