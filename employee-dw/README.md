# Enterprise Employee Analytics & Data Warehouse

A group mini project: take the small IBM HR dataset, grow it into a company-sized
one, build an OLTP database and a star-schema warehouse in MySQL, and put a
Streamlit app on top so HR can enter data and executives can explore it.

**What's inside**

| Folder | What it holds |
|---|---|
| `scripts/` | Data synthesizer, staging loader, ETL runner, DB setup, smoke test |
| `sql/` | DDL for staging/OLTP/OLAP, stored procedures, CTE + window-function queries |
| `src/` | The OOP backend: Singleton connection, entities, managers |
| `app/` | The Streamlit app (dashboard + data entry) |
| `docs/` | Architecture write-up, editable diagrams, Git workflow |

## Quick start

You'll need Python 3.10+ and **MySQL 8.0.19 or newer**.

```bash
# 1. get set up
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then put your MySQL password in .env

# 2. get the data: download the IBM HR Analytics Attrition CSV from Kaggle and drop it in data/raw/
python scripts/synthesize_data.py --input data/raw/WA_Fn-UseC_-HR-Employee-Attrition.csv
#    (no file yet? `python scripts/synthesize_data.py --demo` builds a look-alike so you can test)

# 3. build the databases, load staging, run the ETL
python scripts/setup_database.py
python scripts/load_staging.py
python scripts/run_etl.py

# 4. optional sanity check, then launch
python scripts/smoke_test.py
streamlit run app/streamlit_app.py
```

Steps 2-3 take a few minutes the first time (about 390k review rows get inserted).

### Prefer MySQL Workbench?
Open and run the files in `sql/` in order (01 to 05). Then run
`python scripts/load_staging.py`, and in Workbench run:

```sql
CALL employee_oltp.sp_load_oltp_from_staging();
CALL employee_dw.sp_run_full_etl();
```
`sql/06_analytics_queries.sql` has the dashboard queries with plain literals.

## Using the app

**Analytics dashboard** - KPIs, year-over-year trends, top performers by department,
attrition and risk, project bottlenecks, and an employee-history viewer.

**Data entry** - onboard employees, create projects, assign people (it stops
anyone going over 100% allocation), submit reviews, and change an employee's
department. That last one is the SCD Type 2 demo: the old warehouse row is closed,
a new one is opened, and the page shows both.

## Deploying to Streamlit Community Cloud

Streamlit Cloud can't see the MySQL on your laptop, so you need a MySQL server
that's reachable from the internet (a free tier from Aiven, TiDB Cloud or Railway works).

1. Point `.env` at that cloud database and run steps 2-3 above once to fill it.
2. Push the repo to GitHub (see `docs/GIT_WORKFLOW.md`).
3. On [share.streamlit.io](https://share.streamlit.io) create an app, choose your repo,
   and set the main file to `app/streamlit_app.py`.
4. In the app's **Settings > Secrets** paste the contents of `.streamlit/secrets.toml.example`
   with your real host, user and password. If your provider requires SSL, add `ssl_ca`.

## Troubleshooting

- **"Can't reach MySQL"** - check `.env`, and that the server is running.
- **`Access denied` / authentication errors** - make sure `cryptography` installed (it is in `requirements.txt`).
- **Dashboard says the warehouse isn't ready** - run `scripts/run_etl.py`.
- **Re-running `setup_database.py` wiped my data** - yes, it drops and recreates tables. Re-run steps 3 to reload.

## Notes on testing

I ran the whole pipeline (setup, staging load, both ETL stages, the smoke test, and
the Streamlit pages through Streamlit's test runner) on a local **MariaDB 10.11**
server because that's what was available, not on MySQL 8 itself. The SQL sticks
to features both support, but run `scripts/smoke_test.py` on your own MySQL
and tell us if anything behaves differently.

More detail on the design is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
