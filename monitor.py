import os
import time
import logging
import json
import asyncio
import threading
import re
from db_manager import get_all_accounts, get_account_update
from tasks import process_email_task
from imapclient import IMAPClient
import aioimaplib

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
DEBUG_MODE = os.getenv("DEBUG", "").lower() in ("true", "1", "yes")
logging.basicConfig(
    level=logging.DEBUG if DEBUG_MODE else logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class AccountDeletedError(Exception):
    pass

class AsyncMonitor:
    def __init__(self, acc, seen_emails, wake_event):
        self.acc = acc
        self.seen_emails = seen_emails
        self.wake_event = wake_event
        self.mail = None

    async def run(self):
        """Main loop for a single account using IDLE."""
        while True:
            try:
                self.mail = aioimaplib.IMAP4_SSL(self.acc['server'])
                await self.mail.wait_hello_from_server()
                await self.mail.login(self.acc['user'], self.acc['password'])
                await self.mail.select(self.acc['consume_folder'])
                await self.check_and_dispatch()
                while True:
                    await self.mail.idle_start()
                    try:
                        await asyncio.wait_for(self.mail.wait_server_push(), timeout=1500)
                    finally:
                        self.mail.idle_done()
                    await self.check_and_dispatch()
            except AccountDeletedError:
                logging.info(f"Monitor for {self.acc['user']} stopped (account deleted from DB)")
                return
            except Exception as e:
                logging.error(f"Connection failed for {self.acc['user']}: {e}. Retrying in 30s...")
                await asyncio.sleep(30)
            finally:
                if self.mail:
                    try:
                        await self.mail.logout()
                    except:
                        pass

    async def check_and_dispatch(self):
        """Checks for ANY emails in the folder and dispatches if not seen."""
        status, data = await self.mail.search(None, 'ALL')
        if status == 'OK':
            seq_nums = data[0].split()
            for seq_num in seq_nums:
                fetch_status, fetch_data = await self.mail.fetch(seq_num.decode(), '(UID)')
                if fetch_status == 'OK' and fetch_data:
                    raw_response = fetch_data[0].decode()
                    match = re.search(r'UID\s+(\d+)', raw_response)
                    if match:
                        uid_str = match.group(1)
                        unique_key = f"{self.acc['user']}_{uid_str}"
                        if unique_key not in self.seen_emails:
                            logging.info(f"New email detected for {self.acc['user']}: {uid_str}")
                            fresh = get_account_update(self.acc['uuid'])
                            if fresh is None:
                                logging.warning(f"DELETED: account {self.acc['uuid']} user={self.acc['user']} no longer in DB, stopping monitor")
                                self.wake_event.set()
                                raise AccountDeletedError()
                            self.acc.update(fresh)
                            if not self.acc.get('is_active'):
                                logging.debug(f"INACTIVE: dropping email uid={uid_str} for {self.acc['user']}")
                                continue
                            logging.debug(f"DISPATCH: account uuid={self.acc['uuid']} user={self.acc['user']} allow_parent={self.acc['allow_parent']!r} type={type(self.acc['allow_parent']).__name__}")
                            task_payload = {
                                "server": self.acc['server'], "user": self.acc['user'], "password": self.acc['password'],
                                "consume_folder": self.acc['consume_folder'], "processed_folder": self.acc['processed_folder'],
                                "prompt": self.acc['prompt'],
                                "allow_parent": self.acc['allow_parent']
                            }
                            logging.debug(f"PAYLOAD: allow_parent={task_payload['allow_parent']!r}")
                            clean_uid = "".join(filter(str.isdigit, uid_str))
                            if clean_uid:
                                process_email_task.delay(task_payload, uid_str)
                            else:
                                logging.error(f"Dropped invalid message ID: {m_id}")
                            self.seen_emails.add(unique_key)
                    else:
                        logging.error(f"Could not parse UID from FETCH response: {raw_response}")
                else:
                    logging.error(f"FETCH UID failed for seq {seq_num.decode()}: {fetch_status}")
        else:
            logging.error(f"SEARCH failed for {self.acc['user']}. Status: {status}")

async def async_monitor_manager():
    """Manages the lifecycle of multiple AsyncMonitor tasks."""
    seen_emails = set()
    monitored_tasks = {}  # account_uuid -> task
    wake_event = asyncio.Event()
    while True:
        accounts = get_all_accounts()
        current_uuids = {acc['uuid'] for acc in accounts}

        for uuid_ in list(monitored_tasks.keys()):
            if monitored_tasks[uuid_].done() or uuid_ not in current_uuids:
                monitored_tasks[uuid_].cancel()
                del monitored_tasks[uuid_]

        for acc in accounts:
            if acc['uuid'] not in monitored_tasks:
                logging.info(f"Starting new monitor for account {acc['uuid']} user={acc['user']}")
                monitor = AsyncMonitor(acc, seen_emails, wake_event)
                monitored_tasks[acc['uuid']] = asyncio.create_task(monitor.run())

        wake_event.clear()
        try:
            await asyncio.wait_for(wake_event.wait(), timeout=15)
            logging.debug("WAKE: account deleted, re-polling immediately")
        except asyncio.TimeoutError:
            pass

if __name__ == "__main__":
    try:
        logging.info("Starting Async Monitor (aioimaplib)...")
        asyncio.run(async_monitor_manager())
    except KeyboardInterrupt:
        logging.info("Monitor stopped by user.")
