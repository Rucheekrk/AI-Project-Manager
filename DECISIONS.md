# Decisions Log

Why this file exists: a running record of the non-obvious calls made on this project - what
was decided, why, what alternatives were considered and rejected, and what's still pending.
The code shows *what* the system does; this file is for *why* it does it that way, so nobody
(including future us) has to reconstruct the reasoning from scratch or guess at it when
explaining the system to someone else.

Newest entries at the top. Each entry: the decision, the reasoning behind it, what was
considered and not chosen, and current status.

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
