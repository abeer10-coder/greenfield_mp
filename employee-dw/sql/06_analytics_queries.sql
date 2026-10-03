-- =====================================================================
-- 06_analytics_queries.sql
-- The queries behind the dashboard, with plain literals so you can paste
-- them straight into MySQL Workbench. (The app runs the same logic with
-- bound parameters.)
-- =====================================================================

USE employee_dw;

-- 1) Year-over-year performance by department (CTE + LAG) -------------
WITH yearly AS (
    SELECT dt.year_number AS review_year,
           dep.department_name,
           AVG(f.review_score) AS avg_score,
           COUNT(*)            AS reviews
    FROM fact_performance_reviews f
    JOIN dim_date       dt  ON dt.date_key = f.date_key
    JOIN dim_department dep ON dep.department_key = f.department_key
    GROUP BY dt.year_number, dep.department_name
)
SELECT review_year, department_name, ROUND(avg_score, 2) AS avg_score, reviews,
       ROUND(avg_score - LAG(avg_score) OVER (PARTITION BY department_name
                                              ORDER BY review_year), 2) AS yoy_change
FROM yearly
ORDER BY department_name, review_year;

-- 2) Top 5 performers per department in 2025 (DENSE_RANK) ------------
WITH per_employee AS (
    SELECT e.employee_id, e.full_name, dep.department_name,
           ROUND(AVG(f.review_score), 2) AS avg_score
    FROM fact_performance_reviews f
    JOIN dim_employee   e   ON e.employee_key = f.employee_key
    JOIN dim_department dep ON dep.department_key = f.department_key
    JOIN dim_date       dt  ON dt.date_key = f.date_key
    WHERE dt.year_number = 2025
    GROUP BY e.employee_id, e.full_name, dep.department_name
),
ranked AS (
    SELECT per_employee.*,
           DENSE_RANK() OVER (PARTITION BY department_name
                              ORDER BY avg_score DESC) AS dept_rank
    FROM per_employee
)
SELECT * FROM ranked WHERE dept_rank <= 5 ORDER BY department_name, dept_rank;

-- 3) Attrition by department and overtime ----------------------------
SELECT department_name,
       CASE WHEN over_time_flag = 1 THEN 'Overtime' ELSE 'No overtime' END AS overtime_group,
       COUNT(*) AS headcount,
       SUM(attrition_flag) AS leavers,
       ROUND(100 * AVG(attrition_flag), 1) AS attrition_rate_pct
FROM dim_employee
WHERE is_current = 1
GROUP BY department_name, over_time_flag
ORDER BY department_name, over_time_flag;

-- 4) Projects where people struggle the most (RANK) -------------------
WITH project_stats AS (
    SELECT p.project_name, p.department_name, p.status,
           COUNT(*) AS reviews,
           ROUND(AVG(f.review_score), 2) AS avg_score,
           ROUND(100 * AVG(f.performance_rating <= 2), 1) AS low_rating_pct
    FROM fact_performance_reviews f
    JOIN dim_project p ON p.project_key = f.project_key
    WHERE p.project_key <> -1
    GROUP BY p.project_name, p.department_name, p.status
    HAVING COUNT(*) >= 20
)
SELECT RANK() OVER (ORDER BY avg_score ASC) AS bottleneck_rank, project_stats.*
FROM project_stats
ORDER BY bottleneck_rank
LIMIT 10;

-- 5) SCD Type 2 in action: everything the warehouse knows about one person
SELECT employee_key, employee_id, full_name, department_name, job_role,
       job_level, monthly_income, start_date, end_date, is_current, change_reason
FROM dim_employee
WHERE employee_id = (SELECT employee_id FROM dim_employee
                     GROUP BY employee_id HAVING COUNT(*) > 1 LIMIT 1)
ORDER BY start_date;
