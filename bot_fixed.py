from keep_alive import keep_alive
import os
import json
import time
import sqlite3
from urllib.request import Request, urlopen
from urllib.parse import urlencode

# =========================================================
# الإعدادات الأساسية
# =========================================================
TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
BOT_USERNAME = os.environ.get("BOT_USERNAME", "your_bot")

if not TOKEN:
    raise SystemExit("BOT_TOKEN غير موجود - تأكد من Environment Variables")

API = f"https://api.telegram.org/bot{TOKEN}"
DB = "marketplace.db"

# الأقسام المطلوبة
CATEGORIES = [
    "👕 ملابس",
    "🍳 أواني منزلية",
    "🔥 عروض وخصم",
    "⭐ رائج",
    "👗 موضة",
    "📦 أخرى"
]

# =========================================================
# قاعدة البيانات
# =========================================================
db = sqlite3.connect(DB, check_same_thread=False)

db.executescript("""
CREATE TABLE IF NOT EXISTS users(
    user_id INTEGER PRIMARY KEY,
    state TEXT,
    temp TEXT,
    points INTEGER DEFAULT 0,
    purchases INTEGER DEFAULT 0,
    sales INTEGER DEFAULT 0,
    referred_by INTEGER
);

CREATE TABLE IF NOT EXISTS merchants(
    user_id INTEGER PRIMARY KEY,
    store_name TEXT,
    phone TEXT,
    city TEXT,
    status TEXT DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS products(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    merchant_id INTEGER,
    name TEXT,
    price INTEGER,
    photo_id TEXT,
    description TEXT,
    category TEXT,
    status TEXT DEFAULT 'pending'
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
db.commit()

# =========================================================
# دوال الاتصال بتليجرام
# =========================================================
def api(method, data=None):
    data = data or {}
    try:
        req = Request(
            API + "/" + method,
            data=urlencode(data).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        with urlopen(req, timeout=30) as response:
            return json.loads(response.read())
    except Exception as e:
        print(f"API Error {method}: {e}")
        return {}

def send(chat_id, text, inline_keyboard=None, photo=None, show_main_keyboard=False):
    """
    إرسال رسالة
    show_main_keyboard = True يظهر زر التحديث المقترح
    """
    if photo:
        payload = {
            "chat_id": chat_id,
            "photo": photo,
            "caption": text
        }
        if inline_keyboard:
            payload["reply_markup"] = json.dumps(
                {"inline_keyboard": inline_keyboard},
                ensure_ascii=False
            )
        return api("sendPhoto", payload)
    else:
        payload = {
            "chat_id": chat_id,
            "text": text
        }
        if inline_keyboard:
            payload["reply_markup"] = json.dumps(
                {"inline_keyboard": inline_keyboard},
                ensure_ascii=False
            )
        elif show_main_keyboard:
            # هذا هو زر start المقترح
            payload["reply_markup"] = json.dumps(
                {
                    "keyboard": [
                        ["🔄 تحديث الصفحة /start"],
                        ["📊 حسابي ونقاطي"]
                    ],
                    "resize_keyboard": True
                },
                ensure_ascii=False
            )
        return api("sendMessage", payload)

def edit(chat_id, message_id, text, inline_keyboard=None):
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text
    }
    if inline_keyboard:
        payload["reply_markup"] = json.dumps(
            {"inline_keyboard": inline_keyboard},
            ensure_ascii=False
        )
    try:
        return api("editMessageText", payload)
    except:
        payload2 = {
            "chat_id": chat_id,
            "message_id": message_id,
            "caption": text
        }
        if inline_keyboard:
            payload2["reply_markup"] = json.dumps(
                {"inline_keyboard": inline_keyboard},
                ensure_ascii=False
            )
        try:
            return api("editMessageCaption", payload2)
        except Exception as e:
            print(f"فشل التعديل: {e}")
            return None

def answer(callback_query_id, text=""):
    return api("answerCallbackQuery", {
        "callback_query_id": callback_query_id,
        "text": text
    })

# =========================================================
# دوال المستخدم
# =========================================================
def get_temp(user_id):
    row = db.execute("SELECT temp FROM users WHERE user_id=?", (user_id,)).fetchone()
    if row and row[0]:
        try:
            return json.loads(row[0])
        except:
            return {}
    return {}

def set_state(user_id, state, temp_data=None):
    db.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (user_id,))
    if temp_data is not None:
        db.execute(
            "UPDATE users SET state=?, temp=? WHERE user_id=?",
            (state, json.dumps(temp_data, ensure_ascii=False), user_id)
        )
    else:
        db.execute("UPDATE users SET state=? WHERE user_id=?", (state, user_id))
    db.commit()

def get_state(user_id):
    row = db.execute("SELECT state FROM users WHERE user_id=?", (user_id,)).fetchone()
    return row[0] if row else None

def get_category_keyboard(prefix):
    keyboard = []
    for i in range(0, len(CATEGORIES), 2):
        row = [
            {"text": CATEGORIES[i], "callback_data": f"{prefix}:{CATEGORIES[i]}"}
        ]
        if i + 1 < len(CATEGORIES):
            row.append(
                {"text": CATEGORIES[i+1], "callback_data": f"{prefix}:{CATEGORIES[i+1]}"}
            )
        keyboard.append(row)
    return keyboard

def setup_bot_commands():
    try:
        commands = json.dumps([
            {"command": "start", "description": "🏠 الرئيسية - تحديث الصفحة"}
        ], ensure_ascii=False)
        api("setMyCommands", {"commands": commands})
        print("تم ضبط أمر /start المقترح")
    except Exception as e:
        print(f"خطأ في setup commands: {e}")

# =========================================================
# معالجة الرسائل النصية
# =========================================================
def handle_message(message):
    user_id = message["from"]["id"]
    chat_id = message["chat"]["id"]
    text = message.get("text", "")

    state = get_state(user_id)
    temp = get_temp(user_id)

    db.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (user_id,))
    db.commit()

    # زر التحديث المقترح
    if text in ["🔄 تحديث الصفحة /start", "🔄 تحديث الصفحة", "تحديث", "📊 حسابي ونقاطي"]:
        if "تحديث" in text:
            text = "/start"
        elif "حسابي" in text:
            row = db.execute("SELECT points,purchases,sales FROM users WHERE user_id=?", (user_id,)).fetchone()
            points = row[0] if row else 0
            purch = row[1] if row else 0
            sales_count = row[2] if row else 0
            ref_link = f"https://t.me/{BOT_USERNAME}?start={user_id}" if BOT_USERNAME!= "your_bot" else f"رابطك: /start {user_id}"
            msg = f"📊 حسابك:\n\n🛒 منتجات اشتريتها: {purch}\n📦 منتجات بعتها: {sales_count}\n⭐ نقاط الإحالة: {points}\n\n🔗 رابط الإحالة:\n{ref_link}\n\nكل إحالة = 10 نقاط 🎁"
            send(chat_id, msg, show_main_keyboard=True)
            return

    # حالات رفض بتعليق
    if state and state.startswith("await_reject_reason_"):
        reason = text
        parts = state.split("_")
        typ = parts[-2]
        target_id = int(parts[-1])

        if typ == "m":
            db.execute("UPDATE merchants SET status='rejected' WHERE user_id=?", (target_id,))
            db.commit()
            send(chat_id, f"✅ تم رفض التاجر {target_id} مع إرسال السبب.")
            try:
                send(target_id, f"❌ تم رفض متجرك للسبب التالي:\n\n{reason}\n\nيمكنك التعديل وإعادة التقديم.", show_main_keyboard=True)
            except:
                pass
        else:
            db.execute("UPDATE products SET status='rejected' WHERE id=?", (target_id,))
            db.commit()
            prod = db.execute("SELECT merchant_id, name FROM products WHERE id=?", (target_id,)).fetchone()
            send(chat_id, f"✅ تم رفض المنتج {target_id} مع إرسال السبب.")
            if prod:
                try:
                    send(prod[0], f"❌ تم رفض منتجك '{prod[1]}' للسبب:\n\n{reason}", show_main_keyboard=True)
                except:
                    pass

        set_state(user_id, None, {})
        return

    # تسجيل التاجر
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
                [{"text": "✅ موافقة", "callback_data": f"m_ok:{user_id}"}],
                [
                    {"text": "❌ رفض بتعليق", "callback_data": f"m_reject:{user_id}"},
                    {"text": "🔇 كانسل (صامت)", "callback_data": f"m_no:{user_id}"}
                ]
            ]
            send(ADMIN_ID, f"🔔 تاجر جديد بانتظار الموافقة:\n\nالمتجر: {temp['store_name']}\nالهاتف: {temp['phone']}\nالمدينة: {temp['city']}\nالايدي: {user_id}", kb)
        return

    # إضافة منتج
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
                [{"text": "✅ موافقة ونشر", "callback_data": f"p_ok:{product_id}"}],
                [
                    {"text": "❌ رفض بتعليق", "callback_data": f"p_reject:{product_id}"},
                    {"text": "🔇 كانسل", "callback_data": f"p_no:{product_id}"}
                ]
            ]
            send(ADMIN_ID, f"🔔 منتج جديد بانتظار الموافقة:\n📦 {temp['name']} - {temp['price']} جنيه\n🏷️ القسم: {temp.get('cat')}\n📝 {temp['desc']}", kb, photo=temp["photo"])
        return

    # نظام الدفع
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
            send(temp["mid"], f"🔔 طلب جديد #{order_id} - دفع عند الاستلام 💵\n\n📦 المنتج: {temp['pname']}\n💰 السعر: {temp['price']} جنيه\n👤 بيانات المشتري: {text}\n\nتواصل مع المشتري فورا!")
        except:
            pass
        return

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
        send(chat_id, f"✅ تمام! تم حفظ طلبك #{order_id}\n\n💳 طريقة الدفع: قبل الاستلام\n📞 رقمك: {text}\n\nالبائع سوف يتصل بك خلال دقائق لتأكيد الطلب.", show_main_keyboard=True)
        try:
            send(temp["mid"], f"🔔 طلب جديد #{order_id} - دفع قبل الاستلام 💳\n\n📦 المنتج: {temp['pname']}\n💰 السعر: {temp['price']} جنيه\n📞 رقم المشتري: {text}\n\n⚠️ اتصل بالمشتري الآن!")
        except:
            pass
        return

    if "photo" in message and state == "await_prod_photo":
        photo_id = message["photo"][-1]["file_id"]
        temp["photo"] = photo_id
        set_state(user_id, "await_prod_name", temp)
        send(chat_id, "الصورة وصلت ✅\nالآن أرسل اسم المنتج:")
        return

    # أمر البداية مع الإحالة
    if text.startswith("/start"):
        parts = text.split()
        if len(parts) > 1 and parts[1].isdigit():
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
                        current_points = db.execute("SELECT points FROM users WHERE user_id=?", (ref_id,)).fetchone()[0]
                        send(ref_id, f"🎉 مبروك! شخص جديد سجل برابطك وحصلت على 10 نقاط!\n⭐ نقاطك الآن: {current_points}")
                    except:
                        pass

        merch = db.execute("SELECT * FROM merchants WHERE user_id=?", (user_id,)).fetchone()
        if merch and merch[4] == "approved":
            count = db.execute("SELECT COUNT(*) FROM products WHERE merchant_id=? AND status='approved'", (user_id,)).fetchone()[0]
            kb = [
                [{"text": "➕ إضافة منتج", "callback_data": "add"}, {"text": "📊 مبيعاتي", "callback_data": "sales"}],
                [{"text": "🛍️ تصفح السوق", "callback_data": "buyer"}],
                [{"text": "📊 حسابي ونقاطي", "callback_data": "my_account"}]
            ]
            send(chat_id, f"أهلا بك يا صاحب متجر {merch[1]} ✅\n\nمنتجاتك المنشورة: {count}\n\nلو الصفحة علقت دوس 🔄 تحديث تحت 👇", kb, show_main_keyboard=True)
            return

        if merch and merch[4] == "pending":
            send(chat_id, f"مرحب بيك 👋\nمتجرك '{merch[1]}' لسه قيد المراجعة ⏳", show_main_keyboard=True)
            return

        kb = [
            [{"text": "🛍️ أنا مشتري - تصفح السوق", "callback_data": "buyer"}, {"text": "🏪 أنا تاجر - افتح متجر", "callback_data": "merchant"}],
            [{"text": "📊 حسابي ونقاطي", "callback_data": "my_account"}]
        ]
        send(chat_id, "أهلا بك في سوق طوّر نفسك 🌟\n\nاختر هل أنت مشتري أم تاجر؟\n\n💡 لو علقت الصفحة دوس زر 🔄 تحديث الصفحة تحت", kb, show_main_keyboard=True)
        return

# =========================================================
# معالجة الأزرار
# =========================================================
def handle_callback(callback):
    user_id = callback["from"]["id"]
    chat_id = callback["message"]["chat"]["id"]
    message_id = callback["message"]["message_id"]
    data = callback["data"]

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
            products = db.execute("SELECT * FROM products WHERE status='approved' ORDER BY id DESC LIMIT 15").fetchall()
            title = "كل المنتجات 🛍️"
        else:
            products = db.execute("SELECT * FROM products WHERE status='approved' AND category=? ORDER BY id DESC LIMIT 15", (cat,)).fetchall()
            title = f"قسم {cat}"

        if not products:
            edit(chat_id, message_id, f"{title}\n\nلسه ما في منتجات في القسم دا 🌙", [[{"text": "🔙 رجوع للأقسام", "callback_data": "buyer"}]])
        else:
            edit(chat_id, message_id, f"{title} - {len(products)} منتج 👇")
            for p in products[:10]:
                merch = db.execute("SELECT store_name FROM merchants WHERE user_id=?", (p[1],)).fetchone()
                store_name = merch[0] if merch else "متجر"
                kb = [[{"text": f"🛒 شراء - {p[3]} جنيه", "callback_data": f"buy:{p[0]}"}]]
                send(chat_id, f"📦 {p[2]}\n💰 {p[3]} جنيه\n🏷️ {p[6]}\n📝 {p[5]}\n🏪 {store_name}", kb, photo=p[4])
        answer(callback["id"])
        return

    if data == "merchant":
        merch = db.execute("SELECT * FROM merchants WHERE user_id=?", (user_id,)).fetchone()
        if merch:
            if merch[4] == "pending":
                edit(chat_id, message_id, "طلبك قيد المراجعة، انتظر موافقة الإدارة ⏳", [[{"text": "🏠 الرئيسية", "callback_data": "home"}]])
            elif merch[4] == "approved":
                count = db.execute("SELECT COUNT(*) FROM products WHERE merchant_id=? AND status='approved'", (user_id,)).fetchone()[0]
                edit(chat_id, message_id, f"أهلا بك يا صاحب متجر {merch[1]} ✅\n\nمنتجاتك: {count}", [[{"text": "➕ إضافة منتج", "callback_data": "add"}, {"text": "📊 مبيعاتي", "callback_data": "sales"}]])
            else:
                edit(chat_id, message_id, "تم رفض متجرك، تواصل مع الإدارة.", [[{"text": "🏠 الرئيسية", "callback_data": "home"}]])
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
        edit(chat_id, message_id, f"اخترت قسم {cat} ✅\n\nالآن أرسل وصف قصير للمنتج:")
        answer(callback["id"])
        return

    if data == "add":
        set_state(user_id, "await_prod_photo", {})
        send(chat_id, "لإضافة منتج جديد، أرسل صورة المنتج أولاً:")
        answer(callback["id"])
        return

    if data == "sales":
        total = db.execute("SELECT COUNT(*) FROM orders WHERE merchant_id=?", (user_id,)).fetchone()[0]
        conf = db.execute("SELECT COUNT(*) FROM orders WHERE merchant_id=? AND status='confirmed'", (user_id,)).fetchone()[0]
        pend = db.execute("SELECT COUNT(*) FROM orders WHERE merchant_id=? AND status LIKE 'pending%'", (user_id,)).fetchone()[0]
        cnt = db.execute("SELECT COUNT(*) FROM products WHERE merchant_id=? AND status='approved'", (user_id,)).fetchone()[0]
        edit(chat_id, message_id, f"📊 مبيعاتك يا صاحب المتجر:\n\n📦 منتجاتك المنشورة: {cnt}\n🛒 إجمالي الطلبات: {total}\n✅ طلبات مؤكدة: {conf}\n⏳ بانتظار: {pend}", [[{"text": "📋 عرض آخر الطلبات", "callback_data": "orders"}, {"text": "🏠 الرئيسية", "callback_data": "home"}]])
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
                emoji = "✅" if o[6] == "confirmed" else "⏳"
                txt += f"{emoji} #{o[0]} - {pname}\nالدفع: {o[5]}\nالمشتري: {o[4][:30]}...\n\n"
            edit(chat_id, message_id, txt, [[{"text": "🔙 رجوع", "callback_data": "sales"}]])
        answer(callback["id"])
        return

    if data == "my_account":
        row = db.execute("SELECT points,purchases,sales FROM users WHERE user_id=?", (user_id,)).fetchone()
        points = row[0] if row else 0
        purch = row[1] if row else 0
        sales_count = row[2] if row else 0
        ref_link = f"https://t.me/{BOT_USERNAME}?start={user_id}" if BOT_USERNAME!= "your_bot" else f"رابطك: /start {user_id}"
        edit(chat_id, message_id, f"📊 حسابك:\n\n🛒 منتجات اشتريتها: {purch}\n📦 منتجات بعتها: {sales_count}\n⭐ نقاط الإحالة: {points}\n\n🔗 رابط الإحالة الخاص بك:\n{ref_link}\n\nكل شخص يسجل برابطك تاخد 10 نقاط!\nقريبا حنضيف متجر نقاط وعروض 🎁", [[{"text": "🏠 الرئيسية", "callback_data": "home"}]])
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
        send(chat_id, "💵 اخترت الدفع عند الاستلام\n\nأرسل معلومات التوصيل بهذا الشكل:\nالاسم - رقم الهاتف - العنوان كامل\n\nمثال: محمد 0912345678 الخرطوم بحري شارع...")
        answer(callback["id"])
        return

    if data.startswith("pre:"):
        tmp = get_temp(user_id)
        set_state(user_id, "await_pre", tmp)
        send(chat_id, "💳 اخترت الدفع قبل الاستلام\n\nأرسل رقم هاتفك فقط، وسيقوم البائع بالاتصال بك لتأكيد الطلب وطريقة التحويل (بنكك).\n\nمثال: 0912345678")
        answer(callback["id"])
        return

    # نظام الإدارة الجديد - موافقة / رفض بتعليق / كانسل
    if data.startswith("m_ok:"):
        target_id = int(data.split(":")[1])
        db.execute("UPDATE merchants SET status='approved' WHERE user_id=?", (target_id,))
        db.commit()
        edit(chat_id, message_id, f"تم قبول التاجر {target_id} ✅")
        try:
            send(target_id, "🎉 مبروك! تم قبول متجرك. الآن /start لإضافة منتجات", show_main_keyboard=True)
        except:
            pass
        answer(callback["id"], "تم القبول")
        return

    if data.startswith("m_reject:"):
        target_id = int(data.split(":")[1])
        set_state(user_id, f"await_reject_reason_m_{target_id}", {})
        edit(chat_id, message_id, f"✍️ أرسل سبب رفض التاجر {target_id}:\nسيتم إرساله للمستخدم.")
        answer(callback["id"])
        return

    if data.startswith("m_no:"):
        target_id = int(data.split(":")[1])
        db.execute("UPDATE merchants SET status='rejected' WHERE user_id=?", (target_id,))
        db.commit()
        edit(chat_id, message_id, f"🔇 تم رفض التاجر {target_id} بصمت (ما وصلتو رسالة) - كانسل")
        answer(callback["id"])
        return

    if data.startswith("p_ok:"):
        pid = int(data.split(":")[1])
        db.execute("UPDATE products SET status='approved' WHERE id=?", (pid,))
        db.commit()
        p = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
        edit(chat_id, message_id, f"✅ تم نشر المنتج: {p[2] if p else pid}")
        if p:
            try:
                send(p[1], f"✅ تم قبول منتجك {p[2]} ونشره في السوق", show_main_keyboard=True)
            except:
                pass
        answer(callback["id"], "تم النشر ✅")
        return

    if data.startswith("p_reject:"):
        target_id = int(data.split(":")[1])
        set_state(user_id, f"await_reject_reason_p_{target_id}", {})
        edit(chat_id, message_id, f"✍️ أرسل سبب رفض المنتج {target_id}:\nسيتم إرساله للتاجر.")
        answer(callback["id"])
        return

    if data.startswith("p_no:"):
        pid = int(data.split(":")[1])
        db.execute("UPDATE products SET status='rejected' WHERE id=?", (pid,))
        db.commit()
        edit(chat_id, message_id, f"🔇 تم رفض المنتج {pid} بصمت - ما وصلت رسالة للمستخدم (كانسل)")
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

# =========================================================
# التشغيل الرئيسي
# =========================================================
def main():
    keep_alive()
    setup_bot_commands()
    offset = 0
    print("Marketplace Bot V6 الكامل يعمل - 450 سطر...")
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
