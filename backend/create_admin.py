import sqlite3

conn = sqlite3.connect("proctoring.db")
cur = conn.cursor()

cur.execute("""
INSERT OR IGNORE INTO users(username,password,role)
VALUES ('admin','admin123','admin')
""")

conn.commit()
conn.close()

print("✅ Admin Created: admin / admin123")
