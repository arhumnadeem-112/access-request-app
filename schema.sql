-- Database schema for the System Access Request app.
-- db.py runs this file to create a fresh, empty database.

-- Start clean: drop the tables in reverse dependency order.
DROP TABLE IF EXISTS access_requests;
DROP TABLE IF EXISTS systems;
DROP TABLE IF EXISTS users;

-- Everyone who can log in.
-- manager_id points at another row in this same table. A request is routed to
-- the requester's manager for approval. The admin's manager_id is NULL.
CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    username      TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,          -- never the plain-text password
    role          TEXT    NOT NULL CHECK (role IN ('employee', 'manager', 'admin')),
    manager_id    INTEGER REFERENCES users(id)
);

-- The company systems people can request access to.
CREATE TABLE systems (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    description TEXT
);

-- One row per access request. decided_by_id, decision_comment and decided_at
-- stay NULL while the request is Pending.
-- Timestamps are ISO-8601 text in UTC, e.g. '2026-10-13 14:05:00'.
CREATE TABLE access_requests (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    requester_id     INTEGER NOT NULL REFERENCES users(id),
    system_id        INTEGER NOT NULL REFERENCES systems(id),
    reason           TEXT    NOT NULL,
    status           TEXT    NOT NULL DEFAULT 'Pending'
                             CHECK (status IN ('Pending', 'Approved', 'Rejected')),
    decided_by_id    INTEGER REFERENCES users(id),
    decision_comment TEXT,
    created_at       TEXT    NOT NULL,
    decided_at       TEXT,
    -- Database-level backstop for "nobody can approve their own request".
    CHECK (decided_by_id IS NULL OR decided_by_id <> requester_id)
);

-- Safety net for "no duplicate pending requests". This is a *partial* unique
-- index: it only covers rows WHERE status = 'Pending'. So a user can have many
-- old Approved/Rejected requests for a system, but only one Pending one.
CREATE UNIQUE INDEX one_pending_request_per_user_system
    ON access_requests (requester_id, system_id)
    WHERE status = 'Pending';
