"""
entities.py
-----------
Plain Python classes for the three things the business cares about:
Employee, Project and Review. They guard their own data (bad ages, empty
names and out-of-range ratings are rejected right here, before MySQL ever
sees them) and know how to turn themselves into a row for the database.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

PROJECT_STATUSES = ("Active", "On Hold", "Completed")
PROJECT_PRIORITIES = ("Low", "Medium", "High")
ASSIGNMENT_ROLES = ("Contributor", "Lead", "Reviewer")


def _need_text(value: str, label: str, max_len: int = 120) -> str:
    value = (value or "").strip()
    if not value:
        raise ValueError(f"{label} can't be empty.")
    if len(value) > max_len:
        raise ValueError(f"{label} is too long (max {max_len} characters).")
    return value


def _need_range(value: int, label: str, low: int, high: int) -> int:
    if not low <= int(value) <= high:
        raise ValueError(f"{label} must be between {low} and {high}.")
    return int(value)


class Employee:
    """Someone joining the company."""

    def __init__(self, first_name: str, last_name: str, email: str, gender: str, age: int,
                 marital_status: str, education_level: int, education_field: str,
                 hire_date: date, department_id: int, job_role_id: int, job_level: int,
                 monthly_income: int, over_time: bool = False,
                 business_travel: str = "Non-Travel", distance_from_home: int = 1,
                 stock_option_level: int = 0, total_working_years: int = 0,
                 num_companies_worked: int = 0, employee_id: Optional[int] = None) -> None:
        self.employee_id = employee_id
        self._first_name = _need_text(first_name, "First name", 60)
        self._last_name = _need_text(last_name, "Last name", 60)
        self._email = self._check_email(email)
        self._age = _need_range(age, "Age", 18, 70)
        self._job_level = _need_range(job_level, "Job level", 1, 5)
        self._education_level = _need_range(education_level, "Education level", 1, 5)
        self._monthly_income = self._check_income(monthly_income)
        self.gender, self.marital_status = gender, marital_status
        self.education_field, self.hire_date = education_field, hire_date
        self.department_id, self.job_role_id = department_id, job_role_id
        self.over_time, self.business_travel = bool(over_time), business_travel
        self.distance_from_home = distance_from_home
        self.stock_option_level = stock_option_level
        self.total_working_years = total_working_years
        self.num_companies_worked = num_companies_worked

    @staticmethod
    def _check_email(email: str) -> str:
        email = _need_text(email, "Email", 120).lower()
        if "@" not in email or "." not in email.split("@")[-1]:
            raise ValueError("That email doesn't look right.")
        return email

    @staticmethod
    def _check_income(value: int) -> int:
        if int(value) <= 0:
            raise ValueError("Monthly income must be more than zero.")
        return int(value)

    @property
    def first_name(self) -> str: return self._first_name
    @property
    def last_name(self) -> str: return self._last_name
    @property
    def email(self) -> str: return self._email
    @property
    def age(self) -> int: return self._age
    @property
    def job_level(self) -> int: return self._job_level
    @property
    def education_level(self) -> int: return self._education_level
    @property
    def monthly_income(self) -> int: return self._monthly_income

    @property
    def full_name(self) -> str:
        return f"{self._first_name} {self._last_name}"

    def to_row(self) -> dict:
        return {
            "first_name": self._first_name, "last_name": self._last_name, "email": self._email,
            "gender": self.gender, "age": self._age, "marital_status": self.marital_status,
            "education_level": self._education_level, "education_field": self.education_field,
            "hire_date": self.hire_date, "distance_from_home": self.distance_from_home,
            "business_travel": self.business_travel, "over_time": int(self.over_time),
            "stock_option_level": self.stock_option_level,
            "total_working_years": self.total_working_years,
            "num_companies_worked": self.num_companies_worked,
            "department_id": self.department_id, "job_role_id": self.job_role_id,
            "job_level": self._job_level, "monthly_income": self._monthly_income,
        }


class Project:
    """A piece of work people get assigned to."""

    def __init__(self, project_name: str, department_id: int, start_date: date,
                 status: str = "Active", priority: str = "Medium", budget: float = 0,
                 end_date: Optional[date] = None, project_id: Optional[int] = None) -> None:
        self.project_id = project_id
        self._name = _need_text(project_name, "Project name", 100)
        if status not in PROJECT_STATUSES:
            raise ValueError(f"Status must be one of {', '.join(PROJECT_STATUSES)}.")
        if priority not in PROJECT_PRIORITIES:
            raise ValueError(f"Priority must be one of {', '.join(PROJECT_PRIORITIES)}.")
        if end_date and end_date < start_date:
            raise ValueError("The end date can't be before the start date.")
        if budget < 0:
            raise ValueError("Budget can't be negative.")
        self.department_id, self.start_date, self.end_date = department_id, start_date, end_date
        self.status, self.priority, self.budget = status, priority, float(budget)

    @property
    def name(self) -> str:
        return self._name

    def to_row(self) -> dict:
        return {"project_name": self._name, "department_id": self.department_id,
                "status": self.status, "priority": self.priority, "budget": self.budget,
                "start_date": self.start_date, "end_date": self.end_date}


class Review:
    """A yearly performance review."""

    def __init__(self, employee_id: int, review_date: date, performance_rating: int,
                 job_satisfaction: int, environment_satisfaction: int, work_life_balance: int,
                 percent_salary_hike: int = 0, project_id: Optional[int] = None) -> None:
        self.employee_id, self.review_date, self.project_id = employee_id, review_date, project_id
        self._rating = _need_range(performance_rating, "Performance rating", 1, 4)
        self._job_sat = _need_range(job_satisfaction, "Job satisfaction", 1, 4)
        self._env_sat = _need_range(environment_satisfaction, "Environment satisfaction", 1, 4)
        self._wlb = _need_range(work_life_balance, "Work-life balance", 1, 4)
        self._hike = _need_range(percent_salary_hike, "Salary hike %", 0, 50)

    def compute_score(self) -> float:
        """60% from the rating, 40% from how the person feels (same idea as the synthesizer)."""
        mood = (self._job_sat + self._env_sat + self._wlb) / 12
        return round(self._rating / 4 * 60 + mood * 40, 2)

    def to_row(self) -> dict:
        return {"employee_id": self.employee_id, "project_id": self.project_id,
                "review_date": self.review_date, "performance_rating": self._rating,
                "job_satisfaction": self._job_sat, "environment_satisfaction": self._env_sat,
                "work_life_balance": self._wlb, "percent_salary_hike": self._hike,
                "review_score": self.compute_score()}
