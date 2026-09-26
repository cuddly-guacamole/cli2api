"""打印 cli2api 的管理员密钥（从 SQLite 的 app_secrets 表读，只读打开）。

用法: python get-key.py [db路径]
默认: 同目录下的 data/qoder.db
"""
import os
import sqlite3
import sys

db = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "qoder.db"
)
if not os.path.exists(db):
    sys.stderr.write("db not found: %s\n" % db)
    raise SystemExit(1)

con = sqlite3.connect("file:%s?mode=ro" % db.replace("\\", "/"), uri=True)
row = con.execute("select value from app_secrets where name='proxy_api_key'").fetchone()
con.close()
if not row:
    sys.stderr.write("proxy_api_key not found in app_secrets\n")
    raise SystemExit(1)
print(row[0])
