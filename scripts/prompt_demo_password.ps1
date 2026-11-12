$secure = Read-Host "Nhap mat khau benchmark moi (toi thieu 12 ky tu)" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)

try {
    $env:SEED_DEMO_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)

    @'
import os
import sys
import bcrypt
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "app"))
from controlled_rag import get_db_config
import psycopg2

password = os.environ["SEED_DEMO_PASSWORD"]
if len(password) < 12:
    raise SystemExit("ERROR: Mat khau phai co it nhat 12 ky tu.")

users = ("nv_dev", "mgr_tech", "mgr_sales", "partner_01", "ceo_boss")
password_hash = bcrypt.hashpw(
    password.encode("utf-8"), bcrypt.gensalt()
).decode("ascii")

conn = psycopg2.connect(**get_db_config())

try:
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT username FROM users WHERE username = ANY(%s) FOR UPDATE",
                (list(users),)
            )
            found = {row[0] for row in cur.fetchall()}
            missing = set(users) - found

            if missing:
                raise RuntimeError(
                    "Thieu tai khoan; rollback: " + ", ".join(sorted(missing))
                )

            cur.execute(
                "UPDATE users SET password_hash = %s WHERE username = ANY(%s)",
                (password_hash, list(users))
            )

            if cur.rowcount != len(users):
                raise RuntimeError(
                    f"So dong cap nhat khong dung: {cur.rowcount}; rollback."
                )

    print("PASS: Da cap nhat password_hash cho dung 5 tai khoan.")
    print("MFA secret, role va department khong bi thay doi.")
finally:
    conn.close()
'@ | python -

    if ($LASTEXITCODE -ne 0) {
        throw "Cap nhat that bai. Kiem tra loi Python phia tren."
    }
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    Remove-Item Env:SEED_DEMO_PASSWORD -ErrorAction SilentlyContinue
    $secure.Dispose()
}