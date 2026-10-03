-- =====================================================================
-- 03_olap_ddl.sql
-- Star schema for the warehouse.
--
--   fact_performance_reviews  (grain: one performance review)
--      -> dim_employee   (SCD Type 2, surrogate key employee_key)
--      -> dim_department (surrogate key department_key)
--      -> dim_project    (surrogate key project_key)
--      -> dim_date       (smart key yyyymmdd)
--
-- Every dimension has its own surrogate key. The "real" ids from the
-- OLTP side (employee_id, project_id ...) are kept as business keys.
-- =====================================================================

USE employee_dw;

SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS fact_performance_reviews;
DROP TABLE IF EXISTS dim_employee;
DROP TABLE IF EXISTS dim_department;
DROP TABLE IF EXISTS dim_project;
DROP TABLE IF EXISTS dim_date;
SET FOREIGN_KEY_CHECKS = 1;

CREATE TABLE dim_date (
    date_key       INT PRIMARY KEY,          -- 20251215
    full_date      DATE NOT NULL,
    day_of_month   TINYINT NOT NULL,
    day_name       VARCHAR(10) NOT NULL,
    month_number   TINYINT NOT NULL,
    month_name     VARCHAR(10) NOT NULL,
    quarter_number TINYINT NOT NULL,
    year_number    SMALLINT NOT NULL,
    is_weekend     TINYINT(1) NOT NULL,
    UNIQUE KEY uq_dim_date_full (full_date)
);

CREATE TABLE dim_department (
    department_key  INT AUTO_INCREMENT PRIMARY KEY,
    department_id   INT NOT NULL,
    department_name VARCHAR(60) NOT NULL,
    UNIQUE KEY uq_dim_dept_id (department_id),
    UNIQUE KEY uq_dim_dept_name (department_name)
);

CREATE TABLE dim_project (
    project_key     INT AUTO_INCREMENT PRIMARY KEY,
    project_id      INT NOT NULL,
    project_name    VARCHAR(100) NOT NULL,
    department_name VARCHAR(60)  NULL,
    status          VARCHAR(20)  NULL,
    priority        VARCHAR(10)  NULL,
    budget          DECIMAL(12,2) NULL,
    start_date      DATE NULL,
    end_date        DATE NULL,
    UNIQUE KEY uq_dim_project_id (project_id)
);

-- The "unknown member": reviews that were not tied to a project point here
-- instead of carrying a NULL foreign key into the fact table.
INSERT INTO dim_project (project_key, project_id, project_name, status)
VALUES (-1, 0, 'No project', 'n/a');

-- SCD Type 2: every change in department / role / level / salary creates
-- a NEW row. start_date/end_date say when that version was true, and
-- is_current flags the live one (end_date = 9999-12-31 for it).
-- Age, marital status, attrition and name are treated as Type 1
-- (overwritten in place) because we don't need their history.
CREATE TABLE dim_employee (
    employee_key    INT AUTO_INCREMENT PRIMARY KEY,
    employee_id     INT NOT NULL,
    full_name       VARCHAR(130) NOT NULL,
    gender          VARCHAR(10)  NOT NULL,
    age             TINYINT UNSIGNED NOT NULL,
    marital_status  VARCHAR(15)  NOT NULL,
    education_level TINYINT      NOT NULL,
    education_field VARCHAR(40)  NOT NULL,
    hire_date       DATE         NOT NULL,
    department_name VARCHAR(60)  NOT NULL,
    job_role        VARCHAR(60)  NOT NULL,
    job_level       TINYINT      NOT NULL,
    monthly_income  INT          NOT NULL,
    attrition_flag  TINYINT(1)   NOT NULL,
    over_time_flag  TINYINT(1)   NOT NULL,
    start_date      DATE         NOT NULL,
    end_date        DATE         NOT NULL,
    is_current      TINYINT(1)   NOT NULL,
    change_reason   VARCHAR(40)  NULL,
    UNIQUE KEY uq_dim_emp_version (employee_id, start_date),
    KEY ix_dim_emp_current (is_current, department_name)
);

CREATE TABLE fact_performance_reviews (
    review_key               BIGINT AUTO_INCREMENT PRIMARY KEY,
    review_id                INT NOT NULL,        -- degenerate dimension (OLTP id)
    employee_key             INT NOT NULL,
    department_key           INT NOT NULL,
    project_key              INT NOT NULL,
    date_key                 INT NOT NULL,
    performance_rating       TINYINT NOT NULL,
    job_satisfaction         TINYINT NOT NULL,
    environment_satisfaction TINYINT NOT NULL,
    work_life_balance        TINYINT NOT NULL,
    percent_salary_hike      TINYINT NOT NULL,
    review_score             DECIMAL(5,2) NOT NULL,
    UNIQUE KEY uq_fact_review_id (review_id),
    KEY ix_fact_date (date_key),
    CONSTRAINT fk_fact_employee   FOREIGN KEY (employee_key)   REFERENCES dim_employee (employee_key),
    CONSTRAINT fk_fact_department FOREIGN KEY (department_key) REFERENCES dim_department (department_key),
    CONSTRAINT fk_fact_project    FOREIGN KEY (project_key)    REFERENCES dim_project (project_key),
    CONSTRAINT fk_fact_date       FOREIGN KEY (date_key)       REFERENCES dim_date (date_key)
);
