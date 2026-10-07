from flask import Flask
import threading
import os
import json
import time
import sqlite3
import re
import unicodedata
from difflib import SequenceMatcher
from urllib.request import Request, urlopen
from urllib.parse import urlencode


# =========================================================
# FLASK / KEEP ALIVE
# =========================================================

app = Flask(__name__)


@app.route("/")
def home():
    return "Bot is Alive!"


def run_server():
    app.run(host="0.0.0.0", port=10000, use_reloader=False)


threading.Thread(target=run_server, daemon=True).start()


# =========================================================
# SETTINGS
# =========================================================

TOKEN = os.environ.get("BOT_TOKEN", "").strip()

try:
    ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
except ValueError:
    ADMIN_ID = 0

BOT_USERNAME = os.environ.get("BOT_USERNAME", "your_bot").replace("@", "").strip()
ADMIN_CONTACT = os.environ.get("ADMIN_CONTACT", "@admin").strip()

COMMISSION_RATE = 9
REFERRAL_RATE = 4

API = f"https://api.telegram.org/bot{TOKEN}"
DB = "marketplace.db"

CATEGORIES = [
    "👕 ملابس",
    "🍳 أواني منزلية",
    "🔥 عروض وخصم",
    "⭐ رائج",
    "👗 موضة",
    "📦 أخرى",
    "🌾 أعلاف حيوانات",
    "💄 منتجات تجميل",
    "🌱 أسمدة زراعية",
    "💪 منتجات جيم",
]


# =========================================================
# DATABASE
# =========================================================

db = sqlite3.connect(DB, check_same_thread=False)
db.execute("PRAGMA journal_mode=WAL")
db.execute("PRAGMA busy_timeout=10000")


def db_commit():
    db.commit()


def init_db():
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY,
            state TEXT,
            temp TEXT,
            points INTEGER DEFAULT 0,
            purchases INTEGER DEFAULT 0,
            sales INTEGER DEFAULT 0,
            referred_by INTEGER,
            is_banned INTEGER DEFAULT 0,
            profit_active INTEGER DEFAULT 0,
            referral_earnings INTEGER DEFAULT 0,
            referral_balance INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS merchants(
            user_id INTEGER PRIMARY KEY,
            store_name TEXT,
            phone TEXT,
            city TEXT,
            doc_photo TEXT,
            status TEXT DEFAULT 'pending',
            reject_reason TEXT,
            commission_due INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS products(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            merchant_id INTEGER,
            name TEXT,
            price INTEGER,
            photo_id TEXT,
            description TEXT,
            category TEXT,
            status TEXT DEFAULT 'pending',
            reject_reason TEXT,
            base_price INTEGER DEFAULT 0,
            commission_fee INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS orders(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            buyer_id INTEGER,
            product_id INTEGER,
            merchant_id INTEGER,
            price INTEGER,
            commission INTEGER,
            referral_comm INTEGER DEFAULT 0,
            buyer_info TEXT,
            status TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS commission_payments(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            merchant_id INTEGER,
            amount INTEGER,
            receipt_photo TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT,
            reviewed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS referrals(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            referred_id INTEGER UNIQUE,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS referral_profits(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            buyer_id INTEGER,
            order_id INTEGER,
            amount INTEGER,
            created_at TEXT
        );
        """
    )

    # توافق مع قواعد البيانات القديمة
    columns = {
        "users": [
            ("profit_active", "INTEGER DEFAULT 0"),
            ("referral_earnings", "INTEGER DEFAULT 0"),
            ("referral_balance", "INTEGER DEFAULT 0"),
            ("is_banned", "INTEGER DEFAULT 0"),
        ],
        "merchants": [
            ("doc_photo", "TEXT"),
            ("reject_reason", "TEXT"),
            ("commission_due", "INTEGER DEFAULT 0"),
        ],
        "products": [
            ("reject_reason", "TEXT"),
            ("base_price", "INTEGER DEFAULT 0"),
            ("commission_fee", "INTEGER DEFAULT 0"),
        ],
        "orders": [
            ("price", "INTEGER"),
            ("commission", "INTEGER"),
            ("referral_comm", "INTEGER DEFAULT 0"),
            ("created_at", "TEXT"),
        ],
    }

    for table, cols in columns.items():
        existing = {
            row[1]
            for row in db.execute(f"PRAGMA table_info({table})").fetchall()
        }

        for column, definition in cols:
            if column not in existing:
                try:
                    db.execute(
                        f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
                    )
                except Exception:
                    pass

    db_commit()


init_db()


# =========================================================
# TELEGRAM API
# =========================================================

def api(method, data=None):
    if not TOKEN:
        print("ERROR: BOT_TOKEN غير موجود.")
        return {}

    if data is None:
        data = {}

    try:
        encoded = urlencode(data).encode("utf-8")
        request = Request(
            f"{API}/{method}",
            data=encoded,
            headers={
                "Content-Type": "application/x-www-form-urlencoded"
            },
        )

        with urlopen(request, timeout=40) as response:
            return json.loads(response.read().decode("utf-8"))

    except Exception as e:
        print(f"Telegram API error [{method}]: {e}")
        return {}


def send(chat_id, text, kb=None, photo=None, main_kb=False):
    if not chat_id:
        return {}

    if photo:
        data = {
            "chat_id": chat_id,
            "photo": photo,
            "caption": text[:1024],
        }

        if kb is not None:
            data["reply_markup"] = json.dumps(
                {"inline_keyboard": kb},
                ensure_ascii=False,
            )

        return api("sendPhoto", data)

    data = {
        "chat_id": chat_id,
        "text": text[:4096],
    }

    if kb is not None:
        data["reply_markup"] = json.dumps(
            {"inline_keyboard": kb},
            ensure_ascii=False,
        )

    elif main_kb:
        merchant = db.execute(
            "SELECT status FROM merchants WHERE user_id=?",
            (chat_id,),
        ).fetchone()

        keyboard = [
            ["🛍️ تسوق", "🔍 بحث عن منتج"],
        ]

        if merchant:
            button = (
                "🏪 لوحة متجري"
                if merchant[0] == "approved"
                else "🏪 حالة متجري"
            )
            keyboard.append([button])
        else:
            keyboard.append(
                ["🏪 إنشاء حساب تاجر", "💰 الربح من البوت"]
            )

        keyboard.append(["📊 حسابي", "☎️ خدمة العملاء"])

        if chat_id == ADMIN_ID and ADMIN_ID:
            keyboard.append(["👑 لوحة الأدمن"])

        data["reply_markup"] = json.dumps(
            {
                "keyboard": keyboard,
                "resize_keyboard": True,
            },
            ensure_ascii=False,
        )

    return api("sendMessage", data)


def edit(chat_id, message_id, text, kb=None):
    data = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text[:4096],
    }

    if kb is not None:
        data["reply_markup"] = json.dumps(
            {"inline_keyboard": kb},
            ensure_ascii=False,
        )

    result = api("editMessageText", data)

    if result.get("ok"):
        return result

    # إذا كانت الرسالة صورة، نحاول تعديل الـ caption
    data2 = {
        "chat_id": chat_id,
        "message_id": message_id,
        "caption": text[:1024],
    }

    if kb is not None:
        data2["reply_markup"] = json.dumps(
            {"inline_keyboard": kb},
            ensure_ascii=False,
        )

    return api("editMessageCaption", data2)


def answer(callback_id, text=""):
    return api(
        "answerCallbackQuery",
        {
            "callback_query_id": callback_id,
            "text": text[:200],
        },
    )


# =========================================================
# USER STATE
# =========================================================

def ensure_user(uid):
    db.execute(
        "INSERT OR IGNORE INTO users(user_id) VALUES(?)",
        (uid,),
    )
    db_commit()


def set_state(uid, state=None, temp=None):
    ensure_user(uid)

    if temp is not None:
        temp_json = json.dumps(
            temp,
            ensure_ascii=False,
        )
        db.execute(
            "UPDATE users SET state=?, temp=? WHERE user_id=?",
            (state, temp_json, uid),
        )
    else:
        db.execute(
            "UPDATE users SET state=? WHERE user_id=?",
            (state, uid),
        )

    db_commit()


def get_state(uid):
    row = db.execute(
        "SELECT state FROM users WHERE user_id=?",
        (uid,),
    ).fetchone()

    return row[0] if row else None


def get_temp(uid):
    row = db.execute(
        "SELECT temp FROM users WHERE user_id=?",
        (uid,),
    ).fetchone()

    if not row or not row[0]:
        return {}

    try:
        return json.loads(row[0])
    except Exception:
        return {}


# =========================================================
# KEYBOARDS
# =========================================================

def cat_kb(prefix):
    keyboard = []

    for i in range(0, len(CATEGORIES), 2):
        row = []

        row.append(
            {
                "text": CATEGORIES[i],
                "callback_data": f"{prefix}:{i}",
            }
        )

        if i + 1 < len(CATEGORIES):
            row.append(
                {
                    "text": CATEGORIES[i + 1],
                    "callback_data": f"{prefix}:{i + 1}",
                }
            )

        keyboard.append(row)

    return keyboard


def category_from_index(value):
    try:
        index = int(value)
        if 0 <= index < len(CATEGORIES):
            return CATEGORIES[index]
    except Exception:
        pass

    return "📦 أخرى"


# =========================================================
# SEARCH
# =========================================================

def normalize_search_text(value):
    value = unicodedata.normalize(
        "NFKC",
        str(value or ""),
    ).lower()

    value = re.sub(
        r"[\u064b-\u065f\u0670\u0640]",
        "",
        value,
    )

    value = value.translate(
        str.maketrans(
            {
                "أ": "ا",
                "إ": "ا",
                "آ": "ا",
                "ى": "ي",
                "ة": "ه",
                "ؤ": "و",
                "ئ": "ي",
            }
        )
    )

    return re.sub(
        r"[^\w\s]",
        " ",
        value,
    ).strip()


def word_score(query_word, words):
    best = 0

    for word in words:
        if query_word == word:
            return 1.0

        if len(query_word) >= 3 and (
            query_word in word or word in query_word
        ):
            best = max(best, 0.86)

        best = max(
            best,
            SequenceMatcher(
                None,
                query_word,
                word,
            ).ratio(),
        )

    return best


def do_search(chat_id, query):
    normalized = normalize_search_text(query)
    query_words = normalized.split()

    if not query_words:
        send(
            chat_id,
            "أرسل اسم المنتج للبحث.",
            main_kb=True,
        )
        return

    products = db.execute(
        """
        SELECT p.*
        FROM products p
        JOIN merchants m ON m.user_id=p.merchant_id
        WHERE p.status='approved'
        AND m.status='approved'
        ORDER BY p.id DESC
        """
    ).fetchall()

    results = []

    for product in products:
        title = normalize_search_text(product[2])
        description = normalize_search_text(product[5])
        category = normalize_search_text(product[6])

        combined = f"{title} {description} {category}"
        words = combined.split()

        if normalized in combined:
            score = 1.2
        else:
            scores = [
                word_score(q, words)
                for q in query_words
            ]

            matched = sum(
                s >= 0.60
                for s in scores
            )

            if matched / len(query_words) < 0.5:
                continue

            score = sum(scores) / len(scores)

            if any(q in title for q in query_words):
                score += 0.15

        results.append((score, product))

    results.sort(
        key=lambda x: (x[0], x[1][0]),
        reverse=True,
    )

    results = results[:10]

    if not results:
        send(
            chat_id,
            f"🔍 لا توجد نتائج عن: {query}\n\n"
            "جرّب كلمة أخرى.",
            main_kb=True,
        )
        return

    send(
        chat_id,
        f"🔍 نتائج البحث عن «{query}»",
        main_kb=True,
    )

    for _, product in results:
        store = db.execute(
            "SELECT store_name FROM merchants WHERE user_id=?",
            (product[1],),
        ).fetchone()

        store_name = store[0] if store else "متجر"

        kb = [
            [
                {
                    "text": f"🛒 شراء {product[3]}ج",
                    "callback_data": f"buy:{product[0]}",
                }
            ]
        ]

        text = (
            f"📦 {product[2]}\n"
            f"💰 {product[3]}ج عند الاستلام\n"
            f"📝 {product[5] or 'لا يوجد وصف'}\n"
            f"🏷️ {product[6]}\n"
            f"🏪 {store_name}"
        )

        send(
            chat_id,
            text,
            kb,
            photo=product[4],
        )


# =========================================================
# MARKET
# =========================================================

def show_market(chat_id):
    keyboard = cat_kb("browse")

    keyboard.append(
        [
            {
                "text": "🛍️ كل المنتجات",
                "callback_data": "browse:all",
            }
        ]
    )

    keyboard.append(
        [
            {
                "text": "🔍 بحث عن منتج",
                "callback_data": "search",
            }
        ]
    )

    send(
        chat_id,
        "🛍️ سوق السودان\n\nاختر القسم:",
        keyboard,
    )


# =========================================================
# MERCHANT
# =========================================================

def show_merchant_intro(chat_id):
    keyboard = [
        [
            {
                "text": "✅ أنا تاجر الآن",
                "callback_data": "merchant",
            }
        ]
    ]

    send(
        chat_id,
        f"""
🏪 إنشاء حساب تاجر

يمكنك إنشاء متجر وبيع منتجاتك داخل البوت.

خطوات التسجيل:
1️⃣ اسم المتجر
2️⃣ رقم الهاتف
3️⃣ المدينة
4️⃣ صورة إثبات الهوية
5️⃣ مراجعة الإدارة

عمولة السوق: {COMMISSION_RATE}٪
نظام الإحالات: {REFERRAL_RATE}٪
""",
        keyboard,
    )


def open_merchant(chat_id, uid, message_id=None):
    set_state(uid, None, {})

    merchant = db.execute(
        "SELECT * FROM merchants WHERE user_id=?",
        (uid,),
    ).fetchone()

    if not merchant:
        set_state(uid, "await_store_name", {})
        text = "🏪 إنشاء متجر\n\nأرسل اسم المتجر:"
        keyboard = []
    else:
        status = merchant[5]

        if status == "banned":
            text = (
                "🚫 متجر موقوف.\n"
                f"تواصل مع الإدارة: {ADMIN_CONTACT}"
            )
            keyboard = []

        elif status == "pending":
            text = (
                f"⏳ متجرك «{merchant[1]}» قيد المراجعة."
            )
            keyboard = []

        elif status in ("rejected_temp", "rejected_perm"):
            reason = merchant[6] or "لم يتم تحديد السبب."

            text = (
                "❌ تم رفض طلب المتجر.\n\n"
                f"السبب:\n{reason}\n\n"
                "يمكنك إعادة التقديم."
            )

            keyboard = [
                [
                    {
                        "text": "🔄 إعادة التقديم",
                        "callback_data": "merchant_reregister",
                    }
                ]
            ]

        else:
            product_count = db.execute(
                """
                SELECT COUNT(*)
                FROM products
                WHERE merchant_id=? AND status='approved'
                """,
                (uid,),
            ).fetchone()[0]

            pending_orders = db.execute(
                """
                SELECT COUNT(*)
                FROM orders
                WHERE merchant_id=?
                AND status IN ('pending_shipment','shipped')
                """,
                (uid,),
            ).fetchone()[0]

            due = merchant[7] or 0

            text = (
                f"🏪 متجر: {merchant[1]}\n\n"
                f"📦 المنتجات: {product_count}\n"
                f"🚚 الطلبات: {pending_orders}\n"
                f"💰 العمولة المستحقة: {due}ج"
            )

            keyboard = []

            if due > 0:
                keyboard.append(
                    [
                        {
                            "text": f"💳 دفع العمولة {due}ج",
                            "callback_data": "pay_commission",
                        }
                    ]
                )
            else:
                keyboard.append(
                    [
                        {
                            "text": "➕ إضافة منتج",
                            "callback_data": "add",
                        },
                        {
                            "text": "📊 مبيعاتي",
                            "callback_data": "sales",
                        },
                    ]
                )

            keyboard.append(
                [
                    {
                        "text": f"📦 الطلبات ({pending_orders})",
                        "callback_data": "my_pending",
                    }
                ]
            )

            keyboard.append(
                [
                    {
                        "text": "🛍️ تصفح السوق",
                        "callback_data": "buyer",
                    }
                ]
            )

    if message_id:
        edit(
            chat_id,
            message_id,
            text,
            keyboard,
        )
    else:
        send(
            chat_id,
            text,
            keyboard,
        )


# =========================================================
# HOME
# =========================================================

def home_keyboard(uid):
    keyboard = [
        [
            {
                "text": "🛍️ تسوق",
                "callback_data": "buyer",
            },
            {
                "text": "🔍 بحث",
                "callback_data": "search",
            },
        ],
        [
            {
                "text": "📊 حسابي",
                "callback_data": "account",
            },
            {
                "text": "💰 الربح",
                "callback_data": "profit",
            },
        ],
        [
            {
                "text": "☎️ خدمة العملاء",
                "callback_data": "support",
            }
        ],
    ]

    merchant = db.execute(
        "SELECT status FROM merchants WHERE user_id=?",
        (uid,),
    ).fetchone()

    if merchant:
        keyboard.append(
            [
                {
                    "text": "🏪 لوحة متجري",
                    "callback_data": "merchant",
                }
            ]
        )
    else:
        keyboard.append(
            [
                {
                    "text": "🏪 إنشاء حساب تاجر",
                    "callback_data": "merchant",
                }
            ]
        )

    if uid == ADMIN_ID and ADMIN_ID:
        keyboard.append(
            [
                {
                    "text": "👑 لوحة الأدمن",
                    "callback_data": "admin_panel",
                }
            ]
        )

    return keyboard


def show_home(chat_id, uid, message_id=None):
    text = (
        "🏠 سوق السودان\n\n"
        "مرحبًا بك 👋\n"
        "اختر الخدمة التي تريدها:"
    )

    keyboard = home_keyboard(uid)

    if message_id:
        edit(chat_id, message_id, text, keyboard)
    else:
        send(chat_id, text, keyboard, main_kb=True)


# =========================================================
# ACCOUNT
# =========================================================

def account_text(uid):
    row = db.execute(
        """
        SELECT points,purchases,sales,profit_active,
               referral_earnings,referral_balance
        FROM users
        WHERE user_id=?
        """,
        (uid,),
    ).fetchone()

    if not row:
        row = (0, 0, 0, 0, 0, 0)

    referrals = db.execute(
        "SELECT COUNT(*) FROM referrals WHERE referrer_id=?",
        (uid,),
    ).fetchone()[0]

    link = f"https://t.me/{BOT_USERNAME}?start={uid}"

    status = "✅ مفعل" if row[3] else "❌ غير مفعل"

    return (
        "📊 حسابي\n\n"
        f"🛒 المشتريات: {row[1]}\n"
        f"📦 المبيعات: {row[2]}\n"
        f"⭐ النقاط: {row[0]}\n\n"
        f"💰 الربح بالإحالة: {status}\n"
        f"👥 الإحالات: {referrals}\n"
        f"💵 الأرباح: {row[4]}ج\n"
        f"💳 الرصيد: {row[5]}ج\n\n"
        f"🔗 رابطك:\n{link}"
    )


# =========================================================
# ADMIN
# =========================================================

def admin_panel(chat_id, message_id):
    users = db.execute(
        "SELECT COUNT(*) FROM users"
    ).fetchone()[0]

    merchants = db.execute(
        "SELECT COUNT(*) FROM merchants WHERE status='approved'"
    ).fetchone()[0]

    pending = db.execute(
        "SELECT COUNT(*) FROM merchants WHERE status='pending'"
    ).fetchone()[0]

    products = db.execute(
        "SELECT COUNT(*) FROM products WHERE status='pending'"
    ).fetchone()[0]

    commission = db.execute(
        """
        SELECT COALESCE(SUM(commission),0)
        FROM orders
        WHERE status='completed'
        """
    ).fetchone()[0]

    referrals = db.execute(
        "SELECT COALESCE(SUM(amount),0) FROM referral_profits"
    ).fetchone()[0]

    orders = db.execute(
        "SELECT COUNT(*) FROM orders"
    ).fetchone()[0]

    text = (
        "👑 لوحة الأدمن\n\n"
        f"👥 المستخدمين: {users}\n"
        f"🏪 التجار: {merchants}\n"
        f"⏳ تجار معلقون: {pending}\n"
        f"📦 منتجات معلقة: {products}\n"
        f"🧾 الطلبات: {orders}\n"
        f"💰 العمولات: {commission}ج\n"
        f"💸 الإحالات: {referrals}ج\n"
    )

    keyboard = [
        [
            {
                "text": f"👥 المستخدمين ({users})",
                "callback_data": "admin_users",
            }
        ],
        [
            {
                "text": f"🏪 التجار ({merchants})",
                "callback_data": "admin_merchants",
            }
        ],
        [
            {
                "text": f"⏳ المعلّق ({pending})",
                "callback_data": "admin_pending",
            }
        ],
        [
            {
                "text": f"📦 منتجات معلقة ({products})",
                "callback_data": "admin_products",
            }
        ],
        [
            {
                "text": "🧾 الطلبات",
                "callback_data": "admin_orders",
            }
        ],
        [
            {
                "text": "💰 العمولات",
                "callback_data": "admin_profits",
            }
        ],
        [
            {
                "text": "💸 أرباح الإحالات",
                "callback_data": "admin_ref_profits",
            }
        ],
        [
            {
                "text": "🏠 الرئيسية",
                "callback_data": "home",
            }
        ],
    ]

    edit(chat_id, message_id, text, keyboard)


# =========================================================
# MESSAGE HANDLER
# =========================================================

def handle_msg(message):
    if "from" not in message or "chat" not in message:
        return

    uid = message["from"]["id"]
    chat = message["chat"]["id"]

    ensure_user(uid)

    text = message.get("text", "")
    state = get_state(uid)
    temp = get_temp(uid)

    banned = db.execute(
        "SELECT is_banned FROM users WHERE user_id=?",
        (uid,),
    ).fetchone()

    if banned and banned[0] and uid != ADMIN_ID:
        send(
            chat,
            f"🚫 حسابك محظور.\nتواصل: {ADMIN_CONTACT}",
        )
        return

    # -----------------------------------------------------
    # START
    # -----------------------------------------------------

    if text.startswith("/start"):
        parts = text.split()

        if len(parts) > 1 and parts[1].isdigit():
            referrer = int(parts[1])

            if referrer != uid:
                existing = db.execute(
                    "SELECT referred_by FROM users WHERE user_id=?",
                    (uid,),
                ).fetchone()

                if not existing or not existing[0]:
                    ref_exists = db.execute(
                        "SELECT id FROM referrals WHERE referred_id=?",
                        (uid,),
                    ).fetchone()

                    if not ref_exists:
                        db.execute(
                            """
                            INSERT OR IGNORE INTO referrals
                            (referrer_id,referred_id,created_at)
                            VALUES(?,?,?)
                            """,
                            (
                                referrer,
                                uid,
                                time.strftime("%Y-%m-%d"),
                            ),
                        )

                        db.execute(
                            "UPDATE users SET referred_by=?, points=points+10 WHERE user_id=?",
                            (referrer, uid),
                        )

                        db_commit()

                        send(
                            referrer,
                            "🎉 إحالة جديدة!\n"
                            "+10 نقاط\n"
                            f"إذا كان الربح مفعلًا ستكسب {REFERRAL_RATE}% من مشتريات الإحالة.",
                        )

        set_state(uid, None, {})
        show_home(chat, uid)
        return

    # -----------------------------------------------------
    # MAIN BUTTONS
    # -----------------------------------------------------

    if text in ("🛍️ تسوق", "تسوق"):
        set_state(uid, None, {})
        show_market(chat)
        return

    if text in (
        "🔍 بحث عن منتج",
        "🔍 بحث",
        "بحث",
        "بحث عن منتج",
    ):
        set_state(uid, "await_search", {})
        send(
            chat,
            "🔍 أرسل اسم المنتج أو جزءًا منه:",
            main_kb=True,
        )
        return

    if text in (
        "🏪 إنشاء حساب تاجر",
        "إنشاء حساب تاجر",
        "🏪 لوحة متجري",
        "🏪 حالة متجري",
        "لوحة متجري",
    ):
        open_merchant(chat, uid)
        return

    if text in ("💰 الربح من البوت", "الربح من البوت"):
        db.execute(
            "UPDATE users SET profit_active=1 WHERE user_id=?",
            (uid,),
        )
        db_commit()

        link = f"https://t.me/{BOT_USERNAME}?start={uid}"

        send(
            chat,
            f"🎉 تم تفعيل الربح {REFERRAL_RATE}%\n\n"
            f"تكسب {REFERRAL_RATE}% من مشتريات الأشخاص الذين يدخلون من رابطك.\n\n"
            f"🔗 رابطك:\n{link}",
            main_kb=True,
        )
        return

    if text in ("📊 حسابي", "حسابي"):
        keyboard = [
            [
                {
                    "text": "💰 أرباح الإحالات",
                    "callback_data": "my_referral_earnings",
                }
            ],
            [
                {
                    "text": "🏠 الرئيسية",
                    "callback_data": "home",
                }
            ],
        ]

        send(
            chat,
            account_text(uid),
            keyboard,
        )
        return

    if text in ("☎️ خدمة العملاء", "خدمة العملاء"):
        send(
            chat,
            f"☎️ خدمة العملاء\n\nتواصل مع الإدارة:\n{ADMIN_CONTACT}",
            main_kb=True,
        )
        return

    if text in ("👑 لوحة الأدمن", "/admin") and uid == ADMIN_ID:
        send(
            chat,
            "👑 لوحة الإدارة:",
            [
                [
                    {
                        "text": "فتح لوحة الأدمن",
                        "callback_data": "admin_panel",
                    }
                ]
            ],
        )
        return

    # -----------------------------------------------------
    # SEARCH
    # -----------------------------------------------------

    if state == "await_search":
        set_state(uid, None, {})
        do_search(chat, text)
        return

    # -----------------------------------------------------
    # MERCHANT REGISTRATION
    # -----------------------------------------------------

    if state == "await_store_name":
        if len(text.strip()) < 2:
            send(chat, "أرسل اسم متجر صحيح:")
            return

        temp["store_name"] = text.strip()

        set_state(
            uid,
            "await_phone",
            temp,
        )

        send(chat, "📱 أرسل رقم الهاتف:")
        return

    if state == "await_phone":
        if len(text.strip()) < 5:
            send(chat, "أرسل رقم هاتف صحيح:")
            return

        temp["phone"] = text.strip()

        set_state(
            uid,
            "await_city",
            temp,
        )

        send(chat, "📍 أرسل اسم المدينة:")
        return

    if state == "await_city":
        if len(text.strip()) < 2:
            send(chat, "أرسل اسم المدينة:")
            return

        temp["city"] = text.strip()

        set_state(
            uid,
            "await_doc",
            temp,
        )

        send(
            chat,
            "🪪 أرسل صورة واضحة لمستند الهوية.\n"
            "أرسل الصورة فقط.",
        )
        return

    if state == "await_doc":
        if "photo" not in message:
            send(
                chat,
                "❌ يجب إرسال صورة مستند الهوية.",
            )
            return

        photo_id = message["photo"][-1]["file_id"]

        db.execute(
            """
            INSERT INTO merchants
            (user_id,store_name,phone,city,doc_photo,status,reject_reason)
            VALUES(?,?,?,?,?,'pending','')
            ON CONFLICT(user_id) DO UPDATE SET
                store_name=excluded.store_name,
                phone=excluded.phone,
                city=excluded.city,
                doc_photo=excluded.doc_photo,
                status='pending',
                reject_reason=''
            """,
            (
                uid,
                temp["store_name"],
                temp["phone"],
                temp["city"],
                photo_id,
            ),
        )

        db_commit()
        set_state(uid, None, {})

        send(
            chat,
            "✅ تم إرسال طلب إنشاء المتجر.\n"
            "⏳ انتظر مراجعة الإدارة.",
            main_kb=True,
        )

        if ADMIN_ID:
            keyboard = [
                [
                    {
                        "text": "✅ قبول",
                        "callback_data": f"m_ok:{uid}",
                    }
                ],
                [
                    {
                        "text": "⏳ رفض مؤقت",
                        "callback_data": f"m_reject_temp:{uid}",
                    },
                    {
                        "text": "🚫 رفض نهائي",
                        "callback_data": f"m_reject_perm:{uid}",
                    },
                ],
            ]

            send(
                ADMIN_ID,
                f"🔔 طلب متجر جديد\n\n"
                f"المتجر: {temp['store_name']}\n"
                f"الهاتف: {temp['phone']}\n"
                f"المدينة: {temp['city']}\n"
                f"ID: {uid}",
                keyboard,
                photo=photo_id,
            )

        return

    # -----------------------------------------------------
    # PRODUCT CREATION
    # -----------------------------------------------------

    if state == "await_prod_photo":
        if "photo" not in message:
            send(chat, "❌ أرسل صورة المنتج:")
            return

        temp["photo"] = message["photo"][-1]["file_id"]

        set_state(
            uid,
            "await_prod_name",
            temp,
        )

        send(chat, "📦 أرسل اسم المنتج:")
        return

    if state == "await_prod_name":
        if len(text.strip()) < 2:
            send(chat, "أرسل اسم المنتج:")
            return

        temp["name"] = text.strip()

        set_state(
            uid,
            "await_prod_price",
            temp,
        )

        send(chat, "💰 أرسل السعر الصافي الذي تريد الحصول عليه:")
        return

    if state == "await_prod_price":
        clean = text.replace(",", "").replace(" ", "")

        if not clean.isdigit() or int(clean) <= 0:
            send(
                chat,
                "❌ أرسل السعر بالأرقام فقط.",
            )
            return

        base_price = int(clean)

        commission_fee = (
            base_price * COMMISSION_RATE + 50
        ) // 100

        final_price = base_price + commission_fee

        temp["base_price"] = base_price
        temp["commission_fee"] = commission_fee
        temp["price"] = final_price

        set_state(
            uid,
            "await_prod_cat",
            temp,
        )

        send(
            chat,
            f"السعر الصافي: {base_price}ج\n"
            f"العمولة {COMMISSION_RATE}%: {commission_fee}ج\n"
            f"السعر النهائي للعميل: {final_price}ج\n\n"
            "اختر القسم:",
            cat_kb("setcat"),
        )
        return

    if state == "await_prod_desc":
        merchant = db.execute(
            """
            SELECT status,commission_due
            FROM merchants
            WHERE user_id=?
            """,
            (uid,),
        ).fetchone()

        if not merchant or merchant[0] != "approved":
            set_state(uid, None, {})
            send(
                chat,
                "❌ حساب التاجر غير مفعل.",
                main_kb=True,
            )
            return

        if (merchant[1] or 0) > 0:
            set_state(uid, None, {})
            send(
                chat,
                f"❌ عليك عمولة مستحقة {merchant[1]}ج.",
                main_kb=True,
            )
            return

        if len(text.strip()) < 2:
            send(chat, "أرسل وصف المنتج:")
            return

        temp["description"] = text.strip()

        db.execute(
            """
            INSERT INTO products
            (merchant_id,name,price,photo_id,description,
             category,status,base_price,commission_fee)
            VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                uid,
                temp["name"],
                temp["price"],
                temp["photo"],
                temp["description"],
                temp.get("category", "📦 أخرى"),
                "pending",
                temp["base_price"],
                temp["commission_fee"],
            ),
        )

        db_commit()

        product_id = db.execute(
            "SELECT last_insert_rowid()"
        ).fetchone()[0]

        set_state(uid, None, {})

        send(
            chat,
            "✅ تم إرسال المنتج للمراجعة.\n"
            "⏳ لن يظهر في السوق حتى توافق الإدارة.",
            main_kb=True,
        )

        if ADMIN_ID:
            keyboard = [
                [
                    {
                        "text": "✅ قبول",
                        "callback_data": f"p_ok:{product_id}",
                    }
                ],
                [
                    {
                        "text": "⏳ رفض مؤقت",
                        "callback_data": f"p_reject_temp:{product_id}",
                    },
                    {
                        "text": "🚫 رفض نهائي",
                        "callback_data": f"p_reject_perm:{product_id}",
                    },
                ],
            ]

            send(
                ADMIN_ID,
                f"🔔 منتج جديد\n\n"
                f"📦 {temp['name']}\n"
                f"💰 {temp['price']}ج\n"
                f"🏷️ {temp.get('category','📦 أخرى')}\n"
                f"ID: {product_id}",
                keyboard,
                photo=temp["photo"],
            )

        return

    # -----------------------------------------------------
    # COMMISSION RECEIPT
    # -----------------------------------------------------

    if state == "await_commission_receipt":
        if "photo" not in message:
            send(
                chat,
                "❌ أرسل صورة واضحة للإيصال.",
            )
            return

        merchant = db.execute(
            """
            SELECT commission_due,store_name
            FROM merchants
            WHERE user_id=?
            """,
            (uid,),
        ).fetchone()

        if not merchant or merchant[0] <= 0:
            set_state(uid, None, {})
            send(
                chat,
                "لا توجد عمولة مستحقة.",
                main_kb=True,
            )
            return

        pending = db.execute(
            """
            SELECT id
            FROM commission_payments
            WHERE merchant_id=? AND status='pending'
            LIMIT 1
            """,
            (uid,),
        ).fetchone()

        if pending:
            set_state(uid, None, {})
            send(
                chat,
                "لديك إيصال قيد المراجعة بالفعل.",
                main_kb=True,
            )
            return

        receipt = message["photo"][-1]["file_id"]
        amount = merchant[0]

        db.execute(
            """
            INSERT INTO commission_payments
            (merchant_id,amount,receipt_photo,status,created_at)
            VALUES(?,?,?,'pending',?)
            """,
            (
                uid,
                amount,
                receipt,
                time.strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )

        db_commit()

        payment_id = db.execute(
            "SELECT last_insert_rowid()"
        ).fetchone()[0]

        set_state(uid, None, {})

        if not ADMIN_ID:
            send(
                chat,
                "⚠️ ADMIN_ID غير مضبوط.",
                main_kb=True,
            )
            return

        keyboard = [
            [
                {
                    "text": "✅ تأكيد السداد",
                    "callback_data": f"commission_paid:{payment_id}",
                }
            ],
            [
                {
                    "text": "❌ رفض الإيصال",
                    "callback_data": f"commission_reject:{payment_id}",
                }
            ],
        ]

        send(
            ADMIN_ID,
            f"🧾 إيصال سداد جديد\n\n"
            f"رقم العملية: {payment_id}\n"
            f"التاجر: {merchant[1]}\n"
            f"ID: {uid}\n"
            f"المبلغ: {amount}ج",
            keyboard,
            photo=receipt,
        )

        send(
            chat,
            "✅ تم إرسال الإيصال للإدارة.\n"
            "انتظر تأكيد السداد.",
            main_kb=True,
        )

        return

    # -----------------------------------------------------
    # ORDER CUSTOMER INFO
    # -----------------------------------------------------

    if state == "await_cod_info":
        if len(text.strip()) < 5:
            send(
                chat,
                "أرسل الاسم + رقم الهاتف + العنوان.",
            )
            return

        merchant = db.execute(
            """
            SELECT status,commission_due
            FROM merchants
            WHERE user_id=?
            """,
            (temp["merchant_id"],),
        ).fetchone()

        if not merchant or merchant[0] != "approved":
            set_state(uid, None, {})
            send(
                chat,
                "❌ المتجر غير متاح.",
                main_kb=True,
            )
            return

        if (merchant[1] or 0) > 0:
            set_state(uid, None, {})
            send(
                chat,
                "❌ المتجر موقوف مؤقتًا بسبب عمولة مستحقة.",
                main_kb=True,
            )
            return

        db.execute(
            """
            INSERT INTO orders
            (buyer_id,product_id,merchant_id,price,
             commission,referral_comm,buyer_info,status,created_at)
            VALUES(?,?,?,?,?,?,?,'pending_shipment',?)
            """,
            (
                uid,
                temp["product_id"],
                temp["merchant_id"],
                temp["price"],
                temp["commission"],
                0,
                text.strip(),
                time.strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )

        db.execute(
            "UPDATE users SET purchases=purchases+1 WHERE user_id=?",
            (uid,),
        )

        db_commit()

        order_id = db.execute(
            "SELECT last_insert_rowid()"
        ).fetchone()[0]

        set_state(uid, None, {})

        send(
            chat,
            f"✅ تم تسجيل الطلب #{order_id}\n\n"
            f"📦 {temp['product_name']}\n"
            f"💰 {temp['price']}ج\n"
            "💳 الدفع عند الاستلام\n\n"
            "انتظر شحن الطلب.",
            main_kb=True,
        )

        keyboard = [
            [
                {
                    "text": f"📦 تم الشحن #{order_id}",
                    "callback_data": f"ship:{order_id}",
                }
            ]
        ]

        send(
            temp["merchant_id"],
            f"🔔 طلب جديد #{order_id}\n\n"
            f"📦 {temp['product_name']}\n"
            f"💰 {temp['price']}ج\n\n"
            f"بيانات العميل:\n{text.strip()}\n\n"
            "اضغط عند شحن الطلب:",
            keyboard,
        )

        return

    # -----------------------------------------------------
    # ADMIN REJECTION REASON
    # -----------------------------------------------------

    if state and state.startswith("reject_reason:"):
        if uid != ADMIN_ID:
            return

        parts = state.split(":")

        if len(parts) != 4:
            set_state(uid, None, {})
            return

        target_type = parts[1]
        action = parts[2]
        target_id = int(parts[3])

        reason = text.strip()

        if target_type == "merchant":
            status = (
                "rejected_perm"
                if action == "perm"
                else "rejected_temp"
            )

            db.execute(
                """
                UPDATE merchants
                SET status=?, reject_reason=?
                WHERE user_id=?
                """,
                (
                    status,
                    reason,
                    target_id,
                ),
            )

            send(
                target_id,
                f"❌ تم رفض طلب المتجر.\n\nالسبب:\n{reason}",
                main_kb=True,
            )

        else:
            status = (
                "rejected_perm"
                if action == "perm"
                else "rejected_temp"
            )

            product = db.execute(
                """
                SELECT merchant_id,name
                FROM products
                WHERE id=?
                """,
                (target_id,),
            ).fetchone()

            db.execute(
                """
                UPDATE products
                SET status=?, reject_reason=?
                WHERE id=?
                """,
                (
                    status,
                    reason,
                    target_id,
                ),
            )

            if product:
                send(
                    product[0],
                    f"❌ تم رفض المنتج «{product[1]}».\n\n"
                    f"السبب:\n{reason}",
                    main_kb=True,
                )

        db_commit()
        set_state(uid, None, {})

        send(
            chat,
            "✅ تم حفظ سبب الرفض.",
        )

        return

    # -----------------------------------------------------
    # NORMAL TEXT SEARCH
    # -----------------------------------------------------

    if text and len(text.strip()) >= 2 and not state:
        do_search(chat, text.strip())
        return


# =========================================================
# CALLBACK HANDLER
# =========================================================

def handle_cb(callback):
    uid = callback["from"]["id"]
    data = callback.get("data", "")

    message = callback.get("message")

    if not message:
        answer(callback["id"])
        return

    chat = message["chat"]["id"]
    mid = message["message_id"]

    ensure_user(uid)

    # -----------------------------------------------------
    # HOME
    # -----------------------------------------------------

    if data == "home":
        set_state(uid, None, {})
        show_home(chat, uid, mid)
        answer(callback["id"])
        return

    # -----------------------------------------------------
    # SEARCH
    # -----------------------------------------------------

    if data == "search":
        set_state(uid, "await_search", {})
        edit(
            chat,
            mid,
            "🔍 أرسل اسم المنتج أو جزءًا منه:",
            [],
        )
        answer(callback["id"])
        return

    # -----------------------------------------------------
    # MARKET
    # -----------------------------------------------------

    if data == "buyer":
        show_market(chat)
        answer(callback["id"])
        return

    if data.startswith("browse:"):
        value = data.split(":", 1)[1]

        if value == "all":
            products = db.execute(
                """
                SELECT p.*
                FROM products p
                JOIN merchants m ON m.user_id=p.merchant_id
                WHERE p.status='approved'
                AND m.status='approved'
                ORDER BY p.id DESC
                LIMIT 10
                """
            ).fetchall()

            title = "🛍️ كل المنتجات"

        else:
            category = category_from_index(value)

            products = db.execute(
                """
                SELECT p.*
                FROM products p
                JOIN merchants m ON m.user_id=p.merchant_id
                WHERE p.status='approved'
                AND m.status='approved'
                AND p.category=?
                ORDER BY p.id DESC
                LIMIT 10
                """,
                (category,),
            ).fetchall()

            title = f"🏷️ {category}"

        if not products:
            edit(
                chat,
                mid,
                f"{title}\n\n❌ لا توجد منتجات.",
                [
                    [
                        {
                            "text": "🔙 رجوع",
                            "callback_data": "buyer",
                        }
                    ]
                ],
            )

            answer(callback["id"])
            return

        edit(
            chat,
            mid,
            f"{title}\n\nعرض المنتجات:",
            [],
        )

        for product in products:
            store = db.execute(
                "SELECT store_name FROM merchants WHERE user_id=?",
                (product[1],),
            ).fetchone()

            store_name = store[0] if store else "متجر"

            keyboard = [
                [
                    {
                        "text": f"🛒 شراء {product[3]}ج",
                        "callback_data": f"buy:{product[0]}",
                    }
                ]
            ]

            send(
                chat,
                f"📦 {product[2]}\n"
                f"💰 {product[3]}ج\n"
                f"📝 {product[5] or 'لا يوجد وصف'}\n"
                f"🏷️ {product[6]}\n"
                f"🏪 {store_name}",
                keyboard,
                photo=product[4],
            )

        answer(callback["id"])
        return

    # -----------------------------------------------------
    # BUY
    # -----------------------------------------------------

    if data.startswith("buy:"):
        try:
            product_id = int(data.split(":", 1)[1])
        except Exception:
            answer(callback["id"], "منتج غير صحيح")
            return

        product = db.execute(
            """
            SELECT id,merchant_id,name,price,photo_id,
                   description,category,status,
                   base_price,commission_fee
            FROM products
            WHERE id=?
            """,
            (product_id,),
        ).fetchone()

        if not product or product[7] != "approved":
            answer(callback["id"], "المنتج غير متاح")
            return

        if product[1] == uid:
            answer(
                callback["id"],
                "لا يمكنك شراء منتجك الخاص.",
            )
            return

        merchant = db.
