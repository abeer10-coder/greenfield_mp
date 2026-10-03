"""Analytics dashboard: everything on this page reads from the star schema."""
import plotly.express as px
import streamlit as st

from src.db_manager import DatabaseError
from src.managers import AnalyticsManager

PALETTE = ["#0F6B6B", "#D08C1F", "#3E4C59", "#8E4B6B", "#6AA6A6"]


@st.cache_data(ttl=300)
def _kpis():
    return AnalyticsManager().kpis()


@st.cache_data(ttl=300)
def _years():
    return AnalyticsManager().review_years()


@st.cache_data(ttl=300)
def _trend():
    return AnalyticsManager().yearly_trend()


@st.cache_data(ttl=300)
def _top(year, top_n):
    return AnalyticsManager().top_performers(year, top_n)


@st.cache_data(ttl=300)
def _attrition():
    return AnalyticsManager().attrition_by_group()


@st.cache_data(ttl=300)
def _risk(top_n):
    return AnalyticsManager().attrition_risk_list(top_n)


@st.cache_data(ttl=300)
def _bottlenecks():
    return AnalyticsManager().project_bottlenecks()


def render() -> None:
    st.title("People analytics")
    try:
        k = _kpis()
    except DatabaseError as err:
        st.error(f"The warehouse isn't ready yet: {err}")
        st.info("Run the setup and ETL scripts first (see the README).")
        return

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Current employees", f"{k['employees']:,}")
    c2.metric("Reviews on file", f"{k['reviews']:,}")
    c3.metric("Average review score", f"{k['avg_score']}")
    c4.metric("Attrition rate", f"{k['attrition_pct']}%")
    c5.metric("People with job history", f"{k['with_history']:,}")

    trend_tab, top_tab, attrition_tab, project_tab, scd_tab = st.tabs(
        ["Performance trends", "Top performers", "Attrition risk", "Project bottlenecks", "Employee history"])

    with trend_tab:
        trend = _trend()
        metric = st.radio("Measure", ["avg_score", "avg_rating"], horizontal=True,
                          format_func=lambda m: "Review score (0-100)" if m == "avg_score" else "Performance rating (1-4)")
        fig = px.line(trend, x="review_year", y=metric, color="department_name", markers=True,
                      color_discrete_sequence=PALETTE, labels={"review_year": "Year", "department_name": "Department"})
        fig.update_xaxes(dtick=1)
        st.plotly_chart(fig, width="stretch")
        st.caption("Year-over-year change in review score (computed in SQL with LAG):")
        st.dataframe(trend[["department_name", "review_year", "avg_score", "yoy_change", "reviews"]],
                     hide_index=True, width="stretch")

    with top_tab:
        years = _years()
        c1, c2 = st.columns(2)
        year = c1.selectbox("Year", years, index=len(years) - 1)
        top_n = c2.slider("Show the top N ranks per department", 1, 10, 3)
        top = _top(year, top_n)
        st.caption("Ranks come from DENSE_RANK(), so employees with identical scores share a rank "
                   "and a department can show more than N people.")
        fig = px.bar(top, x="avg_score", y="full_name", color="department_name", orientation="h",
                     color_discrete_sequence=PALETTE, hover_data=["dept_rank", "avg_rating"],
                     labels={"avg_score": "Average review score", "full_name": "", "department_name": "Department"})
        fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=max(400, 22 * len(top)))
        st.plotly_chart(fig, width="stretch")
        st.dataframe(top, hide_index=True, width="stretch")

    with attrition_tab:
        attrition = _attrition()
        fig = px.bar(attrition, x="department_name", y="attrition_rate_pct", color="overtime_group",
                     barmode="group", color_discrete_sequence=PALETTE[:2],
                     labels={"department_name": "Department", "attrition_rate_pct": "Attrition rate (%)",
                             "overtime_group": ""})
        st.plotly_chart(fig, width="stretch")
        st.subheader("Current employees who look most at risk")
        st.caption("Score = overtime (2) + low job satisfaction (2) + poor work-life balance (1) "
                   "+ low rating (1), based on each person's latest review. A conversation starter, not a verdict.")
        st.dataframe(_risk(st.slider("How many people to list", 10, 50, 20, step=5)),
                     hide_index=True, width="stretch")

    with project_tab:
        projects = _bottlenecks()
        if projects.empty:
            st.info("No projects have enough reviews yet.")
        else:
            fig = px.scatter(projects, x="avg_score", y="low_rating_pct", size="reviews", color="department_name",
                             hover_name="project_name", color_discrete_sequence=PALETTE,
                             labels={"avg_score": "Average review score", "low_rating_pct": "Low ratings (%)",
                                     "department_name": "Department"})
            st.plotly_chart(fig, width="stretch")
            st.caption("Projects in the bottom-right (low scores, many low ratings) are the likeliest bottlenecks.")
            st.dataframe(projects.head(15), hide_index=True, width="stretch")

    with scd_tab:
        st.write("Look up any employee to see every version the warehouse has kept for them.")
        emp_id = int(st.number_input("Employee id", min_value=1, value=1001, step=1, key="history_emp"))
        history = AnalyticsManager().employee_history(emp_id)
        if history.empty:
            st.info("No employee with that id.")
        else:
            st.dataframe(history, hide_index=True, width="stretch")
