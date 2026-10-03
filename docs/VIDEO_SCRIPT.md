# DamDays: 2-minute demo video script (v4)

**Length: 2:00 at most** (Participant Guide: "2 minutes or less"). Ten beats, timed below. The voice-over is **240 words** with the longest possible sealed-result line (12 words). At draft 1's measured pace (2.25 words a second, numbers said in full) that is about 107 seconds of voice, and about **1:57** with the pauses, the opening buzz and the end card: 3 seconds spare. Every key number is also a caption, because many judges watch muted.

**The story in one line.** A farmer's phone buzzes with this week's DamDays text: how many days of water each dam has left. We say who it is for, what they do with it, and show in three pictures why the number can be trusted.

**v2, Sat 3 Oct 2026.** Rewritten from a second mentor's advice (Sat 3 Oct, research/MENTOR_FEEDBACK.md) and a pressure test of draft 1 against what is built:

| asked for | where v2 answers it |
|---|---|
| Accuracy on data the model was not trained on, as recent as possible, shown as a picture | Beat 6: "what we said vs what happened" over ten years to June 2026. Beat 8: the unseen exam also covers forecasts to June 2026 |
| How it keeps up as the climate shifts | Beat 7: better than the usual guess in every year from 2016-17 to 2025-26, dry and wet; refit on new looks; each dam corrected by its own record. The caption admits the drift that makes refitting necessary |
| Dam by dam | Beats 4 and 5: each dam's line in the text, and Dam 1's card with our record on that dam (Dam 5's card shows a dam's own correction, "runs wetter than similar dams") |
| One audience: farmers | The lender beat is cut. The COP31 shot is a title card, not the About page (whose third point is about lenders) |
| Describe the target farmer precisely | Beat 2, one sentence, from [TARGET_FARMER.md](TARGET_FARMER.md) |

Fixed from the pressure test: the 2018-19 replay is out (its "248 dams" were 782 forecasts for 366 dams; 2018-19 is one bar in beat 7); the days and the chance now agree out loud; "9 in 10" is said as a built-in safety margin, not a hit rate; the phone is captioned as a mock-up and the MAP reply as not built; "% full" and the satellite date are explained on screen; the COP31 beat names the Awareness track and the Global Goal on Adaptation.

**v3, Sat 3 Oct 2026, evening.** The farm in the text is now **Farm E (near Mudgee)**. An aerial-photo check found that the Dubbo demo farm used until then was not a farm (its waterbodies were treatment ponds, a racecourse pond, a town-edge pond and a stretch of river), so it was set aside ([BUILD_LOG.md](../BUILD_LOG.md)). Beats 1, 3, 4 and 5 changed with it; the beat structure did not (beats 3 to 5 moved by a second). A 0% dam is now "no water seen", never "dry". The voice-over is 239 words (it was 237). The sealed opening moved from the pre-registered 17:30 AEST on Sat 3 Oct to after the app build.

**v4, Sun 4 Oct 2026.** The text's first line now reads "Fri 2 Oct (dams seen 13 Sep)" (it was "(satellite 13 Sep)"; same length, still 159 of 160 places). Beat 8 says in plain words what the unseen exam is: a third farming region whose satellite data we downloaded and fingerprinted before the event and then never opened or used, kept aside for one final check. It is opened once, on camera, on Sun 4 Oct (clocks went forward at 02:00, so times on the day are AEDT). Beat 6 drops "Is it right?" to make room, so the voice-over is 240 words with the longest sealed line, the limit (a recount found beat 4 had 3 more words than counted).

**Language rules** (from mentor feedback):
- **One audience: farmers.** No lenders, banks or agribusiness in the voice-over or on screen. The only "bigger idea" is the end card's small line: the satellite record covers all of Australia.
- **"%" means only how full a dam is.** A chance is written "1 in 10", never "10%", on screen and out loud. "~80% full" is the share of the dam's usual full water surface the satellite sees wet, not its depth or volume.
- **The headline is days of water** before the dam drops below a third: "at least 68 days". "A third" is DamDays's early-warning line, not empty.
- **A 0% dam is "no water seen"**, never "dry" or "looks dry": the satellite saw no water at its last clear look, and one look can be wrong.
- **Counted, they are "dam-sized waterbodies, mostly farm dams"**, not "farm dams".
- **"9 in 10" is only for the days-left promise**, and always as a built-in safety margin ("built to hold 9 times in 10"), never as "right 9 times in 10". It is not a hit rate.
- **We, not names.** Say "we" throughout; the team is named once, in the pitch's team section, not in the video.
- **Plain words.** Never say "AUC", "Brier", "skill score", "calibration" or "sealed region". The skill number is said as a fraction, rounded down: +0.235 is "nearly a quarter less error than the usual guess".
- **Keeping up, truthfully.** Say "refit" and "corrected by its own record". Never "learns by itself", "evolves" or "monitored every year": automatic refits and drift checks are not built yet.
- **"Unseen" means only the sealed region,** called "the unseen exam": a third farming region whose satellite data we downloaded and fingerprinted before the event and then never opened or used, kept aside for one final check. The test years are "ten years it never trained on": we looked at them before the event, so they are not unseen.
- **Illustrative, never real people.** The farmer in beat 2 is typical survey values, not a real family. The farm in the text is a demo farm: its 5 dams and their forecasts are real, the homestead point is not. Never name a family or a property.
- **No pre-event research** in the video. It is disclosed in [DISCLOSURE.md](../DISCLOSURE.md).

---

## The text on the phone (beats 1, 4 and 10)

The real text made on Fri 2 Oct 2026 for **Farm E (near Mudgee)**, copied from [`outbox/2026-10-02.json`](../outbox/2026-10-02.json) (`farm-e`). It fits in one SMS (159 of 160 places). Show it exactly as it is:

```
Fri 2 Oct (dams seen 13 Sep)
Dam 1 ~80% full: at least 68 days before it drops below 1/3
Dam 3: no water seen
Other 2 dams: 3 months+
Reply MAP for 1 more dam
```

How to read it: "dams seen 13 Sep" is the date of the satellites' last clear look at the farm's dams. Dam 1 is the dam closest to the homestead. Its forecast starts from that look (13 Sep): at least 87 days from then, which is **68 days from Fri 2 Oct**. Its chance of being below a third by 12 Dec is 0.089, "1 in 10": so 68 days is the cautious figure, and the dam will most likely last longer. On the six-month chart the DamDays day is 9 Dec, where the curve reads about 1 in 10 (the two numbers come from two models, and on this dam they agree). "Dam 3: no water seen": the satellite saw no water at its 13 Sep look, and one look can be wrong. "Other 2 dams: 3 months+" are Dams 5 and 2; "Reply MAP for 1 more dam" is Dam 4 (~33% full, no forecast until it refills to 60% full). On aerial photos all 5 are farm dams. The phone is drawn (a mock-up); nothing is sent unless someone runs the sender with their own SMS account's keys, and the MAP and STOP replies are not built yet ([notify/MESSAGE_SPEC.md](../notify/MESSAGE_SPEC.md), section 7).

## The farmer (beat 2)

One sentence, illustrative: "It's for family sheep and cattle farms, say 1,500 hectares and 2,000 sheep, where stock drink from dams." Typical values from ABARES farm surveys, 2022-23 to 2024-25 ([TARGET_FARMER.md](TARGET_FARMER.md)): most often 300 to 1,500 ha; mixed farms run 1,711 to 2,931 sheep and 249 to 431 cattle; 63 to 107 work weeks a year in all (1 to 2 people); stock water from farm dams; mostly Outer Regional Australia. The hard filter is a dam of at least 0.54 ha that the satellites can see. The demo farm in the text has 5 such dams within 3 km, which is the best case: a typical target farm sees 1 or 2.

---

## Before recording

Every box must be ticked, or the beat that needs it changes as noted. The draft-1 ticks (Fri 2 Oct, 23:58) no longer count: the app has changed since (the Proof view is new; `index.html`, `main.js`, `about.js`, `style.css` and `bundle.js` were modified), so check everything again.

- [ ] **Real data.** No MOCK banner; About's methods and scores for specialists say version L3.
- [ ] **My farm** opens on Farm E (beat 5). Dam 1's card shows ~80% full at the 13 Sep look, at least 68 days counted from Fri 2 Oct, a chance of 1 in 10 by 12 Dec, the next six months with the DamDays day (9 Dec) marked, and our record on this dam: held 380 of 428 times. Dam 5's card says "Runs wetter than similar dams: it fell below a third less often than the model expected."
- [ ] **The map shots show farms, not town.** Beat 5 shows Farm E's whole 3 km circle: the map shows only Eurunderee, vineyards and creeks, no town. Keep the circle at 3 km: Dam 5 sits on its edge (3.0 km) and drops out at any smaller size. Do not show aerial imagery next to a dam's status: the imagery is undated (Dam 3 holds water on it, while no water was seen at its 13 Sep look). Beat 3 shows the whole region.
- [ ] **No "dry" on screen for a 0% dam:** it is "no water seen".
- [ ] **Proof, part 1** (beat 6): ten dots near the diagonal; its table says "3 in 10: 4,864 of 17,013".
- [ ] **Proof, part 2** (beat 7): ten bars, all above zero, from "a fifth" (2020-21) to "a quarter" (2025-26); drier years 2017-20 and 2023-26 shaded; the "at least N days" dots from 872 to 927 in 1,000 (2023-24 at 872, below the band).
- [ ] **The app follows the wording rules.** No "%" in the app means a chance.
- [ ] **The sealed-result line is written** (beat 8) by `scripts/21_publish_sealed.py`, after the opening (Sun 4 Oct, after the app build), and read against `artifacts/sealed/SEALED_RESULTS.md`. Proof's "Unseen exam" card shows the scored panel.
- [ ] **Every [square bracket] is filled**, from "Where each number comes from" below.

---

## The script, beat by beat

| # | time | on screen (shot) | voice-over | caption |
|---|---|---|---|---|
| 1 | 0:00-0:11 | **The text arrives.** Two seconds of the phone buzzing, no voice. Then the text, full screen, every line readable. (S1) | "Friday morning. A farmer's phone buzzes. No app needed: one text a week, each dam's days of water." | The text itself (above)<br><small>Mock-up of this week's real text for a demo farm near Mudgee: real forecasts for its 5 farm dams; not a real homestead · the MAP reply is not built yet</small> |
| 2 | 0:11-0:22 | **Who it's for.** A plain card with the farmer's profile. No photos of real people or properties. (S2) | "It's for family sheep and cattle farms, say 1,500 hectares and 2,000 sheep, where stock drink from dams. How long each dam lasts is guesswork." | **Who it's for** (illustrative: typical values from ABARES farm surveys, 2022-23 to 2024-25)<br>Family sheep and cattle farm · about 1,500 ha · about 2,000 sheep and 250 cattle · 1 to 2 people's work · stock water from farm dams<br><small>Needs at least one dam of 0.54 ha or more, big enough for the satellites to see · today: drive the water run and do the sums by hand</small> |
| 3 | 0:22-0:33 | **A drier spring.** The Runway map of the whole region, its dark dots already below a third; a slow drift across it. (S3) | "This spring is drier: 272 of the 894 dam-sized waterbodies we track, mostly farm dams, are already below a third, the most for September since 2019." | **NSW Central West · latest satellite looks to 14 Sep 2026**<br>**272 of the 894 dam-sized waterbodies we track (mostly farm dams) already below a third full**<br>The most for a September since the 2019 drought<br><small>Source: DEA Waterbodies, Geoscience Australia</small> |
| 4 | 0:33-0:45 | **The text, line by line.** Back to the phone; the Dam 1 line lights up, then the Dam 3 line. (S4) | "Dam 1 has at least 68 days before dropping below a third: a cautious figure, built to hold 9 times in 10 across all dams. Dam 3: no water seen." | **~80% full = how full it is** (share of its usual full water surface, not depth)<br>**at least 68 days = days before it drops below a third (cautious)**<br>Built to hold 9 times in 10 across all dams (a little less often for spring looks)<br>**no water seen** = the satellite saw no water at its last clear look; one look can be wrong<br><small>A third: DamDays's early-warning line, long before a dam is empty · "dams seen 13 Sep" = the last clear satellite look; days are counted from the day of the text</small> |
| 5 | 0:45-0:53 | **Dam by dam, in the app.** My farm on Farm E: the whole 3 km circle with its five numbered dams. Tap Dam 1: its card opens on the days and the chance; slide down to the next six months (the DamDays day, 9 Dec, marked; the shaded band in view) and to our record on this dam. (S5) | "The app adds the chance: 1 in 10 by mid-December. And every dam shows our record on it." | **Dam 1 · ~80% full on 13 Sep · at least 68 days**<br>**Chance it drops below a third by 12 Dec 2026: 1 in 10**<br>Our record on this dam: held 380 of 428 times (a little under 9 in 10: its card says give the days extra margin) · on the farm's 5 dams, 1,640 of 1,767<br><small>The next six months · the DamDays day (9 Dec) marked · shaded: a wetter or drier season</small> |
| 6 | 0:53-1:07 | **Proof 1: what we said vs what happened.** The Proof view, part 1: ten dots on the diagonal; hold on the "3 in 10" dot. (S6) | "Over ten years it never trained on, to June 2026: when it said 3 in 10, about 3 in 10 did. The same at every level." | **What we said vs what happened · ten test years, July 2016 to June 2026, scored once**<br>**Said 3 in 10: 4,864 of 17,013 fell below a third within 90 days**<br>All 10 groups matched what we said, to the nearest 1 in 10 · 142,938 forecasts, 29,415 fell<br><small>The model learned only from data before July 2016 · we looked at these years before the event, so they may flatter it slightly: the unseen exam is the clean test</small> |
| 7 | 1:07-1:22 | **Proof 2: it held up year after year.** The Proof view, part 2: the ten bars, all above zero, with the drier years shaded; then the "at least N days" dots. (S7) | "It held up as conditions changed: nearly a quarter less error than the usual guess, better every year, dry or wet. It's refit on new satellite looks, each dam corrected by its own record." | **Less error than the usual guess in all 10 years: from a fifth (2020-21) to a quarter (2025-26) · nearly a quarter overall**<br>Drier years shaded: 2017-20 and 2023-26 · "at least N days" held 872 to 927 times in 1,000 each year<br>Today's forecasts: refit on every satellite look to 14 Sep 2026 · each dam's forecast corrected by its own track record<br><small>Not refitted during the ten test years: in wet years its chances ran high, in some dry years a little low, which is why it is refit · automatic weekly refits: next</small> |
| 8 | 1:22-1:37 | **Proof 3: the unseen exam.** The opening's screen recording (Sun 4 Oct, AEDT), sped up with the clock visible: `git status` clean, 4,711 of 4,711 fingerprints matched, the run, the result. End on the Proof view's "Unseen exam" card. (S8) | "The unseen exam: a third farming region, fingerprinted before the event, never opened. Ten years to June 2026, opened once, on camera. <!-- SEALED:START line -->[Sealed-result line: opens Sat 3 Oct 17:30 AEST.]<!-- SEALED:END -->" | **The unseen exam · Southern Downs, Granite Belt, New England · 4,711 waterbodies**<br>A third farming region: its satellite data downloaded and fingerprinted before the event, then never opened or used, kept aside for one final check<br>Forecasts July 2016 to June 2026 · fingerprints committed Fri 2 Oct, 09:12 AEST · opened once, on camera, [the opening's date and time, from the recording] · published whatever it showed<br><!-- SEALED:START caption -->[sealed numbers: opens Sat 3 Oct 17:30 AEST]<!-- SEALED:END --><br><small>Burn in only the first two lines of the result (see "The sealed-result line")</small> |
| 9 | 1:37-1:47 | **COP31.** A plain title card, not the About page (S9). | "That's COP31's Awareness track: helping farmers adapt, with climate information they can act on, for fewer stock losses and less waste." | **COP31 · Awareness Across All Areas: helping farmers adapt**<br>Each dam's days of water, by text, every week<br><small>Global Goal on Adaptation (UAE Framework for Global Climate Resilience): targets on water scarcity and on climate-resilient food and farming · aim: fewer stock losses, less wasted feed, better use of on-farm water (not yet measured)</small> |
| 10 | 1:47-1:55 | **Close.** The phone with the text, then the end card. (S10) | "DamDays: days of water, by text, every week." | **DamDays**<br>github.com/Shaugato/damdays<br><small>The satellite record covers all of Australia; tested so far in NSW Central West and western Victoria / SE South Australia · Data: DEA Waterbodies (Geoscience Australia) · SILO (Queensland Government) · CC BY 4.0</small> |

**Words per beat** (recounted Sun 4 Oct, every word as written; beat 4 is 30, not the 27 counted before): 18, 25, 26, 30, 18, 26, 34, 22 plus the sealed line (at most 12), 21, 8. Total 240 (238 if the line is the 10-word partial-pass one).

**If the cut runs over 2:00,** trim in this order (the captions keep each point): "The same at every level." (beat 6); "for fewer stock losses and less waste" (beat 9). Together about 12 words, about 5 seconds. Do not cut the sealed line, "to June 2026", "built to hold 9 times in 10" or "refit".

**Reading the numbers aloud:** "fifteen hundred hectares", "two thousand sheep", "two hundred and seventy-two of the eight hundred and ninety-four", "twenty-nineteen", "sixty-eight days", "one in ten", "June twenty twenty-six", "COP thirty-one".

### The sealed-result line (beat 8 and the pitch)

<!-- SEALED:START -->
[The sealed-result line: opens Sat 3 Oct 17:30 AEST. After the opening, `scripts/21_publish_sealed.py` writes it here from the results, by the templates below.]

<!-- SEALED:END -->

`scripts/21_publish_sealed.py` writes it after the opening, from `artifacts/sealed/sealed_results.json`, in one sentence of at most 12 words, whichever way it went. Read it against `artifacts/sealed/SEALED_RESULTS.md` before recording. Templates:

- **Every pass mark met:** "It passed every mark: [a fifth] less error than the usual guess." (If that is over 12 words, as with "nearly a quarter": "Every mark passed: nearly a quarter less error than the usual guess.")
- **Some marks met:** "It met [x] of [y] marks; we published the miss."
- **Pass marks missed:** "It fell short of our marks. Every number is published, as promised."

Words for the error number (the skill score): 0.10 = "a tenth", 0.15 = "about a seventh", 0.20 = "a fifth", 0.225 to 0.249 = "nearly a quarter", 0.25 = "a quarter". Round down, never up: 0.235 is "nearly a quarter", not "a quarter".

Three things scripts/21 writes that v2 handles differently (scripts/21 has changed only its wording since, never what it computes or copies):
- **The caption marker gets three lines; burn in only the first two** (the pass marks met, then the error words and "at least N days" held). The third line is the pre-registered season rating, built with lenders in mind; it stays in the pitch's evidence table, where every pass mark is reported, but this farmer video does not show it.
- **It calls this "beat 5"**, from draft 1. In v2 it is beat 8.
- **If it says "Kill rule triggered ... cut or reword beat 8"**, nothing in v2 needs cutting: there is no lender claim in the video. Keep beat 8's sealed line as written.

---

## Where each number comes from

Check each one just before recording. All commands run from the repo folder.

| number | value now | source |
|---|---|---|
| The text on the phone | Farm E (near Mudgee), Fri 2 Oct 2026, 159 of 160 places | [`outbox/2026-10-02.json`](../outbox/2026-10-02.json), `farm-e`; made by [`scripts/16_weekly_texts.py`](../scripts/16_weekly_texts.py) |
| The farmer: about 1,500 ha, 2,000 sheep, 250 cattle, 1 to 2 people, stock water from dams | illustrative, inside the ABARES ranges for 2022-23 to 2024-25 (land most often 300 to 1,500 ha; mixed farms 1,711 to 2,931 sheep and 249 to 431 cattle; 63 to 107 work weeks a year) | [TARGET_FARMER.md](TARGET_FARMER.md), "Meet Kath and Graeme" and "The target farmer in one table" (ABARES Farm Data Portal) |
| Latest satellite looks: 14 Sep 2026 | `data_through` 2026-09-14 | `app/data/real/meta.json` |
| 272 of the 894 dam-sized waterbodies (mostly farm dams) already below a third | 894 tracked: 576 with a forecast, 272 already below a third, 44 not refilled since their last low, 2 with no clear look in the last 60 days; 148 of the 272 read 0% (no water seen) | `meta.json`, `coverage.live_status_counts` (command below); the 148: `forecasts.json`, live rows with `level_pct` 0 |
| "The most for a September since 2019" | September share below a third: 2018 0.64, 2019 0.65, 2020-2025 between 0.08 and 0.23, 2026 0.29 | `app/data/real/history.json` (command below) |
| Dam 1: "~80% full", "at least 68 days" | level 80% of full at the 13 Sep look; floor 87 days from 13 Sep, less the 19 days to 2 Oct | `app/data/real/farms.json`, Farm E, dam 1 (`nsw_cw-0659`): `level_pct`, `damdays_days`, `days_left` |
| Dam 1: "1 in 10 by 12 December" | chance 0.089; window ends 2026-12-12 | same row: `chance`, `window_end` |
| Dam 1: the next six months | by 13 Oct, 12 Nov, 12 Dec and 12 Mar (30, 60, 90 and 180 days from the 13 Sep look): 0.017, 0.046, 0.089, 0.259 (less than 1, less than 1, 1 and 3 in 10); the DamDays day is 9 Dec (13 Sep + 87 days), where the curve reads about 1 in 10 | `app/data/real/curves.json`, issue 2026-09-14, `nsw_cw-0659` |
| Dam 1: our record | held 380 of 428 times (a little under 9 in 10, so its card says give the days extra margin); Farm E's 5 dams: 1,640 of 1,767 | `app/data/real/track_record.json`, `dams` (`nsw_cw-0659`) and `farms` (`farm-e`) |
| Dam 3: "no water seen" | 0% at the 13 Sep look, already below a third | `farms.json`, Farm E, dam 3 (`nsw_cw-0672`): `level_pct`, `status` |
| Dam 5: "runs wetter than similar dams" | the per-dam correction's note on the live forecast | `app/data/real/forecasts.json`, issue 2026-09-14, `nsw_cw-0674`, `notes`; the correction: [`damdays/models/frailty.py`](../damdays/models/frailty.py) |
| "Built to hold 9 times in 10" | target 0.90; held for 0.9002 of 729,749 judged forecasts in the ten test years; median floor 60 days | [`artifacts/test_results.md`](../artifacts/test_results.md), "DamDays floor" |
| Said vs happened: 142,938 forecasts, 29,415 fell; "3 in 10": 4,864 of 17,013 | all 10 plotted groups matched to the nearest 1 in 10 (an 11th group, "more than 9 in 10", holds 1 forecast and is not drawn) | `app/data/real/proof.json`, `calibration` (command below); totals equal `artifacts/test_results.json` |
| Ten years to June 2026; learned only from data before July 2016 | test block 2016-07 to 2026-06; model cutoff 2016-07-01 | [PREREG.md](../PREREG.md), "Splits"; `proof.json`, `test.intro` |
| "Nearly a quarter less error than the usual guess" | skill vs the usual rate for the region and month +0.235 [+0.224, +0.248] | `test_results.md`, "In plain words"; `proof.json`, `test.skill_vs_usual_rate.words` |
| Better every year: "a fifth" (2020-21) to "a quarter" (2025-26) | skill +0.210 (2020-21, lowest) to +0.281 (2025-26, highest); every year above zero | `proof.json`, `by_year.years` (command below) |
| Drier years 2017-20 and 2023-26 | July-June rain over the two regions below its 1960-2016 average (SILO) | `proof.json`, `by_year.drier_rule` |
| "At least N days" held 872 to 927 in 1,000 each year | worst 2023-24, 872 (below the 880 to 920 band); most cautious 2020-21, 927 | `proof.json`, `by_year.years[].floor`; `test_results.md`, "By July-June year" |
| Chances ran high in wet years, a little low in some dry years | average chance given against share that fell: 2020-21 0.223 vs 0.138; 2021-22 0.191 vs 0.152; 2017-18 0.233 vs 0.261; 2025-26 0.229 vs 0.262 | `proof.json`, `by_year.years[]`: `mean_chance`, `share_fell` |
| Today's forecasts: refit on every look to 14 Sep 2026 | production fit on every answer known by the last look (14 Sep 2026); the data's cutoff, 2026-09-15, is the first day left out; run by hand with `scripts/11_export_app.py --refit-live` | `meta.json`, `live.cutoff`; [`damdays/export/live_model.py`](../damdays/export/live_model.py) |
| 4,711 waterbodies in the locked region | one fingerprinted file per waterbody | [`SEALED_HASHES.csv`](../SEALED_HASHES.csv) (4,711 rows), committed in e0e9b0b, Fri 2 Oct 2026, 09:12 AEST |
| The unseen exam covers forecasts July 2016 to June 2026 | sealed issues 2016-07-01 to 2026-06-30, models fitted on the development regions before 2016-07-01 | [PREREG.md](../PREREG.md), "Sealed region protocol" |
| Sealed numbers | <!-- SEALED:START source -->opens Sat 3 Oct 17:30 AEST<!-- SEALED:END --> | `artifacts/sealed/SEALED_RESULTS.md` |

**Honest framing of the hook.** In our own data, September 2026 has the most dams below a third for a September since 2019 (0.29, against a middle value of 0.26 over the Septembers since 1988), but it is far from the 2018-19 drought (about 0.64). A typical September is about 1 in 4, so this one is drier than usual, not extreme. So the script says "this spring is drier" and "the most since 2019", and never "this spring is dry" on its own or "a drought like 2019". Say "the 2026 drought" only if an official source (the Bureau of Meteorology or the NSW DPI drought indicator) supports it on the day you record, and name that source on screen.

**Live fact** (beat 3):

```
.venv/Scripts/python.exe -c "import json; m=json.load(open('app/data/real/meta.json')); c=m['coverage']; print(m['data_through'], m['model']['version'], c['dams'], c['live_status_counts'], m['live']['cutoff'])"
```

Today (the L3 export of 2 Oct 2026, 21:47 AEST) it prints `2026-09-14 L3 894 {'forecast': 576, 'already_low': 272, 'not_refilled': 44, 'no_recent_look': 2} 2026-09-15`.

**September comparison** (beat 3):

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

Each line: year, dams with a clear September look, share of them below a third. It uses each dam's September median level, so 2026 shows 0.29 (of 878 dams), where the latest-look count gives 272 of 894 (0.30). Both are "about 3 in 10".

**The text and Dam 1** (beats 1, 4 and 5):

```
.venv/Scripts/python.exe -c "
import json
f = json.load(open('app/data/real/farms.json'))
farm = [x for x in f['farms'] if x['farm_id'] == 'farm-e'][0]
print(farm['sms']); print(farm['sms_septets'], 'places')
for d in farm['dams']:
    print(d['name'], d['dam_id'], d['status'], d['level_pct'], d['chance'], d['damdays_days'], d['days_left'], d['issued_on'])
"
```

If `scripts/16_weekly_texts.py` is run again on a later day, the days change (they are counted from the day of the text). The video uses the texts dated Fri 2 Oct 2026: `scripts/16_weekly_texts.py --date 2026-10-02` makes them again.

**The Proof pictures** (beats 6 and 7):

```
.venv/Scripts/python.exe -c "
import json
p = json.load(open('app/data/real/proof.json', encoding='utf-8'))
t = p['test']; print(t['forecasts'], t['fell'], t['skill_vs_usual_rate']['value'], t['skill_vs_usual_rate']['words'])
for b in p['calibration']['bins']: print(b['said'], b['forecasts'], b['fell'], b['happened_in_ten'], b['plotted'])
for y in p['by_year']['years']: print(y['label'], round(y['skill'], 3), y['skill_words'], y['drier'], y['floor']['held_in_1000'], round(y['mean_chance'], 3), round(y['share_fell'], 3))
"
```

It prints `142938 29415 0.23501 nearly a quarter`, then the eleven groups ("3 in 10 17013 4864 3 True"), then one line per year from `2016-17 0.216 a fifth False 889 0.228 0.211` to `2025-26 0.281 a quarter True 900 0.229 0.262`.

---

## Shot list (record in this order)

The recorder names are those in `video/shots.py`. That recorder is superseded: it still drives the old app layout and the Dubbo demo farm, so record these shots by hand from the routes in the "where" column (or update its selectors for the new app first). Not used in v2 or v3: Rewind (`rewind_2018`), the Area outlook (`rating_split`), the About page (`about_cop31`, `about_checks`) and Proof's dam-by-dam part (`proof_dam`, now Farm E: on 1 Nov 2018 its three forecasts gave 1 in 10 to 2 in 10 and Dam 1 fell; over the three Rewind dates about 2 falls were expected and 2 happened. It is honest, but one farm on a few dates is easy to misread in a 2-minute video).

| shot | where | what to do | recorder | length to capture |
|---|---|---|---|---|
| S1 | phone | The Farm E text arriving on the phone drawn in the app (its first screen), or a phone mock-up made in the video editor with the text copied exactly. Film the buzz, then hold on the full text. Caption it as a mock-up. | `phone_text` | 15 s |
| S2 | card | "Who it's for": the beat-2 caption as a plain card. No farm photos of real people or properties. | new card (like `cop31_card`) | 12 s |
| S3 | app `#runway` | The whole NSW Central West region, dark dots = already below a third; a slow drift. Start on the whole region. | `runway_region` (start at the region view) | 15 s |
| S4 | phone or editor | The same text, close up; highlight the Dam 1 line, then the Dam 3 line (no water seen). | `phone_highlight` | 12 s |
| S5 | app, My farm | Farm E, the whole 3 km circle (no town in view; keep the circle at 3 km so Dam 5 stays in). Tap Dam 1; hold on the days and the chance; slide down to the next six months (the DamDays day, 9 Dec, marked; keep the shaded band in view) and to our record on this dam. Optional: Dam 5's card, for "Runs wetter than similar dams" and "held 413 of 413 times". | `dam_card` (set to Farm E, Dam 1) | 15 s |
| S6 | app `#proof`, part 1 | "What we said vs what happened": hold on the chart; a highlight or slow zoom on the "3 in 10" dot. | `proof_said_vs_happened` | 15 s |
| S7 | app `#proof`, part 2 | "It held up year after year": the ten bars, then the "at least N days" dots. | `proof_by_year` | 18 s |
| S8 | terminal and repo, at the opening (Sun 4 Oct, after the app build); then app `#proof` | The whole sealed-opening recording, from 15 minutes before the run to the pushed results (runbook: [SEALED_OPENING.md](SEALED_OPENING.md)). Keep the raw file as evidence; the video uses a 15-second sped-up cut with a visible clock, ending on Proof's "Unseen exam" card once scripts/21 has filled it. | screen recording; `sealed_card` as a fallback | whole run |
| S9 | card | COP31 title card (the beat-9 caption). | `cop31_card` | 10 s |
| S10 | phone, then title card | The phone with the text for 2 s; then name, repository address, data credits. | `phone_text`, `closing_card` | 8 s |

## Recording checklist

- [ ] Every box under "Before recording" ticked.
- [ ] Browser at 1920 x 1080, page zoom about 125% so text reads on a phone; bookmarks bar hidden; no other tabs, emails, phone numbers or personal data on screen.
- [ ] No percent on screen means a chance: "%" is only how full a dam is. No lender, bank or agribusiness words on screen.
- [ ] Captions burned into the video, and they match the voice-over.
- [ ] Voice-over at most 240 words; final cut **2:00 or less**; exported as 1080p MP4.
- [ ] No music, or music you made or are licensed to use; list it in [DISCLOSURE.md](../DISCLOSURE.md).
- [ ] Add the video, phone mock-up and screen-recording tools to [DISCLOSURE.md](../DISCLOSURE.md) ("Tools").
- [ ] The video link opens without asking for access.

## The video build (`video/`)

`video/beats.json` (draft 1, copied from the script as it stood at 09:00 on Sat 3 Oct) and `video/shots.py` are superseded and marked so: they still have the 2018-19 replay, the lender beat, the About-page COP31 shot, the Dubbo demo farm (set aside; use Farm E from this page) and a 0% dam called "dry" (now "no water seen"), and shots.py drives the old app's page layout. They were not updated, because the video platform is being decided first. Whatever makes the final cut should take its beats, voice-over and captions from this page. Renders go to `video/out/`, which is git-ignored (`.gitignore`), so big media never enters git.
