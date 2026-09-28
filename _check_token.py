import sqlite3, os, json

db = os.path.expandvars('%APPDATA%') + r'\IBM Bob\User\globalStorage\state.vscdb'
print('DB path:', db, 'exists:', os.path.exists(db))
conn = sqlite3.connect(db)
rows = conn.execute("SELECT key, value FROM ItemTable").fetchall()
for key, val in rows:
    k = key.lower()
    if any(x in k for x in ['secret','token','auth','bob','session']):
        print('\nKEY:', key)
        if isinstance(val, (bytes, bytearray)):
            print('  BYTES len:', len(val), 'hex prefix:', val[:16].hex())
        else:
            s = str(val) if val else ''
            print('  STR:', s[:200])
conn.close()
