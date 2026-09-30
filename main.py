import asyncio, logging, os
from aiohttp import web
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup,
    InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
import db, api_client

# =========================
# 🔧 Environment Variables (Render में सेट कर)
# =========================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "PASTE_NEW_TOKEN_HERE")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "8747368604"))
SUPPORT_USERNAME = os.environ.get("SUPPORT_USERNAME", "@REDEYESIR")

# Render का URL — deploy के बाद यह मिलेगा
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://your-app.onrender.com")
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{RENDER_URL}{WEBHOOK_PATH}"

# 🔐 Private Channels
FORCE_CHANNELS = [
    {
        "name": "Channel 1",
        "invite": "https://t.me/+MbS4bity8z43Y2Y1",
        "id": -1003996290552
    },
    {
        "name": "Channel 2",
        "invite": "https://t.me/+zhfbEVmdMrI3MjM1",
        "id": -1003083624607
    },
]
# =========================

router = Router()
state = {}

def admin(uid):
    return uid == ADMIN_ID

def menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🛒 Buy Services"), KeyboardButton(text="💰 My Balance")],
        [KeyboardButton(text="📦 My Orders"), KeyboardButton(text="➕ Add Funds")],
        [KeyboardButton(text="📞 Support")]
    ], resize_keyboard=True)


async def blocked(m):
    u = await db.user(m.from_user.id)
    return bool(u and u[4])


# =========================
# FORCE JOIN SYSTEM
# =========================
async def is_joined(bot: Bot, user_id: int):
    not_joined = []
    for ch in FORCE_CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=ch["id"], user_id=user_id)
            if member.status in ["left", "kicked", "restricted"]:
                not_joined.append(ch)
        except Exception as e:
            logging.error(f"Force join check failed {ch['name']}: {e}")
            not_joined.append(ch)
    return (len(not_joined) == 0, not_joined)


def force_join_keyboard():
    buttons = []
    for ch in FORCE_CHANNELS:
        buttons.append([InlineKeyboardButton(text=f"📢 Join {ch['name']}", url=ch["invite"])])
    buttons.append([InlineKeyboardButton(text="✅ Verify", callback_data="verify_join")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(CommandStart())
async def start(m: Message):
    await db.add_user(m.from_user)
    if await blocked(m):
        return await m.answer("🚫 You are banned.")

    joined, not_joined = await is_joined(m.bot, m.from_user.id)
    if not joined:
        ch_text = "\n".join([f"• {ch['name']}" for ch in not_joined])
        return await m.answer(
            f"🔥 <b>WELCOME TO SMM BOT</b> 🔥\n\n"
            f"Bot use karne ke liye pehle in channels ko join karo:\n\n"
            f"{ch_text}\n\n"
            f"Join karne ke baad ✅ <b>Verify</b> button dabao.",
            reply_markup=force_join_keyboard()
        )

    await m.answer(
        "🔥 <b>WELCOME TO SMM BOT</b> 🔥\n\n"
        "🚀 Choose a platform, select a service and place your order.",
        reply_markup=menu()
    )


@router.callback_query(F.data == "verify_join")
async def verify_join(c: CallbackQuery):
    joined, not_joined = await is_joined(c.bot, c.from_user.id)
    if joined:
        await c.message.delete()
        await c.message.answer(
            "✅ <b>Verification successful!</b>\n\n"
            "🔥 <b>WELCOME TO SMM BOT</b> 🔥\n\n"
            "🚀 Choose a platform, select a service and place your order.",
            reply_markup=menu()
        )
    else:
        await c.answer("❌ Pehle saare channels join karo!", show_alert=True)


# =========================
# USER MENU
# =========================
@router.message(F.text == "💰 My Balance")
async def balance(m: Message):
    u = await db.user(m.from_user.id)
    await m.answer(f"💰 <b>MY BALANCE</b>\n\nAvailable: ₹{u[3]:.2f}")


@router.message(F.text == "🛒 Buy Services")
async def buy(m: Message):
    ps = await db.platforms()
    if not ps:
        return await m.answer("⚠️ No services available. Admin must sync services.")
    await m.answer("📱 <b>Select Platform</b>", reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=p, callback_data=f"p:{p}")] for p in ps]
    ))


@router.callback_query(F.data.startswith("p:"))
async def platform(c: CallbackQuery):
    p = c.data[2:]
    rows = await db.services(p)
    gp = float(await db.setting("profit_percent"))
    kb = []
    for sid, name, rate, profit in rows:
        pct = gp if profit < 0 else profit
        kb.append([InlineKeyboardButton(
            text=f"{name} — ₹{rate * (1 + pct / 100):.2f}",
            callback_data=f"s:{sid}"
        )])
    await c.message.edit_text(f"📱 <b>{p} Services</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await c.answer()


@router.callback_query(F.data.startswith("s:"))
async def choose(c: CallbackQuery):
    state[c.from_user.id] = {"sid": c.data[2:], "step": "link"}
    await c.message.answer("🔗 Send target link/username.")
    await c.answer()


@router.message(F.text == "📦 My Orders")
async def myorders(m: Message):
    rows = await db.orders(m.from_user.id)
    if not rows:
        return await m.answer("📦 No orders yet.")
    t = "📦 <b>MY ORDERS</b>\n\n"
    for x in rows:
        t += f"#{x[0]} | {x[1]}\nQty: {x[2]} | ₹{x[3]:.2f}\nStatus: {x[4]}\n\n"
    await m.answer(t)


@router.message(F.text == "➕ Add Funds")
async def funds(m: Message):
    state[m.from_user.id] = {"step": "amount"}
    await m.answer(f"💳 Enter amount (minimum ₹{await db.setting('min_deposit')}).")


@router.message(F.text == "📞 Support")
async def support(m: Message):
    state[m.from_user.id] = {"step": "support"}
    await m.answer(f"📞 Write your problem. It will be sent to support ({SUPPORT_USERNAME}).")


# =========================
# ADMIN PANEL
# =========================
@router.message(Command("admin"))
async def panel(m: Message):
    if not admin(m.from_user.id):
        return
    await m.answer(
        "👑 <b>ADMIN PANEL</b>\n\n"
        "/addbalance USER_ID AMOUNT\n/deductbalance USER_ID AMOUNT\n"
        "/ban USER_ID\n/unban USER_ID\n/approvepay PAYMENT_ID\n"
        "/setprofit PERCENT\n/setupi UPI\n/setowner NAME\n"
        "/setapiurl URL\n/setapikey KEY\n/setminamount AMOUNT\n/syncservices"
    )


@router.message(Command("addbalance"))
async def addbal(m: Message):
    if not admin(m.from_user.id): return
    try:
        _, uid, amt = m.text.split(maxsplit=2)
        uid = int(uid); amt = float(amt)
        await db.credit(uid, amt, "Admin balance add")
        await m.answer(f"✅ ₹{amt:.2f} added.")
        await m.bot.send_message(uid, f"💰 ₹{amt:.2f} added to your balance.")
    except:
        await m.answer("Usage: /addbalance USER_ID AMOUNT")


@router.message(Command("deductbalance"))
async def deduct(m: Message):
    if not admin(m.from_user.id): return
    try:
        _, uid, amt = m.text.split(maxsplit=2)
        uid = int(uid); amt = float(amt)
        u = await db.user(uid)
        if not u or u[3] < amt:
            return await m.answer("❌ Insufficient balance.")
        await db.credit(uid, -amt, "Admin deduction")
        await m.answer("✅ Deducted.")
    except:
        await m.answer("Usage: /deductbalance USER_ID AMOUNT")


@router.message(Command("ban"))
async def ban(m: Message):
    if admin(m.from_user.id):
        try:
            uid = int(m.text.split()[1]); await db.set_ban(uid, True); await m.answer("🚫 Banned.")
        except: await m.answer("Usage: /ban USER_ID")


@router.message(Command("unban"))
async def unban(m: Message):
    if admin(m.from_user.id):
        try:
            uid = int(m.text.split()[1]); await db.set_ban(uid, False); await m.answer("✅ Unbanned.")
        except: await m.answer("Usage: /unban USER_ID")


@router.message(Command("setprofit"))
async def profit(m: Message):
    if admin(m.from_user.id):
        try:
            await db.set_setting("profit_percent", float(m.text.split()[1])); await m.answer("✅ Profit updated.")
        except: await m.answer("Usage: /setprofit 25")


@router.message(Command("setminamount"))
async def setmin(m: Message):
    if admin(m.from_user.id):
        try:
            await db.set_setting("min_deposit", float(m.text.split()[1])); await m.answer("✅ Min updated.")
        except: await m.answer("Usage: /setminamount 50")


@router.message(Command("setupi"))
async def setupi(m: Message):
    if admin(m.from_user.id):
        await db.set_setting("upi_id", m.text.partition(" ")[2]); await m.answer("✅ UPI updated.")


@router.message(Command("setowner"))
async def setowner(m: Message):
    if admin(m.from_user.id):
        await db.set_setting("owner_name", m.text.partition(" ")[2]); await m.answer("✅ Owner updated.")


@router.message(Command("setapiurl"))
async def setapiurl(m: Message):
    if admin(m.from_user.id):
        await db.set_setting("api_url", m.text.partition(" ")[2]); await m.answer("✅ API URL updated.")


@router.message(Command("setapikey"))
async def setapikey(m: Message):
    if admin(m.from_user.id):
        await db.set_setting("api_key", m.text.partition(" ")[2]); await m.answer("✅ API Key updated.")


@router.message(Command("syncservices"))
async def sync(m: Message):
    if not admin(m.from_user.id): return
    try:
        data = await api_client.fetch_services(await db.setting("api_url"), await db.setting("api_key"))
        count = 0
        for s in data:
            sid = str(s.get("service")); name = str(s.get("name", "Service"))
            cat = str(s.get("category", "Other")); rate = float(s.get("rate", 0))
            await db.execute(
                "INSERT INTO services(service_id,platform,name,rate) VALUES(?,?,?,?) "
                "ON CONFLICT(service_id) DO UPDATE SET platform=excluded.platform,name=excluded.name,rate=excluded.rate",
                (sid, cat, name, rate)
            )
            count += 1
        await m.answer(f"✅ Synced {count} services.")
    except Exception as e:
        await m.answer(f"❌ Sync failed: {e}")


@router.message(Command("approvepay"))
async def approve(m: Message):
    if not admin(m.from_user.id): return
    try:
        pid = int(m.text.split()[1])
        r = await db.qone("SELECT user_id,amount,status FROM payments WHERE id=?", (pid,))
        if not r or r[2] != "pending":
            return await m.answer("❌ Already processed/not found.")
        await db.execute("UPDATE payments SET status='approved' WHERE id=?", (pid,))
        await db.credit(r[0], r[1], "Manual payment approved")
        await m.bot.send_message(r[0], f"✅ Payment approved. ₹{r[1]:.2f} credited.")
        await m.answer("✅ Approved.")
    except:
        await m.answer("Usage: /approvepay PAYMENT_ID")


# =========================
# MAIN FLOW
# =========================
@router.message()
async def flow(m: Message):
    if await blocked(m):
        return await m.answer("🚫 You are banned.")

    joined, not_joined = await is_joined(m.bot, m.from_user.id)
    if not joined:
        ch_text = "\n".join([f"• {ch['name']}" for ch in not_joined])
        return await m.answer(
            f"⚠️ Pehle in channels ko join karo:\n\n{ch_text}\n\nPhir ✅ Verify dabao.",
            reply_markup=force_join_keyboard()
        )

    s = state.get(m.from_user.id)
    if not s:
        return
    step = s["step"]

    if step == "support":
        await m.bot.send_message(ADMIN_ID,
            f"📩 SUPPORT\nUser: {m.from_user.full_name}\nID: {m.from_user.id}\n\n{m.text or '[media]'}")
        await m.answer("✅ Sent to support.")
        state.pop(m.from_user.id, None)

    elif step == "amount":
        try:
            amount = float(m.text); minimum = float(await db.setting("min_deposit"))
        except:
            return await m.answer("Enter a valid amount.")
        if amount < minimum:
            return await m.answer(f"Minimum is ₹{minimum:.2f}")
        s.update(step="utr", amount=amount)
        upi = await db.setting("upi_id"); owner = await db.setting("owner_name")
        await m.answer(f"💳 Pay ₹{amount:.2f}\nUPI: <code>{upi}</code>\nOwner: {owner}")
        await m.answer("After payment send UTR/transaction ID.")

    elif step == "utr":
        try:
            pid = await db.execute("INSERT INTO payments(user_id,amount,utr) VALUES(?,?,?)",
                (m.from_user.id, s["amount"], m.text.strip()))
            await m.bot.send_message(ADMIN_ID,
                f"💳 Payment #{pid}\nUser ID: {m.from_user.id}\nAmount: ₹{s['amount']:.2f}\n"
                f"UTR: {m.text.strip()}\nApprove: /approvepay {pid}")
            await m.answer("⏳ Payment sent for manual approval.")
            state.pop(m.from_user.id, None)
        except:
            await m.answer("❌ Duplicate/invalid UTR.")

    elif step == "link":
        s.update(link=m.text.strip(), step="quantity")
        await m.answer("🔢 Send quantity.")

    elif step == "quantity":
        try:
            q = int(m.text)
        except:
            return await m.answer("Enter a valid integer quantity.")
        svc = await db.service(s["sid"])
        if not svc:
            return await m.answer("Service unavailable.")
        pct = float(await db.setting("profit_percent")) if svc[4] < 0 else svc[4]
        cost = svc[3] * (1 + pct / 100) * q / 1000
        u = await db.user(m.from_user.id)
        if u[3] < cost:
            return await m.answer(f"❌ Insufficient balance. Need ₹{cost:.2f}")
        await db.credit(m.from_user.id, -cost, "Order debit")
        oid = await db.execute(
            "INSERT INTO orders(user_id,platform,service_id,service_name,link,quantity,cost,status) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (m.from_user.id, svc[1], svc[0], svc[2], s["link"], q, cost, "Pending API")
        )
        try:
            result = await api_client.create_order(
                await db.setting("api_url"), await db.setting("api_key"),
                svc[0], s["link"], q)
            api_id = str(result.get("order", ""))
            if not api_id:
                raise ValueError(str(result))
            await db.execute("UPDATE orders SET api_order_id=?,status='Pending' WHERE id=?", (api_id, oid))
            await m.answer(f"✅ Order #{oid} placed. Cost ₹{cost:.2f}")
        except Exception as e:
            await db.execute("UPDATE orders SET status='Cancelled',refunded=1,refund_amount=? WHERE id=?",
                (cost, oid))
            await db.credit(m.from_user.id, cost, "Automatic refund: API order failed")
            await m.answer(f"❌ Order failed. ₹{cost:.2f} refunded.")
        state.pop(m.from_user.id, None)


# =========================
# WEB SERVER + BOT START
# =========================
async def on_startup(bot: Bot):
    await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)
    print(f"✅ Webhook set: {WEBHOOK_URL}")


async def on_shutdown(bot: Bot):
    await bot.delete_webhook()
    print("❌ Webhook removed")


async def main():
    await db.init_db()

    bot = Bot(BOT_TOKEN, parse_mode="HTML")
    dp = Dispatcher()
    dp.include_router(router)

    # Health check route (Render के लिए)
    async def health(request):
        return web.Response(text="Bot is alive ✅")

    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)

    # Webhook handler
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"✅ Server running on port {port}")
    await asyncio.Event().wait()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
