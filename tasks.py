import logging
import os
import imaplib
import email
from email.header import decode_header
from openai import OpenAI
import re
import shlex
from celery import Celery

API_KEY = os.getenv("API_KEY")
API_BASE = os.getenv("API_BASE")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o")

DEFAULT_PROMPT = (
    "Classify this email into EXACTLY ONE of these categories: {categories}. "
    "If it isn't a solid fit, respond with 'Uncategorized'. Return ONLY the category name.\n\n"
    "From: {sender}\n"
    "Subject: {subject}\n\n"
    "Body: {body}"
)
LLM_PROMPT_TEMPLATE = os.getenv("LLM_PROMPT_TEMPLATE", DEFAULT_PROMPT)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
app = Celery('email_tasks', broker=REDIS_URL)
app.conf.worker_prefetch_multiplier = 1
app.conf.task_acks_late = True

client = OpenAI(
    api_key=API_KEY,
    base_url=API_BASE
)
@app.task(bind=True, max_retries=3)
def process_email_task(self, account_config, email_msg_id):
    """
    The actual work: Classify and Move.
    """
    server = account_config['server']
    user = account_config['user']
    password = account_config['password']
    consume_folder = account_config['consume_folder']
    processed_folder = account_config['processed_folder']
    if not str(email_msg_id).isdigit():
        logging.error(f"Aborting task: Received invalid non-numeric UID '{email_msg_id}'")
        return
    try:
        mail = imaplib.IMAP4_SSL(server)
        mail.login(user, password)
        mail.select(consume_folder)
        status, data = mail.uid('FETCH', email_msg_id, "(RFC822)")
        if status != 'OK':
            raise Exception(f"Failed to fetch email from {consume_folder}")
        if data and len(data) > 0 and data[0] is not None:
            raw_email = data[0][1]
        else:
            logging.error(f"Failed to fetch email data for UID {email_msg_id}. Response was: {data}")
            raise Exception(f"IMAP fetch returned no data for UID {email_msg_id}")
        msg = email.message_from_bytes(raw_email)
        subject = decode_header(msg["Subject"])[0][0]
        sender_raw = msg.get("From", "(Unknown Sender)")
        sender_parts = decode_header(sender_raw)
        sender = ""
        for part, encoding in sender_parts:
            if isinstance(part, bytes):
                sender += part.decode(encoding or 'utf-8', errors='ignore')
            else:
                sender += part
        logging.info(f"Got sender: {sender}")

        if isinstance(subject, bytes):
            subject = subject.decode(errors='ignore')
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True).decode(errors='ignore')
                    break
        else:
            body = msg.get_payload(decode=True).decode(errors='ignore')
        mail.select(processed_folder)
        status, folders = mail.list()
        if status != 'OK':
            raise Exception(f"Could not access {processed_folder}")
        category_to_full_path = {}
        for folder in folders:
            folder_str = folder.decode().strip()
            logging.debug(f"Raw IMAP folder string: {folder_str}")
            try:
                parts = shlex.split(folder_str)
                if not parts:
                    continue
                actual_path = parts[-1]
                logging.debug(f"Isolated path: '{actual_path}'")
                if '.' in actual_path:
                    path_parts = actual_path.split('.')
                    if path_parts[0] == processed_folder:
                        category_name = '.'.join(path_parts[1:])
                        logging.debug(f"Extracted category_name: '{category_name}'")
                        if category_name:
                            category_to_full_path[category_name] = actual_path
                            logging.debug(f"Successfully mapped '{category_name}' -> '{actual_path}'")
                        else:
                            logging.debug(f"Skipping '{actual_path}' (empty category)")
                    else:
                        logging.debug(f"Skipping '{actual_path}' (does not start with {processed_folder})")
                else:
                    logging.debug(f"Skipping '{actual_path}' (no '.' found)")
            except Exception as e:
                logging.debug(f"Error parsing folder string '{folder_str}': {e}")
        discovered_categories = list(category_to_full_path.keys())
        if 'Uncategorized' not in discovered_categories:
            discovered_categories.append('Uncategorized')
        if not discovered_categories:
            raise Exception(f"No valid categories found in {processed_folder}.")
        try:
            prompt = LLM_PROMPT_TEMPLATE.format(
                categories=', '.join(discovered_categories),
                sender=sender,
                subject=subject,
                body=body[:1500]
            )
        except KeyError as e:
            logging.error(f"LLM_PROMPT_TEMPLATE KeyError: Missing {e}. Using hardcoded default.")
            prompt = DEFAULT_PROMPT.format(
                categories=', '.join(discovered_categories),
                sender=sender,
                subject=subject,
                body=body[:1500]
            )
        logging.debug(f"LLM Prompt: {prompt}")
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        category = response.choices[0].message.content.strip()
        destination = category_to_full_path.get(category)
        if not destination and category == 'Uncategorized':
            uncat_path = f"{processed_folder}.Uncategorized"
            logging.debug(f"Uncategorized target path: {uncat_path}")
            status, _ = mail.select(uncat_path)
            if status != 'OK':
                logging.debug(f"Creating Uncategorized folder: {uncat_path}")
                create_status, _ = mail.create(uncat_path)
                if create_status == 'OK':
                    destination = uncat_path
                    if ' ' in destination and not destination.startswith('"'):
                        destination = f'"{destination}"'
                else:
                    logging.error(f"Failed to create Uncategorized folder: {uncat_path}")
            else:
                destination = uncat_path
                if ' ' in destination and not destination.startswith('"'):
                    destination = f'"{destination}"'
        if destination:
            if ' ' in destination and not destination.startswith('"'):
                destination = f'"{destination}"'
            logging.debug(f"Attempting to move email to destination: {destination}")
            mail.select(consume_folder)
            status, _ = mail.select(destination)
            if status == 'OK':
                mail.select(consume_folder)
                copy_status, _ = mail.uid('COPY', email_msg_id, destination)
                if copy_status == 'OK':
                    mail.uid('STORE', email_msg_id, '+FLAGS', '\Deleted')
                    logging.info(f"SUCCESS: {user} | {subject},{sender} -> {category}")
                else:
                    raise Exception(f"IMAP Copy failed for {destination}")
            else:
                raise Exception(f"Destination folder '{destination}' does not exist or is inaccessible.")
        else:
            logging.info(f"SKIPPED: {user} | {subject} (Category: {category})")
        mail.expunge()
        mail.logout()
    except Exception as exc:
        logging.error(f"Task failed for {user}. Details: {exc}")
        raise self.retry(exc=exc, countdown=60)
