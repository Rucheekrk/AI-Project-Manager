"""Checkpoints: the last valid state of each project, saved automatically, so a restore goes back to it instead of to the golden state.

    checkpoints/<project-id>/<YYYYMMDD-HHMMSS>/   golden.json + files/ (the same export format as apps/utils/golden.py) and meta.json
    checkpoints/<project-id>/before-restore/      the state a restore replaced (the latest one only): the way back from a wrong restore

A background loop (start_checkpointer, run by the API) looks at every project each minute. When a project differs from its last checkpoint, and has
looked the same on two looks in a row (a run in progress has not finished), nothing is running for it and the checks below pass, its state becomes
the newest checkpoint. The last KEEP are kept. A checkpoint holds real email addresses, so the folder is local only: it writes its own .gitignore.

A state is NOT saved when: a reset is running or the folder watcher is reading a file; the project's latest run (since the last checkpoint) is
still running or failed; the project has no tasks; a row points at a task, deliverable or dependency outside the project (a restore would fail on it);
or the project's own reports cannot be worked out. Jira issues, calendar events, chat history and the activity feed are not part of a checkpoint.

Restoring is never automatic: scripts/golden.py asks first and keeps what it replaces in before-restore/."""
import hashlib
import json
import os
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path

from apps.db.db import get_connection
from apps.logger import get_logger
from apps.utils import golden
from apps.utils import timesheet_watcher as tw

logger = get_logger("CHECKPOINTS")

CHECKPOINT_DIR = Path(os.getenv("CHECKPOINT_DIR") or Path(__file__).resolve().parents[2] / "checkpoints")
KEEP = int(os.getenv("CHECKPOINT_KEEP") or 10)
POLL_SECONDS = float(os.getenv("CHECKPOINT_POLL_SECONDS") or 60)
BEFORE_RESTORE = "before-restore"
STALE_RUN_SECONDS = 20 * 60  # a run still marked running after this long died with its process (a run is capped at 10 minutes)
_started = False
_seen: dict = {}  # project_id -> fingerprint on the previous look
_told: dict = {}  # project_id -> the last reason logged for not saving, so a project that stays blocked is not logged every minute


# ---------------------------------------------------------------- what is stored

def _dir(project_id: str) -> Path:
    return CHECKPOINT_DIR / project_id


def list_checkpoints(project_id: str) -> list:
    """The project's checkpoint folders, newest first (before-restore is not one of them)."""
    d = _dir(project_id)
    if not d.is_dir():
        return []
    found = [p for p in d.iterdir() if p.is_dir() and p.name != BEFORE_RESTORE and not p.name.startswith(".") and (p / "golden.json").exists()]
    return sorted(found, key=lambda p: p.name, reverse=True)


def stored_ids() -> list:
    """Projects that have at least one checkpoint."""
    if not CHECKPOINT_DIR.is_dir():
        return []
    return sorted(p.name for p in CHECKPOINT_DIR.iterdir() if p.is_dir() and list_checkpoints(p.name))


def _meta(folder: Path) -> dict:
    try:
        return json.loads((folder / "meta.json").read_text())
    except (OSError, ValueError):
        return {}


def pick(project_id: str, which: str = None):
    """The folder to restore from: None/'latest', 'previous' (the one before the latest), 'before-restore', or a timestamp (a prefix is enough)."""
    items = list_checkpoints(project_id)
    if which in (None, "latest"):
        return items[0] if items else None
    if which == "previous":
        return items[1] if len(items) > 1 else None
    if which == BEFORE_RESTORE:
        folder = _dir(project_id) / BEFORE_RESTORE
        return folder if (folder / "golden.json").exists() else None
    return next((p for p in items if p.name.startswith(which)), None)


# ---------------------------------------------------------------- is the project quiet, did it change, is it valid

def fingerprint(project_id: str, root=None, tables: dict = None) -> str:
    """One hash of everything a checkpoint holds: every row of the project and the content of its plan, meetings and timesheets files."""
    root = Path(root or tw.ROOT)
    tables = tables if tables is not None else golden.collect_tables(project_id)
    h = hashlib.sha256(json.dumps(tables, sort_keys=True, default=str).encode())
    for sub in golden.FOLDERS:
        for path in sorted((root / project_id / sub).rglob("*")):
            if path.is_file() and not path.name.startswith(".") and not path.is_symlink():
                h.update(str(path.relative_to(root / project_id)).encode())
                h.update(hashlib.sha256(path.read_bytes()).digest())
    return h.hexdigest()


def _busy(root: Path):
    if (root / tw.PAUSED).exists():
        return "a reset is running"
    if (root / tw.SCANNING).exists():
        return "the folder watcher is reading a file"
    return None


def _run_problem(project_id: str, since: str):
    """Why the project's latest run (after the last checkpoint) means its state is not settled, or None."""
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT status, created_at, NOW() - created_at FROM agent_jobs WHERE project_id = %s ORDER BY created_at DESC LIMIT 1", (project_id,))
        row = cur.fetchone()
    conn.close()
    if not row:
        return None
    status, created, age = row
    if status == "running" and age.total_seconds() < STALE_RUN_SECONDS:
        return "a run is in progress"
    if status == "failed" and (not since or created > datetime.fromisoformat(since)):
        return "the latest run failed, so the project may be half-updated"
    return None


def problems(project_id: str, tables: dict) -> list:
    """Reasons this state must not become a checkpoint (empty = valid). Every one of them would make a restore fail or give wrong numbers."""
    out = []
    task_ids = {r["task_id"] for r in tables["tasks"]}
    deliverable_ids = {r["deliverable_id"] for r in tables["deliverables"]}
    for r in tables["task_dependencies"]:
        if r["task_id"] == r["depends_on_task_id"]:
            out.append("a task depends on itself")
        elif r["depends_on_task_id"] not in task_ids:
            out.append("a dependency points at a task outside the project")
    if any(r["deliverable_id"] and r["deliverable_id"] not in deliverable_ids for r in tables["tasks"]):
        out.append("a task points at a deliverable outside the project")
    if any(r["source_task_id"] and r["source_task_id"] not in task_ids for r in tables["deliverables"]):
        out.append("a deliverable points at a task outside the project")
    if any(r["task_id"] and r["task_id"] not in task_ids for r in tables["time_entries"]):
        out.append("an hours entry points at a task outside the project")
    try:
        golden.manifest(project_id)
    except Exception as e:
        out.append(f"the project's reports cannot be worked out ({e})")
    return sorted(set(out))


# ---------------------------------------------------------------- taking one

def take(project_id: str, root=None, label: str = None, force: bool = False):
    """Save the project's current state as a checkpoint -> (folder, "saved") or (None, why nothing was saved).
    label=BEFORE_RESTORE saves the state a restore is about to replace, without the checks. force=True skips the checks but not the save."""
    root = Path(root or tw.ROOT)
    safety = label == BEFORE_RESTORE
    if not safety and not force and (why := _busy(root)):
        return None, why
    tables = golden.collect_tables(project_id)
    if not tables["tasks"]:
        return None, "the project has no tasks"
    last = (list_checkpoints(project_id) or [None])[0]
    if not safety and not force:
        if bad := problems(project_id, tables):
            return None, "; ".join(bad)
        if why := _run_problem(project_id, _meta(last).get("created") if last else None):
            return None, why
    fp = fingerprint(project_id, root, tables)
    if not safety and not force and last and _meta(last).get("fingerprint") == fp:
        return None, "unchanged since the last checkpoint"
    tmp = _dir(project_id) / f".tmp-{os.getpid()}"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    try:
        golden.export_project(project_id, root, out_dir=tmp, hide_emails=False)
        if fingerprint(project_id, root) != fp:  # something wrote while the files were copied: the copy may mix two states
            return None, "the project changed while it was being saved"
        created = datetime.now().astimezone()
        (tmp / "meta.json").write_text(json.dumps({"created": created.isoformat(), "fingerprint": fp, "label": label, "tasks": len(tables["tasks"])}, indent=1) + "\n")
        final = _dir(project_id) / (BEFORE_RESTORE if safety else created.strftime("%Y%m%d-%H%M%S"))
        if final.exists():
            if not safety:
                return None, "a checkpoint with this timestamp exists"
            shutil.rmtree(final)
        tmp.rename(final)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    (CHECKPOINT_DIR / ".gitignore").write_text("*\n")  # real email addresses are in here: never committed
    for old in list_checkpoints(project_id)[KEEP:]:
        shutil.rmtree(old, ignore_errors=True)
    return final, "saved"


# ---------------------------------------------------------------- restoring one

def live_has_data(project_id: str) -> bool:
    counts = golden.counts(project_id)
    return bool(counts["tasks"] or counts["source_documents"])


def restore(project_id: str, source: Path, root=None) -> dict:
    """Put the project back as `source` holds it (a checkpoint, or the golden export), after saving what is there now as before-restore."""
    root = Path(root or tw.ROOT)
    copy = None
    if source.name == BEFORE_RESTORE:  # undoing a restore: saving the current state replaces that very folder, so read from a copy of it
        copy = source.parent / f".undo-{os.getpid()}"
        shutil.rmtree(copy, ignore_errors=True)
        shutil.copytree(source, copy)
        source = copy
    try:
        if live_has_data(project_id):
            take(project_id, root, label=BEFORE_RESTORE)
        return golden.restore_project(project_id, golden_dir=source, root=root)
    finally:
        if copy:
            shutil.rmtree(copy, ignore_errors=True)


# ---------------------------------------------------------------- the loop

def _project_ids() -> list:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT project_id FROM tasks WHERE project_id IS NOT NULL")
        ids = [r[0] for r in cur.fetchall()]
    conn.close()
    return sorted(i for i in ids if tw._safe_id(i))


def check_once(root=None) -> list:
    """One look at every project: save a checkpoint for each that changed and has settled -> the ids saved."""
    root = Path(root or tw.ROOT)
    saved = []
    if _busy(root):
        return saved
    for pid in _project_ids():
        try:
            fp = fingerprint(pid, root)
            last = (list_checkpoints(pid) or [None])[0]
            if last and _meta(last).get("fingerprint") == fp:
                _seen[pid] = fp
            elif _seen.get(pid) != fp:  # new since the last look: wait one more look, so a run that is still writing can finish
                _seen[pid] = fp
            else:
                folder, why = take(pid, root)
                if folder:
                    saved.append(pid)
                    _told.pop(pid, None)
                    logger.info(f"{pid}: checkpoint {folder.name} saved")
                elif _told.get(pid) != why:
                    _told[pid] = why
                    logger.info(f"{pid}: no checkpoint yet ({why})")
        except Exception:
            logger.exception(f"{pid}: the checkpoint check failed; trying again next time")
    return saved


def _loop():
    time.sleep(POLL_SECONDS)  # let the API finish starting first
    while True:
        try:
            check_once()
        except Exception:
            logger.exception("Checkpoint loop failed; trying again next time")
        time.sleep(POLL_SECONDS)


def start_checkpointer() -> None:
    """Called once when the API starts. Off if CHECKPOINTS=0."""
    global _started
    if _started:
        return
    if os.getenv("CHECKPOINTS", "1") == "0":
        logger.info("Automatic checkpoints are switched off (CHECKPOINTS=0)")
        return
    _started = True
    threading.Thread(target=_loop, daemon=True, name="checkpointer").start()
    logger.info(f"Checking every {POLL_SECONDS:g}s for projects to checkpoint in {CHECKPOINT_DIR}")
