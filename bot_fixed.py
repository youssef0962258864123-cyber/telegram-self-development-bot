from keep_alive import keep_alive
import os
import json
import time
import sqlite3
from urllib.request import Request, urlopen
from urllib.parse import urlencode

# ================== الإعدادات ==================
TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

if not TOKEN:
    raise SystemExit("BOT_TOKEN غير موجود")

API = f"https://api.telegram.org/bot{TOKEN}"
DB = "marketplace.db"

# الأقسام الجديدة حسب طلبك
CATEGORIES = [
    "👕 ملابس",
    "🍳 أواني منزلية",
    "🔥 عروض وخصم",
    "⭐ رائج",
    "👗 موضة",
    "📦 أخرى"
]

# ================== قاعدة البيانات ==================
db = sqlite3.connect(DB, check_same_thread=False)

# إنشاء الجداول
db.executescript("""
CREATE TABLE IF NOT EXISTS users(
    user_id INTEGER PRIMARY KEY,
    state TEXT,
    temp TEXT
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
""")
db.commit()

# ================== دوال التليجرام ==================
def api(method, data=None):
    data = data or {}
    req = Request(
        API + "/" + method,
        data=urlencode(data).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    with urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def send(chat, text, kb=None, photo=None):
    """إرسال رسالة أو صورة"""
    if photo:
        d = {"chat_id": chat, "photo": photo, "caption": text}
        if kb:
            d["reply_markup"] = json.dumps({"inline_keyboard": kb}, ensure_ascii=False)
        return api("sendPhoto", d)
    else:
        d = {"chat_id": chat, "text": text}
        if kb:
            d["reply_markup"] = json.dumps({"inline_keyboard": kb}, ensure_ascii=False)
        return api("sendMessage", d)

def edit(chat, msg, text, kb=None):
    """تعديل رسالة (نص أو صورة)"""
    d = {"chat_id": chat, "message_id": msg, "text": text}
    if kb:
        d["reply_markup"] = json.dumps({"inline_keyboard": kb}, ensure_ascii=False)
    try:
        return api("editMessageText", d)
    except:
        # لو الرسالة صورة، نعدل الكابشن
        d2 = {"chat_id": chat, "message_id": msg, "caption": text}
        if kb:
            d2["reply_markup"] = json.dumps({"inline_keyboard": kb}, ensure_ascii=False)
        try:
            return api("editMessageCaption", d2)
        except Exception as e:
            print(f"فشل التعديل: {e}")
            return None

def answer(cid, text=""):
    return api("answerCallbackQuery", {"callback_query_id": cid, "text": text})

# ================== دوال المستخدمين ==================
def get_temp(uid):
    row = db.execute("SELECT temp FROM users WHERE user_id=?", (uid,)).fetchone()
    if row and row[0]:
        try:
            return json.loads(row[0])
        except:
            return {}
    return {}

def set_state(uid, state, temp=None):
    db.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (uid,))
    if temp is not None:
        db.execute(
            "UPDATE users SET state=?, temp=? WHERE user_id=?",
            (state, json.dumps(temp, ensure_ascii=False), uid)
        )
    else:
        db.execute("UPDATE users SET state=? WHERE user_id=?", (state, uid))
    db.commit()

def get_state(uid):
    row = db.execute("SELECT state FROM users WHERE user_id=?", (uid,)).fetchone()
    return row[0] if row else None

def get_category_keyboard(prefix):
    """كيبورد الأقسام"""
    kb = []
    for i in range(0, len(CATEGORIES), 2):
        row = [{"text": CATEGORIES[i], "callback_data": f"{prefix}:{CATEGORIES[i]}"}]
        if i+1 < len(CATEGORIES):
            row.append({"text": CATEGORIES[i+1], "callback_data": f"{prefix}:{CATEGORIES[i+1]}"})
        kb.append(row)
    return kb

# ================== معالجة الرسائل ==================
def handle_message(m):
    uid = m["from"]["id"]
    chat = m["chat"]["id"]
    text = m.get("text", "")
    state = get_state(uid)
    temp = get_temp(uid)

    db.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (uid,))
    db.commit()

    # --- تسجيل التاجر ---
    if state == "await_store_name":
        temp["store_name"] = text
        set_state(uid, "await_phone", temp)
        send(chat, "تمام ✅\nالآن أرسل رقم واتساب المتجر:")
        return

    if state == "await_phone":
        temp["phone"] = text
        set_state(uid, "await_city", temp)
        send(chat, "آخر خطوة، أرسل مدينتك / ولايتك:")
        return

    if state == "await_city":
        temp["city"] = text
        db.execute(
            "INSERT OR REPLACE INTO merchants(user_id, store_name, phone, city, status) VALUES(?,?,?,?,?)",
            (uid, temp["store_name"], temp["phone"], temp["city"], "pending")
        )
        db.commit()
        set_state(uid, None, {})
        send(chat, "✅ تم إرسال طلبك للإدارة، سيتم مراجعته خلال ساعات.")
        if ADMIN_ID:
            kb = [[{"text": "✅ قبول التاجر", "callback_data": f"m_ok:{uid}"}, {"text": "❌ رفض", "callback_data": f"m_no:{uid}"}]]
            send(ADMIN_ID, f"🔔 تاجر جديد بانتظار الموافقة:\n\nالمتجر: {temp['store_name']}\nالهاتف: {temp['phone']}\nالمدينة: {temp['city']}\nالايدي: {uid}", kb)
        return

    # --- إضافة منتج ---
    if state == "await_prod_name":
        temp["name"] = text
        set_state(uid, "await_prod_price", temp)
        send(chat, "حلو، الآن أرسل السعر بالأرقام فقط (مثلا 15000):")
        return

    if state == "await_prod_price":
        if not text.isdigit():
            send(chat, "أرسل السعر أرقام فقط:")
            return
        temp["price"] = int(text)
        set_state(uid, "await_prod_cat", temp)
        send(chat, "ممتاز، الآن اختر قسم المنتج:", get_category_keyboard("setcat"))
        return

    if state == "await_prod_desc":
        temp["desc"] = text
        db.execute(
            "INSERT INTO products(merchant_id, name, price, photo_id, description, category, status) VALUES(?,?,?,?,?,?,?)",
            (uid, temp["name"], temp["price"], temp["photo"], temp["desc"], temp.get("cat", "📦 أخرى"), "pending")
        )
        db.commit()
        pid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        set_state(uid, None, {})
        send(chat, f"✅ تم رفع المنتج في قسم {temp.get('cat')}، بانتظار موافقة الإدارة.")
        if ADMIN_ID:
            kb = [[{"text": "✅ نشر المنتج", "callback_data": f"p_ok:{pid}"}, {"text": "❌ رفض", "callback_data": f"p_no:{pid}"}]]
            send(ADMIN_ID, f"🔔 منتج جديد بانتظار الموافقة:\n📦 {temp['name']} - {temp['price']} جنيه\n🏷️ القسم: {temp.get('cat')}\n📝 {temp['desc']}", kb, photo=temp["photo"])
        return

    # --- نظام الدفع الجديد ---
    if state == "await_cod":
        db.execute(
            "INSERT INTO orders(buyer_id, product_id, merchant_id, buyer_info, payment_type, status) VALUES(?,?,?,?,?,?)",
            (uid, temp["pid"], temp["mid"], text, "عند الاستلام", "confirmed")
        )
        db.commit()
        oid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        set_state(uid, None, {})
        send(chat, f"✅ تم تأكيد طلبك #{oid} بنجاح!\n\n💵 طريقة الدفع: عند الاستلام\n📦 المنتج: {temp['pname']}\n\nسيتواصل معك البائع قريبا للتوصيل. شكرا 🙏")
        send(temp["mid"], f"🔔 طلب جديد #{oid} - دفع عند الاستلام 💵\n\n📦 المنتج: {temp['pname']}\n💰 السعر: {temp['price']} جنيه\n👤 بيانات المشتري: {text}\n\nتواصل مع المشتري فورا!")
        return

    if state == "await_pre":
        info = f"رقم الهاتف: {text}"
        db.execute(
            "INSERT INTO orders(buyer_id, product_id, merchant_id, buyer_info, payment_type, status) VALUES(?,?,?,?,?,?)",
            (uid, temp["pid"], temp["mid"], info, "قبل الاستلام", "pending_call")
        )
        db.commit()
        oid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        set_state(uid, None, {})
        send(chat, f"✅ تمام! تم حفظ طلبك #{oid}\n\n💳 طريقة الدفع: قبل الاستلام\n📞 رقمك: {text}\n\nالبائع سوف يتصل بك خلال دقائق لتأكيد الطلب.")
        send(temp["mid"], f"🔔 طلب جديد #{oid} - دفع قبل الاستلام 💳\n\n📦 المنتج: {temp['pname']}\n💰 السعر: {temp['price']} جنيه\n📞 رقم المشتري: {text}\n\n⚠️ اتصل بالمشتري الآن!")
        return

    if "photo" in m and state == "await_prod_photo":
        temp["photo"] = m["photo"][-1]["file_id"]
        set_state(uid, "await_prod_name", temp)
        send(chat, "الصورة وصلت ✅\nالآن أرسل اسم المنتج:")
        return

    # --- أوامر ---
    if text.startswith("/start"):
        merch = db.execute("SELECT * FROM merchants WHERE user_id=?", (uid,)).fetchone()
        if merch and merch[4] == "approved":
            cnt = db.execute("SELECT COUNT(*) FROM products WHERE merchant_id=? AND status='approved'", (uid,)).fetchone()[0]
            kb = [[{"text": "➕ إضافة منتج", "callback_data": "add"}, {"text": "📊 مبيعاتي", "callback_data": "sales"}], [{"text": "🛍️ تصفح السوق", "callback_data": "buyer"}]]
            send(chat, f"أهلا بك يا صاحب متجر {merch[1]} ✅\n\nمنتجاتك المنشورة: {cnt}\n\nلإضافة منتج جديد دوس الزر تحت 👇", kb)
            return
        if merch and merch[4] == "pending":
            send(chat, f"مرحب بيك 👋\nمتجرك '{merch[1]}' لسه قيد المراجعة ⏳")
            return
        kb = [[{"text": "🛍️ أنا مشتري - تصفح السوق", "callback_data": "buyer"}, {"text": "🏪 أنا تاجر - افتح متجر", "callback_data": "merchant"}]]
        send(chat, "أهلا بك في سوق طوّر نفسك 🌟\n\nاختر هل أنت مشتري أم تاجر؟", kb)
        return

# ================== معالجة الأزرار ==================
def handle_callback(c):
    uid = c["from"]["id"]
    chat = c["message"]["chat"]["id"]
    mid = c["message"]["message_id"]
    data = c["data"]

    if data == "buyer":
        kb = get_category_keyboard("browse")
        kb.append([{"text": "🔍 عرض كل المنتجات", "callback_data": "browse:all"}])
        kb.append([{"text": "🏠 الرئيسية", "callback_data": "home"}])
        edit(chat, mid, "🛍️ اختر القسم اللي داير تتصفحو:", kb)
        answer(c["id"])
        return

    if data.startswith("browse:"):
        cat = data.split(":", 1)[1]
        if cat == "all":
            prods = db.execute("SELECT * FROM products WHERE status='approved' ORDER BY id DESC LIMIT 10").fetchall()
            title = "كل المنتجات 🛍️"
        else:
            prods = db.execute("SELECT * FROM products WHERE status='approved' AND category=? ORDER BY id DESC LIMIT 10", (cat,)).fetchall()
            title = f"قسم {cat}"
        if not prods:
            edit(chat, mid, f"{title}\n\nلسه ما في منتجات في القسم دا 🌙", [[{"text": "🔙 رجوع للأقسام", "callback_data": "buyer"}]])
        else:
            edit(chat, mid, f"{title} - {len(prods)} منتج 👇")
            for p in prods[:10]:
                store = db.execute("SELECT store_name FROM merchants WHERE user_id=?", (p[1],)).fetchone()
                sname = store[0] if store else "متجر"
                kb = [[{"text": f"🛒 شراء - {p[3]} جنيه", "callback_data": f"buy:{p[0]}"}]]
                send(chat, f"📦 {p[2]}\n💰 {p[3]} جنيه\n🏷️ {p[6]}\n📝 {p[5]}\n🏪 {sname}", kb, photo=p[4])
        answer(c["id"])
        return

    if data == "merchant":
        merch = db.execute("SELECT * FROM merchants WHERE user_id=?", (uid,)).fetchone()
        if merch:
            if merch[4] == "pending":
                edit(chat, mid, "طلبك قيد المراجعة، انتظر موافقة الإدارة ⏳", [[{"text": "🏠 الرئيسية", "callback_data": "home"}]])
            elif merch[4] == "approved":
                cnt = db.execute("SELECT COUNT(*) FROM products WHERE merchant_id=? AND status='approved'", (uid,)).fetchone()[0]
                edit(chat, mid, f"أهلا بك يا صاحب متجر {merch[1]} ✅\n\nمنتجاتك: {cnt}", [[{"text": "➕ إضافة منتج", "callback_data": "add"}, {"text": "📊 مبيعاتي", "callback_data": "sales"}]])
            else:
                edit(chat, mid, "تم رفض متجرك، تواصل مع الإدارة.", [[{"text": "🏠 الرئيسية", "callback_data": "home"}]])
        else:
            set_state(uid, "await_store_name", {})
            edit(chat, mid, "لفتح متجر جديد، أرسل اسم المتجر:")
        answer(c["id"])
        return

    if data.startswith("setcat:"):
        cat = data.split(":", 1)[1]
        tmp = get_temp(uid)
        tmp["cat"] = cat
        set_state(uid, "await_prod_desc", tmp)
        edit(chat, mid, f"اخترت قسم {cat} ✅\n\nالآن أرسل وصف قصير للمنتج:")
        answer(c["id"])
        return

    if data == "add":
        set_state(uid, "await_prod_photo", {})
        send(chat, "لإضافة منتج جديد، أرسل صورة المنتج أولاً:")
        answer(c["id"])
        return

    if data == "sales":
        total = db.execute("SELECT COUNT(*) FROM orders WHERE merchant_id=?", (uid,)).fetchone()[0]
        conf = db.execute("SELECT COUNT(*) FROM orders WHERE merchant_id=? AND status='confirmed'", (uid,)).fetchone()[0]
        pend = db.execute("SELECT COUNT(*) FROM orders WHERE merchant_id=? AND status LIKE 'pending%'", (uid,)).fetchone()[0]
        cnt = db.execute("SELECT COUNT(*) FROM products WHERE merchant_id=? AND status='approved'", (uid,)).fetchone()[0]
        rows = db.execute("SELECT p.price FROM orders o JOIN products p ON o.product_id=p.id WHERE o.merchant_id=? AND o.status='confirmed'", (uid,)).fetchall()
        prof = sum([r[0] for r in rows]) * 0.9 if rows else 0
        text = f"📊 مبيعاتك يا صاحب المتجر:\n\n📦 منتجاتك المنشورة: {cnt}\n🛒 إجمالي الطلبات: {total}\n✅ طلبات مؤكدة: {conf}\n⏳ بانتظار: {pend}\n💰 أرباحك (90%): {int(prof)} جنيه"
        kb = [[{"text": "📋 عرض آخر الطلبات", "callback_data": "orders"}, {"text": "🏠 الرئيسية", "callback_data": "home"}]]
        edit(chat, mid, text, kb)
        answer(c["id"])
        return

    if data == "orders":
        ords = db.execute("SELECT * FROM orders WHERE merchant_id=? ORDER BY id DESC LIMIT 5", (uid,)).fetchall()
        if not ords:
            edit(chat, mid, "لسه ما جاك أي طلب 🌙", [[{"text": "🔙 رجوع", "callback_data": "sales"}]])
        else:
            t = "📋 آخر 5 طلبات:\n\n"
            for o in ords:
                prod = db.execute("SELECT name FROM products WHERE id=?", (o[2],)).fetchone()
                pn = prod[0] if prod else f"منتج #{o[2]}"
                emoji = "✅" if o[6] == "confirmed" else "⏳"
                t += f"{emoji} #{o[0]} - {pn}\nالدفع: {o[5]}\nالمشتري: {o[4][:30]}...\n\n"
            edit(chat, mid, t, [[{"text": "🔙 رجوع", "callback_data": "sales"}]])
        answer(c["id"])
        return

    # شراء مع خيارين دفع
    if data.startswith("buy:"):
        pid = int(data.split(":")[1])
        p = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
        if not p:
            answer(c["id"], "المنتج غير موجود")
            return
        set_state(uid, "choice", {"pid": p[0], "mid": p[1], "price": p[3], "pname": p[2]})
        kb = [[{"text": "💵 الدفع عند الاستلام", "callback_data": f"cod:{p[0]}"}], [{"text": "💳 الدفع قبل الاستلام", "callback_data": f"pre:{p[0]}"}]]
        send(chat, f"📦 {p[2]}\n💰 {p[3]} جنيه\n\nاختر طريقة الدفع:", kb)
        answer(c["id"])
        return

    if data.startswith("cod:"):
        tmp = get_temp(uid)
        set_state(uid, "await_cod", tmp)
        send(chat, "💵 اخترت الدفع عند الاستلام\n\nأرسل معلومات التوصيل بهذا الشكل:\nالاسم - رقم الهاتف - العنوان كامل\n\nمثال: محمد 0912345678 الخرطوم بحري")
        answer(c["id"])
        return

    if data.startswith("pre:"):
        tmp = get_temp(uid)
        set_state(uid, "await_pre", tmp)
        send(chat, "💳 اخترت الدفع قبل الاستلام\n\nأرسل رقم هاتفك فقط، وسيقوم البائع بالاتصال بك لتأكيد الطلب وطريقة التحويل (بنكك).\n\nمثال: 0912345678")
        answer(c["id"])
        return

    # إدارة
    if data.startswith("m_ok:"):
        mid_t = int(data.split(":")[1])
        db.execute("UPDATE merchants SET status='approved' WHERE user_id=?", (mid_t,))
        db.commit()
        edit(chat, mid, f"تم قبول التاجر {mid_t} ✅")
        send(mid_t, "🎉 مبروك! تم قبول متجرك. الآن /start لإضافة منتجات")
        answer(c["id"], "تم القبول")
        return

    if data.startswith("m_no:"):
        mid_t = int(data.split(":")[1])
        db.execute("UPDATE merchants SET status='rejected' WHERE user_id=?", (mid_t,))
        db.commit()
        edit(chat, mid, f"تم رفض التاجر {mid_t} ❌")
        answer(c["id"])
        return

    if data.startswith("p_ok:"):
        pid = int(data.split(":")[1])
        db.execute("UPDATE products SET status='approved' WHERE id=?", (pid,))
        db.commit()
        p = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
        edit(chat, mid, f"✅ تم نشر المنتج: {p[2] if p else pid}")
        if p:
            send(p[1], f"✅ تم قبول منتجك {p[2]} ونشره في السوق")
        answer(c["id"], "تم النشر ✅")
        return

    if data.startswith("p_no:"):
        pid = int(data.split(":")[1])
        db.execute("UPDATE products SET status='rejected' WHERE id=?", (pid,))
        db.commit()
        edit(chat, mid, f"تم رفض المنتج {pid} ❌")
        answer(c["id"])
        return

    if data == "home":
        merch = db.execute("SELECT * FROM merchants WHERE user_id=?", (uid,)).fetchone()
        if merch and merch[4] == "approved":
            edit(chat, mid, f"🏠 لوحة التاجر {merch[1]}", [[{"text": "➕ إضافة منتج", "callback_data": "add"}, {"text": "📊 مبيعاتي", "callback_data": "sales"}], [{"text": "🛍️ تصفح كمشتري", "callback_data": "buyer"}]])
        else:
            edit(chat, mid, "🏠 الرئيسية\nاختر:", [[{"text": "🛍️ مشتري", "callback_data": "buyer"}, {"text": "🏪 تاجر", "callback_data": "merchant"}]])
        answer(c["id"])
        return

# ================== التشغيل ==================
def main():
    keep_alive()
    offset = 0
    print("Marketplace Bot V5 - 300 سطر يعمل...")
    while True:
        try:
            r = api("getUpdates", {"timeout": 30, "offset": offset})
            for u in r.get("result", []):
                offset = u["update_id"] + 1
                if "message" in u:
                    handle_message(u["message"])
                elif "callback_query" in u:
                    handle_callback(u["callback_query"])
        except Exception as e:
            print("خطأ:", e)
            time.sleep(2)

if __name__ == "__main__":
    main()
