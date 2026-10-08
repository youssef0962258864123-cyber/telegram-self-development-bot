from flask import Flask
import threading, os, json, time, sqlite3, re, unicodedata
from difflib import SequenceMatcher
from urllib.request import Request, urlopen
from urllib.parse import urlencode

# --- خادم الحفاظ على عمل البوت ---
app = Flask('')
@app.route('/')
def home(): return "Bot is Alive!"
def keep_alive():
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=10000), daemon=True).start()

# --- إعدادات البوت وقاعدة البيانات ---
TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
BOT_USERNAME = os.environ.get("BOT_USERNAME", "your_bot")
ADMIN_CONTACT = os.environ.get("ADMIN_CONTACT", "@admin")
COMMISSION_RATE, REFERRAL_RATE = 9, 4
API = f"https://api.telegram.org/bot{TOKEN}"
DB = "marketplace.db"

CATEGORIES = ["👕 ملابس", "🍳 أواني منزلية", "🔥 عروض وخصم", "⭐ رائج", "👗 موضة", "📦 أخرى", "🌾 أعلاف حيوانات", "💄 منتجات تجميل", "🌱 أسمدة زراعية", "💪 منتجات جيم"]

db = sqlite3.connect(DB, check_same_thread=False)

# دالة التعامل الموحد مع قاعدة البيانات
def query_db(sql, params=(), fetch=None, commit=False):
    cur = db.cursor()
    cur.execute(sql, params)
    res = cur.fetchone() if fetch == "one" else (cur.fetchall() if fetch == "all" else None)
    if commit or sql.strip().upper().startswith(("INSERT", "UPDATE", "DELETE", "CREATE", "ALTER")):
        db.commit()
    return res

# إنشاء الجداول وتحديث الأعمدة تلقائياً بأقل أسطر ممكنة
query_db('''
CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY, state TEXT, temp TEXT, points INTEGER DEFAULT 0, purchases INTEGER DEFAULT 0, sales INTEGER DEFAULT 0, referred_by INTEGER, is_banned INTEGER DEFAULT 0, profit_active INTEGER DEFAULT 0, referral_earnings INTEGER DEFAULT 0, referral_balance INTEGER DEFAULT 0, unpaid_commission INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS merchants(user_id INTEGER PRIMARY KEY, store_name TEXT, phone TEXT, city TEXT, doc_photo TEXT, status TEXT DEFAULT 'pending', reject_reason TEXT);
CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY AUTOINCREMENT, merchant_id INTEGER, name TEXT, price INTEGER, photo_id TEXT, description TEXT, category TEXT, status TEXT DEFAULT 'pending', reject_reason TEXT, base_price INTEGER);
CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT, buyer_id INTEGER, product_id INTEGER, merchant_id INTEGER, price INTEGER, commission INTEGER, referral_comm INTEGER, buyer_info TEXT, status TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS referrals(id INTEGER PRIMARY KEY AUTOINCREMENT, referrer_id INTEGER, referred_id INTEGER, created_at TEXT);
CREATE TABLE IF NOT EXISTS referral_profits(id INTEGER PRIMARY KEY AUTOINCREMENT, referrer_id INTEGER, buyer_id INTEGER, order_id INTEGER, amount INTEGER, created_at TEXT);
''')

# التحديثات التلقائية (Migrations) في حلقة واحدة
alter_columns = [
    ("users", "profit_active INTEGER DEFAULT 0"), ("users", "referral_earnings INTEGER DEFAULT 0"),
    ("users", "referral_balance INTEGER DEFAULT 0"), ("users", "is_banned INTEGER DEFAULT 0"),
    ("users", "unpaid_commission INTEGER DEFAULT 0"), ("merchants", "doc_photo TEXT"),
    ("merchants", "reject_reason TEXT"), ("products", "reject_reason TEXT"),
    ("products", "base_price INTEGER"), ("orders", "price INTEGER"),
    ("orders", "commission INTEGER"), ("orders", "referral_comm INTEGER"), ("orders", "created_at TEXT")
]
for tbl, col in alter_columns:
    try: query_db(f"ALTER TABLE {tbl} ADD COLUMN {col}")
    except: pass

# --- دوال المساعدة لـ API التليجرام ---
def api(method, data=None):
    try:
        req = Request(f"{API}/{method}", data=urlencode(data or {}).encode(), headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urlopen(req, timeout=30) as res: return json.loads(res.read())
    except Exception as e:
        print(f"API Error ({method}):", e)
        return {}

def send(chat_id, text, kb=None, photo=None, main_kb=False):
    payload = {"chat_id": chat_id, ("caption" if photo else "text"): text}
    if photo: payload["photo"] = photo
    
    if kb:
        payload["reply_markup"] = json.dumps({"inline_keyboard": kb}, ensure_ascii=False)
    elif main_kb:
        m = query_db("SELECT status FROM merchants WHERE user_id=?", (chat_id,), fetch="one")
        debt = get_user_debt(chat_id)
        store_btn = "🏪 لوحة متجري" if (m and m[0] == "approved") else ("🏪 حالة متجري" if m else "🏪 إنشاء حساب تاجر")
        keyboard = [["🛍️ تسوق", "🔍 بحث عن منتج"], [store_btn, "💰 الربح من البوت"]]
        if debt > 0: keyboard.append(["💳 دفع العمولة"])
        if chat_id == ADMIN_ID and ADMIN_ID: keyboard.append(["👑 لوحة الأدمن"])
        payload["reply_markup"] = json.dumps({"keyboard": keyboard, "resize_keyboard": True}, ensure_ascii=False)
        
    return api("sendPhoto" if photo else "sendMessage", payload)

def edit(chat_id, msg_id, text, kb=None):
    payload = {"chat_id": chat_id, "message_id": msg_id, "text": text}
    if kb is not None: payload["reply_markup"] = json.dumps({"inline_keyboard": kb}, ensure_ascii=False)
    res = api("editMessageText", payload)
    if not (res and res.get("ok")):
        payload["caption"] = payload.pop("text")
        res = api("editMessageCaption", payload)
    return res

def answer(cid, txt=""): return api("answerCallbackQuery", {"callback_query_id": cid, "text": txt})

# --- دوال إدارة الحالات والرصيد ---
def get_user_session(uid):
    row = query_db("SELECT state, temp FROM users WHERE user_id=?", (uid,), fetch="one")
    if not row: return None, {}
    try: tmp = json.loads(row[1]) if row[1] else {}
    except: tmp = {}
    return row[0], tmp

def set_state(uid, state, tmp=None):
    query_db("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (uid,))
    j_tmp = json.dumps(tmp, ensure_ascii=False) if tmp is not None else None
    query_db("UPDATE users SET state=?, temp=? WHERE user_id=?", (state, j_tmp, uid))

def get_user_debt(uid):
    row = query_db("SELECT unpaid_commission FROM users WHERE user_id=?", (uid,), fetch="one")
    return row[0] if row and row[0] else 0

def check_debt_and_block(chat_id, uid):
    debt = get_user_debt(uid)
    if debt > 0:
        send(chat_id, f"⚠️ **تنبيه:** لديك عمولة مستحقة قدرها ({debt} جنيه).\nلا يمكنك إجراء طلبات جديدة حتى السداد.", [[{"text": "💳 دفع العمولة العليك", "callback_data": "pay_commission"}]], main_kb=True)
        return True
    return False

def cat_kb(prefix):
    return [[{"text": CATEGORIES[i], "callback_data": f"{prefix}:{CATEGORIES[i]}"}] + 
            ([{"text": CATEGORIES[i+1], "callback_data": f"{prefix}:{CATEGORIES[i+1]}"}] if i+1 < len(CATEGORIES) else []) 
            for i in range(0, len(CATEGORIES), 2)]

# --- البحث المتقدم ---
def normalize_search_text(val):
    val = unicodedata.normalize("NFKC", str(val or "")).lower()
    val = re.sub(r"[\u064b-\u065f\u0670\u0640]", "", val)
    return re.sub(r"[^\w\s]", " ", val.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي"}))).strip()

def fuzzy_word_score(q_word, p_words):
    best = 0.0
    for w in p_words:
        if q_word == w: return 1.0
        if min(len(q_word), len(w)) >= 3 and (q_word in w or w in q_word): best = max(best, 0.86)
        else: best = max(best, SequenceMatcher(None, q_word, w).ratio())
    return best

def do_search(chat_id, query):
    norm_q = normalize_search_text(query)
    q_words = norm_q.split()
    if not q_words: return send(chat_id, "أرسل اسم المنتج أو جزءًا من اسمه للبحث.", main_kb=True)

    products = query_db("SELECT * FROM products WHERE status='approved' ORDER BY id DESC", fetch="all")
    ranked = []
    for p in products:
        comb = normalize_search_text(f"{p[2]} {p[5]} {p[6]}")
        if norm_q in comb:
            score = 1.0 + (0.15 if norm_q in normalize_search_text(p[2]) else 0.0)
        else:
            words = comb.split()
            scores = [fuzzy_word_score(w, words) for w in q_words]
            matched = sum(sc >= (0.70 if len(w)==3 else 0.60 if len(w)>=4 else 1.0) for sc, w in zip(scores, q_words))
            if (matched / len(q_words)) < 0.5 or (sum(scores)/len(scores)) < 0.60: continue
            score = (sum(scores)/len(scores)) + (0.12 if any(w in normalize_search_text(p[2]) for w in q_words) else 0.0)
        ranked.append((score, p))

    ranked.sort(key=lambda x: (x[0], x[1][0]), reverse=True)
    prods = [x[1] for x in ranked[:10]]
    if not prods: return send(chat_id, f"🔍 نتائج البحث عن «{query}»\n\n❌ ما لقينا نتائج.", main_kb=True)
    
    send(chat_id, f"🔍 نتائج البحث عن «{query}» - {len(prods)} منتج 👇", main_kb=True)
    for p in prods:
        store = query_db("SELECT store_name FROM merchants WHERE user_id=?", (p[1],), fetch="one")
        sname = store[0] if store else "متجر"
        send(chat_id, f"📦 {p[2]}\n💰 {p[3]}ج عند الاستلام\n📝 {p[5]}\n🏷️ {p[6]}\n🏪 {sname}", [[{"text": f"🛒 شراء {p[3]}ج عند الاستلام", "callback_data": f"buy:{p[0]}"}]], photo=p[4])

def show_market(chat_id):
    kb = cat_kb("browse") + [[{"text": "🛍️ كل المنتجات", "callback_data": "browse:all"}], [{"text": "🔍 بحث عن منتج", "callback_data": "search"}]]
    send(chat_id, "🛍️ خدمات التسوق\nاختر قسمًا لتصفح المنتجات أو ابحث باسم المنتج:", kb)

def open_merchant(chat_id, uid, message_id=None):
    set_state(uid, None, {})
    m = query_db("SELECT * FROM merchants WHERE user_id=?", (uid,), fetch="one")
    if m:
        status = m[5] if len(m) >= 6 else "pending"
        if status == "banned": text, kb = "🚫 حساب التاجر موقوف.", None
        elif status == "pending": text, kb = f"متجرك «{m[1]}» قيد المراجعة ⏳", None
        elif status == "approved":
            p_cnt = query_db("SELECT COUNT(*) FROM products WHERE merchant_id=? AND status='approved'", (uid,), fetch="one")[0]
            o_cnt = query_db("SELECT COUNT(*) FROM orders WHERE merchant_id=? AND status='pending_shipment'", (uid,), fetch="one")[0]
            text = f"أهلاً يا صاحب متجر {m[1]} ✅\nمنتجاتك: {p_cnt}\nطلبات قيد الشحن: {o_cnt}"
            kb = [[{"text": "➕ إضافة منتج", "callback_data": "add"}, {"text": "📊 مبيعاتي", "callback_data": "sales"}],
                  [{"text": f"📦 طلبات تحت الشحن ({o_cnt})", "callback_data": "my_pending"}],
                  [{"text": "🛍️ تصفح السوق", "callback_data": "buyer"}]]
            if uid == ADMIN_ID and ADMIN_ID: kb.append([{"text": "👑 لوحة الأدمن", "callback_data": "admin_panel"}])
        else:
            set_state(uid, "await_store_name", {})
            text, kb = "تم رفض الطلب السابق. أرسل اسم المتجر الجديد:", None
    else:
        set_state(uid, "await_store_name", {})
        text, kb = "✅ لنبدأ إنشاء حسابك التجاري.\nأرسل اسم المتجر:", None

    if message_id: edit(chat_id, message_id, text, kb or [])
    else: send(chat_id, text, kb, main_kb=(kb is None))

def send_payment_info(chat, uid):
    debt = get_user_debt(uid)
    set_state(uid, "await_payment_receipt", {})
    send(chat, f"🏦 **بيانات الدفع لسداد العمولة ({debt:,.0f} جنيه):**\n\n• **تطبيق:** بنكك (Bankak)\n• **رقم الحساب:** `7696230`\n• **الاسم:** بدور عبدالكريم عيسى النعيم\n\n📸 أرسل صورة إشعار التحويل هنا لتأكيد الدفع.", main_kb=True)

# --- معالجة الرسائل ---
def handle_msg(m):
    uid, chat, txt = m["from"]["id"], m["chat"]["id"], m.get("text", "")
    st, tmp = get_user_session(uid)
    query_db("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (uid,))

    banned = query_db("SELECT is_banned FROM users WHERE user_id=?", (uid,), fetch="one")
    if banned and banned[0] == 1 and uid != ADMIN_ID: return send(chat, f"🚫 محظور، تواصل: {ADMIN_CONTACT}")

    if txt in ["💳 دفع العمولة", "دفع العمولة"]: return send_payment_info(chat, uid)
    if txt in ["🛍️ تسوق", "تسوق", "🛍️ تصفح السوق"]: set_state(uid, None); return show_market(chat)
    if txt in ["🔍 بحث عن منتج", "بحث عن منتج", "🔍 بحث", "بحث"]: set_state(uid, "await_search"); return send(chat, "🔍 أرسل اسم المنتج للبحث:", main_kb=True)
    if txt in ["🏪 إنشاء حساب تاجر", "إنشاء حساب تاجر"]: return send(chat, f"🏪 إنشاء حساب تاجر\nعمولة المتجر {COMMISSION_RATE}% منها {REFERRAL_RATE}% للمسوقين.", [[{"text": "✅ أنا تاجر الآن", "callback_data": "merchant"}]])
    if txt in ["✅ أنا تاجر الآن", "أنا تاجر الآن", "🏪 لوحة متجري", "🏪 حالة متجري", "لوحة متجري"]: return open_merchant(chat, uid)
    if txt in ["👑 لوحة الأدمن", "/admin"] and uid == ADMIN_ID: return send(chat, "👑 افتح لوحة الإدارة:", [[{"text": "👑 لوحة الأدمن", "callback_data": "admin_panel"}]])
    
    if txt in ["💰 الربح من البوت", "الربح من البوت"]:
        query_db("UPDATE users SET profit_active=1 WHERE user_id=?", (uid,))
        return send(chat, f"🎉 تم تفعيل الربح {REFERRAL_RATE}٪\n\n🔗 رابطك:\nhttps://t.me/{BOT_USERNAME}?start={uid}", main_kb=True)

    if txt in ["📊 حسابي", "حسابي"]:
        u = query_db("SELECT points, purchases, sales, profit_active, referral_earnings, referral_balance, unpaid_commission FROM users WHERE user_id=?", (uid,), fetch="one") or (0,0,0,0,0,0,0)
        t_ref = query_db("SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (uid,), fetch="one")[0]
        t_comm = query_db("SELECT SUM(commission) FROM orders WHERE merchant_id=? AND status='completed'", (uid,), fetch="one")[0] or 0
        msg = f"📊 حسابك:\n🛒 اشتريت: {u[1]} | 📦 بعت: {u[2]} | ⭐ نقاطك: {u[0]}\n💳 العمولة المستحقة: {u[6]}ج\n\n👥 إحالاتك: {t_ref} | 💵 أرباحك: {u[4]}ج | 💳 رصيدك: {u[5]}ج\n\n🔗 رابط إحالتك:\nhttps://t.me/{BOT_USERNAME}?start={uid}\n\n💰 عمولة مبيعاتك: {t_comm}ج"
        kb = ([{"text": "💳 دفع العمولة العليك", "callback_data": "pay_commission"}] if u[6] > 0 else [])
        return send(chat, msg, [kb] if kb else None, main_kb=True)

    if st == "await_payment_receipt":
        if "photo" not in m: return send(chat, "❌ يرجى إرسال صورة إشعار التحويل فقط.")
        debt = get_user_debt(uid)
        set_state(uid, None)
        send(chat, "✅ تم إرسال إشعار التحويل للمراجعة.", main_kb=True)
        if ADMIN_ID: send(ADMIN_ID, f"📥 **إشعار دفع عمولة:**\nالمستخدم: `{uid}`\nالمبلغ: {debt}ج", [[{"text": "✅ تأكيد المبلغ", "callback_data": f"pay_ok:{uid}"}], [{"text": "❌ رفض الإشعار", "callback_data": f"pay_no:{uid}"}]], photo=m["photo"][-1]["file_id"])
        return

    if st and st.startswith("await_reject_reason_"):
        reason, review_mid = txt, tmp.get("review_message_id")
        if st.startswith("await_reject_reason_pay_"):
            target_id = int(st.split("_")[-1])
            set_state(target_id, "await_payment_receipt"); set_state(uid, None)
            send(chat, f"✅ تم إرسال سبب الرفض للمستخدم `{target_id}`.")
            if review_mid: edit(chat, review_mid, f"❌ تم رفض إشعار التحويل لـ `{target_id}`.\nالسبب: {reason}", [])
            try: send(target_id, f"❌ **تم رفض إشعار التحويل**\nالسبب: {reason}\nيرجى إعادة الإرسال.", main_kb=True)
            except: pass
            return

        parts = st.split("_")
        final_action, typ, target_id = parts[3], parts[4], int(parts[5])
        new_status = "rejected_perm" if final_action == "perm" else "rejected_temp"
        tbl = "merchants" if typ == "m" else "products"
        where_col = "user_id" if typ == "m" else "id"
        
        query_db(f"UPDATE {tbl} SET status=?, reject_reason=? WHERE {where_col}=?", (new_status, reason, target_id))
        send(chat, f"✅ تم الرفض ({final_action}) لـ {target_id}")
        if review_mid: edit(chat, review_mid, f"✅ رفض {final_action} لـ {target_id}.\nالسبب: {reason}", [])
        set_state(uid, None)
        return

    if st == "await_search": set_state(uid, None); return do_search(chat, txt)
    if st == "await_store_name": set_state(uid, "await_phone", {"store_name": txt}); return send(chat, "أرسل رقم واتساب:")
    if st == "await_phone": tmp["phone"] = txt; set_state(uid, "await_city", tmp); return send(chat, "أرسل مدينتك:")
    if st == "await_city": tmp["city"] = txt; set_state(uid, "await_doc", tmp); return send(chat, "أرسل صورة الهوية:")
    if st == "await_doc":
        if "photo" not in m: return send(chat, "❌ أرسل صورة فقط:")
        doc_id = m["photo"][-1]["file_id"]
        query_db("INSERT OR REPLACE INTO merchants(user_id, store_name, phone, city, doc_photo, status) VALUES(?,?,?,?,?,?)", (uid, tmp["store_name"], tmp["phone"], tmp["city"], doc_id, "pending"))
        set_state(uid, None)
        send(chat, f"✅ تم استلام طلبك قيد المراجعة ⏳", main_kb=True)
        if ADMIN_ID: send(ADMIN_ID, f"🔔 طلب متجر جديد:\n{tmp['store_name']}\n{tmp['phone']}\nID:{uid}", [[{"text":"✅ قبول","callback_data":f"m_ok:{uid}"}], [{"text":"⏳ رفض مؤقت","callback_data":f"m_reject_temp:{uid}"},{"text":"🚫 رفض نهائي","callback_data":f"m_reject_perm:{uid}"}]], photo=doc_id)
        return

    if st == "await_prod_name": tmp["name"] = txt; set_state(uid, "await_prod_price", tmp); return send(chat, "أرسل السعر الأساسي (أرقام فقط):")
    if st == "await_prod_price":
        if not txt.isdigit() or int(txt) <= 0: return send(chat, "أرسل السعر أرقام فقط أكبر من صفر:")
        base_price = int(txt)
        comm = int(round(base_price * COMMISSION_RATE / 100))
        tmp.update({"base_price": base_price, "price": base_price + comm, "commission": comm})
        set_state(uid, "await_prod_price_confirm", tmp)
        return send(chat, f"💰 السعر بدون عمولة: {base_price:,.0f}ج\nالعمولة ({COMMISSION_RATE}%): {comm:,.0f}ج\n📌 **سعر النشر:** {base_price+comm:,.0f}ج", [[{"text": "✅ موافق", "callback_data": "prod_price_confirm"}, {"text": "❌ تعديل", "callback_data": "prod_price_cancel"}]])

    if st == "await_prod_desc":
        tmp["desc"] = txt
        query_db("INSERT INTO products(merchant_id,name,price,base_price,photo_id,description,category,status) VALUES(?,?,?,?,?,?,?,?)", (uid, tmp["name"], tmp["price"], tmp.get("base_price", tmp["price"]), tmp["photo"], tmp["desc"], tmp.get("cat","📦 أخرى"), "pending"))
        pid = query_db("SELECT last_insert_rowid()", fetch="one")[0]
        set_state(uid, None)
        send(chat, f"✅ تم رفع المنتج في {tmp.get('cat')}\nبانتظار الموافقة.", main_kb=True)
        if ADMIN_ID: send(ADMIN_ID, f"🔔 منتج جديد:\n{tmp['name']} - {tmp['price']}ج", [[{"text":"✅ قبول","callback_data":f"p_ok:{pid}"}], [{"text":"⏳ رفض مؤقت","callback_data":f"p_reject_temp:{pid}"},{"text":"🚫 رفض نهائي","callback_data":f"p_reject_perm:{pid}"}]], photo=tmp["photo"])
        return

    if st == "await_cod_info":
        comm = tmp.get("commission", int(round(tmp["price"] * COMMISSION_RATE / (100 + COMMISSION_RATE))))
        query_db("INSERT INTO orders(buyer_id,product_id,merchant_id,price,commission,buyer_info,status,created_at) VALUES(?,?,?,?,?,?,?,?)", (uid, tmp["pid"], tmp["mid"], tmp["price"], comm, txt, "pending_shipment", time.strftime("%Y-%m-%d")))
        oid = query_db("SELECT last_insert_rowid()", fetch="one")[0]
        query_db("UPDATE users SET purchases=purchases+1 WHERE user_id=?", (uid,))
        set_state(uid, None)
        send(chat, f"✅ تم تسجيل طلبك #{oid}\nالتاجر سيتواصل معك.", main_kb=True)
        send(tmp["mid"], f"🔔 طلب جديد #{oid}\nالمنتج: {tmp['pname']}\nالزبون:\n{txt}", [[{"text":f"📦 تم الشحن #{oid}","callback_data":f"ship:{oid}"}]])
        return

    if "photo" in m and st == "await_prod_photo":
        tmp["photo"] = m["photo"][-1]["file_id"]
        set_state(uid, "await_prod_name", tmp)
        return send(chat, "الصورة وصلت ✅ أرسل اسم المنتج:")

    if txt.startswith("/start"):
        parts = txt.split()
        if len(parts) > 1 and parts[1].isdigit() and int(parts[1]) != uid:
            ref_id = int(parts[1])
            if not query_db("SELECT * FROM referrals WHERE referred_id=?", (uid,), fetch="one"):
                query_db("INSERT INTO referrals(referrer_id,referred_id,created_at) VALUES(?,?,?)", (ref_id, uid, time.strftime("%Y-%m-%d")))
                query_db("UPDATE users SET points=points+10, referred_by=? WHERE user_id=?", (ref_id, uid))
                try: send(ref_id, f"🎉 إحالة جديدة! +10 نقاط.")
                except: pass
        m_status = query_db("SELECT status FROM merchants WHERE user_id=?", (uid,), fetch="one")
        if m_status and m_status[0] == "approved": return open_merchant(chat, uid)
        return send(chat, "مرحبا بك في سوق السودان 👋", main_kb=True)

    if len(txt) >= 2 and st is None: do_search(chat, txt)

# --- معالجة الضغط على الأزرار (Callbacks) ---
def handle_cb(c):
    uid, chat, mid, data = c["from"]["id"], c["message"]["chat"]["id"], c["message"]["message_id"], c["data"]

    if data == "pay_commission": send_payment_info(chat, uid); return answer(c["id"])
    
    if data.startswith("pay_ok:") and uid == ADMIN_ID:
        target_uid = int(data.split(":")[1])
        query_db("UPDATE users SET unpaid_commission=0 WHERE user_id=?", (target_uid,))
        edit(chat, mid, f"✅ تم تأكيد العمولة وتصفير مديونية `{target_uid}`.", [])
        try: send(target_uid, "✅ **تم تأكيد استلام العمولة بنجاح!**", main_kb=True)
        except: pass
        return answer(c["id"], "تم التأكيد")

    if data.startswith("pay_no:") and uid == ADMIN_ID:
        target_uid = int(data.split(":")[1])
        set_state(uid, f"await_reject_reason_pay_{target_uid}", {"review_message_id": mid})
        edit(chat, mid, f"❌ رفض الإشعار لـ `{target_uid}`\nأرسل سبب الرفض الآن:", [])
        return answer(c["id"])

    if data == "search": set_state(uid, "await_search"); edit(chat, mid, "🔍 أرسل اسم المنتج للبحث:"); return answer(c["id"])
    if data == "activate_profit":
        query_db("UPDATE users SET profit_active=1 WHERE user_id=?", (uid,))
        edit(chat, mid, f"🎉 تم تفعيل الربح {REFERRAL_RATE}٪\n🔗 رابطك:\nhttps://t.me/{BOT_USERNAME}?start={uid}")
        return answer(c["id"])

    if data == "admin_panel" and uid == ADMIN_ID:
        u_cnt = query_db("SELECT COUNT(*) FROM users", fetch="one")[0]
        m_cnt = query_db("SELECT COUNT(*) FROM merchants WHERE status='approved'", fetch="one")[0]
        p_cnt = query_db("SELECT COUNT(*) FROM merchants WHERE status='pending'", fetch="one")[0]
        comm = query_db("SELECT SUM(commission) FROM orders WHERE status='completed'", fetch="one")[0] or 0
        ref_p = query_db("SELECT SUM(amount) FROM referral_profits", fetch="one")[0] or 0
        
        kb = [[{"text":f"👥 المستخدمين ({u_cnt})","callback_data":"admin_users"}, {"text":f"🏪 التجار ({m_cnt})","callback_data":"admin_merchants"}],
              [{"text":f"⏳ معلق ({p_cnt})","callback_data":"admin_pending"}, {"text":f"🧾 الطلبات","callback_data":"admin_orders"}],
              [{"text":"🏠 الرئيسية","callback_data":"home"}]]
        edit(chat, mid, f"👑 لوحة الأدمن\n\n💰 عمولة {COMMISSION_RATE}%: {comm}ج\n💸 إحالات: {ref_p}ج\nصافي: {comm - ref_p}ج", kb)
        return answer(c["id"])

    if data == "admin_pending" and uid == ADMIN_ID:
        pend = query_db("SELECT user_id,store_name,phone,city,doc_photo FROM merchants WHERE status='pending' LIMIT 5", fetch="all")
        if not pend: edit(chat, mid, "لا يوجد طلبات معلقة", [[{"text":"🔙 رجوع","callback_data":"admin_panel"}]])
        else:
            edit(chat, mid, f"⏳ {len(pend)} طلبات معلقة:")
            for m in pend: send(chat, f"🔔 تاجر:\n{m[1]}\n{m[2]}\nID:{m[0]}", [[{"text":"✅ قبول","callback_data":f"m_ok:{m[0]}"}], [{"text":"⏳ رفض","callback_data":f"m_reject_temp:{m[0]}"}]], photo=m[4])
        return answer(c["id"])

    if data.startswith("ship:"):
        if check_debt_and_block(chat, uid): return answer(c["id"], "عليك عمولة")
        oid = int(data.split(":")[1])
        order = query_db("SELECT buyer_id,merchant_id,price FROM orders WHERE id=?", (oid,), fetch="one")
        if not order or order[1] != uid: return answer(c["id"], "ليس طلبك")
        query_db("UPDATE orders SET status='shipped' WHERE id=?", (oid,))
        edit(chat, mid, f"✅ تم شحن #{oid}")
        send(order[0], f"📦 طلبك #{oid} تم شحنه! السعر {order[2]}ج\nهل استلمت؟", [[{"text":f"✅ تأكيد #{oid}","callback_data":f"confirm:{oid}"}], [{"text":f"❌ مشكلة #{oid}","callback_data":f"dispute:{oid}"}]])
        return answer(c["id"], "تم الشحن")

    if data.startswith("confirm:"):
        oid = int(data.split(":")[1])
        o = query_db("SELECT buyer_id,merchant_id,price,commission FROM orders WHERE id=?", (oid,), fetch="one")
        if not o or o[0] != uid: return answer(c["id"], "ليس طلبك")
        
        buyer_id, merchant_id, price, comm_amount = o
        ref_row = query_db("SELECT referred_by FROM users WHERE user_id=?", (buyer_id,), fetch="one")
        ref_amount = 0
        if ref_row and ref_row[0]:
            ref_id = ref_row[0]
            if query_db("SELECT profit_active FROM users WHERE user_id=?", (ref_id,), fetch="one")[0] == 1:
                ref_amount = int(price * REFERRAL_RATE / 100)
                query_db("INSERT INTO referral_profits(referrer_id,buyer_id,order_id,amount,created_at) VALUES(?,?,?,?,?)", (ref_id, buyer_id, oid, ref_amount, time.strftime("%Y-%m-%d")))
                query_db("UPDATE users SET referral_earnings=referral_earnings+?, referral_balance=referral_balance+? WHERE user_id=?", (ref_amount, ref_amount, ref_id))
                try: send(ref_id, f"💰 ربح إحالة جديد! {ref_amount}ج")
                except: pass

        query_db("UPDATE orders SET status='completed', referral_comm=? WHERE id=?", (ref_amount, oid))
        query_db("UPDATE users SET sales=sales+1, unpaid_commission=unpaid_commission+? WHERE user_id=?", (comm_amount, merchant_id))
        edit(chat, mid, f"✅ تم تأكيد استلام #{oid}")
        send(merchant_id, f"🎉 المشتري أكد استلام #{oid}\nعمولة البوت: {comm_amount}ج", main_kb=True)
        return answer(c["id"], "تم التأكيد")

    if data.startswith("browse:"):
        cat = data.split(":", 1)[1]
        sql = "SELECT * FROM products WHERE status='approved' ORDER BY id DESC LIMIT 10" if cat == "all" else "SELECT * FROM products WHERE status='approved' AND category=? ORDER BY id DESC LIMIT 10"
        prods = query_db(sql, () if cat == "all" else (cat,), fetch="all")
        if not prods: edit(chat, mid, "ما في منتجات", [[{"text":"🔙 رجوع","callback_data":"buyer"}]])
        else:
            edit(chat, mid, f"المنتجات ({len(prods)})")
            for p in prods:
                store = query_db("SELECT store_name FROM merchants WHERE user_id=?", (p[1],), fetch="one")
                send(chat, f"📦 {p[2]}\n💰 {p[3]}ج\n📝 {p[5]}\n🏪 {store[0] if store else 'متجر'}", [[{"text":f"🛒 شراء {p[3]}ج","callback_data":f"buy:{p[0]}"}]], photo=p[4])
        return answer(c["id"])

    if data == "prod_price_confirm":
        st, tmp = get_user_session(uid)
        set_state(uid, "await_prod_cat", tmp)
        edit(chat, mid, f"✅ السعر المعايير: {tmp['price']}ج\nاختر القسم:", cat_kb("setcat"))
        return answer(c["id"])

    if data == "prod_price_cancel":
        set_state(uid, "await_prod_price", {})
        edit(chat, mid, "❌ تم الإلغاء. أرسل السعر الأساسي الجديد:")
        return answer(c["id"])

    if data.startswith("setcat:"):
        cat = data.split(":", 1)[1]
        st, tmp = get_user_session(uid)
        tmp["cat"] = cat
        set_state(uid, "await_prod_desc", tmp)
        edit(chat, mid, f"اخترت {cat} ✅ أرسل وصف المنتج:")
        return answer(c["id"])

    if data == "add":
        if check_debt_and_block(chat, uid): return answer(c["id"])
        set_state(uid, "await_prod_photo", {})
        send(chat, "أرسل صورة المنتج:")
        return answer(c["id"])

    if data.startswith("buy:"):
        if check_debt_and_block(chat, uid): return answer(c["id"])
        p = query_db("SELECT * FROM products WHERE id=?", (int(data.split(":")[1]),), fetch="one")
        if not p: return answer(c["id"], "غير موجود")
        base = p[9] or int(round(p[3] * 100 / (100 + COMMISSION_RATE)))
        set_state(uid, "await_cod_info", {"pid": p[0], "mid": p[1], "price": p[3], "pname": p[2], "commission": p[3] - base})
        send(chat, f"المنتج: {p[2]}\nالسعر: {p[3]} جنيه\nأرسل الاسم الكامل والرقمين والموقع:")
        return answer(c["id"])

    if data.startswith("m_ok:"):
        mid_t = int(data.split(":")[1])
        query_db("UPDATE merchants SET status='approved', reject_reason='' WHERE user_id=?", (mid_t,))
        edit(chat, mid, f"✅ تم قبول التاجر {mid_t}", [])
        try: send(mid_t, "🎉 تم قبول متجرك! افتح /start لإدارة منتجاتك.", main_kb=True)
        except: pass
        return answer(c["id"])

    if data.startswith("p_ok:"):
        pid = int(data.split(":")[1])
        query_db("UPDATE products SET status='approved', reject_reason='' WHERE id=?", (pid,))
        edit(chat, mid, f"✅ تم نشر المنتج #{pid}", [])
        return answer(c["id"])

    if data in ["merchant", "home", "buyer"]:
        if data == "merchant": open_merchant(chat, uid, mid)
        elif data == "buyer": show_market(chat)
        else: send(chat, "مرحبا بك في سوق السودان 👋", main_kb=True)
        return answer(c["id"])

def main():
    keep_alive()
    off = 0
    print("Bot Started Successfully!")
    while True:
        try:
            r = api("getUpdates", {"timeout": 30, "offset": off})
            for u in r.get("result", []):
                off = u["update_id"] + 1
                if "message" in u: handle_msg(u["message"])
                elif "callback_query" in u: handle_cb(u["callback_query"])
        except Exception as e:
            print("Loop Error:", e)
            time.sleep(2)

if __name__ == "__main__":
    main()
