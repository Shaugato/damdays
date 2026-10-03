# DamDays: 2-minute demo video script (v2)

**Length: 2:00 at most** (Participant Guide: "2 minutes or less"). Ten beats, timed below. The voice-over is **237 words** with the longest possible sealed-result line (12 words). At draft 1's measured pace (2.25 words a second, numbers said in full) that is about 105 seconds of voice, and about **1:55** with the pauses, the opening buzz and the end card: 5 seconds spare. Every key number is also a caption, because many judges watch muted.

**The story in one line.** A farmer's phone buzzes with this week's DamDays text: how many days of water each dam has left. We say who it is for, what they do with it, and show in three pictures why the number can be trusted.

**v2, Sat 3 Oct 2026.** Rewritten from a second mentor's advice (Sat 3 Oct, research/MENTOR_FEEDBACK.md) and a pressure test of draft 1 against what is built:

| asked for | where v2 answers it |
|---|---|
| Accuracy on data the model never saw, as recent as possible, shown as a picture | Beat 6: "what we said vs what happened" over ten years to June 2026. Beat 8: the unseen exam also covers forecasts to June 2026 |
| How it keeps up as the climate shifts | Beat 7: better than the usual guess in every year from 2016-17 to 2025-26, dry and wet; refit on new looks; each dam corrected by its own record. The caption admits the drift that makes refitting necessary |
| Dam by dam | Beats 4 and 5: each dam's line in the text, Dam 2's card and its own correction ("runs wetter than similar dams") |
| One audience: farmers | The lender beat is cut. The COP31 shot is a title card, not the About page (whose third point is about lenders) |
| Describe the target farmer precisely | Beat 2, one sentence, from [TARGET_FARMER.md](TARGET_FARMER.md) |

Fixed from the pressure test: the 2018-19 replay is out (its "248 dams" were 782 forecasts for 366 dams; 2018-19 is one bar in beat 7); "29 days" and "3 in 10" now agree out loud; "9 in 10" is said as a built-in safety margin, not a hit rate; the phone is captioned as a mock-up and the MAP reply as not built; "% full" and the satellite date are explained on screen; the COP31 beat names the Awareness track and the Global Goal on Adaptation.

**Language rules** (from mentor feedback):
- **One audience: farmers.** No lenders, banks or agribusiness in the voice-over or on screen. The only "bigger idea" is the end card's small line: the satellite record covers all of Australia.
- **"%" means only how full a dam is.** A chance is written "3 in 10", never "30%", on screen and out loud. "~67% full" is the share of the dam's usual full water surface the satellite sees wet, not its depth or volume.
- **The headline is days of water** before the dam drops below a third: "at least 29 days". "A third" is DamDays's early-warning line, not empty.
- **"9 in 10" is only for the days-left promise**, and always as a built-in safety margin ("built to hold 9 times in 10"), never as "right 9 times in 10". It is not a hit rate.
- **Plain words.** Never say "AUC", "Brier", "skill score", "calibration" or "sealed region". The skill number is said as a fraction, rounded down: +0.235 is "nearly a quarter less error than the usual guess".
- **Keeping up, truthfully.** Say "refit" and "corrected by its own record". Never "learns by itself", "evolves" or "monitored every year": automatic refits and drift checks are not built yet.
- **"Unseen" means only the sealed region.** The test years are "ten years it never trained on": we looked at them before the event, so they are not unseen.
- **Illustrative, never real people.** The farmer in beat 2 is typical survey values, not a real family. The farm in the text is a demo farm: its 7 dams and their forecasts are real, the homestead point is not. Never name a family or a property.
- **No pre-event research** in the video. It is disclosed in [DISCLOSURE.md](../DISCLOSURE.md).

---

## The text on the phone (beats 1, 4 and 10)

The real text made on Fri 2 Oct 2026 for **Farm D (near Dubbo)**, copied from [`outbox/2026-10-02.json`](../outbox/2026-10-02.json) (`farm-d`). It takes 146 of one SMS's 160 places. Show it exactly as it is:

```
Fri 2 Oct (satellite 13 Sep)
Dam 2 ~67% full: at least 29 days before it drops below 1/3
Dam 1 looks dry
Other 5 dams: at least 52 days
Reply MAP
```

How to read it: Dam 1 is the dam closest to the homestead. Dam 2's forecast starts from its last clear satellite look (13 Sep): at least 48 days from then, which is **29 days from Fri 2 Oct**. Its chance of being below a third by 12 Dec is 0.319, "3 in 10": so 29 days is the cautious figure, and the dam will most likely last longer. The phone is drawn (a mock-up); nothing is sent unless someone runs the sender with their own SMS account's keys, and the MAP and STOP replies are not built yet ([notify/MESSAGE_SPEC.md](../notify/MESSAGE_SPEC.md), section 7).

## The farmer (beat 2)

One sentence, illustrative: "It's for family sheep and cattle farms, say 1,500 hectares and 2,000 sheep, where stock drink from dams." Typical values from ABARES farm surveys, 2022-23 to 2024-25 ([TARGET_FARMER.md](TARGET_FARMER.md)): most often 300 to 1,500 ha; mixed farms run 1,711 to 2,931 sheep and 249 to 431 cattle; 63 to 107 work weeks a year in all (1 to 2 people); stock water from farm dams; mostly Outer Regional Australia. The hard filter is a dam of at least 0.54 ha that the satellites can see. The demo farm in the text has 7 such dams within 3 km, which is the best case: a typical target farm sees 1 or 2.

---

## Before recording

Every box must be ticked, or the beat that needs it changes as noted. The draft-1 ticks (Fri 2 Oct, 23:58) no longer count: the app has changed since (the Proof view is new; `index.html`, `main.js`, `about.js`, `style.css` and `bundle.js` were modified), so check everything again.

- [ ] **Real data.** No MOCK banner; About → "This page's data" says version L3.
- [ ] **My farm** opens first, on Farm D (beat 5). Dam 2's card says "~67% full on 13 Sep 2026", "29 days" counted from Fri 2 Oct, "Chance it drops below a third by 12 Dec 2026: 3 in 10", and "Runs wetter than similar dams: it fell below a third less often than the model expected."
- [ ] **The map shots show no town edge.** Beat 5 is cropped to Farm D's seven dams only (zoom 15 or closer). Farm D's point is 4.7 km from Dubbo: the wide 3 km view shows the Dubbo sewage treatment plant, the Newell Highway and suburban streets, which reads as town, not a farm. Beat 3 shows the whole region, not Farm D's surroundings.
- [ ] **Proof, part 1** (beat 6): ten dots near the diagonal; its table says "3 in 10: 4,864 of 17,013".
- [ ] **Proof, part 2** (beat 7): ten bars, all above zero, from "a fifth" (2020-21) to "a quarter" (2025-26); drier years 2017-20 and 2023-26 shaded; the "at least N days" dots from 872 to 927 in 1,000 (2023-24 at 872, below the band).
- [ ] **The app follows the wording rules.** No "%" in the app means a chance.
- [ ] **The sealed-result line is written** (beat 8) by `scripts/21_publish_sealed.py`, after the opening on Sat 3 Oct 17:30 AEST, and read against `artifacts/sealed/SEALED_RESULTS.md`. Proof's "Unseen exam" card shows the scored panel.
- [ ] **Every [square bracket] is filled**, from "Where each number comes from" below.

---

## The script, beat by beat

| # | time | on screen (shot) | voice-over | caption |
|---|---|---|---|---|
| 1 | 0:00-0:11 | **The text arrives.** Two seconds of the phone buzzing, no voice. Then the text, full screen, every line readable. (S1) | "Friday morning. A farmer's phone buzzes. No app needed: one text a week, each dam's days of water." | The text itself (above)<br><small>Mock-up of this week's real text for a demo farm near Dubbo: real forecasts for its 7 farm dams; not a real homestead · the MAP reply is not built yet</small> |
| 2 | 0:11-0:22 | **Who it's for.** A plain card with the farmer's profile. No photos of real people or properties. (S2) | "It's for family sheep and cattle farms, say 1,500 hectares and 2,000 sheep, where stock drink from dams. How long each dam lasts is guesswork." | **Who it's for** (illustrative: typical values from ABARES farm surveys, 2022-23 to 2024-25)<br>Family sheep and cattle farm · about 1,500 ha · about 2,000 sheep and 250 cattle · 1 to 2 people's work · stock water from farm dams<br><small>Needs at least one dam of 0.54 ha or more, big enough for the satellites to see · today: drive the water run and do the sums by hand</small> |
| 3 | 0:22-0:32 | **A dry spring.** The Runway map of the whole region, its dark dots already below a third; a slow drift across it. (S3) | "This spring is dry: 272 of the 894 farm dams we track are already below a third, the most for September since 2019." | **NSW Central West · latest satellite looks to 14 Sep 2026**<br>**272 of the 894 farm dams we track already below a third full**<br>The most for a September since the 2019 drought<br><small>Source: DEA Waterbodies, Geoscience Australia</small> |
| 4 | 0:32-0:44 | **The text, line by line.** Back to the phone; the Dam 1 line lights up, then the Dam 2 line. (S4) | "Dam 1 looks dry. Dam 2 has at least 29 days before dropping below a third: a cautious figure, built to hold 9 times in 10." | **~67% full = how much water is there** (share of its usual full water surface)<br>**at least 29 days = days before it drops below a third (cautious)**<br>Built so the dam lasts at least that long 9 times in 10<br><small>A third: DamDays's early-warning line, before a dam runs dry · last clear satellite look 13 Sep; days are counted from the day of the text</small> |
| 5 | 0:44-0:53 | **Dam by dam, in the app.** My farm, cropped tight on Farm D's seven numbered dams. Tap Dam 2: its card opens on the days and the chance; slide down past "Runs wetter than similar dams" to the runway curve and its shaded band. (S5) | "The app adds the chance: 3 in 10 it's that low by mid-December. Time to plan where the stock go." | **Dam 2 · ~67% full on 13 Sep · at least 29 days**<br>**Chance it drops below a third by 12 Dec 2026: 3 in 10**<br>Every dam gets its own forecast · Dam 2 "runs wetter than similar dams"<br><small>Runway to 6 months · shaded: a wetter or drier season</small> |
| 6 | 0:53-1:07 | **Proof 1: what we said vs what happened.** The Proof view, part 1: ten dots on the diagonal; hold on the "3 in 10" dot. (S6) | "Is it right? Over ten years it never trained on, to June 2026: when it said 3 in 10, about 3 in 10 did. The same at every level." | **What we said vs what happened · ten test years, July 2016 to June 2026, scored once**<br>**Said 3 in 10: 4,864 of 17,013 fell below a third within 90 days**<br>All 10 groups matched what we said, to the nearest 1 in 10 · 142,938 forecasts, 29,415 fell<br><small>The model learned only from data before July 2016 · we looked at these years before the event, so they may flatter it slightly: the unseen exam is the clean test</small> |
| 7 | 1:07-1:22 | **Proof 2: it held up year after year.** The Proof view, part 2: the ten bars, all above zero, with the drier years shaded; then the "at least N days" dots. (S7) | "It held up as conditions changed: nearly a quarter less error than the usual guess, better every year, dry or wet. It's refit on new satellite looks, each dam corrected by its own record." | **Less error than the usual guess in all 10 years: from a fifth (2020-21) to a quarter (2025-26) · nearly a quarter overall**<br>Drier years shaded: 2017-20 and 2023-26 · "at least N days" held 872 to 927 times in 1,000 each year<br>Today's forecasts: refit on every satellite look to 14 Sep 2026 · each dam's forecast corrected by its own track record<br><small>Not refitted during the ten test years: in wet years its chances ran high, in some dry years a little low, which is why it is refit · automatic weekly refits: next</small> |
| 8 | 1:22-1:37 | **Proof 3: the unseen exam.** The Sat 3 Oct 17:30 screen recording, sped up with the clock visible: `git status` clean, 4,711 of 4,711 fingerprints matched, the run, the result. End on the Proof view's "Unseen exam" card. (S8) | "The clean test: a farming region we locked away at the start, ten years to June 2026, opened once, on camera. <!-- SEALED:START line -->[Sealed-result line: opens Sat 3 Oct 17:30 AEST.]<!-- SEALED:END -->" | **The unseen exam · Southern Downs, Granite Belt, New England · 4,711 waterbodies**<br>Forecasts July 2016 to June 2026 · fingerprints published Fri 2 Oct, 09:12 AEST · opened once, on camera, Sat 3 Oct, 17:30 AEST · published whatever it showed<br><!-- SEALED:START caption -->[sealed numbers: opens Sat 3 Oct 17:30 AEST]<!-- SEALED:END --><br><small>Burn in only the first two lines of the result (see "The sealed-result line")</small> |
| 9 | 1:37-1:47 | **COP31.** A plain title card, not the About page (S9). | "That's COP31's Awareness track: helping farmers adapt, with climate information they can act on, for fewer stock losses and less waste." | **COP31 · Awareness Across All Areas: helping farmers adapt**<br>Each dam's days of water, by text, every week<br><small>Global Goal on Adaptation (UAE Framework for Global Climate Resilience): targets on water scarcity and on climate-resilient food and farming · aim: fewer stock losses, less wasted feed, better use of on-farm water (not yet measured)</small> |
| 10 | 1:47-1:55 | **Close.** The phone with the text, then the end card. (S10) | "DamDays: days of water, by text, every week." | **DamDays**<br>github.com/Shaugato/damdays<br><small>The satellite record covers all of Australia; tested so far in NSW Central West and western Victoria / SE South Australia · Data: DEA Waterbodies (Geoscience Australia) · SILO (Queensland Government) · CC BY 4.0</small> |

**Words per beat:** 18, 25, 23, 26, 20, 29, 34, 21 plus the sealed line (at most 12), 21, 8. Total 237 (235 if the line is the 10-word partial-pass one).

**If the cut runs over 2:00,** trim in this order (the captions keep each point): "Is it right?" (beat 6); "The same at every level." (beat 6); "for fewer stock losses and less waste" (beat 9). Together about 15 words, 6 to 7 seconds. Do not cut the sealed line, "to June 2026", "built to hold 9 times in 10" or "refit".

**Reading the numbers aloud:** "fifteen hundred hectares", "two thousand sheep", "two hundred and seventy-two of the eight hundred and ninety-four", "twenty-nineteen", "twenty-nine days", "June twenty twenty-six", "COP thirty-one".

### The sealed-result line (beat 8 and the pitch)

<!-- SEALED:START -->
[The sealed-result line: opens Sat 3 Oct 17:30 AEST. After the opening, `scripts/21_publish_sealed.py` writes it here from the results, by the templates below.]

<!-- SEALED:END -->

`scripts/21_publish_sealed.py` writes it on Saturday from `artifacts/sealed/sealed_results.json`, in one sentence of at most 12 words, whichever way it went. Read it against `artifacts/sealed/SEALED_RESULTS.md` before recording. Templates:

- **Every pass mark met:** "It passed every mark: [a fifth] less error than the usual guess." (If that is over 12 words, as with "nearly a quarter": "Every mark passed: nearly a quarter less error than the usual guess.")
- **Some marks met:** "It met [x] of [y] marks; we published the miss."
- **Pass marks missed:** "It fell short of our marks. Every number is published, as promised."

Words for the error number (the skill score): 0.10 = "a tenth", 0.15 = "about a seventh", 0.20 = "a fifth", 0.225 to 0.249 = "nearly a quarter", 0.25 = "a quarter". Round down, never up: 0.235 is "nearly a quarter", not "a quarter".

Three things scripts/21 writes that v2 handles differently (scripts/21 was not changed, so nothing in the opening's tooling moves):
- **The caption marker gets three lines; burn in only the first two** (the pass marks met, then the error words and "at least N days" held). The third line is the pre-registered season rating, built with lenders in mind; it stays in the pitch's evidence table, where every pass mark is reported, but this farmer video does not show it.
- **It calls this "beat 5"**, from draft 1. In v2 it is beat 8.
- **If it says "Kill rule triggered ... cut or reword beat 8"**, nothing in v2 needs cutting: there is no lender claim in the video. Keep beat 8's sealed line as written.

---

## Where each number comes from

Check each one just before recording. All commands run from the repo folder.

| number | value now | source |
|---|---|---|
| The text on the phone | Farm D (near Dubbo), Fri 2 Oct 2026, 146 of 160 places | [`outbox/2026-10-02.json`](../outbox/2026-10-02.json), `farm-d`; made by [`scripts/16_weekly_texts.py`](../scripts/16_weekly_texts.py) |
| The farmer: about 1,500 ha, 2,000 sheep, 250 cattle, 1 to 2 people, stock water from dams | illustrative, inside the ABARES ranges for 2022-23 to 2024-25 (land most often 300 to 1,500 ha; mixed farms 1,711 to 2,931 sheep and 249 to 431 cattle; 63 to 107 work weeks a year) | [TARGET_FARMER.md](TARGET_FARMER.md), "Meet Kath and Graeme" and "The target farmer in one table" (ABARES Farm Data Portal) |
| Latest satellite looks: 14 Sep 2026 | `data_through` 2026-09-14 | `app/data/real/meta.json` |
| 272 of 894 farm dams already below a third | 894 tracked: 576 with a forecast, 272 already below a third, 44 not refilled since their last low, 2 with no clear look in the last 60 days | `meta.json`, `coverage.live_status_counts` (command below) |
| "The most for a September since 2019" | September share below a third: 2018 0.64, 2019 0.65, 2020-2025 between 0.08 and 0.23, 2026 0.29 | `app/data/real/history.json` (command below) |
| Dam 2: "~67% full", "at least 29 days" | level 67% of full at the 13 Sep look; floor 48 days from 13 Sep, less the 19 days to 2 Oct | `app/data/real/farms.json`, Farm D, dam 2 (`nsw_cw-0408`): `level_pct`, `damdays_days`, `days_left` |
| Dam 2: "3 in 10 by 12 December" | chance 0.319; window ends 2026-12-12 | same row: `chance`, `window_end` |
| Dam 2: "runs wetter than similar dams" | the per-dam correction's note on the live forecast | `app/data/real/forecasts.json`, issue 2026-09-14, `nsw_cw-0408`, `notes`; the correction: [`damdays/models/frailty.py`](../damdays/models/frailty.py) |
| Dam 2: the runway | 30, 60, 90, 180 days: 0.084, 0.212, 0.319, 0.637 (about 1, 2, 3 and 6 in 10) | `app/data/real/curves.json`, issue 2026-09-14, `nsw_cw-0408` |
| "Built to hold 9 times in 10" | target 0.90; held for 0.9002 of 729,749 judged forecasts in the ten test years; median floor 60 days | [`artifacts/test_results.md`](../artifacts/test_results.md), "DamDays floor" |
| Said vs happened: 142,938 forecasts, 29,415 fell; "3 in 10": 4,864 of 17,013 | all 10 plotted groups matched to the nearest 1 in 10 (an 11th group, "more than 9 in 10", holds 1 forecast and is not drawn) | `app/data/real/proof.json`, `calibration` (command below); totals equal `artifacts/test_results.json` |
| Ten years to June 2026; learned only from data before July 2016 | test block 2016-07 to 2026-06; model cutoff 2016-07-01 | [PREREG.md](../PREREG.md), "Splits"; `proof.json`, `test.intro` |
| "Nearly a quarter less error than the usual guess" | skill vs the usual rate for the region and month +0.235 [+0.224, +0.248] | `test_results.md`, "In plain words"; `proof.json`, `test.skill_vs_usual_rate.words` |
| Better every year: "a fifth" (2020-21) to "a quarter" (2025-26) | skill +0.210 (2020-21, lowest) to +0.281 (2025-26, highest); every year above zero | `proof.json`, `by_year.years` (command below) |
| Drier years 2017-20 and 2023-26 | July-June rain over the two regions below its 1960-2016 average (SILO) | `proof.json`, `by_year.drier_rule` |
| "At least N days" held 872 to 927 in 1,000 each year | worst 2023-24, 872 (below the 880 to 920 band); most cautious 2020-21, 927 | `proof.json`, `by_year.years[].floor`; `test_results.md`, "By July-June year" |
| Chances ran high in wet years, a little low in some dry years | average chance given against share that fell: 2020-21 0.223 vs 0.138; 2021-22 0.191 vs 0.152; 2017-18 0.233 vs 0.261; 2025-26 0.229 vs 0.262 | `proof.json`, `by_year.years[]`: `mean_chance`, `share_fell` |
| Today's forecasts: refit on every look to 14 Sep 2026 | production fit on every answer known by the last look; cutoff 2026-09-15; run by hand with `scripts/11_export_app.py --refit-live` | `meta.json`, `live.cutoff`; [`damdays/export/live_model.py`](../damdays/export/live_model.py) |
| 4,711 waterbodies in the locked region | one fingerprinted file per waterbody | [`SEALED_HASHES.csv`](../SEALED_HASHES.csv) (4,711 rows), committed in e0e9b0b, Fri 2 Oct 2026, 09:12 AEST |
| The unseen exam covers forecasts July 2016 to June 2026 | sealed issues 2016-07-01 to 2026-06-30, models fitted on the development regions before 2016-07-01 | [PREREG.md](../PREREG.md), "Sealed region protocol" |
| Sealed numbers | <!-- SEALED:START source -->opens Sat 3 Oct 17:30 AEST<!-- SEALED:END --> | `artifacts/sealed/SEALED_RESULTS.md` |

**Honest framing of the hook.** In our own data, September 2026 has the most dams below a third for a September since 2019 (0.29, against a middle value of 0.26 over the Septembers since 1988), but it is far from the 2018-19 drought (about 0.64). So the script says "this spring is dry" and "the most since 2019", and never "a drought like 2019". Say "the 2026 drought" only if an official source (the Bureau of Meteorology or the NSW DPI drought indicator) supports it on the day you record, and name that source on screen.

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

**The text and Dam 2** (beats 1, 4 and 5):

```
.venv/Scripts/python.exe -c "
import json
f = json.load(open('app/data/real/farms.json'))
farm = [x for x in f['farms'] if x['farm_id'] == 'farm-d'][0]
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

The recorder names are those in `video/shots.py`, for whoever builds the final cut. Not used in v2: Rewind (`rewind_2018`), Rating (`rating_split`), the About page (`about_cop31`, `about_checks`) and Proof's dam-by-dam part (`proof_dam`: on 1 Nov 2018 Farm D's two highest-chance dams did not fall and two lower ones did, which is honest but reads badly as accuracy evidence in a 2-minute video).

| shot | where | what to do | recorder | length to capture |
|---|---|---|---|---|
| S1 | phone | The Farm D text arriving on the phone drawn in the app's My farm view, or a phone mock-up made in the video editor with the text copied exactly. Film the buzz, then hold on the full text. Caption it as a mock-up. | `phone_text` | 15 s |
| S2 | card | "Who it's for": the beat-2 caption as a plain card. No farm photos of real people or properties. | new card (like `cop31_card`) | 12 s |
| S3 | app `#runway` | The whole NSW Central West region, dark dots = already below a third; a slow drift. Do not start on Farm D's surroundings. | `runway_region` (start at the region view) | 15 s |
| S4 | phone or editor | The same text, close up; highlight the Dam 1 line, then the Dam 2 line. | `phone_highlight` | 12 s |
| S5 | app, My farm | Farm D, cropped tight on its seven dams (zoom 15 or closer: no town, highway or sewage-plant labels). Tap Dam 2; hold on the days and the chance; slide down past the "Runs wetter than similar dams" line to the runway curve, keeping the shaded band in view. | `dam_card` (crop tighter than draft 1) | 15 s |
| S6 | app `#proof`, part 1 | "What we said vs what happened": hold on the chart; a highlight or slow zoom on the "3 in 10" dot. | `proof_said_vs_happened` | 15 s |
| S7 | app `#proof`, part 2 | "It held up year after year": the ten bars, then the "at least N days" dots. | `proof_by_year` | 18 s |
| S8 | terminal and repo, Sat 3 Oct; then app `#proof` | The whole sealed-opening recording, 17:15 to about 18:00 (runbook: [SEALED_OPENING.md](SEALED_OPENING.md)). Keep the raw file as evidence; the video uses a 15-second sped-up cut with a visible clock, ending on Proof's "Unseen exam" card once scripts/21 has filled it. | screen recording; `sealed_card` as a fallback | whole run |
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

`video/beats.json` is draft 1 (copied from the script as it stood at 09:00 on Sat 3 Oct) and is now out of date: it still has the 2018-19 replay, the lender beat and the About-page COP31 shot. It was not changed in this pass, because the video platform is being decided first. Whatever makes the final cut should take its beats, voice-over and captions from this page. Renders go to `video/out/`, which is git-ignored (`.gitignore`), so big media never enters git.
