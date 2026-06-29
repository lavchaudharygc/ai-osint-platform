CREATE TABLE IF NOT EXISTS user_database (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(100),
    phone VARCHAR(20),
    email VARCHAR(100),
    address TEXT,
    alternate_username VARCHAR(100),
    platform VARCHAR(50),
    data_source VARCHAR(100),
    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_username ON user_database(username);
CREATE INDEX IF NOT EXISTS idx_phone ON user_database(phone);
CREATE INDEX IF NOT EXISTS idx_email ON user_database(email);
