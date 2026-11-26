
import os
import sqlite3
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters
)

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DB = "smart_income.db"

AMOUNT, BKASH = range(2)

MENU = ReplyKeyboardMarkup(
    [
        ["💰 ব্যালেন্স", "👥 রেফারেল"],
        ["💸 টাকা তুলুন", "📞 সাহায্য"]
    ],
    resize_keyboard=True
)


def connect():
    return sqlite3.connect(DB)


def setup():
    with connect() as db:
        db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            uid INTEGER PRIMARY KEY,
            balance INTEGER DEFAULT 0,
            referred_by INTEGER DEFAULT 0
        )
        """)
        db.execute("""
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid INTEGER,
            amount INTEGER,
            bkash TEXT,
            status TEXT DEFAULT 'pending'
        )
        """)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id

    with connect() as db:
        exists = db.execute(
            "SELECT uid FROM users WHERE uid=?", (uid,)
        ).fetchone()

        if not exists:
            ref = 0
            if context.args:
                try:
                    ref = int(context.args[0])
                except ValueError:
                    pass

            if ref == uid:
                ref = 0

            valid_ref = db.execute(
                "SELECT uid FROM users WHERE uid=?", (ref,)
            ).fetchone() if ref else None

            if not valid_ref:
                ref = 0

            db.execute(
                "INSERT INTO users(uid,balance,referred_by) VALUES(?,?,?)",
                (uid, 5, ref)
            )

            if ref:
                db.execute(
                    "UPDATE users SET balance=balance+5 WHERE uid=?",
                    (ref,)
                )

    await update.message.reply_text(
        "স্বাগতম Smart Income Bot-এ! 🎉\n"
        "আপনার অ্যাকাউন্টে ৫ টাকা বোনাস যোগ হয়েছে।",
        reply_markup=MENU
    )


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    with connect() as db:
        row = db.execute(
            "SELECT balance FROM users WHERE uid=?", (uid,)
        ).fetchone()

    amount = row[0] if row else 0
    await update.message.reply_text(f"আপনার ব্যালেন্স: {amount} টাকা")


async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    bot = await context.bot.get_me()
    link = f"https://t.me/{bot.username}?start={uid}"

    with connect() as db:
        count = db.execute(
            "SELECT COUNT(*) FROM users WHERE referred_by=?", (uid,)
        ).fetchone()[0]

    await update.message.reply_text(
        f"আপনার রেফারেল লিংক:\n{link}\n\n"
        f"সদস্য সংখ্যা: {count}\n"
        "প্রতি বৈধ নতুন সদস্যে ৫ টাকা বোনাস।"
    )


async def withdraw_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "কত টাকা তুলতে চান? পরিমাণ লিখুন।\n"
        "সর্বনিম্ন ১০ টাকা।"
    )
    return AMOUNT


async def withdraw_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text)
    except ValueError:
        await update.message.reply_text("শুধু টাকার পরিমাণ সংখ্যায় লিখুন।")
        return AMOUNT

    if amount < 10:
        await update.message.reply_text("সর্বনিম্ন ১০ টাকা তুলতে পারবেন।")
        return AMOUNT

    uid = update.effective_user.id
    with connect() as db:
        row = db.execute(
            "SELECT balance FROM users WHERE uid=?", (uid,)
        ).fetchone()

    if not row or amount > row[0]:
        await update.message.reply_text("আপনার ব্যালেন্স যথেষ্ট নয়।")
        return ConversationHandler.END

    context.user_data["withdraw_amount"] = amount
    await update.message.reply_text("আপনার বিকাশ নম্বর লিখুন:")
    return BKASH


async def withdraw_bkash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    amount = context.user_data["withdraw_amount"]
    number = update.message.text.strip()

    if not number.isdigit() or len(number) < 11:
        await update.message.reply_text("সঠিক বিকাশ নম্বর লিখুন।")
        return BKASH

    with connect() as db:
        row = db.execute(
            "SELECT balance FROM users WHERE uid=?", (uid,)
        ).fetchone()

        if not row or row[0] < amount:
            await update.message.reply_text("আপনার ব্যালেন্স যথেষ্ট নয়।")
            return ConversationHandler.END

        db.execute(
            "UPDATE users SET balance=balance-? WHERE uid=?",
            (amount, uid)
        )
        cur = db.execute(
            "INSERT INTO withdrawals(uid,amount,bkash) VALUES(?,?,?)",
            (uid, amount, number)
        )
        wid = cur.lastrowid

    await update.message.reply_text(
        f"টাকা তোলার আবেদন গ্রহণ হয়েছে।\n"
        f"আবেদন নম্বর: {wid}\n"
        "অ্যাডমিন যাচাই করে বিকাশে টাকা পাঠাবেন।",
        reply_markup=MENU
    )

    if ADMIN_ID:
        await context.bot.send_message(
            ADMIN_ID,
            f"নতুন আবেদন #{wid}\n"
            f"User: {uid}\nপরিমাণ: {amount} টাকা\n"
            f"বিকাশ: {number}\n"
            f"অনুমোদন: /approve {wid}\n"
            f"বাতিল: /reject {wid}"
        )

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("আবেদন বাতিল হয়েছে।", reply_markup=MENU)
    return ConversationHandler.END


async def pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    with connect() as db:
        rows = db.execute(
            "SELECT id,uid,amount,bkash FROM withdrawals "
            "WHERE status='pending'"
        ).fetchall()

    if not rows:
        await update.message.reply_text("কোনো অপেক্ষমাণ আবেদন নেই।")
        return

    for wid, uid, amount, number in rows:
        await update.message.reply_text(
            f"আবেদন #{wid}\nUser: {uid}\n"
            f"টাকা: {amount}\nবিকাশ: {number}"
        )


async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    if not context.args:
        await update.message.reply_text("ব্যবহার: /approve আবেদন_নম্বর")
        return

    try:
        wid = int(context.args[0])
    except ValueError:
        return

    with connect() as db:
        row = db.execute(
            "SELECT uid FROM withdrawals WHERE id=? AND status='pending'",
            (wid,)
        ).fetchone()
        if not row:
            await update.message.reply_text("আবেদন পাওয়া যায়নি।")
            return
        db.execute(
            "UPDATE withdrawals SET status='approved' WHERE id=?", (wid,)
        )

    await context.bot.send_message(
        row[0], f"আপনার আবেদন #{wid} অনুমোদিত হয়েছে।"
    )
    await update.message.reply_text("আবেদন অনুমোদিত হয়েছে।")


async def reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    if not context.args:
        await update.message.reply_text("ব্যবহার: /reject আবেদন_নম্বর")
        return

    try:
        wid = int(context.args[0])
    except ValueError:
        return

    with connect() as db:
        row = db.execute(
            "SELECT uid,amount FROM withdrawals "
            "WHERE id=? AND status='pending'", (wid,)
        ).fetchone()

        if not row:
            await update.message.reply_text("আবেদন পাওয়া যায়নি।")
            return

        db.execute(
            "UPDATE withdrawals SET status='rejected' WHERE id=?", (wid,)
        )
        db.execute(
            "UPDATE users SET balance=balance+? WHERE uid=?",
            (row[1], row[0])
        )

    await context.bot.send_message(
        row[0], f"আপনার আবেদন #{wid} বাতিল হয়েছে। টাকা ব্যালেন্সে ফেরত দেওয়া হয়েছে।"
    )
    await update.message.reply_text("আবেদন বাতিল হয়েছে। টাকা ফেরত দেওয়া হয়েছে।")


async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("আপনার অনুমতি নেই।")
        return

    with connect() as db:
        users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    await update.message.reply_text(
        f"অ্যাডমিন প্যানেল\nমোট সদস্য: {users}\n"
        "/pending - অপেক্ষমাণ আবেদন\n"
        "/approve ID - অনুমোদন\n"
        "/reject ID - বাতিল"
    )


async def help_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "সাহায্যের জন্য বট অ্যাডমিনের সঙ্গে যোগাযোগ করুন।",
        reply_markup=MENU
    )


def main():
    if not TOKEN or not ADMIN_ID:
        raise RuntimeError("BOT_TOKEN এবং ADMIN_ID সেট করতে হবে।")

    setup()
    app = Application.builder().token(TOKEN).build()

    withdrawal = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^💸 টাকা তুলুন$"), withdraw_start)
        ],
        states={
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_amount)],
            BKASH: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_bkash)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CommandHandler("pending", pending))
    app.add_handler(CommandHandler("approve", approve))
    app.add_handler(CommandHandler("reject", reject))
    app.add_handler(withdrawal)
    app.add_handler(MessageHandler(filters.Regex("^💰 ব্যালেন্স$"), balance))
    app.add_handler(MessageHandler(filters.Regex("^👥 রেফারেল$"), referral))
    app.add_handler(MessageHandler(filters.Regex("^📞 সাহায্য$"), help_user))

    print("Smart Income Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
