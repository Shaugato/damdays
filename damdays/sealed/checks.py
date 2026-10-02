"""The checks that run before a single sealed file is parsed.

PREREG "Sealed region protocol": the sealed region "is opened once, Sat 3 Oct 17:30 AEST, after
the freeze addendum is committed and pushed. Every file hash is checked against
SEALED_HASHES.csv first." The runner refuses to go on unless ALL of these hold:

1. The unlock switch. The environment variable DAMDAYS_OPEN_SEALED is "yes" (damdays.data.guard
   refuses every sealed path, and the sealed SILO key, without it).
2. git, read only. The working tree is clean (only the runner's own output files may differ:
   artifacts/sealed/ and the TEST ledger, so a run resumed after a crash fix can start), and HEAD
   is on the remote, i.e. pushed (checked live with `git ls-remote`; offline, against the local
   copy of the remote branch, which a push from this clone updates).
3. The hash list is the one committed at the start of the event: SEALED_HASHES.csv is read from
   git (not from the sealed folder), it was added in one commit and never changed since, the
   working copy equals it, and it lists exactly 4,711 files (PREREG "Data").
4. Every sealed file matches. The sealed time-series folder holds exactly the 4,711 listed files
   (none missing, none extra), and every file's SHA-256 and size equal the committed values: a
   100% match. One mismatch stops the run.

Every git command here only reads (status, rev-parse, ls-remote, log, diff, show, merge-base);
`git` refuses anything else.

The dry run (a rehearsal on a development region) runs the same functions, with two differences:
the unlock switch must be OFF (proof that nothing sealed is touched), and the git checks are
printed but do not stop it (the build is still being edited). Its file check verifies the
development region's own files against a dry-run hash list made on its first run.
"""
import hashlib
import io
import os
import re
import subprocess
import time
from pathlib import Path

import pandas as pd

from damdays import config
from damdays.data import guard

EXPECTED_SEALED_FILES = 4_711                    # PREREG "Data": the sealed region holds 4,711 eligible waterbodies
HASH_LIST_NAME = "SEALED_HASHES.csv"             # committed at the start of the event, in the repo root
HASH_LIST_COLUMNS = ["file", "sha256", "bytes"]
FILE_NAME = re.compile(r"^r[0-9a-z]+_v3\.csv$")  # a DEA Waterbodies v3 time-series file, e.g. r67hfpx0v_v3.csv
SHA256_TEXT = re.compile(r"^[0-9a-f]{64}$")
READ_ONLY_GIT = ("status", "rev-parse", "ls-remote", "log", "diff", "show", "merge-base")


class CheckFailed(RuntimeError):
    """A pre-opening check failed: the runner stops before the sealed data is parsed."""


# ===========================================================================
# git (read only)
# ===========================================================================
GIT_TIMEOUT_SECONDS = 60                         # a slow network must not hang the opening (ls-remote)


def git(*args, allow_fail=False):
    """Run one READ-ONLY git command in the repo; returns (exit code, output text).

    Raises CheckFailed on a non-zero exit code (or no answer within GIT_TIMEOUT_SECONDS) unless
    allow_fail is True; then a failure returns a non-zero code. git never asks for a password here.
    """
    if args[0] not in READ_ONLY_GIT:
        raise ValueError(f"git {args[0]} is not one of the read-only commands {READ_ONLY_GIT}.")
    try:
        done = subprocess.run(["git", *args], cwd=config.REPO_DIR, capture_output=True, text=True,
                              timeout=GIT_TIMEOUT_SECONDS, env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
        code, out, err = done.returncode, done.stdout, done.stderr
    except subprocess.TimeoutExpired:
        code, out, err = 124, "", f"no answer within {GIT_TIMEOUT_SECONDS} s"
    if code != 0 and not allow_fail:
        raise CheckFailed(f"`git {' '.join(args)}` failed: {err.strip() or out.strip()}")
    return code, out.rstrip()      # rstrip only: `git status` lines start with a space


def changed_paths():
    """Every path git reports as modified, added, deleted or untracked (git-ignored files excluded)."""
    _, out = git("status", "--porcelain=v1", "--untracked-files=all")
    paths = []
    for line in out.splitlines():
        path = line[3:].split(" -> ")[-1].strip().strip('"')
        paths.append(path)
    return paths


def runner_outputs(run):
    """Repo-relative paths the runner itself writes (allowed to be uncommitted on a resumed run)."""
    def relative(path):
        return Path(path).resolve().relative_to(config.REPO_DIR).as_posix()
    return (relative(run.results_dir) + "/", relative(run.ledger_path))


def git_status(run):
    """{clean, changed (paths that are not the runner's own outputs), ignored_outputs}."""
    allowed = runner_outputs(run)
    changed = changed_paths()
    other = [p for p in changed if not any(p == a or p.startswith(a) for a in allowed)]
    return dict(clean=not other, changed=other, runner_outputs_changed=[p for p in changed if p not in other])


def head_is_pushed():
    """{pushed, head, remote_sha, how}: is the commit being run on the remote branch?

    Read only: `git ls-remote` asks the remote (GitHub) for its branch tip without changing
    anything here. Offline, the local copy of the remote branch (updated by the last push from
    this clone) is used instead, and the result says so.
    """
    _, head = git("rev-parse", "HEAD")
    code, upstream = git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", allow_fail=True)
    if code != 0 or "/" not in upstream:
        return dict(pushed=False, head=head, remote_sha=None, how="this branch has no upstream branch")
    remote, branch = upstream.split("/", 1)
    code, out = git("ls-remote", remote, f"refs/heads/{branch}", allow_fail=True)
    if code == 0 and out:
        remote_sha, how = out.split()[0], f"live: git ls-remote {remote} {branch}"
    else:
        _, remote_sha = git("rev-parse", upstream)
        how = f"OFFLINE: the local copy of {upstream} (updated by the last push from this clone)"
    if remote_sha == head:
        return dict(pushed=True, head=head, remote_sha=remote_sha, how=how)
    contained, _ = git("merge-base", "--is-ancestor", head, remote_sha, allow_fail=True)
    return dict(pushed=contained == 0, head=head, remote_sha=remote_sha,
                how=how + ("" if contained == 0 else "; HEAD is NOT on the remote branch"))


# ===========================================================================
# The committed hash list
# ===========================================================================
def parse_hash_list(text):
    """The hash list as a table (file, sha256, bytes), after checking its format. Raises CheckFailed."""
    table = pd.read_csv(io.StringIO(text), dtype={"file": str, "sha256": str, "bytes": "int64"})
    if list(table.columns) != HASH_LIST_COLUMNS:
        raise CheckFailed(f"{HASH_LIST_NAME} has columns {list(table.columns)}, expected {HASH_LIST_COLUMNS}.")
    bad_names = ~table["file"].str.match(FILE_NAME)
    bad_hashes = ~table["sha256"].str.match(SHA256_TEXT)
    if bad_names.any() or bad_hashes.any() or table["file"].duplicated().any() or (table["bytes"] <= 0).any():
        raise CheckFailed(f"{HASH_LIST_NAME} is malformed: {int(bad_names.sum())} bad file names, "
                          f"{int(bad_hashes.sum())} bad hashes, {int(table['file'].duplicated().sum())} duplicates.")
    return table


def committed_hash_list(expected_files=EXPECTED_SEALED_FILES):
    """The sealed files' committed SHA-256 list, read from git, with its provenance checked.

    Returns (table, provenance). Raises CheckFailed unless:
      * SEALED_HASHES.csv was added in ONE commit and never changed since;
      * the working copy is that committed file (no uncommitted edit);
      * it lists exactly `expected_files` files.
    The list is read from the commit itself (`git show`), never from the sealed folder.
    """
    _, log = git("log", "--format=%H|%ad|%s", "--date=iso", "--", HASH_LIST_NAME)
    commits = [line.split("|", 2) for line in log.splitlines() if line]
    if len(commits) != 1:
        raise CheckFailed(f"{HASH_LIST_NAME} must have been committed once and never changed; "
                          f"git log lists {len(commits)} commits touching it.")
    sha, date, subject = commits[0]
    edited, _ = git("diff", "--quiet", "HEAD", "--", HASH_LIST_NAME, allow_fail=True)
    if edited != 0:
        raise CheckFailed(f"The working copy of {HASH_LIST_NAME} differs from the committed one.")
    _, text = git("show", f"{sha}:{HASH_LIST_NAME}")
    table = parse_hash_list(text + "\n")
    if len(table) != expected_files:
        raise CheckFailed(f"{HASH_LIST_NAME} lists {len(table):,} files; PREREG says {expected_files:,}.")
    # Fingerprint of the list itself (line endings read as LF, so a Windows checkout gives the same value).
    list_bytes = (config.REPO_DIR / HASH_LIST_NAME).read_bytes().replace(b"\r\n", b"\n")
    provenance = dict(commit=sha, committed_at=date, subject=subject, files=int(len(table)),
                      total_bytes=int(table["bytes"].sum()), list_sha256=hashlib.sha256(list_bytes).hexdigest())
    return table, provenance


# ===========================================================================
# The files themselves
# ===========================================================================
def sha256_of_file(path, chunk=1 << 20):
    """SHA-256 (hex) of a file's bytes."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_files(hash_list, folder, only_listed_files=True, progress=None):
    """Recompute every listed file's SHA-256 in `folder` and compare with the list.

    only_listed_files  True: the folder must hold exactly the listed files (the sealed folder).
                       False: other files may sit beside them (a development folder holds two regions).
    Returns a report: n_listed, n_present, n_matched, missing, extra, mismatched (name: what differs),
    seconds and all_match. `folder` goes through damdays.data.guard first, so the sealed folder
    is refused unless the unlock switch is on.
    """
    started = time.time()
    folder = guard.check_path(folder)
    if not folder.is_dir():
        raise CheckFailed(f"Folder {folder} does not exist.")
    expected = dict(zip(hash_list["file"], zip(hash_list["sha256"], hash_list["bytes"])))
    if only_listed_files:
        on_disk = {entry.name for entry in os.scandir(folder) if entry.is_file()}
    else:
        on_disk = {name for name in expected if (folder / name).is_file()}
    missing = sorted(set(expected) - on_disk)
    extra = sorted(on_disk - set(expected))
    mismatched = {}
    for count, name in enumerate(sorted(set(expected) & on_disk), start=1):
        sha, size = expected[name]
        path = folder / name
        if path.stat().st_size != size:
            mismatched[name] = f"size {path.stat().st_size} bytes, committed {size}"
        elif sha256_of_file(path) != sha:
            mismatched[name] = "SHA-256 differs"
        if progress and count % 1000 == 0:
            progress(f"hashed {count:,} of {len(expected):,} files")
    n_present = len(set(expected) & on_disk)
    return dict(folder=str(folder), n_listed=len(expected), n_present=n_present,
                n_matched=n_present - len(mismatched), missing=missing, extra=extra, mismatched=mismatched,
                all_match=not missing and not extra and not mismatched, seconds=round(time.time() - started, 1))


def require_full_match(report, expected_files):
    """Raise CheckFailed unless the file report is a 100% match on exactly `expected_files` files."""
    problems = []
    if report["missing"]:
        problems.append(f"{len(report['missing'])} listed files are missing (e.g. {report['missing'][:3]})")
    if report["extra"]:
        problems.append(f"{len(report['extra'])} unlisted files are present (e.g. {report['extra'][:3]})")
    if report["mismatched"]:
        problems.append(f"{len(report['mismatched'])} files differ from their committed hash "
                        f"(e.g. {list(report['mismatched'].items())[:3]})")
    if report["n_matched"] != expected_files:
        problems.append(f"{report['n_matched']:,} files match, {expected_files:,} expected")
    if problems:
        raise CheckFailed("Sealed files do not match the committed hashes: " + "; ".join(problems) + ".")


# ===========================================================================
# The two pre-flight routines
# ===========================================================================
def opening_preflight(run, sealed_ts_dir, say):
    """Every check before the opening (1-4 in the module docstring). Raises CheckFailed on the first failure.

    Returns (what was checked: a dict for the results page, the verified file names). The build
    then reads only those files (region.require_manifest_matches_files).
    """
    say("check 1: the unlock switch")
    if not guard.sealed_unlocked():
        raise CheckFailed(f"The unlock switch is off: set {config.SEALED_UNLOCK_ENV}=yes for the opening.")
    say(f"  {config.SEALED_UNLOCK_ENV}=yes")

    say("check 2: git is clean and HEAD is pushed (read-only git)")
    status = git_status(run)
    if not status["clean"]:
        raise CheckFailed("Uncommitted changes (commit and push them first): " + ", ".join(status["changed"][:10]))
    pushed = head_is_pushed()
    if not pushed["pushed"]:
        raise CheckFailed(f"HEAD {pushed['head'][:12]} is not on the remote ({pushed['how']}). Push it first.")
    say(f"  clean; HEAD {pushed['head'][:12]} is on the remote ({pushed['how']})")

    say(f"check 3: the hash list committed at the start of the event ({HASH_LIST_NAME}, read from git)")
    hash_list, provenance = committed_hash_list()
    say(f"  {provenance['files']:,} files listed; committed once, in {provenance['commit'][:12]} "
        f"at {provenance['committed_at']}; unchanged since")

    say(f"check 4: SHA-256 of every sealed file in {sealed_ts_dir}")
    files = verify_files(hash_list, sealed_ts_dir, only_listed_files=True, progress=lambda m: say("  " + m))
    require_full_match(files, EXPECTED_SEALED_FILES)
    say(f"  100% match: {files['n_matched']:,} of {files['n_listed']:,} files, none missing, none extra "
        f"({files['seconds']} s)")
    return (dict(unlock_switch=True, git=dict(status, **pushed), hash_list=provenance, files=files),
            sorted(hash_list["file"]))


def rehearsal_preflight(run, region_files, rehearsal_list_path, say):
    """The dry run's version of the checks: the same functions, nothing sealed touched.

    region_files         (file names, folder) of the region the dry run treats as unseen
    rehearsal_list_path  its own hash list: made on the first dry run, verified on every later one
    Returns (what was checked, the verified file names), like opening_preflight.
    """
    say("check 1: the unlock switch must be OFF for a dry run (nothing sealed may be touched)")
    if guard.sealed_unlocked():
        raise CheckFailed(f"{config.SEALED_UNLOCK_ENV} is set: unset it for the dry run.")
    say("  off: every sealed path and the sealed SILO key are refused")

    say("check 2 (reported only, not enforced in a dry run): git clean and pushed")
    status = git_status(run)
    pushed = head_is_pushed()
    say(f"  clean: {status['clean']} ({len(status['changed'])} changed paths); pushed: {pushed['pushed']} "
        f"({pushed['how']})")

    say(f"check 3: the committed {HASH_LIST_NAME} (read from git, not from the sealed folder)")
    _, provenance = committed_hash_list()
    say(f"  {provenance['files']:,} files listed; committed once, in {provenance['commit'][:12]} "
        f"at {provenance['committed_at']}; unchanged since")

    names, folder = region_files
    say(f"check 4 (rehearsed on the {run.target_region} files): SHA-256 of every file")
    if not Path(rehearsal_list_path).exists():
        rows = [dict(file=name, sha256=sha256_of_file(Path(folder) / name), bytes=(Path(folder) / name).stat().st_size)
                for name in sorted(names)]
        Path(rehearsal_list_path).parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows, columns=HASH_LIST_COLUMNS).to_csv(rehearsal_list_path, index=False, lineterminator="\n")
        say(f"  first dry run: hash list of {len(rows):,} files written to {rehearsal_list_path}")
    hash_list = parse_hash_list(Path(rehearsal_list_path).read_text())
    files = verify_files(hash_list, folder, only_listed_files=False, progress=lambda m: say("  " + m))
    require_full_match(files, len(names))
    say(f"  100% match: {files['n_matched']:,} of {files['n_listed']:,} files ({files['seconds']} s)")
    return (dict(unlock_switch=False, git=dict(status, **pushed), hash_list=provenance, files=files,
                 note="rehearsal: git reported, not enforced; files verified against the dry run's own list"),
            sorted(hash_list["file"]))


# ===========================================================================
# The freeze addendum (PREREG: opened "after the freeze addendum is committed and pushed")
# ===========================================================================
def freeze_addendum_quotes(evaporation_sha256, config_hash=None, folder=None):
    """Which committed PREREG_ADDENDUM*.md quote the sealed evaporation hash (and the config hash).

    PREREG "Sealed region protocol": the sealed evaporation shape is "hashed in the addendum before
    opening". Raises CheckFailed unless an addendum quotes evaporation_sha256. (git is clean and
    pushed by check 2, so an addendum on disk is the committed one.) Returns {evaporation: [files],
    config_hash: [files] or None}; a config hash that no addendum quotes is reported, not refused,
    because a logged crash fix after the opening changes the code.
    """
    texts = {path.name: path.read_text(encoding="utf-8")
             for path in sorted(Path(folder or config.REPO_DIR).glob("PREREG_ADDENDUM*.md"))}
    quoting = [name for name, text in texts.items() if evaporation_sha256 in text]
    if not quoting:
        raise CheckFailed(f"No committed PREREG_ADDENDUM*.md quotes the sealed evaporation SHA-256 "
                          f"{evaporation_sha256}: the freeze addendum must be committed and pushed first.")
    return dict(evaporation=quoting, config_hash=None if config_hash is None else
                [name for name, text in texts.items() if config_hash[:12] in text])
