# Git workflow for the team

The brief asks for feature branches merged into `main` through Pull Requests.
Here's a simple routine that satisfies that and keeps us out of each other's way.

## One-time setup

```bash
git init
git add .
git commit -m "Initial project skeleton"
git branch -M main
git remote add origin https://github.com/<your-org>/employee-dw.git
git push -u origin main
```

## Suggested branches (one per teammate or deliverable)

| Branch | What goes in it |
|---|---|
| `feature/data-synthesizer` | `scripts/synthesize_data.py`, `scripts/load_staging.py` |
| `feature/database-design` | `sql/01`-`03` and the diagrams in `docs/diagrams/` |
| `feature/etl-procedures` | `sql/04`, `sql/05`, `scripts/run_etl.py` |
| `feature/oop-backend` | everything in `src/` |
| `feature/streamlit-dashboard` | everything in `app/` |
| `docs/readme-and-report` | README, `docs/`, the Google doc |

## Day-to-day

```bash
git checkout main && git pull
git checkout -b feature/streamlit-dashboard
# ...work, then...
git add app/
git commit -m "Add attrition risk tab to the dashboard"
git push -u origin feature/streamlit-dashboard
```

Open a Pull Request on GitHub, ask a teammate to review it, and merge it into
`main` when it's approved. Don't push straight to `main`. After merging, everyone
runs `git pull` on `main` before starting new work.

## Tips
- Small commits with plain-English messages are easier to review than one giant one.
- Never commit `.env` or `.streamlit/secrets.toml` (they're in `.gitignore`).
- If two people touched the same file, resolve the conflict locally, run `python scripts/smoke_test.py`, then push.
