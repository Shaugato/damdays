# The weekly text: message spec

**What it is.** Once a week, each farm gets one text message (SMS) about its dams: how many days of water each dam that matters has left before it drops below a third, and how full it is. A longer version of the same message is for the app or an email.

**Why a text.** A mentor who grew up on farms told us (Fri 2 Oct 2026) that farmers do not open emails or apps, but "a text that comes in once a week is super handy". So the text is the product. The app is where a farm is set up and where you look deeper.

**Where the code is.** [`notify/`](.) is a small package that reads the live forecasts the app already shows. It does not import or change the frozen model (`damdays/`).

| file | what it does |
|---|---|
| [`farms.py`](farms.py) | a farm = homestead point + radius (3 km by default) + optional name; `dams_for_farm()` finds its dams and numbers them by distance |
| [`message.py`](message.py) | `weekly_text()` makes the SMS; `long_text()` makes the app/email version |
| [`gsm7.py`](gsm7.py) | which characters an SMS can carry, and how many of the 160 places each takes |
| [`outbox.py`](outbox.py) | writes the week's texts to `outbox/<date>.json` |
| [`sms.py`](sms.py) | optional Twilio sender: a dry run unless you add `--send` and your own account's keys |
| [`examples.py`](examples.py) | the inputs of the worked examples below |
| [`../scripts/16_weekly_texts.py`](../scripts/16_weekly_texts.py) | makes this week's texts for 10 demo farms (outbox, `app/data/real/farms.json`, test fixtures) |
| [`../tests/test_weekly_text.py`](../tests/test_weekly_text.py) | checks every rule on this page |
| [`../app/js/text.js`](../app/js/text.js) | the same text in JavaScript, for the phone in the app's My farm view (checked against this code: section 8) |

Run: `.venv/Scripts/python.exe scripts/16_weekly_texts.py` (seconds), then `.venv/Scripts/python.exe -m pytest tests/test_weekly_text.py`.

---

## 1. The farm and its dams

- **A farm** is a homestead point (latitude, longitude), a radius and an optional name.
- **We have no property boundaries.** So a farm's dams are the farm dams the satellites can see within the radius of the homestead: 3 km by default. On a small block the circle can take in a neighbour's dams, and on a big station it can miss some. The farmer fixes that by moving the point or changing the radius.
- **Which dams.** Every dam in the live forecasts (`app/data/real/forecasts.json`): waterbodies that look and behave like farm dams, about 0.5 ha and up. Smaller dams, tanks and bores are invisible to the satellites.
- **Numbering.** Dams are numbered by distance: **Dam 1 is the closest** to the homestead. Two dams at the same distance (to the nearest 10 m) go in order of their id. Each dam also keeps its stable id (`dam_id`, and DEA's own `dea_uid`), so it can always be traced back to the data.

## 2. The words (the mentor's rules)

The mentor read "%" as how full a dam is, not as a chance. So:

| what | how it is written | rule |
|---|---|---|
| **How full** | `~45% full`, or `full` at 100% or more | The only thing ever written as a percent. It is the dam's latest clear satellite look, against the dam's own full level. |
| **Days left** (the headline) | `at least 16 days before it drops below 1/3` | The cautious DamDays floor. On the ten test years it held 9 times in 10. **Counted from the day the text is sent**: the floor from the satellite look, minus the days since that look. |
| ... once it reaches 180 days | `6 months+` | The cap (the app shows "180+"). |
| ... once the floor has run out since the look | `may be below 1/3 now` | The cautious number of days has passed. The next clear look will tell. |
| **Chance** (long text only) | `6 in 10` | The 90-day chance of falling below a third, rounded to the nearest tenth (halves up). Under 0.05 is `less than 1 in 10`, and 0.95 or more is `more than 9 in 10`. Never a percent. The SMS gives no chances. |

"Below a third" (`1/3`) is the project's R30 line: below 30% of the dam's usual full level ([PREREG.md](../PREREG.md)).

**Why subtract the days since the look.** A forecast starts from the dam's last clear satellite look, which can be a week or more before the text goes out. "At least 35 days from 13 Sep" and "at least 16 days from 2 Oct" are the same promise, so the text gives the second one. The farmer reads days from today.

## 3. The SMS, line by line

One message, one fact per line, most important first:

| line | what | example |
|---|---|---|
| 1 | **The date** the text is sent, then the farm's latest satellite look | `Fri 2 Oct (satellite 13 Sep)` |
| 2 | **The dams that matter most**, fewest days left first: any dam whose floor has run out since its look (two or more share one line, `Dams 1 and 4 may be below 1/3 now`); **the headline dam** (the fewest days still left); and any dam with at least a **5 in 10 chance** of falling below a third within 90 days. Only the first line that gives days says "before it drops below 1/3". | `Dam 2 ~55% full: at least 18 days before it drops below 1/3`<br>`Dam 4 ~60% full: at least 33 days` |
| 3 | **Dams already below a third**, said plainly | `Dam 1 already below 1/3` · `Dam 3 looks dry` (no water seen) · `Dams 1 and 2 already below 1/3` · `5 dams already below 1/3` (5 or more) |
| 4 | **The other dams with a forecast**, summed up by their shortest floor (one dam alone gets its own line) | `Other 2 dams OK for 3 months+` (all at least 90 days) · `Other 2 dams: at least 68 days` |
| 5 | **Dams with no forecast** | `Dam 2 ~40% full: no forecast until it refills` (not back to 60% full since its last low: the forecast's starting rule) · `Dam 5: no clear satellite look lately` (none in 60 days) · `Dams 7 and 11: no forecast this week` |
| last | **The close** | `Reply MAP` (replying MAP would send the link to the farm's map in the app) |

Two special cases:

- **All is fine.** Every dam has a forecast with at least 90 days left and under a 5 in 10 chance. Then the text says `All 3 dams look OK for 3 months+` (or `Your dam ...`, or `Both dams ...`), then the headline dam's line.
- **No dams.** `No farm dams the satellites can see within 3 km`.

### Fitting one SMS

- **One SMS = 160 places, in the GSM-7 alphabet.** A single emoji or curly quote switches a message to a 70-character format, so the texts use only plain letters, digits, spaces, line breaks and `. , : ; ( ) + - / % ' ~`. No emoji.
- **`~` takes two places.** It sits in GSM-7's extension table. So `Dam 1 ~45% full` is 15 characters but 16 places. The code counts places (`gsm7.septets`), not just characters.
- **If the text is too long:** first the satellite date is left out of line 1. Then lines are left out from the end, the least important first (5, then 4, then 3, then the later lines of 2). The headline dam's line always stays. The close says how many dams were left out: `Reply MAP for 5 more dams`.

## 4. The long text (app or email)

Two to four lines:

1. The farm, the date, how many dams lie within the radius, and the latest satellite look.
2. The headline dam in full: its distance from the homestead, how full it was and on which day, its days from today, and its chance (`Chance it drops below a third by 27 Dec: 6 in 10.`).
3. `Also:` the other dams, most urgent first (at most 6 by name; the map shows them all).
4. What the days mean ("in ten test years a dam stayed above a third at least that long 9 times in 10"), and the map link (`[map link]` is a placeholder).

Example (the farm of worked example 2 below):

```
Example farm 2, Mon 5 Oct 2026: 3 farm dams within 3 km of the homestead; latest satellite look 28 Sep.
Dam 1 (0.4 km from the homestead) was ~45% full on 28 Sep: at least 23 days before it drops below a third, counted from today. Chance it drops below a third by 27 Dec: 6 in 10.
Also: Dam 3 ~80% full, at least 103 days (chance by 27 Dec: 1 in 10); Dam 2 full, at least 143 days (chance by 27 Dec: 1 in 10).
Days are counted from today and are cautious: in ten test years a dam stayed above a third at least that long 9 times in 10. Map: [map link]
```

---

## 5. Worked examples

**The numbers are made up**, only to show the rules (inputs in [`examples.py`](examples.py)). Every text is sent on **Monday 5 Oct 2026**. Every dam was last seen by the satellite on **Monday 28 Sep**, 7 days earlier, unless the table says otherwise. So "days left on 5 Oct" is the floor from the look minus 7. The chance column is the model's number (0 to 1); it decides which dams are named, but only the long text shows it ("6 in 10"). The tests check that the code makes exactly these texts.

### 1. Every dam is fine

| dam | km | status | how full | floor from the look | days left on 5 Oct | chance in 90 days |
|---|---|---|---|---|---|---|
| Dam 1 | 0.6 | forecast | 100% | 200 | 193 | 0.02 (less than 1 in 10) |
| Dam 2 | 1.4 | forecast | 85% | 140 | 133 | 0.06 (1 in 10) |
| Dam 3 | 2.2 | forecast | 70% | 120 | 113 | 0.08 (1 in 10) |

```
Mon 5 Oct (satellite 28 Sep)
All 3 dams look OK for 3 months+
Dam 3 ~70% full: at least 113 days before it drops below 1/3
Reply MAP
```

Every dam has at least 90 days and under a 5 in 10 chance. The headline dam is still named (Dam 3, the fewest days), even though it is the furthest away.

### 2. One dam at risk, the others fine

| dam | km | status | how full | floor from the look | days left on 5 Oct | chance in 90 days |
|---|---|---|---|---|---|---|
| Dam 1 | 0.4 | forecast | 45% | 30 | 23 | 0.62 (6 in 10) |
| Dam 2 | 1.1 | forecast | 100% | 150 | 143 | 0.05 (1 in 10) |
| Dam 3 | 2.7 | forecast | 80% | 110 | 103 | 0.09 (1 in 10) |

```
Mon 5 Oct (satellite 28 Sep)
Dam 1 ~45% full: at least 23 days before it drops below 1/3
Other 2 dams OK for 3 months+
Reply MAP
```

The floor was 30 days from 28 Sep, so it is 23 days from 5 Oct.

### 3. A dam already below a third

| dam | km | status | how full | floor from the look | days left on 5 Oct | chance in 90 days |
|---|---|---|---|---|---|---|
| Dam 1 | 0.8 | already_low | 25% | - | - | - |
| Dam 2 | 1.9 | forecast | 65% | 60 | 53 | 0.35 (4 in 10) |

```
Mon 5 Oct (satellite 28 Sep)
Dam 2 ~65% full: at least 53 days before it drops below 1/3
Dam 1 already below 1/3
Reply MAP
```

The days come first, because they are the headline. Then it says plainly which dam is already below a third. Its fullness (~25%) is in the long text.

### 4. Two dams at risk, and the rest summed up (the satellite date is left out to fit)

| dam | km | status | how full | floor from the look | days left on 5 Oct | chance in 90 days |
|---|---|---|---|---|---|---|
| Dam 1 | 0.5 | forecast | 90% | 75 | 68 | 0.3 (3 in 10) |
| Dam 2 | 1.2 | forecast | 55% | 25 | 18 | 0.71 (7 in 10) |
| Dam 3 | 1.8 | forecast | 95% | 95 | 88 | 0.2 (2 in 10) |
| Dam 4 | 2.6 | forecast | 60% | 40 | 33 | 0.52 (5 in 10) |

```
Mon 5 Oct
Dam 2 ~55% full: at least 18 days before it drops below 1/3
Dam 4 ~60% full: at least 33 days
Other 2 dams: at least 68 days
Reply MAP
```

Dam 2 is the headline. Dam 4 is named too, because it has a 5 in 10 chance. With the satellite date, the text would take 165 places, so the date is left out first (146 places).

### 5. A floor that ran out since the satellite look, and a dry dam

| dam | km | status | how full | floor from the look | days left on 5 Oct | chance in 90 days |
|---|---|---|---|---|---|---|
| Dam 1 | 0.3 | forecast | 35% | 5 | -2 | 0.81 (8 in 10) |
| Dam 2 | 1.0 | forecast | 60% | 50 | 43 | 0.4 (4 in 10) |
| Dam 3 | 2.4 | already_low | 0% | - | - | - |

```
Mon 5 Oct (satellite 28 Sep)
Dam 1 ~35% full: may be below 1/3 now
Dam 2 ~60% full: at least 43 days before it drops below 1/3
Dam 3 looks dry
Reply MAP
```

Dam 1's 5 cautious days ran out on 3 Oct, so the text does not promise any more. Dam 2 has the fewest days still left, so it is named and carries "before it drops below 1/3".

### 6. One dam, its floor capped at 6 months

| dam | km | status | how full | floor from the look | days left on 5 Oct | chance in 90 days |
|---|---|---|---|---|---|---|
| Dam 1 | 0.9 | forecast | 100% | 260 | 253 | 0.01 (less than 1 in 10) |

```
Mon 5 Oct (satellite 28 Sep)
Your dam looks OK for 3 months+
Dam 1 full: 6 months+ before it drops below 1/3
Reply MAP
```

253 days is past the 180-day cap, so it is "6 months+". At 100% or more the dam is simply "full".

### 7. Every dam already below a third

| dam | km | status | how full | floor from the look | days left on 5 Oct | chance in 90 days |
|---|---|---|---|---|---|---|
| Dam 1 | 0.7 | already_low | 0% | - | - | - |
| Dam 2 | 1.6 | already_low | 15% | - | - | - |

```
Mon 5 Oct (satellite 28 Sep)
Dams 1 and 2 already below 1/3
Reply MAP
```

Two to four such dams are listed by number, and five or more are counted. The long text says Dam 1 looks dry and Dam 2 is ~15% full.

### 8. A dam with no forecast until it refills

| dam | km | status | how full | floor from the look | days left on 5 Oct | chance in 90 days |
|---|---|---|---|---|---|---|
| Dam 1 | 1.2 | forecast | 75% | 45 | 38 | 0.38 (4 in 10) |
| Dam 2 | 2.0 | not_refilled | 40% | - | - | - |

```
Mon 5 Oct (satellite 28 Sep)
Dam 1 ~75% full: at least 38 days before it drops below 1/3
Dam 2 ~40% full: no forecast until it refills
Reply MAP
```

A forecast starts only once a dam has been back to 60% full within the last 180 days, with no fall below a third since (the PREREG starting rule). Dam 2 has not.

### 9. Twelve dams: lines left out to fit one SMS

| dam | km | status | how full | floor from the look | days left on 5 Oct | chance in 90 days |
|---|---|---|---|---|---|---|
| Dam 1 | 0.3 | forecast | 70% | 64 | 57 | 0.33 (3 in 10) |
| Dam 2 | 0.6 | already_low | 22% | - | - | - |
| Dam 3 | 0.9 | forecast | 50% | 21 | 14 | 0.68 (7 in 10) |
| Dam 4 | 1.1 | already_low | 18% | - | - | - |
| Dam 5 | 1.3 | forecast | 85% | 130 | 123 | 0.07 (1 in 10) |
| Dam 6 | 1.6 | already_low | 9% | - | - | - |
| Dam 7 | 1.8 | not_refilled | 41% | - | - | - |
| Dam 8 | 2.0 | forecast | 58% | 36 | 29 | 0.55 (6 in 10) |
| Dam 9 | 2.2 | already_low | 0% | - | - | - |
| Dam 10 | 2.5 | already_low | 26% | - | - | - |
| Dam 11 | 2.7 | no_recent_look (last look 10 Jul) | 90% | - | - | - |
| Dam 12 | 2.9 | forecast | 100% | 190 | 183 | 0.02 (less than 1 in 10) |

```
Mon 5 Oct
Dam 3 ~50% full: at least 14 days before it drops below 1/3
Dam 8 ~58% full: at least 29 days
5 dams already below 1/3
Reply MAP for 5 more dams
```

In full, it would also say `Other 3 dams: at least 57 days` and `Dams 7 and 11: no forecast this week`. That is 227 places. Leaving out the satellite date and those two lines (5 dams) brings it to 156. The long text names 6 of the other dams and points to the map for the rest.

### 10. No dam the satellites can see within 3 km

No dam within 3 km.

```
Mon 5 Oct
No farm dams the satellites can see within 3 km
Reply MAP
```

---

## 6. This week's real texts

`scripts/16_weekly_texts.py` makes the texts for 10 demo farms from the live forecasts (data to 14 Sep 2026):

- **5 farms in NSW Central West**, from the app's published file.
- **5 farms in western Victoria / SE South Australia**, from the same production fit. The script rebuilds them with the app exporter's own functions, and it first checks that rebuilding NSW the same way gives the published file row for row.

Each homestead point is the middle of a real cluster of dams (the densest clusters, at least 25 km apart), named after the nearest town. **They are not real homesteads.** The texts go to `outbox/<date>.json` and `app/data/real/farms.json`. For example, the text made on Fri 2 Oct 2026 for Farm D (near Dubbo), 7 dams within 3 km:

```
Fri 2 Oct (satellite 13 Sep)
Dam 2 ~67% full: at least 29 days before it drops below 1/3
Dam 1 looks dry
Other 5 dams: at least 52 days
Reply MAP
```

Dam 2's forecast was made from its 13 Sep look, so its floor (48 days from then) is 29 days from 2 Oct.

## 7. Sending (optional, never automatic)

`notify/sms.py` reads an outbox file and, by default, only prints what it would send (a dry run). It sends through Twilio's REST API **only** if both of these hold:

- the command has `--send`;
- the environment holds your own account's `TWILIO_SID`, `TWILIO_TOKEN` and `TWILIO_FROM`. No keys are kept in this repository.

The demo farms have no phone numbers, so a real send also needs `--farm` and `--to` (one farm's text to one phone).

```
.venv/Scripts/python.exe -m notify.sms outbox/2026-10-02.json                                      # dry run
.venv/Scripts/python.exe -m notify.sms outbox/2026-10-02.json --farm farm-d --to +61491570156 --send # real send
```

**Not built yet (needed for a real service):**

- sending only to farmers who opted in when they set up their farm;
- the `MAP` and `STOP` replies;
- a sender name.

Australia's Spam Act 2003 asks commercial messages to identify the sender and to offer a working unsubscribe.

## 8. The app's JavaScript port

The app's **My farm** view (`app/index.html`, opens first) shows the weekly text on a drawn phone for any homestead you click on the map. That text is made in the browser by [`app/js/text.js`](../app/js/text.js), a line-for-line port of `message.py` (and the parts of `farms.py` and `gsm7.py` it needs). To check that the port writes exactly what Python writes:

```
node app/tools/check_text_port.js                                # the fixtures below and app/data/real/farms.json
.venv/Scripts/python.exe -m pytest tests/test_app_text_port.py   # the same, plus 600 random farms made by Python
```

`scripts/16_weekly_texts.py` writes two fixtures for this check:

- [`fixtures/spec_examples.json`](fixtures/spec_examples.json): the 10 worked examples above.
- [`fixtures/demo_week.json`](fixtures/demo_week.json): this week's 10 demo farms. It keeps their dams, plus those up to 1 km beyond each radius, so the cut-off is tested too.

Each fixture holds `today`, the input `forecasts` (the format of `forecasts.json`), and `cases`. Each case has a `farm` and the expected `dam_ids` (closest first), `sms` and `long`. Run each farm on `today` and compare the texts exactly.

Three details keep the two languages in step:

- **Rounding is halves-up in whole numbers:**
  - chance to tenths: `floor((floor(c*1000 + 0.5) + 50) / 100)`;
  - distance to 10 m: `floor(km*100 + 0.5) / 100`;
  - one decimal: `floor(km*10 + 0.5)`.
- **Dates are calendar days** (`YYYY-MM-DD`, no time zone), with fixed English names (`Mon`, `Sep`).
- **Distances** use the haversine formula with an Earth radius of 6371.0088 km.
