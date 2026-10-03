-- =====================================================================
-- 02_oltp_ddl.sql
-- The normalized backend the Streamlit forms talk to.
-- Departments and job roles live in their own lookup tables, an
-- employee's job changes live in employee_job_history, and everything
-- else hangs off employee_id.
-- =====================================================================

USE employee_oltp;

SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS performance_reviews;
DROP TABLE IF EXISTS project_assignments;
DROP TABLE IF EXISTS employee_job_history;
DROP TABLE IF EXISTS projects;
DROP TABLE IF EXISTS employees;
DROP TABLE IF EXISTS job_roles;
DROP TABLE IF EXISTS departments;
SET FOREIGN_KEY_CHECKS = 1;

CREATE TABLE departments (
    department_id   INT AUTO_INCREMENT PRIMARY KEY,
    department_name VARCHAR(60) NOT NULL,
    UNIQUE KEY uq_department_name (department_name)
);

CREATE TABLE job_roles (
    job_role_id INT AUTO_INCREMENT PRIMARY KEY,
    job_title   VARCHAR(60) NOT NULL,
    UNIQUE KEY uq_job_title (job_title)
);

CREATE TABLE employees (
    employee_id          INT AUTO_INCREMENT PRIMARY KEY,
    first_name           VARCHAR(60)  NOT NULL,
    last_name            VARCHAR(60)  NOT NULL,
    email                VARCHAR(120) NOT NULL,
    gender               VARCHAR(10)  NOT NULL,
    age                  TINYINT UNSIGNED NOT NULL,
    marital_status       VARCHAR(15)  NOT NULL,
    education_level      TINYINT      NOT NULL,
    education_field      VARCHAR(40)  NOT NULL,
    hire_date            DATE         NOT NULL,
    distance_from_home   SMALLINT     NOT NULL DEFAULT 1,
    business_travel      VARCHAR(30)  NOT NULL DEFAULT 'Non-Travel',
    over_time            TINYINT(1)   NOT NULL DEFAULT 0,
    stock_option_level   TINYINT      NOT NULL DEFAULT 0,
    total_working_years  SMALLINT     NOT NULL DEFAULT 0,
    num_companies_worked SMALLINT     NOT NULL DEFAULT 0,
    attrition            TINYINT(1)   NOT NULL DEFAULT 0,
    -- where the person sits today; the full story is in employee_job_history
    department_id        INT NOT NULL,
    job_role_id          INT NOT NULL,
    job_level            TINYINT NOT NULL,
    monthly_income       INT NOT NULL,
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_employee_email (email),
    KEY ix_employee_department (department_id),
    CONSTRAINT fk_emp_department FOREIGN KEY (department_id) REFERENCES departments (department_id),
    CONSTRAINT fk_emp_job_role   FOREIGN KEY (job_role_id)   REFERENCES job_roles (job_role_id),
    CONSTRAINT ck_emp_age    CHECK (age BETWEEN 18 AND 70),
    CONSTRAINT ck_emp_income CHECK (monthly_income > 0)
);

-- One row per "version" of an employee's job. effective_end is NULL while
-- the version is still the current one. This is the source the warehouse
-- uses to build its SCD Type 2 dimension.
CREATE TABLE employee_job_history (
    history_id      INT AUTO_INCREMENT PRIMARY KEY,
    employee_id     INT NOT NULL,
    department_id   INT NOT NULL,
    job_role_id     INT NOT NULL,
    job_level       TINYINT NOT NULL,
    monthly_income  INT NOT NULL,
    effective_start DATE NOT NULL,
    effective_end   DATE NULL,
    change_reason   VARCHAR(40) NOT NULL,
    UNIQUE KEY uq_history_version (employee_id, effective_start),
    CONSTRAINT fk_hist_employee   FOREIGN KEY (employee_id)   REFERENCES employees (employee_id),
    CONSTRAINT fk_hist_department FOREIGN KEY (department_id) REFERENCES departments (department_id),
    CONSTRAINT fk_hist_job_role   FOREIGN KEY (job_role_id)   REFERENCES job_roles (job_role_id)
);

CREATE TABLE projects (
    project_id    INT AUTO_INCREMENT PRIMARY KEY,
    project_name  VARCHAR(100) NOT NULL,
    department_id INT NOT NULL,
    status        VARCHAR(20)  NOT NULL DEFAULT 'Active',
    priority      VARCHAR(10)  NOT NULL DEFAULT 'Medium',
    budget        DECIMAL(12,2) NOT NULL DEFAULT 0,
    start_date    DATE NOT NULL,
    end_date      DATE NULL,
    UNIQUE KEY uq_project_name (project_name),
    CONSTRAINT fk_proj_department FOREIGN KEY (department_id) REFERENCES departments (department_id)
);

CREATE TABLE project_assignments (
    assignment_id   INT AUTO_INCREMENT PRIMARY KEY,
    employee_id     INT NOT NULL,
    project_id      INT NOT NULL,
    role_on_project VARCHAR(20) NOT NULL DEFAULT 'Contributor',
    allocation_pct  TINYINT UNSIGNED NOT NULL,
    start_date      DATE NOT NULL,
    end_date        DATE NULL,
    UNIQUE KEY uq_assignment (employee_id, project_id),
    KEY ix_assignment_project (project_id),
    CONSTRAINT fk_asg_employee FOREIGN KEY (employee_id) REFERENCES employees (employee_id),
    CONSTRAINT fk_asg_project  FOREIGN KEY (project_id)  REFERENCES projects (project_id),
    CONSTRAINT ck_asg_alloc CHECK (allocation_pct BETWEEN 1 AND 100)
);

CREATE TABLE performance_reviews (
    review_id                INT AUTO_INCREMENT PRIMARY KEY,
    employee_id              INT NOT NULL,
    project_id               INT NULL,
    review_date              DATE NOT NULL,
    performance_rating       TINYINT NOT NULL,
    job_satisfaction         TINYINT NOT NULL,
    environment_satisfaction TINYINT NOT NULL,
    work_life_balance        TINYINT NOT NULL,
    percent_salary_hike      TINYINT NOT NULL DEFAULT 0,
    review_score             DECIMAL(5,2) NOT NULL,
    UNIQUE KEY uq_review_per_day (employee_id, review_date),
    KEY ix_review_project (project_id),
    CONSTRAINT fk_rev_employee FOREIGN KEY (employee_id) REFERENCES employees (employee_id),
    CONSTRAINT fk_rev_project  FOREIGN KEY (project_id)  REFERENCES projects (project_id),
    CONSTRAINT ck_rev_rating CHECK (performance_rating BETWEEN 1 AND 4)
);
