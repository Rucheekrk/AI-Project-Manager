"""Golden and checkpoint state of the projects (apps/utils/golden.py, apps/utils/checkpoints.py). Run inside the api container:

  python -m scripts.golden status                 each demo project: golden export present? does the live project match it?
  python -m scripts.golden restore forloop        put one project back to its latest checkpoint (the last valid state the app saved), or to its golden
                                                  state when it has none (restore all: every project that has either)
        --golden                                  go to the golden state instead (restore all --golden also clears AI Chat and the activity feed)
        --previous | --at 20261117-1015           an older checkpoint; --at before-restore undoes the last restore
        --yes                                     do not ask first (a restore shows what it would lose and waits for "yes")
  python -m scripts.golden checkpoints [forloop]  list the saved checkpoints
  python -m scripts.golden checkpoint forloop     save the project's state as a checkpoint now (--force: even if the checks fail)
  python -m scripts.golden verify all             compare live demo projects with their golden exports, change nothing
  python -m scripts.golden export forloop         save the live project as its new golden state (do this only when you mean to)
  python -m scripts.golden drop forloop           copy the project's ready-to-run demo file into the folder it belongs in

A restore does not undo Jira issues or calendar events a demo created. Before replacing anything it saves the current state as before-restore."""
import shutil
import sys
import time

from apps.utils import checkpoints, golden
from apps.utils import timesheet_watcher as tw


def ids() -> list:
    return sorted(p.name for p in golden.GOLDEN_DIR.iterdir() if (p / "golden.json").exists()) if golden.GOLDEN_DIR.is_dir() else []


def targets(arg: str) -> list:
    return ids() if arg == "all" else [arg]


def parse(argv: list):
    """-> (positional words, flags). --at takes the word after it."""
    at = argv[argv.index("--at") + 1] if "--at" in argv and argv.index("--at") + 1 < len(argv) else None
    words = [a for i, a in enumerate(argv) if not a.startswith("--") and not (i and argv[i - 1] == "--at")]
    return words, {"golden": "--golden" in argv, "previous": "--previous" in argv, "yes": "--yes" in argv, "force": "--force" in argv, "at": at}


def restore_plan(pid: str, flags: dict):
    """-> (folder to restore from, what to call it); exits when there is nothing to restore from."""
    gold = golden.GOLDEN_DIR / pid
    if flags["golden"]:
        src, name = (gold, "the golden state") if (gold / "golden.json").exists() else (None, None)
    else:
        which = flags["at"] or ("previous" if flags["previous"] else None)
        src = checkpoints.pick(pid, which)
        name = f"checkpoint {src.name} (saved {checkpoints._meta(src).get('created', '?')[:16].replace('T', ' ')})" if src else None
        if not src and which is None and (gold / "golden.json").exists():  # no checkpoint yet: the golden state is the only one there is
            src, name = gold, "the golden state (no checkpoint saved yet)"
    if not src:
        asked = f"--at {flags['at']}" if flags["at"] else "--previous" if flags["previous"] else "--golden" if flags["golden"] else None
        raise SystemExit(f"{pid}: nothing to restore from" + (f" ({asked})" if asked else ""))
    return src, name


def confirm(plans: list, flags: dict) -> None:
    """Show what each restore would lose and wait for 'yes'. Nothing to ask when no project has data yet (a new install)."""
    lines, risky = [], False
    for pid, src, name in plans:
        has_data = checkpoints.live_has_data(pid)
        risky |= has_data
        lines.append(f"{pid}: back to {name}")
        if has_data:
            diffs = golden.verify_project(pid, src)["differences"]
            lines += [f"   - {d}" for d in diffs[:8]] + ([f"   ... and {len(diffs) - 8} more"] if len(diffs) > 8 else [])
            if not diffs:
                lines.append("   (counts and numbers already match; edits to single rows would still be undone)")
    print("\n".join(lines))
    if not risky or flags["yes"]:
        return
    print("\nThis replaces the current state of the project(s) above. It is saved first as before-restore (restore --at before-restore undoes it).")
    if not sys.stdin.isatty():
        raise SystemExit("Not asked: there is no terminal to answer in. Add --yes to go ahead.")
    if input("Type yes to continue: ").strip().lower() != "yes":
        raise SystemExit("Cancelled, nothing changed.")


def main(argv: list):
    cmd = argv[0] if argv else "status"
    words, flags = parse(argv[1:])
    arg = words[0] if words else "all"
    if cmd == "status":
        for pid in ids():
            r = golden.verify_project(pid)
            print(f"{pid:12} {'matches its golden state' if r['ok'] else str(len(r['differences'])) + ' difference(s)'}")
            for d in r["differences"][:6]:
                print("   -", d)
    elif cmd == "restore":
        if arg == "all":
            names = ids() if flags["golden"] else sorted(set(ids()) | set(checkpoints.stored_ids()))
        else:
            names = [arg]
        plans = [(pid, *restore_plan(pid, flags)) for pid in names]
        confirm(plans, flags)
        if arg == "all" and flags["golden"]:  # a full reset to golden also clears what the demo left in AI Chat and the activity feed
            from apps.db.db import get_connection
            conn = get_connection()
            with conn.cursor() as cur:
                for table in ("chat_messages", "agent_jobs"):
                    cur.execute(f"DELETE FROM {table}")
            conn.commit()
            conn.close()
            print("chat history and activity feed cleared")
        bad = 0
        for pid, src, name in plans:
            t0 = time.time()
            r = checkpoints.restore(pid, src)
            print(f"{pid:12} {'ok' if r['ok'] else 'DIFFERENT'}  ({time.time() - t0:.1f} s)")
            for d in r["differences"]:
                print("   -", d)
            bad += not r["ok"]
        raise SystemExit(1 if bad else 0)
    elif cmd == "verify":
        bad = 0
        for pid in targets(arg):
            t0 = time.time()
            r = golden.verify_project(pid)
            print(f"{pid:12} {'ok' if r['ok'] else 'DIFFERENT'}  ({time.time() - t0:.1f} s)")
            for d in r["differences"]:
                print("   -", d)
            bad += not r["ok"]
        raise SystemExit(1 if bad else 0)
    elif cmd == "checkpoint":
        for pid in (checkpoints._project_ids() if arg == "all" else [arg]):
            folder, why = checkpoints.take(pid, force=flags["force"])
            print(f"{pid:12} {'saved as ' + folder.name if folder else 'not saved: ' + why}")
    elif cmd == "checkpoints":
        for pid in ([arg] if words else checkpoints.stored_ids()):
            for p in checkpoints.list_checkpoints(pid):
                m = checkpoints._meta(p)
                print(f"{pid:12} {p.name}  {m.get('tasks', '?')} tasks")
            undo = checkpoints.pick(pid, checkpoints.BEFORE_RESTORE)
            if undo:
                print(f"{pid:12} before-restore  (saved {checkpoints._meta(undo).get('created', '?')[:16].replace('T', ' ')})")
    elif cmd == "export":
        print(golden.export_project(arg))
    elif cmd == "drop":
        src = golden.GOLDEN_DIR / arg / "drop"
        for f in sorted(src.glob("*")):
            sub = "meetings" if f.suffix in (".txt", ".md", ".vtt", ".srt", ".docx") else "timesheets" if f.name.lower().find("timesheet") >= 0 else "plan"
            dest = tw.ROOT / arg / sub / f.name
            shutil.copy2(f, dest)
            print(f"copied {f.name} -> projects/{arg}/{sub}/")
    else:
        raise SystemExit(__doc__)


main(sys.argv[1:])
