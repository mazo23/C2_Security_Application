-- Drop the existing tables if they exist
DROP TABLE IF EXISTS devices;
DROP TABLE IF EXISTS logs;

-- Create the 'devices' table
CREATE TABLE devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    os_name TEXT NOT NULL,
    os_version TEXT NOT NULL,
    installed_apps TEXT,  -- Column for storing installed apps (as a comma-separated string)
    last_seen TEXT NOT NULL,
    watchlist INTEGER NOT NULL DEFAULT 0,
    online_timestamp TEXT NOT NULL
);

-- Create the 'logs' table
CREATE TABLE logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    action TEXT NOT NULL,
    details TEXT
);

-- Optional: Create some initial records in logs
INSERT INTO logs (timestamp, action, details) VALUES
('2024-10-01 10:00:00', 'Log Initialized', 'System logging started.');
