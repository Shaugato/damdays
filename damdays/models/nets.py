"""Tidemark's two neural-net members: S (the sequence net) and M (the tabular MLP).

PREREG "Model", P1, per event kind (R30, D0, D0-gradual):
  (S) a causal dilated TCN on the 24 complete months before the issue, fused with a tabular MLP;
  (M) an MLP on 64 tabular inputs.
  S and M are 3-seed averages (fusion.member_logit averages the seeds on the log-odds scale).
tidemark.MEMBERS registers them; rung L2 fuses T + S + M in equal thirds.

One net, three answers (multi-task)
-----------------------------------
Each net has three outputs ("heads"): R30, D0 and D0g. It is trained ONCE per
cutoff and seed, and each head learns only from the rows Tidemark gives that
kind (tidemark.member_fit_rows): at risk for that kind, label determinable and
known, answer final before the cutoff. When a 90-day window holds only an
abrupt dry-out (often a satellite artefact), the D0-gradual label is missing,
so that row is left out of the D0g head (masked), not counted as "no event".
The first fit call of a (net, cutoff, seed) trains it; the other two kinds
reuse it and read their own head.

Inputs
------
TABULAR_INPUTS: 43 causal columns of the P1 table (level, trend, history,
yearly checkpoints, track record, neighbours, rain percentiles; each is
explained in damdays/features/spec.py and docs/FEATURES.md). Counts and
durations are log-scaled. Each column is standardised with the mean and spread
of the FIT rows only, clipped to +-5 spreads, and a missing value becomes 0
plus a "was missing" flag (for columns missing in more than 0.1% of the fit
rows). With the VAL fit rows that is 64 numbers, the PREREG's "64 tabular inputs".
S also reads the 24-month sequence of 9 channels (damdays.features.sequences).

Disclosed: the history length n_hist_c is one of the 43 columns. The PREREG
keeps time-growing counts out of the P1 TREES; the frozen pre-event nets used
it (log-scaled), so it is kept here unchanged.

Architecture (small enough for a laptop CPU)
--------------------------------------------
  tabular part   Linear(inputs, 64) - ReLU - Dropout 0.1 - Linear(64, 64) - ReLU
  sequence part  (S only) causal dilated TCN: 1x1 convolution to 32 channels, then
                 4 residual convolutions (kernel 3, dilation 1, 2, 4, 8, padded on the
                 left only, so month t never sees months after t); its value at the
                 last month summarises the 24 months
  head           Linear(64 [+ 32], 64) - ReLU - Dropout 0.1 - Linear(64, 3 log-odds)

Training (NET_SETTINGS; fixed before the event, not tuned here)
---------------------------------------------------------------
AdamW (learning rate 2e-3, weight decay 1e-4), one-cycle schedule, batches of
1024, ONE pass over the fit rows, gradient clipping at 1, binary cross-entropy
averaged over the (row, head) pairs that are unmasked. Seeds 0, 1 and 2.
At most 4 CPU threads (other jobs share the machine).

The time rules
--------------
* Fit rows come from Tidemark (answers final before the cutoff); the
  normalising means and spreads come from those rows only.
* For an inner-backtest cutoff (before 2009) the three dam_rate columns are
  replaced by their values as of that cutoff, exactly as Tidemark does for T
  (tidemark.member_setup); predictions read the same replaced values.
* Every input is causal: the tabular columns are proved so by
  tests/test_no_lookahead.py, and so are the sequences (generator "net sequences").

Checkpoints (crash safety)
--------------------------
A trained net is saved to data_cache/nets/<cutoff>/<S|M>_seed<k>.pt together
with a fingerprint of everything it learned from (fit rows, labels, inputs,
settings). A later run with the same fingerprint loads it instead of training
again; any change to the data or settings makes it train afresh.
"""
import hashlib
import json
import logging
import pickle
import time
import weakref
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import torch
from torch import nn

from damdays import config
from damdays.features import sequences as seq
from damdays.features import spec

logger = logging.getLogger(__name__)

KINDS = ("R30", "D0", "D0g")             # the three heads, in this order
SEEDS = (0, 1, 2)                         # PREREG: S and M are 3-seed averages
TORCH_THREADS = 4                         # CPU cap for the event build
P_MIN, P_MAX = 1e-6, 1 - 1e-6             # probabilities are kept strictly inside (0, 1), as in fusion
PREDICT_CHUNK = 8192                      # rows per forward pass when predicting
CHECKPOINT_DIR = config.CACHE_DIR / "nets"

NET_SETTINGS = dict(
    tabular_width=64, tcn_channels=32, tcn_kernel=3, tcn_dilations=(1, 2, 4, 8), head_width=64, dropout=0.1,
    learning_rate=2e-3, weight_decay=1e-4, warmup_share=0.15, batch_size=1024, epochs=1, grad_clip=1.0,
    clip_spreads=5.0, flag_missing_share=1e-3,
)

MODELS = {
    "S": "causal dilated TCN on the 24 complete months before the issue month + tabular MLP (multi-task)",
    "M": "MLP on the tabular inputs (multi-task)",
}

# ---------------------------------------------------------------------------
# The tabular inputs (all causal; see damdays/features/spec.py for each column)
# ---------------------------------------------------------------------------
TABULAR_INPUTS = spec.check_feature_list([
    # the dam's own recent history (windows end at today's look)
    "rel", "last3", "s60", "s120", "rec", "max365", "min365", "since_full", "anom_own",
    "clim_dd", "clim_fast", "gap_prev", "armed", "since_arm", "sin_doy", "cos_doy",
    # what we knew about the dam on 1 January (checkpoints), and its outline
    "full_c", "wet_share_c", "fill_share_c", "n_hist_c", "log_n_pixels", "pixel_compactness", "elongation",
    # "low" history and days-to-threshold, for both thresholds
    "low365_D0", "since_low_D0", "dtt_trend_D0", "dtt_clim_D0", "dtt_fast_D0",
    "low365_R30", "since_low_R30", "dtt_trend_R30", "dtt_clim_R30", "dtt_fast_R30",
    # the dam's track record (only forecasts whose answer was final), one per kind
    "dam_rate_D0", "dam_rate_R30", "dam_rate_D0g",
    # the neighbours (their looks strictly before the issue)
    "R_anom", "R_chg3", "R_zero",
    # rain percentiles (windows end the month before the issue month)
    "rain_pctc3", "rain_pctc6", "rain_pctc12", "rain_pctc24",
])
LOG_SCALED = {"since_full", "since_arm", "gap_prev", "n_hist_c", "since_low_D0", "since_low_R30"}


# ===========================================================================
# 1. Tabular inputs: log scale, standardise on fit rows, flag missing values
# ===========================================================================
def raw_tabular(columns, positions):
    """The tabular inputs of the table rows at `positions`: (n, 43) float32, counts log-scaled.

    columns  one array per TABULAR_INPUTS column, aligned with the table rows
    """
    out = np.empty((len(positions), len(TABULAR_INPUTS)), dtype=np.float32)
    for j, (name, values) in enumerate(zip(TABULAR_INPUTS, columns)):
        x = np.asarray(values[positions], dtype=np.float32)
        out[:, j] = np.log1p(np.clip(x, 0, None)) if name in LOG_SCALED else x
    return out


@dataclass
class TabularScaler:
    """Standardise with fit-row means and spreads, clip to +-5, missing -> 0 plus a "was missing" flag.

    mean, spread  per column, from the fit rows only
    flagged       columns missing in more than 0.1% of the fit rows: each gets a 0/1 flag input
    """
    mean: np.ndarray
    spread: np.ndarray
    flagged: np.ndarray

    @classmethod
    def fit(cls, raw):
        """Learn the statistics from the fit rows' raw inputs."""
        raw64 = raw.astype(np.float64)
        missing_share = np.isnan(raw64).mean(axis=0)
        return cls(mean=np.nanmean(raw64, axis=0).astype(np.float32),
                   spread=(np.nanstd(raw64, axis=0) + 1e-6).astype(np.float32),
                   flagged=np.flatnonzero(missing_share > NET_SETTINGS["flag_missing_share"]))

    @property
    def n_inputs(self):
        """How many numbers the net receives: one per column plus one per flagged column."""
        return len(self.mean) + len(self.flagged)

    def transform(self, raw):
        """(n, n_inputs) float32 net inputs from raw inputs."""
        flags = np.isnan(raw[:, self.flagged]).astype(np.float32)
        limit = NET_SETTINGS["clip_spreads"]
        z = np.clip((raw - self.mean) / self.spread, -limit, limit)
        return np.concatenate([np.nan_to_num(z, nan=0.0), flags], axis=1).astype(np.float32)

    def state(self):
        """The statistics as tensors (for the checkpoint file)."""
        return {"mean": torch.from_numpy(self.mean), "spread": torch.from_numpy(self.spread),
                "flagged": torch.from_numpy(self.flagged.astype(np.int64))}

    @classmethod
    def from_state(cls, state):
        """Inverse of state()."""
        return cls(mean=state["mean"].numpy(), spread=state["spread"].numpy(), flagged=state["flagged"].numpy())


# ===========================================================================
# 2. The networks
# ===========================================================================
class CausalTCN(nn.Module):
    """Dilated convolutions over the months that only look backwards; returns a summary at the last month.

    Each layer pads (kernel - 1) x dilation months on the LEFT only, so the value
    at month t depends on months t, t - d and t - 2d: never on later months.
    With dilations 1, 2, 4, 8 the last month sees 31 months back (all 24).
    """

    def __init__(self, n_channels, width, kernel, dilations):
        super().__init__()
        self.project = nn.Conv1d(n_channels, width, kernel_size=1)
        self.layers = nn.ModuleList(nn.Conv1d(width, width, kernel_size=kernel, dilation=d) for d in dilations)
        self.left_pads = [(kernel - 1) * d for d in dilations]

    def every_month(self, months):
        """months: (batch, 24, channels) -> (batch, width, 24): the summary up to each month."""
        h = self.project(months.transpose(1, 2))
        for layer, pad in zip(self.layers, self.left_pads):
            h = h + torch.relu(layer(nn.functional.pad(h, (pad, 0))))     # residual; left padding = causal
        return h

    def forward(self, months):
        """months: (batch, 24, channels) -> (batch, width): the summary at the last month."""
        return self.every_month(months)[:, :, -1]


class TidemarkNet(nn.Module):
    """Tabular MLP (+ the TCN summary for S) -> head -> three log-odds (R30, D0, D0g)."""

    def __init__(self, n_tabular, use_sequence):
        super().__init__()
        s = NET_SETTINGS
        self.tabular = nn.Sequential(nn.Linear(n_tabular, s["tabular_width"]), nn.ReLU(), nn.Dropout(s["dropout"]),
                                     nn.Linear(s["tabular_width"], s["tabular_width"]), nn.ReLU())
        self.sequence = (CausalTCN(len(seq.CHANNELS), s["tcn_channels"], s["tcn_kernel"], s["tcn_dilations"])
                         if use_sequence else None)
        width = s["tabular_width"] + (s["tcn_channels"] if use_sequence else 0)
        self.head = nn.Sequential(nn.Linear(width, s["head_width"]), nn.ReLU(), nn.Dropout(s["dropout"]),
                                  nn.Linear(s["head_width"], len(KINDS)))

    def forward(self, tabular, months=None):
        """tabular: (batch, n_tabular); months: (batch, 24, 9) for S, None for M. Returns (batch, 3) log-odds."""
        parts = [self.tabular(tabular)]
        if self.sequence is not None:
            parts.append(self.sequence(months))
        return self.head(torch.cat(parts, dim=1))


def new_net(model, n_tabular):
    """An untrained S (with the sequence part) or M (tabular only)."""
    if model not in MODELS:
        raise ValueError(f"Unknown net {model!r}; expected one of {sorted(MODELS)}")
    return TidemarkNet(n_tabular, use_sequence=(model == "S"))


# ===========================================================================
# 3. What the nets read from one P1 table (built once per table, then reused)
# ===========================================================================
_DEFAULT_HISTORY = {}


def default_monthly_history():
    """The monthly history of the development regions, built from data_cache (scripts/01_build_data.py)."""
    if "history" not in _DEFAULT_HISTORY:
        panel = pd.read_pickle(config.CACHE_DIR / "panel.pkl")
        attrs = pd.read_pickle(config.CACHE_DIR / "attributes.pkl")
        with open(config.CACHE_DIR / "silo_rain.pkl", "rb") as handle:
            rain_by_cell = pickle.load(handle)
        _DEFAULT_HISTORY["history"] = seq.build_monthly_history(panel, attrs, rain_by_cell)
        logger.info("monthly history built for the sequences: %d dams x %d months",
                    *_DEFAULT_HISTORY["history"].pc_ffill.shape)
    return _DEFAULT_HISTORY["history"]


@dataclass
class TrainingPlan:
    """What a net learns from at one cutoff (the same rows Tidemark gives each kind).

    rows      positions in the P1 table of every row at least one head learns from
    heads     (rows, 3) True where that kind's head learns from the row
    labels    (rows, 3) the answers (0 where the head is masked)
    replace   {column: one value per table row} read instead of the stored column
    fit_rows  {kind: positions}, exactly tidemark.member_fit_rows
    """
    rows: np.ndarray
    heads: np.ndarray
    labels: np.ndarray
    replace: dict
    fit_rows: dict


class TableInputs:
    """Everything the nets read from one P1 table: tabular columns, sequence indices, training plans."""

    def __init__(self, table, history):
        missing = [c for c in TABULAR_INPUTS if c not in table.columns]
        if missing:
            raise ValueError(f"The P1 table lacks the net inputs {missing} (load the 'rain' group too).")
        self.table_ref = weakref.ref(table)
        self.n_rows = len(table)
        self.columns = {c: table[c].to_numpy() for c in TABULAR_INPUTS}
        self.history = history
        self.dam_row, self.issue_month = seq.sequence_rows(history, table["uid"].astype(str).to_numpy(),
                                                           table["issue_date"])
        self.full_c = table["full_c"].to_numpy(dtype=np.float64)
        self.plans = {}

    def tabular_columns(self, replace):
        """The tabular input columns in TABULAR_INPUTS order, with replaced columns swapped in."""
        return [np.asarray(replace[c]) if c in replace else self.columns[c] for c in TABULAR_INPUTS]

    def sequences(self, positions):
        """The (n, 24, 9) input sequences of the table rows at `positions`."""
        return seq.issue_sequences(self.history, self.dam_row[positions], self.issue_month[positions],
                                   self.full_c[positions])


_TABLE_INPUTS = {}


def table_inputs(inputs):
    """The TableInputs of inputs["p1"], built on first use and reused while the same table AND history are in use.

    inputs["monthly_history"] (optional) is the monthly history to read the
    sequences from; by default it is built from data_cache (development regions).
    The table is assumed not to change in place while it is in use (pass a new
    table instead): the nets read their input columns once.
    """
    table = inputs["p1"]
    history = inputs.get("monthly_history")
    if history is None:
        history = default_monthly_history()
    cached = _TABLE_INPUTS.get("current")
    # Both must match: the same table with a different monthly history must not reuse the old sequences.
    if cached is None or cached.table_ref() is not table or cached.history is not history:
        _TABLE_INPUTS["current"] = TableInputs(table, history)
        logger.info("net inputs prepared for a P1 table of %d rows", len(table))
    return _TABLE_INPUTS["current"]


def training_plan(inputs, cutoff):
    """The TrainingPlan at `cutoff`: Tidemark's own fit rows and replaced columns, for all three kinds at once."""
    # Imported here, not at the top: tidemark imports this module to register S and M.
    from damdays.models import tidemark
    prepared = table_inputs(inputs)
    if cutoff not in prepared.plans:
        table = inputs["p1"]
        fit_rows = {kind: tidemark.member_fit_rows(table, kind, cutoff) for kind in KINDS}
        replace = {}
        for kind in KINDS:
            replace.update(tidemark.member_setup(table, kind, cutoff)["replace"])
        rows = np.unique(np.concatenate(list(fit_rows.values())))
        heads = np.stack([np.isin(rows, fit_rows[kind]) for kind in KINDS], axis=1)
        answers = np.stack([table[f"y_{kind}"].to_numpy(dtype=np.float64)[rows] for kind in KINDS], axis=1)
        labels = np.where(heads, np.nan_to_num(answers, nan=0.0), 0.0).astype(np.float32)
        prepared.plans[cutoff] = TrainingPlan(rows=rows, heads=heads, labels=labels, replace=replace,
                                              fit_rows=fit_rows)
    return prepared.plans[cutoff]


# ===========================================================================
# 4. Training (one multi-task net per model, cutoff and seed)
# ===========================================================================
def use_cpu_threads():
    """Cap torch at TORCH_THREADS threads (other jobs share the machine)."""
    torch.set_num_threads(TORCH_THREADS)


def masked_loss(logits, labels, heads):
    """Binary cross-entropy averaged over the unmasked (row, head) pairs only."""
    per_pair = nn.functional.binary_cross_entropy_with_logits(logits, labels, reduction="none")
    return (per_pair * heads).sum() / heads.sum().clamp(min=1.0)


def train_net(model, seed, X, heads, labels, sequences_of=None, label=""):
    """Train one net for NET_SETTINGS["epochs"] pass(es) over the rows. Returns (net, info).

    X             (rows, n_inputs) standardised tabular inputs
    heads, labels (rows, 3) masks and answers
    sequences_of  for S: a function giving the (n, 24, 9) sequences of row numbers 0..rows-1
    """
    s = NET_SETTINGS
    use_cpu_threads()
    torch.manual_seed(seed)
    order_rng = np.random.default_rng(seed)
    net = new_net(model, X.shape[1])
    optimiser = torch.optim.AdamW(net.parameters(), lr=s["learning_rate"], weight_decay=s["weight_decay"])
    n_batches = int(np.ceil(len(X) / s["batch_size"]))
    schedule = torch.optim.lr_scheduler.OneCycleLR(optimiser, max_lr=s["learning_rate"],
                                                   total_steps=n_batches * s["epochs"], pct_start=s["warmup_share"])
    heads_t, labels_t = torch.from_numpy(heads.astype(np.float32)), torch.from_numpy(labels)
    started, losses = time.time(), []
    net.train()
    for epoch in range(s["epochs"]):
        order = order_rng.permutation(len(X))
        total = 0.0
        for b in range(n_batches):
            batch = order[b * s["batch_size"]:(b + 1) * s["batch_size"]]
            months = torch.from_numpy(sequences_of(batch)) if sequences_of is not None else None
            loss = masked_loss(net(torch.from_numpy(X[batch]), months), labels_t[batch], heads_t[batch])
            optimiser.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(net.parameters(), s["grad_clip"])
            optimiser.step()
            schedule.step()
            total += loss.item()
            if (b + 1) % max(1, n_batches // 5) == 0:
                logger.info("%s epoch %d: %d%% of batches, mean loss %.4f, %.0f s", label, epoch + 1,
                            round(100 * (b + 1) / n_batches), total / (b + 1), time.time() - started)
        losses.append(total / n_batches)
    net.eval()
    info = dict(rows=int(len(X)), head_rows={k: int(heads[:, j].sum()) for j, k in enumerate(KINDS)},
                head_events={k: int(labels[heads[:, j], j].sum()) for j, k in enumerate(KINDS)},
                n_inputs=int(X.shape[1]), parameters=int(sum(p.numel() for p in net.parameters())),
                epoch_losses=[round(v, 5) for v in losses], train_seconds=round(time.time() - started, 1),
                torch=torch.__version__, threads=TORCH_THREADS)
    return net, info


def fingerprint(*parts):
    """A short SHA-1 fingerprint of arrays, strings and dicts (for checkpoint validity)."""
    digest = hashlib.sha1()
    for part in parts:
        if isinstance(part, np.ndarray):
            digest.update(str((part.dtype, part.shape)).encode())
            digest.update(np.ascontiguousarray(part).tobytes())
        else:
            digest.update(json.dumps(part, sort_keys=True, default=str).encode())
    return digest.hexdigest()[:16]


def history_fingerprint(history):
    """Fingerprint of the monthly history (computed once per history object)."""
    if not hasattr(history, "_fingerprint"):
        history._fingerprint = fingerprint(history.uids.astype(str), history.pc_ffill, history.observed,
                                           history.months_since, history.dry_ffill, history.log_rain,
                                           history.rain_anomaly, str(history.data_end))
    return history._fingerprint


def checkpoint_path(model, cutoff, seed):
    """data_cache/nets/<cutoff>/<model>_seed<seed>.pt"""
    return CHECKPOINT_DIR / str(cutoff) / f"{model}_seed{seed}.pt"


# ===========================================================================
# 5. A trained net, and its predictions
# ===========================================================================
@dataclass
class TrainedNet:
    """One trained multi-task net (all three heads), ready to predict any rows of a P1 table."""
    model: str
    seed: int
    cutoff: str
    net: TidemarkNet
    scaler: TabularScaler
    info: dict
    _logits: dict = field(default_factory=dict, repr=False)   # {"source": weakref to TableInputs, "values": (rows, 3)}

    def __getstate__(self):
        """Pickle without the prediction cache (it refers to the inputs of one table)."""
        state = dict(self.__dict__)
        state["_logits"] = {}
        return state

    def log_odds(self, inputs, positions):
        """(n, 3) log-odds for the table rows at `positions`, computed once per row and then reused.

        The cache belongs to one TableInputs (one table and one monthly history):
        a new table or a new history starts it afresh.
        """
        prepared = table_inputs(inputs)
        cache = self._logits
        if cache.get("source") is None or cache["source"]() is not prepared:
            cache.clear()
            cache.update(source=weakref.ref(prepared),
                         values=np.full((prepared.n_rows, len(KINDS)), np.nan, np.float32))
        values = cache["values"]
        positions = np.asarray(positions)
        todo = np.unique(positions[np.isnan(values[positions, 0])])      # rows not predicted yet
        if len(todo):
            started = time.time()
            values[todo] = self.compute_log_odds(inputs, todo)
            logger.info("%s seed %d (cutoff %s): predicted %d rows in %.0f s", self.model, self.seed, self.cutoff,
                        len(todo), time.time() - started)
        return values[positions]

    def compute_log_odds(self, inputs, positions):
        """Run the net on the table rows at `positions` (chunked, no gradients)."""
        use_cpu_threads()
        prepared = table_inputs(inputs)
        replace = training_plan(inputs, self.cutoff).replace if replaced_columns_needed(self.cutoff) else {}
        columns = prepared.tabular_columns(replace)
        out = np.empty((len(positions), len(KINDS)), dtype=np.float32)
        with torch.no_grad():
            for start in range(0, len(positions), PREDICT_CHUNK):
                chunk = positions[start:start + PREDICT_CHUNK]
                X = torch.from_numpy(self.scaler.transform(raw_tabular(columns, chunk)))
                months = torch.from_numpy(prepared.sequences(chunk)) if self.model == "S" else None
                out[start:start + len(chunk)] = self.net(X, months).numpy()
        return out

    def probabilities(self, inputs, positions, kind):
        """P(event) for one kind on the table rows at `positions`, clipped to (1e-6, 1 - 1e-6), float64."""
        z = self.log_odds(inputs, positions)[:, KINDS.index(kind)].astype(np.float64)
        return np.clip(1.0 / (1.0 + np.exp(-z)), P_MIN, P_MAX)


def replaced_columns_needed(cutoff):
    """True for an inner-backtest cutoff (before 2009): the dam_rate columns are recomputed as of it."""
    return pd.Timestamp(cutoff) < pd.Timestamp(config.VAL_START)


_TRAINED = {}


def trained_net(inputs, model, cutoff, seed):
    """The net `model` ("S" or "M") trained at `cutoff` with `seed`: from memory, from its checkpoint, or trained now.

    TIME: it learns only from Tidemark's fit rows at the cutoff (answers final
    before it), and its input statistics come from those rows only.
    """
    cutoff = str(pd.Timestamp(cutoff).date())
    plan = training_plan(inputs, cutoff)
    prepared = table_inputs(inputs)
    raw = raw_tabular(prepared.tabular_columns(plan.replace), plan.rows)
    sequence_part = (history_fingerprint(prepared.history), prepared.full_c[plan.rows]) if model == "S" else ()
    signature = fingerprint(model, seed, cutoff, NET_SETTINGS, TABULAR_INPUTS, list(seq.CHANNELS),
                            seq.SEQUENCE_MONTHS, plan.rows, plan.heads, plan.labels, raw, *sequence_part)
    key = (model, cutoff, seed, signature)
    if key in _TRAINED:
        return _TRAINED[key]

    path = checkpoint_path(model, cutoff, seed)
    trained = load_checkpoint(path, signature)
    if trained is None:
        label = f"{model} seed {seed} (cutoff {cutoff})"
        logger.info("%s: training on %d rows (%s)", label, len(plan.rows),
                    ", ".join(f"{k} {int(plan.heads[:, j].sum()):,}" for j, k in enumerate(KINDS)))
        scaler = TabularScaler.fit(raw)
        X = scaler.transform(raw)
        sequences_of = (lambda batch: prepared.sequences(plan.rows[batch])) if model == "S" else None
        net, info = train_net(model, seed, X, plan.heads, plan.labels, sequences_of, label)
        info.update(model=model, about=MODELS[model], seed=seed, cutoff=cutoff, signature=signature,
                    replaced_columns=sorted(plan.replace))
        trained = TrainedNet(model=model, seed=seed, cutoff=cutoff, net=net, scaler=scaler, info=info)
        save_checkpoint(trained, path)
        logger.info("%s: trained in %.0f s (loss %s); saved to %s", label, info["train_seconds"],
                    info["epoch_losses"], path)
    _TRAINED[key] = trained
    return trained


def save_checkpoint(trained, path):
    """Write the net, its input statistics and its fingerprint (written to a temporary file first)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    torch.save({"state_dict": trained.net.state_dict(), "scaler": trained.scaler.state(),
                "info": json.loads(json.dumps(trained.info, default=str))}, temporary)
    temporary.replace(path)


def load_checkpoint(path, signature):
    """The TrainedNet saved at `path` if its fingerprint matches, else None (it will be retrained)."""
    if not path.exists():
        return None
    saved = torch.load(path, weights_only=True)
    info = saved["info"]
    if info.get("signature") != signature:
        logger.info("checkpoint %s is for different data or settings: retraining", path)
        return None
    scaler = TabularScaler.from_state(saved["scaler"])
    net = new_net(info["model"], scaler.n_inputs)
    net.load_state_dict(saved["state_dict"])
    net.eval()
    logger.info("%s seed %d (cutoff %s): loaded from %s", info["model"], info["seed"], info["cutoff"], path)
    return TrainedNet(model=info["model"], seed=int(info["seed"]), cutoff=info["cutoff"], net=net, scaler=scaler,
                      info=dict(info, loaded_from_checkpoint=True))


# ===========================================================================
# 6. The Tidemark members (Member.fit / Member.predict, see tidemark.Member)
# ===========================================================================
@dataclass
class NetHead:
    """A member as Tidemark sees it: one trained multi-task net, read at one kind's head."""
    trained: TrainedNet
    kind: str


def fit_net_member(model, inputs, kind, fit_rows, setup, seed):
    """The trained net (shared by the three kinds) and the head of `kind`; checks the fit rows agree with Tidemark's."""
    trained = trained_net(inputs, model, setup["cutoff"], seed)
    plan = training_plan(inputs, trained.cutoff)
    if not np.array_equal(plan.fit_rows[kind], np.asarray(fit_rows)):
        raise AssertionError(f"The {model} net's {kind} rows differ from the fit rows Tidemark passed.")
    return NetHead(trained=trained, kind=kind)


def fit_sequence_member(inputs, kind, fit_rows, setup, seed):
    """Member S: the sequence net (TCN + tabular MLP) at the setup's cutoff, read at `kind`'s head."""
    return fit_net_member("S", inputs, kind, fit_rows, setup, seed)


def fit_tabular_member(inputs, kind, fit_rows, setup, seed):
    """Member M: the tabular MLP at the setup's cutoff, read at `kind`'s head."""
    return fit_net_member("M", inputs, kind, fit_rows, setup, seed)


def predict_net_member(fitted, inputs, row_positions, setup):
    """P(event) of a NetHead for the P1 rows at row_positions (setup is not needed: the net knows its cutoff)."""
    return fitted.trained.probabilities(inputs, row_positions, fitted.kind)
