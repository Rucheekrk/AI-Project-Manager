# Investor demo: your part (product walkthrough, 5 to 10 min)

Your manager opens, pitches and sets the premise. **You take over for the product demo, 5 to 10 minutes, then product questions.** Business questions (market, pricing, customers, funding, team, competitors) go back to your manager.
Anchor the whole demo on **halvane** (At risk). It has the best story and every number below was checked.

---

## 0. Before you start (do these in order)

1. `docker compose up -d`, then **restore** (clears chat, resets all four projects, puts the week-7 file back):
   `docker compose exec api python -m scripts.golden restore all`
2. Open `localhost:3010`. Settings > Theme > **Dark** (the Forloop logo is pale; it shows best on dark). Browser zoom 100 to 110%, window wide (the three-column tiles get cramped on a small window).
3. Close other tabs and notifications. Have these tabs ready: Dashboard, Workspace (halvane), Hours (halvane), AI Chat. **Registers is not shown** (manager's call: unfinished). Do not click it in the sidebar, and see the Dashboard note below.
4. Do **not** click Approve on any meeting: it creates a real Google Calendar event and sends invites to Nirmal, Ram and Rucheek. Show it pending and say so.
5. Keep the week-7 transcript as a spare: `datasets/golden/halvane/drop/drop-week7-sync.txt`. Only use it if asked "does it really read a transcript?". If you rehearse it, restore again afterwards.
6. Do not rehearse the AI Chat right before. Each restore clears the chat anyway.

**Numbers to have in your head (halvane, demo date 29 Oct 2026):** budget 920 h, 396 h logged, 524 h left, forecast **969 h = 49 h over**, status **At risk**. 2 tasks blocked. Plan grew **74 h** over the 820 h baseline (open banking scope added). Launch 4 Dec (week 12). Team of 8, with Kofi and Rucheek over capacity next week.
**Portfolio (dashboard):** 4 projects, 2 need attention, 3 blocked, 6 overdue, 9 open high-impact risks, 7 people over capacity.

---

## 1. The handover (about 15 seconds)

Your manager has already explained the problem. Do not repeat the pitch. Start with:

> "Thanks. Let me show you what that looks like on one project, halvane, which is at risk. The agent reads the files the team already has: the statement of work, the plan in Excel, meeting notes, timesheets. A person approves every change; nothing writes itself into the plan."

Then go straight to the Dashboard.

---

## 2. Run of show

Four screens, about 2 minutes each, so about 8 minutes with a little slack. If you only get 5 minutes, spend 1 minute on Dashboard and Hours, and 1.5 on Workspace and AI Chat.

| Min | Where | Say | Do |
|---|---|---|---|
| 0:15 | **Dashboard** | "Four projects. These tiles count what is wrong, not totals, so a healthy project cannot hide a troubled one." | Point at *Projects needing attention: 2*, *Blocked: 3*, *Overdue: 6*, *People over capacity: 7*. Click **halvane** inside *Projects forecast over budget*. **Do not click the high-impact risks tile: it opens Registers.** |
| 2:00 | **Hours** (halvane) | "920 hours budgeted, forecast 969. That is 49 over, and it is At risk because work is also behind plan. The status is computed, not typed in." | *Overview*: show the status and the forecast. Then click *Capacity* > *Show who is free*: "Kofi is over capacity next week and so is Rucheek." Point at the red cells (Kofi 48 of 36 h, Rucheek 33 of 32 h in the week of 2 Nov) |
| 4:00 | **Workspace** (halvane) | "The plan stays an Excel file in a folder; the app reads it. Two tasks are blocked, and the plan has grown 74 hours since the baseline." | Show the plan and the two blocked tasks. Open *Meetings*: one meeting is **proposed by the agent and waits for approval** (do not click Approve) |
| 6:00 | **AI Chat** | "Now plain English. It answers only from the project's data, and the reason for the blocks comes from here." | The three questions below |
| 8:00 | none | "Files in, a PM approves, everyone sees the same truth." | Stop sharing, take questions |

**Where the "why" now lives:** the vendor access and sandbox credentials reasons used to be shown in Registers. Now they come from AI Chat (question 1). Ask that one first and say it out loud: "the reason is the ID vendor has not granted production access, and the payment gateway has not issued sandbox credentials."

**AI Chat: use exactly these** (each passed 5 of 5 identical runs; free-form dates were the weak spot, so avoid "last week of October" style questions):
1. `What is blocked on halvane and why?` (answer: the two tasks, the vendor access and the sandbox credentials)
2. `Who is available for QA work on halvane in the next four weeks?` (answer: Jonas)
3. `Is the halvane project on track?` (answer: at risk, with the figures)

Spare: `What are the main risks on halvane?` and `Has the halvane plan changed since the baseline?` (74 h over 820).

**If something misbehaves:** do not debug live. Say "that is the live model; here is the same answer in the registers", and move on. If the page looks empty, restore (15 s).

---

## 3. If they ask to see "the AI do something"

Drop `drop-week7-sync.txt` into `projects/halvane/meetings/`. It reads the meeting and proposes plan changes (a task unblocked, a new SMS login task, the fraud model slipping a week) and a follow-up meeting for Friday. **Nothing changes until you approve.** Allow about a minute and do not do it unless asked; you have not timed it today.

---

## 4. Questions that are yours

### Product
- **"What about risks, owners, who is responsible?"** (Registers is not shown.) There are RAID and RACI registers and a deliverables list behind the app, and they feed the dashboard and the chat. That part is still being finished, so we kept today to the plan, the hours and the chat. Do not open it even if asked to; offer a follow-up.
- **Does it replace the project manager?** No. It does the assembling and flagging; a person approves every change to the plan and every meeting.
- **What does it actually read?** SOW, the Excel plan, meeting transcripts, timesheets, dropped in a folder per project.
- **What can it write to?** Its own plan (a backup of the previous version is kept), Jira (only after approval), Google Calendar (only after approval).
- **Why a folder and not a plug-in to our systems?** It works on day one with no integration project. Integrations are additive.
- **How is it different from Jira, Asana or MS Project?** Those record what people type in. This reads the artifacts that already exist and flags what is wrong across projects. It sits over those tools and syncs to Jira after approval; it does not ask a team to change tools.
- **Why now?** Language models can now read an unstructured transcript or SOW and produce structured changes reliably enough to review.

### Trust and accuracy (investors push here)
- **Do the answers hallucinate?** Chat answers come from tool calls on the project's own data, and it says "this app does not track that" for anything outside it. We measure it: **46 demo questions, each asked 5 times, all consistent.** We found and fixed real failures this way (wrong-year dates, a lifetime total quoted as a weekly figure).
- **Is it deterministic?** No LLM is 100%. What we guarantee is the facts match the data, and the plan only changes when a human approves.
- **What if it is wrong?** A person approves every change, so a wrong suggestion is rejected, not applied. The plan keeps a backup before every write.
- **How did you test it?** 446 automated tests, a separate test database, and a real-model check of the demo questions. It has been run on demo data only, not on a customer's.

### Data and security (answer honestly; this is the weakest area)
- **Is there login and access control?** **Not yet.** Today it is a single-tenant demo with no user accounts. Role-based access and SSO are designed and written up; they are the first thing built before a real client.
- **Where does the data go?** Project text is sent to a hosted language model (OpenAI) for reading and chat. The model layer is swappable (LiteLLM), so a client who needs a private or on-prem model can use one.
- **Is client data kept apart between clients?** Not yet; same answer as access control.

### Integrations
- **Jira / Calendar?** Both work and are gated by approval. Each was tested once against the real service this week: a Jira issue is created only after a plan change is approved, and a calendar event only after a meeting is approved.
- **Slack, Teams, email, Azure DevOps?** Not built. Folder drop covers them today. Order on the roadmap is a question for your manager.

### Hard questions, and honest answers
- **"Is this real data?"** No. The four projects are invented; three real people appear on them. The numbers are computed by the app from the data loaded.
- **"Why is the date 29 October?"** The demo date is frozen so answers repeat. In real use it is today's date.
- **"Tarnwood is On track but has 5 overdue tasks, why?"** The hours status looks at budget and work done, not individual deadlines. The dashboard's Overdue tile exists for exactly that gap; I would show it as the next thing to refine.
- **"What breaks?"** Chat on loosely worded date questions was the weak spot; we fixed the tools and re-measured. Anything outside the data returns "not tracked".
- **"What does a transcript cost to process?"** I have not measured an average cost per project, so I will not quote one.

---

## 5. Hand these to your manager

Say: **"My manager is better placed to answer that."** Do not improvise.
- Market size, target customer, competitors, moat
- Pricing and business model
- Customers, pilots, revenue, traction
- Team, funding, runway, use of funds
- Roadmap priorities beyond what is built

Agree with your manager beforehand who answers what, and how he wants you to signal a handoff.

## 6. Do not say
- "Fully autonomous" or "replaces PMs" (it needs approval, by design).
- "Secure" or "enterprise-ready" (there is no login yet).
- Any customer, revenue or market number.
- That Jira or Calendar are "integrated with your tools" beyond the one-time test.

## 7. Close
"Files in, one person approves, and everyone sees the same truth." Then hand back to your manager and stop talking.
