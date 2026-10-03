"""
smoke_test.py
-------------
A quick end-to-end check you can run after the ETL, before you open the app.
It onboards a test employee, moves them to another department (the SCD Type 2
moment), submits a review, and runs every dashboard query once.

    python scripts/smoke_test.py
"""
import uuid
from datetime import date

import _common  # noqa: F401
from src.entities import Employee, Review
from src.managers import AnalyticsManager, EmployeeManager, EtlManager, ReviewManager


def main() -> None:
    employees, etl, analytics = EmployeeManager(), EtlManager(), AnalyticsManager()
    depts = employees.list_departments()
    roles = employees.list_job_roles()
    sales = int(depts.loc[depts.department_name == "Sales", "department_id"].iloc[0])
    hr = int(depts.loc[depts.department_name == "Human Resources", "department_id"].iloc[0])
    role = int(roles["job_role_id"].iloc[0])

    tag = uuid.uuid4().hex[:6]
    new_id = employees.add_employee(Employee(
        "Test", f"Person{tag}", f"test.{tag}@northwind-corp.example", "Female", 29, "Single", 3,
        "Life Sciences", date(2025, 3, 1), sales, role, 2, 5200))
    etl.refresh_employee(new_id)
    print(f"1. onboarded employee {new_id}; warehouse rows: {len(analytics.employee_history(new_id))}")

    employees.change_department(new_id, hr, role, date(2025, 9, 1))
    etl.refresh_employee(new_id)
    history = analytics.employee_history(new_id)
    print("2. after the department change the dimension has two versions:")
    print(history[["employee_key", "department_name", "start_date", "end_date", "is_current"]].to_string(index=False))

    ReviewManager().submit_review(Review(new_id, date(2025, 12, 5), 4, 3, 3, 4, 12))
    etl.refresh_reviews()
    print("3. review submitted and loaded into the fact table")

    print("4. dashboard queries:")
    print("   KPIs:", analytics.kpis())
    year = analytics.review_years()[-1]
    for name, frame in {
        "yearly_trend": analytics.yearly_trend(),
        "top_performers": analytics.top_performers(year, 3),
        "attrition_by_group": analytics.attrition_by_group(),
        "attrition_risk_list": analytics.attrition_risk_list(5),
        "project_bottlenecks": analytics.project_bottlenecks(),
    }.items():
        print(f"   {name:<22} -> {len(frame)} rows")
    print("All good.")


if __name__ == "__main__":
    main()
