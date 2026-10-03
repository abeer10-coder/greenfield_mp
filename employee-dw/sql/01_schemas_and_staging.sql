-- =====================================================================
-- 01_schemas_and_staging.sql
-- Creates the three databases we work with and the staging tables that
-- the Python loader fills with the synthesized CSVs.
--
--   employee_staging : raw, "as delivered" data (no constraints on purpose)
--   employee_oltp    : normalized app database
--   employee_dw      : star schema for analytics
--
-- Staging tables deliberately have no primary keys: the synthesizer
-- sprinkles in a few duplicates and messy values, and we want the
-- cleaning step (CTEs + window functions) to be the one that deals
-- with them.
-- =====================================================================

CREATE DATABASE IF NOT EXISTS employee_staging;
CREATE DATABASE IF NOT EXISTS employee_oltp;
CREATE DATABASE IF NOT EXISTS employee_dw;

USE employee_staging;

DROP TABLE IF EXISTS stg_employee_snapshot;
CREATE TABLE stg_employee_snapshot (
    employee_id          INT,
    first_name           VARCHAR(60),
    last_name            VARCHAR(60),
    email                VARCHAR(120),
    hire_date            DATE,
    age                  INT,
    attrition            VARCHAR(3),
    business_travel      VARCHAR(30),
    department           VARCHAR(40),
    distance_from_home   INT,
    education            INT,
    education_field      VARCHAR(40),
    gender               VARCHAR(10),
    job_level            INT,
    job_role             VARCHAR(40),
    marital_status       VARCHAR(15),
    monthly_income       INT,
    num_companies_worked INT,
    over_time            VARCHAR(3),
    stock_option_level   INT,
    total_working_years  INT,
    years_at_company     INT,
    KEY ix_stg_snapshot_emp (employee_id)
);

DROP TABLE IF EXISTS stg_employee_history;
CREATE TABLE stg_employee_history (
    employee_id     INT,
    department      VARCHAR(40),
    job_role        VARCHAR(40),
    job_level       INT,
    monthly_income  INT,
    effective_start DATE,
    effective_end   DATE NULL,
    change_reason   VARCHAR(40),
    KEY ix_stg_history_emp (employee_id, effective_start)
);

DROP TABLE IF EXISTS stg_projects;
CREATE TABLE stg_projects (
    project_id   INT,
    project_name VARCHAR(100),
    department   VARCHAR(40),
    status       VARCHAR(20),
    priority     VARCHAR(10),
    budget       DECIMAL(12,2),
    start_date   DATE,
    end_date     DATE NULL
);

DROP TABLE IF EXISTS stg_assignments;
CREATE TABLE stg_assignments (
    employee_id     INT,
    project_id      INT,
    role_on_project VARCHAR(20),
    allocation_pct  INT,
    start_date      DATE,
    end_date        DATE NULL,
    KEY ix_stg_assign_emp (employee_id)
);

DROP TABLE IF EXISTS stg_reviews;
CREATE TABLE stg_reviews (
    review_id                INT,
    employee_id              INT,
    project_id               INT NULL,
    review_date              DATE,
    performance_rating       INT,
    job_satisfaction         INT,
    environment_satisfaction INT,
    work_life_balance        INT,
    percent_salary_hike      INT,
    review_score             DECIMAL(5,2),
    KEY ix_stg_reviews_emp (employee_id, review_date)
);
