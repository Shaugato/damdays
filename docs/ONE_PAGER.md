# DamDays on one page

Climate Hack-tion 2026 · Build for 2035 · COP31 track: **Awareness Across All Areas** · Sun 4 Oct 2026 · App: https://shaugato.github.io/damdays/app/ · Code: https://github.com/Shaugato/damdays

## The problem, in one sentence

Graziers whose stock drink from farm dams have no easy way to know how many days of water each dam has left, so the costly moves a drought forces (move stock, cart water, buy feed, agist or sell) rest on guesswork, and when they are left late the choices shrink.

Today they drive the water run and do the sums by hand: measure the dam, look up its volume, divide by what the stock drink.

## Which farms

**Family sheep and cattle farms in south-eastern Australia's dam country** (NSW, Victoria, South Australia): mostly 300 to 1,500 ha, a few hundred cattle or a few thousand sheep, run by one or two people, whose stock drink from **at least one farm dam big enough for the satellites to see** (about 0.5 to 5 ha of water). Not bore-fed stations, irrigators or hobby blocks. Not every farm has such a dam (in our test regions, only about 1 in 6 evenly spaced points, farmland or not, has one within 3 km), and a typical target farm will see 1 or 2 of its dams in the text. Profile and sources: [TARGET_FARMER.md](TARGET_FARMER.md).

## What DamDays does

- **One text a week.** A mentor told us farmers rarely open apps or emails, so the product is one SMS per farm (not yet tried with farmers). The real text for a demo farm near Mudgee (Farm E) on Fri 2 Oct (real dams and forecasts; the homestead point is made up, and its 3 km circle is bigger than a typical farm):
  ```
  Fri 2 Oct (dams seen 13 Sep)
  Dam 1 ~80% full: at least 68 days before it drops below 1/3
  Dam 3: no water seen
  Other 2 dams: 3 months+
  Reply MAP for 1 more dam
  ```
  "Dams seen 13 Sep" is the date of the satellites' last clear look at the farm's dams; the days are counted from the day of the text.
- **Dam by dam: how full, days left, and the chance.** How full each dam was at its last clear satellite look; at least how many days before it drops below a third (cautious by design, built to hold 9 times in 10 across all dams, a little less often for spring looks); and in the app, the chance it drops below a third within 90 days of that satellite look (Dam 1: 1 in 10 by 12 Dec). "No water seen" means the satellite saw no water at its last clear look; one look can be wrong, so we never call a dam dry.
- **How a satellite tells how much water, when dams differ in size and depth.** It can't measure litres. It sees how much of a dam's outline is wet, and we compare that with the same dam's own usual full water surface: "%" only ever means that share, not depth. So a big dam and a small one are each measured against themselves, and each dam's 38-year record shows how fast its surface shrinks in a dry spell.
- **How the days are worked out.** Models learn, from each dam's 38-year satellite record and the rainfall, how fast dams like it drop in a dry spell, then give a cautious count of days before it drops below a third, built to hold 9 times in 10.
- **No sensors.** Nothing to install or measure: each dam's satellite water record (Geoscience Australia) and the rainfall (SILO), both free. A dam sensor reads one dam's level now, more exactly than we can, but it has to be bought and fitted to each dam, and none of the sensors we checked advertised a forecast.

## Why now

Dams are lower this spring than in any September since the 2019 drought. At the latest satellite looks (to 14 Sep 2026), **272 of the 894 dam-sized waterbodies DamDays tracks in NSW Central West (mostly farm dams) were already below a third full**: about 3 in 10, the most for a September since 2019 (a typical September since 1988 is about 1 in 4; in the 2018-19 drought it was over 6 in 10).

## What already exists, and what is new

Forecasting stock water is not new. Sensors show one dam's level now; NSW's monthly maps use the same satellite data, by parish, with no forecast; Victoria's calculators and Small Farm Dams pilot need the farmer to measure each dam; USGS FEWS NET forecasts African waterholes 30 days ahead. What we did not find is a forecast for **each farm dam big enough for the satellites to see (about 0.5 to 5 ha), with nothing to install**, whose accuracy is **tested in public** (on ten years it never trained on, and on the unseen exam below), sent **dam by dam as one weekly text** with our record on each dam. Full comparison: [WHAT_EXISTS.md](WHAT_EXISTS.md).

## How we know it works

- **The exam came first.** Test rules and pass marks were committed at 09:12 AEST on Fri 2 Oct, before the build began ([PREREG.md](../PREREG.md)).
- **Ten years it never trained on.** Trained only on data before July 2016, tested once on every year to June 2026. The chances (142,938 forecasts made from October to March, when dams run down) had **nearly a quarter less error than the usual guess** (how often dams in that region fell below a third in that month in earlier years), and less in every one of the ten years; the pass mark, written first, was a tenth less. The cautious **days-left promise held 9 times in 10** (900 times in 1,000, over 729,749 forecasts made all year round), as designed ([results](../artifacts/test_results.md)).
- **A farmer can judge it on their own dam.** Each dam's card says how often our days-left number held on it over the last 10 years (we re-ran our forecasts for July 2016 to June 2026 using only data from before July 2016, then checked each one against what the dam really did). On Farm E's 5 dams it held 1,640 of 1,767 times (about 9 in 10); on Dam 1 above, 380 of 428. The typical dam held 912 times in 1,000, and weak dams are shown too: 101 of the 929 dams with a record held less than 8 times in 10 ([record, every number](../artifacts/track_record.md)).
- **The unseen exam.** A third farming region (Southern Downs, Granite Belt, New England) whose satellite data we downloaded and fingerprinted before the event and then never opened or used, kept aside for one final check. Pre-registered to open on Sat 3 Oct, 17:30 AEST, it was opened on Sun 4 Oct, after the app build ([Addendum 2](../PREREG_ADDENDUM_2.md)), once, on camera (09:20 to 10:16 AEDT). **Result: all 4 pre-registered pass marks met.** Nearly a fifth less error than the usual guess (we expected a fifth to a quarter; the ten test years gave nearly a quarter); the cautious days-left number held 882 times in 1,000 (on target: 880 to 920); and it picked the right 2 km area 8 times in 10, against 5 in 10 for rainfall alone. Every number: [SEALED_RESULTS.md](../artifacts/sealed/SEALED_RESULTS.md). (The ten test years were looked at in pre-event research, so they may flatter the model slightly; this is the clean test.)

## COP31 priority

**Awareness Across All Areas:** "helping farmers and land managers adapt" to a changing climate, toward the track's 2035 goal of climate-resilient farming. DamDays turns free satellite and climate data into one line a farmer can act on early. **Secondary:** less waste: fewer stock losses, less wasted feed, better use of on-farm water (not yet measured).

## Who will use it, and who pays

**Farmers first**, as the users (a mentor's advice); then **drought support programmes and agencies** (such as state drought teams and Local Land Services), to provide DamDays to the farmers in their region and see on the district view (Runway) where stock water runs short first; **fire agencies**, to know before fire season which farm dams crews and aircraft can still refill from; and **farm software platforms and dam-sensor companies, as partners**. Later, rural lenders and insurers (set aside for now on mentor advice). We have not set prices or approached these customers yet; the next step is to talk to farmers and two drought programmes.

## What it doesn't do yet

- No small dams (most farm dams are under 0.5 ha), bores, tanks or rivers.
- No depth or volume: "below a third" is our plain rounding of below 30% of the dam's usual wet area, from a satellite look that can be weeks old. "No water seen" is not "dry": one look can miss a small pool or muddy water.
- Not every dam-sized waterbody is a farm dam: the filter also catches some town and industrial ponds. We checked the demo farms against aerial photos and set aside the Dubbo one (treatment ponds, a racecourse pond and the river); Farm E's 5 dams are all farm dams.
- Australia only, for now: built on Australian satellite and rainfall records and tested only in south-eastern Australia. Landsat covers the world, so other countries are a later path; each would need its own waterbody record and its own test.
- Not yet a running service: no texts sent to real farmers, MAP and STOP replies not built, refits run by hand.
