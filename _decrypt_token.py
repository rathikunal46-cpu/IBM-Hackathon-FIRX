import sqlite3, os, json, ctypes, ctypes.wintypes, base64

# ── Step 1: Decrypt the AES key from Local State ──────────────────────────────
local_state_path = os.path.expandvars('%APPDATA%') + r'\IBM Bob\Local State'
with open(local_state_path, encoding='utf-8') as f:
    local_state = json.load(f)

key_b64 = local_state['os_crypt']['encrypted_key']
encrypted_key = base64.b64decode(key_b64)
# Strip the "DPAPI" prefix (first 5 bytes)
encrypted_key = encrypted_key[5:]

class DATA_BLOB(ctypes.Structure):
    _fields_ = [('cbData', ctypes.wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_char))]

buf = ctypes.create_string_buffer(encrypted_key)
blob_in  = DATA_BLOB(len(encrypted_key), buf)
blob_out = DATA_BLOB()
ok = ctypes.windll.Crypt32.CryptUnprotectData(
    ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
)
if not ok:
    print('DPAPI key decrypt failed, error:', ctypes.GetLastError()); exit(1)

aes_key = ctypes.string_at(blob_out.pbData, blob_out.cbData)
ctypes.windll.Kernel32.LocalFree(blob_out.pbData)
print('AES key length:', len(aes_key), '(should be 32)')

# ── Step 2: Decrypt the token ─────────────────────────────────────────────────
db_path = os.path.expandvars('%APPDATA%') + r'\IBM Bob\User\globalStorage\state.vscdb'
conn = sqlite3.connect(db_path)
row = conn.execute(
    "SELECT value FROM ItemTable WHERE key LIKE '%bob.auth.tokens-https://api.us-east.bob.ibm.com%'"
).fetchone()
conn.close()

token_json = json.loads(row[0])
ciphertext = bytes(token_json['data'])
# v10 format: b'v10' + 12-byte nonce + ciphertext + 16-byte tag
nonce      = ciphertext[3:15]
ct_and_tag = ciphertext[15:]

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    aesgcm = AESGCM(aes_key)
    plaintext = aesgcm.decrypt(nonce, ct_and_tag, None)
    token_data = json.loads(plaintext.decode('utf-8'))
    print('\nDecrypted token data keys:', list(token_data.keys()) if isinstance(token_data, dict) else type(token_data))
    if isinstance(token_data, dict):
        for k, v in token_data.items():
            sv = str(v)[:120]
            print(f'  {k}: {sv}')
    elif isinstance(token_data, list):
        print('  List length:', len(token_data))
        for item in token_data[:2]:
            print('  Item keys:', list(item.keys()) if isinstance(item, dict) else str(item)[:120])
except ImportError:
    print('cryptography package not installed — installing...')
    import subprocess
    subprocess.run(['pip', 'install', 'cryptography'], check=True)
    print('Re-run this script after install.')
except Exception as e:
    import traceback; traceback.print_exc()
