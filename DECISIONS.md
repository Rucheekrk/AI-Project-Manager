# Decisions Log

Why this file exists: a running record of the non-obvious calls made on this project - what
was decided, why, what alternatives were considered and rejected, and what's still pending.
The code shows *what* the system does; this file is for *why* it does it that way, so nobody
(including future us) has to reconstruct the reasoning from scratch or guess at it when
explaining the system to someone else.

Newest entries at the top. Each entry: the decision, the reasoning behind it, what was
considered and not chosen, and current status.

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
