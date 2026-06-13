import os
import sqlite3
import logging
import uuid

DB_PATH = "/data/accounts.db"

DEFAULT_PROMPT = (
    "Classify this email into EXACTLY ONE of these categories: {categories}. "
    "If it isn't a solid fit, respond with 'Uncategorized'. Return ONLY the category name.\n\n"
    "From: {sender}\n"
    "Subject: {subject}\n\n"
    "Body: {body}"
)

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(accounts)")
    cols = {row[1] for row in cursor.fetchall()}

    if 'id' in cols:
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.execute('''
            CREATE TABLE accounts_new (
                uuid TEXT PRIMARY KEY,
                server TEXT NOT NULL,
                user TEXT NOT NULL,
                password TEXT NOT NULL,
                consume_folder TEXT NOT NULL,
                processed_folder TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                prompt TEXT DEFAULT NULL,
                allow_parent INTEGER DEFAULT 1
            )
        ''')
        cursor.execute('''
            INSERT INTO accounts_new (uuid, server, user, password,
                consume_folder, processed_folder, is_active, prompt, allow_parent)
            SELECT lower(hex(randomblob(4)) || '-' || hex(randomblob(2)) || '-'
                || hex(randomblob(2)) || '-' || hex(randomblob(2)) || '-'
                || hex(randomblob(6))),
                server, user, password, consume_folder,
                processed_folder, is_active, prompt, allow_parent
            FROM accounts
        ''')
        cursor.execute("DROP TABLE accounts")
        cursor.execute("ALTER TABLE accounts_new RENAME TO accounts")
        cursor.execute("PRAGMA foreign_keys=ON")
    elif 'uuid' not in cols:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS accounts (
                uuid TEXT PRIMARY KEY,
                server TEXT NOT NULL,
                user TEXT NOT NULL,
                password TEXT NOT NULL,
                consume_folder TEXT NOT NULL,
                processed_folder TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                prompt TEXT DEFAULT NULL,
                allow_parent INTEGER DEFAULT 1
            )
        ''')

    conn.commit()
    conn.close()

def add_account(server, user, password, consume_folder, processed_folder, prompt=None, allow_parent=1):
    if not prompt:
        prompt = DEFAULT_PROMPT
    account_uuid = str(uuid.uuid4())
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO accounts (uuid, server, user, password,
            consume_folder, processed_folder, prompt, allow_parent)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (account_uuid, server, user, password,
          consume_folder, processed_folder, prompt, allow_parent))
    conn.commit()
    conn.close()
    return account_uuid

def get_account_update(account_uuid):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT prompt, allow_parent, is_active FROM accounts WHERE uuid = ?", (account_uuid,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_all_accounts():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM accounts")
    rows = cursor.fetchall()
    accounts = [dict(row) for row in rows]
    conn.close()
    return accounts

if __name__ == "__main__":
    init_db()
