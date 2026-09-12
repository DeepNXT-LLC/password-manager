CREATE TABLE password_manager (
    password_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    employee_name VARCHAR(255) NOT NULL,
    account_name VARCHAR(255) NOT NULL,
    username VARCHAR(255) NOT NULL,

    account_password TEXT NOT NULL,

    notes TEXT,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_account UNIQUE(employee_name, account_name, username)
);