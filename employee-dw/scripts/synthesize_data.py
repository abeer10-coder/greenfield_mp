"""
synthesize_data.py
------------------
The IBM HR Analytics file is a single snapshot of ~1,470 people. That is
too small to stress a warehouse and too flat to have any "history". This
script fixes both problems:

  1. SCALE   - grows the snapshot to 100,000+ employees by cloning rows,
               nudging the numbers a little and giving every clone a new
               identity (Faker).
  2. HISTORY - invents past promotions, department transfers and salary
               revisions for roughly a third of the staff, so the
               warehouse has real SCD Type 2 changes to track.
  3. CONTEXT - creates projects, assignments and five years of yearly
               performance reviews.

It also leaves a few "dirty" rows on purpose (duplicates, stray spaces,
shouty emails) so the SQL cleaning step has something to do.

Usage
-----
    python scripts/synthesize_data.py --input data/raw/WA_Fn-UseC_-HR-Employee-Attrition.csv
    python scripts/synthesize_data.py --demo      # no IBM file? builds a look-alike base

Output: CSV files in data/synthetic/ that match the staging tables.
"""
from __future__ import annotations

import argparse
import re
import random
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

AS_OF = date(2025, 12, 31)            # "today" inside the synthetic company
REVIEW_YEARS = [2021, 2022, 2023, 2024, 2025]

ROLES_BY_DEPT = {
    "Sales": ["Sales Executive", "Sales Representative", "Manager"],
    "Research & Development": [
        "Research Scientist", "Laboratory Technician", "Manufacturing Director",
        "Healthcare Representative", "Research Director", "Manager",
    ],
    "Human Resources": ["Human Resources", "Manager"],
}
DEPT_WEIGHTS = {"Sales": 0.30, "Research & Development": 0.65, "Human Resources": 0.05}
CHANGE_REASONS = ["Promotion", "Department Transfer", "Salary Revision"]

REQUIRED_COLUMNS = [
    "Age", "Attrition", "BusinessTravel", "Department", "DistanceFromHome",
    "Education", "EducationField", "EnvironmentSatisfaction", "Gender",
    "JobLevel", "JobRole", "JobSatisfaction", "MaritalStatus", "MonthlyIncome",
    "NumCompaniesWorked", "OverTime", "PercentSalaryHike", "PerformanceRating",
    "StockOptionLevel", "TotalWorkingYears", "WorkLifeBalance", "YearsAtCompany",
]


# ---------------------------------------------------------------- base data
def load_base(path: Path | None, demo: bool, rng: np.random.Generator) -> pd.DataFrame:
    if path and path.exists():
        df = pd.read_csv(path)
        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise SystemExit(f"That file is missing columns we need: {missing}")
        print(f"Loaded the IBM base file: {len(df):,} rows")
        return df[REQUIRED_COLUMNS].copy()
    if not demo:
        raise SystemExit("Couldn't find the IBM CSV. Pass --input <file>, or use --demo to test without it.")
    print("Demo mode: building a look-alike of the IBM dataset (1,470 rows)")
    return build_demo_base(1470, rng)


def build_demo_base(n: int, rng: np.random.Generator) -> pd.DataFrame:
    dept = rng.choice(list(DEPT_WEIGHTS), size=n, p=list(DEPT_WEIGHTS.values()))
    role = [random.choice(ROLES_BY_DEPT[d]) for d in dept]
    level = rng.choice([1, 2, 3, 4, 5], size=n, p=[0.37, 0.36, 0.15, 0.07, 0.05])
    age = rng.integers(18, 61, n)
    total_years = np.minimum(rng.integers(0, 36, n), age - 18)
    years_company = np.minimum(rng.integers(0, 25, n), total_years)
    return pd.DataFrame({
        "Age": age,
        "Attrition": rng.choice(["Yes", "No"], size=n, p=[0.16, 0.84]),
        "BusinessTravel": rng.choice(["Travel_Rarely", "Travel_Frequently", "Non-Travel"], size=n, p=[0.7, 0.19, 0.11]),
        "Department": dept,
        "DistanceFromHome": rng.integers(1, 30, n),
        "Education": rng.integers(1, 6, n),
        "EducationField": rng.choice(["Life Sciences", "Medical", "Marketing", "Technical Degree", "Other", "Human Resources"], size=n),
        "EnvironmentSatisfaction": rng.integers(1, 5, n),
        "Gender": rng.choice(["Male", "Female"], size=n, p=[0.6, 0.4]),
        "JobLevel": level,
        "JobRole": role,
        "JobSatisfaction": rng.integers(1, 5, n),
        "MaritalStatus": rng.choice(["Single", "Married", "Divorced"], size=n, p=[0.32, 0.46, 0.22]),
        "MonthlyIncome": (1500 + level * 2600 + rng.normal(0, 700, n)).clip(1009, 19999).astype(int),
        "NumCompaniesWorked": rng.integers(0, 10, n),
        "OverTime": rng.choice(["Yes", "No"], size=n, p=[0.28, 0.72]),
        "PercentSalaryHike": rng.integers(11, 26, n),
        "PerformanceRating": rng.choice([3, 4], size=n, p=[0.85, 0.15]),
        "StockOptionLevel": rng.integers(0, 4, n),
        "TotalWorkingYears": total_years,
        "WorkLifeBalance": rng.integers(1, 5, n),
        "YearsAtCompany": years_company,
    })


# ------------------------------------------------------------------- scaling
def scale_up(base: pd.DataFrame, target_rows: int, rng: np.random.Generator) -> pd.DataFrame:
    """Keep every original row, then top up with jittered clones."""
    extra = max(target_rows - len(base), 0)
    clones = base.sample(n=extra, replace=True, random_state=int(rng.integers(0, 2**31 - 1))).reset_index(drop=True)

    clones["Age"] = (clones["Age"] + rng.integers(-3, 4, extra)).clip(18, 60)
    clones["DistanceFromHome"] = (clones["DistanceFromHome"] + rng.integers(-2, 3, extra)).clip(1, 29)
    clones["MonthlyIncome"] = (clones["MonthlyIncome"] * rng.uniform(0.9, 1.1, extra)).round().astype(int).clip(1009, None)
    clones["PercentSalaryHike"] = (clones["PercentSalaryHike"] + rng.integers(-1, 2, extra)).clip(11, 25)

    # keep the career numbers believable for the (possibly changed) age
    total = (clones["TotalWorkingYears"] + rng.integers(-1, 2, extra)).clip(0, None)
    total = np.minimum(total, clones["Age"] - 16)
    years = (clones["YearsAtCompany"] + rng.integers(-1, 2, extra)).clip(0, None)
    clones["TotalWorkingYears"] = total
    clones["YearsAtCompany"] = np.minimum(years, total)

    scaled = pd.concat([base, clones], ignore_index=True).head(target_rows)
    scaled.insert(0, "employee_id", np.arange(1001, 1001 + len(scaled)))
    return scaled


def add_identity(df: pd.DataFrame, fake: Faker, rnd: random.Random) -> pd.DataFrame:
    firsts, lasts, emails, hires = [], [], [], []
    for emp_id, gender, years in zip(df["employee_id"], df["Gender"], df["YearsAtCompany"]):
        first = fake.first_name_male() if gender == "Male" else fake.first_name_female()
        last = fake.last_name()
        slug = re.sub(r"[^a-z0-9.]", "", f"{first}.{last}".lower())
        firsts.append(first)
        lasts.append(last)
        emails.append(f"{slug}.{emp_id}@northwind-corp.example")
        hires.append(AS_OF - timedelta(days=int(years) * 365 + rnd.randint(0, 364)))
    out = df.copy()
    out["first_name"], out["last_name"], out["email"] = firsts, lasts, emails
    out["hire_date"] = pd.to_datetime(hires)
    return out


# ------------------------------------------------------------------- history
def _round_income(x: float) -> int:
    return max(1009, int(round(x)))


def previous_state(state: tuple, reason: str, rnd: random.Random) -> tuple:
    """Given where someone is now, work out where they were before `reason` happened."""
    dept, role, level, income = state
    if reason == "Promotion":
        return dept, role, max(1, level - 1), _round_income(income / rnd.uniform(1.10, 1.25))
    if reason == "Department Transfer":
        other = rnd.choice([d for d in ROLES_BY_DEPT if d != dept])
        return other, rnd.choice(ROLES_BY_DEPT[other]), level, _round_income(income / rnd.uniform(0.95, 1.05))
    return dept, role, level, _round_income(income / rnd.uniform(1.05, 1.15))  # Salary Revision


def build_history(snap: pd.DataFrame, rnd: random.Random, change_share: float = 0.30) -> pd.DataFrame:
    rows = []
    for r in snap.itertuples(index=False):
        hire = pd.Timestamp(r.hire_date).date()
        tenure = (AS_OF - hire).days
        current = (r.Department, r.JobRole, int(r.JobLevel), int(r.MonthlyIncome))

        n_changes = 0
        if tenure >= 730 and rnd.random() < change_share:
            n_changes = 2 if (tenure >= 1460 and rnd.random() < 0.3) else 1

        if n_changes == 0:
            starts, reasons, states = [hire], ["Initial Hire"], [current]
        else:
            offsets = sorted(rnd.sample(range(180, tenure - 180, 30), n_changes))
            change_dates = [hire + timedelta(days=o) for o in offsets]
            change_reasons = [rnd.choice(CHANGE_REASONS) for _ in change_dates]
            states = [current]
            for reason in reversed(change_reasons):          # walk backwards in time
                states.insert(0, previous_state(states[0], reason, rnd))
            starts = [hire] + change_dates
            reasons = ["Initial Hire"] + change_reasons

        for i, (dept, role, level, income) in enumerate(states):
            end = starts[i + 1] - timedelta(days=1) if i + 1 < len(starts) else None
            rows.append((r.employee_id, dept, role, level, income, starts[i], end, reasons[i]))

    return pd.DataFrame(rows, columns=[
        "employee_id", "department", "job_role", "job_level", "monthly_income",
        "effective_start", "effective_end", "change_reason"])


# ------------------------------------------------------ projects & reviews
def build_projects(fake: Faker, rnd: random.Random, n: int = 60) -> pd.DataFrame:
    suffix = {
        "Sales": ["Growth Push", "Account Revamp", "Pipeline Sprint"],
        "Research & Development": ["Platform Build", "Lab Automation", "Prototype Run"],
        "Human Resources": ["Talent Drive", "Engagement Revamp"],
    }
    depts = list(DEPT_WEIGHTS)
    rows = []
    for pid in range(1, n + 1):
        # the first six projects guarantee every department owns at least two
        dept = depts[(pid - 1) % 3] if pid <= 6 else rnd.choices(depts, weights=list(DEPT_WEIGHTS.values()))[0]
        start = date(2019, 1, 1) + timedelta(days=rnd.randint(0, 6 * 365))
        status = rnd.choices(["Completed", "Active", "On Hold"], weights=[30, 60, 10])[0]
        end = None
        if status == "Completed":
            end = start + timedelta(days=rnd.randint(200, 900))
            if end > AS_OF:
                status, end = "Active", None
        rows.append((pid, f"{fake.unique.color_name()} {rnd.choice(suffix[dept])}", dept, status,
                     rnd.choice(["Low", "Medium", "High"]), round(rnd.uniform(50_000, 2_000_000), 2), start, end))
    return pd.DataFrame(rows, columns=["project_id", "project_name", "department", "status",
                                       "priority", "budget", "start_date", "end_date"])


def build_assignments(snap: pd.DataFrame, projects: pd.DataFrame, rnd: random.Random) -> pd.DataFrame:
    by_dept = projects.groupby("department")["project_id"].apply(list).to_dict()
    all_ids = projects["project_id"].tolist()
    info = projects.set_index("project_id")[["start_date", "end_date"]].to_dict("index")
    rows = []
    for r in snap.itertuples(index=False):
        hire = pd.Timestamp(r.hire_date).date()
        k = 2 if rnd.random() < 0.35 else 1
        chosen = set()
        for _ in range(20):                               # guard against tiny pools
            if len(chosen) == k:
                break
            pool = by_dept[r.Department] if rnd.random() < 0.8 else all_ids
            chosen.add(rnd.choice(pool))
        allocs = [rnd.choice([50, 75, 100])] if len(chosen) == 1 else [(a := rnd.choice([40, 50, 60])), 100 - a]
        for pid, alloc in zip(chosen, allocs):
            p = info[pid]
            start = max(hire, p["start_date"]) + timedelta(days=rnd.randint(0, 60))
            end = p["end_date"]
            if start > AS_OF or (end is not None and start > end):
                continue
            rows.append((r.employee_id, pid, rnd.choices(["Contributor", "Lead", "Reviewer"], weights=[75, 10, 15])[0],
                         alloc, start, end))
    return pd.DataFrame(rows, columns=["employee_id", "project_id", "role_on_project",
                                       "allocation_pct", "start_date", "end_date"])


def _clamp(v: int, lo: int = 1, hi: int = 4) -> int:
    return max(lo, min(hi, v))


def build_reviews(snap: pd.DataFrame, assignments: pd.DataFrame, rnd: random.Random) -> pd.DataFrame:
    by_emp: dict[int, list] = {}
    for a in assignments.itertuples(index=False):
        by_emp.setdefault(a.employee_id, []).append(a)

    rows, review_id = [], 1
    for r in snap.itertuples(index=False):
        hire = pd.Timestamp(r.hire_date).date()
        # 2025 rating comes from the IBM column; earlier years drift around it
        ratings, current = {}, int(r.PerformanceRating)
        for year in reversed(REVIEW_YEARS):
            ratings[year] = current
            current = _clamp(current + rnd.choice([-1, 0, 0, 0, 1]))

        for year in REVIEW_YEARS:
            review_date = date(year, 12, rnd.randint(1, 20))
            if review_date <= hire + timedelta(days=120):
                continue
            if r.Attrition == "Yes" and year == 2025 and rnd.random() < 0.5:
                continue                                   # leavers often miss the last cycle
            js = _clamp(int(r.JobSatisfaction) + rnd.choice([-1, 0, 0, 1]))
            env = _clamp(int(r.EnvironmentSatisfaction) + rnd.choice([-1, 0, 0, 1]))
            wlb = _clamp(int(r.WorkLifeBalance) + rnd.choice([-1, 0, 0, 1]))
            score = ratings[year] / 4 * 60 + (js + env + wlb) / 12 * 40 + rnd.gauss(0, 3)
            project = None
            for a in by_emp.get(r.employee_id, []):
                if a.start_date <= review_date and (a.end_date is None or a.end_date >= review_date):
                    project = a.project_id
                    break
            rows.append((review_id, r.employee_id, project, review_date, ratings[year], js, env, wlb,
                         _clamp(int(r.PercentSalaryHike) + rnd.randint(-2, 2), 11, 25),
                         round(max(0, min(100, score)), 2)))
            review_id += 1

    df = pd.DataFrame(rows, columns=[
        "review_id", "employee_id", "project_id", "review_date", "performance_rating",
        "job_satisfaction", "environment_satisfaction", "work_life_balance",
        "percent_salary_hike", "review_score"])
    df["project_id"] = df["project_id"].astype("Int64")
    return df


# ---------------------------------------------------------------- messiness
def make_it_messy(snapshot: pd.DataFrame, reviews: pd.DataFrame, rnd: random.Random):
    """A realistic export is never perfectly clean. Add a pinch of dirt."""
    dup_emps = snapshot.sample(frac=0.002, random_state=1)
    snapshot = pd.concat([snapshot, dup_emps], ignore_index=True)

    shaky = snapshot.sample(frac=0.01, random_state=2).index
    snapshot.loc[shaky, "first_name"] = "  " + snapshot.loc[shaky, "first_name"] + " "
    shouty = snapshot.sample(frac=0.01, random_state=3).index
    snapshot.loc[shouty, "email"] = snapshot.loc[shouty, "email"].str.upper()

    dup_reviews = reviews.sample(frac=0.003, random_state=4).copy()
    dup_reviews["review_id"] = np.arange(reviews["review_id"].max() + 1,
                                         reviews["review_id"].max() + 1 + len(dup_reviews))
    reviews = pd.concat([reviews, dup_reviews], ignore_index=True)
    return snapshot, reviews


# --------------------------------------------------------------------- main
def main() -> None:
    parser = argparse.ArgumentParser(description="Scale the IBM HR dataset and fabricate SCD2 history.")
    parser.add_argument("--input", type=Path, help="path to the IBM HR Analytics CSV")
    parser.add_argument("--output-dir", type=Path, default=Path("data/synthetic"))
    parser.add_argument("--rows", type=int, default=100_000, help="employees to generate (default 100,000)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--locale", default="en_IN", help="Faker locale for names (default en_IN)")
    parser.add_argument("--demo", action="store_true", help="use a generated look-alike if the IBM file is missing")
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    rnd = random.Random(args.seed)
    random.seed(args.seed)
    Faker.seed(args.seed)
    fake = Faker(args.locale)

    base = load_base(args.input, args.demo, rng)
    scaled = add_identity(scale_up(base, args.rows, rng), fake, rnd)
    print(f"Scaled to {len(scaled):,} employees")

    history = build_history(scaled, rnd)
    projects = build_projects(fake, rnd)
    assignments = build_assignments(scaled, projects, rnd)
    reviews = build_reviews(scaled, assignments, rnd)

    snapshot = pd.DataFrame({
        "employee_id": scaled["employee_id"], "first_name": scaled["first_name"],
        "last_name": scaled["last_name"], "email": scaled["email"], "hire_date": scaled["hire_date"],
        "age": scaled["Age"], "attrition": scaled["Attrition"], "business_travel": scaled["BusinessTravel"],
        "department": scaled["Department"], "distance_from_home": scaled["DistanceFromHome"],
        "education": scaled["Education"], "education_field": scaled["EducationField"],
        "gender": scaled["Gender"], "job_level": scaled["JobLevel"], "job_role": scaled["JobRole"],
        "marital_status": scaled["MaritalStatus"], "monthly_income": scaled["MonthlyIncome"],
        "num_companies_worked": scaled["NumCompaniesWorked"], "over_time": scaled["OverTime"],
        "stock_option_level": scaled["StockOptionLevel"], "total_working_years": scaled["TotalWorkingYears"],
        "years_at_company": scaled["YearsAtCompany"],
    })
    snapshot, reviews = make_it_messy(snapshot, reviews, rnd)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {"stg_employee_snapshot": snapshot, "stg_employee_history": history,
               "stg_projects": projects, "stg_assignments": assignments, "stg_reviews": reviews}
    for name, frame in outputs.items():
        frame.to_csv(args.output_dir / f"{name}.csv", index=False, date_format="%Y-%m-%d")
        print(f"  {name:<24} {len(frame):>9,} rows")

    changed = history.groupby("employee_id").size().gt(1).sum()
    print(f"\nEmployees with at least one past job change (SCD2 material): {changed:,}")
    print(f"Files written to {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
