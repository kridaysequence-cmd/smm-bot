import aiosqlite

DB_NAME = "smm_bot.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            balance REAL DEFAULT 0,
            banned INTEGER DEFAULT 0,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS services(
            service_id TEXT PRIMARY KEY,
            platform TEXT,
            name TEXT,
            rate REAL,
            profit REAL DEFAULT -1
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS orders(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            platform TEXT,
            service_id TEXT,
            service_name TEXT,
            link TEXT,
            quantity INTEGER,
            cost REAL,
            status TEXT,
            api_order_id TEXT,
            refunded INTEGER DEFAULT 0,
            refund_amount REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS payments(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            utr TEXT UNIQUE,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS settings(
            key TEXT PRIMARY KEY,
            value TEXT
        )""")
        await db.commit()

        defaults = {
            "profit_percent": "25",
            "min_deposit": "50",
            "upi_id": "yourupi@upi",
            "owner_name": "Your Name",
            "api_url": "",
            "api_key": "",
            "qr_file_id": ""
        }
        for k, v in defaults.items():
            await db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))
        await db.commit()


async def add_user(user):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users(user_id,username,full_name) VALUES(?,?,?)",
            (user.id, user.username or "", user.full_name or "")
        )
        await db.commit()


async def user(uid):
    async with aiosqlite.connect(DB_NAME) as db:
        cur = await db.execute(
            "SELECT user_id,username,full_name,balance,banned FROM users WHERE user_id=?",
            (uid,)
        )
        return await cur.fetchone()


async def credit(uid, amount, note=""):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, uid))
        await db.commit()


async def set_ban(uid, status):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET banned=? WHERE user_id=?", (1 if status else 0, uid))
        await db.commit()


async def platforms():
    async with aiosqlite.connect(DB_NAME) as db:
        cur = await db.execute("SELECT DISTINCT platform FROM services")
        rows = await cur.fetchall()
        return [r[0] for r in rows]


async def services(platform):
    async with aiosqlite.connect(DB_NAME) as db:
        cur = await db.execute(
            "SELECT service_id,name,rate,profit FROM services WHERE platform=?",
            (platform,)
        )
        return await cur.fetchall()


async def service(sid):
    async with aiosqlite.connect(DB_NAME) as db:
        cur = await db.execute(
            "SELECT service_id,platform,name,rate,profit FROM services WHERE service_id=?",
            (sid,)
        )
        return await cur.fetchone()


async def orders(uid):
    async with aiosqlite.connect(DB_NAME) as db:
        cur = await db.execute(
            "SELECT id,service_name,quantity,cost,status FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 20",
            (uid,)
        )
        return await cur.fetchall()


async def setting(key):
    async with aiosqlite.connect(DB_NAME) as db:
        cur = await db.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = await cur.fetchone()
        return row[0] if row else ""


async def set_setting(key, value):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value))
        )
        await db.commit()


async def execute(query, params=()):
    async with aiosqlite.connect(DB_NAME) as db:
        cur = await db.execute(query, params)
        await db.commit()
        return cur.lastrowid


async def qone(query, params=()):
    async with aiosqlite.connect(DB_NAME) as db:
        cur = await db.execute(query, params)
        return await cur.fetchone()
