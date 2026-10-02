"""Score the region ONCE with the shared scorecard, and read the PREREG verdicts off the results.

What is scored (PREREG "Sealed region protocol" and "Reported regardless of outcome"; FINAL_SPEC
runbook step 5). Every forecast issued 2016-07-01 to 2026-06-30 (P2: seasons 2016 to 2025).
  P1, the farmer runway, for R30, D0 and D0-gradual: G2 and Tidemark on
      the primary set (dam-like dams, Oct-Mar issues, at risk), persistent dams (Oct-Mar, at risk)
      and dam-like dams in all months, plus the label-determinable sensitivity row (primary set,
      no 3-look rule). Every Tidemark score carries the paired difference Tidemark minus G2 (same
      rows, same resampled dams and region-years).
  Runway curve (R30, D0): Tidemark's 30/60/90/180-day curve, each horizon against its own baselines.
  P2, the season rating: the 2 km cell, the dam and the gradual-dry dam rating, against RAIN, RAIN+ and B2.
  Season band: how many of the region's July-June years fall inside Tidemark's band (the pooled
      band, and the single-block 2009-2016 band, reported alongside as PREREG requires).
  DamDays floor: the share of "at least N days" floors that held.

Order on the ledger. For each task: G2 first, then Tidemark, which names G2 as its reference (the
ledger checks the reference's forecasts are exactly the ledgered ones). For P2: RAIN, RAIN+ and B2
first, then Tidemark. Every further subset of a task passes the same forecast table, so the ledger
records "same_predictions": one look per model and task.

Baselines are fitted on the scored region's OWN history (issues answered before 2016-07-01), in
the same time blocks as for the development regions (PREREG "Baselines"): B0, B2 and PERS for P1;
B0_h and B2_h for the curve; B0, B2, PERS, RAIN and RAIN+ for P2. They come from the same functions
as on the development regions (damdays.models.baselines and hazard), called on the region's table.
"""
import numpy as np
import pandas as pd

from damdays.data.splits import time_block
from damdays.evaluation import band_coverage, band_from_offsets, floor_coverage, score, score_curve
from damdays.evaluation.inputs import join_baselines, tidy_keys
from damdays.evaluation.ledger import Ledger
from damdays.evaluation.rules import is_octmar
from damdays.models import baselines, hazard, rows, tidemark
from damdays.models import uncertainty as unc

BLOCK = "TEST"
KINDS = rows.P1_KINDS
PRIMARY = "dam_like+octmar+at_risk"            # the scorecard's name for the primary P1 subset
N_BOOT_MAIN, N_BOOT_SIDE = 500, 200            # bootstrap draws: primary sets and P2; other subsets (as on VAL)
# P1 subsets: (scorecard subset, population the baselines are fitted on, Oct-Mar only?, bootstrap draws)
P1_SUBSETS = [("primary", "dam_like", True, "main"), ("persistent+octmar+at_risk", "persistent", True, "side"),
              ("dam_like+at_risk", "dam_like", False, "side")]
CURVE_SUBSETS = [("primary", "dam_like", "main"), ("dam_like+at_risk", "dam_like", "side"),
                 ("persistent+octmar+at_risk", "persistent", "side")]
P2_TASKS = [("P2_cell", "all", "p"), ("P2_dam", "dam_like", "p"), ("P2_dam_g", "dam_like", "p_g")]
P2_BASELINE_MODELS = ("RAIN", "RAIN+", "B2")   # scored first, then used as Tidemark's references
P2_PASS_DAUC, P2_KILL_DAUC = 0.05, 0.02        # PREREG: AUC gain over RAIN >= 0.05 (CI above 0); kill if < 0.02

# PREREG "Pre-declared expectations for the sealed region" (forecasts, not pass bars): (label, low, high, central)
EXPECTATIONS = {
    "R30 BSS vs B0": (0.15, 0.23, 0.19),
    "R30 BSS vs B2": (0.08, 0.15, None),
    "R30 calibration slope": (0.9, 1.25, None),
    "R30 CITL": (-0.3, 0.3, None),
    "R30 Tidemark minus G2 (BSS vs B0 units)": (0.01, 0.03, None),
    "P2 cell AUC gain over RAIN": (0.15, 0.30, None),
}


class RegionScoring:
    """Everything one scoring pass needs: the region's table, the forecasts, the ledger and the names."""

    def __init__(self, run, tables, forecasts, models, say, quick=False):
        self.run, self.say = run, say
        self.table, self.data_end = tables["p1"], tables["data_end"]
        self.p2_dam, self.p2_cell = tables["p2_dam"], tables["p2_cell"]
        self.tidemark_out = forecasts["tidemark"]          # predict_tidemark's p1, p2_dam and p2_cell
        self.g2 = forecasts["g2"]                          # {kind: (row positions, p)}
        self.model = models["tidemark"]                    # for the band constants
        self.ledger = Ledger(run.ledger_path)
        self.out_dir = run.scorecard_dir
        self.n_boot = {"main": 0, "side": 0} if quick else {"main": N_BOOT_MAIN, "side": N_BOOT_SIDE}
        self.note = ("DRY RUN (rehearsal): models fitted on " + "+".join(run.fit_regions) + " only, judged on "
                     + run.target_region + "; NOT the development TEST result") if run.rehearsal else (
                     "sealed-region opening, scripts/20_open_sealed_region.py; models "
                     + models["manifest"]["files"]["tidemark"]["sha256"][:12])
        self.results = {}
        self.not_scored = []          # subsets that cannot be scored (no labelled rows, or no events)

    # -- names ---------------------------------------------------------------
    def name(self, model):
        """Scorecard and ledger name: "tidemark", "G2", ... (dry run: "dryrun_tidemark", "dryrun_G2", ...)."""
        return self.run.model_name(model)

    def score(self, frame, task, subset, model, refs, boot, expected):
        """One scorecard call (TEST: through the run's ledger), kept in self.results[(task, subset, model)].

        A subset needs labelled rows with both events and non-events. In a new region a small subset
        (say persistent dams, gradual dry-outs) might have none: it is then listed in self.not_scored
        and on the results page instead of stopping the one-shot run. Nothing goes on the ledger for it.
        Returns the result, or None for such a subset.
        """
        y = frame.loc[expected.index, "y"].to_numpy(dtype=float)       # the rows the scorecard must score
        if len(y) == 0 or y.sum() == 0 or y.sum() == len(y):
            self.not_scored.append(dict(task=task, subset=subset, model=self.name(model), rows=int(len(y)),
                                        events=int(y.sum())))
            self.say(f"  NOT SCORABLE: {task} {subset} {self.name(model)}: {len(y):,} labelled rows, "
                     f"{int(y.sum()):,} events (needs both events and non-events)")
            return None
        result = score(frame, task, subset, model=self.name(model), refs=[self.name(r) for r in refs],
                       expected_keys=expected, n_boot=self.n_boot[boot], out_dir=self.out_dir, ledger=self.ledger,
                       note=self.note)
        self.results[(task, result["subset"], model)] = result
        return result

    # -- shared helpers --------------------------------------------------------
    def on_rows(self, positions, column):
        """A column of Tidemark's P1 output, read on the given rows of the region's P1 table."""
        return self.tidemark_out["p1"].set_index("row").loc[np.asarray(positions), column].to_numpy(dtype=float)

    def keys_and_flags(self, picked):
        """uid, issue_date, region and the subset flags of the P1 rows in `picked` (all at risk by construction)."""
        chosen = self.table.loc[picked]
        return chosen, pd.DataFrame({
            "uid": chosen["uid"].astype(str).to_numpy(), "issue_date": chosen["issue_date"].to_numpy(),
            "region": chosen["region"].astype(str).to_numpy(), "dam_like": chosen["dam_like"].to_numpy(dtype=bool),
            "persistent": chosen["persistent"].to_numpy(dtype=bool), "at_risk": True})

    @staticmethod
    def attach(frame, other, columns):
        """Copy `columns` from `other`; both must list the same forecasts in the same order (checked)."""
        same = (len(frame) == len(other)
                and (frame["uid"].astype(str).to_numpy() == other["uid"].astype(str).to_numpy()).all()
                and (pd.to_datetime(frame["issue_date"]).to_numpy()
                     == pd.to_datetime(other["issue_date"]).to_numpy()).all())
        if not same:
            raise AssertionError("Forecast tables are not row-aligned.")
        for column in columns:
            frame[column] = other[column].to_numpy()
        return frame

    @staticmethod
    def expected(frame, population, octmar_only, label="y"):
        """The rows a subset must be scored on, worked out here independently of the scorecard."""
        keep = frame[label].notna().to_numpy() & frame[population].to_numpy(dtype=bool)
        if octmar_only:
            keep = keep & is_octmar(frame["issue_date"])
        return frame.loc[keep, ["uid", "issue_date"]]

    # =========================================================================
    # P1: G2 and Tidemark, three kinds, three subsets, and the sensitivity row
    # =========================================================================
    def p1_frame(self, kind):
        """Every at-risk TEST issue of `kind`: keys, flags, the label, the sensitivity label, Tidemark and G2."""
        picked = rows.p1_block_rows(self.table, kind, BLOCK)
        positions = np.flatnonzero(picked)
        chosen, frame = self.keys_and_flags(picked)
        frame["y"] = rows.p1_scored_label(chosen, kind)                     # blank where label_ok is False
        raw = chosen[rows.p1_label(kind)].to_numpy(dtype=float)
        frame["y_sens"] = np.where(chosen["window_closed"].to_numpy(dtype=bool), raw, np.nan)   # no 3-look rule
        g2_positions, g2_p = self.g2[kind]
        if not np.array_equal(g2_positions, positions):
            raise AssertionError(f"G2's {kind} forecasts are not on the at-risk TEST rows.")
        frame[f"p_{self.name('G2')}"] = g2_p
        frame[f"p_{self.name('tidemark')}"] = self.on_rows(positions, f"p90_{kind}")
        return frame

    def score_p1(self):
        """G2 then Tidemark on each kind and subset (baselines from the region's own history), then the sensitivity rows."""
        for kind in KINDS:
            task, frame = f"P1_{kind}", self.p1_frame(kind)
            fitted = {pop: baselines.p1_baselines(self.table, kind, BLOCK, pop) for pop in ("dam_like", "persistent")}
            for subset, population, octmar_only, boot in P1_SUBSETS:
                scored = self.attach(frame.copy(), fitted[population], ["p_B0", "p_B2", "p_PERS"])
                keys = self.expected(frame, population, octmar_only)
                for model, refs in (("G2", []), ("tidemark", ["G2"])):
                    self.score(scored.assign(p=scored[f"p_{self.name(model)}"]), task, subset, model, refs, boot, keys)
            sens = self.attach(frame.copy(), fitted["dam_like"], ["p_B0", "p_B2", "p_PERS"]).assign(y=frame["y_sens"])
            keys = self.expected(frame, "dam_like", True, "y_sens")
            for model, refs in (("G2", []), ("tidemark", ["G2"])):
                self.score(sens.assign(p=sens[f"p_{self.name(model)}"]), f"{task}_sens", "primary", model, refs,
                           "side", keys)
            self.say(f"  P1_{kind} primary, BSS vs B0: " + ", ".join(
                f"{label} {self.results[(task, PRIMARY, model)]['point']['bss_B0']:+.4f}"
                if (task, PRIMARY, model) in self.results else f"{label} not scorable"
                for label, model in (("Tidemark", "tidemark"), ("G2", "G2"))))

    # =========================================================================
    # The runway curve (Tidemark only: G2 has no curve)
    # =========================================================================
    def score_curves(self):
        """Tidemark's curve on each subset, each horizon against the region's own B0_h and B2_h."""
        self.curve_results = {}
        for kind in tidemark.CURVE_KINDS:
            labels = hazard.horizon_labels(self.table, kind, self.data_end)
            picked = rows.p1_block_rows(self.table, kind, BLOCK)
            positions = np.flatnonzero(picked)
            _, frame = self.keys_and_flags(picked)
            for h in tidemark.HORIZONS:
                frame[f"y_{h}"] = labels.loc[picked, f"y_{h}"].to_numpy()
                frame[f"p_{h}"] = self.on_rows(positions, f"curve_{kind}_{h}")
            fitted = {pop: hazard.curve_baselines(self.table, kind, BLOCK, labels, pop)
                      for pop in ("dam_like", "persistent")}
            for subset, population, boot in CURVE_SUBSETS:
                scored = self.attach(frame.copy(), fitted[population],
                                     [f"p_B{b}_{h}" for b in (0, 2) for h in tidemark.HORIZONS])
                result = score_curve(scored, f"{kind}_curve", subset, model=self.name("tidemark"),
                                     n_boot=self.n_boot[boot], out_dir=self.out_dir, ledger=self.ledger, note=self.note)
                self.curve_results[(f"{kind}_curve", result["subset"])] = result
            primary = self.curve_results[(f"{kind}_curve", PRIMARY)]["bss_B0_by_horizon"]
            self.say(f"  {kind} curve primary, BSS vs B0_h: " + ", ".join(
                f"{h} d {v:+.3f}" if v is not None else f"{h} d not scorable" for h, v in primary.items()))

    # =========================================================================
    # P2: the season rating against RAIN, RAIN+ and B2
    # =========================================================================
    def p2_reference_frame(self, task, population):
        """Keys, label, flags and every P2 baseline (fitted on the region's own seasons before 2016-07-01)."""
        cells = baselines.add_best_dam_level(self.p2_cell, self.p2_dam)
        source, pers = (cells, baselines.CELL_PERS_INPUTS) if task == "P2_cell" else (self.p2_dam, ["rel"])
        picked = source.loc[rows.p2_block_rows(source, BLOCK)]
        frame = pd.DataFrame({"uid": picked["uid"].astype(str).to_numpy(), "issue_date": picked["issue_date"].to_numpy(),
                              "region": picked["region"].astype(str).to_numpy(),
                              "y": rows.p2_scored_label(picked, rows.P2_LABELS[task])})
        if task != "P2_cell":
            frame["dam_like"] = picked["dam_like"].to_numpy(dtype=bool)
            frame["persistent"] = picked["persistent"].to_numpy(dtype=bool)
        fitted = baselines.p2_baselines(source, task, BLOCK, population, pers_inputs=pers)
        return self.attach(frame, fitted, ["p_B0", "p_B2", "p_PERS", "p_RAIN", "p_RAIN+"])

    def score_p2(self):
        """RAIN, RAIN+ and B2, then Tidemark (references: all three), for the cell, dam and gradual-dam ratings."""
        for task, subset, column in P2_TASKS:
            source = self.tidemark_out["p2_cell"] if task == "P2_cell" else self.tidemark_out["p2_dam"]
            frame = tidy_keys(pd.DataFrame({"uid": source["uid"].to_numpy(), "issue_date": source["issue_date"].to_numpy(),
                                            "region": source["region"].to_numpy(),
                                            f"p_{self.name('tidemark')}": source[column].to_numpy()}))
            frame = join_baselines(frame, self.p2_reference_frame(task, subset))
            for model in P2_BASELINE_MODELS:
                frame[f"p_{self.name(model)}"] = frame[f"p_{model}"]      # a baseline scored as a model, by name
            keep = frame["y"].notna().to_numpy()
            if subset == "dam_like":
                keep = keep & frame["dam_like"].to_numpy(dtype=bool)
            keys = frame.loc[keep, ["uid", "issue_date"]]
            for model in P2_BASELINE_MODELS:
                self.score(frame.assign(p=frame[f"p_{self.name(model)}"]), task, subset, model, [], "main", keys)
            result = self.score(frame.assign(p=frame[f"p_{self.name('tidemark')}"]), task, subset, "tidemark",
                                list(P2_BASELINE_MODELS), "main", keys)
            if result is None:
                continue
            gain = {model: result["point"]["d_auc_vs_" + self.name(model)] for model in P2_BASELINE_MODELS}
            self.say(f"  {task}: Tidemark AUC {result['point']['auc']:.4f}; AUC gain over "
                     + ", ".join(f"{model} {value:+.4f}" for model, value in gain.items()))

    # =========================================================================
    # Season band and DamDays floor
    # =========================================================================
    def band(self):
        """Region-year coverage of Tidemark's season band on the region's TEST forecasts (primary set).

        Two bands: the pooled band Tidemark ships (inner blocks 2002-2009 and 2009-2016), and the
        single-block band (2009-2016 alone), which PREREG reports alongside.
        """
        out = {}
        blocks = time_block(self.table["issue_date"])
        for kind in KINDS:
            mask = ((blocks == BLOCK) & self.table["dam_like"].to_numpy(dtype=bool) & is_octmar(self.table["issue_date"])
                    & self.table[rows.p1_at_risk_column(kind)].to_numpy(dtype=bool)
                    & self.table["label_ok"].to_numpy(dtype=bool) & self.table[rows.p1_label(kind)].notna().to_numpy())
            part = self.table.loc[mask]
            p = self.on_rows(np.flatnonzero(mask), f"p90_{kind}")
            offsets = unc.block_offsets(part[rows.p1_label(kind)].to_numpy(dtype=float), p, part["region"],
                                        part["issue_date"], BLOCK)
            inner = pd.DataFrame(self.model.info["band"]["offsets"][kind])
            single = band_from_offsets(inner[inner["block"] == "2009-2016"])
            out[kind] = dict(pooled=band_coverage(offsets, *self.model.band[kind]),
                             single_block_2009_2016=band_coverage(offsets, *single),
                             offsets=offsets.to_dict(orient="records"))
        self.say("  season band (pooled), region-years covered: " + ", ".join(
            f"{k} {v['pooled']['covered']}/{v['pooled']['region_years']}" for k, v in out.items())
            + "; single-block: " + ", ".join(
            f"{k} {v['single_block_2009_2016']['covered']}/{v['single_block_2009_2016']['region_years']}"
            for k, v in out.items()))
        return out

    def floor(self):
        """DamDays floor coverage: as issued (all labelled forecasts, primary set) and as displayed (180-day cap)."""
        picked = rows.p1_block_rows(self.table, unc.FLOOR_KIND, BLOCK)
        positions = np.flatnonzero(picked)
        chosen = self.table.loc[picked]
        labelled = chosen["label_ok"].to_numpy(dtype=bool)
        primary = labelled & chosen["dam_like"].to_numpy(dtype=bool) & is_octmar(chosen["issue_date"])
        days_to = chosen[f"lab_tte_{unc.FLOOR_KIND}"].to_numpy(dtype=float)
        follow = unc.followup_days(chosen["issue_date"], self.data_end)
        uid, dates = chosen["uid"].astype(str).to_numpy(), chosen["issue_date"].to_numpy()
        floor, shown = self.on_rows(positions, "floor_days"), self.on_rows(positions, "floor_shown")

        def one(values, mask, boot, cap=None):
            result = floor_coverage(values[mask], days_to[mask], follow[mask], uid=uid[mask], issue_date=dates[mask],
                                    cap_days=cap, n_boot=self.n_boot[boot])
            result.pop("bootstrap", None)
            return result
        out = dict(issued_all=one(floor, labelled, "main"), issued_primary=one(floor, primary, "main"),
                   shown_all=one(shown, labelled, "side", unc.FLOOR_DISPLAY_MAX_DAYS))
        self.say(f"  DamDays floor held: {out['issued_all']['coverage']:.3f} (all), "
                 f"{out['issued_primary']['coverage']:.3f} (primary set); target 0.90")
        return out

    # =========================================================================
    # Everything, in ledger order
    # =========================================================================
    def score_everything(self):
        """Run every score; returns the results dict (scores, curves, band, floor, verdicts)."""
        self.say("P1 (G2, then Tidemark with G2 as reference)")
        self.score_p1()
        self.say("runway curve")
        self.score_curves()
        self.say("P2 season rating (RAIN, RAIN+, B2, then Tidemark)")
        self.score_p2()
        self.say("season band and DamDays floor")
        band, floor = self.band(), self.floor()
        return dict(scores=self.results, curves=self.curve_results, band=band, floor=floor,
                    not_scored=self.not_scored, verdicts=verdicts(self.results, self.name))


# ===========================================================================
# PREREG verdicts and the pre-declared expectations
# ===========================================================================
def p2_rules(result, rain_name):
    """PREREG P2: pass bar (AUC gain over RAIN >= 0.05, dam CI above 0) and kill rule (RAIN within 0.02 AUC)."""
    gain = result["point"][f"d_auc_vs_{rain_name}"]
    ci = result["ci_dam"].get(f"d_auc_vs_{rain_name}")
    return dict(d_auc_vs_RAIN=gain, ci_dam=ci, ci_region_year=result["ci_region_year"].get(f"d_auc_vs_{rain_name}"),
                bar=">= +0.05 with the dam 95% CI above 0",
                passed=bool(gain >= P2_PASS_DAUC and ci[0] > 0) if ci else bool(gain >= P2_PASS_DAUC),
                kill_rule_triggered=bool(gain < P2_KILL_DAUC))


def expectation_rows(values):
    """Each pre-declared expectation with the value got: inside, below or above the declared range."""
    out = []
    for label, (low, high, central) in EXPECTATIONS.items():
        value, ci = values.get(label, (None, None))
        verdict = "not computed" if value is None else (
            "inside" if low <= value <= high else ("below" if value < low else "above"))
        out.append(dict(expectation=label, low=low, high=high, central=central, got=value, ci_dam=ci, verdict=verdict))
    return out


def verdicts(results, name):
    """P1 pass bars (Tidemark and G2), the P2 bar and kill rule, and the expectations table."""
    tm = results[("P1_R30", PRIMARY, "tidemark")]
    g2_result = results[("P1_R30", PRIMARY, "G2")]
    cell = results[("P2_cell", "all", "tidemark")]

    def point_ci(result, metric):
        return result["point"].get(metric), result["ci_dam"].get(metric)
    values = {"R30 BSS vs B0": point_ci(tm, "bss_B0"), "R30 BSS vs B2": point_ci(tm, "bss_B2"),
              "R30 calibration slope": point_ci(tm, "cal_slope"), "R30 CITL": point_ci(tm, "citl"),
              "R30 Tidemark minus G2 (BSS vs B0 units)": point_ci(tm, f"d_bss_B0_vs_{name('G2')}"),
              "P2 cell AUC gain over RAIN": point_ci(cell, f"d_auc_vs_{name('RAIN')}")}
    return dict(p1_pass_bars_tidemark=tm["prereg_pass_bars"], p1_pass_bars_g2=g2_result["prereg_pass_bars"],
                p2_cell=p2_rules(cell, name("RAIN")),
                p2_dam=p2_rules(results[("P2_dam", "dam_like", "tidemark")], name("RAIN")),
                expectations=expectation_rows(values))
