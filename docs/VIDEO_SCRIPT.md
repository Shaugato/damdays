# DamDays: 2-minute demo video script (draft)

**Length: 2:00 at most** (Participant Guide: "2 minutes or less"). Ten beats, timed below. The voice-over is about 275 words with the sealed-result line, a calm 140 words a minute; every key number is also on screen as a caption, because many judges watch muted.

**Story:** spring 2026, a dry start in NSW Central West. A farmer's real question is "how long will my dam last?" DamDays answers in days, shows it worked in the 2018-19 drought, and passes an exam it had never seen.

**Language rules** (from mentor feedback):
- "%" means only **how full** a dam is. Write chances as "3 in 10", never "30%".
- The farmer's headline is **days of water left**.
- Say "the unseen exam" or "a locked region", not "sealed region", "BSS" or "AUC".
- Do not talk about the pre-event research; it is disclosed in [DISCLOSURE.md](../DISCLOSURE.md).

**Before recording:** the app must show real data (no MOCK banner), the frozen model (version L3), and the 2018-19 season in Rewind and Rating. Fill every [square bracket] from the sources in "Where each number comes from" below.

---

## The script, beat by beat

| # | time | on screen (shot) | voice-over | caption |
|---|---|---|---|---|
| 1 | 0:00-0:12 | **Hook.** Runway map of NSW Central West, wide. Slow zoom into the darker dots. (Shot S1) | "Spring 2026, near Dubbo. The satellites show 272 of 894 farm dams in this region already below a third full: the most for a September since the 2019 drought." | **14 Sep 2026 · NSW Central West**<br>**272 of 894 farm dams already below a third full**<br>The most for a September since 2019<br><small>Source: DEA Waterbodies, Geoscience Australia</small> |
| 2 | 0:12-0:24 | **The problem.** One dam's water-history line in its card, dropping through 2018-19. (S2) | "If you run stock, you can see how full your dam is. The hard question is how long it will last: when to cart water, move stock or sell." | **Not "how full?" but "how long?"** |
| 3 | 0:24-0:38 | **Demo: the dam card.** Click a dam on the Runway map; the card opens. Hold on the big number. (S3) | "DamDays reads 38 years of satellite history for every farm dam it can see. Pick a dam. The headline is days: at least [N] days of water above a third, 9 times in 10." | **[N] days of water left · 9 times in 10**<br>Chance of falling below a third by [date]: about [k] in 10 |
| 4 | 0:38-0:46 | **Demo: the runway.** Zoom on the card's six-month curve and its shaded band. (S4) | "Behind it: the six-month chance of falling below a third, and how a wetter or drier season moves it." | **Runway: 30 · 60 · 90 · 180 days**<br>Shaded: a wetter or drier season |
| 5 | 0:46-1:02 | **Demo: Rewind 2018.** Rewind tab, "Forecast made on" set to 1 Nov 2018; the map of forecasts; press **Reveal what happened**; rings appear; the tally panel. (S5) | "Does it work? Rewind to November 2018, in the last big drought. These are the forecasts as they would have been made that day, by a model trained only on data up to mid-2016. Now, reveal what happened." | **1 Nov 2018 · only what was known that day**<br>after the reveal: **[X] of [Y] dams fell below a third · DamDays expected about [E]** |
| 6 | 1:02-1:14 | **Demo: the lender view.** Rating tab, season 2018-19, the two maps side by side; press **Reveal which ran dry**; the scoreboard. (S6) | "Lenders get the same view. Left: a rainfall-only score, like most drought tools use. It can't tell neighbouring farms apart. Right: the DamDays Rating, from each dam's own record. Reveal." | **Left: rainfall only · Right: DamDays Rating**<br>**10 test seasons · one 2 km patch that ran dry, one that did not: DamDays picks the right one 8 times in 10 · rainfall only: about 5 in 10, a coin toss** |
| 7 | 1:14-1:26 | **Proof: the test years.** GitHub: PREREG.md with its commit time (Fri 2 Oct, 09:12). Cut to the pass-mark table in `artifacts/test_results.md`, every row PASS. (S7) | "We wrote the exam before writing any code. Then the frozen model sat ten years it had never trained on, and met every pass mark." | **Exam written first: Fri 2 Oct, 09:12**<br>**Test years 2016-2026, scored once**<br>Nearly a quarter less error than guessing the usual rate<br>"At least N days" held 9 times in 10 (729,749 forecasts) |
| 8 | 1:26-1:40 | **Proof: the unseen exam.** The screen recording of Sat 3 Oct 17:30, sped up with the clock visible: `git status` clean, fingerprints checked (4,711 files match), the run, then the results page. (S8) | "The real exam: a whole region, locked away with a public fingerprint before we started, and opened once, on camera, on Saturday. [Sealed-result line.]" | **The unseen exam · Southern Downs, Granite Belt, New England · 4,711 waterbodies**<br>**Locked before the event · opened once, Sat 3 Oct 17:30 AEST**<br>[sealed numbers, in the same words as beat 7] |
| 9 | 1:40-1:51 | **COP31.** The app's About view, "Why it matters for COP31", or a plain title card. (S9) | "COP31's Awareness priority aims for climate-resilient farming by 2035. DamDays turns free satellite data into the number a farmer can act on: days of water left." | **COP31 · Awareness Across All Areas**<br>Goal: "climate-resilient farming and climate education reaching all of society by 2035" |
| 10 | 1:51-2:00 | **Close.** End card. (S10) | "DamDays. Know how long your water will last, before the dam runs dry." | **DamDays**<br>github.com/Shaugato/damdays<br><small>Data: DEA Waterbodies (Geoscience Australia) · SILO (Queensland Government) · CC BY 4.0</small> |

**Optional opening (only if the weekly text message is built and in the repository when you record).** Replace beat 1's first 4 seconds with the phone mock-up from the app receiving the week's text, then cut to the map. Voice-over: "This is the text a grazier near Dubbo could get each week." Then drop "Spring 2026, near Dubbo." from beat 1 to keep its 12 seconds. Do not show a feature that is not in the repository.

### The sealed-result line (beat 8 and the pitch)

Write it on Saturday from `artifacts/sealed/SEALED_RESULTS.md`, in one sentence of at most 12 words (beat 8 has no room for more), whichever way it went. Templates:

- **Every pass mark met:** "It passed every mark: [a fifth] less error than the usual guess."
- **Some marks met:** "It met [x] of [y] marks; we published the miss, and why."
- **Pass marks missed:** "It fell short of our marks. Every number is published, as promised."

Captions use the same words as beat 7: "[fraction] less error than guessing the usual rate", "'at least N days' held [k] times in 10", "lender rating picks the right 2 km patch [k] times in 10, rainfall [m] in 10". Words for the skill score: 0.10 = "a tenth", 0.15 = "about a seventh", 0.20 = "a fifth", 0.23 to 0.24 = "nearly a quarter", 0.25 = "a quarter". Round down, never up: 0.235 is "nearly a quarter", not "a quarter".

---

## Where each number comes from

Check each one just before recording. All commands run from the repo folder.

| number | value now | source |
|---|---|---|
| Date of the latest satellite looks | 14 Sep 2026 | `app/data/real/meta.json`, `data_through` |
| Farm dams tracked in NSW Central West | 894 | `meta.json`, `coverage.dams` |
| Already below a third at their latest look | 272 | `meta.json`, `coverage.live_status_counts.already_low` (of the 894: 576 have a forecast, 44 have not refilled since their last low, 2 have no clear look in the last 60 days) |
| "The most for a September since the 2019 drought" | September share below a third: 2018 0.64, 2019 0.65, 2020-2025 between 0.08 and 0.23, 2026 0.29 | `app/data/real/history.json` (command below) |
| [N], [k], [date] for the dam card | from the dam you pick | the app's card (helper command below) |
| [X], [Y], [E] for Rewind 1 Nov 2018 | after the app is switched to 2018-19 | the app's tally panel; `meta.json`, `rewind.tallies["2018-11-01"]` (`fell_below_third`, `judged`, `expected`) |
| Lender rating, 10 test seasons | 0.81 against 0.53 for rainfall only | [`artifacts/test_results.md`](../artifacts/test_results.md), P2 table (`P2_cell`) |
| Test years: "nearly a quarter less error", "9 times in 10", 729,749 | skill +0.235; held 0.9002 of 729,749 | [`artifacts/test_results.md`](../artifacts/test_results.md), "In plain words" |
| Exam written first | Fri 2 Oct 2026, 09:12 AEST | commit e0e9b0b on GitHub (adds PREREG.md) |
| Sealed numbers | after Sat 17:30 | `artifacts/sealed/SEALED_RESULTS.md` |

**Honest framing of the hook.** In our own data, September 2026 is the driest September for these dams since 2019, and above the long-run middle (0.29 below a third, against a middle value of 0.26 over the Septembers since 1988), but far from the 2018-19 drought (about 0.64). So the script says "the most since the 2019 drought" and never "a drought like 2019". Say "the 2026 drought" only if an official source (the Bureau of Meteorology or the NSW DPI drought indicator) supports it on the day you record, and name that source on screen.

**Live fact** (beat 1):

```
.venv/Scripts/python.exe -c "import json; m=json.load(open('app/data/real/meta.json')); c=m['coverage']; print(m['data_through'], m['model']['version'], c['dams'], c['live_status_counts'])"
```

Today (the L3 export of 2 Oct 2026, 21:47 AEST) it prints `2026-09-14 L3 894 {'forecast': 576, 'already_low': 272, 'not_refilled': 44, 'no_recent_look': 2}`. The dam statuses come from the satellite looks, not from the model, so they change only if the satellite data is updated; check anyway.

**September comparison** (beat 1):

```
.venv/Scripts/python.exe -c "
import json
h = json.load(open('app/data/real/history.json'))
first_year, first_month = int(h['first_month'][:4]), int(h['first_month'][5:])
for year in range(first_year, int(h['last_month'][:4]) + 1):
    i = (year - first_year) * 12 + (9 - first_month)   # September of that year
    levels = [d['level_pct'][i] for d in h['by_dam'].values() if 0 <= i < len(d['level_pct']) and d['level_pct'][i] is not None]
    if len(levels) >= 300:
        print(year, len(levels), round(sum(v < 30 for v in levels) / len(levels), 3))
"
```

Each line: year, dams with a clear September look, share of them below a third. This uses each dam's September median level, so 2026 shows 0.29 (of 878 dams) where the latest-look count gives 272 of 894 (0.30). Both are "about 3 in 10".

**Picking the dam for beats 3 and 4:**

```
.venv/Scripts/python.exe -c "
import json
f = json.load(open('app/data/real/forecasts.json'))
live = [i for i in f['issues'] if i['kind'] == 'live'][0]
for r in live['rows']:
    if r['status'] == 'forecast' and 40 <= (r['damdays_days'] or 0) <= 90 and 0.3 <= r['chance'] <= 0.6:
        print(r['dam_id'], 'level', r['level_pct'], 'chance', r['chance'], 'days', r['damdays_days'], 'look', r['issued_on'])
"
```

Pick a dam that is fairly full today, with 40 to 90 days and a chance of 3 to 6 in 10, so the card tells a clear story. Read [N], [k] and [date] off the card itself.

---

## Shot list (record in this order)

| shot | where | what to do | length to capture |
|---|---|---|---|
| S1 | app `#runway` | Map fitted to the region. Start wide, slow zoom (scroll) towards a cluster of dark dots. | 20 s |
| S2 | app `#runway` | Open a dam whose water-history line shows the 2018-19 fall (beat 2 uses only the line). | 15 s |
| S3 | app `#runway` | Click the chosen dam; hold 5 s on the card's big "days" number. | 20 s |
| S4 | app `#runway` | Same card: hover along the runway curve; keep the shaded band in view. | 12 s |
| S5 | app `#rewind` | Choose "1 Nov 2018"; pause 3 s on the forecast map; press **Reveal what happened**; hold on the tally. | 30 s |
| S6 | app `#rating` | Choose season 2018-19; pause on the two maps; press **Reveal which ran dry**; hold on the scoreboard. | 25 s |
| S7 | GitHub, then the repo | The commit that adds PREREG.md (shows "Fri 2 Oct, 09:12"); then `artifacts/test_results.md`, scrolled to "PREREG pass bars and the kill rule". | 20 s |
| S8 | terminal + repo (Sat 3 Oct) | The full sealed-opening recording, 17:15 to about 18:00 (runbook: [SEALED_OPENING.md](SEALED_OPENING.md)). Keep the raw file as evidence; the video uses a 14-second sped-up cut with a visible clock. | whole run |
| S9 | app `#about` | Scroll to "Why it matters for COP31". (Or a title card.) | 10 s |
| S10 | title card | Name, repository address, data credits. | 8 s |

## Recording checklist

- [ ] Browser at 1920 x 1080, page zoom about 125% so text reads on a phone; bookmarks bar hidden; no other tabs, emails or personal data on screen.
- [ ] App shows real data: no MOCK banner; About → "This page's data" says version L3; Rewind lists 1 Nov 2018; Rating lists 2018-19.
- [ ] Every [square bracket] filled from the sources above, and the captions match the voice-over.
- [ ] Captions burned into the video.
- [ ] Final cut is **2:00 or less**; exported as 1080p MP4.
- [ ] No music, or music you made or are licensed to use; list it in [DISCLOSURE.md](../DISCLOSURE.md).
- [ ] Add the video and screen-recording tools to [DISCLOSURE.md](../DISCLOSURE.md) ("Tools").
- [ ] The video link opens without asking for access.
