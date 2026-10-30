# Decisions Log

Why this file exists: a running record of the non-obvious calls made on this project - what
was decided, why, what alternatives were considered and rejected, and what's still pending.
The code shows *what* the system does; this file is for *why* it does it that way, so nobody
(including future us) has to reconstruct the reasoning from scratch or guess at it when
explaining the system to someone else.

Newest entries at the top. Each entry: the decision, the reasoning behind it, what was
considered and not chosen, and current status.



---

## Docs becomes a Guide; Feedback removed (2026-10-30)

**Why.** Feedback was a "coming soon" placeholder with no form or storage, which looks unfinished in a demo. Docs was three stale blurbs (it still
described the old task export and said nothing about Hours, the plan or the timesheet folder). With no timesheet upload button, people have to be
told where files go.
- **Feedback:** the sidebar link and `/feedback` page are removed. Not replaced: a real version needs storage and someone who reads it. Cheap options
  if wanted later: a "Send feedback" email link in Settings, or thumbs up / down on AI Chat answers (the more useful signal).
- **Guide:** `/resources` is kept (so no link breaks) and rewritten as seven short cards in the order a project goes: get a project in, keep the plan
  here, send timesheets by folder (path, file-name rule, what Imported / Needs review / Already imported mean), read the hours status, Registers, AI
  Chat example questions, Jira and Calendar. Static text, each card links to its screen. Chat examples only use questions that have a tool behind them
  (there is no risk tool, so none is listed). The sidebar label is now "Guide".
- **Upkeep:** it is hand-written, so it goes stale when a screen changes; update it in the same change.

---

## Timesheets arrive by folder, not by upload button (2026-10-30)

**Why.** The manager's direction: no upload buttons for timesheets. Timesheets are produced by other people, so they are PULLED IN
(the plan is the project manager's own data, so it is loaded once and edited in the app; see the entry below). **Decided (user), the
"go with 1 + 2 + 4 and all six defaults" choice:**
- **Where:** a folder INSIDE the project, `timesheets/<project-id>/`, created for every project with tasks when the API starts. The API
  container already mounts the whole project folder, so no new mount and nothing else on the laptop is visible to it. `timesheets/` is
  gitignored (client data stays off the remote). Subfolders `processed/` and `needs-review/` hold what was handled. A file is never
  overwritten when moved; a name clash gets a time suffix.
- **How:** a background thread in the API process looks every 10 s (`TIMESHEET_POLL_SECONDS`), waits until a file has stopped changing
  (2 s, size and times rechecked) so a half-copied file is never read, skips dotfiles, `~$` lock files, `.tmp/.part/.download` and symlinks. It
  runs only while the API container runs; after a restart it catches up on whatever is in the folders. `TIMESHEET_WATCH=0` switches it off.
  It is automatic pickup, NOT a fifth agent: no LLM decides anything beyond what the import already did (column mapping and task matching).
- **Which project:** decided by the FOLDER, never by file contents (the "Project" column is ignored). So a file dropped in the wrong folder lands
  in the wrong project; the file-name rule is the guard against that.
- **Auto-apply rules (1 + 2 + 4), all must hold, otherwise the file is HELD and nothing is written:** (1) every person in the file is on the
  project's people list; (2) the file name starts with the project id, and not with another, longer project id (`forloop-x.csv` is not for a
  project `for`); (4) the lines are not clearly about different tasks (3 or more task-named lines and none match a task of this project). Plus every
  row readable. A held file moves to `needs-review/` with the reason and shows **Review** in the Incoming timesheets card, which opens the same
  review screen the old upload used; confirming applies it and moves the file to `processed/`.
- **Check these matches (default 1):** applied files are NOT held for guessed task matches; instead the lines whose task was only suggested, guessed
  by the model or not found are listed with a task dropdown. Picking another task MOVES that person's hours for that label (totals do not change;
  `POST /hours/imports/{id}/reassign`; Undo still restores everything, previous values are kept in the import's summary).
- **Same file twice:** content hash against applied imports, status "Already imported", nothing written. Same person + week + task in a different
  file still REPLACES (existing rule). Undo of a picked-up file works like any import. A file that cannot be parsed, is over the size limit or hits an
  unexpected error is held or marked failed and never stops the next file.
- **UI:** the "Upload a timesheet" card is gone. Hours > Timesheet now has **Incoming timesheets**: the folder path, "last checked N s ago",
  the recent files with Imported / Needs review / Already imported / Failed, Undo, Review, and the Check these matches table. The Hours page
  polls every 5 s and reloads the report and grid when a file lands, so a dropped file shows up without a refresh. The hand-entry grid stays.
  The plan upload button stays (first upload only).
- **Kept:** the upload API endpoints still exist (tests and the plan import use them); only the timesheet button is gone. There is no hidden
  manual upload.
- **Golden data:** the `--existing` loader also moves everything in `timesheets/forloop/` to `timesheets/_archive/`. The demo step is now
  `cp datasets/hours/forloop/forloop-timesheet-week5.csv timesheets/forloop/` (the name already starts with `forloop`). Verified live: the
  file was picked up in under 30 s, 463 h logged, 237 h left, forecast 737 h (37 h over), 10 lines in Check these matches; Undo back to 363;
  a file with an unknown person was held, reviewed in the UI, applied; reset restored 363 / 346 / 709. Also rehearsed on a throwaway project.
- **Risks / not done:** auto-apply can guess a task wrong (that is what the check list and Undo are for). The watcher lives in the API process
  (stops with Docker or the laptop; one process only, so running two API replicas would double-read, which the duplicate check absorbs).
  No access control on the folder (anyone with the laptop can drop a file); no record of WHO dropped it. The `ensure_folders` pass runs at start and
  on each scan for projects that exist then; a project created after start gets its folder within one scan. Windows/network-share folders and
  Clarity/Jira worklog pulls are not built. Tests: 336 passing (21 new in `tests/db/test_timesheet_folder.py`).

---

## The plan is maintained in the app: baseline, change history, Plan view (2026-10-30)

**Why.** The project manager owns and maintains the plan; an Excel master re-read every few hours would make two sources of truth (edits
overwritten, tasks matched by fuzzy name so a rename looks like a delete plus an add, history unreliable). Rule used: data other people or
systems produce (timesheets) is PULLED IN; data the project manager owns (the plan) is loaded ONCE and edited here. **Decided (user):** upload
only the first time, no re-import, baseline and change history, Export to Excel as the one-way way out.
- **Where:** Workspace > Tasks, views **Plan | Board** (Plan default). Plan REPLACES List (same table, every List column and filter kept, plan
  columns added; the "Updated" column was dropped to make room). Hours > "By task" is removed; its job moved into Plan (estimate, weeks,
  hours still needed, the needs-attention filter). The Hours Overview "Needs attention" box stays and links to the plan.
- **First upload only:** `Upload plan` appears only while the project has no plan (`plan_summary.has_plan` false). Enforced on the server: a plan
  preview on a project that already has one is a 409. Undoing the first import returns the project to "no plan".
- **Baseline:** `tasks.baseline_*` and `project_hours_settings.baseline_set_at`, set automatically by the first plan import (or by "Set baseline" on
  a project with a plan but none), ONCE per project. A task created after that moment is "added after baseline" (by time, so tasks a document run
  creates later count as scope growth too); a task removed through the plan keeps its baseline hours in the baseline total. The strip above the
  table: "Baseline 29 Oct: 612 h planned, now 620 h (+8 h), 1 task added". The Baseline column shows the original estimate and the change;
  changed weeks show a marker with the original weeks on hover.
- **Change history:** `plan_changes` (what, task, from, to, when, source). Logged: estimate, start / finish week, phase, hours still needed, task
  added / removed, budget, kickoff, baseline set, plan imported / undone. A plan import is ONE line, not one per task. Unchanged values are not
  logged. It records WHEN and WHAT, never WHO: no sign-in yet. Tasks created by a document run after the baseline are listed from the tasks
  themselves.
- **Add / remove:** add by hand (duplicate names refused, owner joins the roster like in the pipeline); remove is a soft removal with a
  one-line confirmation that says how many logged hours stay in the project total as hours not on a task. Dependency links go with it so nothing
  shows "unknown task". Its Jira issue is NOT touched. Phases from the plan file are now saved (they were dropped) and editable.
- **Export to Excel** is the one-way way out: the Workspace button now gives a workbook of Plan (all task columns plus phase, weeks, estimate,
  baseline, change, logged, left), Summary and Change history. Text cells are plain text, never formulas. The Sync/Reporting agent's own
  `generate_report` is untouched.
- **Chat:** new tool `get_plan_changes`: baseline vs now, tasks added and removed, and only the changes made AFTER the baseline, with units
  ("week 6 to week 7", "48 h to 56 h"; the first version said "from 6 hours to 7 hours" about a week number, caught in a real chat test and fixed
  in the tool, not the prompt).
- **Golden data:** the `--existing` loader also clears the plan history and baseline, restores tasks removed in a demo and deletes tasks added by
  hand in the Plan view, so a reset always ends in the same state. forloop after a reset: 612 h baseline = 612 h now, 22 planned tasks in 3 phases
  plus two outside the phases, 363 / 346 / 709 unchanged. Verified by adding a task, editing an estimate, removing the task, then resetting.
- **Not done / open:** (the timesheet folder pickup was built the same day, see the entry above.) Re-baselining (a second baseline) is not offered. The Extractor still
  accepts a second SOW; only the plan FILE is first-upload-only. Tests: 315 passing (17 new in `tests/db/test_plan.py`).

---

## Settings page: seven additions, and why week start is a PROJECT setting (2026-10-29)

**Added** (user approved a list of five and asked for two more): the Default project text now says Workspace, Registers, Hours and Extractor
(it was out of date); agent activity panel shown or collapsed (an existing preference, now reachable from Settings); table rows
comfortable or compact; "show how the assistant got each answer" in Chat (off by default); a display name for the sidebar; date format;
week start. The page is grouped: Appearance, Workspace, Chat, Hours. All are per-browser (localStorage) except week start.
- **Table rows:** `data-density="compact"` on `<html>` (set before first paint by the inline script in `layout.tsx`, like the theme) and one
  un-layered CSS rule that tightens every table cell's padding (8 px less per row on the Workspace list).
- **Chat sources:** the API already returned the tools used; `ChatMessage.trace` now keeps them and `lib/toolLabels.ts` maps tool names to
  client-friendly words ("Hours", "SOW and meeting minutes"). Only answers received in the current session carry it: saved history stores
  no trace. An unknown tool is left out rather than shown by its internal name.
- **Date format:** every displayed date now goes through `lib/format.ts` (`formatDate`, `formatDateTime`): Browser default, DD/MM/YYYY,
  MM/DD/YYYY, YYYY-MM-DD, or "29 Oct 2026". NOT affected, and the page says so: native calendar pickers (they follow the computer's language
  setting) and dates inside the assistant's chat answers or backend notes (they are ISO text from the server).
- **Week start is a per-project setting, not a browser preference.** Hours are stored per week, so two people with different week starts on
  the same project would file the same hours into different weeks. It is `project_hours_settings.week_start_day` (0 Monday ... 6 Sunday;
  the UI offers Monday, Sunday, Saturday), default Monday, so every existing number, including the golden forloop ones, is unchanged. It is
  threaded through `week_start`, `weeks_elapsed`, the planned-finish Friday, availability, the timesheet, the import parser (flat, grid and
  matrix) and the report's default date. Changing it re-files every logged week in one transaction: each stored week moves to the new week
  that contains its middle day, so "the week of 19 Oct" stays the week of 19 Oct, the mapping is reversible, and no hours are lost or merged.
  Control: Settings > Hours only, with a project picker in the row (it starts on the default project). It was first ALSO in Hours > Overview
  next to budget and kickoff; removed the same day: it is set once, does not change any number on that page, and two places for one
  setting was confusing. The picker is what makes Settings enough: before it, the row could only edit the default project.
  Working-week maths (Mon-Fri) does not depend on the choice: forloop's forecast, due-by-now and free hours are identical for all three.
  **Known limit:** undoing an import that was applied before a week-start change puts its overwritten rows back under the OLD week
  convention; change the week start before importing, not between an import and its undo.
**Verified:** in the browser on the disposable copy (not the live forloop): Sunday moved all five logged weeks onto Sundays with 463 h and the
737 h forecast unchanged, Monday restored them; display name and its first letter updated the sidebar; compact rows measured 8 px
tighter; the chosen date format showed on the Workspace "Updated" column; the activity panel stayed collapsed; the sources line appeared
under a real answer. Tests: 298 passing, including the week-start cases for Monday, Saturday and Sunday.

---

## Click-to-edit no longer moves the table (2026-10-29)

**Bug.** Clicking a cell to edit it shifted the column and the rows, and the page itself jumped sideways. Measured on the Hours capacity
table: the edited column grew from 127 to 137 px and the other columns shrank, and an input taller than its text made the row taller;
once the page was taller than the window a scrollbar appeared and pushed the whole table left (about 9 px). It happened in every table
with click-to-edit cells: Workspace tasks, Hours, RAID, Deliverables, RACI, and the Jira key in the Workspace header.
**Fix, and why this one:** a shared wrapper, `frontend/components/InlineEditShell.tsx`. The read-only content STAYS in the layout (hidden
while editing) and the editor FLOATS over it (absolutely positioned, vertically centred, at least as wide as the cell, anchored left,
right or centre), so the cell, row, column and table cannot change size whatever the editor looks like. Used by `TextCell`,
`InlineEditCell`, the dependency picker, `NumberCell`, `SkillsCell`, the RACI role picker and `ProjectSettings`. Two supporting changes:
editors are focused with `focus({ preventScroll: true })` (`autoFocus` made the browser scroll the table sideways to reveal the input),
and `html { scrollbar-gutter: stable }` reserves the scrollbar's width so a page that becomes taller never shifts sideways.
**Rejected:** giving the edit control exactly the same fixed width and height as the text. It fails whenever a value is longer than the
control (a title, a list of skills), and it would make every row taller to fit the control. **Verified** by measuring row heights, column
widths, table position and page height before and after the click, in the browser: no change for the Hours capacity and skills cells,
Workspace owner / status / priority / deadline / blocker / add-dependency, a RACI cell, RAID title and owner, Deliverables title and
deadline, and the Jira key chip. Not covered by the wrapper on purpose: the add-person and add-item forms, which open as new panels.

---

## AI Chat: six demo prompts, checked against forloop, and the bugs checking them found (2026-10-29)

**Change.** The New Chat button now sits below and to the left of the input bar, and the empty-chat screen offers six prompts, one per
topic, replacing four generic ones (one of which named vmware-sim). They name `forloop` explicitly because it is the golden dataset
(`ChatWindow.tsx`, `SUGGESTED_PROMPTS`): (1) status summary, (2) hours left and on track, (3) tasks over their estimate, (4) who is free for
QA or backend work in the next 4 weeks, (5) what the Sales Trends view depends on and whether that is finished, (6) what the SOW says about
the go-live date and concurrent users. **How they were chosen:** eight candidates were run through the real chat and each answer compared
with the database; the six kept were identical across two runs and match the data (7 completed / 7 in progress / 10 not started; 337 h
left and status Watch; VPN 16 vs 12 h and QA plans 14 vs 12 h; David 64 h, Marcus 140 h, Elena 98 h free; depends on the completed ETL
pipeline; go-live end of Week 8 and 200 concurrent users). **Rejected:** "which forloop tasks are synced to Jira" (it listed two of five
and guessed at the rest) and "what is blocked in forloop" (the only blocker is text on a task whose status is in progress, so the answer is
muddled); both need the underlying data or tools to be better first. The answers hold while forloop is in the state the loader leaves it
in (and the free-hours numbers shift with today's date, since planned work is spread from today).

**Bugs found by checking them, all fixed.** (1) The SOW had no search chunks, so Chat said it had no details on go-live or users: documents
stored before search existed were never chunked, and re-submitting them did nothing. `upsert_source_document` now chunks a document that
has none, and `scripts/backfill_document_chunks.py` fills every such document (one was missing: the forloop SOW). (2) The dependency tool
returned task ids, so the chat printed raw ids; it now returns names, owners and statuses of both sides. (3) The hours answer called the
project "at risk" or "on track and Watch": the schedule value and the status word shared a label. The schedule value is now `in_line`, and
the hours report carries a one-sentence `burn_check.summary` ("Watch: work done is in line with the plan, but the forecast is 9.0 h over the
budget.") that the chat manifest tells it to use as written. (4) The project rollup had no not-started count, so the chat computed it; it
is now `not_started_tasks`. 276 + 4 new tests passing.

---

## Hours: design, synthetic forloop data, and the build (2026-10-29)

**Goal.** AI Chat should be able to answer "how many hours are left in this project?" and "who is available for this
engineering work?". Nothing in the app tracked hours before (the Chat manifest says so; the earlier note in the document-search
entry deferred it as "a separate design conversation"). This is that conversation. Built the same day: see "What was built" at the end of this entry. Still LOCAL and UNCOMMITTED.

**Three inputs, three sources.** Budget (SOW or commercial doc), estimated hours per task (project plan), actual hours
(timesheets). The plan holds estimates; actuals almost never live in it. "Hours left" is budget minus actuals; with no actuals the
Chat must say which number it is giving (budget minus planned, or open estimated work), never pass one off as the other.

**Decided (user confirmed).**
- One standard format that clients adapt to, like Jira, not per-client tuning. Time is kept weekly; hours are entered against a
  task PICKED from the project's task list, plus an "Other" bucket, so no free-text matching is needed for hours typed in the app.
- **Upload is the main way in, typing is the fallback** (retyping an existing timesheet is redundant and error-prone). Upload lives
  on the Hours page, NOT in the Extractor / 10-node pipeline: the pipeline extracts tasks from narrative text, reads no Excel, and a
  timesheet row is not a task. The same import also reads the project plan for estimates.
- Import steps: code finds the header and layout (one row per entry, weekly grid, person-by-week matrix); an LLM only PROPOSES the
  column mapping; a person confirms in a preview; hour values are read from the cells by code, never by the LLM, and each entry keeps
  its sheet and row. Free-text task names go through the existing Match logic and wait for confirmation when unsure; unmatched
  hours go to "Other" so the project total stays right. Re-uploads REPLACE by (person, week, task) instead of adding, and every
  import is tagged so it can be undone.
- Metrics: task remaining = estimate - actual (0 if complete); overrun flagged; hours left in budget = budget - all actual hours;
  forecast = actual + remaining on open tasks; ahead/behind = budget - forecast; burn check. Open tasks with no estimate are left out of
  the forecast and the Chat says how many.

**Defaults, not yet explicitly confirmed.** (a) "Hours still needed" (estimate to complete) asked only when an open task reaches its
estimate, so an overrunning task is not shown with 0 left; (b) storage: `estimate_hours` on `tasks`, a small budget table (project
total first, by role later), a `time_entries` table whose task link is optional (rows with no task still count toward the project
total), `weekly_capacity_hours` and skills on `project_people`; totals are computed, never stored; (c) availability = weekly capacity
- remaining hours of open tasks spread evenly to their due dates, tasks with no estimate or date shown as unknown; (d) build order:
estimates + budget + hours entry + the two Chat tools, then capacity and availability, then plan/timesheet import and SOW budget
extraction; (e) UI: an "Hours" sidebar page (Overview, Timesheet, By task, Capacity), plus Estimate/Logged/Left columns in Workspace
Tasks, capacity and skills in People, an "Hours left" card on the Dashboard. A Jira-worklog pull is a possible later path (the Jira
connection only creates issues today).

**Synthetic data.** `datasets/hours/forloop/` (generator: `scripts/generate_forloop_hours_dataset.py`, README inside): a plan, a flat
CSV, a weekly-grid workbook, a person-by-week summary and `forloop-hours-expected.json`, all views of one table of hours, consistent
with the Week 3 sync minutes. Checked by re-reading the generated files cold: flat (258 h) + grid (105 h) = summary = 363 h.

**Burn check (decided by the user: compare work DONE with work DUE BY NOW, with partial credit).** The first version compared
the share of the budget used with the share of task estimates completed, which read badly behind on the synthetic project (51.9%
used, 29.4% done) although the plan was on schedule. Now: a task counts as done in proportion to its hours (logged / (logged +
remaining), capped at 90% until someone marks it completed) and as due in proportion to how much of its planned weeks (start..finish
week from the plan, counted from the kickoff date) have passed. On schedule if done >= due - 5 points; the forecast is "within",
"tight" (over 95% of the budget) or "over"; status is on_track / watch / at_risk (behind AND over). End of Week 4 on the forloop data:
51.9% of budget used, 44.3% due, 43.1% done, forecast 709 h vs 700 h -> schedule on track, cost over, status Watch. Checked by hand
from the plan (due 271.3 of 612 estimated hours, done 263.6), not only by the code.

**What was built (the user asked for every step in one go).**
- Storage (`apps/db/hours_db.py`, `ensure_hours_schema` at startup): `tasks.estimate_hours / plan_start_week / plan_finish_week /
  hours_still_needed`; `project_people.weekly_capacity_hours / skills`; `project_hours_settings` (budget, kickoff date, per-role
  budgets); `time_entries` (task link optional, ON DELETE SET NULL, unique per project + person + week + task so imports REPLACE);
  `hours_imports` (previews, applied imports with what they overwrote, for undo). Nothing computed is stored.
- Rules (`apps/utils/hours.py`, pure functions): remaining, forecast, burn check, availability (capacity for the working days in a
  window minus remaining hours spread evenly from today to each task's due date, due = Friday of the planned finish week or an ISO
  date in the deadline text; unknowns listed, never guessed). The Chat tools, the Hours page and the task list all use it.
- Import (`apps/utils/hours_import.py`, `/projects/{id}/hours/import/preview`, `/hours/imports/{id}/confirm|undo`): layouts one row per
  entry, weekly grid per person, person-by-week matrix, and the plan (tasks, estimates, weeks, budget, kickoff). Code reads every number
  from its cell and keeps the sheet and row; an LLM only proposes columns when headers are unrecognised and the user can override.
  People: exact, "Last, First", initials. Tasks: exact text after expanding abbreviations, then embeddings, then ONE batched LLM check
  that may only pick among the closest tasks or say none; plan mode is stricter (same work, not related work; one task per plan row).
  Uncertain matches are shown as "check" and the user confirms; anything unmatched counts as Other so project totals stay right.
- Budget from the SOW (`apps/utils/hours_budget_ai.py`): kept only if the quote is verbatim and contains the number; never converts a
  weekly availability or days into a budget; the user presses "Use this number".
- AI Chat: tools `get_project_hours` and `find_available_people`, manifest rules to report the numbers as returned and always state the
  caveats (no budget, tasks without estimate, tasks over their estimate, no capacity). Checked with the real chat on the demo project:
  337 h left, Marcus Chen 132 h logged, 28 h left on Sales Trends, Marcus and Elena free for backend work, all as the tools returned.
- UI: sidebar "Hours" (Overview, Timesheet with upload + hand entry + the "hours still needed" prompt, By task with plan upload,
  Capacity with who-is-free search); Estimate / Logged / Left columns in Workspace Tasks; capacity and skills in People; "Hours left"
  cards on the Dashboard. Only difference from the plan: the task list repeats the one-line remaining rule in TypeScript
  (`TaskTracker.remainingFor`) to update a row without a refetch; if the rule in `apps/utils/hours.py` changes, change it there too.

**Measured.** Task matching on the synthetic data (`eval/nodes/eval_hours_import.py`, real LLM): embeddings alone 30 of 36 labels
right, 296 of 363 h (82%); with the model check 32 of 36 labels, 336 h (93%). The misses are the genuinely ambiguous ones (a
"Delivery management" label attached to the final-delivery task, 23 h; three VPN follow-ups left as Other). End to end through the
real API (`scripts/seed_forloop_hours_demo.py`, demo project `forloop-hours-demo`): 363 h imported exactly, 20 of 24 tasks with exactly
the right hours, 29 h on a different task, forecast 693 h against an expected 709 h. Every one of those matches is marked "check" in
the review step; the limits are one synthetic project, one author for data and key, and matching judged against that key.
Tests: 275 passing (72 new, incl. the three layouts, replace-not-add, undo, merge, deletion, chat tools).

**Bugs found by running it on the data, and fixed.** (1) Deleting a task turns its hour entries into "Other" entries, which collided with
existing "Other" entries for the same person and week, so a project with hours could not be deleted; hours are now removed first.
(2) Merging two duplicate tasks left the duplicate's hours behind on a deactivated task; they now move to the survivor (summed where the
same person and week exist on both) and the duplicate's estimate fills blanks. (3) The first plan matching reused the timesheet prompt
and attached the project-management row to an unrelated task; plan rows now use their own stricter prompt.

**Not built / open.** Per-role budgets are stored and shown but no role-level forecast; no Jira worklog pull (the Jira connection still
only creates issues); availability does not read Google Calendar free/busy; "who is available" matches role and skill words only (no
"has done similar tasks" ranking); the burn check assumes plan weeks come from the plan or are entered by hand, and says so when they
are missing; (resolved the same day, see below) the burn check no longer uses today's date.

**Loaded into the live `forloop` project (user request, 2026-10-29: "one golden data set I can run and show to clients").** The
build and its bugs were first found on a disposable copy (`forloop-hours-demo`) so the live project could not be damaged; the user
then asked for forloop itself, so `python -m scripts.seed_forloop_hours_demo forloop --existing` (in the api container) loads the
synthetic hours on top of the live tasks. It is re-runnable before every demo and always ends in the same state: it clears only hours
data (entries, imports, settings, estimates), reloads the plan and both timesheets through the real import API, and never deletes a
task or touches a deadline or owner. Three things it DOES change on forloop, deliberately: (1) task statuses are set to the end-of-Week-4
state from the Week 3 minutes (13 changed, plus the project-management task the plan creates; the originals, 22 "not_started" and one
blank, are in `logs/forloop-before-hours-*.json`, which is git-ignored); (2) blank roles are filled from the SOW's Team list, and
capacity and skills are set (capacity and skills are invented); (3) the script plays the REVIEWER: where the importer's proposed task
for a label differs from the answer key (5-6 of 43 flat-file rows) it applies the key's task, as a person correcting the "check" rows
would; without that step the importer alone reaches 93% of hours (see Measured). Result on forloop: 363 h logged, 346 h open, forecast
709 h vs the 700 h budget, burn check Watch (on schedule, 9 h over), all equal to `forloop-hours-expected.json`.
**Burn-check date:** it is now anchored to the end of the latest week with hours logged (never later than today), not to today, so the
golden numbers do not drift with the calendar; a note says so when nothing has been logged for over a week (otherwise a team that
stopped logging would look fine). An explicit `as_of` still wins. **Stored forloop deadlines, fixed on 2026-10-29 at the user's request** (the old values are in `logs/forloop-deadlines-before-fix.json`, git-ignored):
"Deliver data mapping document" 2026-09-25 -> "end of Week 2"; "Coordinate user acceptance testing" 2026-09-07 -> "Week 7"; "Deploy the
dashboard" 2026-09-25 -> "end of Week 8" (all three straight from the SOW's own wording, which the old date parser had turned into
wrong dates); "Review VPN access resolution" "early next week" -> "early Week 4" (the Week 3 sync said "early next week"). The deploy
task's owner stays blank on purpose: the SOW says "the team", not a person, and a made-up owner would become a person in the People list.
**Demo plan (answer to "delete forloop or run one more doc?"): keep forloop, never delete it.** Live hours step: upload
`datasets/hours/forloop/forloop-timesheet-week5.csv` (100 h, clear labels). Rehearsed on a copy: all 15 rows matched the right task with
no corrections, and the numbers moved exactly as derived by hand (asserted in `tests/unit/test_hours.py`): logged 363 -> 463, left in
budget 337 -> 237, remaining 346 -> 274, forecast 709 -> 737 (37 h over). Reset afterwards with the `--existing` command above. A live
pipeline step (extract a document into tasks) should use a FRESH project id: forloop has Jira project FLP configured, and a run that
creates tasks would create real issues in it (create-only); a fresh project has no Jira mapping, so Jira sync is skipped.

---

## Three pipeline bugs found while documenting the nodes, and fixed (2026-10-27)

Found by RUNNING the code and reading the stored data while writing the node-by-node walkthrough, not by the tests (none
covered these helpers). Fixed with regression tests that fail on the old code (24 failures) and pass on the fix. Full
suite: 203 passed (58 new). Still LOCAL and UNCOMMITTED. **Decision (user): fix the code only; do NOT touch the wrong values
already stored in the `forloop` project.**

**1. Deadlines (`apps/utils/deadline.py`, `resolve_deadline`).** Any text containing a digit fell through to a fuzzy date
parse that read the digit as a day of the current month, and "end of Week N" matched the "end of week" rule. Results:
"Week 7" -> the 7th, "Q2 2026" -> 2026-02-27, "in 3 days" -> the 3rd, and "end of Week 2" and "end of Week 8" both -> the
coming Friday. Stored evidence: in `forloop` two tasks due weeks apart both have 2026-09-25 and the Week 7 task has
2026-09-07. **Fix**: a deadline becomes a date only if the text holds a real calendar date (ISO, "April 14", "14 April",
"5/12/2026") or a relative word (today / tomorrow / next Monday / EOW / EOM). Plan positions ("Week 2", "Sprint 4", "Phase 2",
"Q2") and durations ("in 3 days") keep their ORIGINAL wording; a real date beside a plan reference wins ("Week 6, May 12,
2026" -> 2026-05-12, and the fuzzy parse now starts at the date so the "6" cannot leak into it). **Rejected: computing "Week N"
from a kickoff date** - the SOW rarely states one, so it would be a guess; keeping the wording is honest and can be upgraded
later. The deadline column is text and already held phrases such as "early next week".
Trade-offs / my defaults: a bare "by 15th" and a month-and-year ("April 2026") also keep their wording; an explicit date
now wins over a relative word ("next Monday, May 4" -> May 4); relative words are still resolved against the day the
document is PROCESSED, not the meeting date (unchanged, still open).

**2. Abbreviations (`apps/utils/abbreviations.py`).** Matching was case-insensitive for every entry, so the ordinary
words "was" and "be" became "WebSphere Application Server" and "Backend" ("the test was completed" -> "the test WebSphere
Application Server completed"); "Dr. Smith" would become "Disaster Recovery Smith". No stored task was affected yet.
**Fix**: WAS, BE, FE, HA, DR, LB, IDE and SLA (entries that are ordinary words or titles in lower case) expand only when
written exactly in upper case; everything else stays case-insensitive because people do type "k8s", "poc", "mvp".
Trade-off: a lower-case "ha cluster" no longer expands to High Availability.

**3. Blocker events (`apps/nodes/format.py`, `apply_task_updates`).** A "blocker" event only exists when the document gave
no status (match.py's `infer_event_type` checks status first), yet the code wrote the event's (empty) status into the
task, blanking it. Stored evidence: `forloop` "Review VPN access resolution" has a blank status next to its blocker text.
**Fix**: set the status to "blocked" when the event has none (a status the event does state is kept). This follows the
code's own comment ("mark task status as blocked") and the dashboard's existing rule that a blocker means blocked. **My
default**: the alternative was to leave the status untouched.

**Tests added**: `tests/unit/test_deadline_resolution.py` (43), `tests/unit/test_abbreviations.py` (13),
`tests/db/test_blocker_update.py` (2). **Not done**: repairing the already-stored `forloop` rows (the user's call); the
other open points listed in the walkthrough document (Planning's deadline is not stored, Sync / Reporting only creates Jira
issues and never updates them, a document that yields no tasks is not saved).

---

## Finishing RAID: Excel export + AI "Suggest from documents" (2026-10-26)

Part of "let's finish building RACI/RAID". Still LOCAL and UNCOMMITTED. Items marked **(my default)** are mine, for review.

**1. Excel export (done).** `GET /projects/{id}/registers/export` -> one .xlsx: Summary, RAID log, Deliverables,
"RACI - Deliverables", "RACI - Tasks". Confirmed items only (suggestions not yet reviewed are counted on the Summary
sheet, not listed). Cell text that starts with `= + - @` is forced to plain text (formula-injection guard); "(R)" marks an
*inferred* Responsible (the task owner). Button "Export to Excel" next to the project selector. 8 tests.

**2. AI RAID suggestions (done, experimental).** Button "Suggest from documents (experimental)" ->
`POST /projects/{id}/raid/suggest`. It reads only the project's stored documents it has not read yet
(`source_documents.raid_scanned_at`; `force` re-reads all), one LLM call per document, and saves results as `suggested`
(origin `agent`) with a verbatim quote as evidence. It only PROPOSES - nothing joins the log until a person accepts.
Rules enforced in code, not just asked of the model: a quote that is not really in the document is dropped; probability
and impact are kept only when that verified quote backs them, otherwise blank (the earlier decision: the assistant does
not estimate them); items that restate an existing one of the SAME type, in ANY state including *rejected*, are skipped
(so a rejection is remembered); a document the model failed on is reported and stays unscanned so the next click retries.
10 tests with a scripted LLM.

**Bug found by the eval, not by tests**: models wrap quotes in `"..."` and mark cuts with `...`; the first version
treated every such quote as invented (0 of 4 verified). Fixed by stripping wrapper quotes/ellipses and requiring each
remaining stretch to appear verbatim; a made-up quote still fails (tested).

**Measured (eval/nodes/eval_raid_suggest.py; ONE synthetic SOW; real LLM calls).** Sections 7 (assumptions) and 8
(dependencies) removed from the SOW; the 9 + 6 items in them are the key.
- gpt-4o-mini (the app default): 4-9 items, 4 of 9 quotes verified, pooled recall 1/15 by the scorer.
- gpt-4o: 5-8 items, erratic (found 1 assumption). gpt-4.1: 15-16 items, 15 of 15 quotes verified, steady across runs.
- **The scorer undercounts.** compare.py's 0.6 title-similarity cutoff misses same-meaning pairs because SOW sentences are
  long (scored 3/15 pooled). Reading each key item next to its closest extraction, ~6/15 were recovered in meaning
  (API credentials, production environment, CSV datasets). The other ~9 ("Priya 20 h/week", "Stat Key API format will not
  change", "third-party libraries are open-source", ...) are stated ONLY in the removed sections, so no extractor could
  recover them: treat ~40% as a ceiling for this test, not a failure rate. Assumption vs dependency is also a judgment
  call even for people ("NovaTech will provide credentials" is both).
- On the full project (9 documents: SOW + 8 meetings) gpt-4.1 returned 80 suggestions with verbatim evidence; all 15 SOW
  items from sections 7/8 appeared. Meetings gave real risks and issues (e.g. whitelist-approval delay, cache-key bug,
  pie-chart label overlap). Risks and issues have NO answer key, so their precision is not measured.
- **Known weaknesses (seen by reading the 80):** ~15-20 are really action items ("send Priya the endpoint list by April 2")
  filed as dependencies/assumptions; the same fact appears under two types or in several meetings (dedupe is per type and
  cuts only near-restatements); one "risk" quoted "Not a risk exactly, more of a watch item"; 80 in one review queue is a
  heavy chore. A tightened "action items are tasks" rule moved dependencies 30 -> 24 and action-like titles 4 -> 3 on the
  meetings: a small effect, so the review step is the real guard, not the prompt.

**Choices (my default):**
- Model: `RAID_AI_MODEL` env var, **defaulting to gpt-4.1 in docker-compose.yml** (set it empty to fall back to the app-wide
  LLM_MODEL). Chosen from the numbers above; only this call uses it. It costs more per document than gpt-4o-mini.
- Same-item cutoff `SAME_RAID_TITLE_MIN_SCORE = 0.65`: calibrated on those 15 items - distinct items score up to 0.53
  against each other, the same item reworded 0.54-0.74. 0.65 sits above every distinct pair, so it hides only near-restatements;
  a looser paraphrase simply appears for a person to reject (the safer direction). Limited to one document.
- The four RAID definitions in `apps/utils/raid_ai.py` are written by Claude; the user's own wording is still wanted
  (same open question as the deliverable definition).
- Synchronous request: a project with 9 documents takes about a minute and a half with no progress bar.

**Not done / open:** RACI role proposals from the text (A/C/I cues), the status report/snapshot, the Governance advisor,
a way to review 80 suggestions faster (accept-all per type? filter by document?), running the extraction in the pipeline
instead of on a click. The eval project `eval-vmware-sim` now holds 80 suggested items from the UI test.

---

## Deliverable-level RACI: investigation, scope NOT yet decided (2026-10-20)

**Question**: RACI is per task today; PMs expect it per deliverable. Can deliverables be discovered automatically?

**Finding 1 - correcting a first impression.** The synthetic SOW (`sow.txt`, the one the golden data is built from)
has a clean numbered "4. DELIVERABLES" section: 11 items (4.1-4.11), each with an explicit Owner (some two) and
Deadline, cited by number in its dependency section (8.4-8.6) and 21 times across the meeting minutes. A first
assessment generalised from that one file and called discovery "the easy part". **That was wrong**: this dataset is
scripted/synthetic (the user has pointed this out before for the matching evals too), and it is the only one with
that structure.

**Finding 2 - the other SOW-style inputs** (`datasets/inputs/input-sow-1..4`, `input-sow-forloop`): none has a
numbered deliverables section. The word "deliverable" appears 0x in the forloop SOW (the closest to a real client
SOW) and 1-3x elsewhere, only in boilerplate. The forloop SOW describes work as 3 phases with 17 bullets of the form
"<Person> will <do X>" - owner inside the sentence, deadlines relative ("end of Week 2") or absent. Stable numbers
like "4.6" mostly do not exist, so later documents would have to match deliverables by name.

**Finding 3 - experiment (read-only LLM call, gpt-4o-mini, forloop SOW).** Asked "what a project manager would
track as deliverables" it returned 13 items (including activities such as "End-to-End QA Testing" and "UAT
Coordination", and omitting most of Phase 1: the ETL pipeline, CRM sync, data schema, VPN); asked for "only tangible
outputs the client receives or signs off on" it returned 3 (Data Mapping Document, the Dashboard, Training Session and
User Guide) and invented the client as the owner. Same document, a one-line wording change, 3 vs 13 items: what counts
as a deliverable is a judgment, not an extraction fact.

**Consequence**: AI discovery of deliverables is NOT the easy part and cannot be trusted without a definition and a
hand-labeled evaluation set. The sensible shape is **manual-first**, like Registers v1: a deliverables register
(number/name, owner(s), deadline, status), RACI rows by deliverable (per-task view kept as a secondary toggle; no
real data uses task RACI yet - 0 rows - so nothing to migrate), and a practical way to create deliverables from what
already exists, e.g. **promote an extracted task to a deliverable** (copies title/owner/deadline). A deterministic parse
of a numbered DELIVERABLES section stays a cheap bonus for the rare SOW that has one. AI "suggest deliverables" comes
later, behind a review step, once there is (a) a written definition of "deliverable" for this product and (b) a
hand-labeled real-style SOW (the forloop SOW would take a person about ten minutes) to measure against.

**Open**: the user's definition of a deliverable (tangible outputs only? named features/views? phases? milestones?);
whether to build the manual-first register now. Rough size if built manual-first: a third to a half of Registers v1.

---

## Registers copy fix + open question: should Deliverables be its own tab? (2026-10-20)

**Bug reported by the user**: the Deliverables tab always said "These are the rows of the RACI matrix", yet in a project
with no deliverables that tab is empty while the RACI tab shows rows. Cause: with no confirmed deliverables the RACI tab
deliberately falls back to the Tasks view, so the claim was false in exactly that state. **Fixed**: the Deliverables tab now
says "Each one is a row in the RACI matrix (Deliverables view)" only when deliverables exist, and otherwise "Until you add
some, the RACI matrix shows your tasks instead"; the RACI tab, when showing tasks because there are no deliverables, says so
and offers an "Add deliverables" link. Verified in the browser in both states.

**Open question (user asked "why is there a new tab for deliverables?")**: the third tab was part of the plan agreed before the
register was built, but it was not discussed as a layout choice. Reasons for a separate tab: a deliverable is a register in its
own right (number, owner, deadline, status, task count, a review queue for AI suggestions, task assignment); keeping it apart
leaves the RACI tab a pure matrix. Alternatives not chosen yet: fold it into the RACI tab (a "Manage deliverables" panel above
the matrix); or put it in Workspace next to tasks, since assigning tasks to deliverables happens there too. Waiting for the
user's preference.

---

## Four follow-ups to the deliverables register: SOW RAID import, similarity hint, task assignment, AI suggestions (2026-10-20)

**Status**: all four built, tested (125 pytest tests) and the two AI-assisted ones measured with new evals. Built in one go
so they can be reviewed together; none is committed yet. **Every default marked "(my default)" below is awaiting the
user's review.**

**1. RAID items from a SOW's numbered Assumptions / Dependencies lists** (`apps/utils/sow_sections.py`; the pipeline step
is now `sow_registers`, replacing `deliverables`, and also does the deliverables parse). Deterministic, no LLM. Results on
the real files: synthetic SOW -> 9 assumptions + 6 dependencies; `input-sow-3` -> its 9 numbered assumptions (stops before
its "Out of Scope" list); `input-sow-1` (bulleted PDF text), `-2` (PDF extraction with numbers split from their text), `-4`
and forloop -> nothing, never a guess. Imported items are explicit statements in the document, so they join the log as
**confirmed**, origin `document`, with a per-document key (`source_ref`) making re-runs idempotent while a different
document's "7.1" stays separate. Title = first sentence (<=110 chars), full text in the description. A real `/run` of the
synthetic SOW created all 15 and the 11 deliverables. Limit: only clean numbered lists; messy PDF layouts would need an LLM
pass (not built).

**2. "Similar to ..." hint when promoting a task to a deliverable.** Calibrated on a real run (35 tasks vs 11 deliverables):
the 6 true restatements scored 0.71-0.85, the next score down was 0.66 -> `SIMILAR_DELIVERABLE_MIN_SCORE = 0.70`. But
related sub-tasks ("Conduct smoke test post-deployment" ~ 4.8, 0.83; "Review and approve deployment runbook" ~ 4.9, 0.77)
score as high as true restatements - the same limit as embedding-only task matching - so it is a **hint a person judges,
never a block or a duplicate verdict**. Distinct deliverable titles never exceed 0.56 against each other, which sets the
"same thing reworded" cutoff used when de-duplicating AI suggestions - **corrected after browser testing**: that was first set to
0.75 from an *assumed* ~0.9 for rewordings and let two restated deliverables through; measured, the same deliverable with vs
without its "(codebase + unit tests)" suffix scores 0.74-1.00 (distinct ones <= 0.56), so the cutoff is now **0.65**, in the gap.

**3. Assign tasks to deliverables** (`tasks.deliverable_id`, `PUT /tasks/{id}/deliverable`, bulk assign, proposals). A task
citing exactly one known deliverable number ("(Deliverable 4.6)") is assigned deterministically; the rest go to the LLM in
batches of 50, which may answer "none" ("a wrong assignment is worse than none"). Proposals are NEVER applied silently:
a review panel (Registers -> Deliverables -> Assign tasks) shows them with a per-row deliverable dropdown, and only
**high-confidence ones are pre-selected**. Promoting a task also assigns it to the deliverable it created. Workspace list
has a Deliverable column (dropdown) and board cards a number chip; the register shows a task count per deliverable.
**Measured** (`eval/nodes/eval_task_assignment.py`; seeded project, golden SOW hierarchy as the answer key: 11 deliverables,
72 subtasks + the 11 titles restated as tasks): the 11 restated titles 11/11; subtasks: assigned 60/72 (83%), correct
among assigned 47/60 (78%), overall correct 47/72 (65%). **Confidence is a useful signal: high was right 54 of 61 times
(89%), medium only 4 of 10 (40%)** - hence the pre-selection rule. Many "errors" are topically ambiguous (the golden file
puts "Implement VMware Aria API authentication" under 4.1 while 4.3 is literally "VMware Aria Operations API Integration";
smoke-test tasks went to the module they test instead of 4.8). Caveats: the golden subtasks are clean human-written lines,
not the pipeline's mixed-granularity tasks; one document.

**4. AI "suggest deliverables" from the project's latest SOW** (`POST /projects/{id}/deliverables/suggest`; button labeled
**experimental**). Suggestions are stored as `review_state = suggested`, origin `agent`: they are not real deliverables and
not RACI rows until a person accepts them; ones that restate an existing deliverable - in any state, including a rejected
one - are not re-proposed. Each suggestion's "evidence" is kept ONLY if it is a verbatim quote from the SOW (an invented
quote is dropped and the UI says "no supporting quote"). **(my default) the definition of "deliverable"** is a
Claude-written sentence in `deliverable_ai.DELIVERABLE_DEFINITION` (a named, tangible output the client receives or signs
off: documents/reports, working modules/features/views, the deployed system, a training session; not internal activities or
single build steps) - **it needs replacing with the user's own**; the API accepts an override for experiments.
**Measured** (`eval/nodes/eval_deliverable_suggest.py`; synthetic SOW with section 4 REMOVED, its 11 items as the key,
matched by title similarity): recall is poor - **4/11 (36%) with the first prompt**; adding a generic "go section by
section, list every distinct output, prefer including" instruction (tuned on this one keyed document, so optimistic) gave
**6/11 (55%), precision ~60%**, stable over two runs, still missing 5 (Aria API integration, multi-cluster aggregation,
Integration Testing Report, UAT Report, production deployment + smoke tests; two of those are never named outside the
removed section, so the ceiling is below 11). The three definitions (default/strict/broad) scored about the same, so on this
test the definition is not the limiting factor - recall is. On the forloop SOW the output is unstable: the non-exhaustive
variant gave 9 suggestions in one run and 3 in the next. With the default prompt forloop gets 3 (Data Mapping Document,
Customer Insights Dashboard, Training Session and User Guide - all with verified quotes). Conclusion: usable as a
review-gated starting point, not something to trust; hence "experimental".

**Open / for the review**: the user's definition of a deliverable; whether assignments should feed RACI (e.g. an implied
Responsible from the assigned tasks' owners when a deliverable has no owner); whether the board should group by deliverable;
dependencies between deliverables (the synthetic SOW's section 8 states some); an LLM pass for assumptions in messy PDF-style
SOWs; the task-assignment and suggestion evals each cover ONE synthetic document, so neither number should be read as a
general accuracy.

---

## Deliverables register BUILT (manual-first) + RACI by deliverable (2026-10-20)

**Status**: built and tested (97 pytest tests, 21 new for this; a real end-to-end pipeline run also verified). Follows
the investigation entry below: AI discovery of deliverables is deliberately NOT built; the register is manual-first.

**What exists**
- **`deliverables` table** (number, title, owner(s), deadline as free text, status, origin, source task) and
  `deliverable_raci`. The status vocabulary is the same as tasks (not started / in progress / completed / blocked /
  on hold). A deliverable number is unique per project; a task can be promoted only once.
- **Three ways to create one** (Registers -> Deliverables tab): (1) **by hand**; (2) **Add from tasks** - pick the tasks
  that are really deliverables out of those already extracted; title, owner, deadline and status are copied and the task
  stays a task (this is the practical path for SOWs like the forloop one that never say "deliverable"); (3) **from a
  SOW's numbered DELIVERABLES section**, automatically.
- **The numbered-section parse** (`apps/utils/deliverables.py` + a new pipeline step `deliverables`, after `format`):
  deterministic, no LLM, runs only for SOWs, idempotent on re-runs (never overwrites a person's edits), and wrapped so it
  can never fail a run. Checked against the real files: the synthetic SOW gives its 11 deliverables (owners with role
  descriptions stripped, "A + B" split into two owners); all five real-style SOWs give none (no invented items). A real
  `/run` of the synthetic SOW created the 11 and a second run did not duplicate them.
- **RACI by deliverable**: the RACI tab now has a Deliverables | Tasks toggle (deliverables by default once a project
  has any, tasks otherwise). The matrix code was generalised so both subjects share one implementation (implied R from
  the owner(s), the same warnings); the API response is now `{people, rows[{subject_id, number, title, ...}]}` and
  `GET /projects/{id}/raci?subject=deliverable|task`. Nothing needed migrating (0 RACI rows existed).
- Deliverables are deleted with their project; the shared inline-edit cell was extracted to `TextCell.tsx`.

**Not built (by decision)**: AI "suggest deliverables" (needs the user's written definition of a deliverable and a
hand-labeled real-style SOW to evaluate against); assigning tasks to a deliverable (the deliverables list is the
prerequisite and nothing built here blocks it); dependencies between deliverables (the synthetic SOW's section 8 states
some); parsing the SOW's numbered Assumptions (7.x) and Dependencies (8.x) into RAID items - a natural follow-up, since
the same deterministic approach works for that document.

**Observed in browser testing (open)**: promoting a task can create a near-duplicate of a deliverable that already came
from the SOW (e.g. the task "Build Data Source Integration Module" next to deliverable 4.1 "Data Source Integration
Module (codebase + unit tests)"). There is no duplicate warning yet; the match machinery (embeddings + gate) is the
obvious tool when that is wanted.

**Known limit**: the parser only understands dotted numbers (4.1, 4.2) under a heading literally called "Deliverables";
other layouts simply yield nothing and the person adds them by hand or from tasks.

---

## Probability and impact: AI-suggested risks start BLANK (2026-10-20)

**Question (user)**: probability and impact are not measured anywhere - how would the agent suggest them?
**Honest answer**: it can't measure them; it can only estimate, and an LLM's "high probability" is poorly calibrated
and looks more precise than it is. Nothing in the system measures them today (manual fields only).

**Decision (user chose option 1)**: when the extraction step proposes a risk it fills in type, title, owner and the
quoted source sentence, and sets probability/impact ONLY when the document itself states them ("high risk", "could
delay go-live by two weeks") - recording the quote as evidence. Otherwise both stay empty for a person to fill.
Empty is a valid, honest state; no guessing.

**Later options (not built, not decided)**
- *Evidence-based estimates*: once risks link to tasks, the Governance advisor can propose levels backed by numbers
  the system really has - downstream tasks blocked (`task_dependencies`), priority and deadline proximity of the
  affected tasks (impact); deadlines already moved (deadline-change events), stalled/blocked status, owner workload
  (probability) - shown as "suggested" with the evidence ("blocks 4 tasks, due in 9 days"), never as a measurement.
- *Checklist instead of a guess*: a few yes/no factors (on the critical path? deadline under two weeks? blocks other
  work?) feeding a score computed in code - more transparent than an LLM's feeling.
- *Calibration from outcomes*: the "It happened" action (promote to Issue) versus closing a risk records whether it
  really occurred, so over time the hit rate per level can be measured and the estimates corrected.
All of the evidence-based options need risks linked to tasks (the traceability question, still open), which does not
exist yet - which is why blank is the honest default until then.

---

## RAID: "materialized" dropped - a risk that happens is promoted to an Issue; status colors (2026-10-20)

**Question (user)**: what is the difference between Closed and Materialized? **Answer**: Closed = nothing left to
track; Materialized = the risk actually happened and still needs handling (it turns into an Issue). It only made
sense for risks, yet the dropdown offered it on all four types.

**Decision (user chose option 2)**: drop `materialized`. Statuses are now **open / mitigating / closed** for every
item type. When a risk happens, a person clicks **"It happened"** on the risk (with a confirm): the system creates an
**Issue** from it (same title, description, owner and impact; starts open; no probability, since it already
happened) and **closes the risk, linked to the new issue** (`raid_items.promoted_to`). In the table the closed risk
reads "Happened - became an issue" and the issue reads "Promoted from a risk that happened". Rules: only a confirmed
risk can be promoted, and only once; the button is hidden on closed risks (a retired risk is reopened first). Endpoint `POST /raid/{id}/promote-to-issue`, one transaction.
This answers the earlier open question about "materialized -> issue" auto-creation: it is an explicit human step, not
automatic.

**Migration**: tables created with the old CHECK are migrated at startup (`ensure_registers_schema`): any
`materialized` row becomes `closed`, the old constraint is replaced; idempotent, covered by a test that recreates the
old state. The live database was migrated and verified.

**Status colors** (user request): **open = orange, mitigating = yellow, closed = green**, applied to each row's
status dropdown. Implemented as theme tokens in `globals.css` (`--status-open-*`, `--status-mitigating-*`, with
separate light/dark values; closed reuses the existing success tokens), not hardcoded colors. Red is not used for a
status: it stays the color of the Issue type chip, so the two never compete. Tests: 76 passing (4 new).

---

## INCIDENT: unpinned dependencies broke every tool-calling LLM path after a rebuild (2026-10-19 to 2026-10-20)

**What happened**: `docker compose up -d --build frontend` (run on 2026-10-19 to see a UI change) also rebuilt the
`api` and `mcp` images, because compose builds a service's dependencies too. `requirements.txt` had 16 unpinned
lines, so the rebuild pulled `litellm 1.106.0` alongside `mcp 1.30.0`; litellm 1.106.0 imports
`mcp.types.CacheableResult`, which `mcp 1.30.0` does not have. Result: ANY LLM call that passes `tools` raised an
`ImportError` - the AI Chat, and the planning, sync-reporting and meeting-coordinator agents. Calls without tools
(the match gate, extraction) were unaffected, which is why tests, evals and the UI work I ran afterwards did not
reveal it. Found on 2026-10-20 when the Chat returned a 500 while verifying the Extractor/Workspace rename.

**Impact**: about 28 hours. Checked the logs: no `POST /run` happened in that window, so no job failed and no data
was lost; the only affected feature was the AI Chat.

**Fix**: tested litellm 1.98.1 - 1.105.1 against `mcp 1.30.0` in throwaway containers with real tool-calling
requests; all work, only 1.106.0 breaks. Pinned `litellm==1.105.1` and pinned every other unpinned line to the
version running at the time (`mcp[cli]==1.30.0`, `langchain-mcp-adapters==0.3.0`, ... - `requirements.txt` now has
no unpinned entries). Rebuilt the `api` image from the pinned file, recreated the container (not hot-patched),
verified the Chat's tool path, an end-to-end document run (3 tasks, 5 planning-agent tool calls) and all tests.

**Lessons**: (1) never leave runtime dependencies unpinned - a rebuild must not change behaviour; (2) rebuild a
single service with `docker compose up -d --build --no-deps <service>` (the frontend-only rebuilds after this one
used it) - without `--no-deps` compose rebuilds and recreates dependencies too; (3) the test suite mocks the LLM and
the evals avoid `tools`, so nothing automated exercises the real tool-calling path - an offline guard is now in
`tests/unit/test_litellm_tool_calling.py` (litellm's `mock_response` runs the library's tools branch with no network);
verified to PASS on the pinned 1.105.1 and FAIL with the exact `CacheableResult` ImportError on 1.106.0.

---

## Registers v1 BUILT: manual-first RAID log + RACI matrix (2026-10-20)

**Status**: built, tested and checked in the real browser (72 pytest tests pass, 14 new for registers; tab state, accept/reject, add, edit, delete, RACI cell edits and persistence across a reload all verified); shown in the sidebar as **Registers**
(`/products/registers`, tabs RAID log | RACI matrix, URL `?tab=raci`). The AI side (extraction node, Governance
advisor agent, Excel sheets, snapshot reports) is NOT built - the design entry below still applies to it.

**What exists**
- **RAID log**: `raid_items` table (type risk/assumption/issue/dependency, title, owner, status, probability, impact,
  review date, `review_state` suggested/confirmed/rejected, `origin` manual/agent). `GET/POST /projects/{id}/raid`,
  `PATCH/DELETE /raid/{id}`. UI: type filter chips with counts, add form, inline-editable table (status,
  probability, impact, review date, owner, title), delete with confirm, "Show closed" toggle. An amber "suggested by
  the assistant" review queue (Accept / Reject) appears when suggested items exist; rejected items are hidden, not
  deleted (so a future extractor can avoid re-proposing them). The tab badge counts suggested items.
- **RACI matrix**: `task_raci` table (task, person, role; one person may hold several roles, e.g. A/R).
  `GET /projects/{id}/raci`, `PUT /tasks/{id}/raci`. UI: tasks x people grid, click a cell to toggle R/A/C/I, a
  Check column with warnings, search, "only rows needing attention". People columns come from the Workspace People
  roster (plus owners and assigned people), so people are managed in one place.
- Registers are deleted with their project; `ensure_registers_schema()` self-provisions at startup like the other
  migrations.

**CONFIRMED with the user (decided; not re-opened)**: Registers is its own sidebar page with RAID | RACI tabs; UI is
the source of truth and Excel export / snapshot reports come later (no import); new first-class entities rather than
task columns; AI proposals arrive as "suggested" and a person confirms; extraction will be a node after `format` plus
one "Governance advisor" agent (no separate RAID and RACI agents); build order RAID -> RACI -> reports; sidebar
names Dashboard | Extractor | Workspace | Registers.

**DEFAULTS I CHOSE for v1 (not discussed - change freely)**
- Statuses: open / mitigating / closed (was four with `materialized` - see the entry above). Probability and impact: low / medium / high; no numeric risk
  score or heat map. Closed items are hidden unless "Show closed" is ticked.
- RACI is per TASK (existing tasks are the rows), not per deliverable.
- The task owner counts as an *implied* Responsible (shown lighter, italic) until someone is given a role on that
  task: a person with ANY explicit role is no longer guessed at (found in browser testing - an explicit "C" used to
  leave the implied R alongside it). An owner like "Jordan Mills, Priya Nair" or "A and B" is split into people.
- Warnings fire only on rows someone has started (otherwise every untouched task would be flagged): "More than one
  Accountable", "Nobody Responsible", "No Accountable yet". Only the first two are definite errors.
- No task/meeting/source-document links on items, no change history, no export yet.

**NEEDS DISCUSSION (open)**
1. **What "PMP" should mean** - PMBOK-aligned artifacts, a PM-knowledge assistant, or both (PMBOK is copyrighted).
2. **RACI granularity** - per task, or per deliverable (the textbook way)? Should every task need an Accountable?
   (That is why "No Accountable yet" is only a soft warning on started rows.)
3. **Risk scales** - keep 3 levels, or 1-5 with an exposure score / heat map? Different wording for statuses?
4. **Derived vs manual** - should blocked tasks automatically appear as Issues and task dependencies as Dependencies,
   or stay manual? (A risk that happens is already handled: an explicit "It happened" promotion to an Issue.)
5. **Permissions** - who may edit and who may confirm AI suggestions (ties into the RBAC design).
6. **Audience / export** - do sponsors or the client read these outside the tool? Decides Excel sheet layout and when
   snapshot status reports are built.
7. **AI extraction** - when it runs, what counts as a risk vs an assumption (labeling guidelines), how it is
   evaluated (precision first: an invented risk is worse than a missed one), cost per document.
8. **Traceability** - link items to tasks, meetings and the source sentence in the document?
9. **History** - who changed a status and when (audit trail), needed?
10. **Dashboard** - an "open high risks" summary across projects?

---

## Sidebar renamed: Extractor | Workspace (Registers to follow) (2026-10-20)

**Why**: "Task Manager" no longer described the page (it now holds Tasks, Meetings and People), and "Task
Extractor" will outgrow "Task" once it also extracts meetings, people and RAID/RACI items.

**Decision (agreed with the user)**: the Products section reads **Dashboard | Extractor | Workspace | Registers**.
- **Task Manager -> "Workspace"**, not bare "Manager": "Manager" alone is vague and clashes with the product
  name ("Agentic Project Manager"); "Workspace" says what it is (one project's tasks, meetings, people) and still
  fits if more tabs are added.
- **Task Extractor -> "Extractor"**: short, and already the route name. Names say what a person does, not how it
  works; the page subtitle ("Turn an SOW into a plan, then keep it current with meeting minutes") carries the
  detail. "Document Intake" was considered as more descriptive and not chosen.
- **"Registers"** (RAID | RACI, see the design entry below) joins the sidebar when that page is built - a link to a
  page that does not exist would be a dead end, so it is NOT in the sidebar yet.

**What changed (labels only)**: sidebar, page titles, the Workspace subtitle ("Tasks, meetings and people for one
project at a time."), button/empty-state text ("Open in Workspace", "submit an SOW in Extractor"), Settings and
Docs/Integrations wording, a docstring in `api.py`, and the AI Chat's own instructions (`manifests/chat.md`), so the
assistant points users to "the Workspace page" and "the Extractor" instead of the old names.

**Deliberately not changed**: the URL stays `/products/task-manager` (renaming it would break saved links and the
saved default project/view; add a redirect if it is ever renamed); internal component/function names
(`TaskManagerPage`); backend comments that use "task-manager project" generically; and the older entries in this
log, which keep the names that were current when they were written.

---

## RAID log, RACI matrix and "PMP": design only, NOT built (2026-10-20)

**Status**: discussed and designed with the user; nothing implemented. Written down so it can be built later
without re-deriving it, in the same spirit as the RBAC entry. Direction from the user: the system should grow
from managing tasks and meetings into a broader AI assistant for project managers.

**What the two artifacts are, and what the system already has**
- **RAID** (Risks, Assumptions, Issues, Dependencies). Partly present already: dependencies live in
  `task_dependencies`, blockers (`tasks.blocker`) are effectively issues. Risks and assumptions are exactly the
  statements the pipeline discards today - the golden data's "should not be picked" sections are full of them
  ("whitelist expected by April 17", "tokens expire after thirty minutes", API-limit discussion).
- **RACI** (Responsible, Accountable, Consulted, Informed). `tasks.owner` roughly gives R. A, C and I are rarely
  stated explicitly; they come from cues ("Marcus approves", "keep Sarah informed", review/sign-off wording) and
  mostly need a person to confirm. RACI is normally per deliverable, not per low-level task.

**Decisions**
1. **Where it lives in the UI: a new sidebar page, "Project Registers", with tabs RAID | RACI** - not more tabs in
   Task Manager. Reasons: Task Manager already became Tasks | Meetings | People; these are governance artifacts
   with a different audience (sponsor/PMO) and rhythm; later registers (stakeholders, change log, lessons learned)
   get a natural home. Reuses `Tabs.tsx`, the project selector and `?project=`. A small "open high risks" card on
   the Dashboard is a possible later summary, not the register itself. AI Chat should answer questions about both
   but is not where they live.
2. **UI first, files second.** They are living registers (change every meeting, need confirm/edit), so the UI over
   the database is the source of truth; Excel export is a read-only view of it (extra sheets on the existing
   `/projects/{id}/export`); **no import** (edits in an exported file would diverge from the system). "Reports"
   are point-in-time snapshots generated from the database on demand (e.g. weekly status report), built last.
3. **Data model: new first-class entities, not new task columns.** `raid_items` (type, title, description, owner,
   status open/mitigating/closed/materialized, probability, impact, review date, source document + excerpt, linked
   task ids, origin agent|manual, review state suggested|confirmed|rejected). `task_raci` (deliverable or task,
   person, role R/A/C/I, source, review state). Dependencies and issues are **derived/linked** from
   `task_dependencies` and blockers rather than duplicated. A real `projects` table (name, sponsor, stakeholders,
   phase) is a needed foundation - `project_id` is only a string on rows today.
4. **Agents: extraction is a node, analysis is one new agent.**
   - Governance extraction = ONE structured LLM call per document (same shape as the `extract` node, no tool loop)
     that pulls candidate risks/assumptions/issues and role cues. Runs AFTER `format` so items can link to real
     task ids. Kept separate from the existing `extract` node on purpose: that node's job is tasks, and mixing in
     informational statements would hurt its precision.
   - De-duplication ("same risk mentioned again" = update, not a new row) reuses the match machinery (embedding
     candidates + LLM gate); it is the same problem already solved for tasks.
   - RACI is mostly derived: owner -> R in code, A/C/I from the extraction cues, then code validation (exactly one
     A, at least one R, no person missing from the roster).
   - ONE new conditional agent, a "Governance advisor" (ReAct with tools, triggered like `sync_reporting`), that
     cross-checks tasks, dependencies, blockers and the registers and proposes new items (a blocker -> issue, a
     slipping dependency -> risk, an unassigned A) and writes the status report.
   - **Rejected: separate RAID and RACI agents** - same inputs and tools, so splitting only duplicates prompts.
   - Tools follow the existing entity-mapped principle (get/upsert raid items with filters, get/set raci), not
     one tool per question.
5. **Human in the loop for everything AI-proposed.** Items land as "suggested" until a person confirms, edits or
   rejects them (same pattern as possible duplicates); each decision is recorded for later training/evaluation. An
   invented risk is worse than a missed one, so precision matters more than recall here.
6. **Evaluation plan**: a node-level eval for governance extraction in the style of the match evals (fixed state,
   target-correct scoring). The golden "should not be picked" statements are a starting pool for labels but need
   hand-labeling as risk / assumption / issue / not-governance; measure invented items (precision) first.
7. **Build order**: (1) RAID log, (2) RACI, (3) PMBOK-style reports and registers generated from data we already
   hold (status report, stakeholder register, change log, lessons learned). RAID first because the data is already
   flowing and it reuses blockers and dependencies.

**Open / not decided**
- **What "PMP" should mean.** Two readings: (a) make the system's artifacts PMBOK-aligned (RAID, RACI, stakeholder
  register, change log, status reports, lessons learned); (b) a PM-knowledge assistant in Chat. Caveat for (b): the
  PMBOK Guide is copyrighted, so it cannot be ingested; options are the model's general PM knowledge or content the
  user licenses. Waiting on the user's intent.
- **Who reads these outside the tool** (sponsors, the client)? If they do, Excel export and snapshot reports move
  up the order.
- Probability/impact scales and the risk status workflow (open -> mitigating -> closed, or materialized -> issue).
- RACI granularity (deliverable vs task) and how deliverables are identified (the SOW's numbered deliverables are
  the obvious source).
- Who may confirm items - tie into the RBAC design (project_members roles) when that is built.

**Related**: possible-duplicate review + `duplicate_decisions` (the confirm-and-record pattern), the match gate (dedup
of repeated items), the RBAC design (who confirms), the node-eval approach (how this is tested).

---

## Pending meetings: passive "needs attention" notice instead of an automatic pop-up (2026-10-20)

**Problem (user feedback)**: opening Task Manager auto-opened the "Review Proposed Meeting" dialog whenever a
meeting was pending (originally the "pop up and ask for approval" step). It reappeared on every visit, including
for people who deliberately do not want to resolve attendee emails yet - nagging, and shown on tabs unrelated to
meetings.

**Change** (frontend only): removed the automatic dialog entirely. The review dialog now opens only when someone
clicks **Review** on a meeting. Pending meetings are surfaced where they belong, in the Meetings tab, without
interrupting anyone:
- an amber notice at the top of the Meetings tab ("N meeting(s) need your approval", "nothing is scheduled until
  you approve it... or leave it pending", plus how many attendees have no email on file);
- on the meeting card, which attendees couldn't be matched to an email, with an "add them in People" link that
  switches to the People tab;
- the Meetings tab badge (count of pending) and the card's "Pending approval" status are unchanged.
Leaving a meeting pending is a legitimate choice: nothing re-prompts, and nothing is created until approval.

**Verified in the real browser**: loading Task Manager (any tab) opens no dialog; the Meetings tab shows the notice
and the unresolved names; the People link works; Review opens the dialog only on click; Decide later leaves the
meeting pending with the notice intact.

---

## Task Manager split into tabs: Tasks | Meetings | People (2026-10-20)

**Why**: the page was one long scroll (stats, tasks, meetings, people). User asked for a tab bar so each
section is its own view.

**What changed** (frontend only, no backend change):
- New shared `components/Tabs.tsx` (accessible tablist, attention badges, scrolls sideways when narrow) - built
  generic so the planned Project Registers page (RAID | RACI) can reuse it.
- Active tab lives in the URL (`?tab=meetings|people`; Tasks is the default and omits the param), so refresh and
  shared links keep it, same pattern as `?project=`.
- **Tasks tab**: the stat cards, Export to Excel, Board/List toggle, and the task view. **Meetings tab**: the
  Schedule Meeting button and the list. **People tab**: the people panel.
- Project-level actions (Jira project key, Delete project) moved up beside the project selector so they show on
  every tab instead of belonging to the task toolbar. The Activity feed stays on the right of every tab.
- **Badges** (live, no reload): Tasks = possible duplicates to review, Meetings = meetings awaiting approval,
  People = people with no email on file. `PeoplePanel` got an optional `onPeopleChange` callback so its edits
  update the badge; the page keeps its own copies of meetings/people only for the badges.
- ~~The unprompted "review proposed meeting" popup is unchanged~~ **Superseded the same day**, see the next entry.

**Verified in the real browser** (demo project, since deleted): all three tabs render only their own content;
badges appear for seeded data and clear on resolving a duplicate (Keep both), a missing email, and rejecting a
meeting; reload keeps the tab; no console errors. Not done: the app's fixed sidebar makes the whole UI cramped at
phone width (pre-existing, not part of this change).

**Ops**: rebuilt only the frontend with `docker compose up -d --build --no-deps frontend`, so the API and database
containers were not recreated this time (unlike the earlier rebuild that restarted everything).

---

## Gate model comparison: stronger models did NOT beat gpt-4o-mini (2026-10-19)

**Question** (from a side-chat suggestion): would a stronger model make the gate's judgment calls better?
**Setup**: fixed-state eval, 3 repeats, same prompt, only the gate's model varied. New setting
`MATCH_GATE_MODEL` / `GATE_MODEL` in `match.py` (default unset = app-wide `LLM_MODEL`, i.e. gpt-4o-mini, no
behaviour change); `complete()` now omits `temperature` when passed `None` (reasoning models reject
temperature=0; default unchanged). Only an OpenAI key is configured, so Claude models were not tested. The eval
now reports gate items with no usable verdict per model: 0 for every model, so these are real judgments, not
broken calls.

| Gate model | Errors per repeat | Paraphrase | Specificity | Time for the 14 gate calls |
|---|---|---|---|---|
| **gpt-4o-mini (current)** | **3, 3, 3** | 14/15 | 64/66 | ~11s |
| gpt-4.1-mini | 4, 6, 5 | 14/15 | 61-63/66 | ~11s |
| gpt-4o | 5, 5, 6 | 13-14/15 | 62/66 | ~11s |
| gpt-4.1 | 7, 7, 7 | 14/15 | 60/66 | ~11s |
| gpt-5-mini (reasoning) | 7, 8, 8 | 14/15 | 59-60/66 | ~45s |
| gpt-5 (reasoning) | 7, 7, 8 | 14/15 | 59-60/66 | ~105s |

**Reading**: no model improved recall (the one remaining miss, "Production deployment and configuration" at
cosine 0.62, is below the candidate floor so no model ever sees its target - as expected), and every stronger
model made MORE wrong merges. The extra errors are lifecycle neighbours, e.g. "Finalize integration test plan"
-> "Review integration test plan", "Draft deployment runbook" -> "Deliver Deployment Runbook": the prompt says
the next lifecycle step of the same deliverable counts as "same", the golden labels treat each step as its own
task, and the stronger models follow the prompt's rule more literally than gpt-4o-mini does. So these look
like prompt-vs-label convention errors, not capability errors (hypothesis, not tested). Caveats: the prompt
was tuned on gpt-4o-mini only, ~100 scored items so 2-5 errors is a small margin, and golden labels are noisy.
Stronger models were also up to 10x slower and pricier for no gain. **Decision: keep gpt-4o-mini as the gate.**
**Possible follow-up**: test a gate prompt that does not treat lifecycle steps as the same task, across models.

---

## Duplicate handling: flag, merge or keep (2026-10-19)

**Problem**: the gate deliberately turns doubtful matches into new tasks (a duplicate beats a silent wrong
merge, per the user's decision), so users now see some duplicates. They need a way to resolve them.

**What was built** (backend + task-table UI, verified in the real browser):
- **Flagging** (`match.py`): a new task is flagged as a possible duplicate of the closest existing task when the
  gate said "unsure", or rejected a candidate whose cosine was >= 0.85 (`POSSIBLE_DUPLICATE_MIN_SCORE`) - the
  cases where a wrong rejection is most likely. Ordinary rejections are not flagged (would be noise: ~145
  rejections in one day of evals). `format.py` stores it in new columns `tasks.possible_duplicate_of` /
  `possible_duplicate_reason` (self-provisioned at startup like the other migrations).
- **Merge** (`POST /tasks/{id}/merge {into_task_id}`): one transaction; the existing (target) task keeps its own
  fields and only blanks (owner, deadline, blocker, Jira key) are filled from the new one; the new task's event
  history and dependency edges move to the target (edges between the two are dropped, not turned into
  self-loops); the new task is **soft-deleted** (`is_active = false`), nothing is destroyed. If both tasks
  already had a Jira issue, the other key is returned in the response - no Jira call is made.
- **Keep both** (`POST /tasks/{id}/not-duplicate`): clears the flag.
- **Every resolution is recorded** in new table `duplicate_decisions` (both task texts, merged/not_duplicate, why
  it was flagged) - clean human-confirmed same/different pairs, the labeled data a future fine-tune of the gate
  would need (the blocker noted in the open-source-model discussion). Deleted with the project.
- **UI**: in the List view each flagged row shows an amber "Possible duplicate of <task>" notice with Merge and
  Keep both buttons. A flag whose target has since been merged away disappears.

**Not done / choices**: the Board (kanban) view does not show the notice (List only); the overview stat cards
don't refresh after a merge until the page reloads; merge is one-directional (new into existing); the existing
`unresolved_events` table is still unused (write-only, no consumer). Tests: 12 new (58 total passing) covering
flagging rules, persistence, merge/dependency/Jira handling, validation, keep-both, and the HTTP statuses.

**Ops note**: seeing the UI needed a frontend image rebuild (`docker compose up -d --build frontend`), which also
recreated the api/mcp/postgres containers (~11 min build). The Postgres named volume was reused, data intact
(365 tasks before and after); the migration ran on startup.

---

## Match experiments on the fixed eval: candidate floor, containment candidates, golden cleanup (2026-10-19)

**Gate variance first**: the gate (gpt-4o-mini, temperature 0) is not perfectly deterministic - one item
("Test LLM graph spec quality with and without sample rows", 0.96 to its target) flipped miss/hit in 1 of 4
runs, and standalone the model got it right. Everything below was therefore run 3 times; results were stable
across repeats (differences of at most 1 error).

**1. Lower the candidate floor (0.65 -> 0.60 / 0.55 / 0.50): rejected.** It recovers 1 paraphrase (14/15 vs
13/15) but offering more weak candidates makes the gate approve wrong ones: specificity 62 / 60 / 56-57 of 68
vs 63-64, total errors 7 / 9 / 12-13 vs 6-7. `CANDIDATE_MIN_SCORE = 0.65` stays (now a named constant; it
replaces `SEMANTIC_THRESHOLD`, which was redundant with the old "low band discarded" rule).

**2. Containment candidates: adopted.** A task whose normalized text contains (or is contained in) the
mention's, shorter side >= 3 words, is offered to the gate as an extra candidate (max 2) regardless of
cosine - never as an automatic match, which was the flaw of the removed partial stage. Recovers "Fix all
four integration test defects" -> its long task (cosine 0.60, below the floor), with no specificity loss:
5-6 errors vs 6-7 on every repeat. `CONTAINMENT_CANDIDATES = True`. 4 new tests (46 total passing): offered
below the floor, never auto-matched, word guard, flag off = old behaviour.

**3. Golden cleanup, in the eval layer only (dataset files untouched)**: `match_targets.json` gained
`ambiguous_new_tasks` - two golden new tasks whose deliverable already exists in the golden state under a
near-identical name ("Deliverable 4.6" / "4.7" vs the SOW's Integration Testing Report / UAT Report), now
excluded as `ambiguous_label` with reasons. Deliberately NOT extended to look-alikes the matcher merely gets
wrong (that would be tuning labels to results); "Follow up on whitelist approval status and copy Sarah on
email" is a judgement call left in the scored set.

**Result, 3 repeats, scored items (9 of 111 excluded)**:

| Matcher | Exact-twin | Paraphrase | Wrong target | Missed | Specificity | Errors |
|---|---|---|---|---|---|---|
| gate off | 21/21 | 13/15 | 1 | 1 | 56/66 | 12 |
| gate, no containment candidates | 21/21 | 13/15 | 0 | 2 | 63-64/66 | 4-5 |
| **live: gate + containment candidates** | 21/21 | 14/15 | 0 | 1 | 63-64/66 | **3-4** |
| old 3-stage (reconstruction) | 21/21 | 15/15 | 0 | 0 | 54/66 | 12 |

Remaining: 1 miss ("Production deployment and configuration" -> "Execute Production Deployment and Smoke Test",
a pure paraphrase at 0.62 - lowering the floor is the only thing that surfaces it and that costs more than
it gains), and 2-3 false positives (e.g. "Finalize and send deployment runbook draft" -> "Deliver Deployment
Runbook"). **Not re-checked end to end** (3 averaged e2e runs ~ 1h, real LLM cost). Label review by the user
(`match_targets.json`, written by Claude) is still open.

---

## Match eval fixed: target-correct scoring (2026-10-07)

**Problems found**: (1) `eval_match.py` counted a should-match item as a hit if it matched ANY existing
task, so a wrong merge scored as a success - this inflated gate-off's end-to-end recall and made the
gate look like it lost ~10 recall points when ~4-6 were real. (2) The seeded eval had a second
flaw: 21 of its 36 scored update events are verbatim copies of a task already in the seeded state
(golden update events restate earlier tasks word for word), so their "recall" was just the exact
stage and said nothing about semantic matching or the gate. Only 15 are real paraphrases.

**Fix** (`eval/nodes/eval_match_seeded.py` + new `eval/nodes/match_targets.json`):
- An update event now must match the RIGHT task: its verbatim twin (identical normalized text,
  labeled automatically) or, for the 19 paraphrased ones, a hand-labeled target in
  `match_targets.json`. Matching another task is a separate outcome, `wrong_target`, counted as an
  error. An update event with neither a twin nor a label stops the run instead of being guessed.
- Recall is reported separately for exact-twin and paraphrase items; the `no_target` exclusion is now
  an explicit label (`targets: []`) instead of the old cosine < 0.55 heuristic.
- The labels are MY judgment from each item's top-6 cosine neighbours, not dataset-author ground
  truth - flagged in the file, open to the user's review. `eval_match.py` (end to end) cannot check
  targets (pipeline wording differs), so it now records `matched_pairs` and labels its recall an
  any-target upper bound; use the seeded eval to compare matchers.

**Result on the fixed state** (scored items; errors = missed + wrong-target + false positives):

| Matcher | Exact-twin | Paraphrase | Wrong target | Missed | Specificity | Errors |
|---|---|---|---|---|---|---|
| exact+semantic (gate off) | 21/21 | 13/15 | 1 | 1 | 56/68 | 14 |
| exact+semantic+LLM gate (live) | 21/21 | 12/15 | 0 | 3 | 64/68 | 7 |
| old 3-stage (reconstruction) | 21/21 | 15/15 | 0 | 0 | 54/68 | 14 |

**Reading**: the gate halves total errors, almost all through specificity (16 -> 4 wrong merges of
genuinely new tasks). The old 3-stage was best at paraphrased updates (15/15): many golden paraphrases
are a containment of the target ("Add file locking for report index JSON" inside "...using filelock
library"), which the removed partial stage catches - a real strength we gave up, offset by 14 false
positives. The one gate-off wrong target is exactly the failure the old metric hid ("Fix all four
integration test defects" -> "Regress all four integration test defect fixes"). Two of the gate's 3
misses are right targets scoring below the 0.65 candidate floor (0.60, 0.62) so they are never offered
to the gate; the third ("Test LLM graph spec quality with and without sample rows" vs "...and report
findings", 0.96) is a plain gate miss worth investigating.

---

## Gate v2: top-3 candidates + owner/status/deadline hints + "unsure" verdict (2026-10-05)

**Why**: user kept the gate (a wrong merge is worse than a missed update) and asked how to cut its
missed updates. Two causes found: the gate only ever saw the single closest candidate as two bare
strings (the right target is sometimes rank 2-3), and it had no way to say "can't tell".

**Changes** (`apps/nodes/match.py`, `apps/nodes/format.py`):
1. Embeddings now propose up to **3 candidates** per mention (same floor as before: >= 0.55 and not the
   "low" band) and the gate sees all of them, lettered, plus owner/status/deadline for the mention and
   each candidate (stated as hints only - owners legitimately change between meetings). It picks one
   candidate or none. Still ONE batched LLM call per run.
2. Verdicts are **same / different / unsure**. "unsure" and an invalid candidate letter both become a
   new task flagged `match_method = "llm_unsure"` (persisted in `task_events`, no schema change).
   No verdict at all (API/parse failure) is still plain new-task, as before.
3. **Found while implementing - the gate's "different" verdict was being silently overridden.**
   `format.py`'s store_tasks has a 0.85 semantic dedup guard (no LLM) meant for race conditions; any
   gate-rejected mention whose candidate scored >= 0.85 was re-merged there, i.e. the exact wrong
   merge the gate had just prevented. From today's logs: 22 of 145 gate rejections had a candidate
   >= 0.85, and 39 semantic dedups fired. Fix: the gate marks events it ruled on
   (`llm_adjudicated`) and the format guard skips them; the exact-text guard and un-adjudicated events
   are unchanged. This also means the earlier gate-on end-to-end numbers understated the gate's
   effect in the 0.85+ band.

**No UI/queue for "unsure" yet**: the existing `unresolved_events` table is write-only (no endpoint or
screen reads it) and means "no task created", so using it would silently drop work. Unsure mentions
become visible duplicates instead (consistent with the decision that wrong merges are worse), and are
queryable via `task_events.match_method = 'llm_unsure'`. The candidate's identity is only in the log
line, not persisted - a real review screen would need a column for it.

**Seeded eval, same fixed state, scored items**: gate v1 recall 33/36, specificity 62/68 (9 errors) ->
gate v2 34/36, 63/68 (7 errors). Gate-off unchanged at 13 errors (sanity check). The model returned
"unsure" 0 times on this set (prompt says use sparingly), so that path is covered by deterministic
tests, not by the eval.

**Tests**: `tests/db/test_match_gate.py` (8 tests, scripted LLM): unsure flag, picking candidate "b"
over the closest, owner hint present in the prompt, invalid letter -> unsure, LLM failure -> new task
and not adjudicated, format guard still merges when the gate did not rule, does not override a gate
rejection, unsure flag survives store_tasks. Full suite 42 passed.

**End-to-end result (3 parallel in-process runs)**: recall 17/40 and specificity 62/71 in all three runs -
identical to gate v1's recall (17/17/17) and within 1 of its specificity (63.3). No end-to-end gain is
visible. Semantic dedups inside format.py dropped from ~8 per run (v1) to ~2 (the override fix working).
Task counts at meeting 8: 136, 137, 146 (v1: 141-143).

**Why the e2e recall number is misleading (diagnostic on one shared e2e state, targets printed)**: the
eval counts a should-match item as a hit if the matcher matched it to ANY existing task, even the wrong
one. Of 40 should-match items: 18 matched by both gate-off and gate, 10 matched only by gate-off, 0 only
by the gate, 12 by neither; where both matched, targets agreed. Reading the 10 gate-off-only pairs by
eye (my judgment, not a labeled measurement): ~4 are real gate misses (e.g. "Run real-data validation
of multi-cluster merge output" vs the same text "...using dev clusters"; "Production deployment and
configuration" vs "Deploy the platform to production environment"), ~4 are the gate correctly refusing a
wrong target that the eval scored as a hit (e.g. "Confirm whitelist approval status" -> "Perform risk
check for whitelist approval"), ~2 ambiguous. So the gate's true recall loss is roughly 4-6 items, not
the ~10 the table implies, and gate-off's e2e recall is overstated. **Eval fix still to do**: score
target correctness (needs golden target labels) or at least print targets for human review.
The `llm_unsure` path fired for real once ("Complete CSV module coding and unit tests" vs "Write unit
tests for CSV module", 0.88).

**Possible next steps** (not started): gate misses are mostly "same item plus extra detail" and
lifecycle-step cases - tune the prompt on those; optionally route the gate to a different model via
`complete(model=...)` (parameter already exists) to test open-source models on the seeded eval.

---

## End-to-end confirmation of the LLM gate: 3 runs each, gate on vs gate off

**Setup**: `eval_match.py`'s full pipeline run 3x with the live gate and 3x with the gate patched
to approve every candidate (process-local patch, live file untouched), both via the same in-process
pipeline, two streams in parallel on separate projects. Each variant's DB state was built by its own matcher.

| | Recall (3 runs) | Specificity (3 runs) | Avg errors | Tasks in DB at meeting 8 |
|---|---|---|---|---|
| Gate off | 28, 27, 27 /40 (avg 68%) | 52, 54, 52 /71 (avg 74%) | 31.0 | 135, 122, 126 |
| Gate on (loosened prompt) | 17, 17, 17 /40 (avg 43%) | 63, 64, 63 /71 (avg 89%) | 30.7 | 142, 141, 143 |

**Reading**: end to end the gate is a wash on total errors (30.7 vs 31.0): ~10.7 fewer wrong merges,
~10 more missed updates, ~14 more tasks (duplicates) by meeting 8, plus one extra LLM call per run.
Run-to-run spread within a variant is small (+-1), so the gap between variants in recall/specificity
is real, but the totals cancel. This is weaker than the seeded result (9 vs 13 errors): on perfect
golden state the gate lost only 2 recall items, here it loses ~10. Hypothesis (not verified): real
extraction wording diverges more from the original task text than golden wording does, so the gate
rejects more legitimate updates, and every rejection adds a duplicate that later meetings then match
against.

**Decision framing**: whether the gate is worth keeping depends on the relative cost of a wrong merge
(silently updates the wrong task) vs a missed update (task goes stale and a duplicate appears). If a
wrong merge is worse, the gate wins marginally; if not, it's an extra LLM call and a prompt to maintain
for no gain. **DECIDED (2026-10-05, user): keep the gate.** The user judged a wrong merge worse than a missed update:
a wrong merge silently loses a real task (invisible, hard to undo, nothing on screen shows it), while a
missed update leaves a visible duplicate that is easy to spot and delete. The gate roughly halves silent
errors (~18 -> ~8 wrong merges) at the price of ~10 more visible duplicates and one cheap LLM call per
run. Known downside accepted: a duplicate task could sync as a duplicate Jira ticket if sync runs.
**Follow-ups, not started**: reduce the gate's missed updates (the 3 seeded-eval misses and the
e2e recall drop are the targets); decide how duplicates should be surfaced/merged for users.

---

## Seeded deterministic match eval (`eval/nodes/eval_match_seeded.py`) - matcher comparison on a fixed state

**Why**: `eval_match.py` builds its DB by running the real pipeline, so every run (and every matcher)
starts from a different task list - differences of a couple of pairs can't be told from noise. Real
runs aren't fixed-state either, so this is NOT a prediction of production numbers; it's a controlled
experiment for choosing between matchers. Production realism stays with the end-to-end evals,
to be run several times and averaged. Both kept, different questions.

**How**: seeds the project straight from the golden outputs (SOW tasks + new tasks of meetings
< N, via `insert_task`), then scores every matcher variant on that identical state (match never
writes to the DB, so one state per meeting serves all variants). Needs only the DB (no API/pipeline),
runs in seconds. The old 3-stage reconstruction lives in `eval/nodes/old3stage_match.py` as a
reference baseline, never imported by the app.

**Exclusions (7 of 111 items, listed in the output)**: 4 contradictory (same text labeled both
"should match" and "should not" in one meeting), 2 should-match with no plausible target in the
golden state (best cosine < 0.55), 1 should-not that is a verbatim duplicate of an already-seeded
task (exact match is correct behaviour, label is noise).

**Result, single run, scored items** (recall = update events matched / specificity = new tasks left unmatched):

| Matcher | Recall | Specificity | Errors |
|---|---|---|---|
| exact+semantic (gate off) | 35/36 (97%) | 56/68 (82%) | 13 |
| exact+semantic+LLM gate (live, loosened prompt) | 33/36 (92%) | 62/68 (91%) | 9 |
| old 3-stage (reconstruction) | 36/36 (100%) | 54/68 (79%) | 14 |

**Reading**: on identical state the LLM gate has the fewest errors (9): it trades 2 extra misses for
6 fewer false positives vs. gate-off. Old 3-stage vs exact+semantic is a wash (14 vs 13), but 8 of
its 14 false positives come from fuzzy/partial claiming a match first (e.g. "Draft deployment
runbook" -> "Deliver Deployment Runbook") - consistent with the reason they were removed. Not all
remaining gate false positives are real errors: "Deliver Integration Testing Report (Deliverable
4.6)" vs "Deliver Integration Testing Report" and "Deliver UAT Report (Deliverable 4.7)" vs "Deliver
User Acceptance Testing (UAT) Report" are plausibly the same task - the golden data itself
contains near-duplicates. The 3 gate misses: "Fix all four integration test defects", "Production
deployment and configuration", "Test LLM graph spec quality with and without sample rows".

**Caveats**: single run (gate is temperature 0 but not guaranteed deterministic); seeded state is
perfect extraction with clean wording, so absolute numbers flatter production; compounding is
invisible. **Status**: gate stays in `match.py` for now. **Next**: confirm with ~3 averaged
end-to-end runs before treating it as settled.

---

## Baseline re-run of the OLD 3-stage match logic (scratch reconstruction, LLM gate off)

**Why**: to check whether removing partial/fuzzy actually moved the node-level numbers, since the
removal was argued from design reasoning and a spot check, never measured against the eval.

**How**: the old stages were deleted with no git history, so they were rebuilt in a scratch module
(outside `apps/`, live `apps/nodes/match.py` untouched) from this file's description. Assumptions
where it is silent: partial = containment either direction, no length guard, first hit, fixed 0.90;
fuzzy = best SequenceMatcher score, accepted at >= 0.60 (medium 0.60-0.84, "high" label above that
assumed); semantic unchanged (0.55). The scratch module was swapped in via `sys.modules` and the
full pipeline run in-process, so the old logic also built the DB state, not only the direct calls
(verified by tallying: 22 fuzzy + 13 semantic + 1 exact matches inside the pipeline itself).

**Result** (`eval/nodes/eval_match.py`, recall = should-match, specificity = should-NOT-match):

| Matcher | Recall | Specificity | Errors |
|---|---|---|---|
| Old 3-stage, gate off | 28/40 (70%) | 53/71 (75%) | 30 |
| Exact + semantic (live before gate) | 28/40 (70%) | 55/71 (77%) | 28 |
| LLM gate, strict prompt | 13/40 (32%) | 67/71 (94%) | 31 |
| LLM gate, loosened prompt | 18/40 (45%) | 63/71 (89%) | 30 |

**Reading**: removing partial/fuzzy did not measurably change the totals - recall identical, 2 pairs
of specificity - which is inside run-to-run noise (pipeline extraction is nondeterministic, runs
started from 42 vs ~28 tasks). So the removal is not proven by this eval to have helped. What it does
show: of the old matcher's 18 false positives, 10 came from fuzzy's medium band and 1 from partial
(e.g. "Draft deployment runbook" -> "Provide deployment runbook", "Update project tracker with Week 3
progress" -> "Update tracker with whitelist approval details"), i.e. the failure mode the removal
targeted is real, and fuzzy did ~half of all matches (24 of 46 direct) without semantic losing any
recall once it was gone. 2 of the 18 were `exact` matches of verbatim-restated tasks (golden-label
noise, as before). Same eval caveats apply: contradictory golden labels, nondeterministic state,
recall capped by extraction.

**Status**: informational only; no code changed. Deterministic seeded eval is still the pending
next step before any keep/revert call on the LLM gate. Scratch files removed from the container;
`report_match.json` restored to the loosened-gate run (old-3-stage report kept in the session scratchpad).

---

## match.py: LLM confirmation of semantic candidates (first version - tradeoff, not yet a win)

**Problem (measured by `eval/nodes/eval_match.py`)**: 15 semantic false positives scored 0.657-0.899
cosine - inside the medium/high bands, overlapping genuine paraphrases - so no threshold fixes it.
Pattern: same feature, different action/deliverable (e.g. three different CSV-module tasks all merged
into "Write unit tests for CSV module"). One more flagged "false positive" was actually an exact
text match - golden-label noise, not a match.py bug.

**Rejected: keyword/entity/verb matching.** Verbs legitimately change across a task's lifecycle
(draft -> finalize -> deliver), so a verb gate creates new false negatives; same-verb pairs with
different objects ("Send access package" vs "Send API credentials") slip through anyway; and it
repeats the brittle-lexical-heuristic mistake already removed from match.py (partial/fuzzy).
**Rejected: human review queue** - needs table + endpoints + UI + a workflow, and re-adds the
"unresolved events" concept removed earlier. **Chosen: LLM second opinion** - embeddings only
propose a candidate, one batched `complete()` call per run decides same-task vs different-task
(`_llm_confirm_matches`); any failure -> treated as new task (duplicate is cheaper than a wrong merge).

**First measured result** (same eval, before -> after): should-match recall 28/40 (70%) -> 13/40 (32%);
should-NOT-match specificity 55/71 (77%) -> 67/71 (94%). Total errors 28 -> 31; rejected matches become
duplicate tasks. The first prompt ("same only when completing one completes the other") was too strict.

**Prompt tuning**: froze 37 candidate pairs from one run; tuned on meetings 2-5, held out 6-8. Loosened
prompt ("would a project manager track these as one line item or two?", lifecycle steps of the same
deliverable count as same) gave tune 9/17 -> 10/17, holdout 7/12 -> 8/12 - modest. A third variant
embedding tune-set examples scored no better (and leaked), so it was dropped. Of the 12 remaining
misses, ~6 are label/wrong-candidate noise (LLM arguably right), ~3 real LLM errors, ~3 ambiguous
lifecycle cases - further tuning would fit noise.

**Full eval with the loosened prompt**: recall 18/40 (45%), specificity 63/71 (89%); errors 30 vs the
28 baseline. Net: roughly a wash in error count, shifted from wrong merges to duplicates.

**Why the eval can't settle this yet (found while tuning)**:
1. Golden labels contradict themselves - identical (new, existing) pairs appear as both "should match"
   and "should not" (e.g. "Confirm whitelist approval status", meeting 5).
2. Pipeline extraction is nondeterministic run to run (the SOW alone produced 28, 29 and 45 tasks
   across three runs), so the DB state each meeting is matched against differs every run.
3. "Should match" recall is capped by whether the earlier task was ever extracted at all - a miss can
   be extraction's fault, not match's, defeating the point of a node-level eval.

**Status**: LLM confirmation (loosened prompt) is in `match.py`. Whether to keep it is undecided until
the eval is made deterministic. **Next**: seed existing tasks directly from the golden expected outputs
(via `insert_task`) instead of running the pipeline, so state is fixed, every should-match has a true
target, and a run costs only the confirm call. Then re-measure and decide keep/revert.

---

## Added a third, node-level eval tier - separate from tests/ and eval/

**Decision**: created `eval/nodes/`, organizationally distinct from both `tests/` (deterministic,
no real LLM judgment) and `eval/` (end-to-end, checks only the pipeline's final task list).
Each file in `eval/nodes/` calls one graph node directly (not through the full graph) against
real DB state, so a wrong result is unambiguously that node's own fault, never conflated with
upstream/downstream nodes' quality.

**Why**: `eval/run_eval.py` only ever diffs the final task list against golden - if a task is
missing, there was no way to tell whether extraction missed it, normalization mangled it, match
wrongly deduped it, or planning dropped it. Came up directly out of reviewing `apps/nodes/match.py`
(see below): we wanted to know match's own precision/recall, and discovered nothing in `tests/`
or `eval/` actually measured it in isolation.

**Scope decided**: of the 9 graph nodes, only 2 could get a node-level eval without authoring new
golden data: `supervisor` (document_type classification - the dataset's own file split, sow.txt
vs meeting-NN.txt, already is the label) and `match` (no LLM; reuses the existing golden dataset's
previously-unused "UPDATE EVENTS" section as ground truth for "should match an existing task").
`extract`/`normalize`/`planning`/`sync_reporting`/`meeting_coordinator` all need new intermediate-
stage golden fixtures that don't exist yet (e.g. "expected raw extraction," "expected normalized
fields") - deliberately not fabricated by guessing; held pending a decision on how to author them.
`format`/`finalize` are pure deterministic code with no model judgment - routed to `tests/db/` and
`tests/unit/` instead of an eval, not given a node-level eval entry.

**`eval/nodes/eval_supervisor.py`** (9/9 correct on first real run): tests only the two
deterministic branches (`existing_task_count == 0` -> sow, `> 0` and no SOW markers -> mom).
Confirmed via grep that no meeting-NN.txt file contains SOW markers, so the one LLM call
(`_llm_tiebreak`) is never exercised by this dataset - the eval says so explicitly rather than
silently claiming full coverage. Needs a working DB only, no API/LLM calls, seeds one task via the
real `insert_task()` to flip the branch.

**`eval/nodes/eval_match.py`** (real run against the full 8-meeting dataset): extended
`golden_parser.GoldenMeeting` with an `update_events` field (previously discarded entirely) - text
that should match something already in the DB, used alongside the existing `new_tasks` (text that
should NOT match anything). Calls `task_match_node()` directly per meeting step, against real
accumulated DB state built by actually submitting each document through the API in sequence (same
`/run` + `force_run=True` pattern as `run_eval.py`), using a separate dedicated project
(`eval-match-node`) so it never collides with `run_eval.py`'s `eval-vmware-sim`.

**Real finding from the first run**: should-match recall 28/40 (70%), should-NOT-match specificity
55/71 (77%) - i.e. ~23% of genuinely new tasks get wrongly matched to an existing one. This number
did not exist anywhere before this eval; `run_eval.py`'s end-to-end check couldn't isolate it
because a wrongly-matched "update" and a correctly-matched one both look identical in the final
task list (neither creates a new row). **Status: surfaced, not yet acted on** - whether this means
`SEMANTIC_THRESHOLD` (0.55) is too loose, or the confidence banding needs adjustment, or something
else, is an open question for the next session.

**Also fixed while here**: `run_eval.py`'s docstring/default `--api-base` said "run from the host"
on `:8010`, stale since `compare.py` started depending on `apps.utils.embeddings`
(`sentence_transformers`, container-only). Now documented and defaulted to run inside the api
container on its actual in-container port (`:8000`), matching how the two new node evals run.

**Status**: implemented, both scripts run successfully against real data. Git push: holding, per
earlier instruction, pending a request to push.

---

## Eval harness's own matching switched from character similarity to embeddings

**Date:** 2026-10-01
**Status:** Done, including a self-caught bug in how it was first deployed

**Decision:** `eval/compare.py`'s task-similarity function switched from
`difflib.SequenceMatcher` (character overlap) to cosine similarity over the same embedding
model `apps/utils/embeddings.py` already uses for real task-dedup matching in production.

**Why:** `SequenceMatcher` measures shared characters, not shared meaning. It credited
"Deliver Integration Testing Report" against "Have draft of integration test plan ready for
review" at 0.58 - two different tasks that happen to share the substring "integration test" -
purely because of character overlap, not because they mean the same thing.

**Calibrated, not guessed:** ran known-good pairs (confirmed correct matches from real eval
runs) and the one known-bad pair through the new embedding similarity and compared scores:
unrelated topics separated cleanly (0.13-0.32), but the known-bad match scored 0.595 - almost
on top of the weakest confirmed good match (0.615). Set `MATCH_THRESHOLD = 0.6`: just above
the bad match, just below the weakest good one. Explicitly logged as calibrated against a
small sample (6 pairs), not a rigorous validation set - a real gray zone between roughly
0.55-0.65 likely still exists for other cases not yet tested.

**Bug caught while documenting this, not before:** told the user this was set to 0.6, but the
actual deployed code had `MATCH_THRESHOLD = 0.55` - a real discrepancy between what was
described and what was written, not just a rounding choice. At 0.55 the known-bad match
(0.595) would still have passed, defeating the entire point of the calibration. Caught when
the user asked a follow-up question and both files were checked directly instead of answering
from memory. Fixed to the correct, calibrated value.

**Scope, stated precisely:** this only changed the eval's own comparison logic
(`eval/compare.py`). It did not touch and was never meant to touch production's own semantic
matching threshold (`apps/nodes/match.py`'s `SEMANTIC_THRESHOLD = 0.55`, unchanged) - that's a
separate file with a separate, already more sophisticated design (3-tier confidence banding
that already discards low-confidence matches, rather than one flat cutoff) - see the next
entry below for that review.

---

## Production matching logic (match.py) simplified to exact + semantic only

**Date:** 2026-10-01
**Status:** Done, verified against real task history

**Decision:** Removed `match.py`'s partial/containment and fuzzy (`SequenceMatcher`) match
stages entirely. Only exact-text match (free, first pass) and semantic (embedding cosine
similarity, the primary method for everything else) remain.

**Why:** Reviewing the eval harness's own matching-order bug raised the question of whether
production's real matching logic had an analogous weakness - it did, a more serious one.
Both removed stages could accept a wrong match and then **short-circuit before semantic ever
ran**, meaning a weaker-but-passing textual match could silently block a stronger semantic
one from ever being considered:
- Partial/containment had no minimum length guard and a **hardcoded** confidence (0.90,
  never actually measured), and took the first containment hit in iteration order with no
  comparison against other candidates - the weakest-reasoned stage in the file, checked
  first.
- Fuzzy's medium confidence band (0.60-0.84) was **not guaranteed to be the best available
  candidate** - a different existing task could score higher under semantic, but fuzzy would
  never find out, because it already claimed the match and moved on.

**Why exact-match was kept, not removed too:** this was explicitly checked, not assumed - for
identical normalized text, cosine similarity between the two embeddings is 1.0, the maximum
possible score. Semantic can mathematically never find a *better* candidate than an exact
textual duplicate, so keeping the shortcut produces an identical outcome to removing it and
letting semantic handle that case too - it's a pure performance optimization (skip an
embedding call for text already known identical), not a precision tradeoff. This is a
structurally different situation from fuzzy/partial, where a better semantic candidate
genuinely could exist and get missed.

**Honest residual risk, not solved by this or any version of the matcher:** identical surface
text doesn't logically guarantee the same real-world task/referent (e.g., two genuinely
separate review cycles could coincidentally share identical wording). This is accepted as an
inherent limit of automated text-based matching in this domain, not something this change
fixes or worsens - semantic alone, given that same identical text, would reach the identical
(possibly wrong) conclusion regardless of whether the exact-match shortcut exists.

**Verified against real task history, not just reviewed:** resubmitted `forloop`'s real MoM
(23 existing tasks, real prior history to match against) with `force_run=true` after
deploying. Confirmed via `task_events`: this run produced exactly 4 `exact` + 1 `semantic`
match - zero `partial`/`fuzzy`, matching the job's own reported `event_signals` count exactly.
No duplicate task explosion, no crash, task count unchanged. The `partial`/`fuzzy` rows still
visible in `task_events` are historical records from before this fix - correctly left alone,
since that table is an append-only audit log, not something rewritten retroactively.

---

## Eval harness fix #2 - greedy matching-order bug, verified against real data before trusting the fix

**Date:** 2026-09-30
**Status:** Fixed (`compare.py` now defaults to `algorithm="optimal"`) and empirically confirmed
to have changed real results, not just a theoretical flaw - per the user's own instruction to
verify the test's correctness before judging the thing under test.

**The bug:** `compare_tasks()` matched golden tasks against actual tasks one at a time, in
golden-file order - each golden task greedily claiming its own best-available match without
knowing what a later golden task in the list might need. If two golden tasks both had a
legitimate claim on the same actual task, whichever was processed first won it, regardless of
which one it actually belonged to.

**The fix:** score every (golden, actual) pair up front, sort all pairs by score descending,
assign highest-scoring pairs first across the whole matrix, skipping any pair where either
side is already claimed. A greedy approximation of optimal bipartite matching, not the full
Hungarian algorithm - sufficient at this scale (dozens of tasks) and simple enough to trust by
inspection.

**Verified, not assumed:** ran both algorithms side-by-side on the same real pipeline output in
one eval run (`_check_matching_algorithm_divergence` in `run_eval.py`, temporary
verification-only instrumentation). Result: diverged in 2 of 9 documents.
- meeting-07.txt: 8 → 9 matched (old algorithm was wrongly denying a golden task a match that
  belonged to it - the theorized failure mode, confirmed real).
- meeting-06.txt: 6 → 5 matched (old algorithm was *overcounting* - the opposite direction.
  Traced the exact bad match: "Deliver Integration Testing Report" had been credited against
  "Have draft of integration test plan ready for review," a 0.58 similarity score for two
  genuinely different things, barely above the 0.5 threshold).

**A second, separate finding surfaced while tracing that bad match, not yet acted on:** 0.58
clearing a 0.5 `MATCH_THRESHOLD` for two tasks that don't actually mean the same thing suggests
the threshold itself may be a little loose. This is independent of the ordering bug and still
open - worth revisiting once the Meeting Coordinator coverage gap (next entry) is addressed.

**Net effect on the run's aggregate total:** unchanged (52/82 either way - one document lost a
match, another gained one, canceling out in the overall number). The point of checking wasn't
the aggregate, though - it's that the *per-document* truth changed in two places, which a
future investigation into "why is meeting-06 weak" would have reasoned from incorrectly without
this fix, even though the headline percentage looked stable.

---

## Test suite - Phase 5 (real-LLM eval harness) - built, run, and it surfaced a real
methodology gap in the eval itself, not just in extraction

**Date:** 2026-09-29
**Status:** Harness built and successfully run end-to-end against real LLM calls. The
headline number it produced (49% recall) is NOT trustworthy as-is - see below. Refining the
comparison logic is the next step before treating this harness's output as a real quality
signal.

**What was built:** `eval/golden_parser.py` (parses both golden formats - the SOW's
numbered-deliverable format and the MoM's NEW TASKS/UPDATE EVENTS/SHOULD NOT BE PICKED
format), `eval/compare.py` (fuzzy task matching via `SequenceMatcher`, the same technique
`extract.py` already uses internally for its own dedup guard, plus a false-positive check
against the golden "should not be picked" negative examples), `eval/run_eval.py`
(orchestrates: reset a fixed `eval-vmware-sim` project, submit the SOW then all 8 meeting
files in order via the real `/run` API with `force_run=true`, diff the task list before/after
each step to find newly-created tasks, compare against golden, print + save a scored report).
Runs from the host over plain HTTP using only the standard library - no new dependency, and
deliberately not part of `pytest tests/` (real LLM calls cost real money/time - see the Phase
1+2 entry for why the two are kept apart).

**What the first real run found:** 40/82 expected new-task mentions matched (49%) across the
SOW + 8 meetings, recall declining sharply through the middle meetings (71% → 44% → 17% → 50%
→ 30% → 17% → 38% → 83%) before recovering at the end, plus 3 flagged possible false
positives and a much larger "extra tasks created" count than golden accounts for (125 total
tasks in the project vs. 82 golden "new task" mentions across the whole run).

**Investigated rather than reported at face value - two real findings, not one:**
1. **The SOW's "extra tasks" are very likely legitimate, not hallucinated.** Direct inspection
   confirmed extraction is decomposing each SOW deliverable into concrete implementation-level
   tasks (e.g. "Implement CSV file listing, upload, and ingestion") rather than keeping only
   the 11 top-level deliverables golden's `TASK COUNT: 11` counts - and the golden file's own
   per-deliverable `Subtasks:` lists show its author anticipated this same granularity, just
   never modeled it as comparable "tasks." This isn't extraction being wrong; it's the eval
   comparing two different levels of granularity as if they were the same thing.
2. **The comparison methodology itself undercounts recall for later meetings, and this is the
   more important finding.** Checked a specific "MISS" from meeting-06 directly: the golden
   task "Deliver Integration Testing Report" has a 0.59-similarity match already sitting in the
   project ("Conduct integration testing for end-to-end pipeline") - well above the match
   threshold - but it wasn't counted, because it almost certainly wasn't a *newly created* row
   in meeting-06's step. It was very likely created earlier and correctly matched/updated by
   this run's matching logic instead of duplicated - which is *correct* system behavior (the
   entire point of the dedup/match pipeline), but invisible to a harness that only diffs
   newly-created task IDs per step. The declining-then-recovering recall curve is consistent
   with this: later meetings have more accumulated task history to correctly match against,
   which this harness currently punishes instead of crediting.

**Conclusion, stated honestly:** the harness works end-to-end and the infrastructure is
sound, but its recall number is not yet a trustworthy quality signal - it's very likely a real
underestimate, by an unknown amount, specifically for meetings with substantial existing task
history to match against. Reporting 49% as "extraction quality" without this caveat would be
actively misleading.

**Next step, not yet done:** extend the comparison to also credit a golden "new task" against
an *updated* existing task (check `task_events`/the task's `updated_at` for activity during
that step, not just newly-inserted `task_id`s) before treating this harness's score as
meaningful. The false-positive check and the SOW-granularity finding stand on their own and
don't need this fix first.

---

## Test suite - Phase 4 (mocked-LLM pipeline-logic tests)

**Date:** 2026-09-29
**Status:** Done - 8 new tests, all passing on first run, 34 total in the suite

**Decision:** Added `tests/pipeline_logic/` covering `run_react_loop`'s tool-call-budget
enforcement, its JSON-parse-retry fallback, and the Supervisor's `_llm_tiebreak` classifier -
the three places in the codebase that call the LLM from inside a function whose *surrounding
control flow* (not the model's judgment) needed a regression test.

**Mechanism:** a `scripted_llm` fixture (`tests/conftest.py`) monkeypatches `complete()` to
return a fixed sequence of fake response objects, one per call, shaped to match exactly what
the real code reads off a response (`.choices[0].message.content`, `.tool_calls`,
`.model_dump(exclude_none=True)`) - so nothing about *how* the response was obtained differs
from the real path, only *what* it contains is fixed instead of left to a live model.

**The budget test is the actual Meeting Coordinator bug, encoded as a permanent regression
check:** scripts the exact real sequence (1 `resolve_attendees` + 3 `check_owner_availability`
calls) and asserts that with `max_tool_calls=4` the loop never reaches a 5th call, while with
`max_tool_calls=8` a `schedule_meeting` call does get through. Confirmed these aren't
tautological passes: if budget enforcement were removed entirely, the `max_tool_calls=4` test
would try to consume a 6th scripted response that doesn't exist and error with
`StopIteration` - a real, structural check, not just an assertion that happens to be true.

**Not testing model judgment here, deliberately:** these tests would stay green even if the
configured model were swapped entirely (OpenAI to Anthropic to a self-hosted model) - that's
correct, not a gap, since verifying the *model's* decision quality is the eval harness's job
(Phase 5, not yet built), not this layer's.

---

## Test suite - Phase 1 + 2 (infrastructure + DB-integration regression tests)

**Date:** 2026-09-29
**Status:** Done - 26 tests, all passing, verified against the real dev DB with clean teardown

**Decision:** No test suite existed at all before this (verified: zero test files, zero CI,
zero testing dependencies anywhere in the repo). Built `pytest`-based deterministic tests
against the real Postgres instance (not mocked), kept strictly separate from a planned,
not-yet-built real-LLM evaluation harness (`eval/`) - see the reasoning already captured in
this conversation: deterministic tests prove code is provably right or wrong; LLM output has
no such single correct answer and needs fuzzy comparison against the golden dataset instead.

**Why real Postgres, not a mocked DB:** most of this app's actual logic *is* a database
constraint or query, not standalone Python (cache isolation = a UNIQUE constraint, Jira
idempotency = a column read-then-skip, the blocked-filter fix = a WHERE clause). Mocking the
DB would mean hand-reimplementing Postgres's own constraint enforcement in Python just to fake
it - more work than running real Postgres, and prone to the mock saying "works" when the real
constraint would actually reject it.

**Where tests run:** inside the `api` container (`docker compose exec api pytest tests/`),
reusing its already-correct `DB_HOST`/`DB_PORT` and installed dependencies rather than
standing up a separate host-side test environment to keep in sync.

**What was built:**
- `tests/conftest.py` - a `test_project` fixture yielding a disposable `project_id`
  (`test-<uuid>`) and guaranteeing teardown across every table a project's data can land in
  (more thorough than production's `delete_project()`, which deliberately preserves
  `project_people` for real users - test data has no such reason to survive).
- `tests/unit/` - pure Python, no DB/LLM: `chunk_document()` (empty input, single-chunk,
  multi-chunk overlap, no content lost at a boundary), `_parse_deadline_window()` (valid date,
  no-date fallback, malformed-date fallback).
- `tests/db/` - real-Postgres regression tests, one file per bug fixed this session:
  cache isolation, Jira idempotency + accountId resolution (Jira's own HTTP calls mocked -
  this suite must never create a real external issue), the blocked-task filter, the
  never-clobber-a-real-email placeholder guarantee, the meeting approval state machine
  (pending → scheduled/rejected, a rejected meeting never gets a `google_event_id`), and
  `project_people` surviving `delete_project()` while tasks don't.
- `pytest.ini` - `pythonpath = .`, needed because pytest's default "rootless" import mode
  doesn't add the project root to `sys.path` the way `uvicorn`'s own invocation happens to;
  without it, `from apps.db.db import ...` fails inside every test file.

**Two real mistakes caught and fixed while writing these, not just while running the app:**
- A Jira test initially patched `os.getenv` directly to fake `JIRA_BASE_URL`/etc. `os` is a
  shared module singleton, so this silently broke `get_connection()`'s own `DB_HOST`/`DB_PORT`
  lookups too (every caller of `os.getenv` process-wide gets shadowed, not just the one module
  the patch target's dotted path suggests) - the DB connection failed with a `localhost`
  refused error. Fixed by patching `mcp_server.tools.jira._get_jira_auth` directly instead -
  narrow, and doesn't touch anything outside the one function being faked.
- The already-synced idempotency test didn't call `set_project_jira_key` first - the real code
  checks `jira_project_key` *before* the idempotency check, so the test was short-circuiting to
  `not_configured` before ever reaching the branch it was meant to verify. Not a production bug
  - a gap in the test's own setup, caught by actually running it rather than assuming it would
  pass.

**Verified, not just run:** confirmed zero leftover `test-%` rows in `tasks`/`project_people`/
`meetings` after a full suite run, and confirmed `forloop`'s real 23 tasks were untouched
throughout.

**Not built yet, deliberately deferred:**
- Phase 3 was folded into Phase 2 above (the unit tests) rather than kept as a separate step -
  no reason to sequence them separately once both were straightforward to write together.
- Phase 4 (mocked-LLM pipeline-logic tests for `react_loop.py`'s budget cutoff and JSON-retry
  fallback, `supervisor.py`'s tie-break classifier) - next planned increment.
- Phase 5, the real-LLM eval harness against the existing golden SOW/MoM dataset - planned,
  not started.
- CI wiring (GitHub Actions to run this automatically on push) - no CI exists at all today;
  treat as a deliberate future phase, not assumed.

---

## RBAC design - logged and ready, not yet implemented

**Date:** 2026-09-26
**Status:** Designed only - deliberately not built yet, no real trigger for it exists.
Implement when either a real client integration is on the table, or a login wall is wanted
for other reasons. This entry exists so implementation can start immediately, without
re-deriving the reasoning below.

**Current state, stated plainly:** there is no authentication of any kind in this system
today. No `users` table, no login, no session/token check on any of the ~25+ endpoints in
`apps/api.py`. Every action - including destructive/external-side-effect ones like deleting a
project or approving a meeting (real Google Calendar invites to real people) - is callable by
anyone who can reach the API. RBAC (what a role can do) is the *second* layer of a two-layer
problem; authentication (who is asking) is the missing first layer.

**Why this will be necessary before attaching to a client's ecosystem:**
- `project_id` is just a string today - nothing stops a request naming any project. A client
  org needs people restricted to the projects they're actually on.
- Several actions have real external side effects (project deletion, meeting approval →
  calendar invites, Jira config changes) that shouldn't be triggerable by whoever has the URL.
- Enterprise clients generally expect SSO against their own identity provider (Okta/Azure
  AD/Google Workspace), not a separate password database, plus an audit trail of *which human*
  triggered an action - today's activity feed only tracks which *agent* acted, not which
  person asked it to.

**The key design decision: authentication and authorization are fully decoupled**, so
starting with simple email/password now costs nothing later - swapping in a client's real SSO
only ever touches the authentication layer, never the RBAC layer built on top of it.

**Schema:**
```sql
CREATE TABLE IF NOT EXISTS users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL UNIQUE,
    name TEXT,
    password_hash TEXT,           -- null once/if a user is SSO-only
    auth_provider TEXT,           -- null for password users; set once SSO exists ('okta', 'google', ...)
    auth_provider_subject TEXT,   -- the IdP's own id for this user
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS project_members (
    project_id VARCHAR NOT NULL,
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('viewer', 'editor', 'admin')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (project_id, user_id)
);
```
`project_members` (a role per user *per project*), not a single global role on `users` -
matches how everything else in this app (`project_people`, `project_integrations`) is already
project-scoped, and correctly allows someone to be an admin on one project and only a viewer
on another.

**Illustrative role tiers (not final - confirm against a real client's actual needs before
building):**
- **Viewer** - read tasks/people/meetings/activity/chat, no writes
- **Editor** - + edit tasks, manage people, submit new documents
- **Admin** - + delete project, approve/reject meetings, edit Jira config

**The two dependencies that make this SSO-ready without a future rewrite:**
- `get_current_user(token) -> user_id` - today: decode a JWT our own `/auth/login` issues
  after checking `password_hash`. Later: swap this function's *internals* to validate an
  SSO-issued token instead. Signature and what it hands downstream (`user_id`) never change.
- `require_role(project_id, minimum_role)` - looks up `project_members` for
  `(user_id, project_id)`, checks the role, 403s otherwise. Already fully
  authentication-method-agnostic - never touches how the user was verified.

**Planned incremental rollout, once triggered:**
1. Add `users`/`project_members` tables - pure addition, zero behavior change to anything
   currently working.
2. Login endpoint + `get_current_user` dependency - exists, testable, not yet enforced
   anywhere.
3. Apply `require_role` to the highest-risk endpoints first - project deletion, meeting
   approval, Jira config - not all ~25 endpoints at once.
4. Frontend: login page, token storage, attach to every request.
5. Broaden to remaining endpoints; make Chat's tools user-access-aware - `list_projects` etc.
   currently return everything, with no concept of "only what this user can see."
6. Whenever a real client/IdP is known: swap `get_current_user`'s internals for SSO - nothing
   else changes.

**Deliberately not decided yet, on purpose:** the exact role tiers (the 3 above are
illustrative, not confirmed against any real client's actual org structure), and the auth
method for the *first* build (email/password is the assumed starting point, but this should be
revisited the moment a real client/IdP enters the picture rather than committed to
speculatively).

---

## LLM-agnostic model layer via LiteLLM

**Date:** 2026-09-25
**Status:** Done - implemented and verified against real OpenAI calls across all 3 call paths

**Decision:** Route every LLM call in the app through one shared `complete()` function in
`apps/llm.py`, backed by LiteLLM instead of the raw `openai` SDK client, with the actual
provider/model chosen entirely by `.env` (`LLM_MODEL`, `LLM_API_KEY`, `LLM_API_BASE`,
`LLM_FALLBACK_MODEL`, `LLM_EXTRA_HEADERS`).

**Why:** The goal is running any model a client wants - OpenAI, Anthropic, Gemini, or their
own self-hosted open-source model (Ollama, vLLM, etc.) - via config, not a code change per
provider.

**Why LiteLLM over OpenRouter** (the other option discussed): OpenRouter is a hosted gateway -
your request goes to OpenRouter's servers, which call the actual provider and translate the
response. That only reaches open-source models OpenRouter itself has chosen to host; it has no
way to reach a client's own private/self-hosted model server, which was the deciding
requirement. LiteLLM is a library that runs in-process and calls each provider's real native
API directly (including a self-hosted `api_base` a client controls) - no added network hop, no
third-party in the request path, no markup on top of provider pricing.

**Why not a hand-written class-per-provider abstraction** (discussed first, before settling on
this): would have meant writing and maintaining our own translation layer for every provider's
actual request/response shape. LiteLLM already does exactly that translation, is
already a dependency-weight most teams accept for this problem, and is free/open-source - no
reason to hand-roll the same thing.

**What changed - exactly 3 files with real LLM calls, everything else untouched:**
- `apps/llm.py` - rewritten around one `complete()` helper wrapping `litellm.completion()`;
  `call_llm`/`call_llm_json` keep their exact same signatures, calling it internally.
- `apps/agent/react_loop.py` - both `run_react_loop` and `run_chat_loop` (4 call sites total)
  swapped from the raw `client.chat.completions.create()` to `complete()`; `model` parameter
  default changed from the hardcoded `"gpt-4o-mini"` to `None` (meaning "use the configured
  default" instead of a literal baked into this file).
- `apps/supervisor.py` - its one direct LLM call (the SOW/MoM tie-break classifier) swapped
  the same way.
- `extract.py`, `normalize.py`, `planning.py`, `chat.py`, `sync_reporting.py`,
  `meeting_coordinator.py` - **zero changes**. They only ever called `call_llm_json()` or
  `run_react_loop()`/`run_chat_loop()`, whose signatures never changed.

**Non-disruptive by design:** `LLM_API_KEY` falls back to the existing `OPENAI_API_KEY`, and
`LLM_MODEL` defaults to `"gpt-4o-mini"` - leaving `.env` completely untouched reproduces the
exact previous behavior. Switching providers later is a `.env` change only.

**Verified against real calls, not just reviewed** - rebuilt the API image (a genuinely new
dependency, not just a code change, needs a real image rebuild rather than the usual
`docker compose restart`), then re-ran the paths most likely to break under a client-library
swap:
- Chat's tool-calling loop, including the `choice.model_dump(exclude_none=True)` re-injection
  step that was flagged as needing real verification, not just assumed - confirmed correct
  with a multi-hop question requiring 4 chained tool calls
- The full document pipeline (extraction, matching, Planning's own tool-calling) end to end on
  a real SOW submission
- No errors in the API logs across any of the above

**Not built:** self-hosted-model testing (no Ollama/vLLM instance available in this
environment) and multi-provider fallback testing (`LLM_FALLBACK_MODEL`) - the code path exists
and was reviewed, but only the default OpenAI path has been exercised against a live call so
far. Worth a real test against a second provider before relying on it for a client
presentation.

---

## RAG system for AI Chat - semantic search over source documents

**Date:** 2026-09-24
**Status:** Done - implemented and verified against a live document, not just code-reviewed

**Decision:** Add a `document_chunks` table (project-scoped, its own `vector(384)` column +
HNSW index) so the Chat assistant can semantically search the actual SOW/MoM text, not just
the structured tasks/people/meetings extracted from it.

**Why:** The extraction pipeline only ever pulls out *tasks* - everything else in a document
(scope narrative, commercial terms, background context, the reasoning behind a decision in a
meeting) is discarded once extraction finishes. Chat's existing 9 tools only ever query
structured tables, so any question about that narrative content is unanswerable today ("what
did the SOW say about X", "why did we decide to delay Y", "summarize the last meeting").

**How it's being built:**
1. New table `document_chunks` (`chunk_id`, `doc_id` FK to `source_documents` ON DELETE
   CASCADE, `project_id`, `chunk_index`, `chunk_text`, `chunk_embedding vector(384)`),
   self-provisioned via `ensure_document_chunks_table()` at API startup like every other
   table this session. HNSW index on `chunk_embedding` (`vector_cosine_ops`).
2. New chunking function, smaller granularity than extraction's existing `_chunk_text()`
   (~800-1200 chars w/ ~150 char overlap, vs. extraction's 15,000-char windows meant for LLM
   prompt budgeting, not retrieval precision) - same sentence-boundary-aware technique, tuned
   differently because the two chunking use cases have different goals.
3. Reuses the exact same embedding function/model already used for task-matching
   (`apps/utils/embeddings.py`, `all-MiniLM-L6-v2`, 384-dim) - same vector space, no new
   dependency.
4. Hooked into `upsert_source_document()` in `apps/db/db.py` - chunks + embeds only on a
   genuinely new document insert (not the `ON CONFLICT DO NOTHING` resubmission path), so
   chunking never happens redundantly.
5. New Chat tool `search_documents(project_id, query)` - embeds the query, cosine-searches
   `document_chunks` scoped to `project_id`, returns top-5 excerpts with source metadata for
   citation. Added to `CHAT_TOOL_SCHEMAS`/`CHAT_TOOL_IMPLS` alongside the existing 9.
6. Manifest (`chat.md`) updated: this tool's answers must be grounded only in what it actually
   retrieved, and the assistant must say plainly "the documents don't mention that" on a weak
   or empty match - this tool can genuinely fail to retrieve the right passage in a way
   structured DB queries can't (a `SELECT` either has the row or it doesn't; semantic search
   can silently return the wrong-but-plausible chunk).

**Alternatives considered and rejected:**
- *Separate database for the vector store* - rejected. Same Postgres instance already runs
  pgvector for task-matching; a new database would mean separate backups/connections and no
  easy join back to `source_documents` for citation, for no real isolation benefit. Project-id
  scoping (the pattern already used everywhere else in this app) is what actually provides
  isolation, not a second database.
- *IVFFlat index instead of HNSW* - rejected, same reasoning as the existing
  `idx_tasks_embedding_hnsw` index: IVFFlat needs to be trained on existing data at
  index-creation time (degenerate on an empty/small table) and needs periodic rebuilding as
  data grows; HNSW builds incrementally, correct from row zero, no maintenance schedule to
  remember. `document_chunks` starts empty and grows the same organic way `tasks` does, so the
  same reasoning applies.
- *Reusing extraction's existing `_chunk_text()` as-is* - rejected. Its 15,000-char windows are
  sized for fitting the extraction LLM's prompt budget, not for precise semantic retrieval - a
  single embedding representing ~3,000 words is too diluted to distinguish "the sentence about
  payment terms" from "the sentence about the timeline." Built a separate, smaller-granularity
  chunker instead, reusing only the sentence-boundary-aware splitting *technique*.

**Deferred / not building right now:** general open-ended read-only SQL access for Chat (the
"Option B" escape hatch discussed alongside this) - holding off unless real usage shows
questions the structured tools + this document search still can't answer. Also deferred: how
to track hours/budget/cost - nothing in the data model captures this today; a separate design
conversation, not a RAG or tool-wiring problem.

**Verification (against a real submitted document, not a unit test):** wrote a synthetic SOW
containing commercial/process details that would never become a task (payment terms, contract
value cap, an escalation rule naming a specific role), submitted it under a fresh project, and
confirmed:
- Chunks + embeddings were created automatically on submission (2 chunks, both embedded)
- Chat correctly answered "what are the payment terms / total contract value" from real
  retrieved excerpts, matching the source text exactly
- Cross-project isolation holds in both directions - asked the same two questions about a
  different, unrelated real project (`forloop`); it correctly said the documents don't cover
  it rather than leaking the test project's figures

**Bug found during verification, not assumed away:** the first pass at the escalation
question ("who do I escalate a late deliverable to") never called `search_documents` at all -
it went straight to `get_project_people`, found no roster entries for the brand-new test
project, and gave up. The word "who" made the model treat it as a roster lookup rather than a
document-content question. Fixed by adding an explicit manifest rule: an empty structured-tool
result means that fact isn't stored as structured data, not that no answer exists - a
process/policy/escalation question should fall back to `search_documents` before the assistant
tells the user the app doesn't have it. Re-verified after the fix: correctly routed straight to
`search_documents` and answered correctly from the retrieved excerpt.

---

## AI Chat tool consolidation - fixed a real hallucination, redesigned around entities not questions

**Date:** 2026-09-22 to 2026-09-24
**Status:** Done

**Decision:** Grew Chat's tool set from 7 to 9 (before the RAG entry above added a 10th) by
mapping tools to the app's actual data *entities* (tasks, people, meetings, dependencies,
workload, activity, projects) rather than to individual question phrasings, and rewrote the
manifest's anti-hallucination rule to be data-model-agnostic instead of a list of protected
field names.

**Why:** Asked "list all the resources working on vmware-sim along with their role" - Chat
answered with 3 people and invented job titles ("Developer", "Project Manager") that didn't
match reality, and silently omitted a 4th real team member entirely. Root cause was two
separate bugs: (1) no tool gave Chat access to `project_people` at all, so it had no way to
know a real role even existed to fetch - only `get_owner_workload`/`search_tasks` existed,
neither returns a role; (2) the existing grounding rule said "never state a task count,
status, owner, or deadline you didn't retrieve" - an enumerated list that never mentioned
"role" because nobody anticipated it, so the model didn't feel the rule applied.

**What was added:**
- `get_project_people` - wraps the exact same `list_project_people()` already powering the
  People panel UI. Zero new backend code.
- `get_project_meetings` - wraps the exact same `list_meetings()` already powering
  MeetingsPanel. Zero new backend code.
- `jira_issue_key` added to `search_tasks`/`get_task_by_id`'s existing `SELECT`s, and
  `jira_project_key` + `jira_synced_tasks`/`jira_unsynced_tasks` added to
  `get_project_overview`'s aggregate query (`apps/db/db.py: fetch_projects()`) - Jira status is
  a *field* on an entity Chat already has a tool for, not a new entity, so no new tool needed.
- Manifest grounding rule rewritten: "never state ANY fact you didn't just retrieve, including
  a field no tool returns at all (role, budget, hours) - say the app doesn't track it" -
  doesn't need editing every time a new field/tool is added, unlike the old enumerated version.

**Two more real bugs found while verifying the fix, not assumed away:**
- `search_tasks` caps at 20 results with no signal more exist. Asked "how many tasks in
  forloop are synced to Jira" on a 23-task project - Chat counted the truncated 20-row list and
  got it backwards (said 4 synced/19 not, real answer was 16/7). Fixed by pointing counting
  questions at `get_project_overview`'s real un-truncated aggregate instead, and made both
  tools' descriptions explicit about the cap so the model doesn't reach for the wrong one.
- `search_tasks(status='blocked')` used literal `status = 'blocked'` equality and missed a task
  that's blocked in every other sense the app uses (has `blocker` text set, shown as blocked on
  the dashboard's own stat card, counted by `get_project_overview`) but whose `status` column
  was never flipped. Fixed `search_tasks` to match `status = 'blocked' OR blocker IS NOT NULL`
  when `status='blocked'` is requested - the same definition used everywhere else in the app,
  so Chat's answer can't contradict what the UI shows for the same project.

**Alternatives considered and rejected:**
- *One tool per question shape* (e.g. a `list_resources_with_roles` tool) - rejected outright;
  this is what caused the original bug's *shape* of failure (a fixed field list that can't
  anticipate every phrasing) and doesn't scale as more question types come up.
- *One open-ended read-only SQL tool* - considered as a fallback for the long tail, deferred
  (see the RAG entry above) rather than reached for by default; more flexible but real added
  security surface to harden (read-only DB role, query validation, row/time limits) for
  questions the structured tools + document search likely already cover.

---

## Agent Activity panel: collapses horizontally, not vertically

**Date:** 2026-09-22
**Status:** Done

**Decision:** The right-side "Agent activity" panel on Dashboard/Task Manager collapses to a
56px vertical rail (freeing the grid column for the main content to widen into) rather than
just shrinking its own height in place.

**Why:** First implementation (vertical collapse, panel shrinks to just its header) technically
satisfied "make it collapsible" but didn't address the actual goal - reclaiming screen space
for the task board when the feed isn't needed. Corrected after the user clarified the intent:
collapse should resize the *layout*, not just the panel.

**How:** Collapse state moved from the panel component up to each page (`task-manager`,
`dashboard`), since the page owns the grid template (`lg:grid-cols-[1fr_320px]` vs.
`lg:grid-cols-[1fr_auto]`) and only the page can resize it - `ActivityFeed` became a controlled
component (`collapsed`/`onToggleCollapsed` props) instead of owning its own state. Preference
persists via `localStorage` (`lib/preferences.ts`, same pattern as the existing
view/project preferences) and is shared across both pages.

---

## Auto-populate project_people from extracted task owners

**Date:** 2026-09-21 to 2026-09-22
**Status:** Done

**Decision:** Any task owner extracted from a SOW or MoM (both paths, not just MoM) gets
automatically added to that project's `project_people` roster as a name-only placeholder
(`email = NULL`) if they're not already known - rather than requiring every attendee to be
seeded manually before the app is useful.

**Why:** `project_people` previously had no write path except a raw DB insert - the only reason
Nirmal/Ram/Rucheek showed up in the People tab earlier was manual seeding. In a real
deployment, a task owner is almost always a real employee, so the roster should build itself
up as tasks are extracted instead of staying manual-only forever. The user's own framing: an
unresolved person should still show up (so a manager can see who's missing an email and fix
it), not be invisible until someone remembers to add them by hand.

**What this required:**
- `project_people.email` made nullable (`ALTER TABLE ... DROP NOT NULL`) - was `NOT NULL`
  before, since the only write path used to be a manual add with a known address.
- `resolve_person_email()` changed to require `email IS NOT NULL` - critical safety fix: without
  this, a placeholder row would look "resolved" to Meeting Coordinator's `resolve_attendees` and
  try to invite a `null` address to a real Google Calendar event.
- New `ensure_person_placeholder()` - case-insensitive existence check first (never overwrites
  an existing email/role), hooked into the two places in `apps/nodes/format.py` where a task's
  `owner` field is ever written (new-task creation and owner-change updates on existing tasks).
  Splits on `,` first since `owner` can be a multi-person string.
- PeoplePanel UI: unresolved people show "No email on file - add one" with an inline resolve
  form (reuses the existing upsert-by-name endpoint), instead of requiring delete-and-re-add.

**Verified on a real rerun**, not just a unit test: reran `forloop`'s real SOW and confirmed all
5 fictional task owners got added as placeholders while the 3 real people with existing emails
were left untouched - and confirmed no task duplication from the rerun (dedup guards still held).

---

## Run cache scoped by (content_hash, project_id), not content_hash alone

**Date:** 2026-09-21
**Status:** Done

**Decision:** `source_documents`' cache/dedup key changed from `content_hash` alone (globally
unique) to `UNIQUE (content_hash, project_id)`.

**Why:** Identical SOW/MoM text submitted to two *different* projects would incorrectly return
the first project's cached pipeline result for the second project - a real data-integrity bug,
not just a UX inconvenience. The "Force a fresh run" checkbox was a manual workaround, not a fix.

**Alternatives considered:** none seriously - this was a straightforward missing-scope bug, not
a design tradeoff. The only real decision was how to handle existing rows during migration:
left their `project_id` as `NULL` rather than guessing which project they belonged to (a cache
miss just means a fresh run, which is safe; a wrong guess wouldn't be).

**Verified:** submitted identical text under two different project ids directly against the DB
functions and confirmed independent cache entries; confirmed same-project resubmission still
hits the cache (no regression).

---

## Jira sync correctness: real accountId resolution + per-task idempotency

**Date:** 2026-09-21
**Status:** Done

**Decision:** Two independent fixes to `mcp_server/tools/jira.py`'s `sync_task_to_jira`:
(1) resolve an assignee name to a real Jira `accountId` via the user-search API before
assigning, instead of sending the deprecated `assignee.name` field; (2) store `jira_issue_key`
on the task row and skip re-creating an issue if one already exists for that `task_id`.

**Why:** (1) Jira Cloud's v3 API doesn't accept `assignee.name` - it was either being silently
ignored (issue created unassigned, looked like a harmless no-op) or would 400 depending on the
site, an inconsistent and unreliable behavior either way. (2) Nothing tracked "this task was
already synced," so rerunning the pipeline against a still-live project (not a delete+recreate,
which is a deliberate reset) could create duplicate Jira issues for the same task on every rerun.

**Alternatives considered:** for (2), considered also preventing duplicates across a
delete-and-recreate-project cycle, rejected - a deleted project's tasks get entirely new
`task_id`s with no continuity, and deliberately deleting a project is a reset, not something
that should try to carry old Jira state forward.

**Verified against the real Jira instance** (not mocked): confirmed accountId resolution
succeeds for a real user and degrades gracefully (unassigned, not a failed create) for a name
with no match; confirmed a second sync call for the same `task_id` returns `already_synced`
instead of creating a duplicate issue.

---

## Meeting Coordinator gets a human approval gate before scheduling

**Date:** 2026-09-19 to 2026-09-20
**Status:** Done

**Decision:** Meeting Coordinator no longer calls Google Calendar directly. It now calls a new
`propose_meeting` tool that just stages the details; a new `meetings` table holds the proposal
(`pending_approval` / `scheduled` / `rejected`); a person has to review and approve in the UI
before the real Calendar event (and its invites) gets created.

**Why:** Previously the agent could autonomously send real calendar invites to real people with
no review step. Once the two Meeting Coordinator bugs below were fixed and it actually started
succeeding reliably, that meant a fully autonomous agent silently sending meeting invites -
too much unsupervised authority for an action with real external side effects (an email
landing in someone's inbox, a real calendar event).

**What was added:** `meetings` table (self-provisioned), `propose_meeting` tool (stages details,
never touches the Calendar API), `POST /meetings/{id}/approve` (calls the real `schedule_meeting`
only on explicit approval) and `/reject`, a review modal (reuses the existing manual
ScheduleMeetingModal, pre-filled from the proposal, editable before approving), and a Meetings
panel on Task Manager so a proposal doesn't just live invisibly in a job's trace.

**Verified live**: approved and rejected test meetings through the actual UI against the real
Google Calendar integration; confirmed a rejected proposal never touches Calendar and an
approved one does.

---

## Meeting Coordinator reliability: tool-call budget and date grounding

**Date:** 2026-09-19
**Status:** Done

**Decision:** Raised `max_tool_calls` from 4 to 8 for the Meeting Coordinator agent, and inject
the actual current date into its system prompt fresh on every call (not a module-level
constant computed once at process start).

**Why:** Found via direct trace inspection after "ran MoM, added 5 tasks but it did not schedule
any meeting": `resolve_attendees` (1 call) + `check_owner_availability` per attendee (3 calls
for 3 real attendees) already exhausted a budget of 4, leaving zero calls left for
`schedule_meeting` itself - the one tool call the agent exists to make. Separately, with no
date anchor in the prompt, the agent resolving "next week" hallucinated a date years in the
past on one test run before this was caught - a real calendar event with real invites at a
nonsensical date.

**Implementation note:** the date-grounding fix was built via plain string concatenation of the
system prompt, not `.format()` - the manifest's own "Output format" section contains literal
JSON-example braces (`{"followup_warranted": ...}`) that `.format()` would misinterpret as its
own placeholders and crash on. Caught in a first draft via `ast.parse()` before it ever
deployed.

**Verified via direct force-run API calls three times**: before either fix (confirmed the
4-call cutoff exactly), after the budget fix alone (confirmed scheduling succeeded but with a
hallucinated 2023 date), after both fixes (confirmed the correct near-future date). Also
independently re-confirmed by the user running the actual UI flow.

---

## project_people survives project deletion

**Date:** 2026-09-18
**Status:** Done

**Decision:** `delete_project()` no longer deletes rows from `project_people` - a deleted and
recreated project (same `project_id`) keeps its known people.

**Why:** The user's own demo workflow requires deleting and re-running a project live, and
manually re-adding every attendee mid-demo wasn't viable. Mirrors how the run cache already
"survives" deletion (it's keyed by content hash, not tied to project lifecycle) - made explicit
and deliberate here rather than accidental.

**Known tradeoff, accepted:** this leaves orphaned `project_people` rows for a project id that's
genuinely gone for good, not just deleted-and-about-to-be-recreated. Accepted as low-cost;
revisit alongside the cache re-scoping work if it ever becomes a real problem.

---

## Demo dry-run bug-fixing batch

**Date:** 2026-09-17 to 2026-09-18
**Status:** Done

Found through the user's own hands-on testing of the demo SOW/MoM flow, not code review:

- **ActivityFeed mislabeling** - "Jira not connected" was shown even when Jira genuinely was
  connected and only missing a per-project key; a calendar check that returned
  `unavailable_to_check` (the expected OAuth2-mode limitation) was being reported as if it
  succeeded. Fixed by branching on the actual result content instead of a single boolean.
- **"Force a fresh run" control added** to RunPanel - the content-hash cache (see the later,
  proper fix above) meant resubmitting identical text silently replayed a stale cached result
  with no way to bypass it from the UI.
- **AI Chat project_id guessing bug** - reproduced precisely via a two-turn conversation: turn 1
  correctly resolved "northstar" to "northstar-demo" via `list_projects`, turn 2 guessed
  `project_id: "northstar"` directly from conversational phrasing despite the correct id being
  in the same conversation's history. Fixed with an explicit manifest rule: a `project_id` is an
  exact string, never guessed/reconstructed/abbreviated from how someone refers to it in
  conversation - reuse a previously-confirmed one or call `list_projects` again.

---

## MCP considered as the primary tool-access layer - kept as secondary

**Date:** 2026-09-16 (discussion only, no code changed)
**Status:** Deferred, not implemented

**Question raised:** since this project's own agents call tools via direct in-process Python
function calls (not through the MCP server), and an MCP server does exist in the codebase for
external access - should the project's own agents also go through MCP, especially with an eye
toward scaling this to a company-wide deployment with many external consumers?

**Decision:** keep direct in-process calls as the primary path for this project's own agents;
MCP stays the secondary/external-facing interface. Not revisited as a code change - captured
here specifically so the reasoning isn't lost, since "why don't our own agents use our own MCP
server" is a reasonable question to get asked later.

**Why not switched:** no concrete scaling need had actually materialized yet at the time this
was discussed - the direct-call path is simpler, has less latency and fewer failure modes for
first-party in-process agents, and MCP's value (a standard interface for *external, arms-length*
consumers) doesn't add anything for tools an agent's own process already imports directly.
Worth revisiting if/when external consumers of this system's tools become real.

---
