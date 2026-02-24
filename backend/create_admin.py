import database as db

db.init_db()
conn = db.connect("proctoring.db")
cur = conn.cursor()

if db.USE_SUPABASE:
    cur.execute(
        """
        INSERT INTO users(username,password,role)
        VALUES ('admin','admin123','admin')
        ON CONFLICT (username) DO NOTHING
        """
    )
else:
    cur.execute(
        """
        INSERT OR IGNORE INTO users(username,password,role)
        VALUES ('admin','admin123','admin')
        """
    )

conn.commit()
conn.close()

print("✅ Admin Created: admin / admin123")
