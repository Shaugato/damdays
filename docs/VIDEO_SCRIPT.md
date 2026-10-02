# DamDays: 2-minute demo video script (draft)

**Length: 2:00 at most** (Participant Guide: "2 minutes or less"). Ten beats, timed below. The voice-over is about 260 words with the sealed-result line (about 270 once the big numbers are said out loud), a calm 140 words a minute. Every key number is also a caption, because many judges watch muted.

**The story in one line.** Friday morning near Dubbo, a grazier's phone buzzes with this week's DamDays text: how many days of water each dam has left. We show what they do with it, what the app adds, why the number can be trusted, and who else needs it.

**Language rules** (from mentor feedback):
- **"%" means only how full a dam is.** A chance is written "3 in 10", never "30%", on screen and out loud.
- **The headline is days of water left** before the dam drops below a third: "at least 29 days".
- **Plain words.** Say "the unseen exam", never "sealed region", "BSS" or "AUC". Say "picked the right one 8 times in 10", not a score.
- **No pre-event research** in the video. It is disclosed in [DISCLOSURE.md](../DISCLOSURE.md).
- **The farm is a demo farm.** Its 7 dams and their forecasts are real, but the homestead point is not a real one. Say "a grazier near Dubbo"; never name a family or a property.

---

## The text on the phone (beats 1 and 3)

The real text made on Fri 2 Oct 2026 for **Farm D (near Dubbo)**, copied from [`outbox/2026-10-02.json`](../outbox/2026-10-02.json) (`farm-d`). It takes 146 of one SMS's 160 places. Show it exactly as it is:

```
Fri 2 Oct (satellite 13 Sep)
Dam 2 ~67% full: at least 29 days before it drops below 1/3
Dam 1 looks dry
Other 5 dams: at least 52 days
Reply MAP
```

How to read it: Dam 1 is the dam closest to the homestead. Dam 2's forecast starts from its last clear satellite look (13 Sep): at least 48 days from then, which is **29 days from Fri 2 Oct**. Rules: [notify/MESSAGE_SPEC.md](../notify/MESSAGE_SPEC.md).

---

## Before recording

Every box must be ticked, or the beat that needs it changes as noted.

- [x] **Real data.** No MOCK banner; About → "This page's data" says version L3; Rewind lists 1 Nov 2018, 1 Jan 2019 and 1 Mar 2019; Rating lists 2018-19. (Checked Fri 2 Oct, 23:58 AEST; check again if the app data is exported again.)
- [x] **My farm is in the app** (beat 4). It opens first, on Farm D. Dam 2's card also says what the Runway map calls it: **Dam 408** (`nsw_cw-0408`). (Checked Fri 2 Oct, 23:58 AEST.)
- [x] **The app follows the wording rules** (beats 4 and 6). Dam 2's card says "~67% full on 13 Sep 2026", "29 days", counted from Fri 2 Oct ("48 days from its last clear look, less the 19 days since"), and "Chance it drops below a third by 12 Dec 2026: 3 in 10"; Rewind's tables say "likely at 5 in 10 or more". No "%" in the app means a chance. (Checked in the browser Fri 2 Oct, 23:58 AEST; re-check if the app changes.)
- [ ] **The sealed-result line is written** (beat 5), from `artifacts/sealed/SEALED_RESULTS.md`, after the opening on Sat 3 Oct 17:30 AEST.
- [ ] **Every [square bracket] is filled**, from "Where each number comes from" below.

---

## The script, beat by beat

| # | time | on screen (shot) | voice-over | caption |
|---|---|---|---|---|
| 1 | 0:00-0:12 | **The text arrives.** Two seconds of a phone buzzing on a ute's dashboard or a kitchen bench, no voice. Then the text, full screen, every line readable. (S1) | "Friday morning near Dubbo. A grazier's phone buzzes: not an app, not an email, but one weekly text. Days of water, dam by dam." | The text itself (above)<br><small>Demo farm: real forecasts for 7 farm dams near Dubbo; not a real homestead</small> |
| 2 | 0:12-0:24 | **A dry spring.** The Runway map, starting on Farm D's seven dots, pulling back to the whole region and its dark dots. (S2) | "It's a dry spring. In NSW Central West, 272 of 894 farm dams are already below a third full: the most for a September since 2019." | **NSW Central West · satellite looks to 14 Sep 2026**<br>**272 of the 894 farm dams we track already below a third full**<br>The most for a September since the 2019 drought<br><small>Source: DEA Waterbodies, Geoscience Australia</small> |
| 3 | 0:24-0:38 | **What the farmer does with it.** Back to the text; the Dam 1 and Dam 2 lines light up in turn. (S3) | "Dam 1 is dry. Dam 2 has at least 29 days before it drops below a third: time to book a water cart or move stock, while there are still choices." | **~67% full = how much is there**<br>**at least 29 days = how long it lasts**<br>Act early: book a water cart · move stock to the dams that last · sell or agist while there is a choice |
| 4 | 0:38-0:49 | **A quick look at the app.** My farm: the homestead, the 3 km circle, the numbered dams. Tap Dam 2; its card opens on the days; slide down to the runway curve and its shaded band. (S4) | "My farm puts them on a map. Dam 2's card adds the chance, 3 in 10 by 12 December, and a six-month runway." | **My farm · every farm dam the satellites can see within 3 km · Dam 1 = closest**<br>**Dam 2 · ~67% full on 13 Sep · at least 29 days**<br>Chance it drops below a third by 12 Dec: 3 in 10<br>Runway to 6 months · shaded: a wetter or drier season |
| 5 | 0:49-1:10 | **Proof 1: the unseen exam.** The screen recording of Sat 3 Oct 17:30, sped up with the clock visible: `git status` clean, all 4,711 fingerprints checked, the run, the results page. (S5) | "Can you trust it? Our unseen exam: we locked away a whole farming region's satellite data, published its fingerprint at the start, and opened it once, on camera. Whatever score came out, we published it. [Sealed-result line.]" | **The unseen exam**<br>**Southern Downs, Granite Belt, New England · 4,711 waterbodies**<br>Fingerprint published Fri 2 Oct, 09:12 AEST · opened once, on camera, Sat 3 Oct, 17:30 AEST<br>[sealed numbers, in the words of "The sealed-result line" below] |
| 6 | 1:10-1:23 | **Proof 2: the 2018-19 drought, replayed.** Rewind, 1 Nov 2018: the forecast map; press **Reveal what happened**; the rings appear. Quick cuts to the same reveal on 1 Jan and 1 Mar 2019. (S6) | "We replayed the 2018-19 drought, with a model that learned only from data before mid-2016. Over three dates, it expected about 248 dams to fall below a third. 244 did." | **The 2018-19 drought, replayed · NSW Central West**<br>Model learned only from data before July 2016<br>**782 forecasts on 3 dates · expected to fall below a third: about 248 · did: 244**<br><small>1 Nov 2018: about 95, 76 · 1 Jan 2019: about 97, 106 · 1 Mar 2019: about 57, 62</small> |
| 7 | 1:23-1:31 | **Proof 3: ten test years.** `artifacts/test_results.md`, the pass-mark table, every row PASS. (S7) | "And over ten test years it never learned from, the cautious days held 9 times in 10." | **Ten test years, July 2016 to June 2026, scored once**<br>**"At least N days" held 9 times in 10 · 729,749 forecasts**<br>Every pass mark met · pass marks written before any code (Fri 2 Oct, 09:12 AEST) |
| 8 | 1:31-1:45 | **The bigger idea: lenders.** Rating, season 2018-19: the two maps side by side; press **Reveal which ran dry**. (S8) | "Lenders see rainfall, not stored water. Our water-security rating sees it: shown two patches of farms, one that ran dry, it picked right 8 times in 10. Rainfall alone: a coin toss." | **For lenders: a water-security rating**<br>Left: rainfall only · Right: DamDays<br>**10 test seasons · shown a 2 km patch that ran dry and one that did not, DamDays picks the right one 8 times in 10 · rainfall only: about 5 in 10, a coin toss** |
| 9 | 1:45-1:54 | **COP31.** The app's About view, "Why it matters for COP31", or a plain title card. (S9) | "That's COP31's Awareness priority made practical: farmers adapting to a changing climate, with climate information they can actually use." | **COP31 · Awareness Across All Areas**<br>Farmers adapting · climate information people can use |
| 10 | 1:54-2:00 | **Close.** The phone with the text, then the end card. (S10) | "DamDays. Days of water, by text, every week." | **DamDays**<br>github.com/Shaugato/damdays<br><small>Data: DEA Waterbodies (Geoscience Australia) · SILO (Queensland Government) · CC BY 4.0</small> |

**If the cut runs over 2:00,** trim in this order: beat 7's voice-over (keep its caption over the end of beat 6); "Can you trust it?" in beat 5; "Rainfall alone: a coin toss." in beat 8 (the caption still says it).

### The sealed-result line (beat 5 and the pitch)

Write it on Saturday from `artifacts/sealed/SEALED_RESULTS.md`, in one sentence of at most 12 words, whichever way it went. Templates:

- **Every pass mark met:** "It passed every mark: [a fifth] less error than the usual guess."
- **Some marks met:** "It met [x] of [y] marks; we published the miss, and why."
- **Pass marks missed:** "It fell short of our marks. Every number is published, as promised."

Caption words, the same as the test years': "[fraction] less error than guessing the usual rate"; "'at least N days' held [k] times in 10"; "the lender rating picks the right 2 km patch [k] times in 10, rainfall [m] in 10". Words for the error number (the skill score): 0.10 = "a tenth", 0.15 = "about a seventh", 0.20 = "a fifth", 0.23 to 0.24 = "nearly a quarter", 0.25 = "a quarter". Round down, never up: 0.235 is "nearly a quarter", not "a quarter".

---

## Where each number comes from

Check each one just before recording. All commands run from the repo folder.

| number | value now | source |
|---|---|---|
| The text on the phone | Farm D (near Dubbo), Fri 2 Oct 2026, 146 of 160 places | [`outbox/2026-10-02.json`](../outbox/2026-10-02.json), `farm-d`; made by [`scripts/16_weekly_texts.py`](../scripts/16_weekly_texts.py) |
| Dam 2: "~67% full", "at least 29 days" | level 67% of full at the 13 Sep look; floor 48 days from 13 Sep, less the 19 days to 2 Oct | `app/data/real/farms.json`, Farm D, dam 2 (`nsw_cw-0408`): `level_pct`, `damdays_days`, `days_left` |
| Dam 2: "3 in 10 by 12 December" | chance 0.319; window ends 2026-12-12 | same row: `chance`, `window_end` (also the long text in the outbox) |
| Dam 2: the runway | 30, 60, 90, 180 days: 0.084, 0.212, 0.319, 0.637 (about 1, 2, 3 and 6 in 10) | `app/data/real/curves.json`, issue 2026-09-14, `nsw_cw-0408` |
| Date of the latest satellite looks | 14 Sep 2026 | `app/data/real/meta.json`, `data_through` |
| 272 of 894 farm dams already below a third | 894 tracked: 576 with a forecast, 272 already below a third, 44 not refilled since their last low, 2 with no clear look in the last 60 days | `meta.json`, `coverage.live_status_counts` (command below) |
| "The most for a September since the 2019 drought" | September share below a third: 2018 0.64, 2019 0.65, 2020-2025 between 0.08 and 0.23, 2026 0.29 | `app/data/real/history.json` (command below) |
| 4,711 waterbodies in the locked region | one fingerprinted file per waterbody | [`SEALED_HASHES.csv`](../SEALED_HASHES.csv) (4,711 rows), committed in e0e9b0b, Fri 2 Oct 2026, 09:12 AEST |
| 2018-19 replay: 782 forecasts, about 248 expected, 244 fell | 1 Nov 2018: 258 judged, 76 fell, 94.6 expected · 1 Jan 2019: 288, 106, 96.7 · 1 Mar 2019: 236, 62, 57.0 · total 782, 244, 248.3 | `meta.json`, `rewind.tallies` (command below); the app's Rewind panel shows each date ("76 of 258 ... expected about 95") |
| The replay's model learned only from data before July 2016 | frozen L3, test setting | `meta.json`, `rewind.model_cutoff` (2016-07-01) |
| Ten test years: "held 9 times in 10", 729,749 forecasts, every pass mark met | held 0.9002 of 729,749 | [`artifacts/test_results.md`](../artifacts/test_results.md), "In plain words" and "PREREG pass bars" |
| Lender rating: 8 in 10 against about 5 in 10 | 0.812 against 0.527, 14,331 patch-seasons over 10 seasons | `test_results.md`, P2 table (`P2_cell`) |
| Pass marks written before any code | Fri 2 Oct 2026, 09:12 AEST | commit e0e9b0b on GitHub (adds PREREG.md) |
| Sealed numbers | after Sat 3 Oct 17:30 AEST | `artifacts/sealed/SEALED_RESULTS.md` |

**Honest framing of the hook.** In our own data, September 2026 has the most dams below a third for a September since 2019 (0.29, against a middle value of 0.26 over the Septembers since 1988), but it is far from the 2018-19 drought (about 0.64). So the script says "a dry spring" and "the most since the 2019 drought", and never "a drought like 2019". Say "the 2026 drought" only if an official source (the Bureau of Meteorology or the NSW DPI drought indicator) supports it on the day you record, and name that source on screen.

**Live fact** (beat 2):

```
.venv/Scripts/python.exe -c "import json; m=json.load(open('app/data/real/meta.json')); c=m['coverage']; print(m['data_through'], m['model']['version'], c['dams'], c['live_status_counts'])"
```

Today (the L3 export of 2 Oct 2026, 21:47 AEST) it prints `2026-09-14 L3 894 {'forecast': 576, 'already_low': 272, 'not_refilled': 44, 'no_recent_look': 2}`.

**September comparison** (beat 2):

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

**The text and Dam 2** (beats 1, 3 and 4):

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

**The 2018-19 replay** (beat 6):

```
.venv/Scripts/python.exe -c "
import json
t = json.load(open('app/data/real/meta.json'))['rewind']['tallies']
for day, v in t.items(): print(day, v['judged'], v['fell_below_third'], v['expected'])
print('total', sum(v['judged'] for v in t.values()), sum(v['fell_below_third'] for v in t.values()), round(sum(v['expected'] for v in t.values()), 1))
"
```

It prints the three dates, then `total 782 244 248.3`. "Expected" is the chances added up: ten dams at 3 in 10 each means about 3 should fall.

---

## Shot list (record in this order)

| shot | where | what to do | length to capture |
|---|---|---|---|
| S1 | phone | The Farm D text arriving: the phone drawn in the app's My farm view (Farm D); or a phone mock-up made in the video editor with the text copied exactly; or the text sent to your own phone with `notify/sms.py --send` (your own SMS account's keys, one phone, your choice). Film the buzz, then hold on the full text. | 15 s |
| S2 | app `#runway` | Start zoomed on Farm D's dams (around latitude -32.22, longitude 148.635); pull back slowly until the whole region fills the map. | 20 s |
| S3 | phone or editor | The same text, close up; highlight the Dam 1 line, then the Dam 2 line (an editor highlight is fine). | 10 s |
| S4 | app, My farm | Choose Farm D; hold on the map with the circle and numbered dams; tap Dam 2; hold on the days; slide down to the runway curve, keeping the shaded band in view. | 25 s |
| S5 | terminal and repo, Sat 3 Oct | The whole sealed-opening recording, 17:15 to about 18:00 (runbook: [SEALED_OPENING.md](SEALED_OPENING.md)). Keep the raw file as evidence; the video uses a 21-second sped-up cut with a visible clock. | whole run |
| S6 | app `#rewind` | Choose 1 Nov 2018; pause 3 s on the forecast map; press **Reveal what happened**; hold on the rings. Do the same for 1 Jan 2019 and 1 Mar 2019 (the edit uses about 2 s of each). | 40 s |
| S7 | repo | `artifacts/test_results.md`, scrolled to "PREREG pass bars and the kill rule" (every row PASS). Optional: the GitHub commit that adds PREREG.md, showing Fri 2 Oct, 09:12. | 15 s |
| S8 | app `#rating` | Choose season 2018-19; pause on the two maps; press **Reveal which ran dry**; hold. | 20 s |
| S9 | app `#about` | Scroll to "Why it matters for COP31". (Or a title card.) | 10 s |
| S10 | phone, then title card | The phone with the text for 2 s; then name, repository address, data credits. | 8 s |

## Recording checklist

- [ ] Every box under "Before recording" ticked.
- [ ] Browser at 1920 x 1080, page zoom about 125% so text reads on a phone; bookmarks bar hidden; no other tabs, emails, phone numbers or personal data on screen.
- [ ] No percent on screen means a chance: "%" is only how full a dam is.
- [ ] Captions burned into the video, and they match the voice-over.
- [ ] Final cut is **2:00 or less**; exported as 1080p MP4.
- [ ] No music, or music you made or are licensed to use; list it in [DISCLOSURE.md](../DISCLOSURE.md).
- [ ] Add the video, phone mock-up and screen-recording tools to [DISCLOSURE.md](../DISCLOSURE.md) ("Tools").
- [ ] The video link opens without asking for access.
