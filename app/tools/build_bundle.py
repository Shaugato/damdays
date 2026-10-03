"""Pack one dataset folder's JSON files into the scripts the app loads.

Why this exists: when you double-click index.html, the browser opens it from
disk (a file:// address) and blocks JavaScript from reading other local files
with fetch(). It does allow <script src="...">. So we wrap the JSON files in
small scripts that set a global variable. The JSON files stay the
"source of truth" described in app/DATA_CONTRACT.md; everything written here
is a copy.

What it writes, in the dataset folder (e.g. app/data/real/):

  bundle.js       every JSON file in one script (as before: the fallback, the
                  tests, ?data=mock and anyone reading the data contract).
  parts.js and    the same data split by how soon the app needs it, so a phone
  <part>.<hash>.js  on a slow connection downloads a fraction of it first
                  (write_parts(); UI_SPEC 8.2):
                    first       meta, scoreboard, farms, proof, and the demo farms' dams
                                (their entries, today's rows and curves, track records):
                                the Welcome, My farm, the dam sheet's first level, Proof,
                                Questions and About need nothing else
                    farms       the demo farms' dams' water history since 1988
                    core        every other dam: entries, today's rows and curves, track
                                records, and which history-NN part holds its history
                    rewind      the past forecast dates and their curves
                    rating      the 2 km cells (the Area outlook)
                    history-NN  the other dams' water history, in 12 map-area shards
                  Each file name carries a hash of its content, so a browser or the
                  service worker can keep it for good; the previous ones are deleted.

and next to the dataset folders:

  data/datasets.js  the datasets the app can use, "real" first, and which of them
                    are split into parts.

and, if the app folder has a service worker (app/sw.js):

  sw-version.js   the app shell's file list and one fingerprint over all of it
                  (stamp_shell()). A changed file gives a new fingerprint, so
                  installed copies offer "Refresh". Run it after ANY change to the
                  app's own files (HTML, CSS, JS, icons) too:
                      python app/tools/build_bundle.py --stamp
                  and check before a push with
                      python app/tools/build_bundle.py --check-stamp

If the folder also has farms.json (the demo farms and their weekly texts, written
by scripts/16_weekly_texts.py), it is packed too, for the app's "My farm" view.
It is optional: a dataset without it still works, and My farm then starts empty.
The same goes for proof.json (the Proof view's charts, written by
scripts/17_proof_data.py) and track_record.json (each dam's record over the last
10 years, written by scripts/18_track_record.py).

Usage (from the repo root):
    python app/tools/build_bundle.py app/data/mock
    python app/tools/build_bundle.py app/data/real
    python app/tools/build_bundle.py --stamp          (only sw-version.js)
    python app/tools/build_bundle.py --check-stamp    (exit 1 if sw-version.js is out of date)
"""
import gzip
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

# The six files every dataset folder must contain (see DATA_CONTRACT.md).
PARTS = ["meta", "forecasts", "curves", "history", "cells", "scoreboard"]

# Files packed only if the folder has them.
OPTIONAL_PARTS = ["farms", "proof", "track_record"]

# The top-level keys each file must have. A light check that catches a
# half-written export before it reaches the app.
REQUIRED_KEYS = {
    "meta": ["schema_version", "is_mock", "region", "horizon_days"],
    "forecasts": ["dams", "issues"],
    "curves": ["horizons_days", "issues"],
    "history": ["first_month", "last_month", "by_dam"],
    "cells": ["cells", "seasons"],
    "scoreboard": ["source", "rating"],
    "farms": ["date", "farms"],
    "proof": ["schema_version", "test", "unseen_exam", "calibration", "by_year", "dam_by_dam"],
    "track_record": ["schema_version", "label", "min_judged", "tip", "dams", "farms"],
}

# Datasets the app knows about, in order of preference.
PREFERENCE = ["real", "mock"]

# ---- Data parts (write_parts) ----------------------------------------------------------
N_SHARDS = 12                              # the other dams' history, by map area
PRECACHE = ["first", "farms", "rewind"]    # what the service worker saves on install (rewind: Proof's Rewind works offline)
LOAD_ALL = ["first", "farms", "core", "rewind", "rating"]   # what DamDays.data.load() merges
# Every file write_parts() may have written before (deleted when a new export replaces it).
PART_FILE = re.compile(r"^(first|farms|core|rewind|rating|history-\d{2})\.[0-9a-f]{10}\.js$")

# ---- App shell (stamp_shell) -------------------------------------------------------------
APP_DIR = Path(__file__).resolve().parent.parent
SMALL_ICONS = ["icons/icon.svg", "icons/favicon-32.png"]   # the big ones the browser fetches itself


def compact(obj):
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def short_hash(data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()[:10]


def gzip_size(data):
    """Bytes a web server sends for this text (gzip level 6, as GitHub Pages compresses)."""
    return len(gzip.compress(data, compresslevel=6, mtime=0))


def read_part(folder, name):
    """Read one JSON file from the dataset folder and check its top-level keys."""
    path = folder / f"{name}.json"
    if not path.exists():
        raise SystemExit(f"Missing {path}. Every dataset needs {', '.join(PARTS)}.")
    with open(path, encoding="utf-8") as f:
        content = json.load(f)
    missing = [key for key in REQUIRED_KEYS[name] if key not in content]
    if missing:
        raise SystemExit(f"{path} is missing the key(s): {', '.join(missing)}")
    return content


def read_bundle(folder):
    """The six JSON files (and farms.json, proof.json and track_record.json, if there), as one dict."""
    bundle = {name: read_part(folder, name) for name in PARTS}
    for name in OPTIONAL_PARTS:
        if (folder / f"{name}.json").exists():
            bundle[name] = read_part(folder, name)
            print(f"Packed the optional {name}.json too")
    return bundle


def write_bundle(folder, bundle=None):
    """Combine the JSON files into folder/bundle.js. Returns the bundle (a dict)."""
    if bundle is None:
        bundle = read_bundle(folder)
    # Compact separators keep the file small; the JSON files stay readable.
    text = compact(bundle)
    header = (
        "// Generated by app/tools/build_bundle.py from the JSON files in this folder.\n"
        "// Do not edit by hand: edit or re-export the JSON, then rebuild.\n"
    )
    out_path = folder / "bundle.js"
    out_path.write_text(header + "window.DAMDAYS_BUNDLE = " + text + ";\n", encoding="utf-8")
    size_kb = out_path.stat().st_size / 1024
    print(f"Wrote {out_path} ({size_kb:.0f} KB)")
    return bundle


# =========================================================================================
# write_parts(): the same data, split by how soon the app needs it (UI_SPEC 8.2)
# =========================================================================================
def morton(lat, lon, bbox):
    """Interleave 16-bit lat/lon, so dams close on the map get close keys (map-area shards)."""
    lat_min, lat_max, lon_min, lon_max = bbox
    y = int((lat - lat_min) / (lat_max - lat_min + 1e-9) * 65535)
    x = int((lon - lon_min) / (lon_max - lon_min + 1e-9) * 65535)
    y, x = max(0, min(65535, y)), max(0, min(65535, x))
    key = 0
    for i in range(16):
        key |= ((x >> i) & 1) << (2 * i) | ((y >> i) & 1) << (2 * i + 1)
    return key


def demo_dam_ids(bundle):
    """Every dam of the demo farms (farms.json), in order, once each."""
    ids = []
    for farm in (bundle.get("farms") or {}).get("farms") or []:
        for dam in farm.get("dams") or []:
            if dam.get("dam_id"):
                ids.append(dam["dam_id"])
    return list(dict.fromkeys(ids))


def region_bbox(bundle, dams):
    """meta.region.bbox [lat_min, lat_max, lon_min, lon_max], or the dams' own extent."""
    bbox = ((bundle.get("meta") or {}).get("region") or {}).get("bbox")
    if bbox and len(bbox) == 4:
        return bbox
    lats = [d["lat"] for d in dams if d.get("lat") is not None]
    lons = [d["lon"] for d in dams if d.get("lon") is not None]
    if not lats or not lons:
        return [0.0, 1.0, 0.0, 1.0]
    return [min(lats), max(lats), min(lons), max(lons)]


def without(obj, *keys):
    return {k: v for k, v in (obj or {}).items() if k not in keys}


def split_parts(bundle):
    """The parts, as {name: content}. Works on any folder build_bundle accepts (missing pieces are skipped)."""
    fc = bundle.get("forecasts") or {}
    cv = bundle.get("curves") or {}
    hist = bundle.get("history") or {}
    cells = bundle.get("cells") or {}
    track = bundle.get("track_record")
    by_dam = hist.get("by_dam") or {}
    all_dams = fc.get("dams") or []
    issues = fc.get("issues") or []
    live = [i for i in issues if i.get("kind") == "live"]
    past = [i for i in issues if i.get("kind") != "live"]
    live_dates = {i.get("issue_date") for i in live}
    curve_issues = cv.get("issues") or []

    demo_ids = demo_dam_ids(bundle)
    demo = set(demo_ids)
    in_farms = [d for d in demo_ids if d in by_dam]          # their history goes in "farms"

    # ---- first: what the first screens draw from ----------------------------------------
    first_forecasts = without(fc, "dams", "issues")
    first_forecasts["dams"] = [d for d in all_dams if d.get("dam_id") in demo]
    first_forecasts["issues"] = [
        dict(without(i, "rows"), rows=[r for r in i.get("rows") or [] if r.get("dam_id") in demo]) for i in live]
    first_curves = without(cv, "issues")
    first_curves["issues"] = [
        dict(without(c, "by_dam"), by_dam={k: v for k, v in (c.get("by_dam") or {}).items() if k in demo})
        for c in curve_issues if c.get("issue_date") in live_dates]
    first_track = None
    if track:
        first_track = without(track, "dams")
        first_track["dams"] = {k: v for k, v in (track.get("dams") or {}).items() if k in demo}
    first = {
        "meta": bundle.get("meta"),
        "scoreboard": bundle.get("scoreboard"),
        "farms": bundle.get("farms"),
        "proof": bundle.get("proof"),
        "track_record": first_track,
        "forecasts": first_forecasts,
        "curves": first_curves,
        "history": dict(without(hist, "by_dam"), by_dam={}),
        "cells": dict(without(cells, "cells", "seasons"), cells=[], seasons=[]),
        "history_in_farms": in_farms,
    }

    # ---- history shards: the other dams, by map area -------------------------------------
    dams_by_id = {d.get("dam_id"): d for d in all_dams}
    bbox = region_bbox(bundle, all_dams)

    def area_key(dam_id):
        d = dams_by_id.get(dam_id)
        if not d or d.get("lat") is None or d.get("lon") is None:
            return (1, 0, dam_id)
        return (0, morton(d["lat"], d["lon"], bbox), dam_id)

    rest = sorted((k for k in by_dam if k not in demo), key=area_key)
    shards = {}
    size = -(-len(rest) // N_SHARDS) if rest else 0
    for i in range(N_SHARDS):
        chunk = rest[i * size:(i + 1) * size]
        if chunk:
            shards[f"history-{i:02d}"] = chunk

    # ---- core: every other dam ------------------------------------------------------------
    core = {
        "forecasts_dams": [d for d in all_dams if d.get("dam_id") not in demo],
        "live_rows": {i.get("issue_date"): [r for r in i.get("rows") or [] if r.get("dam_id") not in demo]
                      for i in live},
        "live_curves": {c.get("issue_date"): {k: v for k, v in (c.get("by_dam") or {}).items() if k not in demo}
                        for c in curve_issues if c.get("issue_date") in live_dates},
        "track_record_dams": {k: v for k, v in ((track or {}).get("dams") or {}).items() if k not in demo},
        "history_index": {dam_id: name for name, ids in shards.items() for dam_id in ids},
    }

    parts = {
        "first": first,
        "farms": {"history": {k: by_dam[k] for k in in_farms}},
        "core": core,
        "rewind": {"issues": past,
                   "curves": [c for c in curve_issues if c.get("issue_date") not in live_dates]},
        "rating": {"cells": cells.get("cells") or [], "seasons": cells.get("seasons") or []},
    }
    for name, ids in shards.items():
        parts[name] = {"history": {k: by_dam[k] for k in ids}}
    return parts


def write_parts(folder, bundle=None):
    """Write folder/<part>.<hash>.js for every part and folder/parts.js (their list); delete the old ones.

    Each part is a plain script that adds itself to self.DAMDAYS_PART_DATA["<dataset>/<part>"], so a
    double-clicked index.html still works (no fetch()). Returns the listing written to parts.js.
    """
    if bundle is None:
        bundle = read_bundle(folder)
    dataset = folder.name
    files, raw, packed = {}, {}, {}
    for name, content in split_parts(bundle).items():
        body = ("(self.DAMDAYS_PART_DATA = self.DAMDAYS_PART_DATA || {})[" + json.dumps(dataset + "/" + name)
                + "] = " + compact(content) + ";\n")
        data = body.encode("utf-8")
        fname = f"{name}.{short_hash(data)}.js"
        out = folder / fname
        header = (f"// Generated by app/tools/build_bundle.py: the \"{name}\" part of data/{dataset} "
                  "(app/DATA_CONTRACT.md, \"Data parts\"). Do not edit.\n")
        if not out.exists() or out.read_bytes() != header.encode("utf-8") + data:
            out.write_bytes(header.encode("utf-8") + data)
        files[name] = fname
        raw[name] = len(data)
        packed[name] = gzip_size(data)
    # The previous export's parts (their names no longer listed)
    keep = set(files.values())
    removed = [p.name for p in folder.iterdir() if PART_FILE.match(p.name) and p.name not in keep]
    for name in removed:
        (folder / name).unlink()

    listing = {
        "dataset": dataset,
        "files": files,
        "bytes": raw,
        "gzip": packed,
        "precache": [p for p in PRECACHE if p in files],
        "load": [p for p in LOAD_ALL if p in files],
    }
    listing["version"] = short_hash(compact(listing))
    text = (
        "// Generated by app/tools/build_bundle.py: the data parts of data/" + dataset + " and their\n"
        "// content-hashed files (app/DATA_CONTRACT.md, \"Data parts\"). Do not edit by hand.\n"
        "// The page and the service worker (sw.js, importScripts) both read it.\n"
        "(self.DAMDAYS_PART_LISTS = self.DAMDAYS_PART_LISTS || {})[" + json.dumps(dataset) + "] = "
        + json.dumps(listing, indent=1) + ";\n"
        "// In a page (not the service worker): start the \"first\" part now, before the other scripts run,\n"
        "// unless the address asks for another dataset (?data=mock). js/data.js picks it up.\n"
        "(function (name) {\n"
        "  if (typeof document === \"undefined\") return;\n"
        "  var list = self.DAMDAYS_PART_LISTS[name], asked = /[?&]data=([^&#]*)/.exec(location.search);\n"
        "  if (!list.files.first || (asked && decodeURIComponent(asked[1]) !== name)) return;\n"
        "  var loads = self.DAMDAYS_PART_LOADS = self.DAMDAYS_PART_LOADS || {}, key = name + \"/first\";\n"
        "  if (loads[key] || (self.DAMDAYS_PART_DATA && self.DAMDAYS_PART_DATA[key])) return;\n"
        "  loads[key] = new Promise(function (resolve, reject) {\n"
        "    var s = document.createElement(\"script\");\n"
        "    s.src = \"data/\" + name + \"/\" + list.files.first;\n"
        "    s.onload = resolve;\n"
        "    s.onerror = function () { delete loads[key]; s.remove(); reject(new Error(\"Could not load \" + s.src)); };\n"
        "    document.head.appendChild(s);\n"
        "  });\n"
        "  loads[key].catch(function () {});\n"
        "})(" + json.dumps(dataset) + ");\n"
    )
    (folder / "parts.js").write_text(text, encoding="utf-8")
    print(f"Wrote {folder / 'parts.js'}: {len(files)} parts"
          + (f" (deleted {len(removed)} old)" if removed else ""))
    for name in files:
        print(f"  {files[name]:30s} {raw[name] / 1024:8.1f} KB, {packed[name] / 1024:6.1f} KB gzipped")
    return listing


def write_dataset_list(data_dir):
    """List every dataset folder that has a bundle.js, preferred first, in datasets.js (and which are split)."""
    found = [name for name in PREFERENCE if (data_dir / name / "bundle.js").exists()]
    split = [name for name in found if (data_dir / name / "parts.js").exists()]
    out_path = data_dir / "datasets.js"
    out_path.write_text(
        "// Generated by app/tools/build_bundle.py. The app loads the first dataset listed.\n"
        "window.DAMDAYS_DATASETS = " + json.dumps(found) + ";\n"
        "// Datasets split into parts (data/<name>/parts.js); the others load their bundle.js.\n"
        "window.DAMDAYS_SPLIT = " + json.dumps(split) + ";\n",
        encoding="utf-8",
    )
    print(f"Wrote {out_path}: {found} (split: {split})")


# =========================================================================================
# stamp_shell(): sw-version.js, the app shell's files and one fingerprint (UI_SPEC 9.4)
# =========================================================================================
def _published(rel):
    """GitHub Pages runs Jekyll, which leaves out any file or folder starting with _ or ."""
    return not any(part.startswith(("_", ".")) for part in Path(rel).parts)


def shell_files(app):
    """The files the service worker saves as one version: the page, CSS, JS, fonts, small icons, data lists."""
    names = ["./", "index.html"]
    if (app / "manifest.webmanifest").exists():
        names.append("manifest.webmanifest")
    if (app / "data" / "datasets.js").exists():
        names.append("data/datasets.js")
    names += [f"data/{ds}/parts.js" for ds in PREFERENCE if (app / "data" / ds / "parts.js").exists()]
    for folder, pattern in (("css", "*.css"), ("js", "*.js"), ("fonts", "*.woff2"), ("fonts", "*.css")):
        if (app / folder).is_dir():
            found = sorted(p.relative_to(app).as_posix() for p in (app / folder).rglob(pattern))
            names += [n for n in found if _published(n)]
    names += [n for n in SMALL_ICONS if (app / n).exists()]
    return names


def shell_stamp(app):
    """(version, files, part lists) for this app folder, or None when it has no service worker."""
    sw = app / "sw.js"
    if not sw.exists() or not (app / "index.html").exists():
        return None
    names = shell_files(app)
    h = hashlib.sha256()
    for n in names[1:]:                      # "./" is index.html
        h.update(n.encode("utf-8") + b"\0")
        h.update((app / n).read_bytes())
    h.update(b"sw.js\0" + sw.read_bytes())
    parts = [n for n in names if n.endswith("/parts.js")]
    return h.hexdigest()[:10], names, parts


def stamp_text(version, names, parts):
    return (
        "// Generated by app/tools/build_bundle.py (stamp_shell): the app shell the service worker saves as one\n"
        "// version, and its fingerprint. A new version here makes installed copies offer \"Refresh\".\n"
        "// After ANY change to the app's files run: python app/tools/build_bundle.py --stamp\n"
        "self.DAMDAYS_SHELL = " + json.dumps({"version": version, "files": names, "parts": parts}, indent=1) + ";\n"
    )


def untracked(app, names):
    """Shell files git does not track yet (they would be missing on GitHub Pages until committed)."""
    try:
        out = subprocess.run(["git", "ls-files", "--others", "--exclude-standard", "--", "."], cwd=app,
                             capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return []
    if out.returncode != 0:
        return []
    loose = {line.strip() for line in out.stdout.splitlines() if line.strip()}
    return [n for n in names if n in loose]


def warn_untracked(app, names):
    # the data parts too: the worker saves "first" and "farms" on install
    for ds in PREFERENCE:
        folder = app / "data" / ds
        if folder.is_dir():
            names = names + sorted(f"data/{ds}/{p.name}" for p in folder.iterdir() if PART_FILE.match(p.name))
    loose = untracked(app, names)
    if loose:
        print("NOTE: not committed yet (commit them with this push, or the offline copy cannot save them): "
              + ", ".join(loose))


def stamp_shell(app=APP_DIR):
    """Write app/sw-version.js. Skipped (returns None) for a folder without sw.js, e.g. a test's temporary app."""
    stamp = shell_stamp(app)
    if stamp is None:
        return None
    version, names, parts = stamp
    out = app / "sw-version.js"
    text = stamp_text(version, names, parts)
    if not out.exists() or out.read_text(encoding="utf-8") != text:
        out.write_text(text, encoding="utf-8")
    print(f"Wrote {out}: shell version {version}, {len(names)} files")
    warn_untracked(app, names)
    return version


def check_stamp(app=APP_DIR):
    """0 if sw-version.js matches the app's files now, 1 if it needs `--stamp`."""
    stamp = shell_stamp(app)
    if stamp is None:
        print(f"No service worker in {app}: nothing to check.")
        return 0
    out = app / "sw-version.js"
    current = out.read_text(encoding="utf-8") if out.exists() else ""
    warn_untracked(app, stamp[1] + ["sw.js", "sw-version.js"])
    if current == stamp_text(*stamp):
        print(f"sw-version.js is up to date (shell version {stamp[0]}).")
        return 0
    print("sw-version.js is OUT OF DATE: run  python app/tools/build_bundle.py --stamp  before pushing.")
    return 1


def main():
    args = sys.argv[1:]
    if args == ["--stamp"]:
        if stamp_shell() is None:
            raise SystemExit(f"No sw.js in {APP_DIR}: nothing to stamp.")
        return
    if args == ["--check-stamp"]:
        raise SystemExit(check_stamp())
    if len(args) != 1 or args[0].startswith("--"):
        raise SystemExit("Usage: python app/tools/build_bundle.py <dataset folder> | --stamp | --check-stamp")
    folder = Path(args[0]).resolve()
    bundle = write_bundle(folder)
    write_parts(folder, bundle)
    write_dataset_list(folder.parent)
    # The app folder this dataset belongs to (app/data/<name>): stamp its shell, if it has a service worker.
    stamp_shell(folder.parent.parent)


if __name__ == "__main__":
    main()
