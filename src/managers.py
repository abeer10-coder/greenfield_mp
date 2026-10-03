"""
managers.py
-----------
The data access layer. Each manager owns one area of the app and inherits
the connection handling from DatabaseHandler:

  EmployeeManager   - onboarding, lookups, department changes (OLTP)
  ProjectManager    - projects and who is assigned to them (OLTP)
  ReviewManager     - performance reviews (OLTP)
  EtlManager        - pushes OLTP changes into the warehouse
  AnalyticsManager  - read-only queries against the star schema (OLAP)

Business-rule problems raise ValueError (the UI shows them as warnings);
database problems raise DatabaseError (the UI shows them as errors).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import pandas as pd
from sqlalchemy import text

from src.db_manager import DW_DB, OLTP_DB, DatabaseHandler
from src.entities import Employee, Project, Review


# ===================================================================== OLTP
class EmployeeManager(DatabaseHandler):
    def __init__(self) -> None:
        super().__init__(OLTP_DB)

    def list_departments(self) -> pd.DataFrame:
        return self._fetch_df("SELECT department_id, department_name FROM departments ORDER BY department_name")

    def list_job_roles(self) -> pd.DataFrame:
        return self._fetch_df("SELECT job_role_id, job_title FROM job_roles ORDER BY job_title")

    def get_profile(self, employee_id: int) -> Optional[dict]:
        rows = self._fetch_all("""
            SELECT e.employee_id, CONCAT(e.first_name, ' ', e.last_name) AS full_name, e.email,
                   e.hire_date, e.department_id, d.department_name, e.job_role_id,
                   jr.job_title, e.job_level, e.monthly_income
            FROM employees e
            JOIN departments d ON d.department_id = e.department_id
            JOIN job_roles jr  ON jr.job_role_id = e.job_role_id
            WHERE e.employee_id = :id""", {"id": employee_id})
        return rows[0] if rows else None

    def add_employee(self, employee: Employee) -> int:
        """Insert the employee AND their first job-history row in one transaction."""
        if self._fetch_all("SELECT 1 FROM employees WHERE email = :e", {"e": employee.email}):
            raise ValueError(f"Someone with the email {employee.email} already exists.")
        with self._transaction() as conn:
            result = conn.execute(text("""
                INSERT INTO employees (first_name, last_name, email, gender, age, marital_status,
                    education_level, education_field, hire_date, distance_from_home, business_travel,
                    over_time, stock_option_level, total_working_years, num_companies_worked,
                    department_id, job_role_id, job_level, monthly_income)
                VALUES (:first_name, :last_name, :email, :gender, :age, :marital_status,
                    :education_level, :education_field, :hire_date, :distance_from_home, :business_travel,
                    :over_time, :stock_option_level, :total_working_years, :num_companies_worked,
                    :department_id, :job_role_id, :job_level, :monthly_income)"""), employee.to_row())
            new_id = int(result.lastrowid)
            conn.execute(text("""
                INSERT INTO employee_job_history (employee_id, department_id, job_role_id, job_level,
                    monthly_income, effective_start, effective_end, change_reason)
                VALUES (:id, :dept, :role, :level, :income, :start, NULL, 'Initial Hire')"""),
                {"id": new_id, "dept": employee.department_id, "role": employee.job_role_id,
                 "level": employee.job_level, "income": employee.monthly_income,
                 "start": employee.hire_date})
        return new_id

    def change_department(self, employee_id: int, new_department_id: int, new_job_role_id: int,
                          effective_date: date, reason: str = "Department Transfer") -> None:
        """
        Moves someone to a new department the SCD2 way: the old history row is
        closed the day before, a new one is opened on `effective_date`, and the
        employee's current department is updated. The warehouse picks the
        change up when EtlManager.refresh_employee() runs.
        """
        with self._transaction() as conn:
            current = conn.execute(text("""
                SELECT history_id, effective_start, department_id, job_level, monthly_income
                FROM employee_job_history
                WHERE employee_id = :id AND effective_end IS NULL FOR UPDATE"""),
                {"id": employee_id}).mappings().first()
            if current is None:
                raise ValueError(f"No active job record found for employee {employee_id}.")
            if current["department_id"] == new_department_id:
                raise ValueError("They're already in that department.")
            if effective_date <= current["effective_start"]:
                raise ValueError(f"The move must be after their current role started on {current['effective_start']}.")

            conn.execute(text("UPDATE employee_job_history SET effective_end = :end WHERE history_id = :h"),
                         {"end": effective_date - timedelta(days=1), "h": current["history_id"]})
            conn.execute(text("""
                INSERT INTO employee_job_history (employee_id, department_id, job_role_id, job_level,
                    monthly_income, effective_start, effective_end, change_reason)
                VALUES (:id, :dept, :role, :level, :income, :start, NULL, :reason)"""),
                {"id": employee_id, "dept": new_department_id, "role": new_job_role_id,
                 "level": current["job_level"], "income": current["monthly_income"],
                 "start": effective_date, "reason": reason})
            conn.execute(text("UPDATE employees SET department_id = :dept, job_role_id = :role WHERE employee_id = :id"),
                         {"dept": new_department_id, "role": new_job_role_id, "id": employee_id})


class ProjectManager(DatabaseHandler):
    def __init__(self) -> None:
        super().__init__(OLTP_DB)

    def list_projects(self, open_only: bool = True) -> pd.DataFrame:
        where = "WHERE p.status <> 'Completed'" if open_only else ""
        return self._fetch_df(f"""
            SELECT p.project_id, p.project_name, d.department_name, p.status, p.priority
            FROM projects p JOIN departments d ON d.department_id = p.department_id
            {where} ORDER BY p.project_name""")

    def create_project(self, project: Project) -> int:
        if self._fetch_all("SELECT 1 FROM projects WHERE project_name = :n", {"n": project.name}):
            raise ValueError(f"A project called '{project.name}' already exists.")
        with self._transaction() as conn:
            result = conn.execute(text("""
                INSERT INTO projects (project_name, department_id, status, priority, budget, start_date, end_date)
                VALUES (:project_name, :department_id, :status, :priority, :budget, :start_date, :end_date)"""),
                project.to_row())
            return int(result.lastrowid)

    def current_allocation(self, employee_id: int) -> int:
        rows = self._fetch_all("""SELECT COALESCE(SUM(allocation_pct), 0) AS total
                                  FROM project_assignments
                                  WHERE employee_id = :id AND end_date IS NULL""", {"id": employee_id})
        return int(rows[0]["total"])

    def assign_employee(self, employee_id: int, project_id: int, role: str,
                        allocation_pct: int, start_date: date) -> None:
        used = self.current_allocation(employee_id)
        if used + allocation_pct > 100:
            raise ValueError(f"That would put them at {used + allocation_pct}% allocation "
                             f"(they're already at {used}%). Keep the total at 100% or less.")
        if self._fetch_all("SELECT 1 FROM project_assignments WHERE employee_id = :e AND project_id = :p",
                           {"e": employee_id, "p": project_id}):
            raise ValueError("They're already assigned to that project.")
        self._execute("""
            INSERT INTO project_assignments (employee_id, project_id, role_on_project, allocation_pct, start_date)
            VALUES (:e, :p, :role, :alloc, :start)""",
            {"e": employee_id, "p": project_id, "role": role, "alloc": allocation_pct, "start": start_date})


class ReviewManager(DatabaseHandler):
    def __init__(self) -> None:
        super().__init__(OLTP_DB)

    def submit_review(self, review: Review) -> int:
        emp = self._fetch_all("SELECT hire_date FROM employees WHERE employee_id = :id", {"id": review.employee_id})
        if not emp:
            raise ValueError(f"There is no employee with id {review.employee_id}.")
        if review.review_date < emp[0]["hire_date"]:
            raise ValueError(f"That review is dated before their hire date ({emp[0]['hire_date']}).")
        if self._fetch_all("SELECT 1 FROM performance_reviews WHERE employee_id = :e AND review_date = :d",
                           {"e": review.employee_id, "d": review.review_date}):
            raise ValueError("They already have a review on that date.")
        with self._transaction() as conn:
            result = conn.execute(text("""
                INSERT INTO performance_reviews (employee_id, project_id, review_date, performance_rating,
                    job_satisfaction, environment_satisfaction, work_life_balance, percent_salary_hike, review_score)
                VALUES (:employee_id, :project_id, :review_date, :performance_rating, :job_satisfaction,
                    :environment_satisfaction, :work_life_balance, :percent_salary_hike, :review_score)"""),
                review.to_row())
            return int(result.lastrowid)


# ===================================================================== ETL
class EtlManager(DatabaseHandler):
    """Thin wrapper around the stored procedures that feed the warehouse."""

    def __init__(self) -> None:
        super().__init__(DW_DB)

    def refresh_employee(self, employee_id: int) -> None:
        self._db.call_procedure("sp_load_dim_employee_scd2", [employee_id], DW_DB)

    def refresh_reviews(self) -> None:
        self._db.call_procedure("sp_load_dim_date", ["2015-01-01", "2030-12-31"], DW_DB)
        self._db.call_procedure("sp_load_dim_project", [], DW_DB)
        self._db.call_procedure("sp_load_fact_performance_reviews", [], DW_DB)

    def run_full_etl(self) -> None:
        self._db.call_procedure("sp_run_full_etl", [], DW_DB)


# ================================================================== OLAP
class AnalyticsManager(DatabaseHandler):
    def __init__(self) -> None:
        super().__init__(DW_DB)

    def kpis(self) -> dict:
        return self._fetch_all("""
            SELECT
              (SELECT COUNT(*) FROM dim_employee WHERE is_current = 1)                       AS employees,
              (SELECT COUNT(*) FROM fact_performance_reviews)                                AS reviews,
              (SELECT ROUND(AVG(review_score), 1) FROM fact_performance_reviews)             AS avg_score,
              (SELECT ROUND(100 * AVG(attrition_flag), 1) FROM dim_employee WHERE is_current = 1) AS attrition_pct,
              (SELECT COUNT(*) FROM (SELECT employee_id FROM dim_employee
                                     GROUP BY employee_id HAVING COUNT(*) > 1) x)            AS with_history""")[0]

    def review_years(self) -> list[int]:
        df = self._fetch_df("""SELECT DISTINCT dt.year_number FROM fact_performance_reviews f
                               JOIN dim_date dt ON dt.date_key = f.date_key ORDER BY 1""")
        return df["year_number"].astype(int).tolist()

    def yearly_trend(self) -> pd.DataFrame:
        return self._fetch_df("""
            WITH yearly AS (
                SELECT dt.year_number AS review_year, dep.department_name,
                       AVG(f.review_score) AS avg_score, AVG(f.performance_rating) AS avg_rating,
                       COUNT(*) AS reviews
                FROM fact_performance_reviews f
                JOIN dim_date dt ON dt.date_key = f.date_key
                JOIN dim_department dep ON dep.department_key = f.department_key
                GROUP BY dt.year_number, dep.department_name)
            SELECT review_year, department_name, ROUND(avg_score, 2) AS avg_score,
                   ROUND(avg_rating, 2) AS avg_rating, reviews,
                   ROUND(avg_score - LAG(avg_score) OVER (PARTITION BY department_name
                                                          ORDER BY review_year), 2) AS yoy_change
            FROM yearly ORDER BY department_name, review_year""")

    def top_performers(self, year: int, top_n: int = 5) -> pd.DataFrame:
        return self._fetch_df("""
            WITH per_employee AS (
                SELECT e.employee_id, e.full_name, dep.department_name,
                       ROUND(AVG(f.review_score), 2) AS avg_score,
                       ROUND(AVG(f.performance_rating), 2) AS avg_rating
                FROM fact_performance_reviews f
                JOIN dim_employee e ON e.employee_key = f.employee_key
                JOIN dim_department dep ON dep.department_key = f.department_key
                JOIN dim_date dt ON dt.date_key = f.date_key
                WHERE dt.year_number = :year
                GROUP BY e.employee_id, e.full_name, dep.department_name),
            ranked AS (
                SELECT per_employee.*,
                       DENSE_RANK() OVER (PARTITION BY department_name
                                          ORDER BY avg_score DESC, avg_rating DESC) AS dept_rank
                FROM per_employee)
            SELECT department_name, dept_rank, employee_id, full_name, avg_score, avg_rating
            FROM ranked WHERE dept_rank <= :top_n
            ORDER BY department_name, dept_rank, employee_id""", {"year": year, "top_n": top_n})

    def attrition_by_group(self) -> pd.DataFrame:
        return self._fetch_df("""
            SELECT department_name,
                   CASE WHEN over_time_flag = 1 THEN 'Overtime' ELSE 'No overtime' END AS overtime_group,
                   COUNT(*) AS headcount, SUM(attrition_flag) AS leavers,
                   ROUND(100 * AVG(attrition_flag), 1) AS attrition_rate_pct
            FROM dim_employee WHERE is_current = 1
            GROUP BY department_name, over_time_flag
            ORDER BY department_name, over_time_flag""")

    def attrition_risk_list(self, top_n: int = 20) -> pd.DataFrame:
        """People still here whose latest review + overtime pattern looks like the leavers'."""
        return self._fetch_df("""
            WITH latest AS (
                SELECT e.employee_id, f.job_satisfaction, f.work_life_balance,
                       f.performance_rating, f.review_score,
                       ROW_NUMBER() OVER (PARTITION BY e.employee_id ORDER BY f.date_key DESC) AS rn
                FROM fact_performance_reviews f
                JOIN dim_employee e ON e.employee_key = f.employee_key)
            SELECT c.employee_id, c.full_name, c.department_name, c.job_role,
                   CASE WHEN c.over_time_flag = 1 THEN 'Yes' ELSE 'No' END AS overtime,
                   l.job_satisfaction, l.work_life_balance, l.performance_rating,
                   (c.over_time_flag * 2 + (l.job_satisfaction <= 2) * 2
                    + (l.work_life_balance <= 2) + (l.performance_rating <= 2)) AS risk_score
            FROM dim_employee c
            JOIN latest l ON l.employee_id = c.employee_id AND l.rn = 1
            WHERE c.is_current = 1 AND c.attrition_flag = 0
            ORDER BY risk_score DESC, l.review_score ASC, c.employee_id
            LIMIT :top_n""", {"top_n": top_n})

    def project_bottlenecks(self, min_reviews: int = 20) -> pd.DataFrame:
        return self._fetch_df("""
            WITH project_stats AS (
                SELECT p.project_name, p.department_name, p.status, p.priority,
                       COUNT(*) AS reviews, COUNT(DISTINCT e.employee_id) AS people,
                       ROUND(AVG(f.review_score), 2) AS avg_score,
                       ROUND(100 * AVG(f.performance_rating <= 2), 1) AS low_rating_pct
                FROM fact_performance_reviews f
                JOIN dim_project p ON p.project_key = f.project_key
                JOIN dim_employee e ON e.employee_key = f.employee_key
                WHERE p.project_key <> -1
                GROUP BY p.project_name, p.department_name, p.status, p.priority
                HAVING COUNT(*) >= :min_reviews)
            SELECT RANK() OVER (ORDER BY avg_score ASC) AS bottleneck_rank, project_stats.*
            FROM project_stats ORDER BY bottleneck_rank""", {"min_reviews": min_reviews})

    def employee_history(self, employee_id: int) -> pd.DataFrame:
        return self._fetch_df("""
            SELECT employee_key, employee_id, full_name, department_name, job_role, job_level,
                   monthly_income, start_date, end_date, is_current, change_reason
            FROM dim_employee WHERE employee_id = :id ORDER BY start_date""", {"id": employee_id})
