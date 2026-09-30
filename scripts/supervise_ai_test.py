"""Windows-only isolated AI supervisor, never used by Odoo.sh or port 8070.

Create output/ai-preview.stop to stop supervision and its own worker.
Remove that file before starting again. Docker Desktop must be running.
"""
import logging
import msvcrt
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[1]
OUTPUT = REPO / 'output'
SERVER = Path('C:/Program Files/Odoo 19.0e.20260805/server')


def listening(port):
    with socket.socket() as probe:
        probe.settimeout(2)
        return probe.connect_ex(('127.0.0.1', port)) == 0


def main():
    OUTPUT.mkdir(exist_ok=True)
    with (OUTPUT / 'ai-supervisor.lock').open('a+b') as lock:
        lock.seek(0)
        if not lock.read(1):
            lock.write(b'0')
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return
        logging.basicConfig(filename=OUTPUT / 'ai-supervisor.log', level=logging.INFO,
                            format='%(asctime)s %(levelname)s %(message)s')
        logging.info('Supervisor started pid=%s', os.getpid())
        args = [sys.executable, str(SERVER / 'odoo-bin'), '-c', str(SERVER / 'odoo.conf'),
                '--addons-path=' + str(SERVER / 'odoo/addons') + ',' + str(REPO / 'custom_addons'),
                '--db_host=127.0.0.1', '--db_port=15432', '--db_user=ai_test',
                '--db_password=ai_local_isolated_test', '-d', 'b2b_ai_test_20260918',
                '--db-filter=^b2b_ai_test_20260918$', '--data-dir=' + str(OUTPUT / 'ai-data'),
                '--http-port=8072', '--http-interface=127.0.0.1', '--max-cron-threads=1',
                '--limit-time-real=300', '--logfile=' + str(OUTPUT / 'ai-preview.log')]
        stop = OUTPUT / 'ai-preview.stop'
        while not stop.exists():
            if listening(8072) or not listening(15432):
                # Never replace an unrelated port owner; wait for the database.
                time.sleep(5)
                continue
            with (OUTPUT / 'ai-preview-console.log').open('ab') as console:
                child = subprocess.Popen(args, cwd=REPO, stdin=subprocess.DEVNULL,
                                         stdout=console, stderr=console,
                                         creationflags=subprocess.CREATE_NO_WINDOW)
                logging.info('Worker started pid=%s', child.pid)
                try:
                    while child.poll() is None and not stop.exists():
                        time.sleep(2)
                finally:
                    if child.poll() is None:
                        child.terminate()
                        child.wait(timeout=30)
                logging.info('Worker exited code=%s', child.returncode)
            if not stop.exists():
                logging.info('Retrying in 10 seconds')
                time.sleep(10)
        logging.info('Supervisor stopped')


if __name__ == '__main__':
    main()
