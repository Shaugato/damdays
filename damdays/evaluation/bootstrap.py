"""95% confidence intervals by re-drawing whole dams, or whole region-years.

Why whole dams? Forecasts for the same dam on nearby dates are not independent
pieces of evidence: if a dam is easy to forecast, all of its rows are. Re-drawing
single rows would pretend we have far more independent evidence than we do,
and the intervals would be too narrow. So we re-draw dams instead: pick N dams
at random, with replacement, from the N we have (some appear twice, some not
at all), recompute every number, and repeat many times. The middle 95% of the
recomputed values is the 95% interval.

The region-year bootstrap does the same with (region, July-June year) blocks.
A dry year hits every dam in a region at once, so this interval answers "how
different could the result be with a different run of years?". TEST has only
about 20 region-years, so this interval is rough and usually the wider one.

Each replicate re-weights rows instead of copying them: a dam drawn twice gets
weight 2 on all its rows, a dam not drawn gets weight 0. Clusters are numbered
in sorted order and the seed is fixed, so the same predictions always get the
same intervals, whatever order their rows arrive in.
"""
import numpy as np

CI_LEVEL = 0.95


def cluster_weights(cluster_index, n_clusters, rng):
    """Row weights for one replicate: how many times each row's cluster was drawn."""
    times_drawn = np.bincount(rng.integers(0, n_clusters, n_clusters), minlength=n_clusters)
    return times_drawn[cluster_index].astype(float)


def percentile_intervals(replicates, level=CI_LEVEL):
    """[low, high] percentile interval for every number in a list of replicate dicts."""
    if not replicates:
        return {}
    low_q, high_q = 50 * (1 - level), 100 - 50 * (1 - level)    # 2.5 and 97.5 for 95%
    intervals = {}
    for name in replicates[0]:
        values = np.array([rep[name] for rep in replicates], dtype=float)
        values = values[np.isfinite(values)]
        intervals[name] = ([float(np.percentile(values, low_q)), float(np.percentile(values, high_q))]
                           if len(values) else [np.nan, np.nan])
    return intervals


def cluster_bootstrap(metric_fn, clusters, n_boot, seed):
    """Percentile 95% intervals for every number that metric_fn returns.

    metric_fn(w) receives row weights and returns a dict of numbers, or None
    when a replicate cannot be scored (for example it drew no dam that had an
    event); such replicates are skipped and counted.

    Returns (intervals, info). intervals maps each number's name to [low, high];
    info records the number of clusters, the seed and how many replicates were used.
    """
    names, cluster_index = np.unique(np.asarray(clusters), return_inverse=True)
    cluster_index = cluster_index.ravel()
    rng = np.random.default_rng(seed)
    replicates = []
    for _ in range(n_boot):
        values = metric_fn(cluster_weights(cluster_index, len(names), rng))
        if values is not None:
            replicates.append(values)
    info = dict(clusters=int(len(names)), seed=int(seed), n_boot=int(n_boot), replicates_used=len(replicates))
    return percentile_intervals(replicates), info
