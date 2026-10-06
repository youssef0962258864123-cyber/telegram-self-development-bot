from keep_alive import keep_alive
import os, json, time, sqlite3
from datetime import date
from urllib.request import Request, urlopen
from urllib.parse import urlencode

TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", os.environ.get("YOUR_CHAT_ID", "0")))
if not TOKEN:
    raise SystemExit("BOT_TOKEN غير موجود")

API = f"https://api.telegram.org/bot{TOKEN}"
DB = "marketplace.db"

BANKAK_INFO = "بنكك: 1234567 - باسم يوسف - 10% عمولة المنصة"

db = sqlite3.connect(DB, check_same_thread=False)
db.executescript("""
CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY, role TEXT, state TEXT, temp_data TEXT);
CREATE TABLE IF NOT EXISTS merchants(user_id INTEGER PRIMARY KEY, store_name TEXT, phone TEXT, city TEXT, status TEXT DEFAULT 'pending');
CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY AUTOINCREMENT, merchant_id INTEGER, name TEXT, price INTEGER, photo_id TEXT, description TEXT, status TEXT DEFAULT 'pending');
CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT, buyer_id INTEGER, product_id INTEGER, merchant_id INTEGER, buyer_info TEXT, photo_proof TEXT, status TEXT DEFAULT 'awaiting_proof');
""")
db.commit()

def api(method, data=None):
    data = data or {}
    req = Request(API + "/" + method, data=urlencode(data).encode(), headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def send(chat, text, kb=None, photo=None):
    if photo:
        d = {"chat_id": chat, "photo": photo, "caption": text}
        if kb: d["reply_markup"] = json.dumps({"inline_keyboard": kb}, ensure_ascii=False)
        return api("sendPhoto", d)
    else:
        d = {"chat_id": chat, "text": text}
        if kb: d["reply_markup"] = json.dumps({"inline_keyboard": kb}, ensure_ascii=False)
        return api("sendMessage", d)

def edit(chat, msg, text, kb=None):
    d = {"chat_id": chat, "message_id": msg, "text": text}
    if kb: d["reply_markup"] = json.dumps({"inline_keyboard": kb}, ensure_ascii=False)
    try:
        return api("editMessageText", d)
    except:
        # لو الرسالة فيها صورة، نعدل الكابشن
        d2 = {"chat_id": chat, "message_id": msg, "caption": text}
        if kb: d2["reply_markup"] = json.dumps({"inline_keyboard": kb}, ensure_ascii=False)
        try:
            return api("editMessageCaption", d2)
        except Exception as e:
            print(f"فشل التعديل: {e}")
            return None

def answer(cid, text=""):
    return api("answerCallbackQuery", {"callback_query_id": cid, "text": text})

def get_user(uid):
    row = db.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
    if not row:
        db.execute("INSERT INTO users(user_id, role, state) VALUES(?,?,?)", (uid, None, None))
        db.commit()
        return (uid, None, None, None)
    return row

def set_state(uid, state, temp=None):
    if temp is not None:
        db.execute("UPDATE users SET state=?, temp_data=? WHERE user_id=?", (state, json.dumps(temp, ensure_ascii=False), uid))
    else:
        db.execute("UPDATE users SET state=? WHERE user_id=?", (state, uid))
    db.commit()

def get_temp(uid):
    row = get_user(uid)
    if row[3]:
        try: return json.loads(row[3])
        except: return {}
    return {}

def handle_message(m):
    uid = m["from"]["id"]
    chat = m["chat"]["id"]
    text = m.get("text", "")
    get_user(uid)
    is_admin = (ADMIN_ID!= 0 and uid == ADMIN_ID)
    user = get_user(uid)
    state = user[2]
    temp = get_temp(uid)

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
        db.execute("INSERT OR REPLACE INTO merchants(user_id, store_name, phone, city, status) VALUES(?,?,?,?,?)",
                   (uid, temp["store_name"], temp["phone"], temp["city"], "pending"))
        db.commit()
        set_state(uid, None, {})
        send(chat, "✅ تم إرسال طلبك للإدارة، سيتم مراجعته خلال ساعات وسيصلك إشعار عند القبول.")
        if ADMIN_ID!= 0:
            kb = [[{"text": "✅ قبول التاجر", "callback_data": f"admin_m_ok:{uid}"}, {"text": "❌ رفض", "callback_data": f"admin_m_no:{uid}"}]]
            send(ADMIN_ID, f"🔔 تاجر جديد بانتظار الموافقة:\n\nالمتجر: {temp['store_name']}\nالهاتف: {temp['phone']}\nالمدينة: {temp['city']}\nالايدي: {uid}", kb)
        return
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
        set_state(uid, "await_prod_desc", temp)
        send(chat, "آخر خطوة، أرسل وصف قصير للمنتج:")
        return
    if state == "await_prod_desc":
        temp["desc"] = text
        db.execute("INSERT INTO products(merchant_id, name, price, photo_id, description, status) VALUES(?,?,?,?,?,?)",
                   (uid, temp["name"], temp["price"], temp["photo"], temp["desc"], "pending"))
        db.commit()
        set_state(uid, None, {})
        send(chat, "✅ تم رفع المنتج، بانتظار موافقة الإدارة. سيظهر في السوق بعد الموافقة.")
        if ADMIN_ID!= 0:
            prod_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            kb = [[{"text": "✅ نشر المنتج", "callback_data": f"admin_p_ok:{prod_id}"}, {"text": "❌ رفض", "callback_data": f"admin_p_no:{prod_id}"}]]
            send(ADMIN_ID, f"🔔 منتج جديد بانتظار الموافقة:\n{temp['name']} - {temp['price']} جنيه\nالوصف: {temp['desc']}", kb, photo=temp["photo"])
        return
    if state == "await_buyer_info":
        temp["buyer_info"] = text
        set_state(uid, "await_proof", temp)
        send(chat, f"تمام، معلوماتك محفوظة.\n\n{BANKAK_INFO}\n\nالسعر الكلي: {temp['price']} جنيه\n\nبعد التحويل، أرسل **صورة إشعار بنكك** هنا:")
        return
    if "photo" in m and state == "await_prod_photo":
        photo_id = m["photo"][-1]["file_id"]
        temp["photo"] = photo_id
        set_state(uid, "await_prod_name", temp)
        send(chat, "الصورة وصلت ✅\nالآن أرسل اسم المنتج:")
        return
    if "photo" in m and state == "await_proof":
        photo_id = m["photo"][-1]["file_id"]
        temp["proof"] = photo_id
        db.execute("INSERT INTO orders(buyer_id, product_id, merchant_id, buyer_info, photo_proof, status) VALUES(?,?,?,?,?,?)",
                   (uid, temp["product_id"], temp["merchant_id"], temp["buyer_info"], photo_id, "pending_admin"))
        db.commit()
        order_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        set_state(uid, None, {})
        send(chat, "✅ تم استلام إشعار الدفع، الإدارة حتراجعو الآن ولو صحيح حنأكد ليك الطلب.")
        if ADMIN_ID!= 0:
            kb = [[{"text": "✅ تأكيد الدفع والتسليم", "callback_data": f"admin_o_ok:{order_id}"}, {"text": "❌ دفع غير صحيح", "callback_data": f"admin_o_no:{order_id}"}]]
            send(ADMIN_ID, f"💰 طلب جديد بانتظار تأكيد الدفع #{order_id}\nالمنتج: {temp['prod_name']}\nالمشتري: {temp['buyer_info']}\nالمبلغ: {temp['price']}", kb, photo=photo_id)
        return
    if text.startswith("/start"):
        kb = [[{"text": "🛍️ أنا مشتري - تصفح السوق", "callback_data": "role:buyer"}, {"text": "🏪 أنا تاجر - افتح متجر", "callback_data": "role:merchant"}]]
        if is_admin:
            kb.append([{"text": "👑 لوحة الإدارة", "callback_data": "admin:panel"}])
        send(chat, "أهلا بك في سوق طوّر نفسك 🌟\n\nاختر هل أنت مشتري أم تاجر؟", kb)
        return
    if text.startswith("/add_product"):
        merch = db.execute("SELECT * FROM merchants WHERE user_id=?", (uid,)).fetchone()
        if not merch or merch[4]!= "approved":
            send(chat, "متجرك لم تتم الموافقة عليه بعد. انتظر موافقة الإدارة.")
            return
        set_state(uid, "await_prod_photo", {})
        send(chat, "لإضافة منتج جديد، أرسل صورة المنتج أولاً:")
        return
    if text.startswith("/admin") and is_admin:
        show_admin(chat)
        return

def handle_callback(c):
    uid = c["from"]["id"]
    chat = c["message"]["chat"]["id"]
    mid = c["message"]["message_id"]
    data = c["data"]
    get_user(uid)
    is_admin = (ADMIN_ID!= 0 and uid == ADMIN_ID)

    if data == "role:buyer":
        products = db.execute("SELECT * FROM products WHERE status='approved' ORDER BY id DESC LIMIT 10").fetchall()
        if not products:
            edit(chat, mid, "السوق فاضي حاليا، تعال لاحقا 🌙", [[{"text": "🏠 الرئيسية", "callback_data": "home"}]])
        else:
            for p in products[:5]:
                merch = db.execute("SELECT store_name FROM merchants WHERE user_id=?", (p[1],)).fetchone()
                store = merch[0] if merch else "متجر"
                kb = [[{"text": f"🛒 شراء - {p[3]} جنيه", "callback_data": f"buy:{p[0]}"}, {"text": f"🏪 {store}", "callback_data": f"store:{p[1]}"}]]
                send(chat, f"📦 {p[2]}\n💰 {p[3]} جنيه\n📝 {p[5]}\n🏪 {store}", kb, photo=p[4])
        answer(c["id"])
        return
    if data == "role:merchant":
        merch = db.execute("SELECT * FROM merchants WHERE user_id=?", (uid,)).fetchone()
        if merch:
            if merch[4] == "pending":
                edit(chat, mid, "طلبك قيد المراجعة، انتظر موافقة الإدارة ⏳", [[{"text": "🏠 الرئيسية", "callback_data": "home"}]])
            elif merch[4] == "approved":
                edit(chat, mid, f"أهلا بك يا صاحب متجر {merch[1]} ✅\n\nلإضافة منتج أرسل /add_product\nمنتجاتك المنشورة: {db.execute('SELECT COUNT(*) FROM products WHERE merchant_id=? AND status=?',(uid,'approved')).fetchone()[0]}", [[{"text": "➕ إضافة منتج", "callback_data": "add_prod"}, {"text": "📊 مبيعاتي", "callback_data": "my_sales"}]])
            else:
                edit(chat, mid, "تم رفض متجرك، تواصل مع الإدارة.", [[{"text": "🏠 الرئيسية", "callback_data": "home"}]])
        else:
            set_state(uid, "await_store_name", {})
            edit(chat, mid, "لفتح متجر جديد، أرسل اسم المتجر:")
        answer(c["id"])
        return
    if data == "add_prod":
        set_state(uid, "await_prod_photo", {})
        send(chat, "أرسل صورة المنتج:")
        answer(c["id"])
        return
    if data.startswith("buy:"):
        prod_id = int(data.split(":")[1])
        p = db.execute("SELECT * FROM products WHERE id=?", (prod_id,)).fetchone()
        if not p:
            answer(c["id"], "المنتج غير موجود")
            return
        set_state(uid, "await_buyer_info", {"product_id": p[0], "merchant_id": p[1], "price": p[3], "prod_name": p[2]})
        send(chat, f"أنت ستشتري: {p[2]} - {p[3]} جنيه\n\nأرسل معلومات التوصيل بهذا الشكل:\nالاسم - رقم الهاتف - العنوان كامل")
        answer(c["id"])
        return
    if data.startswith("admin_m_ok:") and is_admin:
        mid_t = int(data.split(":")[1])
        db.execute("UPDATE merchants SET status='approved' WHERE user_id=?", (mid_t,)); db.commit()
        edit(chat, mid, f"تم قبول التاجر {mid_t} ✅")
        send(mid_t, "🎉 مبروك! تم قبول متجرك. الآن يمكنك رفع المنتجات عبر /add_product")
        answer(c["id"], "تم قبول التاجر"); return
    if data.startswith("admin_m_no:") and is_admin:
        mid_t = int(data.split(":")[1])
        db.execute("UPDATE merchants SET status='rejected' WHERE user_id=?", (mid_t,)); db.commit()
        edit(chat, mid, f"تم رفض التاجر {mid_t} ❌")
        send(mid_t, "نأسف، تم رفض طلب متجرك. تواصل مع الإدارة.")
        answer(c["id"]); return
    if data.startswith("admin_p_ok:") and is_admin:
        pid = int(data.split(":")[1])
        db.execute("UPDATE products SET status='approved' WHERE id=?", (pid,)); db.commit()
        p = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
        edit(chat, mid, f"✅ تم نشر المنتج: {p[2] if p else pid}")
        if p:
            send(p[1], f"✅ تم قبول منتجك {p[2]} ونشره في السوق")
            # رسالة للمشترين انه منتج جديد نزل
        answer(c["id"], "تم النشر ✅"); return
    if data.startswith("admin_p_no:") and is_admin:
        pid = int(data.split(":")[1])
        db.execute("UPDATE products SET status='rejected' WHERE id=?", (pid,)); db.commit()
        edit(chat, mid, f"تم رفض المنتج {pid} ❌")
        answer(c["id"], "تم الرفض"); return
    if data.startswith("admin_o_ok:") and is_admin:
        oid = int(data.split(":")[1])
        o = db.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
        db.execute("UPDATE orders SET status='confirmed' WHERE id=?", (oid,)); db.commit()
        edit(chat, mid, f"تم تأكيد الطلب #{oid} ✅")
        if o:
            send(o[1], f"✅ تم تأكيد دفعك للطلب #{oid}. طلبك قيد التجهيز والتوصيل.")
            send(o[3], f"🔔 عندك طلب جديد مؤكد #{oid}\nمعلومات المشتري: {o[4]}\nتواصل معه وسلمه، عمولتك 90%")
        answer(c["id"]); return
    if data.startswith("admin_o_no:") and is_admin:
        oid = int(data.split(":")[1])
        db.execute("UPDATE orders SET status='rejected' WHERE id=?", (oid,)); db.commit()
        o = db.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
        edit(chat, mid, f"تم رفض الطلب #{oid} ❌")
        if o: send(o[1], f"❌ تم رفض إشعار الدفع للطلب #{oid}. تأكد من المبلغ وأعد المحاولة أو تواصل مع الإدارة.")
        answer(c["id"]); return
    if data == "admin:panel" and is_admin:
        show_admin(chat, mid, edit_mode=True)
        answer(c["id"]); return
    if data == "home":
        edit(chat, mid, "🏠 الرئيسية\n\nاختر:", [[{"text": "🛍️ مشتري", "callback_data": "role:buyer"}, {"text": "🏪 تاجر", "callback_data": "role:merchant"}]])
        answer(c["id"]); return

def show_admin(chat, mid=None, edit_mode=False):
    m_count = db.execute("SELECT COUNT(*) FROM merchants WHERE status='pending'").fetchone()[0]
    p_count = db.execute("SELECT COUNT(*) FROM products WHERE status='pending'").fetchone()[0]
    o_count = db.execute("SELECT COUNT(*) FROM orders WHERE status='pending_admin'").fetchone()[0]
    text = f"👑 لوحة الإدارة\n\n🕒 تجار بانتظار: {m_count}\n📦 منتجات بانتظار: {p_count}\n💰 طلبات بانتظار تأكيد دفع: {o_count}\n\n{BANKAK_INFO}"
    kb = [[{"text": f"تجار ({m_count})", "callback_data": "admin_list_m"}, {"text": f"منتجات ({p_count})", "callback_data": "admin_list_p"}]]
    if edit_mode: edit(chat, mid, text, kb)
    else: send(chat, text, kb)

def main():
    keep_alive()
    offset = 0
    print("Marketplace Bot يعمل...")
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
