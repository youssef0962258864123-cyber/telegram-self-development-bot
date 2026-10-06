from keep_alive import keep_alive
import os
import json
import time
import sqlite3
from urllib.request import Request
from urllib.request import urlopen
from urllib.parse import urlencode

TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
BOT_USERNAME = os.environ.get("BOT_USERNAME", "your_bot")
ADMIN_CONTACT = os.environ.get("ADMIN_CONTACT", "@admin")
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

db = sqlite3.connect(DB, check_same_thread=False)
db.executescript('''
CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY, state TEXT, temp TEXT, points INTEGER DEFAULT 0, purchases INTEGER DEFAULT 0, sales INTEGER DEFAULT 0, referred_by INTEGER, is_banned INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS merchants(user_id INTEGER PRIMARY KEY, store_name TEXT, phone TEXT, city TEXT, status TEXT DEFAULT 'pending', reject_reason TEXT);
CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY AUTOINCREMENT, merchant_id INTEGER, name TEXT, price INTEGER, photo_id TEXT, description TEXT, category TEXT, status TEXT DEFAULT 'pending', reject_reason TEXT);
CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT, buyer_id INTEGER, product_id INTEGER, merchant_id INTEGER, buyer_info TEXT, payment_type TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS referrals(id INTEGER PRIMARY KEY AUTOINCREMENT, referrer_id INTEGER, referred_id INTEGER);
''')
try:
    db.execute("ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0")
except:
    pass
try:
    db.execute("ALTER TABLE merchants ADD COLUMN reject_reason TEXT")
except:
    pass
try:
    db.execute("ALTER TABLE products ADD COLUMN reject_reason TEXT")
except:
    pass
db.commit()

def api(method, data=None):
    if data is None:
        data = {}
    try:
        req = Request(API + "/" + method, data=urlencode(data).encode(), headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urlopen(req, timeout=30) as res:
            return json.loads(res.read())
    except Exception as e:
        print(e)
        return {}

def send(chat_id, text, kb=None, photo=None, main_kb=False):
    if photo:
        payload = {"chat_id": chat_id, "photo": photo, "caption": text}
        if kb:
            payload["reply_markup"] = json.dumps({"inline_keyboard": kb}, ensure_ascii=False)
        return api("sendPhoto", payload)
    payload = {"chat_id": chat_id, "text": text}
    if kb:
        payload["reply_markup"] = json.dumps({"inline_keyboard": kb}, ensure_ascii=False)
    elif main_kb:
        payload["reply_markup"] = json.dumps({"keyboard": [["🔄 تحديث الصفحة /start"], ["📊 حسابي", "☎️ خدمة العملاء"]], "resize_keyboard": True}, ensure_ascii=False)
    return api("sendMessage", payload)

def edit(chat_id, msg_id, text, kb=None):
    payload = {"chat_id": chat_id, "message_id": msg_id, "text": text}
    if kb:
        payload["reply_markup"] = json.dumps({"inline_keyboard": kb}, ensure_ascii=False)
    try:
        return api("editMessageText", payload)
    except:
        payload2 = {"chat_id": chat_id, "message_id": msg_id, "caption": text}
        if kb:
            payload2["reply_markup"] = json.dumps({"inline_keyboard": kb}, ensure_ascii=False)
        try:
            return api("editMessageCaption", payload2)
        except:
            return None

def answer(cid, txt=""):
    return api("answerCallbackQuery", {"callback_query_id": cid, "text": txt})

def get_temp(uid):
    row = db.execute("SELECT temp FROM users WHERE user_id=?", (uid,)).fetchone()
    if row and row[0]:
        try:
            return json.loads(row[0])
        except:
            return {}
    return {}

def set_state(uid, state, tmp=None):
    db.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (uid,))
    if tmp is not None:
        j = json.dumps(tmp, ensure_ascii=False)
        db.execute("UPDATE users SET state=?, temp=? WHERE user_id=?", (state, j, uid))
    else:
        db.execute("UPDATE users SET state=? WHERE user_id=?", (state, uid))
    db.commit()

def get_state(uid):
    row = db.execute("SELECT state FROM users WHERE user_id=?", (uid,)).fetchone()
    if row:
        return row[0]
    return None

def cat_kb(prefix):
    kb = []
    for i in range(0, len(CATEGORIES), 2):
        row = []
        b1 = {"text": CATEGORIES[i], "callback_data": f"{prefix}:{CATEGORIES[i]}"}
        row.append(b1)
        if i+1 < len(CATEGORIES):
            b2 = {"text": CATEGORIES[i+1], "callback_data": f"{prefix}:{CATEGORIES[i+1]}"}
            row.append(b2)
        kb.append(row)
    return kb

def setup():
    try:
        cmds = [{"command": "start", "description": "🏠 الرئيسية - تحديث"}]
        api("setMyCommands", {"commands": json.dumps(cmds, ensure_ascii=False)})
    except:
        pass

def handle_msg(m):
    uid = m["from"]["id"]
    chat = m["chat"]["id"]
    txt = m.get("text", "")
    st = get_state(uid)
    tmp = get_temp(uid)
    db.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (uid,))
    db.commit()
    banned = db.execute("SELECT is_banned FROM users WHERE user_id=?", (uid,)).fetchone()
    if banned and banned[0]==1 and uid!=ADMIN_ID:
        send(chat, "🚫 محظور، تواصل: "+ADMIN_CONTACT)
        return
    if txt in ["🔄 تحديث الصفحة /start","🔄 تحديث الصفحة","تحديث","/start","start"]:
        txt = "/start"
    if txt in ["📊 حسابي","حسابي"]:
        row = db.execute("SELECT points,purchases,sales FROM users WHERE user_id=?", (uid,)).fetchone()
        p = row[0] if row else 0
        pu = row[1] if row else 0
        s = row[2] if row else 0
        link = f"https://t.me/{BOT_USERNAME}?start={uid}" if BOT_USERNAME!="your_bot" else f"/start {uid}"
        send(chat, f"📊 حسابك:\n🛒 {pu}\n📦 {s}\n⭐ {p}\n\n🔗 {link}", main_kb=True)
        return
    if txt in ["☎️ خدمة العملاء","خدمة العملاء"]:
        send(chat, f"☎️ خدمة العملاء\n\n⭐⭐⭐\n\nتواصل: {ADMIN_CONTACT}\nقريبا بوت تواصل.", main_kb=True)
        return
    if st and st.startswith("await_reject_reason_"):
        reason = txt
        parts = st.split("_")
        final_action = parts[3]
        typ = parts[4]
        target_id = int(parts[5])
        if typ=="m":
            new_status = "rejected_perm" if final_action=="perm" else "rejected_temp"
            db.execute("UPDATE merchants SET status=?, reject_reason=? WHERE user_id=?", (new_status, reason, target_id))
            db.commit()
            if final_action=="perm":
                send(chat, f"✅ رفض نهائي {target_id}")
                try:
                    send(target_id, f"❌ رفض نهائي:\n{reason}\nتواصل: {ADMIN_CONTACT}\n☎️ ⭐⭐⭐", main_kb=True)
                except:
                    pass
            else:
                send(chat, f"✅ رفض مؤقت {target_id}")
                try:
                    send(target_id, f"⏳ رفض مؤقت:\n{reason}\n/start", main_kb=True)
                except:
                    pass
        else:
            new_status = "rejected_perm" if final_action=="perm" else "rejected_temp"
            db.execute("UPDATE products SET status=?, reject_reason=? WHERE id=?", (new_status, reason, target_id))
            db.commit()
            prod = db.execute("SELECT merchant_id,name FROM products WHERE id=?", (target_id,)).fetchone()
            send(chat, f"✅ رفض {final_action} للمنتج {target_id}")
            if prod:
                try:
                    if final_action=="perm":
                        send(prod[0], f"❌ رفض نهائي '{prod[1]}':\n{reason}", main_kb=True)
                    else:
                        send(prod[0], f"⏳ رفض مؤقت '{prod[1]}':\n{reason}", main_kb=True)
                except:
                    pass
        set_state(uid, None, {})
        return
    if st=="await_store_name":
        tmp["store_name"]=txt
        set_state(uid, "await_phone", tmp)
        send(chat, "تمام ✅\nأرسل رقم واتساب:")
        return
    if st=="await_phone":
        tmp["phone"]=txt
        set_state(uid, "await_city", tmp)
        send(chat, "أرسل مدينتك:")
        return
    if st=="await_city":
        tmp["city"]=txt
        db.execute("INSERT OR REPLACE INTO merchants(user_id, store_name, phone, city, status) VALUES(?,?,?,?,?)", (uid, tmp["store_name"], tmp["phone"], tmp["city"], "pending"))
        db.commit()
        set_state(uid, None, {})
        send(chat, "✅ تم إرسال طلبك للإدارة.", main_kb=True)
        kb = []
        kb.append([{"text":"✅ قبول","callback_data":f"m_ok:{uid}"}])
        kb.append([{"text":"⏳ رفض مؤقت","callback_data":f"m_reject_temp:{uid}"},{"text":"🚫 رفض نهائي","callback_data":f"m_reject_perm:{uid}"}])
        kb.append([{"text":"🔇 كانسل","callback_data":f"m_no:{uid}"}])
        if ADMIN_ID:
            send(ADMIN_ID, f"🔔 تاجر جديد:\n{tmp['store_name']}\n{tmp['phone']}\n{tmp['city']}\nID:{uid}", kb)
        return
    if st=="await_prod_name":
        tmp["name"]=txt
        set_state(uid, "await_prod_price", tmp)
        send(chat, "أرسل السعر أرقام فقط:")
        return
    if st=="await_prod_price":
        if not txt.isdigit():
            send(chat, "أرقام فقط:")
            return
        tmp["price"]=int(txt)
        set_state(uid, "await_prod_cat", tmp)
        send(chat, "اختر قسم المنتج:", cat_kb("setcat"))
        return
    if st=="await_prod_desc":
        tmp["desc"]=txt
        db.execute("INSERT INTO products(merchant_id,name,price,photo_id,description,category,status) VALUES(?,?,?,?,?,?,?)", (uid, tmp["name"], tmp["price"], tmp["photo"], tmp["desc"], tmp.get("cat","📦 أخرى"), "pending"))
        db.commit()
        pid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        set_state(uid, None, {})
        send(chat, f"✅ تم رفع المنتج في {tmp.get('cat')} بانتظار الموافقة.", main_kb=True)
        kb = []
        kb.append([{"text":"✅ قبول","callback_data":f"p_ok:{pid}"}])
        kb.append([{"text":"⏳ رفض مؤقت","callback_data":f"p_reject_temp:{pid}"},{"text":"🚫 رفض نهائي","callback_data":f"p_reject_perm:{pid}"}])
        kb.append([{"text":"🔇 كانسل","callback_data":f"p_no:{pid}"}])
        if ADMIN_ID:
            send(ADMIN_ID, f"🔔 منتج جديد:\n{tmp['name']} - {tmp['price']}ج\n{tmp.get('cat')}", kb, photo=tmp["photo"])
        return
    if st=="await_cod":
        db.execute("INSERT INTO orders(buyer_id,product_id,merchant_id,buyer_info,payment_type,status) VALUES(?,?,?,?,?,?)", (uid, tmp["pid"], tmp["mid"], txt, "عند الاستلام", "confirmed"))
        db.commit()
        db.execute("UPDATE users SET purchases=purchases+1 WHERE user_id=?", (uid,))
        db.execute("UPDATE users SET sales=sales+1 WHERE user_id=?", (tmp["mid"],))
        db.commit()
        oid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        set_state(uid, None, {})
        send(chat, f"✅ طلبك #{oid} مؤكد عند الاستلام", main_kb=True)
        send(tmp["mid"], f"🔔 طلب جديد #{oid} عند الاستلام\n{tmp['pname']}\n{txt}")
        return
    if st=="await_pre":
        db.execute("INSERT INTO orders(buyer_id,product_id,merchant_id,buyer_info,payment_type,status) VALUES(?,?,?,?,?,?)", (uid, tmp["pid"], tmp["mid"], f"رقم:{txt}", "قبل الاستلام", "pending_call"))
        db.commit()
        db.execute("UPDATE users SET purchases=purchases+1 WHERE user_id=?", (uid,))
        db.execute("UPDATE users SET sales=sales+1 WHERE user_id=?", (tmp["mid"],))
        db.commit()
        oid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        set_state(uid, None, {})
        send(chat, f"✅ طلبك #{oid} محفوظ قبل الاستلام\nالبائع سيتصل بك", main_kb=True)
        send(tmp["mid"], f"🔔 طلب #{oid} قبل الاستلام\n{tmp['pname']}\n{txt}")
        return
    if "photo" in m and st=="await_prod_photo":
        tmp["photo"]=m["photo"][-1]["file_id"]
        set_state(uid, "await_prod_name", tmp)
        send(chat, "الصورة وصلت ✅\nأرسل اسم المنتج:")
        return
    if txt.startswith("/start"):
        parts = txt.split()
        if len(parts)>1 and parts[1].isdigit():
            ref_id = int(parts[1])
            if ref_id!=uid:
                already = db.execute("SELECT * FROM referrals WHERE referred_id=?", (uid,)).fetchone()
                user_ref = db.execute("SELECT referred_by FROM users WHERE user_id=?", (uid,)).fetchone()
                if not already and (not user_ref or not user_ref[0]):
                    db.execute("INSERT INTO referrals(referrer_id,referred_id) VALUES(?,?)", (ref_id, uid))
                    db.execute("UPDATE users SET points=points+10 WHERE user_id=?", (ref_id,))
                    db.execute("UPDATE users SET referred_by=? WHERE user_id=?", (ref_id, uid))
                    db.commit()
                    try:
                        send(ref_id, f"🎉 إحالة جديدة! +10 نقاط")
                    except:
                        pass
        merch = db.execute("SELECT * FROM merchants WHERE user_id=?", (uid,)).fetchone()
        if merch and merch[4]=="banned":
            send(chat, f"🚫 محظور نهائيا.\nالسبب: {merch[5] or 'مخالفة'}\nتواصل: {ADMIN_CONTACT}", main_kb=True)
            return
        if merch and merch[4]=="approved":
            cnt = db.execute("SELECT COUNT(*) FROM products WHERE merchant_id=? AND status='approved'", (uid,)).fetchone()[0]
            kb = []
            kb.append([{"text":"➕ إضافة منتج","callback_data":"add"},{"text":"📊 مبيعاتي","callback_data":"sales"}])
            kb.append([{"text":"🛍️ تصفح السوق","callback_data":"buyer"}])
            kb.append([{"text":"☎️ خدمة العملاء ⭐⭐⭐","callback_data":"support"}])
            if uid==ADMIN_ID:
                kb.append([{"text":"👑 لوحة الأدمن","callback_data":"admin_panel"}])
            send(chat, f"أهلا يا صاحب متجر {merch[1]} ✅\nمنتجاتك: {cnt}", kb, main_kb=True)
            return
        if merch and merch[4]=="pending":
            send(chat, f"متجرك '{merch[1]}' قيد المراجعة ⏳", main_kb=True)
            return
        if merch and merch[4] in ["rejected_perm","rejected_temp","rejected"]:
            reason = merch[5] or "غير محدد"
            kb_reapply = []
            kb_reapply.append([{"text":"🔄 إعادة التقديم","callback_data":"merchant"}])
            kb_reapply.append([{"text":"☎️ تواصل مع الإدارة","callback_data":"support"}])
            if merch[4]=="rejected_perm":
                send(chat, f"❌ تم رفض متجرك نهائيا سابقا.\nالسبب: {reason}\n\nيمكنك التواصل {ADMIN_CONTACT} أو إعادة التقديم.", kb_reapply, main_kb=True)
            else:
                send(chat, f"⏳ تم رفض متجرك مؤقتا.\nالسبب: {reason}\n\nيمكنك التقديم مرة أخرى الآن.", kb_reapply, main_kb=True)
            return
        kb = []
        kb.append([{"text":"🛍️ أنا مشتري","callback_data":"buyer"},{"text":"🏪 أنا تاجر","callback_data":"merchant"}])
        kb.append([{"text":"☎️ خدمة العملاء","callback_data":"support"}])
        if uid==ADMIN_ID:
            kb.append([{"text":"👑 لوحة الأدمن","callback_data":"admin_panel"}])
        send(chat, "أهلا بك في سوق طوّر نفسك 🌟\nاختر:", kb, main_kb=True)
        return

def handle_cb(c):
    uid = c["from"]["id"]
    chat = c["message"]["chat"]["id"]
    mid = c["message"]["message_id"]
    data = c["data"]
    if data=="admin_panel" and uid==ADMIN_ID:
        total_users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        total_merch = db.execute("SELECT COUNT(*) FROM merchants WHERE status='approved'").fetchone()[0]
        pending_m = db.execute("SELECT COUNT(*) FROM merchants WHERE status='pending'").fetchone()[0]
        rejected = db.execute("SELECT COUNT(*) FROM merchants WHERE status LIKE 'rejected%'").fetchone()[0]
        banned = db.execute("SELECT COUNT(*) FROM users WHERE is_banned=1").fetchone()[0]
        kb = []
        kb.append([{"text":f"👥 كل المستخدمين ({total_users})","callback_data":"admin_users"}])
        kb.append([{"text":f"🏪 التجار المقبولين ({total_merch})","callback_data":"admin_merchants"}])
        kb.append([{"text":f"⏳ طلبات معلقة ({pending_m})","callback_data":"admin_pending"}])
        kb.append([{"text":f"❌ المرفوضين ({rejected})","callback_data":"admin_rejected"}])
        kb.append([{"text":f"🚫 المحظورين ({banned})","callback_data":"admin_banned"}])
        kb.append([{"text":"🏠 الرئيسية","callback_data":"home"}])
        edit(chat, mid, f"👑 لوحة الأدمن\n\n👥 المستخدمين: {total_users}\n🏪 التجار: {total_merch}\n⏳ معلق: {pending_m}\n❌ مرفوض: {rejected}\n🚫 محظور: {banned}", kb)
        answer(c["id"])
        return
    if data=="admin_users" and uid==ADMIN_ID:
        users = db.execute("SELECT user_id,points,purchases,sales,is_banned FROM users ORDER BY user_id DESC LIMIT 10").fetchall()
        txt = "👥 آخر 10 مستخدمين:\n\n"
        kb = []
        for u in users:
            status = "🚫 محظور" if u[4]==1 else "✅ نشط"
            txt += f"ID:{u[0]} - نقاط:{u[1]} - شراء:{u[2]} بيع:{u[3]} - {status}\n"
            kb.append([{"text":f"{'فك حظر' if u[4]==1 else 'حظر'} {u[0]}","callback_data":f"admin_toggle_ban:{u[0]}"},{"text":f"تفاصيل {u[0]}","callback_data":f"admin_user_info:{u[0]}"}])
        kb.append([{"text":"🔙 رجوع","callback_data":"admin_panel"}])
        edit(chat, mid, txt, kb)
        answer(c["id"])
        return
    if data.startswith("admin_toggle_ban:") and uid==ADMIN_ID:
        target = int(data.split(":")[1])
        cur = db.execute("SELECT is_banned FROM users WHERE user_id=?", (target,)).fetchone()
        new_val = 0 if cur and cur[0]==1 else 1
        db.execute("UPDATE users SET is_banned=? WHERE user_id=?", (new_val, target))
        if new_val==1:
            db.execute("UPDATE merchants SET status='banned' WHERE user_id=?", (target,))
        else:
            db.execute("UPDATE merchants SET status='approved' WHERE user_id=? AND status='banned'", (target,))
        db.commit()
        answer(c["id"], "تم الحظر" if new_val==1 else "تم فك الحظر")
        edit(chat, mid, f"{'🚫 تم حظر' if new_val==1 else '✅ تم فك حظر'} {target}", [[{"text":"🔙 رجوع","callback_data":"admin_users"}]])
        return
    if data.startswith("admin_user_info:") and uid==ADMIN_ID:
        target = int(data.split(":")[1])
        u = db.execute("SELECT points,purchases,sales,referred_by,is_banned FROM users WHERE user_id=?", (target,)).fetchone()
        merch = db.execute("SELECT store_name,phone,city,status,reject_reason FROM merchants WHERE user_id=?", (target,)).fetchone()
        txt = f"👤 تفاصيل {target}:\n\nنقاط: {u[0] if u else 0}\nمشتريات: {u[1] if u else 0}\nمبيعات: {u[2] if u else 0}\nمحظور: {'نعم' if u and u[4]==1 else 'لا'}\n"
        if merch:
            txt += f"\n🏪 متجر: {merch[0]}\n📞 {merch[1]}\n📍 {merch[2]}\nحالة: {merch[3]}\nسبب: {merch[4] or 'لا يوجد'}"
        else:
            txt += "\nلا يوجد متجر"
        kb = []
        kb.append([{"text":"🚫 حظر","callback_data":f"admin_toggle_ban:{target}"},{"text":"✅ قبول كتاجر","callback_data":f"m_ok:{target}"}])
        kb.append([{"text":"🔙 رجوع","callback_data":"admin_users"}])
        edit(chat, mid, txt, kb)
        answer(c["id"])
        return
    if data=="admin_merchants" and uid==ADMIN_ID:
        merchs = db.execute("SELECT user_id,store_name,city FROM merchants WHERE status='approved' ORDER BY user_id DESC LIMIT 10").fetchall()
        txt = "🏪 التجار المقبولين:\n\n"
        kb = []
        for m in merchs:
            txt += f"{m[1]} - {m[2]} - ID:{m[0]}\n"
            kb.append([{"text":f"حظر {m[1]}","callback_data":f"admin_toggle_ban:{m[0]}"},{"text":f"رفض {m[0]}","callback_data":f"m_reject_perm:{m[0]}"}])
        kb.append([{"text":"🔙 رجوع","callback_data":"admin_panel"}])
        edit(chat, mid, txt or "لا يوجد تجار", kb)
        answer(c["id"])
        return
    if data=="admin_pending" and uid==ADMIN_ID:
        pend = db.execute("SELECT user_id,store_name,phone,city FROM merchants WHERE status='pending' LIMIT 5").fetchall()
        if not pend:
            edit(chat, mid, "لا يوجد طلبات معلقة", [[{"text":"🔙 رجوع","callback_data":"admin_panel"}]])
        else:
            edit(chat, mid, f"⏳ {len(pend)} طلبات معلقة")
            for m in pend:
                kb = []
                kb.append([{"text":"✅ قبول","callback_data":f"m_ok:{m[0]}"}])
                kb.append([{"text":"⏳ رفض مؤقت","callback_data":f"m_reject_temp:{m[0]}"},{"text":"🚫 رفض نهائي","callback_data":f"m_reject_perm:{m[0]}"}])
                kb.append([{"text":"🔇 كانسل","callback_data":f"m_no:{m[0]}"}])
                send(chat, f"🔔 تاجر معلق:\n{m[1]}\n{m[2]}\n{m[3]}\nID:{m[0]}", kb)
        answer(c["id"])
        return
    if data=="admin_rejected" and uid==ADMIN_ID:
        rej = db.execute("SELECT user_id,store_name,status,reject_reason FROM merchants WHERE status LIKE 'rejected%' LIMIT 10").fetchall()
        txt = "❌ المرفوضين (يمكنك قبولهم تاني):\n\n"
        kb = []
        for r in rej:
            txt += f"ID:{r[0]} - {r[1]} - {r[2]}\nالسبب: {(r[3] or 'بدون سبب')[:30]}\n\n"
            kb.append([{"text":f"✅ قبول {r[0]} تاني","callback_data":f"m_ok:{r[0]}"},{"text":f"🚫 حظر {r[0]}","callback_data":f"admin_toggle_ban:{r[0]}"}])
        kb.append([{"text":"🔙 رجوع","callback_data":"admin_panel"}])
        edit(chat, mid, txt or "لا يوجد مرفوضين", kb)
        answer(c["id"])
        return
    if data=="admin_banned" and uid==ADMIN_ID:
        banned = db.execute("SELECT user_id FROM users WHERE is_banned=1 LIMIT 10").fetchall()
        txt = "🚫 المحظورين:\n\n"
        kb = []
        for b in banned:
            txt += f"ID:{b[0]}\n"
            kb.append([{"text":f"✅ فك حظر {b[0]}","callback_data":f"admin_toggle_ban:{b[0]}"}])
        kb.append([{"text":"🔙 رجوع","callback_data":"admin_panel"}])
        edit(chat, mid, txt or "لا يوجد محظورين", kb)
        answer(c["id"])
        return
    if data=="buyer":
        kb = cat_kb("browse")
        kb.append([{"text":"🔍 كل المنتجات","callback_data":"browse:all"}])
        kb.append([{"text":"🏠 الرئيسية","callback_data":"home"}])
        edit(chat, mid, "🛍️ اختر القسم:", kb)
        answer(c["id"])
        return
    if data.startswith("browse:"):
        cat = data.split(":", 1)[1]
        if cat=="all":
            prods = db.execute("SELECT * FROM products WHERE status='approved' ORDER BY id DESC LIMIT 10").fetchall()
            title = "كل المنتجات"
        else:
            prods = db.execute("SELECT * FROM products WHERE status='approved' AND category=? ORDER BY id DESC LIMIT 10", (cat,)).fetchall()
            title = f"قسم {cat}"
        if not prods:
            edit(chat, mid, f"{title}\n\nما في منتجات 🌙", [[{"text":"🔙 رجوع","callback_data":"buyer"}]])
        else:
            edit(chat, mid, f"{title} - {len(prods)} منتج 👇")
            for p in prods:
                store = db.execute("SELECT store_name FROM merchants WHERE user_id=?", (p[1],)).fetchone()
                sname = store[0] if store else "متجر"
                kb = []
                kb.append([{"text":f"🛒 شراء - {p[3]} جنيه","callback_data":f"buy:{p[0]}"}])
                send(chat, f"📦 {p[2]}\n💰 {p[3]}ج\n{p[6]}\n{p[5]}\n🏪 {sname}", kb, photo=p[4])
        answer(c["id"])
        return
    if data=="merchant":
        merch = db.execute("SELECT * FROM merchants WHERE user_id=?", (uid,)).fetchone()
        if merch:
            if merch[4]=="pending":
                edit(chat, mid, "طلبك قيد المراجعة ⏳")
            elif merch[4]=="approved":
                edit(chat, mid, f"أهلا {merch[1]} ✅", [[{"text":"➕ إضافة منتج","callback_data":"add"},{"text":"📊 مبيعاتي","callback_data":"sales"}]])
            elif merch[4]=="banned":
                edit(chat, mid, f"🚫 محظور: {merch[5]}\nتواصل: {ADMIN_CONTACT}")
            else:
                set_state(uid, "await_store_name", {})
                edit(chat, mid, f"تم رفضك سابقا: {merch[5] or ''}\nأرسل اسم المتجر الجديد:")
        else:
            set_state(uid, "await_store_name", {})
            edit(chat, mid, "أرسل اسم المتجر:")
        answer(c["id"])
        return
    if data.startswith("setcat:"):
        cat = data.split(":", 1)[1]
        tmp = get_temp(uid)
        tmp["cat"]=cat
        set_state(uid, "await_prod_desc", tmp)
        edit(chat, mid, f"اخترت {cat} ✅\nأرسل وصف المنتج:")
        answer(c["id"])
        return
    if data=="add":
        set_state(uid, "await_prod_photo", {})
        send(chat, "أرسل صورة المنتج:")
        answer(c["id"])
        return
    if data=="sales":
        total = db.execute("SELECT COUNT(*) FROM orders WHERE merchant_id=?", (uid,)).fetchone()[0]
        cnt = db.execute("SELECT COUNT(*) FROM products WHERE merchant_id=? AND status='approved'", (uid,)).fetchone()[0]
        edit(chat, mid, f"📊 مبيعاتك:\n📦 منتجاتك: {cnt}\n🛒 طلبات: {total}", [[{"text":"📋 آخر الطلبات","callback_data":"orders"},{"text":"🏠 الرئيسية","callback_data":"home"}]])
        answer(c["id"])
        return
    if data=="orders":
        ords = db.execute("SELECT * FROM orders WHERE merchant_id=? ORDER BY id DESC LIMIT 5", (uid,)).fetchall()
        if not ords:
            edit(chat, mid, "ما جاك طلبات 🌙", [[{"text":"🔙 رجوع","callback_data":"sales"}]])
        else:
            t = "📋 آخر 5 طلبات:\n\n"
            for o in ords:
                prod = db.execute("SELECT name FROM products WHERE id=?", (o[2],)).fetchone()
                pn = prod[0] if prod else o[2]
                t += f"#{o[0]} - {pn}\nالدفع: {o[5]}\n{o[4][:30]}\n\n"
            edit(chat, mid, t, [[{"text":"🔙 رجوع","callback_data":"sales"}]])
        answer(c["id"])
        return
    if data=="my_account":
        row = db.execute("SELECT points,purchases,sales FROM users WHERE user_id=?", (uid,)).fetchone()
        points = row[0] if row else 0
        purch = row[1] if row else 0
        sales = row[2] if row else 0
        link = f"https://t.me/{BOT_USERNAME}?start={uid}" if BOT_USERNAME!="your_bot" else f"/start {uid}"
        edit(chat, mid, f"📊 حسابك:\n🛒 اشتريت: {purch}\n📦 بعت: {sales}\n⭐ نقاطك: {points}\n\n🔗 {link}", [[{"text":"🏠 الرئيسية","callback_data":"home"}]])
        answer(c["id"])
        return
    if data=="support":
        edit(chat, mid, f"☎️ خدمة العملاء\n\n⭐⭐⭐\n\nتواصل: {ADMIN_CONTACT}\nقريبا بوت تواصل خاص.", [[{"text":"🏠 الرئيسية","callback_data":"home"}]])
        answer(c["id"])
        return
    if data.startswith("buy:"):
        pid = int(data.split(":")[1])
        p = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
        if not p:
            answer(c["id"], "غير موجود")
            return
        set_state(uid, "choice", {"pid":p[0],"mid":p[1],"price":p[3],"pname":p[2]})
        kb = []
        kb.append([{"text":"💵 عند الاستلام","callback_data":f"cod:{p[0]}"}])
        kb.append([{"text":"💳 قبل الاستلام","callback_data":f"pre:{p[0]}"}])
        send(chat, f"📦 {p[2]}\n💰 {p[3]}ج\n\nاختر طريقة الدفع:", kb)
        answer(c["id"])
        return
    if data.startswith("cod:"):
        tmp = get_temp(uid)
        set_state(uid, "await_cod", tmp)
        send(chat, "💵 عند الاستلام\nأرسل الاسم - الهاتف - العنوان:")
        answer(c["id"])
        return
    if data.startswith("pre:"):
        tmp = get_temp(uid)
        set_state(uid, "await_pre", tmp)
        send(chat, "💳 قبل الاستلام\nأرسل رقم هاتفك:")
        answer(c["id"])
        return
    if data.startswith("m_ok:"):
        mid_t = int(data.split(":")[1])
        db.execute("UPDATE merchants SET status='approved', reject_reason='' WHERE user_id=?", (mid_t,))
        db.commit()
        edit(chat, mid, f"✅ تم قبول التاجر {mid_t}")
        try:
            send(mid_t, "🎉 مبروك! تم قبول متجرك. /start", main_kb=True)
        except:
            pass
        answer(c["id"])
        return
    if data.startswith("m_reject_temp:"):
        target = int(data.split(":")[1])
        set_state(uid, f"await_reject_reason_temp_m_{target}", {})
        edit(chat, mid, f"⏳ رفض مؤقت للتاجر {target}\nأرسل سبب الرفض:")
        answer(c["id"])
        return
    if data.startswith("m_reject_perm:"):
        target = int(data.split(":")[1])
        set_state(uid, f"await_reject_reason_perm_m_{target}", {})
        edit(chat, mid, f"🚫 رفض نهائي للتاجر {target}\nأرسل سبب الرفض:")
        answer(c["id"])
        return
    if data.startswith("m_no:"):
        mid_t = int(data.split(":")[1])
        db.execute("UPDATE merchants SET status='rejected_temp', reject_reason='رفض صامت' WHERE user_id=?", (mid_t,))
        db.commit()
        edit(chat, mid, f"🔇 تم رفض {mid_t} بصمت")
        answer(c["id"])
        return
    if data.startswith("p_ok:"):
        pid = int(data.split(":")[1])
        db.execute("UPDATE products SET status='approved', reject_reason='' WHERE id=?", (pid,))
        db.commit()
        p = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
        edit(chat, mid, f"✅ تم نشر {p[2] if p else pid}")
        if p:
            try:
                send(p[1], f"✅ تم نشر منتجك {p[2]}", main_kb=True)
            except:
                pass
        answer(c["id"], "تم النشر")
        return
    if data.startswith("p_reject_temp:"):
        target = int(data.split(":")[1])
        set_state(uid, f"await_reject_reason_temp_p_{target}", {})
        edit(chat, mid, f"⏳ رفض مؤقت للمنتج {target}\nأرسل السبب:")
        answer(c["id"])
        return
    if data.startswith("p_reject_perm:"):
        target = int(data.split(":")[1])
        set_state(uid, f"await_reject_reason_perm_p_{target}", {})
        edit(chat, mid, f"🚫 رفض نهائي للمنتج {target}\nأرسل السبب:")
        answer(c["id"])
        return
    if data.startswith("p_no:"):
        pid = int(data.split(":")[1])
        db.execute("UPDATE products SET status='rejected_temp', reject_reason='كانسل' WHERE id=?", (pid,))
        db.commit()
        edit(chat, mid, f"🔇 كانسل {pid}")
        answer(c["id"])
        return
    if data=="home":
        merch = db.execute("SELECT * FROM merchants WHERE user_id=?", (uid,)).fetchone()
        if merch and merch[4]=="approved":
            kb = []
            kb.append([{"text":"➕ إضافة منتج","callback_data":"add"},{"text":"📊 مبيعاتي","callback_data":"sales"}])
            kb.append([{"text":"🛍️ تصفح","callback_data":"buyer"}])
            edit(chat, mid, f"🏠 لوحة التاجر {merch[1]}", kb)
        else:
            kb = []
            kb.append([{"text":"🛍️ مشتري","callback_data":"buyer"},{"text":"🏪 تاجر","callback_data":"merchant"}])
            edit(chat, mid, "🏠 الرئيسية", kb)
        answer(c["id"])
        return

def main():
    keep_alive()
    setup()
    off = 0
    print("Bot V7 Expanded 612 lines يعمل...")
    while True:
        try:
            r = api("getUpdates", {"timeout":30, "offset":off})
            for u in r.get("result", []):
                off = u["update_id"]+1
                if "message" in u:
                    handle_msg(u["message"])
                elif "callback_query" in u:
                    handle_cb(u["callback_query"])
        except Exception as e:
            print(e)
            time.sleep(2)

if __name__=="__main__":
    main()
