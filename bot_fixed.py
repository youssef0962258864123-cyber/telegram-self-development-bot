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
COMMISSION_RATE = 9
REFERRAL_RATE = 4
API = f"https://api.telegram.org/bot{TOKEN}"
DB = "marketplace.db"

CATEGORIES = ["👕 ملابس","🍳 أواني منزلية","🔥 عروض وخصم","⭐ رائج","👗 موضة","📦 أخرى"]

db = sqlite3.connect(DB, check_same_thread=False)
db.executescript("""
CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY, state TEXT, temp TEXT, points INTEGER DEFAULT 0, purchases INTEGER DEFAULT 0, sales INTEGER DEFAULT 0, referred_by INTEGER, is_banned INTEGER DEFAULT 0, profit_active INTEGER DEFAULT 0, referral_earnings INTEGER DEFAULT 0, referral_balance INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS merchants(user_id INTEGER PRIMARY KEY, store_name TEXT, phone TEXT, city TEXT, doc_photo TEXT, status TEXT DEFAULT 'pending', reject_reason TEXT);
CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY AUTOINCREMENT, merchant_id INTEGER, name TEXT, price INTEGER, photo_id TEXT, description TEXT, category TEXT, status TEXT DEFAULT 'pending', reject_reason TEXT);
CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT, buyer_id INTEGER, product_id INTEGER, merchant_id INTEGER, price INTEGER, commission INTEGER, referral_comm INTEGER, buyer_info TEXT, status TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS referrals(id INTEGER PRIMARY KEY AUTOINCREMENT, referrer_id INTEGER, referred_id INTEGER, created_at TEXT);
CREATE TABLE IF NOT EXISTS referral_profits(id INTEGER PRIMARY KEY AUTOINCREMENT, referrer_id INTEGER, buyer_id INTEGER, order_id INTEGER, amount INTEGER, created_at TEXT);
""")

def api(method, data=None):
    if data is None: data = {}
    try:
        req = Request(API + "/" + method, data=urlencode(data).encode(), headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urlopen(req, timeout=30) as res:
            return json.loads(res.read())
    except Exception as e:
        print(e); return {}

def send(chat_id, text, kb=None, photo=None, main_kb=False):
    if photo:
        payload = {"chat_id": chat_id, "photo": photo, "caption": text}
        if kb: payload["reply_markup"] = json.dumps({"inline_keyboard": kb}, ensure_ascii=False)
        return api("sendPhoto", payload)
    payload = {"chat_id": chat_id, "text": text}
    if kb: payload["reply_markup"] = json.dumps({"inline_keyboard": kb}, ensure_ascii=False)
    elif main_kb: payload["reply_markup"] = json.dumps({"keyboard": [["🔄 تحديث /start", "🔍 بحث"], ["📊 حسابي", "💰 تفعيل الربح"], ["☎️ خدمة العملاء"]], "resize_keyboard": True}, ensure_ascii=False)
    return api("sendMessage", payload)

def edit(chat_id, msg_id, text, kb=None):
    payload = {"chat_id": chat_id, "message_id": msg_id, "text": text}
    if kb: payload["reply_markup"] = json.dumps({"inline_keyboard": kb}, ensure_ascii=False)
    try: return api("editMessageText", payload)
    except:
        payload2 = {"chat_id": chat_id, "message_id": msg_id, "caption": text}
        if kb: payload2["reply_markup"] = json.dumps({"inline_keyboard": kb}, ensure_ascii=False)
        try: return api("editMessageCaption", payload2)
        except: return None

def answer(cid, txt=""): return api("answerCallbackQuery", {"callback_query_id": cid, "text": txt})

def get_temp(uid):
    row = db.execute("SELECT temp FROM users WHERE user_id=?", (uid,)).fetchone()
    if row and row[0]:
        try: return json.loads(row[0])
        except: return {}
    return {}

def set_state(uid, state, tmp=None):
    db.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (uid,))
    if tmp is not None:
        j = json.dumps(tmp, ensure_ascii=False)
        db.execute("UPDATE users SET state=?, temp=? WHERE user_id=?", (state, j, uid))
    else: db.execute("UPDATE users SET state=? WHERE user_id=?", (state, uid))
    db.commit()

def get_state(uid):
    row = db.execute("SELECT state FROM users WHERE user_id=?", (uid,)).fetchone()
    return row[0] if row else None

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
        cmds = [{"command": "start", "description": "🏠 الرئيسية - تحديث وبحث"}]
        api("setMyCommands", {"commands": json.dumps(cmds, ensure_ascii=False)})
    except: pass

def do_search(chat_id, query):
    like = f"%{query}%"
    prods = db.execute("SELECT * FROM products WHERE status='approved' AND (name LIKE? OR description LIKE? OR category LIKE?) ORDER BY id DESC LIMIT 10", (like, like, like)).fetchall()
    if not prods:
        send(chat_id, f"🔍 بحث عن '{query}'\n\n❌ ما لقينا نتائج، جرب كلمة تانية", main_kb=True)
        return
    send(chat_id, f"🔍 نتائج بحث '{query}' - {len(prods)} منتج 👇", main_kb=True)
    for p in prods:
        store = db.execute("SELECT store_name FROM merchants WHERE user_id=?", (p[1],)).fetchone()
        sname = store[0] if store else "متجر"
        kb = [[{"text": f"🛒 شراء {p[3]}ج عند الاستلام", "callback_data": f"buy:{p[0]}"}]]
        send(chat_id, f"📦 {p[2]}\n💰 {p[3]}ج عند الاستلام\n📝 {p[5]}\n🏷️ {p[6]}\n🏪 {sname}", kb, photo=p[4])

def handle_msg(m):
    uid = m["from"]["id"]; chat = m["chat"]["id"]; txt = m.get("text", ""); st = get_state(uid); tmp = get_temp(uid)
    db.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (uid,)); db.commit()
    if db.execute("SELECT is_banned FROM users WHERE user_id=?", (uid,)).fetchone()[0]==1 and uid!=ADMIN_ID:
        send(chat, "🚫 محظور"); return
    if txt in ["🔄 تحديث /start","🔄 تحديث","/start","start"]: txt="/start"
    if txt in ["📊 حسابي","حسابي"]:
        row = db.execute("SELECT points,purchases,sales,profit_active,referral_earnings,referral_balance FROM users WHERE user_id=?", (uid,)).fetchone()
        points=row[0] if row else 0; purch=row[1] if row else 0; sales=row[2] if row else 0; profit_active=row[3] if row else 0; earn=row[4] if row else 0; bal=row[5] if row else 0
        total_ref=db.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (uid,)).fetchone()[0]
        link=f"https://t.me/{BOT_USERNAME}?start={uid}"
        status_txt="✅ مفعل" if profit_active==1 else "❌ غير مفعل"
        send(chat, f"📊 حسابك:\n🛒 {purch}\n📦 {sales}\n⭐ {points}\n\n💰 ربح {REFERRAL_RATE}%:\n{status_txt}\n👥 {total_ref}\n💵 {earn}ج\n💳 {bal}ج\n\n🔗 {link}", main_kb=True)
        if profit_active==0: send(chat, "💰 تفعيل الربح:", [[{"text":"💰 تفعيل الربح 4%","callback_data":"activate_profit"}]])
        return
    if txt in ["💰 تفعيل الربح","تفعيل الربح"]:
        send(chat, f"💰 تفعيل {REFERRAL_RATE}% مدى الحياة\nرابطك: https://t.me/{BOT_USERNAME}?start={uid}", [[{"text":"✅ فعل الربح 4%","callback_data":"activate_profit"}]]); return
    if txt in ["🔍 بحث","بحث"]:
        set_state(uid, "await_search", {}); send(chat, "🔍 أرسل اسم المنتج:", main_kb=True); return
    if txt in ["☎️ خدمة العملاء"]: send(chat, f"☎️ {ADMIN_CONTACT}", main_kb=True); return
    if st=="await_search": set_state(uid, None, {}); do_search(chat, txt); return
    if st=="await_store_name": tmp["store_name"]=txt; set_state(uid, "await_phone", tmp); send(chat, "أرسل رقم واتساب:"); return
    if st=="await_phone": tmp["phone"]=txt; set_state(uid, "await_city", tmp); send(chat, "أرسل مدينتك:"); return
    if st=="await_city": tmp["city"]=txt; set_state(uid, "await_doc", tmp); send(chat, f"⚠️ أرسل صورة مستند (بطاقة/جواز/رخصة)\nالعمولة {COMMISSION_RATE}% عند البيع"); return
    if st=="await_doc":
        if "photo" not in m: send(chat, "❌ أرسل صورة"); return
        doc_id=m["photo"][-1]["file_id"]; db.execute("INSERT OR REPLACE INTO merchants(user_id, store_name, phone, city, doc_photo, status) VALUES(?,?,?,?,?,?)", (uid, tmp["store_name"], tmp["phone"], tmp["city"], doc_id, "pending")); db.commit(); set_state(uid, None, {}); send(chat, f"✅ تم استلام طلبك {tmp['store_name']} العمولة {COMMISSION_RATE}% قيد المراجعة", main_kb=True)
        if ADMIN_ID: send(ADMIN_ID, f"🔔 تاجر جديد + مستند:\n{tmp['store_name']}\n{tmp['phone']}\n{tmp['city']}\nID:{uid}", [[{"text":"✅ قبول","callback_data":f"m_ok:{uid}"}],[{"text":"⏳ رفض مؤقت","callback_data":f"m_reject_temp:{uid}"},{"text":"🚫 رفض نهائي","callback_data":f"m_reject_perm:{uid}"}]], photo=doc_id)
        return
    if st=="await_prod_name": tmp["name"]=txt; set_state(uid, "await_prod_price", tmp); send(chat, "أرسل السعر أرقام:"); return
    if st=="await_prod_price":
        if not txt.isdigit(): send(chat, "أرقام فقط:"); return
        tmp["price"]=int(txt); set_state(uid, "await_prod_cat", tmp); send(chat, "اختر قسم:", cat_kb("setcat")); return
    if st=="await_prod_desc":
        tmp["desc"]=txt; db.execute("INSERT INTO products(merchant_id,name,price,photo_id,description,category,status) VALUES(?,?,?,?,?,?,?)", (uid, tmp["name"], tmp["price"], tmp["photo"], tmp["desc"], tmp.get("cat","📦 أخرى"), "pending")); db.commit(); pid=db.execute("SELECT last_insert_rowid()").fetchone()[0]; set_state(uid, None, {}); comm=int(tmp["price"]*COMMISSION_RATE/100); send(chat, f"✅ تم رفع المنتج {tmp.get('cat')} السعر {tmp['price']}ج عمولة {comm}ج بانتظار الموافقة", main_kb=True)
        if ADMIN_ID: send(ADMIN_ID, f"🔔 منتج جديد:\n{tmp['name']} - {tmp['price']}ج", [[{"text":"✅ قبول","callback_data":f"p_ok:{pid}"}],[{"text":"⏳ رفض مؤقت","callback_data":f"p_reject_temp:{pid}"},{"text":"🚫 رفض نهائي","callback_data":f"p_reject_perm:{pid}"}]], photo=tmp["photo"])
        return
    if st=="await_cod_info":
        commission=int(tmp["price"]*COMMISSION_RATE/100); db.execute("INSERT INTO orders(buyer_id,product_id,merchant_id,price,commission,buyer_info,status,created_at) VALUES(?,?,?,?,?,?,?,?)", (uid, tmp["pid"], tmp["mid"], tmp["price"], commission, txt, "pending_shipment", time.strftime("%Y-%m-%d"))); db.commit(); oid=db.execute("SELECT last_insert_rowid()").fetchone()[0]; db.execute("UPDATE users SET purchases=purchases+1 WHERE user_id=?", (uid,)); db.commit(); set_state(uid, None, {}); send(chat, f"✅ طلبك #{oid} تم {tmp['pname']} {tmp['price']}ج عند الاستلام", main_kb=True); send(tmp["mid"], f"🔔 طلب جديد #{oid}\n{tmp['pname']}\n{tmp['price']}ج عمولة {commission}ج\n{txt}", [[{"text":f"📦 تم الشحن #{oid}","callback_data":f"ship:{oid}"}]]); return
    if "photo" in m and st=="await_prod_photo": tmp["photo"]=m["photo"][-1]["file_id"]; set_state(uid, "await_prod_name", tmp); send(chat, "الصورة وصلت ✅ أرسل اسم المنتج:"); return
    if st and st.startswith("await_reject_reason_"):
        reason=txt; parts=st.split("_"); final_action=parts[3]; typ=parts[4]; target_id=int(parts[5])
        if typ=="m":
            new_status="rejected_perm" if final_action=="perm" else "rejected_temp"; db.execute("UPDATE merchants SET status=?, reject_reason=? WHERE user_id=?", (new_status, reason, target_id)); db.commit()
            send(chat, f"✅ رفض {target_id}");
            try: send(target_id, f"❌ رفض متجرك:\n{reason}", main_kb=True)
            except: pass
        else:
            new_status="rejected_perm" if final_action=="perm" else "rejected_temp"; db.execute("UPDATE products SET status=?, reject_reason=? WHERE id=?", (new_status, reason, target_id)); db.commit(); send(chat, f"✅ رفض منتج {target_id}")
        set_state(uid, None, {}); return
    if txt.startswith("/start"):
        parts=txt.split()
        if len(parts)>1 and parts[1].isdigit():
            ref_id=int(parts[1])
            if ref_id!=uid:
                already=db.execute("SELECT * FROM referrals WHERE referred_id=?", (uid,)).fetchone()
                user_ref=db.execute("SELECT referred_by FROM users WHERE user_id=?", (uid,)).fetchone()
                if not already and (not user_ref or not user_ref[0]):
                    db.execute("INSERT INTO referrals(referrer_id,referred_id,created_at) VALUES(?,?,?)", (ref_id, uid, time.strftime("%Y-%m-%d"))); db.execute("UPDATE users SET points=points+10 WHERE user_id=?", (ref_id,)); db.execute("UPDATE users SET referred_by=? WHERE user_id=?", (ref_id, uid)); db.commit()
                    try: send(ref_id, f"🎉 إحالة جديدة! +10 نقاط ستكسب {REFERRAL_RATE}% مدى الحياة!")
                    except: pass
        merch=db.execute("SELECT * FROM merchants WHERE user_id=?", (uid,)).fetchone()
        if merch and merch[5]=="approved":
            cnt=db.execute("SELECT COUNT(*) FROM products WHERE merchant_id=? AND status='approved'", (uid,)).fetchone()[0]
            kb=[[{"text":"➕ إضافة منتج","callback_data":"add"},{"text":"📊 مبيعاتي","callback_data":"sales"}],[{"text":"🛍️ تصفح السوق","callback_data":"buyer"}],[{"text":"🔍 بحث","callback_data":"search"}]]
            if uid==ADMIN_ID: kb.append([{"text":"👑 لوحة الأدمن","callback_data":"admin_panel"}])
            send(chat, f"أهلا يا صاحب متجر {merch[1]} ✅ منتجاتك {cnt} العمولة {COMMISSION_RATE}%", kb, main_kb=True); return
        if merch and merch[5]=="pending": send(chat, f"متجرك '{merch[1]}' قيد المراجعة ⏳", main_kb=True); return
        kb=[[{"text":"🛍️ أنا مشتري","callback_data":"buyer"},{"text":"🏪 أنا تاجر","callback_data":"merchant"}],[{"text":"🔍 بحث عن منتج","callback_data":"search"},{"text":f"💰 تفعيل الربح {REFERRAL_RATE}%","callback_data":"activate_profit"}],[{"text":"☎️ خدمة العملاء","callback_data":"support"}]]
        if uid==ADMIN_ID: kb.append([{"text":"👑 لوحة الأدمن","callback_data":"admin_panel"}])
        send(chat, f"أهلا بك في سوق طوّر نفسك 🌟\n\nللتجار: العمولة {COMMISSION_RATE}% + مستند\nللمسوقين: فعل الربح واكسب {REFERRAL_RATE}% مدى الحياة!\nللمشترين: اكتب اسم المنتج للبحث مباشرة", kb, main_kb=True); return
    if len(txt)>=2 and st is None and txt not in ["📊 حسابي","💰 تفعيل الربح","☎️ خدمة العملاء","🔄 تحديث /start","🔍 بحث","حسابي"]:
        do_search(chat, txt); return

def handle_cb(c):
    uid=c["from"]["id"]; chat=c["message"]["chat"]["id"]; mid=c["message"]["message_id"]; data=c["data"]
    if data=="search": set_state(uid, "await_search", {}); edit(chat, mid, "🔍 أرسل اسم المنتج:"); answer(c["id"]); return
    if data=="activate_profit":
        row=db.execute("SELECT profit_active FROM users WHERE user_id=?", (uid,)).fetchone()
        if row and row[0]==1: edit(chat, mid, f"✅ مفعل مسبقا!\nhttps://t.me/{BOT_USERNAME}?start={uid}")
        else: db.execute("UPDATE users SET profit_active=1 WHERE user_id=?", (uid,)); db.commit(); edit(chat, mid, f"🎉 تم تفعيل الربح {REFERRAL_RATE}% مدى الحياة!\n🔗 رابطك:\nhttps://t.me/{BOT_USERNAME}?start={uid}\nشاركه واكسب مدى الحياة!")
        answer(c["id"], "تم التفعيل!"); return
    if data=="my_referral_earnings":
        row=db.execute("SELECT referral_earnings,referral_balance FROM users WHERE user_id=?", (uid,)).fetchone(); earn=row[0] if row else 0; bal=row[1] if row else 0; total_ref=db.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (uid,)).fetchone()[0]
        edit(chat, mid, f"💰 أرباح الإحالة {REFERRAL_RATE}%:\n👥 {total_ref}\n💵 {earn}ج\n💳 {bal}ج\n🔗 https://t.me/{BOT_USERNAME}?start={uid}", [[{"text":"🔙 رجوع","callback_data":"home"}]]); answer(c["id"]); return
    if data=="admin_panel" and uid==ADMIN_ID:
        total_users=db.execute("SELECT COUNT(*) FROM users").fetchone()[0]; total_merch=db.execute("SELECT COUNT(*) FROM merchants WHERE status='approved'").fetchone()[0]; pending_m=db.execute("SELECT COUNT(*) FROM merchants WHERE status='pending'").fetchone()[0]; total_comm=db.execute("SELECT SUM(commission) FROM orders WHERE status='completed'").fetchone()[0] or 0; total_ref=db.execute("SELECT SUM(amount) FROM referral_profits").fetchone()[0] or 0
        edit(chat, mid, f"👑 لوحة الأدمن\n👥 {total_users}\n🏪 {total_merch}\n⏳ {pending_m}\n💰 عمولة {COMMISSION_RATE}%: {total_comm}ج\n💸 إحالات {REFERRAL_RATE}%: {total_ref}ج\nصافي: {total_comm-total_ref}ج", [[{"text":f"👥 المستخدمين ({total_users})","callback_data":"admin_users"}],[{"text":f"🏪 التجار ({total_merch})","callback_data":"admin_merchants"}],[{"text":f"⏳ معلق ({pending_m})","callback_data":"admin_pending"}],[{"text":f"💰 أرباح {total_comm}ج","callback_data":"admin_profits"}],[{"text":"🏠 الرئيسية","callback_data":"home"}]]); answer(c["id"]); return
    if data=="admin_pending" and uid==ADMIN_ID:
        pend=db.execute("SELECT user_id,store_name,phone,city,doc_photo FROM merchants WHERE status='pending' LIMIT 5").fetchall()
        if not pend: edit(chat, mid, "لا يوجد طلبات", [[{"text":"🔙 رجوع","callback_data":"admin_panel"}]])
        else:
            edit(chat, mid, f"⏳ {len(pend)} طلبات + مستندات")
            for m in pend: send(chat, f"🔔 تاجر:\n{m[1]}\n{m[2]}\n{m[3]}\nID:{m[0]}", [[{"text":"✅ قبول","callback_data":f"m_ok:{m[0]}"}],[{"text":"⏳ رفض مؤقت","callback_data":f"m_reject_temp:{m[0]}"},{"text":"🚫 رفض نهائي","callback_data":f"m_reject_perm:{m[0]}"}]], photo=m[4])
        answer(c["id"]); return
    if data=="my_pending":
        orders=db.execute("SELECT id,price,commission,buyer_info,status FROM orders WHERE merchant_id=? AND status IN ('pending_shipment','shipped') ORDER BY id DESC LIMIT 10", (uid,)).fetchall()
        if not orders: edit(chat, mid, "لا يوجد طلبات", [[{"text":"🔙 رجوع","callback_data":"home"}]])
        else:
            txt="📦 طلبات قيد الشحن:\n\n"; kb=[]
            for o in orders:
                txt+=f"#{o[0]} - {o[1]}ج عمولة {o[2]}ج {o[4]}\n{o[3][:30]}\n\n"
                if o[4]=="pending_shipment": kb.append([{"text":f"📦 شحن #{o[0]}","callback_data":f"ship:{o[0]}"}])
            kb.append([{"text":"🔙 رجوع","callback_data":"home"}]); edit(chat, mid, txt, kb)
        answer(c["id"]); return
    if data.startswith("ship:"):
        oid=int(data.split(":")[1]); order=db.execute("SELECT buyer_id,merchant_id,price FROM orders WHERE id=?", (oid,)).fetchone()
        if not order or order[1]!=uid: answer(c["id"], "ليس طلبك"); return
        db.execute("UPDATE orders SET status='shipped' WHERE id=?", (oid,)); db.commit(); edit(chat, mid, f"✅ تم شحن #{oid}"); send(order[0], f"📦 طلبك #{oid} تم شحنه! {order[2]}ج عند الاستلام هل استلمت؟", [[{"text":f"✅ تأكيد استلام #{oid}","callback_data":f"confirm:{oid}"}],[{"text":f"❌ مشكلة #{oid}","callback_data":f"dispute:{oid}"}]]); answer(c["id"]); return
    if data.startswith("confirm:"):
        oid=int(data.split(":")[1]); order=db.execute("SELECT buyer_id,merchant_id,price,commission FROM orders WHERE id=?", (oid,)).fetchone()
        if not order or order[0]!=uid: answer(c["id"], "ليس طلبك"); return
        buyer_id=order[0]; merchant_id=order[1]; price=order[2]; ref_row=db.execute("SELECT referred_by FROM users WHERE user_id=?", (buyer_id,)).fetchone(); referral_amount=0
        if ref_row and ref_row[0]:
            referrer_id=ref_row[0]; active=db.execute("SELECT profit_active FROM users WHERE user_id=?", (referrer_id,)).fetchone()
            if active and active[0]==1:
                referral_amount=int(price*REFERRAL_RATE/100); db.execute("INSERT INTO referral_profits(referrer_id,buyer_id,order_id,amount,created_at) VALUES(?,?,?,?,?)", (referrer_id, buyer_id, oid, referral_amount, time.strftime("%Y-%m-%d"))); db.execute("UPDATE users SET referral_earnings=referral_earnings+?, referral_balance=referral_balance+? WHERE user_id=?", (referral_amount, referral_amount, referrer_id))
                try: send(referrer_id, f"💰 ربح إحالة جديد! المشتري {buyer_id} اشترى ب {price}ج ربحك {referral_amount}ج ({REFERRAL_RATE}%) مدى الحياة!")
                except: pass
        db.execute("UPDATE orders SET status='completed', referral_comm=? WHERE id=?", (referral_amount, oid)); db.execute("UPDATE users SET sales=sales+1 WHERE user_id=?", (merchant_id,)); db.commit(); edit(chat, mid, f"✅ تم تأكيد استلام #{oid}"); send(merchant_id, f"🎉 المشتري أكد استلام #{oid} السعر {price}ج عمولة {order[3]}ج"); answer(c["id"]); return
    if data.startswith("dispute:"):
        oid=int(data.split(":")[1]); db.execute("UPDATE orders SET status='disputed' WHERE id=?", (oid,)); db.commit(); edit(chat, mid, f"⚠️ شكوى #{oid} الإدارة ستتواصل"); answer(c["id"]); return
    if data=="buyer": edit(chat, mid, "🛍️ اختر القسم أو ابحث:", cat_kb("browse")+[[{"text":"🔍 كل المنتجات","callback_data":"browse:all"}],[{"text":"🔍 بحث بالاسم","callback_data":"search"}],[{"text":"🏠 الرئيسية","callback_data":"home"}]]); answer(c["id"]); return
    if data.startswith("browse:"):
        cat=data.split(":",1)[1]
        if cat=="all": prods=db.execute("SELECT * FROM products WHERE status='approved' ORDER BY id DESC LIMIT 10").fetchall(); title="كل المنتجات"
        else: prods=db.execute("SELECT * FROM products WHERE status='approved' AND category=? ORDER BY id DESC LIMIT 10", (cat,)).fetchall(); title=f"قسم {cat}"
        if not prods: edit(chat, mid, f"{title}\nما في منتجات", [[{"text":"🔙 رجوع","callback_data":"buyer"}]])
        else:
            edit(chat, mid, f"{title} - {len(prods)} منتج")
            for p in prods: sname=db.execute("SELECT store_name FROM merchants WHERE user_id=?", (p[1],)).fetchone(); sname=sname[0] if sname else "متجر"; send(chat, f"📦 {p[2]}\n💰 {p[3]}ج عند الاستلام\n{sname}", [[{"text":f"🛒 شراء {p[3]}ج","callback_data":f"buy:{p[0]}"}]], photo=p[4])
        answer(c["id"]); return
    if data=="merchant":
        merch=db.execute("SELECT * FROM merchants WHERE user_id=?", (uid,)).fetchone()
        if merch:
            if merch[5]=="pending": edit(chat, mid, "طلبك قيد المراجعة ⏳")
            elif merch[5]=="approved": edit(chat, mid, f"أهلا {merch[1]} ✅ العمولة {COMMISSION_RATE}%", [[{"text":"➕ إضافة منتج","callback_data":"add"},{"text":"📊 مبيعاتي","callback_data":"sales"}]])
            else: set_state(uid, "await_store_name", {}); edit(chat, mid, f"تم رفضك سابقا. أرسل اسم المتجر الجديد (العمولة {COMMISSION_RATE}%):")
        else: set_state(uid, "await_store_name", {}); edit(chat, mid, f"أرسل اسم المتجر (العمولة {COMMISSION_RATE}%):")
        answer(c["id"]); return
    if data.startswith("setcat:"): cat=data.split(":",1)[1]; tmp=get_temp(uid); tmp["cat"]=cat; set_state(uid, "await_prod_desc", tmp); edit(chat, mid, f"اخترت {cat} ✅ أرسل وصف:"); answer(c["id"]); return
    if data=="add": set_state(uid, "await_prod_photo", {}); send(chat, "أرسل صورة المنتج:"); answer(c["id"]); return
    if data=="sales": total=db.execute("SELECT COUNT(*) FROM orders WHERE merchant_id=? AND status='completed'", (uid,)).fetchone()[0]; total_comm=db.execute("SELECT SUM(commission) FROM orders WHERE merchant_id=? AND status='completed'", (uid,)).fetchone()[0] or 0; cnt=db.execute("SELECT COUNT(*) FROM products WHERE merchant_id=? AND status='approved'", (uid,)).fetchone()[0]; edit(chat, mid, f"📊 مبيعاتك:\n📦 {cnt}\n✅ {total}\n💰 عمولة دفعتها: {total_comm}ج", [[{"text":"📋 آخر الطلبات","callback_data":"orders"},{"text":"🏠 الرئيسية","callback_data":"home"}]]); answer(c["id"]); return
    if data=="orders": ords=db.execute("SELECT id,price,commission,status FROM orders WHERE merchant_id=? ORDER BY id DESC LIMIT 5", (uid,)).fetchall(); t="📋 آخر 5:\n\n" if ords else "ما جاك طلبات";
        if ords:
            for o in ords: t+=f"#{o[0]} - {o[1]}ج عمولة {o[2]}ج {o[3]}\n"
        edit(chat, mid, t, [[{"text":"🔙 رجوع","callback_data":"sales"}]]); answer(c["id"]); return
    if data.startswith("buy:"): pid=int(data.split(":")[1]); p=db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone(); comm=int(p[3]*COMMISSION_RATE/100); set_state(uid, "await_cod_info", {"pid":p[0],"mid":p[1],"price":p[3],"pname":p[2]}); send(chat, f"📦 {p[2]}\n💰 {p[3]}ج عند الاستلام فقط\nأرسل الاسم - الهاتف - العنوان:"); answer(c["id"]); return
    if data.startswith("m_ok:"): mid_t=int(data.split(":")[1]); db.execute("UPDATE merchants SET status='approved', reject_reason='' WHERE user_id=?", (mid_t,)); db.commit(); edit(chat, mid, f"✅ تم قبول التاجر {mid_t}");
        try: send(mid_t, f"🎉 تم قبول متجرك. العمولة {COMMISSION_RATE}%\n/start", main_kb=True)
        except: pass
        answer(c["id"]); return
    if data.startswith("m_reject_temp:"): target=int(data.split(":")[1]); set_state(uid, f"await_reject_reason_temp_m_{target}", {}); edit(chat, mid, f"⏳ رفض مؤقت للتاجر {target}\nأرسل السبب:"); answer(c["id"]); return
    if data.startswith("m_reject_perm:"): target=int(data.split(":")[1]); set_state(uid, f"await_reject_reason_perm_m_{target}", {}); edit(chat, mid, f"🚫 رفض نهائي للتاجر {target}\nأرسل السبب:"); answer(c["id"]); return
    if data.startswith("m_no:"): mid_t=int(data.split(":")[1]); db.execute("UPDATE merchants SET status='rejected_temp', reject_reason='رفض صامت' WHERE user_id=?", (mid_t,)); db.commit(); edit(chat, mid, f"🔇 تم رفض {mid_t} بصمت"); answer(c["id"]); return
    if data.startswith("p_ok:"): pid=int(data.split(":")[1]); db.execute("UPDATE products SET status='approved', reject_reason='' WHERE id=?", (pid,)); db.commit(); p=db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone(); edit(chat, mid, f"✅ تم نشر {p[2] if p else pid}");
        if p:
            try: send(p[1], f"✅ تم نشر منتجك {p[2]}", main_kb=True)
            except: pass
        answer(c["id"]); return
    if data.startswith("p_reject_temp:"): target=int(data.split(":")[1]); set_state(uid, f"await_reject_reason_temp_p_{target}", {}); edit(chat, mid, f"⏳ رفض مؤقت للمنتج {target}\nأرسل السبب:"); answer(c["id"]); return
    if data.startswith("p_reject_perm:"): target=int(data.split(":")[1]); set_state(uid, f"await_reject_reason_perm_p_{target}", {}); edit(chat, mid, f"🚫 رفض نهائي للمنتج {target}\nأرسل السبب:"); answer(c["id"]); return
    if data.startswith("p_no:"): pid=int(data.split(":")[1]); db.execute("UPDATE products SET status='rejected_temp', reject_reason='كانسل' WHERE id=?", (pid,)); db.commit(); edit(chat, mid, f"🔇 كانسل {pid}"); answer(c["id"]); return
    if data=="home": edit(chat, mid, "🏠 الرئيسية", [[{"text":"🛍️ مشتري","callback_data":"buyer"},{"text":"🏪 تاجر","callback_data":"merchant"}]]); answer(c["id"]); return

def main():
    keep_alive(); setup(); off=0
    print(f"Bot V10 FINAL - {COMMISSION_RATE}% + {REFERRAL_RATE}% + Doc + Search + Confirm")
    while True:
        try:
            r=api("getUpdates", {"timeout":30, "offset":off})
            for u in r.get("result", []):
                off=u["update_id"]+1
                if "message" in u: handle_msg(u["message"])
                elif "callback_query" in u: handle_cb(u["callback_query"])
        except Exception as e:
            print(e); time.sleep(2)

if __name__=="__main__":
    main()
