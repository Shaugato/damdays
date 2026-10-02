# The scorecard, in plain language

Every DamDays forecast is judged by the same code, on the same rows, with the same numbers. The main model (Tidemark), the benchmark (G2) and the simple baselines all go through it. This page explains what each number means and how to read it. You do not need a statistics background.

Code: [`damdays/evaluation/`](../damdays/evaluation/). Tests: `tests/test_eval_*.py`.

## 1. What is being judged

A forecast is a probability: "a 30% chance this dam falls below a third of full in the next 90 days". When we look back, each forecast has an answer. The event either happened (1) or did not (0). The scorecard compares the forecasts with the answers.

| task | the question | issued |
|---|---|---|
| `P1_R30` | Will the dam fall **below a third** of full within 90 days? (the farmer's headline) | at every clear satellite look |
| `P1_D0` | Will the dam be **fully dry** within 90 days? | same |
| `P1_D0g` | Will it dry out **gradually** (a real dry-out, not a satellite glitch)? | same |
| `P2_dam`, `P2_cell` | Will the dam (or every farm dam in a 2 km cell) run dry this summer (Oct-Mar)? (the lender rating) | each 1 July |
| `R30_curve`, `D0_curve` | The same questions at 30, 60, 90 and 180 days (the runway curve) | at every look |

`P1_*_sens` tasks are the pre-registered sensitivity rows. They use every at-risk forecast, including those whose 90-day window had fewer than 3 clear looks; if no event was seen, the answer counts as 0.

**Which years.** VAL (2009-2015) is used to make every design choice. TEST (July 2016 to June 2026) is used once per model, for the final score (section 5). The scorecard reads the block from the forecast dates, so a TEST score cannot be passed off as anything else.

**Which dams and dates (subsets).**
- `dam_like`: waterbodies that look and behave like farm dams.
- `persistent`: dams that almost never dry out. This is the harder subset.
- `octmar`: forecasts issued from October to March, the months when dams run down.
- `at_risk`: the dam was not already low when the forecast was made. Forecasting "it will stay empty" is too easy, so those rows are left out.
- **`primary`** = dam-like + Oct-Mar + at risk. This is the pre-registered headline set.

## 2. The numbers

### Brier skill score (BSS): "how much better than a simple rule?"

The **Brier score** is the average of (forecast - answer)². Saying 90% when the event happens costs 0.01. Saying 90% when it does not costs 0.81. Lower is better. On its own the number is hard to read, so we compare it with a simple rule:

> BSS = 1 - (model's Brier score) / (simple rule's Brier score)

- **BSS = +0.20**: the model removes 20% of the simple rule's error.
- **BSS = 0**: no better than the simple rule.
- **BSS below 0**: worse than the simple rule.

We use two simple rules:
- **B0, the base rate.** "In this region in this month, about X% of dams fall below a third within 90 days." It knows the season and the region, but nothing about the dam.
- **B2, the dam's own track record.** "This dam has fallen below a third after X% of its past forecasts." Only past forecasts whose answer was already known count. B2 is a much tougher rule to beat, because some dams simply run dry more often than others.

Beating B0 shows the model knows something. Beating B2 shows it knows more than "this dam usually runs dry".

### AUC: "does it rank dams the right way round?"

Pick one forecast where the event happened and one where it did not. The AUC is the chance that the model gave the first one the higher probability. Ties count as half.

- **0.5** is a coin toss. **1.0** ranks perfectly. **0.8** means the right way round 8 times in 10.
- AUC only checks the **order**, not whether "30%" really means 30%. That is calibration's job.

For the season rating we also report:
- **AUC within a season:** which dams fail in a given summer. This is what a lender needs.
- **AUC within a dam (or cell):** which summers a given dam fails.

### Calibration: "does 30% really mean 30%?"

If we collect every forecast that said about 30%, roughly 30% of those dams should have had the event. Two numbers check this:

- **Calibration slope** (ideal 1.0). Below 1: the forecasts are too extreme (too sure of themselves). Above 1: too cautious. The pre-registered bar is 0.8 to 1.2.
- **Calibration-in-the-large, CITL** (ideal 0.0). This is the shift, on the log-odds scale, that would make the forecasts right on average.
  - **Negative:** the forecasts were too high (more alarm than events).
  - **Positive:** the forecasts were too low.
  - A shift of 0.3 means the true odds were about 1.35 times (or 1/1.35 times) the forecast odds.

The result also shows the **base rate** (how often the event really happened) next to the **mean forecast**. If calibration is good, the two are close.

### Precision at 50% recall: "if you act on the worst-looking dams, how often are you right?"

Start with the highest forecasts and work down the list until you have flagged **half of all the dams that really had the event**. Precision is the share of the flagged dams that really had the event. **0.54** means about 1 in 2 flagged dams was a true alarm. Compare it with the base rate: if 15% of forecasts have events, 0.54 is about 3.6 times better than flagging at random.

### Paired difference vs a reference model: "is it really better than the benchmark?"

The pre-registered benchmark is G2. We score both models on **exactly the same rows** and take the difference:

> paired gain = BSS vs B0 (Tidemark) - BSS vs B0 (G2)

The difference is computed inside every bootstrap resample (section 3). Luck that both models share (an easy year, an easy dam) therefore cancels out, so the paired interval is much narrower than you would get by comparing two separate intervals. We also report the AUC difference. A paired gain whose interval sits entirely above 0 means the model is reliably better.

## 3. The 95% intervals: "how sure are we?"

Every number comes with two ranges in brackets. For example, `+0.233 [+0.220, +0.245] ry [+0.210, +0.257]`.

- **First bracket: the dam bootstrap.** Draw a fresh set of dams at random from the ones we have (some twice, some not at all), recompute the number, and repeat 500 times. The middle 95% of the results is the interval. We draw **whole dams**, not single forecasts, because forecasts for the same dam are not independent. Drawing single forecasts would make the intervals look narrower than they should be.
- **`ry` bracket: the region-year bootstrap.** The same idea, but drawing whole (region, July-June year) blocks. A dry year hits every dam in a region at once, so this answers a different question: "would the result hold with a different run of years?" TEST holds only about 20 region-years, so this interval is rough. It is usually the wider of the two, and it is the more cautious one to quote.
- **"CI above 0"** means even the low end of the interval is positive: the skill is unlikely to be luck.
- The random seeds are fixed (2026 and 2027). The same predictions always get the same intervals, so anyone can reproduce them.

## 4. The runway curve, the season band and the floor

**Runway curve, horizon by horizon.** The curve gives the chance of an event within 30, 60, 90 and 180 days. Each horizon is scored against its **own** base rate. A 30-day forecast is never compared with a 90-day base rate, which would flatter it. A runway curve must never go down as the horizon gets longer, so the scorecard also counts curves that "fall" (expected: 0). A helper, `crossing_share`, checks that the below-a-third curve never sits below the fully-dry curve (a dry dam is also below a third).

**Season band.** Some years are drier or wetter than any model expects. Each forecast is therefore shown with a band built from an earlier backtest: the lowest and highest "year offsets" seen there. A year's offset is the CITL on that region-year's forecasts. The band **covers** a region-year when that year's own offset falls inside it. The check also lists every year that fell outside the band, marked "drier than the band" or "wetter than the band".

**The DamDays floor** ("at least N days above a third, 90% confidence"). The floor holds when the dam did not fall below a third before day N. About 90% of floors should hold; 0.88 to 0.92 counts as on target.

There is one subtle rule. A forecast is judged only if we could watch the dam for at least N days, **whatever happened**. Suppose N = 60 but the data stops 30 days after the forecast. If we counted that row only when the dam failed early, the floor would look worse than it is. In the test world this mistake would show 0.856 instead of the true 0.900.

## 5. The TEST ledger: one look per model

If ten versions of a model are scored on the test years and only the best is reported, the "test" score is no longer a test. The ledger ([`artifacts/test_ledger.csv`](../artifacts/test_ledger.csv)) makes that hard to do, even by accident.

- **Every TEST scoring call is written down:** the time, the model, the task, dev or sealed region, a fingerprint (hash) of the predictions, and what happened. Refused calls and dry runs are written down too.
- **First call:** status `new`.
- **Later calls are allowed only with byte-for-byte identical predictions** (`same_predictions`). This lets the same forecasts be scored on other subsets. Change a single probability in its 17th decimal place and the call is **refused**, before any TEST number is computed.
- **There is no override switch.** A fixed model must take a new name, and both rows stay on the ledger.
- **The benchmark must be honest too.** A paired comparison against G2 is allowed only if the G2 predictions passed in are exactly the ones G2 was scored with.
- The development regions and the sealed region are separate tests, each with one look.
- **Dry runs** check every input and the ledger rule but compute nothing, so a crash cannot waste the one look.
- TEST results are always saved (JSON plus a markdown row), even if the caller asks not to save.

## 6. The pre-registered pass bars

[PREREG.md](../PREREG.md) set these before any code was written. For R30, primary set:

| bar | required |
|---|---|
| BSS vs B0 | at least +0.10, with the dam interval entirely above 0 |
| BSS vs B2 | at least +0.05 |
| Calibration slope | between 0.8 and 1.2 |

The scorecard checks them mechanically. The result is in `prereg_pass_bars` in the JSON.

## 7. How we know the scorecard itself is right

The tests build made-up worlds where every forecast's **true** probability is known. From those, the true scores can be worked out exactly and compared with what the scorecard reports (seeds as in the tests):

| check | expected | scorecard |
|---|---|---|
| perfect forecast, BSS vs B0 (60,000 forecasts) | 0.2224 | 0.2203 [0.2107, 0.2284] |
| perfect forecast, BSS vs B2 | 0.1711 | 0.1660 [0.1600, 0.1707] |
| perfect forecast, AUC | 0.7962 | 0.7953 [0.7902, 0.8007] |
| perfect forecast, calibration slope / CITL | 1 / 0 | 0.997 / -0.004 |
| forecast that ignores the weather year, BSS vs B0 / AUC | 0.2042 / 0.7856 | 0.2020 / 0.7838 |
| paired gain, perfect vs weather-blind | +0.0182 | +0.0183 [0.0163, 0.0203] |
| dam interval holds the truth, 40 redrawn worlds | about 95% | 92.5% (37 of 40) |
| over-confident forecast (log-odds x2), slope | 0.50 | 0.498 |
| forecast 0.5 too high in log-odds, CITL | -0.50 | -0.491 |
| correct floor, coverage (full follow-up / half cut short) | 0.900 / 0.900 | 0.900 / 0.901 |

The B2 row is a fair example of how intervals behave. In this one world the truth (0.1711) sits just above the interval. That should happen about 1 time in 20, and it is why the test also checks coverage over 40 redrawn worlds instead of a single draw. A separate run of 200 redraws found the dam interval's implied spread (0.0032) slightly wider than the real spread (0.0029), which is the cautious direction.

AUC, precision and the calibration fit are also checked against scikit-learn and hand-worked examples.

## 8. For developers

```python
from damdays.evaluation import score, score_curve

result = score(pred_df, "P1_R30", "primary", model="tidemark", refs=["G2"])
# pred_df columns: uid, issue_date, region, y, p, p_B0, p_B2, p_G2, dam_like, at_risk
#   (or pass baselines=table to join p_B0 / p_B2 on uid + issue_date)
# expected_keys=keys checks the scored rows are exactly the official ones.
# dry_run=True checks everything (and the ledger) without computing a number.

curve = score_curve(curve_df, "R30_curve", "primary", model="tidemark")
# curve_df columns: p_30, p_60, p_90, p_180, y_30 ... y_180 (blank = not known yet),
#   p_B0_30 ... p_B0_180, optional p_B2_30 ... p_B2_180
```

Outputs go to `artifacts/scorecard/<arena>_<block>/<task>/<model>__<subset>.json`. One row per call is added to `artifacts/scorecard/scorecard_<arena>_<block>.md` (`curves_...md` for curves).

Bootstrap time is about 40 seconds for 145,000 forecasts with 500 resamples of each kind. Use `n_boot=0` for quick looks on VAL.
