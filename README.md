# Automated Email Classification System

An intelligent, distributed automation engine designed to transform high-volume, unorganized email inboxes into structured, categorized archives. By leveraging Large Language Models (LLMs), this system moves beyond fragile keyword-based filters to perform deep semantic classification.

## 🚀 Overview

Traditional email filtering relies on "if-this-then-that" rules that break as soon as a sender changes their subject line slightly. The **Email Classifier** solves this by using AI to "read" the email and decide where it belongs based on intent and context.

The system monitors a designated "Consume" folder via IMAP, analyzes the content using an OpenAI-compatible API, and moves the email to a specific subfolder within a "Processed" directory.

### Key Features
* **Semantic Intelligence:** Uses LLMs to distinguish between complex categories (e.g., "Urgent Invoices" vs. "General Receipts").
* **Dynamic Category Discovery:** No configuration needed for new categories. Simply create a new folder in your email client, and the system automatically learns it.
* **Distributed Architecture:** Built on a Producer-Consumer model using **Celery** and **Redis**, allowing it to scale to hundreds of accounts across multiple worker nodes.
* **Management Dashboard:** A Flask-based web interface to manage account credentials and monitor system health.
* **Per-Account Prompt Customization:** Override the global LLM prompt template per email subscription directly from the web UI.
* **Flexible Account Controls:** Enable or disable monitoring per account, and toggle whether parent folders are included as classification targets.

---

## 🏗 Architecture

The system follows a robust **Distributed Task Queue** pattern:

1.  **The Producer (Monitor):** A lightweight service that polls IMAP accounts. When a new email is detected, it dispatches a task to the broker.
2.  **The Broker (Redis):** The central nervous system that manages the queue of pending email processing tasks.
3.  **The Consumers (Workers):** A fleet of Celery workers that perform the heavy lifting: connecting to IMAP, extracting content, calling the LLM, and moving the files.
4.  **The Interface (Web UI):** A management layer to add/remove accounts and monitor worker status.

---

## 🛠 Technology Stack

* **Language:** Python 3.11+
* **Task Orchestration:** Celery
* **Message Broker:** Redis
* **Inference Engine:** OpenAI-compatible API (via `openai` library)
* **Database:** SQLite (for persistent account configuration)
* **Web Framework:** Flask
* **Deployment:** Docker & Docker Compose

---

## 🚦 Getting Started

### Prerequisites
* [Docker](https://docs.docker.com/get-docker/)
* [Docker Compose](https://docs.docker.com/compose/install/)

### 1. Email Account Preparation
Before running the system, you must prepare your email account structure. The system relies on two specific folders to manage the workflow:

1.  **The `Consume` Folder:** This is your "inbox" for the automation. All new emails you want the system to process should arrive here.
2.  **The `Processed` Folder:** This is the destination directory. **Crucially, this folder must contain subfolders that represent your desired categories.**
    *   *Example:* If you want emails categorized into "Invoices", "Newsletters", and "Personal", you must create those three folders inside your `Processed` folder.
    *   **Automatic Discovery:** You do **not** need to tell the software about these categories. The system automatically scans the `Processed` directory on every run. If you create a new folder named "Travel" inside `Processed`, the AI will immediately begin classifying emails into "Travel" without any code or config changes.

### 2. Configuration
Create a `.env` file in the root directory to store your sensitive credentials. **The system will refuse to start if the Admin credentials are not provided.**

```env
# Admin Web UI Credentials
ADMIN_USERNAME=your_admin_user
ADMIN_PASSWORD=your_secure_password

# LLM Configuration
API_KEY=sk-your-openai-key
API_BASE=https://api.openai.com/v1
MODEL_NAME=gpt-4o

# LLM Prompt Template (Optional - global default, overridable per account in the UI)
# Use {categories}, {sender}, {subject}, and {body} as placeholders.
LLM_PROMPT_TEMPLATE="Classify this email into EXACTLY ONE of these categories: {categories}. If it isn't a solid fit, respond with 'Uncategorized'. Return ONLY the category name.\n\nFrom: {sender}\nSubject: {subject}\n\nBody: {body}"

# Redis Configuration
REDIS_URL=redis://redis:6379/0
```

### 3. Deployment
Launch the entire stack with a single command:

```bash
docker-compose up -d
```

This will spin up the Redis broker, the Celery workers, the Monitor service, and the Flask Management UI.

### 4. Managing Accounts
1.  Access the Web UI at `http://localhost:5000`.
2.  Log in using your `ADMIN_USERNAME` and `ADMIN_PASSWORD`.
3.  Add your IMAP accounts with the following fields:

    - **Server, User, Password** — IMAP connection details.
    - **Consume / Processed Folder** — Source and destination folders.
    - **LLM Prompt** — A per-account prompt template override. Leave blank to use the global default.
    - **Include parent folders** — When enabled (default), parent folders are valid classification targets alongside their subfolders. Disable to restrict classification to only the deepest subfolders.

    Each account also has an **Active toggle** in the table — disable it to pause monitoring without deleting the account.

---

## 🔍 How it Works (The Workflow)

1.  **Detection:** The `monitor.py` service detects a new message in the `Consume` folder.
2.  **Task Dispatch:** A task is sent to Redis containing the account details and the Message UID.
3.  **Extraction:** A worker picks up the task, connects via SSL, and extracts the `Subject`, `From`, `Date`, and `Body`.
4.  **Classification:** The worker sends the metadata to the LLM with a prompt: *"Classify this email into exactly one of these categories: [List of subfolders found in Processed/]"*.
5.  **Movement:** The worker performs a `COPY` to the target folder and a `DELETE` from the source folder.

---

## ⚠️ Security & Best Practices

* **Non-Root Execution:** This system is designed to run as a non-privileged user within the Docker container to mitigate risks.
* **Environment Variables:** Never hardcode credentials in the source code. Always use the `.env` file.
* **IMAP Security:** Always use `use_ssl=True` and port `993` for all production accounts.

## 📄 License
GPL-3.0
