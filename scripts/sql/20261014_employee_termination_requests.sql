-- Apply during a controlled PostgreSQL deployment BEFORE enabling termination request routes.
-- Additive migration: no existing employee or contract records are changed.
BEGIN;
CREATE TABLE IF NOT EXISTS employee_termination_requests (
    id TEXT PRIMARY KEY,
    employee_id TEXT NOT NULL REFERENCES user_profiles(id),
    odoo_employee_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    effective_date TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    reason TEXT NOT NULL,
    notes TEXT NOT NULL,
    requested_by_sub TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    last_error TEXT NULL,
    steps_completed JSON NOT NULL DEFAULT '[]'::json,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_employee_termination_employee UNIQUE (employee_id),
    CONSTRAINT uq_employee_termination_key UNIQUE (idempotency_key),
    CONSTRAINT ck_employee_termination_status
      CHECK (status IN ('PENDING','IN_PROGRESS','FAILED','COMPLETED'))
);
COMMIT;
