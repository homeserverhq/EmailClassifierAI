from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from db_manager import get_active_accounts, init_db, add_account
import sqlite3
import os

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "super-secret-key-for-session")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD_RAW = os.getenv("ADMIN_PASSWORD")
if not ADMIN_USERNAME or not ADMIN_PASSWORD_RAW:
    logging.critical("CRITICAL SECURITY ERROR: ADMIN_USERNAME or ADMIN_PASSWORD environment variables are not set!")
    logging.critical("The application will now exit to prevent running with insecure default credentials.")
    import sys
    sys.exit(1)
ADMIN_PASSWORD_HASH = generate_password_hash(ADMIN_PASSWORD_RAW)
DB_PATH = "/data/accounts.db"

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, password):
            session['logged_in'] = True
            return redirect(url_for('index'))
        flash('Invalid credentials', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/')
def index():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    conn = get_db_connection()
    accounts = conn.execute('SELECT * FROM accounts').fetchall()
    conn.close()
    return render_template('index.html', accounts=accounts)

@app.route('/add', methods=['POST'])
def add():
    if not session.get('logged_in'): return redirect(url_for('login'))
    add_account(
        request.form.get('server'),
        request.form.get('user'),
        request.form.get('password'),
        request.form.get('consume_folder'),
        request.form.get('processed_folder')
    )
    flash('Account added successfully!', 'success')
    return redirect(url_for('index'))

@app.route('/delete/<int:acc_id>', methods=['POST'])
def delete(acc_id):
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    conn.execute('DELETE FROM accounts WHERE id = ?', (acc_id,))
    conn.commit()
    conn.close()
    flash('Account removed.', 'success')
    return redirect(url_for('index'))

@app.route('/edit/<int:acc_id>', methods=['POST'])
def edit(acc_id):
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    conn.execute('''
        UPDATE accounts 
        SET server=?, user=?, password=?, consume_folder=?, processed_folder=?
        WHERE id=?
    ''', (
        request.form.get('server'),
        request.form.get('user'),
        request.form.get('password'),
        request.form.get('consume_folder'),
        request.form.get('processed_folder'),
        acc_id
    ))
    conn.commit()
    conn.close()
    flash('Account updated.', 'success')
    return redirect(url_for('index'))

if __name__ == '__main__':
    # Ensure the DB is initialized in the volume location
    init_db()
    app.run(host='0.0.0.0', port=5000)
