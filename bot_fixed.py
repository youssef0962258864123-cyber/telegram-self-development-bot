from keep_alive import keep_alive
import os
import json
import time
import sqlite3
from urllib.request import Request
from urllib.request import urlopen
from urllib.parse import urlencode

# ============================================================
# ============== الإعدادات الأساسية للبوت ====================
# ============================================================

TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
BOT_USERNAME = os.environ.get("BOT_USERNAME", "your_bot")
ADMIN_CONTACT = os.environ.get("ADMIN_CONTACT", "@admin")

if not TOKEN:
    raise SystemExit("BOT_TOKEN غير موجود في Environment Variables")

API = f"https://api.telegram.org/bot{TOKEN}"
DB = "marketplace.db"

CATEGORIES = [
    "👕 ملابس",
    "🍳 أواني منزلية",
    "🔥 عروض وخصم",
    "⭐ رائج",
    "👗 موضة",
    "📦 أخرى"
]

# ============================================================
# ============== إعداد قاعدة البيانات =========================
# ============================================================

db = sqlite3.connect(DB, check_same_thread=False)

# إنشاء الجداول الأساسية
db.executescript("""
CREATE TABLE IF NOT EXISTS users(
    user_id INTEGER PRIMARY KEY,
    state TEXT,
    temp TEXT,
    points INTEGER DEFAULT 0,
    purchases INTEGER DEFAULT 0,
    sales INTEGER DEFAULT 0,
    referred_by INTEGER,
    is_banned INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS merchants(
    user_id INTEGER PRIMARY KEY,
    store_name TEXT,
    phone TEXT,
    city TEXT,
    status TEXT DEFAULT 'pending',
    reject_reason TEXT
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
    reject_reason TEXT
);

CREATE TABLE IF NOT EXISTS orders(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    buyer_id INTEGER,
    product_id INTEGER,
    merchant_id INTEGER,
    buyer_info TEXT,
    payment_type TEXT,
    status TEXT
);

CREATE TABLE IF NOT EXISTS referrals(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    referrer_id INTEGER,
    referred_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
""")

# محاولة إضافة الأعمدة الجديدة لو الجدول قديم
try:
    db.execute("ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0")
    db.commit()
except Exception:
    pass

try:
    db.execute("ALTER TABLE merchants ADD COLUMN reject_reason TEXT")
    db.commit()
except Exception:
    pass

try:
    db.execute("ALTER TABLE products ADD COLUMN reject_reason TEXT")
    db.commit()
except Exception:
    pass

db.commit()

# ============================================================
# ============== دوال الاتصال بتليجرام =======================
# ============================================================

def api(method, data=None):
    """
    دالة إرسال طلبات لتليجرام
    """
    if data is None:
        data = {}

    try:
        request = Request(
            API + "/" + method,
            data=urlencode(data).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        with urlopen(request, timeout=30) as response:
            result = json.loads(response.read())
            return result
    except Exception as e:
        print(f"خطأ في api {method}: {e}")
        return {}

def send(chat_id, text, inline_keyboard=None, photo=None, show_main_keyboard=False):
    """
    إرسال رسالة أو صورة
    show_main_keyboard = يظهر زر التحديث المقترح وخدمة العملاء
    """
    if photo:
        payload = {}
        payload["chat_id"] = chat_id
        payload["photo"] = photo
        payload["caption"] = text

        if inline_keyboard:
            payload["reply_markup"] = json.dumps(
                {"inline_keyboard": inline_keyboard},
                ensure_ascii=False
            )

        return api("sendPhoto", payload)
    else:
        payload = {}
        payload["chat_id"] = chat_id
        payload["text"] = text

        if inline_keyboard:
            payload["reply_markup"] = json.dumps(
                {"inline_keyboard": inline_keyboard},
                ensure_ascii=False
            )
        elif show_main_keyboard:
            # هذا هو زر start المقترح + خدمة العملاء
            payload["reply_markup"] = json.dumps(
                {
                    "keyboard": [
                        ["🔄 تحديث الصفحة /start"],
                        ["📊 حسابي", "☎️ خدمة العملاء"]
                    ],
                    "resize_keyboard": True
                },
                ensure_ascii=False
            )

        return api("sendMessage", payload)

def edit(chat_id, message_id, text, inline_keyboard=None):
    """
    تعديل رسالة موجودة
    """
    payload = {}
    payload["chat_id"] = chat_id
    payload["message_id"] = message_id
    payload["text"] = text

    if inline_keyboard:
        payload["reply_markup"] = json.dumps(
            {"inline_keyboard": inline_keyboard},
            ensure_ascii=False
        )

    try:
        return api("editMessageText", payload)
    except Exception:
        payload2 = {}
        payload2["chat_id"] = chat_id
        payload2["message_id"] = message_id
        payload2["caption"] = text

        if inline_keyboard:
            payload2["reply_markup"] = json.dumps(
                {"inline_keyboard": inline_keyboard},
                ensure_ascii=False
            )

        try:
            return api("editMessageCaption", payload2)
        except Exception as e:
            print(f"فشل تعديل الرسالة: {e}")
            return None

def answer(callback_query_id, text=""):
    """
    رد على ضغطة زر
    """
    return api("answerCallbackQuery", {
        "callback_query_id": callback_query_id,
        "text": text
    })

# ============================================================
# ============== دوال إدارة حالة المستخدم =====================
# ============================================================

def get_temp(user_id):
    row = db.execute("SELECT temp FROM users WHERE user_id=?", (user_id,)).fetchone()

    if row and row[0]:
        try:
            data = json.loads(row[0])
            return data
        except Exception:
            return {}

    return {}

def set_state(user_id, state, temp_data=None):
    db.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (user_id,))

    if temp_data is not None:
        json_data = json.dumps(temp_data, ensure_ascii=False)
        db.execute(
            "UPDATE users SET state=?, temp=? WHERE user_id=?",
            (state, json_data, user_id)
        )
    else:
        db.execute(
            "UPDATE users SET state=? WHERE user_id=?",
            (state, user_id)
        )

    db.commit()

def get_state(user_id):
    row = db.execute("SELECT state FROM users WHERE user_id=?", (user_id,)).fetchone()

    if row:
        return row[0]
    else:
        return None

def get_category_keyboard(prefix):
    keyboard = []

    for i in range(0, len(CATEGORIES), 2):
        row = []
        button1 = {
            "text": CATEGORIES[i],
            "callback_data": f"{prefix}:{CATEGORIES[i]}"
        }
        row.append(button1)

        if i + 1 < len(CATEGORIES):
            button2 = {
                "text": CATEGORIES[i+1],
                "callback_data": f"{prefix}:{CATEGORIES[i+1]}"
            }
            row.append(button2)

        keyboard.append(row)

    return keyboard

def setup_bot_commands():
    try:
        commands_list = [
            {"command": "start", "description": "🏠 الرئيسية - تحديث الصفحة"}
        ]
        commands_json = json.dumps(commands_list, ensure_ascii=False)
        api("setMyCommands", {"commands": commands_json})
        print("تم ضبط أمر /start المقترح بنجاح")
    except Exception as e:
        print(f"خطأ في setup_bot_commands: {e}")

# ============================================================
# ============== معالجة الرسائل النصية =======================
# ============================================================

def handle_message(message):
    user_id = message["from"]["id"]
    chat_id = message["chat"]["id"]
    text = message.get("text", "")

    state = get_state(user_id)
    temp = get_temp(user_id)

    db.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (user_id,))
    db.commit()

    # التحقق من الحظر
    banned_row = db.execute("SELECT is_banned FROM users WHERE user_id=?", (user_id,)).fetchone()

    if banned_row and banned_row[0] == 1:
        if user_id!= ADMIN_ID:
            send(chat_id, "🚫 تم حظرك من استخدام البوت، تواصل مع الإدارة: " + ADMIN_CONTACT)
            return

    # معالجة زر التحديث المقترح
    if text in ["🔄 تحديث الصفحة /start", "🔄 تحديث الصفحة", "تحديث", "/start", "start"]:
        text = "/start"

    # معالجة حسابي
    if text in ["📊 حسابي", "حسابي", "حسابي ونقاطي"]:
        row = db.execute("SELECT points, purchases, sales FROM users WHERE user_id=?", (user_id,)).fetchone()

        points = 0
        purch = 0
        sales_count = 0

        if row:
            points = row[0]
            purch = row[1]
            sales_count = row[2]

        if BOT_USERNAME!= "your_bot":
            ref_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        else:
            ref_link = f"رابطك: /start {user_id}"

        msg = ""
        msg += "📊 حسابك:\n\n"
        msg += f"🛒 منتجات اشتريتها: {purch}\n"
        msg += f"📦 منتجات بعتها: {sales_count}\n"
        msg += f"⭐ نقاط الإحالة: {points}\n\n"
        msg += f"🔗 رابط الإحالة الخاص بك:\n{ref_link}\n\n"
        msg += "كل شخص يسجل برابطك تاخد 10 نقاط 🎁"

        send(chat_id, msg, show_main_keyboard=True)
        return

    # معالجة خدمة العملاء
    if text in ["☎️ خدمة العملاء", "خدمة العملاء"]:
        msg = ""
        msg += "☎️ خدمة العملاء\n\n"
        msg += "⭐⭐⭐\n\n"
        msg += f"للتواصل مع الإدارة:\n{ADMIN_CONTACT}\n\n"
        msg += "قريبا سيتم إطلاق بوت تواصل خاص.\n\n"
        msg += "في حال تم رفض طلبك نهائيا، يمكنك التواصل هنا لمعرفة السبب."

        send(chat_id, msg, show_main_keyboard=True)
        return

    # معالجة رفض بتعليق (نهائي أو مؤقت)
    if state and state.startswith("await_reject_reason_"):
        reason = text
        parts = state.split("_")

        final_action = parts[3]
        typ = parts[4]
        target_id = int(parts[5])

        if typ == "m":
            if final_action == "perm":
                new_status = "rejected_perm"
            else:
                new_status = "rejected_temp"

            db.execute(
                "UPDATE merchants SET status=?, reject_reason=? WHERE user_id=?",
                (new_status, reason, target_id)
            )
            db.commit()

            if final_action == "perm":
                send(chat_id, f"✅ تم الرفض النهائي للتاجر {target_id} مع إرسال السبب.")
                try:
                    msg_to_user = ""
                    msg_to_user += "❌ تم رفض طلب متجرك نهائيا للسبب التالي:\n\n"
                    msg_to_user += f"{reason}\n\n"
                    msg_to_user += f"للاستفسار تواصل مع الإدارة: {ADMIN_CONTACT}\n\n"
                    msg_to_user += "☎️ خدمة العملاء: ⭐⭐⭐"
                    send(target_id, msg_to_user, show_main_keyboard=True)
                except Exception:
                    pass
            else:
                send(chat_id, f"✅ تم الرفض المؤقت للتاجر {target_id} - يقدر يقدم تاني.")
                try:
                    msg_to_user = ""
                    msg_to_user += "⏳ تم رفض طلبك مؤقتا للسبب التالي:\n\n"
                    msg_to_user += f"{reason}\n\n"
                    msg_to_user += "يمكنك التعديل والتقديم مرة أخرى عبر /start"
                    send(target_id, msg_to_user, show_main_keyboard=True)
                except Exception:
                    pass
        else:
            if final_action == "perm":
                new_status = "rejected_perm"
            else:
                new_status = "rejected_temp"

            db.execute(
                "UPDATE products SET status=?, reject_reason=? WHERE id=?",
                (new_status, reason, target_id)
            )
            db.commit()

            prod = db.execute("SELECT merchant_id, name FROM products WHERE id=?", (target_id,)).fetchone()

            send(chat_id, f"✅ تم الرفض {final_action} للمنتج {target_id}")

            if prod:
                try:
                    if final_action == "perm":
                        msg_to_merchant = f"❌ تم رفض منتجك '{prod[1]}' نهائيا للسبب:\n\n{reason}\n\nتواصل مع الإدارة: {ADMIN_CONTACT}"
                        send(prod[0], msg_to_merchant, show_main_keyboard=True)
                    else:
                        msg_to_merchant = f"⏳ تم رفض منتجك '{prod[1]}' مؤقتا:\n{reason}\nيمكنك التعديل ورفعه مجددا."
                        send(prod[0], msg_to_merchant, show_main_keyboard=True)
                except Exception:
                    pass

        set_state(user_id, None, {})
        return

    # تسجيل التاجر - الخطوات
    if state == "await_store_name":
        temp["store_name"] = text
        set_state(user_id, "await_phone", temp)
        send(chat_id, "تمام ✅\nالآن أرسل رقم واتساب المتجر:")
        return

    if state == "await_phone":
        temp["phone"] = text
        set_state(user_id, "await_city", temp)
        send(chat_id, "آخر خطوة، أرسل مدينتك / ولايتك:")
        return

    if state == "await_city":
        temp["city"] = text

        db.execute(
            "INSERT OR REPLACE INTO merchants(user_id, store_name, phone, city, status) VALUES(?,?,?,?,?)",
            (user_id, temp["store_name"], temp["phone"], temp["city"], "pending")
        )
        db.commit()
        set_state(user_id, None, {})

        send(chat_id, "✅ تم إرسال طلبك للإدارة، سيتم مراجعته خلال ساعات.", show_main_keyboard=True)

        if ADMIN_ID!= 0:
            kb = [
                [{"text": "✅ قبول التاجر", "callback_data": f"m_ok:{user_id}"}],
                [
                    {"text": "⏳ رفض مؤقت", "callback_data": f"m_reject_temp:{user_id}"},
                    {"text": "🚫 رفض نهائي", "callback_data": f"m_reject_perm:{user_id}"}
                ],
                [{"text": "🔇 كانسل (رفض صامت)", "callback_data": f"m_no:{user_id}"}]
            ]

            msg_admin = ""
            msg_admin += "🔔 تاجر جديد (حتى لو كان مرفوض سابقا):\n\n"
            msg_admin += f"المتجر: {temp['store_name']}\n"
            msg_admin += f"الهاتف: {temp['phone']}\n"
            msg_admin += f"المدينة: {temp['city']}\n"
            msg_admin += f"الايدي: {user_id}"

            send(ADMIN_ID, msg_admin, kb)

        return

    # إضافة منتج - الخطوات
    if state == "await_prod_name":
        temp["name"] = text
        set_state(user_id, "await_prod_price", temp)
        send(chat_id, "حلو، الآن أرسل السعر بالأرقام فقط (مثلا 15000):")
        return

    if state == "await_prod_price":
        if not text.isdigit():
            send(chat_id, "أرسل السعر أرقام فقط:")
            return

        temp["price"] = int(text)
        set_state(user_id, "await_prod_cat", temp)
        send(chat_id, "ممتاز، الآن اختر قسم المنتج:", get_category_keyboard("setcat"))
        return

    if state == "await_prod_desc":
        temp["desc"] = text

        db.execute(
            "INSERT INTO products(merchant_id, name, price, photo_id, description, category, status) VALUES(?,?,?,?,?,?,?)",
            (user_id, temp["name"], temp["price"], temp["photo"], temp["desc"], temp.get("cat", "📦 أخرى"), "pending")
        )
        db.commit()

        product_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        set_state(user_id, None, {})

        send(chat_id, f"✅ تم رفع المنتج في قسم {temp.get('cat')}، بانتظار موافقة الإدارة.", show_main_keyboard=True)

        if ADMIN_ID!= 0:
            kb = [
                [{"text": "✅ قبول ونشر", "callback_data": f"p_ok:{product_id}"}],
                [
                    {"text": "⏳ رفض مؤقت", "callback_data": f"p_reject_temp:{product_id}"},
                    {"text": "🚫 رفض نهائي", "callback_data": f"p_reject_perm:{product_id}"}
                ],
                [{"text": "🔇 كانسل صامت", "callback_data": f"p_no:{product_id}"}]
            ]

            msg_admin = ""
            msg_admin += "🔔 منتج جديد بانتظار الموافقة:\n\n"
            msg_admin += f"📦 {temp['name']} - {temp['price']} جنيه\n"
            msg_admin += f"🏷️ القسم: {temp.get('cat')}\n"
            msg_admin += f"📝 {temp['desc']}"

            send(ADMIN_ID, msg_admin, kb, photo=temp["photo"])

        return

    # نظام الدفع - عند الاستلام
    if state == "await_cod":
        db.execute(
            "INSERT INTO orders(buyer_id, product_id, merchant_id, buyer_info, payment_type, status) VALUES(?,?,?,?,?,?)",
            (user_id, temp["pid"], temp["mid"], text, "عند الاستلام", "confirmed")
        )
        db.commit()

        db.execute("UPDATE users SET purchases=purchases+1 WHERE user_id=?", (user_id,))
        db.execute("UPDATE users SET sales=sales+1 WHERE user_id=?", (temp["mid"],))
        db.commit()

        order_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        set_state(user_id, None, {})

        send(chat_id, f"✅ تم تأكيد طلبك #{order_id} بنجاح!\n\n💵 طريقة الدفع: عند الاستلام\n📦 المنتج: {temp['pname']}\n\nسيتواصل معك البائع قريبا للتوصيل.", show_main_keyboard=True)

        try:
            msg_merchant = ""
            msg_merchant += f"🔔 طلب جديد #{order_id} - دفع عند الاستلام 💵\n\n"
            msg_merchant += f"📦 المنتج: {temp['pname']}\n"
            msg_merchant += f"💰 السعر: {temp['price']} جنيه\n"
            msg_merchant += f"👤 بيانات المشتري: {text}\n\n"
            msg_merchant += "تواصل مع المشتري فورا!"

            send(temp["mid"], msg_merchant)
        except Exception:
            pass

        return

    # نظام الدفع - قبل الاستلام
    if state == "await_pre":
        info = f"رقم الهاتف: {text}"

        db.execute(
            "INSERT INTO orders(buyer_id, product_id, merchant_id, buyer_info, payment_type, status) VALUES(?,?,?,?,?,?)",
            (user_id, temp["pid"], temp["mid"], info, "قبل الاستلام", "pending_call")
        )
        db.commit()

        db.execute("UPDATE users SET purchases=purchases+1 WHERE user_id=?", (user_id,))
        db.execute("UPDATE users SET sales=sales+1 WHERE user_id=?", (temp["mid"],))
        db.commit()

        order_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        set_state(user_id, None, {})

        msg_buyer = ""
        msg_buyer += f"✅ تمام! تم حفظ طلبك #{order_id}\n\n"
        msg_buyer += "💳 طريقة الدفع: قبل الاستلام\n"
        msg_buyer += f"📞 رقمك: {text}\n\n"
        msg_buyer += "البائع سوف يتصل بك خلال دقائق لتأكيد الطلب."

        send(chat_id, msg_buyer, show_main_keyboard=True)

        try:
            msg_merchant = ""
            msg_merchant += f"🔔 طلب جديد #{order_id} - دفع قبل الاستلام 💳\n\n"
            msg_merchant += f"📦 المنتج: {temp['pname']}\n"
            msg_merchant += f"💰 السعر: {temp['price']} جنيه\n"
            msg_merchant += f"📞 رقم المشتري: {text}\n\n"
            msg_merchant += "⚠️ اتصل بالمشتري الآن!"

            send(temp["mid"], msg_merchant)
        except Exception:
            pass

        return

    # استقبال صورة المنتج
    if "photo" in message and state == "await_prod_photo":
        photo_id = message["photo"][-1]["file_id"]
        temp["photo"] = photo_id
        set_state(user_id, "await_prod_name", temp)
        send(chat_id, "الصورة وصلت ✅\nالآن أرسل اسم المنتج:")
        return

    # أمر البداية مع نظام الإحالة
    if text.startswith("/start"):
        parts = text.split()

        if len(parts) > 1:
            if parts[1].isdigit():
                ref_id = int(parts[1])

                if ref_id!= user_id:
                    already = db.execute("SELECT * FROM referrals WHERE referred_id=?", (user_id,)).fetchone()
                    user_ref = db.execute("SELECT referred_by FROM users WHERE user_id=?", (user_id,)).fetchone()

                    if not already and (not user_ref or not user_ref[0]):
                        db.execute("INSERT INTO referrals(referrer_id,referred_id) VALUES(?,?)", (ref_id, user_id))
                        db.execute("UPDATE users SET points=points+10 WHERE user_id=?", (ref_id,))
                        db.execute("UPDATE users SET referred_by=? WHERE user_id=?", (ref_id, user_id))
                        db.commit()

                        try:
                            send(ref_id, "🎉 مبروك! شخص جديد سجل برابطك وحصلت على 10 نقاط! ⭐")
                        except Exception:
                            pass

        merch = db.execute("SELECT * FROM merchants WHERE user_id=?", (user_id,)).fetchone()

        if merch and merch[4] == "banned":
            reason = merch[5] or "مخالفة"
            msg = f"🚫 تم حظر متجرك نهائيا.\nالسبب: {reason}\nتواصل مع الإدارة: {ADMIN_CONTACT}"
            send(chat_id, msg, show_main_keyboard=True)
            return

        if merch and merch[4] == "approved":
            count = db.execute("SELECT COUNT(*) FROM products WHERE merchant_id=? AND status='approved'", (user_id,)).fetchone()[0]

            kb = [
                [{"text": "➕ إضافة منتج", "callback_data": "add"}, {"text": "📊 مبيعاتي", "callback_data": "sales"}],
                [{"text": "🛍️ تصفح السوق", "callback_data": "buyer"}],
                [{"text": "☎️ خدمة العملاء ⭐⭐⭐", "callback_data": "support"}]
            ]

            if user_id == ADMIN_ID:
                kb.append([{"text": "👑 لوحة تحكم الأدمن", "callback_data": "admin_panel"}])

            msg = f"أهلا بك يا صاحب متجر {merch[1]} ✅\n\nمنتجاتك المنشورة: {count}\n\nلو الصفحة علقت دوس 🔄 تحديث تحت 👇"
            send(chat_id, msg, kb, show_main_keyboard=True)
            return

        if merch and merch[4] == "pending":
            msg = f"مرحب بيك 👋\nمتجرك '{merch[1]}' لسه قيد المراجعة ⏳"
            send(chat_id, msg, show_main_keyboard=True)
            return

        if merch and merch[4] in ["rejected_perm", "rejected_temp", "rejected"]:
            reason = merch[5] or "غير محدد"

            kb_reapply = [
                [{"text": "🔄 إعادة التقديم", "callback_data": "merchant"}],
                [{"text": "☎️ تواصل مع الإدارة", "callback_data": "support"}]
            ]

            if merch[4] == "rejected_perm":
                msg = f"❌ تم رفض متجرك نهائيا سابقا.\nالسبب: {reason}\n\nيمكنك التواصل مع الإدارة {ADMIN_CONTACT} أو إعادة التقديم بعد التعديل."
                send(chat_id, msg, kb_reapply, show_main_keyboard=True)
            else:
                msg = f"⏳ تم رفض متجرك مؤقتا.\nالسبب: {reason}\n\nيمكنك التقديم مرة أخرى الآن عبر زر إعادة التقديم."
                send(chat_id, msg, kb_reapply, show_main_keyboard=True)

            return

        kb = [
            [{"text": "🛍️ أنا مشتري - تصفح السوق", "callback_data": "buyer"}, {"text": "🏪 أنا تاجر - افتح متجر", "callback_data": "merchant"}],
            [{"text": "☎️ خدمة العملاء ⭐⭐⭐", "callback_data": "support"}]
        ]

        if user_id == ADMIN_ID:
            kb.append([{"text": "👑 لوحة تحكم الأدمن", "callback_data": "admin_panel"}])

        msg = "أهلا بك في سوق طوّر نفسك 🌟\n\nاختر هل أنت مشتري أم تاجر؟\n\n💡 لو علقت الصفحة دوس زر 🔄 تحديث الصفحة تحت"
        send(chat_id, msg, kb, show_main_keyboard=True)
        return

# ============================================================
# ============== معالجة الأزرار ===============================
# ============================================================

def handle_callback(callback):
    user_id = callback["from"]["id"]
    chat_id = callback["message"]["chat"]["id"]
    message_id = callback["message"]["message_id"]
    data = callback["data"]

    # ================== لوحة الأدمن ==================
    if data == "admin_panel" and user_id == ADMIN_ID:
        total_users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        total_merch = db.execute("SELECT COUNT(*) FROM merchants WHERE status='approved'").fetchone()[0]
        pending_m = db.execute("SELECT COUNT(*) FROM merchants WHERE status='pending'").fetchone()[0]
        rejected = db.execute("SELECT COUNT(*) FROM merchants WHERE status LIKE 'rejected%'").fetchone()[0]
        banned = db.execute("SELECT COUNT(*) FROM users WHERE is_banned=1").fetchone()[0]

        kb = [
            [{"text": f"👥 كل المستخدمين ({total_users})", "callback_data": "admin_users"}],
            [{"text": f"🏪 التجار المقبولين ({total_merch})", "callback_data": "admin_merchants"}],
            [{"text": f"⏳ طلبات معلقة ({pending_m})", "callback_data": "admin_pending"}],
            [{"text": f"❌ المرفوضين ({rejected})", "callback_data": "admin_rejected"}],
            [{"text": f"🚫 المحظورين ({banned})", "callback_data": "admin_banned"}],
            [{"text": "🏠 الرئيسية", "callback_data": "home"}]
        ]

        msg = ""
        msg += "👑 لوحة تحكم الأدمن\n\n"
        msg += f"👥 المستخدمين: {total_users}\n"
        msg += f"🏪 التجار: {total_merch}\n"
        msg += f"⏳ معلق: {pending_m}\n"
        msg += f"❌ مرفوض: {rejected}\n"
        msg += f"🚫 محظور: {banned}"

        edit(chat_id, message_id, msg, kb)
        answer(callback["id"])
        return

    if data == "admin_users" and user_id == ADMIN_ID:
        users = db.execute("SELECT user_id, points, purchases, sales, is_banned FROM users ORDER BY user_id DESC LIMIT 10").fetchall()

        txt = "👥 آخر 10 مستخدمين:\n\n"
        kb = []

        for u in users:
            if u[4] == 1:
                status = "🚫 محظور"
            else:
                status = "✅ نشط"

            txt += f"ID:{u[0]} - نقاط:{u[1]} - شراء:{u[2]} بيع:{u[3]} - {status}\n"

            if u[4] == 1:
                btn_text = f"فك حظر {u[0]}"
            else:
                btn_text = f"حظر {u[0]}"

            kb.append([
                {"text": btn_text, "callback_data": f"admin_toggle_ban:{u[0]}"},
                {"text": f"تفاصيل {u[0]}", "callback_data": f"admin_user_info:{u[0]}"}
            ])

        kb.append([{"text": "🔙 رجوع للوحة الأدمن", "callback_data": "admin_panel"}])

        edit(chat_id, message_id, txt, kb)
        answer(callback["id"])
        return

    if data.startswith("admin_toggle_ban:") and user_id == ADMIN_ID:
        target = int(data.split(":")[1])
        current = db.execute("SELECT is_banned FROM users WHERE user_id=?", (target,)).fetchone()

        if current and current[0] == 1:
            new_val = 0
        else:
            new_val = 1

        db.execute("UPDATE users SET is_banned=? WHERE user_id=?", (new_val, target))

        if new_val == 1:
            db.execute("UPDATE merchants SET status='banned' WHERE user_id=?", (target,))
        else:
            db.execute("UPDATE merchants SET status='approved' WHERE user_id=? AND status='banned'", (target,))

        db.commit()

        if new_val == 1:
            msg = f"🚫 تم حظر المستخدم {target}"
            answer(callback["id"], "تم الحظر")
        else:
            msg = f"✅ تم فك حظر المستخدم {target}"
            answer(callback["id"], "تم فك الحظر")

        edit(chat_id, message_id, msg, [[{"text": "🔙 رجوع", "callback_data": "admin_users"}]])
        return

    if data.startswith("admin_user_info:") and user_id == ADMIN_ID:
        target = int(data.split(":")[1])

        u = db.execute("SELECT points, purchases, sales, referred_by, is_banned FROM users WHERE user_id=?", (target,)).fetchone()
        merch = db.execute("SELECT store_name, phone, city, status, reject_reason FROM merchants WHERE user_id=?", (target,)).fetchone()

        txt = f"👤 تفاصيل المستخدم {target}:\n\n"

        if u:
            txt += f"نقاط: {u[0]}\n"
            txt += f"مشتريات: {u[1]}\n"
            txt += f"مبيعات: {u[2]}\n"
            txt += f"محظور: {'نعم' if u[4]==1 else 'لا'}\n"
        else:
            txt += "لا توجد بيانات\n"

        if merch:
            txt += f"\n🏪 متجر: {merch[0]}\n"
            txt += f"📞 {merch[1]}\n"
            txt += f"📍 {merch[2]}\n"
            txt += f"حالة: {merch[3]}\n"
            txt += f"سبب الرفض: {merch[4] or 'لا يوجد'}"
        else:
            txt += "\nلا يوجد متجر"

        kb = [
            [{"text": "🚫 حظر / فك حظر", "callback_data": f"admin_toggle_ban:{target}"}, {"text": "✅ قبول كتاجر", "callback_data": f"m_ok:{target}"}],
            [{"text": "🔙 رجوع", "callback_data": "admin_users"}]
        ]

        edit(chat_id, message_id, txt, kb)
        answer(callback["id"])
        return

    if data == "admin_merchants" and user_id == ADMIN_ID:
        merchs = db.execute("SELECT user_id, store_name, city FROM merchants WHERE status='approved' ORDER BY user_id DESC LIMIT 10").fetchall()

        txt = "🏪 التجار المقبولين:\n\n"
        kb = []

        for m in merchs:
            txt += f"{m[1]} - {m[2]} - ID:{m[0]}\n"
            kb.append([
                {"text": f"حظر {m[1]}", "callback_data": f"admin_toggle_ban:{m[0]}"},
                {"text": f"رفض {m[0]}", "callback_data": f"m_reject_perm:{m[0]}"}
            ])

        kb.append([{"text": "🔙 رجوع", "callback_data": "admin_panel"}])

        if not merchs:
            txt = "لا يوجد تجار مقبولين"

        edit(chat_id, message_id, txt, kb)
        answer(callback["id"])
        return

    if data == "admin_pending" and user_id == ADMIN_ID:
        pend = db.execute("SELECT user_id, store_name, phone, city FROM merchants WHERE status='pending' LIMIT 5").fetchall()

        if not pend:
            edit(chat_id, message_id, "لا يوجد طلبات معلقة", [[{"text": "🔙 رجوع", "callback_data": "admin_panel"}]])
        else:
            edit(chat_id, message_id, f"⏳ {len(pend)} طلبات معلقة - سيتم عرض أول طلب")

            for m in pend:
                kb = [
                    [{"text": "✅ قبول", "callback_data": f"m_ok:{m[0]}"}],
                    [
                        {"text": "⏳ رفض مؤقت", "callback_data": f"m_reject_temp:{m[0]}"},
                        {"text": "🚫 رفض نهائي", "callback_data": f"m_reject_perm:{m[0]}"}
                    ],
                    [{"text": "🔇 كانسل صامت", "callback_data": f"m_no:{m[0]}"}]
                ]

                msg = f"🔔 تاجر معلق:\n{m[1]}\n{m[2]}\n{m[3]}\nID:{m[0]}"
                send(chat_id, msg, kb)

        answer(callback["id"])
        return

    if data == "admin_rejected" and user_id == ADMIN_ID:
        rej = db.execute("SELECT user_id, store_name, status, reject_reason FROM merchants WHERE status LIKE 'rejected%' LIMIT 10").fetchall()

        txt = "❌ المرفوضين (يمكنك قبولهم تاني):\n\n"
        kb = []

        for r in rej:
            reason_short = (r[3] or "بدون سبب")[:30]
            txt += f"ID:{r[0]} - {r[1]} - {r[2]}\nالسبب: {reason_short}\n\n"

            kb.append([
                {"text": f"✅ قبول {r[0]} تاني", "callback_data": f"m_ok:{r[0]}"},
                {"text": f"🚫 حظر نهائي {r[0]}", "callback_data": f"admin_toggle_ban:{r[0]}"}
            ])

        kb.append([{"text": "🔙 رجوع", "callback_data": "admin_panel"}])

        if not rej:
            txt = "لا يوجد مرفوضين"

        edit(chat_id, message_id, txt, kb)
        answer(callback["id"])
        return

    if data == "admin_banned" and user_id == ADMIN_ID:
        banned = db.execute("SELECT user_id FROM users WHERE is_banned=1 LIMIT 10").fetchall()

        txt = "🚫 المحظورين:\n\n"
        kb = []

        for b in banned:
            txt += f"ID:{b[0]}\n"
            kb.append([{"text": f"✅ فك حظر {b[0]}", "callback_data": f"admin_toggle_ban:{b[0]}"}])

        kb.append([{"text": "🔙 رجوع", "callback_data": "admin_panel"}])

        if not banned:
            txt = "لا يوجد محظورين"

        edit(chat_id, message_id, txt, kb)
        answer(callback["id"])
        return

    # باقي الأزرار
    if data == "buyer":
        kb = get_category_keyboard("browse")
        kb.append([{"text": "🔍 عرض كل المنتجات", "callback_data": "browse:all"}])
        kb.append([{"text": "🏠 الرئيسية", "callback_data": "home"}])
        edit(chat_id, message_id, "🛍️ اختر القسم اللي داير تتصفحو:", kb)
        answer(callback["id"])
        return

    if data.startswith("browse:"):
        cat = data.split(":", 1)[1]

        if cat == "all":
            products = db.execute("SELECT * FROM products WHERE status='approved' ORDER BY id DESC LIMIT 10").fetchall()
            title = "كل المنتجات"
        else:
            products = db.execute("SELECT * FROM products WHERE status='approved' AND category=? ORDER BY id DESC LIMIT 10", (cat,)).fetchall()
            title = f"قسم {cat}"

        if not products:
            edit(chat_id, message_id, f"{title}\n\nما في منتجات 🌙", [[{"text": "🔙 رجوع للأقسام", "callback_data": "buyer"}]])
        else:
            edit(chat_id, message_id, f"{title} - {len(products)} منتج 👇")

            for p in products:
                store = db.execute("SELECT store_name FROM merchants WHERE user_id=?", (p[1],)).fetchone()
                sname = store[0] if store else "متجر"

                kb = [[{"text": f"🛒 شراء - {p[3]} جنيه", "callback_data": f"buy:{p[0]}"}]]

                msg = f"📦 {p[2]}\n💰 {p[3]} جنيه\n🏷️ {p[6]}\n📝 {p[5]}\n🏪 {sname}"
                send(chat_id, msg, kb, photo=p[4])

        answer(callback["id"])
        return

    if data == "merchant":
        merch = db.execute("SELECT * FROM merchants WHERE user_id=?", (user_id,)).fetchone()

        if merch:
            if merch[4] == "pending":
                edit(chat_id, message_id, "طلبك قيد المراجعة، انتظر موافقة الإدارة ⏳")
            elif merch[4] == "approved":
                edit(chat_id, message_id, f"أهلا {merch[1]} ✅", [[{"text": "➕ إضافة منتج", "callback_data": "add"}, {"text": "📊 مبيعاتي", "callback_data": "sales"}]])
            elif merch[4] == "banned":
                edit(chat_id, message_id, f"🚫 تم حظرك نهائيا: {merch[5]}\nتواصل: {ADMIN_CONTACT}")
            else:
                set_state(user_id, "await_store_name", {})
                edit(chat_id, message_id, f"تم رفضك سابقا: {merch[5] or ''}\nيمكنك إعادة التقديم، أرسل اسم المتجر الجديد:")
        else:
            set_state(user_id, "await_store_name", {})
            edit(chat_id, message_id, "لفتح متجر جديد، أرسل اسم المتجر:")

        answer(callback["id"])
        return

    if data.startswith("setcat:"):
        cat = data.split(":", 1)[1]
        tmp = get_temp(user_id)
        tmp["cat"] = cat
        set_state(user_id, "await_prod_desc", tmp)
        edit(chat_id, message_id, f"اخترت قسم {cat} ✅\nالآن أرسل وصف قصير للمنتج:")
        answer(callback["id"])
        return

    if data == "add":
        set_state(user_id, "await_prod_photo", {})
        send(chat_id, "لإضافة منتج جديد، أرسل صورة المنتج أولاً:")
        answer(callback["id"])
        return

    if data == "sales":
        total = db.execute("SELECT COUNT(*) FROM orders WHERE merchant_id=?", (user_id,)).fetchone()[0]
        cnt = db.execute("SELECT COUNT(*) FROM products WHERE merchant_id=? AND status='approved'", (user_id,)).fetchone()[0]
        edit(chat_id, message_id, f"📊 مبيعاتك:\n\n📦 منتجاتك المنشورة: {cnt}\n🛒 إجمالي الطلبات: {total}", [[{"text": "📋 عرض آخر الطلبات", "callback_data": "orders"}, {"text": "🏠 الرئيسية", "callback_data": "home"}]])
        answer(callback["id"])
        return

    if data == "orders":
        orders = db.execute("SELECT * FROM orders WHERE merchant_id=? ORDER BY id DESC LIMIT 5", (user_id,)).fetchall()

        if not orders:
            edit(chat_id, message_id, "لسه ما جاك أي طلب 🌙", [[{"text": "🔙 رجوع", "callback_data": "sales"}]])
        else:
            txt = "📋 آخر 5 طلبات:\n\n"

            for o in orders:
                prod = db.execute("SELECT name FROM products WHERE id=?", (o[2],)).fetchone()
                pname = prod[0] if prod else f"منتج #{o[2]}"
                txt += f"#{o[0]} - {pname}\nالدفع: {o[5]}\nالمشتري: {o[4][:30]}...\n\n"

            edit(chat_id, message_id, txt, [[{"text": "🔙 رجوع", "callback_data": "sales"}]])

        answer(callback["id"])
        return

    if data == "my_account":
        row = db.execute("SELECT points, purchases, sales FROM users WHERE user_id=?", (user_id,)).fetchone()

        points = 0
        purch = 0
        sales_count = 0

        if row:
            points = row[0]
            purch = row[1]
            sales_count = row[2]

        if BOT_USERNAME!= "your_bot":
            ref_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        else:
            ref_link = f"رابطك: /start {user_id}"

        msg = f"📊 حسابك:\n\n🛒 منتجات اشتريتها: {purch}\n📦 منتجات بعتها: {sales_count}\n⭐ نقاط الإحالة: {points}\n\n🔗 رابط الإحالة:\n{ref_link}"

        edit(chat_id, message_id, msg, [[{"text": "🏠 الرئيسية", "callback_data": "home"}]])
        answer(callback["id"])
        return

    if data == "support":
        msg = f"☎️ خدمة العملاء\n\n⭐⭐⭐\n\nللتواصل مع الإدارة:\n{ADMIN_CONTACT}\n\nقريبا بوت تواصل خاص."
        edit(chat_id, message_id, msg, [[{"text": "🏠 الرئيسية", "callback_data": "home"}]])
        answer(callback["id"])
        return

    if data.startswith("buy:"):
        pid = int(data.split(":")[1])
        p = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()

        if not p:
            answer(callback["id"], "المنتج غير موجود")
            return

        set_state(user_id, "choice", {"pid": p[0], "mid": p[1], "price": p[3], "pname": p[2]})

        kb = [
            [{"text": "💵 الدفع عند الاستلام", "callback_data": f"cod:{p[0]}"}],
            [{"text": "💳 الدفع قبل الاستلام", "callback_data": f"pre:{p[0]}"}]
        ]

        send(chat_id, f"📦 {p[2]}\n💰 {p[3]} جنيه\n\nاختر طريقة الدفع:", kb)
        answer(callback["id"])
        return

    if data.startswith("cod:"):
        tmp = get_temp(user_id)
        set_state(user_id, "await_cod", tmp)
        send(chat_id, "💵 اخترت الدفع عند الاستلام\n\nأرسل معلومات التوصيل بهذا الشكل:\nالاسم - رقم الهاتف - العنوان كامل")
        answer(callback["id"])
        return

    if data.startswith("pre:"):
        tmp = get_temp(user_id)
        set_state(user_id, "await_pre", tmp)
        send(chat_id, "💳 اخترت الدفع قبل الاستلام\n\nأرسل رقم هاتفك فقط، وسيقوم البائع بالاتصال بك لتأكيد الطلب.")
        answer(callback["id"])
        return

    # إدارة التجار
    if data.startswith("m_ok:"):
        target_id = int(data.split(":")[1])
        db.execute("UPDATE merchants SET status='approved', reject_reason='' WHERE user_id=?", (target_id,))
        db.commit()
        edit(chat_id, message_id, f"✅ تم قبول التاجر {target_id} - يقدر يسجل تاني عادي لو كان مرفوض")

        try:
            send(target_id, "🎉 مبروك! تم قبول متجرك. الآن /start لإضافة منتجات", show_main_keyboard=True)
        except Exception:
            pass

        answer(callback["id"])
        return

    if data.startswith("m_reject_temp:"):
        target = int(data.split(":")[1])
        set_state(user_id, f"await_reject_reason_temp_m_{target}", {})
        edit(chat_id, message_id, f"⏳ رفض مؤقت للتاجر {target}\nأرسل سبب الرفض (سيقدر يقدم تاني):")
        answer(callback["id"])
        return

    if data.startswith("m_reject_perm:"):
        target = int(data.split(":")[1])
        set_state(user_id, f"await_reject_reason_perm_m_{target}", {})
        edit(chat_id, message_id, f"🚫 رفض نهائي للتاجر {target}\nأرسل سبب الرفض (سيتم إرساله له + زر تواصل):")
        answer(callback["id"])
        return

    if data.startswith("m_no:"):
        target_id = int(data.split(":")[1])
        db.execute("UPDATE merchants SET status='rejected_temp', reject_reason='رفض صامت - كانسل' WHERE user_id=?", (target_id,))
        db.commit()
        edit(chat_id, message_id, f"🔇 تم رفض {target_id} بصمت (كانسل) - يقدر يقدم تاني")
        answer(callback["id"])
        return

    # إدارة المنتجات
    if data.startswith("p_ok:"):
        pid = int(data.split(":")[1])
        db.execute("UPDATE products SET status='approved', reject_reason='' WHERE id=?", (pid,))
        db.commit()

        p = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()

        if p:
            edit(chat_id, message_id, f"✅ تم نشر المنتج: {p[2]}")
        else:
            edit(chat_id, message_id, f"✅ تم نشر المنتج: {pid}")

        if p:
            try:
                send(p[1], f"✅ تم نشر منتجك {p[2]}", show_main_keyboard=True)
            except Exception:
                pass

        answer(callback["id"], "تم النشر ✅")
        return

    if data.startswith("p_reject_temp:"):
        target = int(data.split(":")[1])
        set_state(user_id, f"await_reject_reason_temp_p_{target}", {})
        edit(chat_id, message_id, f"⏳ رفض مؤقت للمنتج {target}\nأرسل سبب الرفض:")
        answer(callback["id"])
        return

    if data.startswith("p_reject_perm:"):
        target = int(data.split(":")[1])
        set_state(user_id, f"await_reject_reason_perm_p_{target}", {})
        edit(chat_id, message_id, f"🚫 رفض نهائي للمنتج {target}\nأرسل سبب الرفض:")
        answer(callback["id"])
        return

    if data.startswith("p_no:"):
        pid = int(data.split(":")[1])
        db.execute("UPDATE products SET status='rejected_temp', reject_reason='كانسل صامت' WHERE id=?", (pid,))
        db.commit()
        edit(chat_id, message_id, f"🔇 تم رفض المنتج {pid} بصمت - كانسل")
        answer(callback["id"])
        return

    if data == "home":
        merch = db.execute("SELECT * FROM merchants WHERE user_id=?", (user_id,)).fetchone()

        if merch and merch[4] == "approved":
            edit(chat_id, message_id, f"🏠 لوحة التاجر {merch[1]}", [[{"text": "➕ إضافة منتج", "callback_data": "add"}, {"text": "📊 مبيعاتي", "callback_data": "sales"}], [{"text": "🛍️ تصفح كمشتري", "callback_data": "buyer"}]])
        else:
            edit(chat_id, message_id, "🏠 الرئيسية\nاختر:", [[{"text": "🛍️ مشتري", "callback_data": "buyer"}, {"text": "🏪 تاجر", "callback_data": "merchant"}]])

        answer(callback["id"])
        return

# ============================================================
# ============== التشغيل الرئيسي ==============================
# ============================================================

def main():
    keep_alive()
    setup_bot_commands()

    offset = 0

    print("Marketplace Bot V7 الكامل 650 سطر يعمل الآن...")

    while True:
        try:
            result = api("getUpdates", {"timeout": 30, "offset": offset})

            for update in result.get("result", []):
                offset = update["update_id"] + 1

                if "message" in update:
                    handle_message(update["message"])
                elif "callback_query" in update:
                    handle_callback(update["callback_query"])

        except Exception as e:
            print(f"خطأ في main loop: {e}")
            time.sleep(2)

if __name__ == "__main__":
    main()
