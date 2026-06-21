import os
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import select
import json
import time
import sys

conn = psycopg2.connect(
    host=os.getenv('DB_HOST'),
    port=int(os.getenv('DB_PORT', 5432)),
    dbname=os.getenv('DB_NAME'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD')
)
conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
cur = conn.cursor()
cur.execute("LISTEN log_notify;")
print("Listening to channel 'log_notify'...", file=sys.stderr)

last_id = 0
while True:
    if select.select([conn], [], [], 10) == ([], [], []):
        # Timeout: polling fallback
        cur.execute(f"SELECT id, endpoint, method, status_code, response_time, timestamp FROM logs WHERE id > {last_id} ORDER BY id ASC")
        rows = cur.fetchall()
        if rows:
            for row in rows:
                record = dict(zip([desc[0] for desc in cur.description], row))
                print(json.dumps(record, default=str), flush=True)
                last_id = max(last_id, record['id'])
    else:
        conn.poll()
        while conn.notifies:
            notify = conn.notifies.pop(0)
            cur.execute(f"SELECT id, endpoint, method, status_code, response_time, timestamp FROM logs WHERE id > {last_id} ORDER BY id ASC")
            rows = cur.fetchall()
            for row in rows:
                record = dict(zip([desc[0] for desc in cur.description], row))
                print(json.dumps(record, default=str), flush=True)
                last_id = max(last_id, record['id'])
    time.sleep(1)