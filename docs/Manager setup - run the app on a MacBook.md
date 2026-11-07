# Run the Agentic Project Manager on your MacBook

This gets the app running on your own Mac, from the Forloop GitHub repository, with four demo projects (invented data). Allow about 30 minutes the first time, mostly waiting for downloads. After that, getting the latest version takes about a minute.

## What you need
- A MacBook (Apple chip or Intel) with an internet connection.
- **Docker Desktop**: download from docker.com. Pick the version that matches your Mac: Apple menu > About This Mac shows "Chip: Apple M..." or "Processor: Intel". Install it, open it, and wait until it says it is running (a whale icon in the menu bar).
- **Git**: open Terminal (press Cmd+Space, type Terminal) and run `git --version`. If a window offers to install developer tools, accept and wait.
- **An OpenAI API key** (yours). The app sends project text to OpenAI to read files and answer chat questions. Demo use costs very little. Do not share the key or put it anywhere except the `.env` file in step 3.
- About 10 GB of free disk space. In Docker Desktop > Settings > Resources, I suggest giving Docker at least 6 GB of memory.

## Set up (once)

**1. Download the code.** In Terminal:

```bash
git clone https://github.com/forlooplearn01/Agentic-Project-Manager.git
```

```bash
cd Agentic-Project-Manager
```

**2. Create the settings file.** Copy this whole block into Terminal and press Enter:

```bash
cat > .env <<'EOF'
OPENAI_API_KEY=PASTE-YOUR-OPENAI-KEY-HERE
DB_HOST=localhost
DB_PORT=5433
DB_NAME=project_plan_agent
DB_USER=postgres
DB_PASSWORD=postgres
MCP_SERVER_URL=http://localhost:8011
PLAN_JIRA_SYNC=0
EOF
```

**3. Put your key in.** Open the file:

```bash
open -e .env
```

Replace `PASTE-YOUR-OPENAI-KEY-HERE` with your real key (keep the `OPENAI_API_KEY=` part). Save with Cmd+S and close the window.

**4. Create the demo email file.** These are fake addresses, so nothing real can be emailed:

```bash
cat > datasets/golden/emails.local.json <<'EOF'
{"Nirmal Babu": "nirmal@example.com", "Ram Anandkumar": "ram@example.com", "Rucheek": "rucheek@example.com"}
EOF
```

**5. Build and start the app.** Docker Desktop must be running. The first time takes 10 to 20 minutes while it downloads and builds everything:

```bash
docker compose up -d --build
```

When it finishes, check that all four parts are running:

```bash
docker compose ps
```

You should see four lines (api, mcp, frontend, postgres) with "Up". Wait about a minute after this, then continue.

**6. Load the demo projects:**

```bash
docker compose exec api python -m scripts.golden restore all
```

You should see `forloop ok`, `halvane ok`, `marrowfield ok`, `tarnwood ok`. The first run also downloads a small language model, so it needs the internet and takes a minute or two.

**7. Open the app:** http://localhost:3010

In the left menu, open **Settings** and set the theme to **Dark** (the Forloop logo shows best on dark).

## What to look at
Start with **halvane**, the project that is At risk.
- **Dashboard:** nine tiles that count what is going wrong across the four projects. Click a project name in a tile to open that project.
- **Hours:** the budget, the forecast and the status. The *Capacity* tab shows who has time.
- **Workspace:** the plan, the blocked tasks, and meetings the agent proposed (they wait for a person to approve).
- **AI Chat:** try these three:
  - `What is blocked on halvane and why?`
  - `Who is available for QA work on halvane in the next four weeks?`
  - `Is the halvane project on track?`

Each chat answer takes a few seconds. The demo date is fixed at 29 October 2026, so answers are worked out as of that day. That is normal.

## Get the latest version later
Whenever new code has been pushed to GitHub:

```bash
cd Agentic-Project-Manager
```

```bash
git pull
```

```bash
docker compose up -d --build
```

```bash
docker compose exec api python -m scripts.golden restore all
```

The last command puts the demo projects back to the start and clears the chat. If the app behaves oddly after an update, wipe it and start fresh (this deletes only the demo data):

```bash
docker compose down -v
```

Then run the `up -d --build` and `restore` commands above again.

## Stop and start
```bash
docker compose stop
```
```bash
docker compose start
```

## Optional: use the team's own model instead of OpenAI
If you are on the same Wi-Fi as the team's DGX Spark, the app can use the open-source Gemma 4 model running there, so no project text leaves the office. Ask Rucheek for the key. Replace the `OPENAI_API_KEY` line in `.env` with these lines (keep the others):

```
LLM_MODEL=hosted_vllm/gemma4
LLM_API_BASE=http://192.168.2.155:8000/v1
LLM_API_KEY=ASK-RUCHEEK-FOR-THE-KEY
LLM_EXTRA_BODY={"chat_template_kwargs": {"enable_thinking": false}}
RAID_AI_MODEL=
PLAN_SUGGEST_MODEL=
MEETING_COORDINATOR_MODEL=
```

Then restart so it reads the file:

```bash
docker compose up -d --force-recreate api mcp
```

This only works while the Spark is switched on, on the same network, and its model server is running. Answers take longer (roughly 10 seconds each). To go back to OpenAI, remove those lines and put the `OPENAI_API_KEY` line back.

## Good to know
- **There is no login yet.** Anyone who can reach your Mac on the network could open the app, so use your own laptop, not a shared server or public Wi-Fi.
- **Project text goes to OpenAI** (or to the Spark, if you use the option above). The four projects are invented.
- **Jira and Google Calendar are switched off** on your copy. You do not need them to try the product.
- **Only pull, never commit.** There is no need to run `git add` or `git commit` in this folder, and the `.env` file holds your key.

## If something goes wrong
| Problem | What to do |
|---|---|
| `Cannot connect to the Docker daemon` | Open Docker Desktop and wait until it says it is running. |
| A "port is already in use" message (3010, 8010, 8011 or 5433) | Close the other program using it. |
| The page does not load right after step 5 | Wait a minute and refresh. Check `docker compose ps` shows four "Up". |
| `No email known for ...` during step 6 | Redo step 4 (the demo email file). |
| `The build ran out of memory` or the build stops | In Docker Desktop > Settings > Resources, raise the memory and run step 5 again. |
| The chat shows an error or stays empty | Check the key in `.env` (no spaces, no quotes), then run `docker compose up -d --force-recreate api mcp`. |
| GitHub asks for a username and password | The repository may have been made private. Ask Rucheek for access. |
| Anything else | Run `docker compose logs api` and send the last lines to Rucheek. |
