-- =====================================================================
-- 04_staging_to_oltp.sql
-- Moves the raw staging data into the normalized OLTP tables.
-- This is where the messy bits get cleaned:
--   * duplicate employees / reviews are collapsed with ROW_NUMBER()
--   * stray spaces and upper-case emails are tidied up
--   * text values are swapped for lookup ids (departments, job roles)
-- Safe to run more than once: anything already loaded is skipped.
-- =====================================================================

USE employee_oltp;

DROP PROCEDURE IF EXISTS sp_load_oltp_from_staging;

DELIMITER $$

CREATE PROCEDURE sp_load_oltp_from_staging()
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    -- 1) lookup tables ------------------------------------------------
    INSERT IGNORE INTO departments (department_name)
    SELECT DISTINCT TRIM(department) FROM employee_staging.stg_employee_snapshot
    UNION
    SELECT DISTINCT TRIM(department) FROM employee_staging.stg_employee_history
    UNION
    SELECT DISTINCT TRIM(department) FROM employee_staging.stg_projects;

    INSERT IGNORE INTO job_roles (job_title)
    SELECT DISTINCT TRIM(job_role) FROM employee_staging.stg_employee_snapshot
    UNION
    SELECT DISTINCT TRIM(job_role) FROM employee_staging.stg_employee_history;

    -- 2) employees: keep one row per employee_id --------------------
    INSERT INTO employees
        (employee_id, first_name, last_name, email, gender, age, marital_status,
         education_level, education_field, hire_date, distance_from_home,
         business_travel, over_time, stock_option_level, total_working_years,
         num_companies_worked, attrition, department_id, job_role_id,
         job_level, monthly_income)
    WITH ranked AS (
        SELECT s.*,
               ROW_NUMBER() OVER (PARTITION BY s.employee_id
                                  ORDER BY s.hire_date DESC) AS rn
        FROM employee_staging.stg_employee_snapshot s
    )
    SELECT r.employee_id, TRIM(r.first_name), TRIM(r.last_name),
           LOWER(TRIM(r.email)), TRIM(r.gender), r.age, TRIM(r.marital_status),
           r.education, TRIM(r.education_field), r.hire_date, r.distance_from_home,
           TRIM(r.business_travel), (TRIM(r.over_time) = 'Yes'), r.stock_option_level,
           r.total_working_years, r.num_companies_worked, (TRIM(r.attrition) = 'Yes'),
           d.department_id, jr.job_role_id, r.job_level, r.monthly_income
    FROM ranked r
    JOIN departments d ON d.department_name = TRIM(r.department)
    JOIN job_roles  jr ON jr.job_title      = TRIM(r.job_role)
    LEFT JOIN employees e ON e.employee_id = r.employee_id
    WHERE r.rn = 1
      AND e.employee_id IS NULL;

    -- 3) job history (the raw material for SCD Type 2) ------------
    INSERT INTO employee_job_history
        (employee_id, department_id, job_role_id, job_level, monthly_income,
         effective_start, effective_end, change_reason)
    SELECT h.employee_id, d.department_id, jr.job_role_id, h.job_level,
           h.monthly_income, h.effective_start, h.effective_end, h.change_reason
    FROM employee_staging.stg_employee_history h
    JOIN employees e   ON e.employee_id = h.employee_id
    JOIN departments d ON d.department_name = TRIM(h.department)
    JOIN job_roles jr  ON jr.job_title      = TRIM(h.job_role)
    LEFT JOIN employee_job_history x
           ON x.employee_id = h.employee_id AND x.effective_start = h.effective_start
    WHERE x.history_id IS NULL;

    -- 4) projects ---------------------------------------------------
    INSERT INTO projects
        (project_id, project_name, department_id, status, priority, budget,
         start_date, end_date)
    SELECT p.project_id, TRIM(p.project_name), d.department_id, p.status,
           p.priority, p.budget, p.start_date, p.end_date
    FROM employee_staging.stg_projects p
    JOIN departments d ON d.department_name = TRIM(p.department)
    LEFT JOIN projects x ON x.project_id = p.project_id
    WHERE x.project_id IS NULL;

    -- 5) assignments --------------------------------------------------
    INSERT INTO project_assignments
        (employee_id, project_id, role_on_project, allocation_pct, start_date, end_date)
    SELECT a.employee_id, a.project_id, a.role_on_project, a.allocation_pct,
           a.start_date, a.end_date
    FROM employee_staging.stg_assignments a
    JOIN employees e ON e.employee_id = a.employee_id
    JOIN projects  p ON p.project_id  = a.project_id
    LEFT JOIN project_assignments x
           ON x.employee_id = a.employee_id AND x.project_id = a.project_id
    WHERE x.assignment_id IS NULL;

    -- 6) reviews: one review per employee per day ------------------
    INSERT INTO performance_reviews
        (review_id, employee_id, project_id, review_date, performance_rating,
         job_satisfaction, environment_satisfaction, work_life_balance,
         percent_salary_hike, review_score)
    WITH ranked AS (
        SELECT r.*,
               ROW_NUMBER() OVER (PARTITION BY r.employee_id, r.review_date
                                  ORDER BY r.review_id) AS rn
        FROM employee_staging.stg_reviews r
    )
    SELECT r.review_id, r.employee_id, r.project_id, r.review_date,
           r.performance_rating, r.job_satisfaction, r.environment_satisfaction,
           r.work_life_balance, r.percent_salary_hike, r.review_score
    FROM ranked r
    JOIN employees e ON e.employee_id = r.employee_id
    LEFT JOIN performance_reviews x
           ON x.employee_id = r.employee_id AND x.review_date = r.review_date
    WHERE r.rn = 1
      AND x.review_id IS NULL;

    COMMIT;
END$$

DELIMITER ;
