import os
import sqlite3
import logging

DB_PATH = "/data/accounts.db"

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server TEXT NOT NULL,
            user TEXT NOT NULL,
            password TEXT NOT NULL,
            consume_folder TEXT NOT NULL,
            processed_folder TEXT NOT NULL,
            is_active INTEGER DEFAULT 1
        )
    ''')
    conn.commit()
    conn.close()

def add_account(server, user, password, consume_folder, processed_folder):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO accounts (server, user, password, consume_folder, processed_folder)
        VALUES (?, ?, ?, ?, ?)
    ''', (server, user, password, consume_folder, processed_folder))
    conn.commit()
    conn.close()

def get_active_accounts():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM accounts WHERE is_active = 1")
    rows = cursor.fetchall()
    accounts = [dict(row) for row in rows]
    conn.close()
    return accounts

if __name__ == "__main__":
    init_db()
    print("Database initialized at", DB_PATH)
