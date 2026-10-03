# What already exists, and where DamDays is different

A mentor told us to search "dam management and forecasting system", see how much comes up, and find what is truly new about DamDays. This page is that search.

- **Checked live on Sat 3 Oct 2026**, by web search and by opening each product's own page (a few government pages block automatic fetching, so they were read in a browser). It re-checks a list of competitors from our pre-event research and adds what today's searches found.
- **Where a detail could not be confirmed, the table says so** ("not checked", "not public", "not stated"). Not finding something is not proof that it does not exist.
- **DamDays numbers** come from [`artifacts/test_results.md`](../artifacts/test_results.md) and the [README](../README.md). The sealed region opens at 17:30 AEST today; its results are not on this page.

## The short answer

- **A lot exists.** Software for big dams, sensors you put in a farm dam, government maps made from satellite data, calculators, rainfall and pasture outlooks, and in Africa a free forecast for livestock waterholes.
- **The closest to DamDays:**
  - Victoria's **Small Farm Dams planning tool**: a 12-month water balance forecast for one dam. The farmer draws the dam on a map and types in its depth.
  - Agriculture Victoria's **Summer Water Calculator**: days of water left, worked out from the farmer's own measurements.
  - NSW DPIRD's **monthly farm dam maps**: the same satellite data DamDays uses, reported by parish, with no forecast.
  - USGS FEWS NET's **Water Point Viewer**: a 30-day status forecast for each waterhole it tracks, in Africa.
- **What we did not find:** a forecast for each farm dam big enough to see from space (about 0.5 to 5 ha) that needs nothing installed or measured, whose chances have been tested in public on years the model never trained on and a region it never saw, and that reaches the farmer as one text a week.

## The table

Column meanings:
- **Per dam?** Does it give an answer for one specific dam or water point?
- **Forecasts days ahead?** Does it say anything about the water to come, not just the water now?
- **Needs sensors or site visits?** Does the farmer have to install hardware, or go out and measure?

### Big dams: reservoir operations, hydropower and dam safety

None of these is built for farm dams. They are what a search for "dam management and forecasting system" mostly brings up.

| name | what it does | per dam? | forecasts days ahead? | needs sensors or site visits? | cost | source URL |
|---|---|---|---|---|---|---|
| Japan Water Agency, Dam Reservoir Inflow Forecasting System | Forecasts the water flowing into a reservoir, and the river below it, from rainfall, for dam operators | Yes, large reservoirs | Yes, inflow (how far ahead is not stated on the page) | Yes: the operator's rain and river data for the catchment | Not public | https://www.jwa.or.jp/english/services-solutions/disaster-mitigation/dam-reservoir-inflow-forecasting-system/ |
| ADASA, DAMER (dam emergency management) | Tracks a dam's condition, manages its emergency plan and warns people downstream; includes "predictive modelling" of water levels | Yes, large dams | Partly (how far ahead is not stated) | Yes: the dam's own monitoring | Not public | https://www.adasasystems.com/en/solution/dam-management-damer-dam-emergency-management.html |
| Deltares, Delft-FEWS | A forecasting platform used in nearly 70 countries, mostly for floods, also for running reservoirs and hydropower | Rivers and reservoir systems | Yes, depending on how each system is set up | Yes: river gauges and expert set-up | Software free; set-up by specialists (cost not public) | https://oss.deltares.nl/web/delft-fews |
| Water utility apps (Seqwater, Sunwater, Melbourne's Water Storages) | Today's levels of big public dams; release alerts | Yes, public storages only | No | No (the utility measures them) | Free | https://apps.apple.com/au/app/seqwater/id1173354226 , https://www.sunwater.com.au/community/sunwater-app/ |

### Farm water sensors

A device in the dam, tank or trough reports the level now. None of these product pages advertised a forecast or "days of water left" (checked 3 Oct 2026).

| name | what it does | per dam? | forecasts days ahead? | needs sensors or site visits? | cost | source URL |
|---|---|---|---|---|---|---|
| Farmbot | Dam and turkey-nest level sensor: levels in near real time, SMS or email alerts when the level is low, high or falling fast, and history. Dam survey data can turn the level into a volume. Says it is "trusted by over 8,000" farmers (not checked) | Yes, each dam with a sensor | No forecast advertised (product page, FAQ, home page) | Yes: a sensor in each dam | Dam Level Sensor $579 (NSW DPIRD AgTech Finder listing, undated). Farmbot's 2021 price guide: Water Level Monitor $1,290 plus $342 a year on 4G or $456 on satellite, before GST. Today's page says "Request a quote" | https://farmbot.com.au/product/dam-level-sensor/ , https://www.agtech.dpi.nsw.gov.au/collections/water-management/products/farmbot-dam-level-sensor |
| Farmo | Tank level monitor: depth and how full the tank is, water use and leak history, alerts | Yes, each tank with a monitor | No forecast advertised | Yes | $599 including GST, plus $11 a month per device before GST | https://www.farmo.com.au/products/water-level-monitor |
| farmIT (damIT) | Dam water level sensor with high and low alerts | Yes | No forecast mentioned | Yes | $750 plus GST and postage; no subscription | https://farmit.com.au/products/dam-water-level-sensor/ |
| mOOvement | Pressure sensor for tanks, troughs, dams and creeks on its own radio network; 30 days of history and alerts | Yes | No forecast mentioned | Yes | One-off sensor cost, no monthly data fees (price not on the page) | https://www.moovement.com.au/water-monitoring |
| Agbot (shown inside AgriWebb) | Tank, trough and rain gauge monitors shown on the AgriWebb farm map | Yes, each tank or trough with a monitor | No forecast mentioned | Yes | Not public. Agbot's own website refused to connect on 3 Oct 2026, so it was not checked directly | https://www.agriwebb.com/integrations/agbot/ |

For scale: in an Agriculture Victoria case study, trough and tank sensors cost about $545 per device plus $8 to $10 a month ([TARGET_FARMER.md](TARGET_FARMER.md)).

### Government and public monitoring

These are maps of the water now, or of the past. None forecasts a dam's water.

| name | what it does | per dam? | forecasts days ahead? | needs sensors or site visits? | cost | source URL |
|---|---|---|---|---|---|---|
| NSW DPIRD Farm Dam Water assessment (with Geoscience Australia's Digital Earth Australia) | About 47,000 NSW waterbodies: today's water area against the largest on record since 1987, added up by parish and reported monthly in the NSW State Seasonal Update. The August 2026 update says many NSW farm dams have water covering less than 20% of their full area | No: published by parish | No | No | Free | https://www.dpird.nsw.gov.au/dpi/climate/seasonal-conditions-and-drought/key-research/features-of-the-nsw-state-seasonal-update/farm-water-monitoring , https://www.dpird.nsw.gov.au/climate_applications/state-seasonal-update/summary |
| DEA Waterbodies (Geoscience Australia) | Over 300,000 Australian waterbodies, each one's wet area over time since 1986, updated as new satellite looks arrive. **DamDays is built on this record** | Yes | No | No | Free (CC BY 4.0) | https://knowledge.dea.ga.gov.au/data/product/dea-waterbodies-landsat/index.html |
| AusDams.org (Malerba and others, Deakin University) | Free maps and statistics for nearly 1.8 million farm dams (water security, methane, wildlife). A 2022 paper by the same group modelled how often farm dams are empty, out to 2050 | Maps each dam; what it shows per dam was not checked | Long-term (to 2050), not days | No | Free | https://ausdams.org/ , https://pubmed.ncbi.nlm.nih.gov/35283121/ |
| WA DPIRD WaterSmart Farms, and OmniWaterMask | Farm dams of WA's south-west mapped by AI, on an interactive map. OmniWaterMask is the open (MIT licence) tool behind it: it finds water in satellite and aerial images with pixels as small as 0.2 m | Maps each dam | No | No | Free | https://www.dpird.wa.gov.au/environment-and-sustainability/water/watersmart-farms/ , https://github.com/DPIRD-DMA/OmniWaterMask |

### Calculators: the farmer measures, the tool does the sums

| name | what it does | per dam? | forecasts days ahead? | needs sensors or site visits? | cost | source URL |
|---|---|---|---|---|---|---|
| Agriculture Victoria, Summer Water Calculator (page updated 17 Jun 2026) | The farmer enters each dam's or tank's shape and measured depth, and the stock type and numbers. It allows for sloping banks, sludge and average summer evaporation, and estimates how long the water for stock will last | Yes, each dam the farmer enters | Yes: days of water, as one fixed number from average evaporation; no rain, no chances | Yes: measure each dam's depth (Agriculture Victoria's DAMDEEP is a home-made reel, float and sinker for this) | Free, no login | https://agriculture.vic.gov.au/support-and-resources/tools-and-calculators/summer-water-calculator , https://agriculture.vic.gov.au/about/media-centre/media-releases/2024-releases/damdeep-tool-impresses-farmers-in-south-west-victoria |
| Agriculture Victoria, Farm Water Calculator | The farm's water for a year: how much is used, how much can be stored and where supply comes from; "a guide only" | Whole farm | A year's balance, not days | Yes: the farmer's own figures | Free | https://agriculture.vic.gov.au/farm-management/prepare/tools-and-calculators/farm-water-calculator |
| **Small Farm Dams planning tool** (Southern Farming Systems and Federation University's CeRDI; Future Drought Fund) | **The closest Australian tool to DamDays.** The farmer draws the dam and its catchment on a map, picks a dam shape, and types in the depth when full and the depth now. It gives water balance forecasts for the next 12 months from the area's past 10 to 50 years of climate. A pilot for Victoria, built from 12 monitored dams. Its own limits page calls the results "indicative" and says calibration of seepage and runoff is ongoing. We found no published check of its forecasts against what dams actually did | Yes, the dam the farmer draws | Yes, 12 months | Yes: the farmer measures the current depth | Free to use (publicly funded; no price shown) | https://fdfdams.cerdi.edu.au/ , https://fdfdams.cerdi.edu.au/planning-tool/planning-tool-limitations , https://sfs.org.au/project/assessing-the-suitability-of-existing-small-farm-dams-to-prepare-for-cope-with-and-recover-from-drought |

### Rainfall and drought forecasts

| name | what it does | per dam? | forecasts days ahead? | needs sensors or site visits? | cost | source URL |
|---|---|---|---|---|---|---|
| Bureau of Meteorology, long-range forecasts | The chance of rain and temperature being above or below normal, weeks, months and seasons ahead (issued Thursdays; one- and two-week forecasts daily) | No (a map) | Rain and temperature, not the water in a dam | No | Free | https://www.bom.gov.au/climate/outlooks/ |
| NSW DPIRD Seasonal Drought Forecast | Drives NSW's drought model with 99 runs of the Bureau's ACCESS-S2 seasonal forecast: the most likely drought category 3 months ahead, by parish, with how much the runs agree and a map of past skill | No (by parish) | Yes, 3 months, but drought category, not water | No | Free | https://www.dpird.nsw.gov.au/dpi/climate/seasonal-conditions-and-drought/key-research/seasonal-drought-forecast |
| My Climate View (CSIRO and the Bureau; Future Drought Fund) | Past climate, seasonal forecasts and future climate for 20 farm commodities; drought history and projections added in June 2026 | No | Climate, not the water in a dam | No | Free | https://www.csiro.au/en/news/All/News/2026/June/New-drought-insights-added-to-My-Climate-View |

### Feed and pasture forecasting

| name | what it does | per dam? | forecasts days ahead? | needs sensors or site visits? | cost | source URL |
|---|---|---|---|---|---|---|
| Farming Forecaster (CSIRO, NSW Government, Tasmanian Institute of Agriculture, Agriculture Victoria, National Landcare Program) | The likely range of pasture available over the next 3 to 4 months, at sites with soil-moisture probes | No (per probe site) | Pasture, 3 to 4 months | Uses the program's own probes | Not stated (publicly funded) | https://farmingforecaster.com.au/ |
| AussieGRASS (Queensland Government, Long Paddock) | A national daily pasture growth model; a 3-month pasture growth outlook written as a chance, with a skill score | No (a map) | Pasture, 3 months | No | Free | https://www.longpaddock.qld.gov.au/aussiegrass/ |
| FORAGE (Long Paddock) | Queensland property reports, including a pasture growth alert. Its "flood and dam information" page links to big public storages, not farm dams | No | Pasture alerts | No | Free reports; a subscription service is also listed (not checked) | https://www.longpaddock.qld.gov.au/forage/ |
| Cibo Labs (PastureKey; MLA's Australian Feedbase Monitor) | Weekly satellite estimates of pasture and ground cover | No (per paddock) | No forecast on its home page | No | Feedbase Monitor free to MLA members; other prices not shown | https://www.cibolabs.com.au/ |
| Pasture.io | Daily pasture cover and growth, grazing plans; says "forecast what is coming"; Australia, New Zealand, UK, US | No (per paddock) | Pasture | Not checked | Plans page not checked | https://pasture.io/ |

### International

| name | what it does | per dam? | forecasts days ahead? | needs sensors or site visits? | cost | source URL |
|---|---|---|---|---|---|---|
| **USGS FEWS NET Water Point Viewer** | Satellite rainfall and a water balance model for each livestock water point: daily depth and condition since 1981 ("Good", "Watch", "Alert", "Near-Dry", "Seasonally-Dry"), now with a 30-day forecast of each water point's status. On 3 Oct 2026 its table listed 299 water points in 16 countries in Africa plus Yemen (our count; its older description says 234 water points from Senegal to Somalia) | Yes, each water point | Yes, 30 days | No | Free | https://earlywarning.usgs.gov/fews/waterpoint/ , https://earlywarning.usgs.gov/fews/ |
| Ethiopia's National Rangeland Monitoring System (Alliance of Bioversity International and CIAT, with the Ethiopian Institute of Agricultural Research) | Water points and pasture, from field reports and satellites: daily updates, monthly bulletins, seasonal climate advice and SMS alerts to communities | Monitors water points; a forecast per water point is not stated | Seasonal climate advice (per water point not stated) | Yes: field reports | Not stated | https://alliancebioversityciat.org/stories/ethiopian-pastoralists-use-digital-monitoring-system-avoid-crisis |
| SCO StockWater (CNES and IRD, France) | Volume, filling rate and water area of 110 reservoirs in India, Tunisia, Laos, Burkina Faso and Brazil, from radar and optical satellites and a terrain model | Yes, reservoirs | No (monitoring only) | No | Results public | https://www.spaceclimateobservatory.org/stock-water |
| Digital Earth Africa Waterbodies | Africa's version of DEA Waterbodies: over 700,000 waterbodies, each one's wet area over time since 1984 | Yes | No | No | Free (CC BY 4.0) | https://docs.digitalearthafrica.org/en/latest/sandbox/notebooks/Datasets/Waterbodies.html |
| JRC Global Surface Water (European Commission) | Maps of surface water for the whole world, month by month, at 30 m, from Landsat since 1984 | No (per pixel, not per dam) | No | No | Free | https://global-surface-water.appspot.com/ |
| AQUAOSO (US) | Water and climate risk maps for farm lenders; says it serves 30+ organisations | Per land parcel, not per dam | No dam forecast | No | Not public | https://aquaoso.com/ |
| Descartes Underwriting | Drought insurance that pays out on a satellite rainfall-shortfall index; its case study is an Australian cane grower | No | No | No | Insurance premium (not public) | https://descartesunderwriting.com/case-studies/water-scarcity-insurance-a-parametric-solution-for-agribusinesses-and-the-agricultural-sector |

### Banks and big platforms (outside the farmer pitch)

| name | what it does | per dam? | forecasts days ahead? | needs sensors or site visits? | cost | source URL |
|---|---|---|---|---|---|---|
| Digital Agriculture Services (Australia) | Property and portfolio analytics, valuations and climate data for banks, insurers and agribusiness | Per property | No dam layer found on its home page | No | Not public | https://www.digitalagricultureservices.com/ |
| National Digital Twin for Australian Agriculture (ASII; $15 million; Elders, MLA, Charles Sturt University) | A planned shared model of farm landscapes from satellites, sensors and climate models, including water availability trends and water scenarios, delivered through service partners | Not described | No per-dam forecast described; not yet running (pilots planned) | Not described | Through partners | https://arr.news/2026/04/02/the-national-digital-twin-for-australian-agriculture/ |

### For comparison: DamDays

| name | what it does | per dam? | forecasts days ahead? | needs sensors or site visits? | cost | source URL |
|---|---|---|---|---|---|---|
| DamDays | One text a week per farm: for each dam the satellites can see, how full it is ("~67% full") and at least how many days before it drops below a third. The app adds the chance of that within 90 days ("3 in 10") and a runway out to 6 months | Yes, each waterbody of about 0.5 to 5 ha that looks and behaves like a farm dam (so far in NSW Central West and western Victoria / SE South Australia) | Yes: the days-left number, the 90-day chance and the runway curve to 180 days | No: built from the satellite water record (DEA Waterbodies) and rainfall (SILO) | No price set; free public data; no hardware | [README](../README.md), [test results](../artifacts/test_results.md) |

## Where DamDays is different

- **Days of water for each farm dam big enough for the satellites to see (about 0.5 to 5 ha), with nothing to install or measure.** Sensors report the level now, one water point at a time, for hundreds of dollars a device plus fees, and none we checked advertised a forecast. The tools that do say how long water will last (Agriculture Victoria's Summer Water Calculator, the Small Farm Dams tool) need the farmer to measure each dam's depth. NSW's monthly maps show the present, by parish. DamDays forecasts each dam from its own 38 years of satellite history and the rainfall, and is refit on the newest satellite looks.
- **Its accuracy is tested in public, against pass marks written before the code.** On ten years the frozen model never trained on (July 2016 to June 2026), 142,938 forecasts were scored once. They had nearly a quarter less error than guessing the usual rate for the region and month. They put a dam that fell below a third ahead of one that did not 8 times in 10. The cautious "at least N days" promise held 900 times in 1,000 (of 729,749), as designed. A sealed region is opened once, on camera, today. Of the forecasting tools we found:
  - the NSW drought forecast publishes past skill for a drought index, not for dams;
  - FEWS NET's model was checked against gauges at 8 waterholes when it was built ([Senay and others, 2013](https://earlywarning.usgs.gov/docs/Senay-et-al-Pastoralism-Research-Policy-and-Practice-2013.pdf)), and [a 2025 study in Senegal](https://www.frontiersin.org/journals/water/articles/10.3389/frwa.2025.1320010/full) found it kept water in ponds after they had dried; we found no published skill for its 30-day forecast;
  - the Small Farm Dams tool calls its own results "indicative".

  We found no farm dam forecast that publishes a test like DamDays's.
- **Dam by dam, sent as one weekly text.** Each dam gets a correction from its own record ("runs wetter than similar dams"), and the farm gets one SMS a week that names the dams that matter. Text alerts are not new (sensor companies send them, and so does Ethiopia's rangeland system). What is new is the content: for each dam, at least how many days of water are left, with a stated safety margin.

**What is not new, to be honest about it.**
- **Forecasting when stock water will run out is not our invention.** FEWS NET does it for African waterholes (30 days), the Small Farm Dams tool for Victorian dams (12 months, with a measured depth), and Agriculture Victoria's calculator by hand. Any "first ever" claim would be wrong.
- **The satellite record is public.** NSW DPIRD already uses it every month for about 47,000 dams, and runs its own seasonal drought forecast, so it could build a dam forecast too.
- **Sensor companies could add a "days to empty" trend line** for the dams they already instrument.

## What DamDays does not do

- **No small dams.** It sees only dams of about 0.5 ha or more: the satellite needs a dam outline of at least 6 pixels (about 5,400 m²). The average Australian farm dam, about 0.27 ha, is too small, so most farm dams are not covered ([TARGET_FARMER.md](TARGET_FARMER.md)).
- **No bores, tanks, troughs or rivers.** It sees surface water in dams only.
- **Australian data so far.** It was built and tested in NSW Central West and western Victoria / south-east South Australia. The sealed region (Southern Downs, Granite Belt, New England) is its test in a new place. Other climates, such as the tropical north and Western Australia, are untested, and no other country has been tried.
- **No depth or volume.** The satellite sees how much of a dam is wet, not how deep it is. "A third" means a third of the dam's usual full wet area. A forecast starts from the last clear satellite look, which can be weeks old.
- **Better at "which dams" than "which year".** It ranks which dams will fall below a third this summer well. It is weak at saying whether a single dam will run dry this year or next.
- **Not yet a running service.** Texts are only sent if someone runs the sender with their own SMS account; the MAP and STOP replies are not built; the refit on new satellite looks is run by hand.
- **Not advice.** It is meant to be used alongside the farmer's own eyes on the dam.

## A global note

- **The need is global, and the idea has prior art.** USGS FEWS NET's Water Point Viewer already forecasts waterholes in Africa: a free, satellite-driven water balance for each livestock water point, with a 30-day status forecast (299 water points in 16 countries in Africa plus Yemen on 3 Oct 2026, our count). It shows that herders and farmers far from Australia face the same question: how long will the water last? It also means DamDays did not invent the concept.
- **DamDays's angle** is narrower and measured: calibrated chances and a dam-by-dam runway for farm dams, tested on years the model never trained on and a region it never saw, and delivered weekly by text.
- **Future path: other countries (not built).** Satellite water archives like the one DamDays uses exist beyond Australia: Digital Earth Africa Waterbodies (over 700,000 waterbodies since 1984), JRC Global Surface Water (the whole world, monthly, since 1984), and Landsat itself covers the globe. In principle the same recipe could run on them. **None of this is built.** DamDays has only ever run on Australian data (DEA Waterbodies and SILO rainfall). Each new country would need its own waterbody record, rainfall record, test on its own years and dams, and a way to reach its farmers. Where FEWS NET already serves herders, working with it would make more sense than competing.

## How this was checked

- **Searches (3 Oct 2026):**
  - "dam management and forecasting system"
  - "farm dam water level app Australia"
  - farm dam water forecasts for farmers
  - stock water monitoring
  - farm dam satellite monitoring
  - the NSW State Seasonal Update farm dam pages
  - DEA Waterbodies
  - Agriculture Victoria's calculators
  - the FEWS NET Water Point Viewer
  - sensor prices (Farmbot, Farmo)
  - pasture forecasts
  - Digital Earth Africa Waterbodies
  - farm dam forecasting research
  - waterhole forecasting for pastoralists
- **Each product's own page was opened** for the "what it does", "forecast" and "cost" columns. Agriculture Victoria, NSW DPIRD and Bureau of Meteorology pages refuse automatic fetching, so they were read in a browser. The FEWS NET water point count is our own count of the viewer's table on 3 Oct 2026.
- **The pre-event competitor list was re-checked.** Every entry was opened again today. One change matters: the Small Farm Dams project, listed then as a runoff tool, now has a public pilot that gives 12-month water balance forecasts for a dam the farmer draws.
- **Not checked:**
  - Agbot's own website (it refused to connect);
  - Pasture.io's and FORAGE's prices;
  - the full results of the Small Farm Dams tool (we did not enter a dam);
  - private or unannounced startups.
