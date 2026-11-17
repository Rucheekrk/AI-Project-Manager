"""Checkpoints (apps/utils/checkpoints.py): the last valid state of a project is saved on its own, a restore goes back to it, and a state that is
half-written, running, failed or broken is never saved."""
import json
import uuid
from datetime import datetime, timedelta

import pytest

from apps.db.db import complete_job, create_job, fail_job, get_connection, insert_task
from apps.utils import checkpoints, golden, timesheet_watcher as tw
from test_golden import build, snapshot_rows


class _Clock(datetime):
    """Every look at the clock is a minute later, in 2020: checkpoint names differ without waiting, and any run made now is newer than them."""
    tick = 0

    @classmethod
    def now(cls, tz=None):
        cls.tick += 1
        return datetime(2020, 1, 1, 9, 0, 0).astimezone() + timedelta(minutes=cls.tick)


@pytest.fixture
def world(test_project, tmp_path, monkeypatch):
    monkeypatch.setattr(tw, "ROOT", tmp_path)
    monkeypatch.setattr(checkpoints, "CHECKPOINT_DIR", tmp_path / "checkpoints")
    monkeypatch.setattr(checkpoints, "KEEP", 3)
    monkeypatch.setattr(checkpoints, "datetime", _Clock)
    monkeypatch.setattr(checkpoints, "_seen", {})
    monkeypatch.setattr(checkpoints, "_told", {})
    build(test_project, tmp_path)
    yield {"p": test_project, "root": tmp_path}
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM agent_jobs WHERE project_id = %s", (test_project,))
    conn.commit()
    conn.close()


def add_task(p, text):
    insert_task({"task_text": text, "normalized_task_text": text.lower(), "owner": None, "status": "not_started"}, p)


def task_texts(p):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT task_text FROM tasks WHERE project_id = %s", (p,))
        out = [r[0] for r in cur.fetchall()]
    conn.close()
    return out


def test_a_restore_goes_back_to_the_checkpoint_not_to_the_golden_state(world):
    p, root = world["p"], world["root"]
    folder, why = checkpoints.take(p, root)
    assert why == "saved" and folder.parent.name == p
    assert (root / "checkpoints" / ".gitignore").read_text() == "*\n"  # real addresses are in a checkpoint: never committed
    text = (folder / "golden.json").read_text()
    assert "ana@example.com" in text and "<<email:" not in text
    before = snapshot_rows(p)
    add_task(p, "Junk from a bad run")
    (root / p / "plan" / "plan.xlsx").write_bytes(b"edited by a bad run")
    result = checkpoints.restore(p, folder, root)
    assert result == {"ok": True, "differences": []}, result
    after = snapshot_rows(p)
    before.pop("meetings"), after.pop("meetings")  # a restore moves a meeting that waits for approval to the next business day
    assert after == before
    assert (root / p / "plan" / "plan.xlsx").read_bytes() != b"edited by a bad run"


def test_what_a_restore_replaces_is_kept_and_can_be_put_back(world):
    p, root = world["p"], world["root"]
    folder, _ = checkpoints.take(p, root)
    add_task(p, "Work done after the checkpoint")
    checkpoints.restore(p, folder, root)
    undo = checkpoints.pick(p, checkpoints.BEFORE_RESTORE)
    saved = json.loads((undo / "golden.json").read_text())
    assert "Work done after the checkpoint" in [t["task_text"] for t in saved["tables"]["tasks"]]
    assert checkpoints.list_checkpoints(p) == [folder]  # before-restore is not one of the checkpoints
    assert checkpoints.restore(p, undo, root)["ok"]
    assert "Work done after the checkpoint" in task_texts(p)


def test_an_unchanged_project_is_not_saved_again_and_a_changed_one_is(world):
    p, root = world["p"], world["root"]
    first, _ = checkpoints.take(p, root)
    assert checkpoints.take(p, root) == (None, "unchanged since the last checkpoint")
    add_task(p, "A new task")
    second, why = checkpoints.take(p, root)
    assert why == "saved" and checkpoints.list_checkpoints(p) == [second, first]
    assert checkpoints.pick(p) == second and checkpoints.pick(p, "previous") == first
    assert checkpoints.pick(p, first.name) == first and checkpoints.pick(p, first.name[:9]) == second  # a prefix gives the newest that starts with it
    assert checkpoints.pick(p, "19990101") is None


def test_only_the_last_few_are_kept(world):
    p, root = world["p"], world["root"]
    made = []
    for n in range(5):
        add_task(p, f"Task {n}")
        made.append(checkpoints.take(p, root)[0])
    assert checkpoints.list_checkpoints(p) == made[:1:-1]  # KEEP is 3: the newest three, newest first


def test_a_state_in_the_middle_of_something_is_held_back(world):
    p, root = world["p"], world["root"]
    (root / tw.PAUSED).touch()
    assert checkpoints.take(p, root) == (None, "a reset is running")
    (root / tw.PAUSED).unlink()
    (root / tw.SCANNING).touch()
    assert checkpoints.take(p, root) == (None, "the folder watcher is reading a file")
    (root / tw.SCANNING).unlink()
    job = str(uuid.uuid4())
    create_job(job, p)
    assert checkpoints.take(p, root) == (None, "a run is in progress")
    fail_job(job, "boom")
    assert "failed" in checkpoints.take(p, root)[1]
    job2 = str(uuid.uuid4())
    create_job(job2, p)
    complete_job(job2, {"tasks_count": 1})
    assert checkpoints.take(p, root)[1] == "saved"  # a later run that finished clears the failed one
    job3 = str(uuid.uuid4())
    create_job(job3, p)
    fail_job(job3, "boom again")
    add_task(p, "Changed after the failed run")
    assert "failed" in checkpoints.take(p, root)[1]
    assert checkpoints.take(p, root, force=True)[1] == "saved"  # --force skips the checks


def test_a_project_without_tasks_is_not_saved(world):
    assert checkpoints.take(f"empty-{uuid.uuid4().hex[:8]}", world["root"]) == (None, "the project has no tasks")


def test_rows_a_restore_could_not_put_back_are_found(monkeypatch):
    monkeypatch.setattr(golden, "manifest", lambda p: {})
    a, b, gone = "task-a", "task-b", "task-elsewhere"
    ok = {"tasks": [{"task_id": a, "deliverable_id": "d1"}, {"task_id": b, "deliverable_id": None}], "deliverables": [{"deliverable_id": "d1", "source_task_id": a}],
          "task_dependencies": [{"task_id": b, "depends_on_task_id": a}], "time_entries": [{"task_id": a}, {"task_id": None}]}
    assert checkpoints.problems("p", ok) == []
    bad = {**ok, "task_dependencies": [{"task_id": b, "depends_on_task_id": gone}, {"task_id": a, "depends_on_task_id": a}],
           "tasks": [{"task_id": a, "deliverable_id": "d-elsewhere"}], "deliverables": [{"deliverable_id": "d1", "source_task_id": gone}],
           "time_entries": [{"task_id": gone}]}
    assert checkpoints.problems("p", bad) == ["a deliverable points at a task outside the project", "a dependency points at a task outside the project",
                                              "a task depends on itself", "a task points at a deliverable outside the project",
                                              "an hours entry points at a task outside the project"]
    monkeypatch.setattr(golden, "manifest", lambda p: 1 / 0)
    assert checkpoints.problems("p", ok)[0].startswith("the project's reports cannot be worked out")


def test_the_loop_saves_only_after_a_project_has_looked_the_same_twice(world):
    p, root = world["p"], world["root"]
    assert p not in checkpoints.check_once(root)  # first look: new to the loop, a run could still be writing
    assert p in checkpoints.check_once(root)  # second look, same state: saved
    assert checkpoints.check_once(root) == []  # nothing new
    add_task(p, "A new task")
    assert p not in checkpoints.check_once(root)  # it changed, so wait one more look
    add_task(p, "Another task before the second look")
    assert p not in checkpoints.check_once(root)  # still changing
    assert p in checkpoints.check_once(root)
    assert len(checkpoints.list_checkpoints(p)) == 2
    (root / tw.PAUSED).touch()
    add_task(p, "During a reset")
    assert checkpoints.check_once(root) == []  # nothing is looked at while a reset runs
