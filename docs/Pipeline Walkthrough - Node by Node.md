# Pipeline Walkthrough: Node by Node

Oct 27, 2026 · @Rucheek R Kashyap

Every document you submit passes through 10 nodes in a fixed order; each node reads a shared state object, adds to it, and hands it on. This document walks through each node with the same headings so you can revise one at a time. It was written from the code as it stands on 2026-10-27, not from memory. Three bugs found while writing it were fixed the same day; the last section lists them.

## Overview

**How a run starts.** The Extractor page (or `POST /run`) sends the text and a project id to the API. If the identical text was already processed for that project, the cached result is returned and the pipeline does not run (unless `force_run` is set). Otherwise a background thread runs the graph with a 10-minute cap, and the browser polls `GET /jobs/{id}` until it finishes.

**The shared state.** All nodes read and write one dictionary (`AgentState`, in `apps/state.py`). It lives only in memory for the duration of one run. The database is the only thing that persists, and only a few nodes write to it (Format above all).

| # | Node | Kind | LLM calls | Runs when | Main output |
| --- | --- | --- | --- | --- | --- |
| 1 | Supervisor | code, LLM only on conflict | 0 (1 on conflict) | every run | `document_type` |
| 2 | Extract | LLM | 1 per 15,000-character chunk | every run | `tasks` |
| 3 | Normalize | code + 1 LLM | 1 | every run (skips if no tasks) | `normalized_events`, `followup_signal` |
| 4 | Match | embeddings + LLM gate | 0 or 1 | every run | `events_to_create`, `events_to_update` |
| 5 | Planning | LLM agent with tools | about 2 to 7 | when there are tasks | `planned_tasks` |
| 6 | Format | code | 0 | every run | database writes, `final_output` |
| 7 | SOW Registers | code | 0 | SOW documents only | deliverables and RAID rows |
| 8 | Sync / Reporting | LLM agent with tools | 0 or about 2 to 6 | only if a task changed | Jira issues, Excel report |
| 9 | Meeting Coordinator | LLM agent with tools | 0 or about 2 to 9 | meeting minutes with a follow-up signal | a proposed meeting |
| 10 | Finalize | code | 0 | every run | completed `final_output` |

**How every node section is laid out:** what it does, how it does it, why it matters, input, output, when it runs, what happens when it fails, known weaknesses, and how it is tested. Weaknesses marked *(inferred)* come from reading the code and were not reproduced by running it.

## Node 1: Supervisor

The Supervisor labels the incoming document as a SOW or as meeting minutes (MoM) and does nothing else. File: `apps/supervisor.py`.

**What it does.** It sets one field, `document_type`, to `"sow"` or `"mom"`. It does not route the graph (the next node is always Extract); the label only decides whether two later steps run.

**How it decides.**

- The project has no active tasks yet: `sow`. A project's first document is assumed to be its SOW.
- The project has tasks and the text has no SOW wording: `mom`. SOW wording is a regex for "statement of work", "scope of work", "deliverable(s):" or "this agreement".
- The project has tasks and the text does have SOW wording: ask the LLM (the tie-break). It sees only the first 3,000 characters and returns `sow` or `mom` at temperature 0.

In normal use this node makes zero LLM calls: counting tasks is free.

**Why it matters.** The label gates two things: the SOW Registers node runs only for `sow`, and the Meeting Coordinator can run only for `mom`. Format also stores the label on the saved source document, and the RAID "Suggest from documents" feature uses it to tell the model what kind of document it is reading. A correction to an earlier explanation: Extract, Normalize and Match do not read the label at all. Match compares against existing tasks the same way for either type, even though a code comment describes SOW as "create" and MoM as "update".

**Input.** `raw_input` (the full text) and `project_id` from the state, plus one database read: the number of active tasks in the project.

**Output.** `document_type` written into the state. Consumers: SOW Registers, Meeting Coordinator, Format (saved with the document), the job record shown on the dashboard.

**When it runs.** First, once per run. It does not run on a cache hit, because the API returns the stored result before starting the graph.

**If it fails.** If the tie-break LLM call errors or returns something unusable, it logs the error and defaults to `mom`, so the run continues.

**Known weaknesses** *(inferred from the code)*:

- The first document in an empty project is always `sow`, even if it is meeting minutes. The Meeting Coordinator then cannot run on it.
- A SOW without the marker phrases, added to a project that already has tasks, is labelled `mom` and its registers step is skipped.
- Minutes that happen to say "this agreement" trigger the LLM call, and an error there defaults to `mom`.
- Only active tasks count. If every task was deleted or deactivated, the next document counts as a first one.
- The tie-break sees only the first 3,000 characters.

**Tests.** `eval/nodes/eval_supervisor.py` scored 9/9, but covers only the two free branches (the dataset's own file split is the answer key: `sow.txt` first, then `meeting-NN.txt`). No meeting file contains the SOW marker words, so the LLM branch is never exercised by real data. `tests/.../test_supervisor_tiebreak.py` checks, with a scripted LLM, that a valid answer passes through and an unparseable one defaults to `mom`.

**Demo line.** "It decides SOW versus minutes by whether the project already has tasks, and only asks an LLM when that conflicts with the document's wording."

## Node 2: Extract

Extract is the first LLM step: it reads the document and returns a flat list of candidate tasks. Files: `apps/nodes/extract.py`, prompt in `prompts/extract/prompt.py`.

**What it does.** It turns free text (a SOW, minutes, notes) into `[{"task": "...", "confidence": "high|medium|low"}]`. At this stage a task is only a sentence: no owner, deadline or status yet. Those come from Normalize.

**How it does it.**

- Documents up to 15,000 characters go to the model in one call.
- Longer documents are split into chunks of 15,000 characters with a 1,500-character overlap (so a task on a boundary appears whole in one chunk). Cuts prefer a sentence end within the last 200 characters.
- Chunks are sent to the model in parallel, then results are merged in chunk order.
- Merging drops near-duplicates created by the overlap: identical text after stripping punctuation, or a text-similarity ratio above 0.85.
- Each returned item must be an object with a `task`; the confidence is forced to high, medium or low (default medium).

**What the prompt tells the model.**

- Be conservative but recall-oriented: extract only tasks explicitly stated or strongly supported, but scan the whole text.
- A task is a clear unit of work someone can act on, not broken into sub-tasks.
- Do not extract agenda or narration ("we will discuss", "we will provide an update", "the board will review"). Returning an empty list is explicitly correct when no real work is present.
- Do not extract trivial admin that would not appear in a tracker: status reminders, follow-up reminders, scheduling a meeting, quick messages, logging notes.

**Why it matters.** Everything downstream works from this list. A task missed here is never created, and the later nodes cannot recover it. Match, the dedupe step and the registers all inherit its mistakes.

**Input.** `raw_input` only. It does not use `project_id` or the label from the Supervisor.

**Output.** `state["tasks"]`, the merged, de-duplicated list. Consumer: Normalize.

**When it runs.** Every run that reaches the graph.

**If it fails.** If one chunk's LLM call errors, that chunk returns an empty list and the others continue. The run still finishes as "completed", just with fewer tasks (silent partial result).

**Known weaknesses** *(inferred from the code unless noted)*:

- The model call does not request JSON mode; the reply is parsed with `json.loads`. If a model wraps JSON in a code fence, that chunk silently yields zero tasks.
- Task text is cleaned with `.strip()` outside the error handling. A non-string `task` value would raise and fail the whole run.
- The similarity merge (0.85) can drop two genuinely different tasks that are worded almost the same.
- Granularity is mixed. It extracts whatever the document states, large deliverables and small actions side by side; it does not break tasks down, and the planning step deliberately does not either.
- Admin exclusions are a judgment encoded in the prompt: a real follow-up that is phrased as a reminder is dropped on purpose.

**Tests.** As of `DECISIONS.md` there is no node-level eval for Extract, because it would need hand-written intermediate answer keys that do not exist. It is covered by the end-to-end eval (`eval/run_eval.py`, which compares the final task list to the golden list). `tests/unit/test_chunking.py` tests a different splitter (the 1,000-character one used for chat search in `apps/utils/chunking.py`); Extract's own 15,000-character splitter has no unit test.

**Demo line.** "One LLM pass turns the text into candidate tasks; long documents are split into overlapping chunks and merged."

## Node 3: Normalize

Normalize turns each bare task sentence into a structured record (owner, status, deadline, blocker, dependency) and flags whether a follow-up meeting might be needed. Files: `apps/nodes/normalize.py`, prompt in `prompts/normalize/prompt.py`, helpers `apps/utils/abbreviations.py` and `apps/utils/deadline.py`.

**What it does.** For every task from Extract it produces one event with `task_text`, `owner`, `status`, `deadline`, `blocker`, `dependency` and `confidence`. It also returns one document-level boolean, `followup_signal`.

**How it does it, in order.**

1. **Abbreviation expansion (code).** A fixed map (CI/CD, K8s, ETL, UAT, QA, DB and so on) is applied to each task's text before the LLM sees it.
2. **One LLM call (whole document).** The model gets the full raw text plus the full task list and fills the fields. Rules: fill a field only if the text explicitly supports it, never invent, rewrite the task to be short and action-oriented, strip wrapper phrases ("mark X as completed" becomes "X"), keep one output per input task. Allowed statuses: not\_started, in\_progress, completed, blocked, on\_hold.
3. **Cleaning (code).** Events with empty text are dropped, confidence is forced to high/medium/low, empty strings become null.
4. **Deadline resolution (code).** Natural-language deadlines are converted to ISO dates by `resolve_deadline`, using today's date.
5. **Follow-up signal.** The model is told to lean toward true if there is any hint of "let's reconvene", an unresolved decision, or a blocker needing discussion. It is a cheap pre-filter; the Meeting Coordinator makes the real decision.

**Why it matters.** This is where the free-text task becomes data the rest of the system can filter, sort and update. The status and deadline fields set here drive later updates to existing tasks. The `event_type` is deliberately not decided here: Match infers it after it knows whether the task already exists.

**Input.** `tasks` (from Extract) and `raw_input`.

**Output.** `normalized_events` (list of structured events) and `followup_signal` (true/false). Consumer: Match; the signal is read later by the Meeting Coordinator.

**When it runs.** Every run. If Extract found no tasks it returns an empty list and `followup_signal = false` without calling the model.

**If it fails.** If the LLM call errors, it sets `normalized_events` to an empty list and `followup_signal` to false and the run continues. Nothing is created, yet the run still reports "completed".

**Known weaknesses.**

- **Deadline bug, fixed 2026-10-27.** The old `resolve_deadline` read any digit as a day of the current month, and matched "end of Week 2" to its "end of week" rule. So "end of Week 2" and "end of Week 8" both became the coming Friday, and "Week 7" became the 7th. Now a deadline becomes a date only if the text holds a real calendar date ("April 14", "14 April", "2026-05-12", "5/12/2026") or a relative word (today, tomorrow, next Monday, EOW, EOM). Plan positions ("end of Week 2", "Sprint 4", "Q2") and durations ("in 3 days") keep their original wording. A real date next to a plan reference wins ("Week 6, May 12, 2026" becomes 2026-05-12). Dates stored before the fix were not corrected: in `forloop`, two tasks still share 2026-09-25 and the Week 7 task still shows 2026-09-07.
- **Abbreviation bug, fixed 2026-10-27.** Matching was case-insensitive for every entry, so the ordinary words "was" and "be" were rewritten to "WebSphere Application Server" and "Backend". Entries that are also ordinary words or titles (WAS, BE, FE, HA, DR, LB, IDE, SLA) now expand only when written in upper case. Trade-off: a lower-case "ha cluster" is no longer expanded to High Availability.
- Relative dates ("tomorrow", "next Monday") are still resolved against the day the document is processed, not the date of the meeting. Minutes processed days late get shifted dates. A bare day ("by 15th") or a month and year ("April 2026") keeps its wording, by design.
- Status is not checked against the allowed list in code; the prompt asks for it but a free-text status would pass through *(inferred)*.
- The whole document goes to the model in one call, with no chunking, so a very long document could exceed the model's limits *(inferred)*.
- Nothing checks that the number of outputs matches the number of inputs; a task the model skips is simply lost *(inferred)*.

**Tests.** No node-level eval of the model's output. The two helpers now have regression tests: `tests/unit/test_deadline_resolution.py` (43 cases, including every phrase that was wrong before) and `tests/unit/test_abbreviations.py` (13 cases). Both fail against the old code and pass against the fix. `tests/unit/test_deadline_parsing.py` tests a different function, the calendar's date-window helper.

**Demo line.** "Normalize enriches each task with owner, status and deadline, and turns date phrases into real dates. A phrase like 'end of Week 2' is kept as written, because there is no real date to resolve." Deadlines stored for `forloop` before the fix are still the old, wrong ones.

## Node 4: Match

Match decides, for each task mention, whether it is a new task or an update to a task already in the project. This is the node that stops the task list filling with duplicates. File: `apps/nodes/match.py`.

**What it does.** It compares every normalized event with the project's existing active tasks and labels it either *matched* (an update to task X) or *new*. For matched events it also infers an `event_type`: status\_change, blocker, dependency, deadline\_change, owner\_change or task\_update, in that priority order, based on which fields the event carries. An unmatched event is `new_task`.

**How it does it, in two passes.**

1. **Exact pass.** Lower-case the text and strip punctuation; if it equals an existing task's text, it is matched with method "exact" and no further work.
2. **Semantic pass, for everything else.**
   - **Propose.** A local embedding model (`all-MiniLM-L6-v2`, 384 numbers per text, no API call) turns each mention into a vector. Cosine similarity ranks existing tasks. The top 3 with similarity at least 0.65 become candidates. Up to 2 more are added if one text contains the other (shorter side at least 3 words), whatever their similarity.
   - **Decide.** One batched LLM call (the "gate") sees every mention with its lettered candidates plus owner, status and deadline as hints, and answers *same* (with the candidate letter), *different*, or *unsure* for each. The test it applies: would a project manager track these as one line item or two?
   - **Apply.** *Same*: matched, method "semantic", confidence from the similarity (0.85 or more high, 0.65 or more medium). *Different*: new task. *Unsure*: new task, flagged `llm_unsure`, and linked to the most similar existing task as a possible duplicate. If the gate says different but the top candidate scored 0.85 or more, the new task is also flagged as a possible duplicate ("rejected\_high\_similarity"). If the gate gave no answer (error), the mention becomes a new task.

**Why it matters, and why there is an LLM gate.** Cosine similarity cannot separate "the same task reworded" from "a different action on the same feature". Measured false positives scored 0.66 to 0.90, overlapping real paraphrases, so no threshold fixes it. Previously, fuzzy and containment matching could also accept a wrong match before the semantic step ever ran. The design principle is that a wrong merge (two different tasks collapsed into one, losing information) is worse than a visible duplicate, so every doubt resolves to "new task", and the doubtful ones are flagged for a person. Embeddings only propose; the LLM decides.

**Input.** `normalized_events` and `project_id` from the state, plus the project's active tasks and their stored embeddings from the database.

**Output.**

- `matched_events`: every event with `is_matched`, `matched_task_id`, `match_method` (exact / semantic / llm\_unsure), `match_confidence`, `event_type`, and optional `possible_duplicate_of` / reason.
- `events_to_update` (matched ones) and `events_to_create` (the rest). Consumers: Planning and Format.
- `unresolved_events` is always an empty list now; the "force-match" concept was removed, and the comments in Format that mention "4 match stages" are stale.

**When it runs.** Every run. In the first document of a project there are no stored embeddings, so everything is new.

**If it fails.** If the gate call errors, no mention is merged (all become new tasks). If embedding fails for a text, that mention becomes a new task.

**What was measured** (`DECISIONS.md`; the answer key is the synthetic VMware dataset, with the 19 paraphrase labels written by Claude and still awaiting your review):

- On a fixed seeded database, the live logic (gate plus containment candidates), repeated three times, scored: exact-twin updates 21/21, paraphrased updates 14/15, wrong-target 0, genuinely new tasks kept as new 63-64 of 66, about 3 to 4 errors total.
- With the gate switched off the same test gave 12 errors, and the old 3-stage logic (rebuilt for comparison) also 12. The gate cuts the errors to about a third (3 to 4 versus 12), almost entirely by avoiding wrong merges of new tasks.
- The one persistent miss is a paraphrase scoring 0.62 cosine, below the 0.65 floor, so the gate never sees it. Lowering the floor would surface it but, as measured, costs more than it gains.
- The data is scripted, and the gate's model choice is nondeterministic by about one item between runs.

**Known weaknesses.**

- Recall of true updates is capped by what the 0.65 floor and the 3-candidate limit let the gate see.
- Tasks mentioned twice inside the same document are compared against the database only, not against each other; Format's dedupe guard is what catches those.
- The gate prompt is a judgment call. Tuning it further was judged to be fitting noise.
- The gate model defaults to the app-wide model (gpt-4o-mini) unless `MATCH_GATE_MODEL` is set. Stronger models were tried (gpt-4.1, gpt-4o, gpt-5-mini, gpt-5) and all made more wrong merges, mostly by treating the next lifecycle step of a deliverable as the same task, so the cheaper default stayed.
- Tasks flagged as possible duplicates are reviewable in the Workspace (merge or "not a duplicate"); nothing else catches a wrong *new* decision.

**Tests.** `tests/db/test_match_gate.py` and related tests cover the gate, containment candidates and flags with a scripted LLM. End-to-end behaviour is measured by `eval/nodes/eval_match_seeded.py` (fixed starting state, target-correct scoring) and `eval/nodes/eval_match.py` (full pipeline).

**Demo line.** "Embeddings find look-alikes, an LLM decides if they are really the same task, and when in doubt it keeps both and flags it."

## Node 5: Planning

Planning gives every task touched in this run a priority and finds dependencies between tasks. It is the first node that is an *agent*: an LLM that can call tools and reason in a loop. Files: `apps/nodes/planning_node.py` (thin wrapper), `apps/agent/planning.py` (the agent), `apps/agent/react_loop.py` (the shared loop), `apps/agent/tool_registry.py` (its tools), `apps/agent/manifests/planning.md` (its job description).

**What it does.** For each task it returns a priority (high, medium or low), a deadline if one is supported, and, when it sees one, which other task this one depends on. It does not break tasks into sub-tasks; a `decompose` step was tried and deliberately removed.

**How it does it.**

- The node collects every task from `events_to_create` and `events_to_update` (new and changed this run) with owner, deadline, blocker, dependency hint and confidence.
- The agent runs a ReAct loop: the model may call tools, sees the results, and decides again, up to 5 tool calls, then must answer in JSON. Temperature is 0.
- Its tools, each scoped to this agent only: `check_owner_availability` (Google Calendar, to ground a deadline), `search_tasks` and `get_task_by_id` (look at other tasks in the project), and `record_dependency` (writes a dependency link between two existing tasks directly to the database).
- Rules in its prompt: high = urgent, foundational, or blocking several tasks; low = final verification (QA, UAT, sign-off) or post-setup work; a prerequisite must have equal or higher priority than what depends on it; set a deadline only if the text gives one or the calendar suggests one; for a dependency between two brand-new tasks, return `depends_on_task_text` instead, because neither has an id yet.

**Why it matters.** It is the only step that looks across tasks. It is what makes the Workspace show meaningful priorities and what builds the dependency graph. It replaced an older prioritize, validate and refine chain with one self-checking loop.

**Input.** `events_to_create` + `events_to_update` and `project_id`.

**Output.** `planned_tasks`: a list of `{task, priority, deadline, depends_on_task_text}`, and `planning_trace`: the list of tool calls it made, shown in the dashboard's trace panel. Consumer: Format, which turns priority into a stored field and `depends_on_task_text` into dependency links. Important: the deadline Planning returns is shown in the run result only; Format stores the deadline that Normalize found, not Planning's.

**When it runs.** Every run. If there are no tasks to plan it returns immediately without calling the model.

**If it fails.** Three safety nets keep a bad model answer from stopping the pipeline. An exception gives every task priority "medium" with its original deadline; an empty or unusable answer does the same; an invalid priority value on one task becomes "medium".

**Known weaknesses** *(inferred from the code unless noted)*:

- Format matches Planning's output back to tasks by exact normalized text. The prompt says "include every task, in the same order" but does not require the text to stay word for word; if the model rewrites a task's text, that new task silently gets the default priority "medium".
- Priority is rewritten for every matched task on every run, so a priority a person edited in the UI can be overwritten the next time a document mentions that task.
- `search_tasks` is scoped to a project only if the model passes the project id to the tool; the code does not force it.
- `record_dependency` writes immediately with no check beyond the prompt's instruction not to guess.
- Calendar-based deadline help needs Google Calendar configured. In the personal-account (OAuth) setup it can only see the connected account's own calendar, so for other people it usually answers "unavailable to check".
- The fallback paths are not identical: one omits `depends_on_task_text`.

**Tests.** The loop and tool-calling mechanics have scripted-LLM unit tests. There is no node-level eval of the quality of the priorities or dependencies, since that needs hand-labelled answers that do not exist.

**Demo line.** "Planning is a small agent that looks at the rest of the project, sets priorities, and records which task blocks which."

## Node 6: Format

Format is where the run's results are actually saved: new tasks are inserted, existing tasks are updated, and an audit trail is written. It is plain code with no model calls. File: `apps/nodes/format.py`.

**What it does, in order.**

1. **Store new tasks.** For each event in `events_to_create`: look up the priority Planning chose (by normalized text; default "medium"), default the status to "not\_started", and make sure the owner exists in the project's people list (a comma-separated owner is split into separate people). Then two last-chance duplicate guards run before inserting. (a) Exact normalized text already in the project: treat it as an update, not a new row. (b) Embedding similarity of 0.85 or more via the database (skipped if the Match gate already ruled on this mention). If neither applies, the task is inserted (its embedding is computed at that moment, so later runs can match against it) and, if Match flagged it, a possible-duplicate link is saved.
2. **Store events.** The source document is saved once (keyed by a hash of its text plus the project, with its type), and every matched event is appended to `task_events` as an audit record pointing at that document.
3. **Apply updates.** For each matched event it writes the field that event is about: status\_change writes status, deadline\_change writes deadline, owner\_change writes owner, blocker writes blocker, and task\_update writes any populated field. Priority from Planning is re-written for every matched task.
4. **Log unresolved events.** A legacy path; the list is always empty now.
5. **Record dependencies.** Planning returns `depends_on_task_text` as text because new tasks had no ids yet. Now that tasks exist, the text is resolved to ids (in this run's tasks, otherwise an existing task with that text) and a dependency link is written.
6. **Build `final_output`.** A summary for the API: task count, the tasks with priority and deadline, the non-new events ("event signals"), the Planning trace, and status "completed".

**Why it matters.** It is the only node that makes the run's decisions permanent, and it must run before Sync/Reporting and the Meeting Coordinator because those need the real task ids created here. The audit table `task_events` is what lets you see how each task changed over time.

**A side effect worth knowing.** Saving a source document also splits it into 1,000-character overlapping chunks and stores an embedding for each. The AI Chat's document search reads those chunks, so "search the documents" in chat works only for text that went through Format.

**Documents with no tasks are not saved.** If a run produces no matched events, Format returns before storing the source document. Such a document is therefore invisible to chat search and to the RAID suggester, and is not cached, so submitting it again repeats the whole run.

**Input.** `events_to_create`, `matched_events`, `planned_tasks`, `unresolved_events`, `raw_input`, `document_type`, `project_id`.

**Output.**

- Database writes: `tasks`, `task_events`, `source_documents`, `project_people`, `task_dependencies`.
- In the state: matched events enriched with the new task ids, and `final_output` (completed later by Finalize).

**When it runs.** Every run.

**If it fails.** A single task insert that errors is logged and skipped while the rest continue. The update and dependency steps have no per-item error handling, so an unexpected database error there would fail the run *(inferred)*.

**Known weaknesses.**

- **Blocker events blanked the status, fixed 2026-10-27.** A "blocker" event only occurs when the document gave no status, and the old code wrote that empty status into the task. It now sets the status to "blocked" (or keeps a status the event does state). Rows stored before the fix were not repaired: in `forloop`, "Review VPN access resolution" still has a blank status.
- Dependency-type events are logged but change nothing on the task; dependency links come only from Planning.
- Planning's priority is matched by exact text (see Planning), and every matched task has its priority overwritten each run.
- The Planning deadline in `final_output` can differ from the deadline actually stored, which can confuse anyone comparing the run result to the Workspace.
- Comments in the file still describe the removed four-stage matcher and a 0.55 threshold; the code uses a 0.65 floor and two stages plus the gate.
- The `task_events` table is large (about 3,500 rows in this database) because every matched event of every run is appended, including repeated verbatim mentions.

**Tests.** Covered mainly by database-level tests in `tests/db/` (insertion, dedupe guards, duplicate flags and merging), by `tests/db/test_blocker_update.py` (the blocker fix: 2 tests) and by the end-to-end eval. Because it is deterministic code it has no model-quality eval.

**Demo line.** "Format is the commit step: save new tasks, apply updates to existing ones, keep an audit trail, and link dependencies."

## Node 7: SOW Registers

SOW Registers copies the explicit lists a SOW sometimes contains (a numbered Deliverables section, and numbered Assumptions and Dependencies lists) into the Registers page. It is plain code with no model calls, and it is an optional bonus rather than a core step. Files: `apps/nodes/sow_registers_node.py`, parsers in `apps/utils/deliverables.py` and `apps/utils/sow_sections.py`.

**What it does.** For a SOW only, it looks for two things in the raw text and stores what it finds:

- A section headed "Deliverables" with at least two dotted-number items (4.1, 4.2, ...). Each item may be followed by `Owner:` and `Deadline:` lines. These become rows in the Deliverables register, marked as coming from the document.
- Sections headed "Assumptions" and "Dependencies" containing numbered items. These become RAID log items of type assumption and dependency, marked "From the SOW". They count as confirmed because they are explicit statements in the document, not guesses.

**How it does it.** Line-by-line pattern matching: find the heading, read numbered items, stop at the next heading or separator. If the text is messy (bullets, PDF extractions where numbers are split from their text) it returns nothing rather than guess. Re-runs are safe: a deliverable whose number already exists in the project is left untouched (so a person's edits are never overwritten), and RAID items carry a per-document key so the same document never adds them twice.

**Why it matters.** It fills the registers for free, with no cost or hallucination risk, when a SOW is written in that clean style. It also keeps the system honest: every item it creates is something the document literally says. Its honest limit is that it only helps for such SOWs. Running both parsers on the six sample SOWs in the repo: only the synthetic VMware SOW has a numbered deliverables section (11 items) and numbered assumptions and dependencies (15 items); one other input yields 9 assumptions and dependencies and no deliverables; the other four, including the `forloop` SOW, yield nothing, so for them this node does nothing.

**Input.** `document_type`, `raw_input`, `project_id`.

**Output.** Database rows in `deliverables` and `raid_items`. It changes nothing in the state; no other node reads its result. The Registers page shows the rows.

**When it runs.** Only when the Supervisor labelled the document `sow`. Meeting minutes pass straight through.

**If it fails.** The two parts are wrapped separately; an error in one is logged and neither the other part nor the run is affected.

**Known weaknesses.**

- It depends on the Supervisor's label: a SOW labelled `mom` (see Supervisor weaknesses) is skipped.
- It only recognizes the exact heading words and numbering styles it was written for.
- It covers only what the document states explicitly. Risks, issues and anything implicit in the text are not found here; that is the job of the separate, on-demand "Suggest from documents (experimental)" button, which uses an LLM and has every suggestion reviewed by a person.
- Because it never overwrites, a changed deliverable in a revised SOW does not update the existing row.

**Tests.** Unit tests for both parsers (`tests/unit/test_deliverable_parser.py`, `tests/unit/test_sow_sections_parser.py`) and database tests for the idempotent import (`tests/db/test_deliverables.py`, `tests/db/test_registers.py`).

**Demo line.** "If the SOW has numbered deliverables, assumptions or dependencies, they land in the Registers automatically, with no AI involved."

## Node 8: Sync / Reporting

Sync / Reporting pushes tasks that changed in this run to Jira and regenerates a task export. It is a small agent that runs only when something actually changed. Files: `apps/nodes/sync_reporting_node.py`, `apps/agent/sync_reporting.py`, manifest `apps/agent/manifests/sync_reporting.md`, tools `mcp_server/tools/jira.py` and `mcp_server/tools/report.py`.

**What it does.** It creates a Jira issue for each task that is new or changed, and writes a report file (markdown, JSON or Excel) of the project's tasks.

**How it does it.**

1. **Cheap trigger (code).** The node checks the state: it runs the agent only if there are new tasks, or any matched event that is not a plain "new\_task". Otherwise it is skipped at zero cost.
2. **Agent.** The model receives the project id and the list of touched tasks (id, text, event type, owner, status) and has two tools: `sync_task_to_jira` and `generate_report`, with a budget of 4 tool calls. The project id for Jira is fixed in code, not supplied by the model, so the model cannot send tasks to the wrong project.
3. **Jira tool.** It needs three Jira settings in `.env` (site URL, email, API token) and a Jira project key mapped to the project. If either is missing it returns "not configured". It never creates a second issue for the same task (a stored issue key makes repeat calls return "already synced"). The owner's name is looked up as a Jira user; if not found the issue is created unassigned.
4. **Grounding check (code).** The model's own summary is not trusted: the final result (`jira_synced`, `report_generated`, `report_path`) is rebuilt from what the tool calls actually returned, and a mismatch is logged and corrected.

**Why it matters.** It is the bridge to the team's real tracker, and the one step with an external side effect. The trigger and the grounding check exist so that a no-op run costs nothing and the dashboard never reports a sync that did not happen.

**Input.** `events_to_create`, `matched_events`, `project_id` (all read from the state; tasks need the ids created by Format, which is why Format runs first).

**Output.** `sync_reporting_triggered`, `sync_reporting_trace` (tool calls) and `sync_reporting_result` in the state; Finalize copies them into the run result. Side effects: Jira issues, and a file in the `reports/` folder.

**When it runs.** Every run reaches the node, but the agent runs only when the trigger fires. A document that merely repeats existing tasks with no new or changed field skips it.

**If it fails.** If the agent errors it returns an empty result and the run continues. If Jira is not configured the tool reports that and nothing is created.

**Current state of this installation.** Jira is connected for two projects: `forloop` (key FLP, 19 of its 23 tasks already have a Jira key) and `vmware-sim` (key VMW, none synced). A run on `forloop` that creates tasks will create real issues in that Jira site, so avoid re-running documents there casually during a demo.

**Known weaknesses.**

- **Create-only.** The tool only creates issues. A task already synced is never updated, so later status, owner or deadline changes in this app do not reach Jira *(confirmed by reading the code: there is no update path)*.
- The list sent to the agent contains every matched task, not only truly changed ones, and the budget of 4 tool calls may limit how many get synced if the model calls tools one at a time *(inferred)*.
- Whether to sync a given task is left to the model's judgment, so two runs can behave differently.
- Jira failures come back as text inside the trace; nothing alerts a person that a sync failed.

**Tests.** `tests/db/test_jira_sync.py` covers the Jira tool (an already-synced task skips the HTTP call, the assignee lookup, the unassigned fallback) with the web call stubbed, and `tests/pipeline_logic/test_react_loop_*.py` cover the shared agent loop. I found no tests of the trigger function or of the grounding check, no test against a live Jira, and no quality eval.

**Demo line.** "If anything changed, an agent pushes it to Jira and refreshes the export, and the system double-checks the agent's own report."

## Node 9: Meeting Coordinator

The Meeting Coordinator reads meeting minutes, decides whether a follow-up meeting is really needed, and if so *proposes* one for a person to approve. It never creates a calendar event by itself. Files: `apps/nodes/meeting_coordinator_node.py`, `apps/agent/meeting_coordinator.py`, manifest `apps/agent/manifests/meeting_coordinator.md`, tools in `mcp_server/tools/calendar.py`.

**What it does.** It confirms a follow-up is warranted (an unresolved decision, an explicit "let's reconvene", or a blocker needing discussion; not merely a date mentioned in passing), works out who should attend, picks a time, and stages a proposal. A person then approves or rejects it in the app.

**How it does it.**

1. **Gate (code).** The agent runs only if the Supervisor said `mom` and Normalize's `followup_signal` was true. Otherwise the node sets "not triggered" and the run moves on.
2. **Agent.** The model gets the full minutes and the project id. It is told today's date (computed fresh on every call, so "next week" is resolved from the real current date) and has three tools, with a budget of 8 tool calls:
   - `resolve_attendees`: maps names to email addresses from the project's people list. A name that does not resolve is reported, never guessed or dropped.
   - `check_owner_availability`: reads Google Calendar. With a personal-account connection it can only see that one account's calendar, so "unavailable to check" is the expected, common answer and must not block scheduling.
   - `propose_meeting`: stages the meeting. It does not touch Google Calendar and notifies nobody.
3. **Grounding check (code).** The result's `scheduled_meeting` is taken from the tool call that actually succeeded, never from what the model claims. A claim with no successful `propose_meeting` call is dropped.
4. **Persist.** A real proposal is saved to the database with status "pending approval", with the unresolved names and the reason.
5. **Human approval.** On the Workspace's Meetings tab a person approves or rejects. Only approval creates the Google Calendar event and emails the attendees (`POST /meetings/{id}/approve`). A rejected proposal can never have a calendar event id.

**Why it matters.** Sending calendar invites to real people is hard to undo, so the design puts a human gate in front of the only step that does it. The two-stage trigger (cheap flag from Normalize, then the agent's own judgement) keeps the cost low while letting the agent overrule an over-eager flag.

**Input.** `document_type`, `followup_signal`, `raw_input`, `project_id`.

**Output.** In the state: `meeting_coordinator_triggered`, `meeting_coordinator_trace`, and `scheduled_meeting` (a *proposal*; the name is historical). In the database: a pending meeting row. Consumers: Finalize (copies into the run result) and the Meetings tab.

**When it runs.** Only for meeting minutes with a positive follow-up signal. It never runs for a SOW.

**If it fails.** If the agent errors, the result is "follow-up not warranted" with the error as the reason, nothing is proposed, and the run continues.

**Known weaknesses.**

- Normalize is told to lean toward true, so the agent is often invoked just to say no. That costs LLM calls without output.
- The proposed time is a reasonable guess (for example next business day mid-morning), because attendee availability usually cannot be checked.
- An attendee can be resolved only if the project's people list has their email. People auto-created from task owners have no email until someone adds it, so many names end up "unresolved".
- The date arithmetic is the model's; the injected "today" helps but does not guarantee it.
- I found no check that stops a re-run of the same minutes from staging a second, similar proposal *(inferred)*.
- Minutes that were mislabelled `sow` by the Supervisor never reach this node.

**Tests.** `tests/pipeline_logic/test_react_loop_budget.py` (a regression test: a budget of 4 ran out before the proposal call, so it was raised to 8), `tests/db/test_meeting_approval.py` (a new proposal starts pending with no event id; approval sets one; rejection never produces one) and `tests/db/test_people_placeholder.py`. No test of whether the agent's "warranted or not" judgement is right.

**Demo line.** "After minutes, an agent can suggest a follow-up meeting, but a human has to approve it before anyone gets an invite."

## Node 10: Finalize

Finalize is the last step: it adds the results of the two conditional agents to the run's summary. It is 25 lines of plain code. File: `apps/nodes/finalize_node.py`.

**What it does.** It takes the `final_output` that Format built earlier and adds six fields to it: whether Sync/Reporting ran, its trace and result, whether the Meeting Coordinator ran, its trace, and the proposed meeting.

**How it does it.** One dictionary update with defaults (false, empty list, null) for anything that did not run. No database access, no model call.

**Why it matters.** Format has to run before the two agents (they need the task ids it creates), so at that point their results do not exist yet. Finalize is the single place where the complete result is assembled, which keeps Format and the agents independent of each other.

**Input.** `final_output` plus the six sync and meeting fields in the state.

**Output.** The finished `final_output`, which holds: `tasks_count`, `tasks` (task, priority, deadline), `event_signals` (events that were updates, not new), `unresolved_events` (always empty now), `planning_trace`, `status`, and the six fields above. After the graph returns, the API adds `document_type`, stores the result on the job record, and returns it when the browser polls `GET /jobs/{id}`. The Extractor page and the dashboard's trace panel read it.

**When it runs.** Every run, last.

**If it fails.** There is almost nothing in it that can fail. Any error from an earlier node that is not caught internally ends the whole run as "failed" before this point.

**What happens after the graph.** If the run produced at least one task (`tasks_count` above 0), the API stores the result in a cache keyed by the document's hash and project, so submitting the identical text again returns instantly without running anything. A run that produced no tasks is not cached.

**Known weaknesses.**

- `final_output` is a loose dictionary, not a typed structure, so a renamed field would silently break the screens that read it *(inferred)*.
- The run result is a snapshot. The Workspace shows the live database state, which can differ from it (for example Planning's deadline versus the stored one).
- A cached result is returned without running anything, so a changed model, prompt or code does not take effect for a document that was already processed unless `force_run` is used.

**Tests.** No dedicated test; its behaviour is exercised by the end-to-end eval.

**Demo line.** "Finalize assembles the complete run report: what changed, what the agents did, and what is waiting for approval."

## Across the pipeline: corrections, confirmed bugs, demo Q&A

While writing this walkthrough I ran the code and checked the stored data, and found three real bugs plus two corrections to things I told you earlier. All three bugs were fixed on 2026-10-27 with regression tests (203 tests pass, 58 of them new). The wrong values already stored in the `forloop` project were left as they are.

### Bugs found, now fixed

| # | Where | What went wrong | Evidence | Fix (2026-10-27) |
| --- | --- | --- | --- | --- |
| 1 | Normalize, `resolve_deadline` | "Week N", "Q2", "Sprint 4" and "in 3 days" became wrong concrete dates: a digit was read as a day of the current month, and "end of Week N" matched the "end of week" rule. | Ran the function; in `forloop` two tasks due weeks apart share 2026-09-25 and the Week 7 task is 2026-09-07. | A date is produced only from a real calendar date or a relative word; plan positions and durations keep their wording. 43 tests. |
| 2 | Normalize, `expand_abbreviations` | Matched case-insensitively, so ordinary words were rewritten: "was" became "WebSphere Application Server", "be" became "Backend". | Ran the function on sample phrases. No stored task was affected. | WAS, BE, FE, HA, DR, LB, IDE and SLA expand only in upper case. Lower-case "ha" no longer expands. 13 tests. |
| 3 | Format, blocker events | A blocker event overwrote the task's status with an empty value. | `forloop`: "Review VPN access resolution" has a blank status and a blocker text. | The status is set to "blocked" when the event has none. 2 tests. |

Also worth knowing, not bugs: Planning's deadline is shown in the run result but not stored; a document that yields no tasks is not saved at all (so chat search and the RAID suggester cannot see it); and Sync / Reporting only creates Jira issues, never updates them.

### Corrections to what I told you earlier

- **The MCP server container is not used by the app.** I described it as a tool shelf the agents call. In fact the agents import the same tool functions directly in Python (`apps/agent/tool_registry.py`), and nothing in `apps/` or the frontend connects to the MCP server. The container exposes the same tools to outside MCP clients and is otherwise idle. If asked, say the agent tools are in-process and the MCP server is an optional external interface.
- **The Supervisor does not make Match behave differently for SOW and minutes.** Only SOW Registers and the Meeting Coordinator use the label.

### Where the LLM is and is not used

| Step | LLM? | Calls per typical run |
| --- | --- | --- |
| Supervisor | only on a conflict | 0 |
| Extract | yes | 1 (more for very long documents) |
| Normalize | yes | 1 |
| Match | yes, the gate | 0 or 1 |
| Planning | yes, with tools | about 2 to 7 |
| Format, SOW Registers, Finalize | no | 0 |
| Sync / Reporting | agent, only if something changed | 0 or more |
| Meeting Coordinator | agent, minutes with a follow-up flag | 0 or more |

All model calls go through one function (`apps/llm.py`), so the provider and model are configuration (`LLM_MODEL`, default gpt-4o-mini). The match gate can use its own model (`MATCH_GATE_MODEL`) and the RAID suggester uses gpt-4.1 by default.

### Likely demo questions

- **How do you avoid duplicate tasks?** Three layers: exact-text match, embeddings plus an LLM judge in Match, and two last-chance guards in Format. Doubtful cases are kept as separate tasks and flagged for review, because a wrong merge is worse than a visible duplicate.
- **Does it send anything out automatically?** Jira issues are created automatically for connected projects (create-only). Calendar invites are never sent without a person approving the proposed meeting.
- **Where does our document go?** The text is sent to the configured model provider (OpenAI by default) for each LLM step, and stored in your own Postgres.
- **How accurate is it?** Measured only on a synthetic, scripted dataset. Match is the best measured part (about 3 to 4 errors in roughly 100 judgements on the fixed-state test). Extract, Normalize and Planning have no node-level accuracy measurement.
- **Is it deterministic?** Calls use temperature 0, but extraction still varies a little between runs; the same document can yield a slightly different task list.
- **What breaks if a model call fails?** Every LLM step catches its own errors and returns empty or default results so the run completes, which also means a failure can show up as "completed with fewer tasks" and not as an error.

### Safest demo path

Use a project with no Jira key (not `forloop`) or expect real Jira issues. Show Match by submitting the SOW and then minutes in the same project, and the possible-duplicate review in the Workspace. New runs keep "Week N" deadlines as written, but deadlines already stored for `forloop` still show the old wrong dates, so do not use that project to show deadlines. Wait a minute after any restart before the first click.
