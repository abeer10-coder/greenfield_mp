-- =====================================================================
-- 05_dw_etl_procedures.sql
-- OLTP -> star schema. One procedure per table, plus sp_run_full_etl
-- which calls them in the right order (dimensions first, fact last).
--
-- The interesting one is sp_load_dim_employee_scd2:
--   1. LEAD() over the job history works out when each version ends
--   2. versions we already have get their end_date / is_current fixed
--      (that is the "expire the old row" part of SCD Type 2)
--   3. versions we have never seen get inserted with a brand new
--      surrogate key (the "add the new row" part)
-- Pass an employee_id to refresh just one person, or NULL for everyone.
-- =====================================================================

USE employee_dw;

DROP PROCEDURE IF EXISTS sp_load_dim_date;
DROP PROCEDURE IF EXISTS sp_load_dim_department;
DROP PROCEDURE IF EXISTS sp_load_dim_project;
DROP PROCEDURE IF EXISTS sp_load_dim_employee_scd2;
DROP PROCEDURE IF EXISTS sp_load_fact_performance_reviews;
DROP PROCEDURE IF EXISTS sp_run_full_etl;

DELIMITER $$

-- ---------------------------------------------------------------------
-- Calendar dimension. We build the list of days from a tiny digits table
-- (0-9 cross joined five times = 100,000 numbers), no recursion needed.
-- ---------------------------------------------------------------------
CREATE PROCEDURE sp_load_dim_date(IN p_start DATE, IN p_end DATE)
BEGIN
    INSERT IGNORE INTO dim_date
        (date_key, full_date, day_of_month, day_name, month_number,
         month_name, quarter_number, year_number, is_weekend)
    WITH digits AS (
        SELECT 0 AS n UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3
        UNION ALL SELECT 4 UNION ALL SELECT 5 UNION ALL SELECT 6
        UNION ALL SELECT 7 UNION ALL SELECT 8 UNION ALL SELECT 9
    ),
    numbers AS (
        SELECT a.n + 10 * b.n + 100 * c.n + 1000 * d.n + 10000 * e.n AS n
        FROM digits a CROSS JOIN digits b CROSS JOIN digits c
             CROSS JOIN digits d CROSS JOIN digits e
    ),
    calendar AS (
        SELECT DATE_ADD(p_start, INTERVAL n DAY) AS d
        FROM numbers
        WHERE n <= DATEDIFF(p_end, p_start)
    )
    SELECT YEAR(d) * 10000 + MONTH(d) * 100 + DAY(d), d, DAY(d), DAYNAME(d),
           MONTH(d), MONTHNAME(d), QUARTER(d), YEAR(d),
           CASE WHEN DAYOFWEEK(d) IN (1, 7) THEN 1 ELSE 0 END
    FROM calendar;
END$$

-- ---------------------------------------------------------------------
-- Department dimension (Type 1: names just get overwritten)
-- ---------------------------------------------------------------------
CREATE PROCEDURE sp_load_dim_department()
BEGIN
    UPDATE dim_department dd
    JOIN employee_oltp.departments d ON d.department_id = dd.department_id
    SET dd.department_name = d.department_name
    WHERE dd.department_name <> d.department_name;

    INSERT INTO dim_department (department_id, department_name)
    SELECT d.department_id, d.department_name
    FROM employee_oltp.departments d
    LEFT JOIN dim_department dd ON dd.department_id = d.department_id
    WHERE dd.department_key IS NULL;
END$$

-- ---------------------------------------------------------------------
-- Project dimension (Type 1)
-- ---------------------------------------------------------------------
CREATE PROCEDURE sp_load_dim_project()
BEGIN
    UPDATE dim_project dp
    JOIN employee_oltp.projects p    ON p.project_id = dp.project_id
    JOIN employee_oltp.departments d ON d.department_id = p.department_id
    SET dp.project_name    = p.project_name,
        dp.department_name = d.department_name,
        dp.status          = p.status,
        dp.priority        = p.priority,
        dp.budget          = p.budget,
        dp.start_date      = p.start_date,
        dp.end_date        = p.end_date;

    INSERT INTO dim_project
        (project_id, project_name, department_name, status, priority, budget,
         start_date, end_date)
    SELECT p.project_id, p.project_name, d.department_name, p.status, p.priority,
           p.budget, p.start_date, p.end_date
    FROM employee_oltp.projects p
    JOIN employee_oltp.departments d ON d.department_id = p.department_id
    LEFT JOIN dim_project dp ON dp.project_id = p.project_id
    WHERE dp.project_key IS NULL;
END$$

-- ---------------------------------------------------------------------
-- Employee dimension, SCD Type 2
-- ---------------------------------------------------------------------
CREATE PROCEDURE sp_load_dim_employee_scd2(IN p_employee_id INT)
BEGIN
    DROP TEMPORARY TABLE IF EXISTS tmp_emp_versions;

    -- Every version of every (selected) employee, with its end date worked
    -- out from the start of the *next* version.
    CREATE TEMPORARY TABLE tmp_emp_versions AS
    WITH timeline AS (
        SELECT h.employee_id, h.effective_start, h.department_id, h.job_role_id,
               h.job_level, h.monthly_income, h.change_reason,
               LEAD(h.effective_start) OVER (PARTITION BY h.employee_id
                                             ORDER BY h.effective_start) AS next_start
        FROM employee_oltp.employee_job_history h
        WHERE p_employee_id IS NULL OR h.employee_id = p_employee_id
    )
    SELECT t.employee_id,
           t.effective_start AS start_date,
           COALESCE(DATE_SUB(t.next_start, INTERVAL 1 DAY), CAST('9999-12-31' AS DATE)) AS end_date,
           CASE WHEN t.next_start IS NULL THEN 1 ELSE 0 END AS is_current,
           CONCAT(e.first_name, ' ', e.last_name) AS full_name,
           e.gender, e.age, e.marital_status, e.education_level, e.education_field,
           e.hire_date, e.attrition, e.over_time,
           d.department_name, jr.job_title, t.job_level, t.monthly_income,
           t.change_reason
    FROM timeline t
    JOIN employee_oltp.employees   e  ON e.employee_id    = t.employee_id
    JOIN employee_oltp.departments d  ON d.department_id  = t.department_id
    JOIN employee_oltp.job_roles   jr ON jr.job_role_id   = t.job_role_id;

    ALTER TABLE tmp_emp_versions ADD PRIMARY KEY (employee_id, start_date);

    -- Step 1: close out old rows (and refresh the Type 1 columns)
    UPDATE dim_employee d
    JOIN tmp_emp_versions v
      ON v.employee_id = d.employee_id AND v.start_date = d.start_date
    SET d.end_date       = v.end_date,
        d.is_current     = v.is_current,
        d.full_name      = v.full_name,
        d.age            = v.age,
        d.marital_status = v.marital_status,
        d.attrition_flag = v.attrition,
        d.over_time_flag = v.over_time
    WHERE d.end_date <> v.end_date
       OR d.is_current <> v.is_current
       OR d.full_name <> v.full_name
       OR d.age <> v.age
       OR d.marital_status <> v.marital_status
       OR d.attrition_flag <> v.attrition
       OR d.over_time_flag <> v.over_time;

    -- Step 2: add versions the warehouse has not seen yet
    INSERT INTO dim_employee
        (employee_id, full_name, gender, age, marital_status, education_level,
         education_field, hire_date, department_name, job_role, job_level,
         monthly_income, attrition_flag, over_time_flag, start_date, end_date,
         is_current, change_reason)
    SELECT v.employee_id, v.full_name, v.gender, v.age, v.marital_status,
           v.education_level, v.education_field, v.hire_date, v.department_name,
           v.job_title, v.job_level, v.monthly_income, v.attrition, v.over_time,
           v.start_date, v.end_date, v.is_current, v.change_reason
    FROM tmp_emp_versions v
    LEFT JOIN dim_employee d
           ON d.employee_id = v.employee_id AND d.start_date = v.start_date
    WHERE d.employee_key IS NULL;

    DROP TEMPORARY TABLE IF EXISTS tmp_emp_versions;
END$$

-- ---------------------------------------------------------------------
-- Fact table. Only reviews that are not in the fact table yet get loaded.
-- The employee_key is the version that was TRUE ON THE REVIEW DATE, which
-- is the whole point of SCD Type 2.
-- ---------------------------------------------------------------------
CREATE PROCEDURE sp_load_fact_performance_reviews()
BEGIN
    INSERT INTO fact_performance_reviews
        (review_id, employee_key, department_key, project_key, date_key,
         performance_rating, job_satisfaction, environment_satisfaction,
         work_life_balance, percent_salary_hike, review_score)
    WITH new_reviews AS (
        SELECT r.*,
               ROW_NUMBER() OVER (PARTITION BY r.employee_id, r.review_date
                                  ORDER BY r.review_id) AS rn
        FROM employee_oltp.performance_reviews r
        LEFT JOIN fact_performance_reviews f ON f.review_id = r.review_id
        WHERE f.review_id IS NULL
    )
    SELECT nr.review_id, e.employee_key, dd.department_key,
           COALESCE(dp.project_key, -1), dt.date_key,
           nr.performance_rating, nr.job_satisfaction, nr.environment_satisfaction,
           nr.work_life_balance, nr.percent_salary_hike, nr.review_score
    FROM new_reviews nr
    JOIN dim_employee   e  ON e.employee_id = nr.employee_id
                          AND nr.review_date BETWEEN e.start_date AND e.end_date
    JOIN dim_department dd ON dd.department_name = e.department_name
    JOIN dim_date       dt ON dt.full_date = nr.review_date
    LEFT JOIN dim_project dp ON dp.project_id = nr.project_id
    WHERE nr.rn = 1;
END$$

-- ---------------------------------------------------------------------
-- The whole pipeline in one call
-- ---------------------------------------------------------------------
CREATE PROCEDURE sp_run_full_etl()
BEGIN
    CALL sp_load_dim_date('2015-01-01', '2030-12-31');
    CALL sp_load_dim_department();
    CALL sp_load_dim_project();
    CALL sp_load_dim_employee_scd2(NULL);
    CALL sp_load_fact_performance_reviews();
END$$

DELIMITER ;
