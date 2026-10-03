"""Data entry screens: they write to the OLTP database and keep the warehouse in step."""
from datetime import date

import streamlit as st

from src.db_manager import DatabaseError
from src.entities import ASSIGNMENT_ROLES, PROJECT_PRIORITIES, PROJECT_STATUSES, Employee, Project, Review
from src.managers import (AnalyticsManager, EmployeeManager, EtlManager, ProjectManager,
                          ReviewManager)

EDUCATION = {1: "Below college", 2: "College", 3: "Bachelor's", 4: "Master's", 5: "Doctorate"}
RATING = {1: "1 - Low", 2: "2 - Good", 3: "3 - Excellent", 4: "4 - Outstanding"}
SCALE = {1: "1 - Low", 2: "2 - Medium", 3: "3 - High", 4: "4 - Very high"}


@st.cache_data(ttl=600)
def _departments():
    return EmployeeManager().list_departments()


@st.cache_data(ttl=600)
def _job_roles():
    return EmployeeManager().list_job_roles()


def _run(action):
    """Run a DAL call and show friendly messages. Returns the result, or None on failure."""
    try:
        return action()
    except ValueError as err:
        st.warning(str(err))
    except DatabaseError as err:
        st.error(str(err))
    return None


def render() -> None:
    st.title("Data entry")
    st.caption("Everything here is saved to the OLTP database. Warehouse updates run right after each save.")
    tabs = st.tabs(["Onboard employee", "New project", "Assign to project",
                    "Performance review", "Change department"])
    with tabs[0]:
        _onboard_tab()
    with tabs[1]:
        _project_tab()
    with tabs[2]:
        _assignment_tab()
    with tabs[3]:
        _review_tab()
    with tabs[4]:
        _department_change_tab()


def _onboard_tab() -> None:
    depts, roles = _departments(), _job_roles()
    dept_map = dict(zip(depts.department_name, depts.department_id))
    role_map = dict(zip(roles.job_title, roles.job_role_id))
    with st.form("onboard", clear_on_submit=True):
        c1, c2 = st.columns(2)
        first, last = c1.text_input("First name"), c2.text_input("Last name")
        email = st.text_input("Work email")
        c3, c4, c5 = st.columns(3)
        gender = c3.selectbox("Gender", ["Female", "Male"])
        age = c4.number_input("Age", 18, 70, 28)
        marital = c5.selectbox("Marital status", ["Single", "Married", "Divorced"])
        c6, c7 = st.columns(2)
        education = c6.selectbox("Education", list(EDUCATION), format_func=EDUCATION.get, index=2)
        field = c7.selectbox("Education field", ["Life Sciences", "Medical", "Marketing",
                                                 "Technical Degree", "Human Resources", "Other"])
        c8, c9, c10 = st.columns(3)
        dept = c8.selectbox("Department", list(dept_map))
        role = c9.selectbox("Job role", list(role_map))
        level = c10.selectbox("Job level", [1, 2, 3, 4, 5])
        c11, c12, c13 = st.columns(3)
        income = c11.number_input("Monthly income", 1000, 50000, 5000, step=100)
        hire = c12.date_input("Hire date", date.today())
        travel = c13.selectbox("Business travel", ["Non-Travel", "Travel_Rarely", "Travel_Frequently"])
        c14, c15 = st.columns(2)
        overtime = c14.checkbox("Works overtime")
        distance = c15.number_input("Distance from home (km)", 1, 100, 5)
        submitted = st.form_submit_button("Onboard employee", type="primary")
    if submitted:
        def action():
            employee = Employee(first, last, email, gender, int(age), marital, education, field, hire,
                                dept_map[dept], role_map[role], level, int(income), overtime, travel, int(distance))
            new_id = EmployeeManager().add_employee(employee)
            EtlManager().refresh_employee(new_id)
            return new_id
        new_id = _run(action)
        if new_id:
            st.cache_data.clear()
            st.success(f"{first} {last} is onboarded as employee #{new_id} and is already in the warehouse.")


def _project_tab() -> None:
    depts = _departments()
    dept_map = dict(zip(depts.department_name, depts.department_id))
    with st.form("project", clear_on_submit=True):
        name = st.text_input("Project name")
        c1, c2, c3 = st.columns(3)
        dept = c1.selectbox("Owning department", list(dept_map))
        status = c2.selectbox("Status", PROJECT_STATUSES)
        priority = c3.selectbox("Priority", PROJECT_PRIORITIES, index=1)
        c4, c5 = st.columns(2)
        budget = c4.number_input("Budget", 0, 10_000_000, 250_000, step=10_000)
        start = c5.date_input("Start date", date.today())
        submitted = st.form_submit_button("Create project", type="primary")
    if submitted:
        def action():
            pid = ProjectManager().create_project(Project(name, dept_map[dept], start, status, priority, budget))
            EtlManager().refresh_reviews()
            return pid
        pid = _run(action)
        if pid:
            st.success(f"Project #{pid} created.")


def _assignment_tab() -> None:
    projects = ProjectManager().list_projects()
    if projects.empty:
        st.info("There are no open projects yet. Create one first.")
        return
    labels = {f"{r.project_name}  ({r.department_name})": int(r.project_id) for r in projects.itertuples()}
    with st.form("assign", clear_on_submit=True):
        emp_id = st.number_input("Employee id", min_value=1, step=1)
        project = st.selectbox("Project", list(labels))
        c1, c2, c3 = st.columns(3)
        role = c1.selectbox("Role on project", ASSIGNMENT_ROLES)
        alloc = c2.slider("Allocation %", 5, 100, 50, step=5)
        start = c3.date_input("Start date", date.today())
        submitted = st.form_submit_button("Assign", type="primary")
    if submitted:
        def action():
            if EmployeeManager().get_profile(int(emp_id)) is None:
                raise ValueError(f"Employee {int(emp_id)} doesn't exist.")
            ProjectManager().assign_employee(int(emp_id), labels[project], role, alloc, start)
            return True
        if _run(action):
            st.success("Assigned. Their total workload is now "
                       f"{ProjectManager().current_allocation(int(emp_id))}%.")


def _review_tab() -> None:
    projects = ProjectManager().list_projects(open_only=False)
    labels = {"(not tied to a project)": None}
    labels.update({r.project_name: int(r.project_id) for r in projects.itertuples()})
    with st.form("review", clear_on_submit=True):
        c1, c2 = st.columns(2)
        emp_id = c1.number_input("Employee id", min_value=1, step=1)
        review_date = c2.date_input("Review date", date.today())
        project = st.selectbox("Project", list(labels))
        c3, c4 = st.columns(2)
        rating = c3.selectbox("Performance rating", list(RATING), format_func=RATING.get, index=2)
        hike = c4.number_input("Salary hike %", 0, 50, 10)
        c5, c6, c7 = st.columns(3)
        job_sat = c5.selectbox("Job satisfaction", list(SCALE), format_func=SCALE.get, index=2)
        env_sat = c6.selectbox("Environment satisfaction", list(SCALE), format_func=SCALE.get, index=2)
        wlb = c7.selectbox("Work-life balance", list(SCALE), format_func=SCALE.get, index=2)
        submitted = st.form_submit_button("Submit review", type="primary")
    if submitted:
        def action():
            review = Review(int(emp_id), review_date, rating, job_sat, env_sat, wlb, int(hike), labels[project])
            review_id = ReviewManager().submit_review(review)
            EtlManager().refresh_reviews()
            return review_id, review.compute_score()
        outcome = _run(action)
        if outcome:
            st.cache_data.clear()
            st.success(f"Review #{outcome[0]} saved with a score of {outcome[1]}. It's in the warehouse too.")


def _department_change_tab() -> None:
    st.write("Moving someone doesn't overwrite their past. The warehouse keeps the old row (closed) "
             "and adds a new one, which is what SCD Type 2 means.")
    emp_id = int(st.number_input("Employee id", min_value=1, step=1, key="move_emp"))
    profile = _run(lambda: EmployeeManager().get_profile(emp_id))
    if not profile:
        st.info("Enter an existing employee id to see their current department.")
        return
    st.markdown(f"**{profile['full_name']}** is in **{profile['department_name']}** as "
                f"{profile['job_title']} (level {profile['job_level']}), since the last change.")

    depts, roles = _departments(), _job_roles()
    dept_map = dict(zip(depts.department_name, depts.department_id))
    role_map = dict(zip(roles.job_title, roles.job_role_id))
    with st.form("move"):
        c1, c2, c3 = st.columns(3)
        new_dept = c1.selectbox("New department", [d for d in dept_map if d != profile["department_name"]])
        new_role = c2.selectbox("New job role", list(role_map))
        effective = c3.date_input("Effective date", date.today())
        submitted = st.form_submit_button("Move employee", type="primary")
    if submitted:
        def action():
            EmployeeManager().change_department(emp_id, dept_map[new_dept], role_map[new_role], effective)
            EtlManager().refresh_employee(emp_id)
            return AnalyticsManager().employee_history(emp_id)
        history = _run(action)
        if history is not None:
            st.cache_data.clear()
            st.success("Done. Here's what the warehouse holds for this employee now:")
            st.dataframe(history, hide_index=True, width="stretch")
