# DamDays on one page

Climate Hack-tion 2026 · Build for 2035 · COP31 track: **Awareness Across All Areas** · Sat 3 Oct 2026

## The problem

Graziers whose stock drink from farm dams have no easy way to know how many days of water each dam has left: today they drive the water run and do the sums by hand. That number decides when to move stock, cart water, buy feed, agist or sell, and in a drought, leaving it late narrows the choices and raises the cost.

## Who has it

**Family sheep and cattle farms in south-eastern Australia's dam country** (NSW, Victoria, South Australia): mostly 300 to 1,500 ha, a few hundred cattle or a few thousand sheep, run by one or two people, whose stock drink from **at least one dam the satellites can see** (about 0.5 ha of water or more). Not bore-fed stations, irrigators or hobby blocks. Not every farm has such a dam (in our test regions, about 1 in 11 points has one within 2 km), and a typical target farm will see 1 or 2 of its dams in the text. Profile and sources: [TARGET_FARMER.md](TARGET_FARMER.md).

## What DamDays does

- **One text a week.** Farmers rarely open apps or emails, so the product is one SMS per farm. The real text for a demo farm near Dubbo on Fri 2 Oct (real dams and forecasts; the homestead point is made up):
  ```
  Fri 2 Oct (satellite 13 Sep)
  Dam 2 ~67% full: at least 29 days before it drops below 1/3
  Dam 1 looks dry
  Other 5 dams: at least 52 days
  Reply MAP
  ```
- **Dam by dam: how full, days left, and the chance.** How full each dam was at its last clear satellite look; at least how many days before it drops below a third (cautious by design, built to hold 9 times in 10); and in the app, the chance it drops below a third within 90 days of that satellite look (Dam 2: 3 in 10 by 12 Dec).
- **No sensors.** Nothing to install or measure: each dam's 38-year satellite water record (Geoscience Australia) and the rainfall (SILO), both free.

## Why now

This spring is dry. At the latest satellite looks (to 14 Sep 2026), **272 of the 894 farm dams DamDays tracks in NSW Central West were already below a third full**: about 3 in 10, the most for a September since 2019 (in the 2018-19 drought it was over 6 in 10).

## What exists, and why DamDays is different

Forecasting stock water is not new. Sensors show one dam's level now; NSW's monthly maps use the same satellite data, by parish, with no forecast; Victoria's calculators and Small Farm Dams pilot need the farmer to measure each dam; USGS FEWS NET forecasts African waterholes 30 days ahead. What we did not find is a forecast for **every farm dam the satellites can see, with nothing to install**, whose accuracy is **tested in public** (on ten years it never trained on, and today on a sealed region it has never seen), sent **dam by dam as one weekly text** with each dam's own track record. Full comparison: [WHAT_EXISTS.md](WHAT_EXISTS.md).

## How we know it works

- **The exam came first.** Test rules and pass marks were committed at 09:12 on Fri 2 Oct, before any code ([PREREG.md](../PREREG.md)).
- **Ten years it never saw.** Trained only on data before July 2016, tested once on every year to June 2026 (142,938 forecasts): **nearly a quarter less error than the usual guess**, and less in every one of the ten years. The cautious **days-left promise held 9 times in 10** (900 in 1,000), as designed ([results](../artifacts/test_results.md)).
- **A track record on your own dam.** Each dam's card says how often the promise held on it: the typical dam 912 times in 1,000; Dam 2 above, 198 of 222. Weak dams are shown too: 101 of the 929 dams with a record held less than 8 times in 10 ([track record](../artifacts/track_record.md)).
- **The unseen exam.** A whole region, locked away with public fingerprints, opens once on camera on **Sat 3 Oct, 17:30 AEST**; the score is published whatever it is. (The ten test years were looked at in pre-event research, so they may flatter the model slightly; this is the clean test.)

## COP31 priority

**Awareness Across All Areas:** "helping farmers and land managers adapt" to a changing climate, toward the track's 2035 goal of climate-resilient farming. DamDays turns free satellite and climate data into one line a farmer can act on early. **Secondary:** less waste: fewer stock losses, less wasted feed, better use of on-farm water (not yet measured).

## What it doesn't do yet

- No small dams (most farm dams are under 0.5 ha), bores, tanks or rivers.
- No depth or volume: "a third" is a third of the dam's usual wet area, from a satellite look that can be weeks old.
- Tested only in south-eastern Australia; no other country tried.
- Not yet a running service: no texts sent to real farmers, MAP and STOP replies not built, refits run by hand.
