سبب الخلل الظاهر في الشاشة هو وجود فاصلة عربية (،) كُتبت بالخطأ داخل أسطر البرمجة (في السطر 3 أو حوله) بدلاً من الفاصلة الإنجليزية (,)، بالإضافة إلى كتابة كلمة From بحرف كبير في بداية الملف.
الكود المُصحح بالكامل والجاهز للتعديل مباشرة:
قم بنسخ الكود التالي واستبدال محتوى ملف bot_fixed.py به:
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

# --- خادم الحفاظ على عمل البوت (Keep Alive) ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is Alive!"

def run():
    app.run(host='0.0.0.0', port=10000)

def keep_alive():
    t = threading.Thread(target=run)
    t.daemon = True
    t.start()

# --- إعدادات البوت وقاعدة البيانات ---
TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
BOT_USERNAME = os.environ.get("BOT_USERNAME", "your_bot")
ADMIN_CONTACT = os.environ.get("ADMIN_CONTACT", "@admin")
COMMISSION_RATE = 9
REFERRAL_RATE = 4
API = f"https://api.telegram.org/bot{TOKEN}"
DB = "marketplace.db"

CATEGORIES = ["👕 ملابس", "🍳 أواني منزلية", "🔥 عروض وخصم", "⭐ رائج", "👗 موضة", "📦 أخرى", "🌾 أعلاف حيوانات", "💄 منتجات تجميل", "🌱 أسمدة زراعية", "💪 منتجات جيم"]

db = sqlite3.connect(DB, check_same_thread=False)
db.executescript('''
CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY, state TEXT, temp TEXT, points INTEGER DEFAULT 0, purchases INTEGER DEFAULT 0, sales INTEGER DEFAULT 0, referred_by INTEGER, is_banned INTEGER DEFAULT 0, profit_active INTEGER DEFAULT 0, referral_earnings INTEGER DEFAULT 0, referral_balance INTEGER DEFAULT 0, unpaid_commission INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS merchants(user_id INTEGER PRIMARY KEY, store_name TEXT, phone TEXT, city TEXT, doc_photo TEXT, status TEXT DEFAULT 'pending', reject_reason TEXT);
CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY AUTOINCREMENT, merchant_id INTEGER, name TEXT, price INTEGER, photo_id TEXT, description TEXT, category TEXT, status TEXT DEFAULT 'pending', reject_reason TEXT, base_price INTEGER);
CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT, buyer_id INTEGER, product_id INTEGER, merchant_id INTEGER, price INTEGER, commission INTEGER, referral_comm INTEGER, buyer_info TEXT, status TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS referrals(id INTEGER PRIMARY KEY AUTOINCREMENT, referrer_id INTEGER, referred_id INTEGER, created_at TEXT);
CREATE TABLE IF NOT EXISTS referral_profits(id INTEGER PRIMARY KEY AUTOINCREMENT, referrer_id INTEGER, buyer_id INTEGER, order_id INTEGER, amount INTEGER, created_at TEXT);
''')

try:
    db.execute("ALTER TABLE users ADD COLUMN profit_active INTEGER DEFAULT 0")
except: pass
try:
    db.execute("ALTER TABLE users ADD COLUMN referral_earnings INTEGER DEFAULT 0")
except: pass
try:
    db.execute("ALTER TABLE users ADD COLUMN referral_balance INTEGER DEFAULT 0")
except: pass
try:
    db.execute("ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0")
except: pass
try:
    db.execute("ALTER TABLE users ADD COLUMN unpaid_commission INTEGER DEFAULT 0")
except: pass
try:
    db.execute("ALTER TABLE merchants ADD COLUMN doc_photo TEXT")
except: pass
try:
    db.execute("ALTER TABLE merchants ADD COLUMN reject_reason TEXT")
except: pass
try:
    db.execute("ALTER TABLE products ADD COLUMN reject_reason TEXT")
except: pass
try:
    db.execute("ALTER TABLE products ADD COLUMN base_price INTEGER")
except: pass
try:
    db.execute("ALTER TABLE orders ADD COLUMN price INTEGER")
except: pass
try:
    db.execute("ALTER TABLE orders ADD COLUMN commission INTEGER")
except: pass
try:
    db.execute("ALTER TABLE orders ADD COLUMN referral_comm INTEGER")
except: pass
try:
    db.execute("ALTER TABLE orders ADD COLUMN created_at TEXT")
except: pass
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
        payload = {}
        payload["chat_id"] = chat_id
        payload["photo"] = photo
        payload["caption"] = text
        if kb:
            payload["reply_markup"] = json.dumps({"inline_keyboard": kb}, ensure_ascii=False)
        return api("sendPhoto", payload)
    payload = {}
    payload["chat_id"] = chat_id
    payload["text"] = text
    if kb:
        payload["reply_markup"] = json.dumps({"inline_keyboard": kb}, ensure_ascii=False)
    elif main_kb:
        merchant_row = db.execute("SELECT status FROM merchants WHERE user_id=?", (chat_id,)).fetchone()
        if merchant_row:
            store_button = "🏪 لوحة متجري" if merchant_row[0] == "approved" else "🏪 حالة متجري"
            keyboard = [
                ["🛍️ تسوق", "🔍 بحث عن منتج"],
                [store_button]
            ]
        else:
            keyboard = [
                ["🛍️ تسوق", "🔍 بحث عن منتج"],
                ["🏪 إنشاء حساب تاجر", "💰 الربح من البوت"]
            ]
        if chat_id == ADMIN_ID and ADMIN_ID:
            keyboard.append(["👑 لوحة الأدمن"])
        payload["reply_markup"] = json.dumps({"keyboard": keyboard, "resize_keyboard": True}, ensure_ascii=False)
    return api("sendMessage", payload)

def edit(chat_id, msg_id, text, kb=None):
    payload = {"chat_id": chat_id, "message_id": msg_id, "text": text}
    if kb is not None:
        payload["reply_markup"] = json.dumps({"inline_keyboard": kb}, ensure_ascii=False)
    result = api("editMessageText", payload)
    if result and result.get("ok"):
        return result

    payload2 = {"chat_id": chat_id, "message_id": msg_id, "caption": text}
    if kb is not None:
        payload2["reply_markup"] = json.dumps({"inline_keyboard": kb}, ensure_ascii=False)
    caption_result = api("editMessageCaption", payload2)
    return caption_result if caption_result and caption_result.get("ok") else result or caption_result

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

def get_user_debt(uid):
    row = db.execute("SELECT unpaid_commission FROM users WHERE user_id=?", (uid,)).fetchone()
    return row[0] if row and row[0] else 0

def check_debt_and_block(chat_id, uid):
    debt = get_user_debt(uid)
    if debt > 0:
        kb = [[{"text": "💳 دفع العمولة العليك", "callback_data": "pay_commission"}]]
        send(chat_id, f"⚠️ **تنبيه:** لديك عمولة مستحقة قدرها ({debt} جنيه).\nلا يمكنك إجراء طلبات جديدة أو استلام طلبات حتى سداد العمولة.", kb)
        return True
    return False

def cat_kb(prefix):
    kb = []
    for i in range(0, len(CATEGORIES), 2):
        row = []
        b1 = {}
        b1["text"] = CATEGORIES[i]
        b1["callback_data"] = f"{prefix}:{CATEGORIES[i]}"
        row.append(b1)
        if i+1 < len(CATEGORIES):
            b2 = {}
            b2["text"] = CATEGORIES[i+1]
            b2["callback_data"] = f"{prefix}:{CATEGORIES[i+1]}"
            row.append(b2)
        kb.append(row)
    return kb

def setup():
    try:
        cmds = []
        cmds.append({"command": "start", "description": "🏠 الرئيسية - تحديث وبحث"})
        api("setMyCommands", {"commands": json.dumps(cmds, ensure_ascii=False)})
    except:
        pass

def normalize_search_text(value):
    value = unicodedata.normalize("NFKC", str(value or "")).lower()
    value = re.sub(r"[\u064b-\u065f\u0670\u0640]", "", value)
    value = value.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي"}))
    return re.sub(r"[^\w\s]", " ", value).strip()

def fuzzy_word_score(query_word, product_words):
    best = 0.0
    for word in product_words:
        if query_word == word:
            return 1.0
        if min(len(query_word), len(word)) >= 3 and (query_word in word or word in query_word):
            best = max(best, 0.86)
        else:
            best = max(best, SequenceMatcher(None, query_word, word).ratio())
    return best

def do_search(chat_id, query):
    normalized_query = normalize_search_text(query)
    query_words = normalized_query.split()
    if not query_words:
        send(chat_id, "أرسل اسم المنتج أو جزءًا من اسمه للبحث.", main_kb=True)
        return

    products = db.execute("SELECT * FROM products WHERE status='approved' ORDER BY id DESC").fetchall()
    ranked = []
    for product in products:
        title = normalize_search_text(product[2])
        description = normalize_search_text(product[5])
        category = normalize_search_text(product[6])
        combined = f"{title} {description} {category}"
        if normalized_query in combined:
            score = 1.0 + (0.15 if normalized_query in title else 0.0)
        else:
            words = combined.split()
            scores = [fuzzy_word_score(word, words) for word in query_words]
            thresholds = [0.70 if len(word) == 3 else 0.60 if len(word) >= 4 else 1.0 for word in query_words]
            matched = sum(score >= threshold for score, threshold in zip(scores, thresholds))
            coverage = matched / len(query_words)
            average = sum(scores) / len(scores)
            if coverage < 0.5 or average < 0.60:
                continue
            score = average + (0.12 if any(word in title for word in query_words) else 0.0)
        ranked.append((score, product))

    ranked.sort(key=lambda item: (item[0], item[1][0]), reverse=True)
    prods = [item[1] for item in ranked[:10]]
    if not prods:
        send(chat_id, f"🔍 نتائج البحث عن «{query}»\n\n❌ ما لقينا نتائج. جرّب كتابة جزء من اسم المنتج أو كلمة قريبة منه.", main_kb=True)
        return
    send(chat_id, f"🔍 نتائج البحث عن «{query}» - {len(prods)} منتج 👇", main_kb=True)
    for product in prods:
        store = db.execute("SELECT store_name FROM merchants WHERE user_id=?", (product[1],)).fetchone()
        store_name = store[0] if store else "متجر"
        kb = [[{"text": f"🛒 شراء {product[3]}ج عند الاستلام", "callback_data": f"buy:{product[0]}"}]]
        send(chat_id, f"📦 {product[2]}\n💰 {product[3]}ج عند الاستلام\n📝 {product[5]}\n🏷️ {product[6]}\n🏪 {store_name}", kb, photo=product[4])

def show_market(chat_id):
    keyboard = cat_kb("browse")
    keyboard.append([{"text": "🛍️ كل المنتجات", "callback_data": "browse:all"}])
    keyboard.append([{"text": "🔍 بحث عن منتج", "callback_data": "search"}])
    send(chat_id, "🛍️ خدمات التسوق\nاختر قسمًا لتصفح المنتجات، أو افتح كل المنتجات، أو ابحث باسم المنتج:", keyboard)

def show_merchant_intro(chat_id):
    keyboard = [[{"text": "✅ أنا تاجر الآن", "callback_data": "merchant"}]]
    message = (
        "🏪 إنشاء حساب تاجر\n\n"
        "بعد إنشاء حساب تاجر، يمكنك رفع منتجاتك مباشرة. عند طلب أي منتج، سيتم التواصل معك لترتيب التسليم.\n"
        f"عمولة المتجر {COMMISSION_RATE}% تضاف تلقائياً فوق سعرك الأساسي، منها {REFERRAL_RATE}% مخصصة للمسوقين.\n"
        "يمكن لأي شخص التسجيل والعمل كمسوق عبر البوت."
    )
    send(chat_id, message, keyboard)

def open_merchant(chat_id, uid, message_id=None):
    set_state(uid, None, {})
    merchant = db.execute("SELECT * FROM merchants WHERE user_id=?", (uid,)).fetchone()
    if merchant:
        status = merchant[5] if len(merchant) >= 6 else "pending"
        if status == "banned":
            text, keyboard = "🚫 حساب التاجر موقوف. تواصل مع خدمة العملاء.", None
        elif status == "pending":
            text, keyboard = f"متجرك «{merchant[1]}» قيد المراجعة ⏳\nستظهر لك خدمات التاجر بعد الموافقة.", None
        elif status == "approved":
            product_count = db.execute("SELECT COUNT(*) FROM products WHERE merchant_id=? AND status='approved'", (uid,)).fetchone()[0]
            pending_orders = db.execute("SELECT COUNT(*) FROM orders WHERE merchant_id=? AND status='pending_shipment'", (uid,)).fetchone()[0]
            text = f"أهلاً يا صاحب متجر {merchant[1]} ✅\nمنتجاتك: {product_count}\nطلبات قيد الشحن: {pending_orders}"
            keyboard = [
                [{"text": "➕ إضافة منتج", "callback_data": "add"}, {"text": "📊 مبيعاتي", "callback_data": "sales"}],
                [{"text": f"📦 طلبات تحت الشحن ({pending_orders})", "callback_data": "my_pending"}],
                [{"text": "🛍️ تصفح السوق", "callback_data": "buyer"}]
            ]
            if uid == ADMIN_ID and ADMIN_ID:
                keyboard.append([{"text": "👑 لوحة الأدمن", "callback_data": "admin_panel"}])
        else:
            set_state(uid, "await_store_name", {})
            text = "تم رفض الطلب السابق. يمكنك إعادة التقديم. أرسل اسم المتجر الجديد:"
            keyboard = None
    else:
        set_state(uid, "await_store_name", {})
        text = "✅ لنبدأ إنشاء حسابك التجاري.\n\nأرسل اسم المتجر:"
        keyboard = None

    if message_id is not None:
        edit(chat_id, message_id, text, keyboard if keyboard is not None else [])
    else:
        send(chat_id, text, keyboard, main_kb=(keyboard is None))

def handle_msg(m):
    uid = m["from"]["id"]
    chat = m["chat"]["id"]
    txt = m.get("text", "")
    st = get_state(uid)
    tmp = get_temp(uid)
    db.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (uid,))
    db.commit()

    banned_row = db.execute("SELECT is_banned FROM users WHERE user_id=?", (uid,)).fetchone()
    if banned_row and banned_row[0]==1 and uid!=ADMIN_ID:
        send(chat, "🚫 محظور، تواصل: "+ADMIN_CONTACT)
        return

    if txt in ["🛍️ تسوق", "تسوق", "🛍️ تصفح السوق"]:
        set_state(uid, None, {})
        show_market(chat)
        return
    if txt in ["🔍 بحث عن منتج", "بحث عن منتج", "🔍 بحث", "بحث", "🔍"]:
        set_state(uid, "await_search", {})
        send(chat, "🔍 أرسل اسم المنتج أو جزءًا من اسمه. لا يلزم أن تكتب الاسم بشكل مطابق تمامًا.", main_kb=True)
        return
    if txt in ["🏪 إنشاء حساب تاجر", "إنشاء حساب تاجر"]:
        set_state(uid, None, {})
        show_merchant_intro(chat)
        return
    if txt in ["✅ أنا تاجر الآن", "أنا تاجر الآن"]:
        open_merchant(chat, uid)
        return
    if txt in ["🏪 لوحة متجري", "🏪 حالة متجري", "لوحة متجري"]:
        open_merchant(chat, uid)
        return
    if txt in ["👑 لوحة الأدمن", "/admin"] and uid==ADMIN_ID:
        send(chat, "👑 افتح لوحة الإدارة:", [[{"text": "👑 لوحة الأدمن", "callback_data": "admin_panel"}]])
        return
    if txt in ["💰 الربح من البوت", "الربح من البوت"]:
        set_state(uid, None, {})
        db.execute("UPDATE users SET profit_active=1 WHERE user_id=?", (uid,))
        db.commit()
        link = f"https://t.me/{BOT_USERNAME}?start={uid}"
        send(chat, f"🎉 تم تفعيل الربح من البوت بنسبة {REFERRAL_RATE}٪\n\nتكسب {REFERRAL_RATE}٪ من قيمة كل عملية شراء مكتملة يقوم بها شخص سجّل من رابطك.\n\n🔗 رابطك الخاص:\n{link}\n\nشارك الرابط مع الآخرين ليتم تسجيلهم من خلاله.", main_kb=True)
        return
    if txt in ["🔄 تحديث /start","🔄 تحديث","تحديث","/start","start"]:
        set_state(uid, None, {})
        st = None
        tmp = {}
        txt = "/start"
    if txt in ["📊 حسابي","حسابي"]:
        row = db.execute("SELECT points,purchases,sales,profit_active,referral_earnings,referral_balance,unpaid_commission FROM users WHERE user_id=?", (uid,)).fetchone()
        points = row[0] if row else 0
        purch = row[1] if row else 0
        sales = row[2] if row else 0
        profit_active = row[3] if row else 0
        earn = row[4] if row else 0
        bal = row[5] if row else 0
        debt = row[6] if row else 0
        total_ref = db.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (uid,)).fetchone()[0]
        total_comm = db.execute("SELECT SUM(commission) FROM orders WHERE merchant_id=? AND status='completed'", (uid,)).fetchone()[0] or 0
        link = f"https://t.me/{BOT_USERNAME}?start={uid}"
        status_txt = "✅ مفعل" if profit_active==1 else "❌ غير مفعل"
        
        msg = f"📊 حسابك:\n\n🛒 اشتريت: {purch}\n📦 بعت: {sales}\n⭐ نقاطك: {points}\n💳 العمولة المستحقة عليك: {debt}ج\n\n💰 نظام الربح {REFERRAL_RATE}%:\nالحالة: {status_txt}\n👥 إحالاتك: {total_ref}\n💵 أرباح الإحالات: {earn}ج\n💳 رصيدك: {bal}ج\n\n🔗 رابط إحالتك:\n{link}\n\nشارك الرابط، تاخد {REFERRAL_RATE}% من مشترياتهم مدى الحياة\n\n💰 عمولة بعتها كتاجر: {total_comm}ج ({COMMISSION_RATE}%)"
        
        kb = []
        if debt > 0:
            kb.append([{"text": "💳 دفع العمولة العليك", "callback_data": "pay_commission"}])
        if profit_active==0:
            kb.append([{"text":"💰 تفعيل الربح 4%","callback_data":"activate_profit"}])
            
        send(chat, msg, kb if kb else None, main_kb=True)
        return

    if st == "await_payment_receipt":
        if "photo" not in m:
            send(chat, "❌ يرجى إرسال صورة إشعار التحويل فقط.")
            return
        photo_id = m["photo"][-1]["file_id"]
        debt = get_user_debt(uid)
        set_state(uid, None, {})
        send(chat, "✅ تم إرسال إشعار التحويل للآدمن للمراجعة والتأكيد. سيتم تفعيل حسابك فور التحقق.", main_kb=True)
        if ADMIN_ID:
            kb = [
                [{"text": "✅ تأكيد استلام المبلغ", "callback_data": f"pay_ok:{uid}"}],
                [{"text": "❌ رفض الإشعار", "callback_data": f"pay_no:{uid}"}]
            ]
            send(ADMIN_ID, f"📥 **إشعار دفع عمولة جديد:**\nالمستخدم: `{uid}`\nالمبلغ المطلوب: {debt}ج", kb, photo=photo_id)
        return

    if st and st.startswith("await_reject_reason_"):
        reason = txt
        parts = st.split("_")
        final_action = parts[3]
        typ = parts[4]
        target_id = int(parts[5])
        review_message_id = tmp.get("review_message_id")
        if typ=="m":
            new_status = "rejected_perm" if final_action=="perm" else "rejected_temp"
            db.execute("UPDATE merchants SET status=?, reject_reason=? WHERE user_id=?", (new_status, reason, target_id))
            db.commit()
            if final_action=="perm":
                send(chat, f"✅ رفض نهائي {target_id}")
                try:
                    send(target_id, f"❌ رفض نهائي لمتجرك:\n{reason}\nتواصل: {ADMIN_CONTACT}", main_kb=True)
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
        if review_message_id:
            outcome = "رفض نهائي" if final_action=="perm" else "رفض مؤقت"
            entity = "التاجر" if typ=="m" else "المنتج"
            edit(chat, review_message_id, f"✅ {outcome} طلب {entity} {target_id}.\nالسبب: {reason}", [])
        set_state(uid, None, {})
        return
    if st=="await_search":
        set_state(uid, None, {})
        do_search(chat, txt)
        return
    if st=="await_store_name":
        tmp["store_name"] = txt
        set_state(uid, "await_phone", tmp)
        send(chat, "تمام ✅\nأرسل رقم واتساب:")
        return
    if st=="await_phone":
        tmp["phone"] = txt
        set_state(uid, "await_city", tmp)
        send(chat, "أرسل مدينتك:")
        return
    if st=="await_city":
        tmp["city"] = txt
        set_state(uid, "await_doc", tmp)
        send(chat, f"✅ استلمنا مدينتك: {txt}\n\nأرسل صورة واضحة لمستند الهوية (بطاقة شخصية أو جواز سفر أو رخصة). أرسل صورة فقط.")
        return
    if st=="await_doc":
        if "photo" not in m:
            send(chat, "❌ أرسل صورة المستند، ليس نص:")
            return
        doc_id = m["photo"][-1]["file_id"]
        tmp["doc"] = doc_id
        db.execute("INSERT OR REPLACE INTO merchants(user_id, store_name, phone, city, doc_photo, status) VALUES(?,?,?,?,?,?)", (uid, tmp["store_name"], tmp["phone"], tmp["city"], doc_id, "pending"))
        db.commit()
        set_state(uid, None, {})
        send(chat, f"✅ تم استلام طلبك مع المستند\nمتجر: {tmp['store_name']}\nقيد المراجعة ⏳", main_kb=True)
        kb = []
        kb.append([{"text":"✅ قبول","callback_data":f"m_ok:{uid}"}])
        kb.append([{"text":"⏳ رفض مؤقت","callback_data":f"m_reject_temp:{uid}"},{"text":"🚫 رفض نهائي","callback_data":f"m_reject_perm:{uid}"}])
        kb.append([{"text":"🔇 كانسل","callback_data":f"m_no:{uid}"}])
        if ADMIN_ID:
            send(ADMIN_ID, f"🔔 طلب إنشاء متجر جديد + مستند هوية:\n{tmp['store_name']}\n{tmp['phone']}\n{tmp['city']}\nID:{uid}", kb, photo=doc_id)
        return
    if st=="await_prod_name":
        tmp["name"] = txt
        set_state(uid, "await_prod_price", tmp)
        send(chat, "أرسل السعر الأساسي أرقام فقط من غير عمولة المتجر:")
        return
    if st=="await_prod_price":
        if not txt.isdigit() or int(txt) <= 0:
            send(chat, "أرسل السعر الأساسي أرقام فقط، ويجب أن يكون أكبر من صفر:")
            return
        base_price = int(txt)
        commission = int(round(base_price * COMMISSION_RATE / 100))
        final_price = base_price + commission
        tmp["base_price"] = base_price
        tmp["price"] = final_price
        tmp["commission"] = commission
        set_state(uid, "await_prod_price_confirm", tmp)
        kb = [[
            {"text": "✅ موافق", "callback_data": "prod_price_confirm"},
            {"text": "❌ رفض / تعديل", "callback_data": "prod_price_cancel"}
        ]]
        send(chat, f"💰 مبلغ الطلب بدون عمولة: {base_price:,.0f}ج\nقيمة العمولة ({COMMISSION_RATE}%): {commission:,.0f}ج\n\n📌 **سيتم نشره بي سعر:** {final_price:,.0f}ج\n\nهل توافق على السعر؟", kb)
        return

    if st=="await_prod_price_confirm":
        send(chat, "استخدم أزرار الموافقة أو الرفض الظاهرة أسفل رسالة السعر.")
        return
    if st=="await_prod_desc":
        tmp["desc"] = txt
        db.execute("INSERT INTO products(merchant_id,name,price,base_price,photo_id,description,category,status) VALUES(?,?,?,?,?,?,?,?)", (uid, tmp["name"], tmp["price"], tmp.get("base_price", tmp["price"]), tmp["photo"], tmp["desc"], tmp.get("cat","📦 أخرى"), "pending"))
        db.commit()
        pid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        set_state(uid, None, {})
        comm = tmp.get("commission", int(tmp["price"] * COMMISSION_RATE / 109))
        send(chat, f"✅ تم رفع المنتج في {tmp.get('cat')}\nالسعر الأساسي: {tmp.get('base_price', tmp['price'])}ج\nعمولة المتجر: {comm}ج\nسعر البيع: {tmp['price']}ج\nبانتظار الموافقة.", main_kb=True)
        kb = []
        kb.append([{"text":"✅ قبول","callback_data":f"p_ok:{pid}"}])
        kb.append([{"text":"⏳ رفض مؤقت","callback_data":f"p_reject_temp:{pid}"},{"text":"🚫 رفض نهائي","callback_data":f"p_reject_perm:{pid}"}])
        kb.append([{"text":"🔇 كانسل","callback_data":f"p_no:{pid}"}])
        if ADMIN_ID:
            send(ADMIN_ID, f"🔔 منتج جديد:\n{tmp['name']} - {tmp['price']}ج\nعمولة {comm}ج", kb, photo=tmp["photo"])
        return
    if st=="await_cod_info":
        commission = tmp.get("commission", int(round(tmp["price"] * COMMISSION_RATE / (100 + COMMISSION_RATE))))
        db.execute("INSERT INTO orders(buyer_id,product_id,merchant_id,price,commission,buyer_info,status,created_at) VALUES(?,?,?,?,?,?,?,?)", (uid, tmp["pid"], tmp["mid"], tmp["price"], commission, txt, "pending_shipment", time.strftime("%Y-%m-%d")))
        db.commit()
        oid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.execute("UPDATE users SET purchases=purchases+1 WHERE user_id=?", (uid,))
        db.commit()
        set_state(uid, None, {})
        send(chat, f"✅ تم تسجيل طلبك #{oid} في قاعدة البيانات\nالمنتج: {tmp['pname']}\nالسعر: {tmp['price']}ج\nالدفع عند الاستلام فقط\nالتاجر سيتواصل معك.", main_kb=True)
        kb_ship = []
        kb_ship.append([{"text":f"📦 تم الشحن - طلب #{oid}","callback_data":f"ship:{oid}"}])
        send(tmp["mid"], f"🔔 طلب جديد #{oid}\nالمنتج: {tmp['pname']}\nالسعر: {tmp['price']}ج\nالزبون:\n{txt}\n\nعند شحن الطلب دوس الزر:", kb_ship)
        return
    if "photo" in m and st=="await_prod_photo":
        tmp["photo"] = m["photo"][-1]["file_id"]
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
                    db.execute("INSERT INTO referrals(referrer_id,referred_id,created_at) VALUES(?,?,?)", (ref_id, uid, time.strftime("%Y-%m-%d")))
                    db.execute("UPDATE users SET points=points+10 WHERE user_id=?", (ref_id,))
                    db.execute("UPDATE users SET referred_by=? WHERE user_id=?", (ref_id, uid))
                    db.commit()
                    try:
                        send(ref_id, f"🎉 إحالة جديدة!\nشخص سجل عبر رابطك\n+10 نقاط\nإذا فعلت الربح {REFERRAL_RATE}% ستكسب من مشترياته مدى الحياة!")
                    except:
                        pass
        merchant_row = db.execute("SELECT status FROM merchants WHERE user_id=?", (uid,)).fetchone()
        if merchant_row and merchant_row[0] == "approved":
            open_merchant(chat, uid)
            return
        send(chat, "مرحبا بك في سوق السودان \nهنا ستجد ما تريده إن شاء الله وبأقل الأسعار.", main_kb=True)
        return
    if len(txt)>=2 and st is None and txt not in ["📊 حسابي","💰 تفعيل الربح","☎️ خدمة العملاء","🔄 تحديث /start","🔍 بحث","🔍 بحث عن منتج","بحث عن منتج","🛍️ تسوق","تسوق","🏪 إنشاء حساب تاجر","إنشاء حساب تاجر","💰 الربح من البوت","أنا تاجر الآن","حسابي"]:
        do_search(chat, txt)
        return

def handle_cb(c):
    uid = c["from"]["id"]
    chat = c["message"]["chat"]["id"]
    mid = c["message"]["message_id"]
    data = c["data"]

    if data == "pay_commission":
        debt = get_user_debt(uid)
        set_state(uid, "await_payment_receipt", {})
        payment_text = (
            f"🏦 **بيانات الدفع لسداد العمولة ({debt:,.0f} جنيه):**\n\n"
            f"• **تطبيق:** بنكك (Bankak)\n"
            f"• **رقم الحساب:** `7696230`\n"
            f"• **الاسم:** بدور عبدالكريم عيسى النعيم\n\n"
            f"📸 **بعد التحويل:** يرجى إرسال صورة إشعار التحويل (المرتد) هنا في الشات لتأكيد التحويل."
        )
        send(chat, payment_text)
        answer(c["id"])
        return

    if data.startswith("pay_ok:") and uid == ADMIN_ID:
        target_uid = int(data.split(":")[1])
        db.execute("UPDATE users SET unpaid_commission=0 WHERE user_id=?", (target_uid,))
        db.commit()
        edit(chat, mid, f"✅ تم تأكيد استلام العمولة وتصفير مديونية المستخدم `{target_uid}` بنجاح.", [])
        try:
            send(target_uid, "✅ **تم تأكيد استلام العمولة بنجاح!**\nتم رفع التقييد عن حسابك ويمكنك الآن استخدام كافة خدمات البوت بحرية.", main_kb=True)
        except: pass
        answer(c["id"], "تم التأكيد")
        return

    if data.startswith("pay_no:") and uid == ADMIN_ID:
        target_uid = int(data.split(":")[1])
        edit(chat, mid, f"❌ تم رفض إشعار التحويل للمستخدم `{target_uid}`.", [])
        try:
            send(target_uid, "❌ **تم رفض إشعار التحويل.**\nيرجى التأكد من صحة صورة التحويل وإعادة إرسالها للتحقق.", main_kb=True)
        except: pass
        answer(c["id"], "تم الرفض")
        return

    if data=="search":
        set_state(uid, "await_search", {})
        edit(chat, mid, "🔍 أرسل اسم المنتج أو جزءًا من اسمه. لا يلزم أن تكتب الاسم بشكل مطابق تمامًا.")
        answer(c["id"])
        return
    if data=="activate_profit":
        db.execute("UPDATE users SET profit_active=1 WHERE user_id=?", (uid,))
        db.commit()
        link = f"https://t.me/{BOT_USERNAME}?start={uid}"
        edit(chat, mid, f"🎉 تم تفعيل الربح من البوت بنسبة {REFERRAL_RATE}٪\n\nتكسب {REFERRAL_RATE}٪ من قيمة كل عملية شراء مكتملة يقوم بها شخص سجّل من رابطك.\n\n🔗 رابطك الخاص:\n{link}\n\nشارك الرابط مع الآخرين ليتم تسجيلهم من خلاله.")
        answer(c["id"], "تم التفعيل!")
        return
    if data=="my_referral_earnings":
        row = db.execute("SELECT referral_earnings,referral_balance FROM users WHERE user_id=?", (uid,)).fetchone()
        earn = row[0] if row else 0
        bal = row[1] if row else 0
        total_ref = db.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (uid,)).fetchone()[0]
        profits = db.execute("SELECT buyer_id,amount,created_at FROM referral_profits WHERE referrer_id=? ORDER BY id DESC LIMIT 10", (uid,)).fetchall()
        txt = f"💰 أرباح الإحالة {REFERRAL_RATE}%:\n\n👥 إحالاتك: {total_ref}\n💵 إجمالي الأرباح: {earn}ج\n💳 الرصيد الحالي: {bal}ج\n\nآخر 10 أرباح:\n"
        if not profits:
            txt += "لا يوجد أرباح بعد، شارك رابطك!"
        else:
            for p in profits:
                txt += f"من {p[0]} - {p[1]}ج - {p[2]}\n"
        link = f"https://t.me/{BOT_USERNAME}?start={uid}"
        txt += f"\n🔗 رابطك:\n{link}"
        edit(chat, mid, txt, [[{"text":"🔙 رجوع","callback_data":"home"}]])
        answer(c["id"])
        return
    if data=="admin_panel" and uid==ADMIN_ID:
        total_users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        total_merch = db.execute("SELECT COUNT(*) FROM merchants WHERE status='approved'").fetchone()[0]
        pending_m = db.execute("SELECT COUNT(*) FROM merchants WHERE status='pending'").fetchone()[0]
        total_comm = db.execute("SELECT SUM(commission) FROM orders WHERE status='completed'").fetchone()[0] or 0
        total_ref_profits = db.execute("SELECT SUM(amount) FROM referral_profits").fetchone()[0] or 0
        total_orders = db.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        kb = []
        kb.append([{"text":f"👥 المستخدمين ({total_users})","callback_data":"admin_users"}])
        kb.append([{"text":f"🏪 التجار ({total_merch})","callback_data":"admin_merchants"}])
        kb.append([{"text":f"⏳ معلق ({pending_m})","callback_data":"admin_pending"}])
        kb.append([{"text":f"💰 أرباح العمولة {total_comm}ج","callback_data":"admin_profits"}])
        kb.append([{"text":f"💸 أرباح الإحالات {total_ref_profits}ج","callback_data":"admin_ref_profits"}])
        kb.append([{"text":f"🧾 طلبات العملاء ({total_orders})","callback_data":"admin_orders"}])
        kb.append([{"text":"🏠 الرئيسية","callback_data":"home"}])
        edit(chat, mid, f"👑 لوحة الأدمن\n\n👥 {total_users}\n🏪 {total_merch}\n⏳ {pending_m}\n💰 عمولة {COMMISSION_RATE}%: {total_comm}ج\n💸 إحالات {REFERRAL_RATE}%: {total_ref_profits}ج\nصافي لك: {total_comm - total_ref_profits}ج", kb)
        answer(c["id"])
        return
    if data=="admin_profits" and uid==ADMIN_ID:
        total = db.execute("SELECT SUM(commission) FROM orders WHERE status='completed'").fetchone()[0] or 0
        edit(chat, mid, f"💰 أرباح العمولة {COMMISSION_RATE}%: {total}ج", [[{"text":"🔙 رجوع","callback_data":"admin_panel"}]])
        answer(c["id"])
        return
    if data=="admin_ref_profits" and uid==ADMIN_ID:
        total = db.execute("SELECT SUM(amount) FROM referral_profits").fetchone()[0] or 0
        rows = db.execute("SELECT referrer_id,buyer_id,amount,created_at FROM referral_profits ORDER BY id DESC LIMIT 10").fetchall()
        txt = f"💸 أرباح الإحالات {REFERRAL_RATE}%: {total}ج\n\nآخر 10:\n"
        for r in rows:
            txt += f"مرجع {r[0]} من مشتري {r[1]} = {r[2]}ج {r[3]}\n"
        edit(chat, mid, txt, [[{"text":"🔙 رجوع","callback_data":"admin_panel"}]])
        answer(c["id"])
        return
    if data=="admin_pending" and uid==ADMIN_ID:
        pend = db.execute("SELECT user_id,store_name,phone,city,doc_photo FROM merchants WHERE status='pending' LIMIT 5").fetchall()
        if not pend:
            edit(chat, mid, "لا يوجد طلبات معلقة", [[{"text":"🔙 رجوع","callback_data":"admin_panel"}]])
        else:
            edit(chat, mid, f"⏳ {len(pend)} طلبات معلقة + مستندات")
            for m in pend:
                kb = []
                kb.append([{"text":"✅ قبول","callback_data":f"m_ok:{m[0]}"}])
                kb.append([{"text":"⏳ رفض مؤقت","callback_data":f"m_reject_temp:{m[0]}"},{"text":"🚫 رفض نهائي","callback_data":f"m_reject_perm:{m[0]}"}])
                send(chat, f"🔔 تاجر:\n{m[1]}\n{m[2]}\n{m[3]}\nID:{m[0]}", kb, photo=m[4])
        answer(c["id"])
        return
    if data=="admin_orders" and uid==ADMIN_ID:
        rows = db.execute("SELECT o.id, o.price, o.status, o.created_at, p.name FROM orders o LEFT JOIN products p ON p.id=o.product_id ORDER BY o.id DESC LIMIT 10").fetchall()
        if not rows:
            edit(chat, mid, "🧾 لا توجد طلبات محفوظة حتى الآن.", [[{"text":"🔙 لوحة الأدمن","callback_data":"admin_panel"}]])
        else:
            lines = ["🧾 آخر طلبات العملاء المحفوظة (حتى 10):"]
            keyboard = []
            for row in rows:
                product_name = row[4] or "منتج محذوف/غير متاح"
                lines.append(f"#{row[0]} — {product_name[:30]} — {row[1]}ج — {row[2]} — {row[3] or ''}")
                keyboard.append([{"text": f"تفاصيل الطلب #{row[0]}", "callback_data": f"admin_order:{row[0]}"}])
            keyboard.append([{"text":"🔙 لوحة الأدمن","callback_data":"admin_panel"}])
            edit(chat, mid, "\n".join(lines), keyboard)
        answer(c["id"])
        return
    if data.startswith("admin_order:") and uid==ADMIN_ID:
        oid = int(data.split(":", 1)[1])
        row = db.execute("SELECT o.id,o.buyer_id,o.merchant_id,o.price,o.commission,o.referral_comm,o.buyer_info,o.status,o.created_at,p.name FROM orders o LEFT JOIN products p ON p.id=o.product_id WHERE o.id=?", (oid,)).fetchone()
        if not row:
            edit(chat, mid, "لم أجد هذا الطلب في قاعدة البيانات.", [[{"text":"🔙 طلبات العملاء","callback_data":"admin_orders"}]])
        else:
            buyer_info = (row[6] or "غير مسجل")[:1400]
            product_name = row[9] or "منتج محذوف/غير متاح"
            message = (f"🧾 تفاصيل الطلب #{row[0]}\n\nالمنتج: {product_name}\nرقم العميل: {row[1]}\nرقم التاجر: {row[2]}\nالسعر: {row[3]}ج\nالعمولة: {row[4]}ج\nإحالة: {row[5] or 0}ج\nالحالة: {row[7]}\nالتاريخ: {row[8] or 'غير محدد'}\n\nبيانات العميل المسجلة:\n{buyer_info}")
            edit(chat, mid, message, [[{"text":"🔙 طلبات العملاء","callback_data":"admin_orders"}]])
        answer(c["id"])
        return
    if data=="my_pending":
        orders = db.execute("SELECT id,price,commission,buyer_info,status FROM orders WHERE merchant_id=? AND status IN ('pending_shipment','shipped') ORDER BY id DESC LIMIT 10", (uid,)).fetchall()
        if not orders:
            edit(chat, mid, "لا يوجد طلبات قيد الشحن", [[{"text":"🔙 رجوع","callback_data":"home"}]])
        else:
            txt = "📦 طلبات قيد الشحن:\n\n"
            kb = []
            for o in orders:
                txt += f"#{o[0]} - {o[1]}ج - {o[4]}\n{o[3][:30]}\n\n"
                if o[4]=="pending_shipment":
                    kb.append([{"text":f"📦 شحن #{o[0]}","callback_data":f"ship:{o[0]}"}])
            kb.append([{"text":"🔙 رجوع","callback_data":"home"}])
            edit(chat, mid, txt, kb)
        answer(c["id"])
        return
    if data.startswith("ship:"):
        if check_debt_and_block(chat, uid):
            answer(c["id"], "عليك عمولة مستحقة")
            return
        oid = int(data.split(":")[1])
        order = db.execute("SELECT buyer_id,merchant_id,price FROM orders WHERE id=?", (oid,)).fetchone()
        if not order or order[1]!=uid:
            answer(c["id"], "ليس طلبك")
            return
        db.execute("UPDATE orders SET status='shipped' WHERE id=?", (oid,))
        db.commit()
        edit(chat, mid, f"✅ تم شحن #{oid}")
        buyer_id = order[0]
        kb_confirm = []
        kb_confirm.append([{"text":f"✅ تأكيد استلام #{oid}","callback_data":f"confirm:{oid}"}])
        kb_confirm.append([{"text":f"❌ مشكلة #{oid}","callback_data":f"dispute:{oid}"}])
        send(buyer_id, f"📦 طلبك #{oid} تم شحنه! السعر {order[2]}ج عند الاستلام\nهل استلمت؟", kb_confirm)
        answer(c["id"], "تم الشحن")
        return
    if data.startswith("confirm:"):
        oid = int(data.split(":")[1])
        order = db.execute("SELECT buyer_id,merchant_id,price,commission FROM orders WHERE id=?", (oid,)).fetchone()
        if not order or order[0]!=uid:
            answer(c["id"], "ليس طلبك")
            return
        buyer_id = order[0]
        merchant_id = order[1]
        price = order[2]
        comm_amount = order[3]

        ref_row = db.execute("SELECT referred_by FROM users WHERE user_id=?", (buyer_id,)).fetchone()
        referral_amount = 0
        if ref_row and ref_row[0]:
            referrer_id = ref_row[0]
            active = db.execute("SELECT profit_active FROM users WHERE user_id=?", (referrer_id,)).fetchone()
            if active and active[0]==1:
                referral_amount = int(price * REFERRAL_RATE / 100)
                db.execute("INSERT INTO referral_profits(referrer_id,buyer_id,order_id,amount,created_at) VALUES(?,?,?,?,?)", (referrer_id, buyer_id, oid, referral_amount, time.strftime("%Y-%m-%d")))
                db.execute("UPDATE users SET referral_earnings=referral_earnings+?, referral_balance=referral_balance+? WHERE user_id=?", (referral_amount, referral_amount, referrer_id))
                try:
                    send(referrer_id, f"💰 ربح إحالة جديد!\nالمشتري {buyer_id} اشترى ب {price}ج\nربحك {referral_amount}ج ({REFERRAL_RATE}%) مدى الحياة!\nطلب #{oid}")
                except:
                    pass
        db.execute("UPDATE orders SET status='completed', referral_comm=? WHERE id=?", (referral_amount, oid))
        db.execute("UPDATE users SET sales=sales+1, unpaid_commission=unpaid_commission+? WHERE user_id=?", (comm_amount, merchant_id))
        db.commit()
        edit(chat, mid, f"✅ تم تأكيد استلام #{oid}")
        send(merchant_id, f"🎉 المشتري أكد استلام #{oid}\nالسعر {price}ج\nعمولة البوت {comm_amount}ج ({COMMISSION_RATE}%)\n⚠️ تم تسجيل العمولة على حسابك.")
        if ADMIN_ID:
            send(ADMIN_ID, f"💰 مكتمل #{oid} السعر {price}ج عمولة {comm_amount}ج إحالة {referral_amount}ج")
        answer(c["id"], "تم التأكيد")
        return
    if data.startswith("dispute:"):
        oid = int(data.split(":")[1])
        db.execute("UPDATE orders SET status='disputed' WHERE id=?", (oid,))
        db.commit()
        edit(chat, mid, f"⚠️ شكوى #{oid} الإدارة ستتواصل")
        if ADMIN_ID:
            send(ADMIN_ID, f"⚠️ شكوى طلب #{oid}")
        answer(c["id"])
        return
    if data=="buyer":
        kb = cat_kb("browse")
        kb.append([{"text":"🛍️ كل المنتجات","callback_data":"browse:all"}])
        kb.append([{"text":"🔍 بحث عن منتج","callback_data":"search"}])
        kb.append([{"text":"🏠 الرئيسية","callback_data":"home"}])
        edit(chat, mid, "🛍️ خدمات التسوق\nاختر قسمًا، تصفح كل المنتجات، أو ابحث باسم المنتج:", kb)
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
            edit(chat, mid, f"{title}\nما في منتجات", [[{"text":"🔙 رجوع","callback_data":"buyer"}]])
        else:
            edit(chat, mid, f"{title} - {len(prods)} منتج")
            for p in prods:
                store = db.execute("SELECT store_name FROM merchants WHERE user_id=?", (p[1],)).fetchone()
                sname = store[0] if store else "متجر"
                kb = []
                kb.append([{"text":f"🛒 شراء {p[3]}ج عند الاستلام","callback_data":f"buy:{p[0]}"}])
                send(chat, f"📦 {p[2]}\n💰 {p[3]}ج عند الاستلام\n📝 {p[5]}\n🏷️ {p[6]}\n🏪 {sname}", kb, photo=p[4])
        answer(c["id"])
        return
    if data=="merchant":
        open_merchant(chat, uid, mid)
        answer(c["id"])
        return
    if data=="prod_price_confirm":
        if get_state(uid) != "await_prod_price_confirm":
            answer(c["id"], "انتهت جلسة التسعير أو تم التعامل معها مسبقاً")
            return
        tmp = get_temp(uid)
        set_state(uid, "await_prod_cat", tmp)
        edit(chat, mid, f"✅ تم اعتماد السعر النهائي {tmp['price']}ج\nاختر قسم المنتج:", cat_kb("setcat"))
        answer(c["id"], "تم اعتماد السعر")
        return

    if data=="prod_price_cancel":
        if get_state(uid) != "await_prod_price_confirm":
            answer(c["id"], "انتهت جلسة التسعير أو تم التعامل معها مسبقاً")
            return
        set_state(uid, "await_prod_price", {})
        edit(chat, mid, "❌ تم إلغاء السعر. أرسل السعر الأساسي الجديد أرقام فقط من غير عمولة المتجر:")
        answer(c["id"], "أرسل السعر الجديد")
        return

    if data.startswith("setcat:"):
        cat = data.split(":", 1)[1]
        tmp = get_temp(uid)
        tmp["cat"] = cat
        set_state(uid, "await_prod_desc", tmp)
        edit(chat, mid, f"اخترت {cat} ✅\nأرسل وصف المنتج:")
        answer(c["id"])
        return
    if data=="add":
        if check_debt_and_block(chat, uid):
            answer(c["id"], "عليك عمولة مستحقة")
            return
        set_state(uid, "await_prod_photo", {})
        send(chat, "أرسل صورة المنتج:")
        answer(c["id"])
        return
    if data=="sales":
        total = db.execute("SELECT COUNT(*) FROM orders WHERE merchant_id=? AND status='completed'", (uid,)).fetchone()[0]
        total_comm = db.execute("SELECT SUM(commission) FROM orders WHERE merchant_id=? AND status='completed'", (uid,)).fetchone()[0] or 0
        cnt = db.execute("SELECT COUNT(*) FROM products WHERE merchant_id=? AND status='approved'", (uid,)).fetchone()[0]
        debt = get_user_debt(uid)
        
        msg = f"📊 مبيعاتك:\n📦 المنتجات: {cnt}\n✅ الطلبات المكتملة: {total}\n💰 إجمالي رسوم السوق: {total_comm}ج\n💳 العمولة غير المدفوعة العليك: {debt}ج"
        kb = [[{"text":"📋 آخر الطلبات","callback_data":"orders"}]]
        if debt > 0:
            kb.append([{"text": "💳 دفع العمولة العليك", "callback_data": "pay_commission"}])
        kb.append([{"text":"🏠 الرئيسية","callback_data":"home"}])
        
        edit(chat, mid, msg, kb)
        answer(c["id"])
        return
    if data=="orders":
        ords = db.execute("SELECT id,price,commission,status FROM orders WHERE merchant_id=? ORDER BY id DESC LIMIT 5", (uid,)).fetchall()
        if not ords:
            edit(chat, mid, "ما جاك طلبات", [[{"text":"🔙 رجوع","callback_data":"sales"}]])
        else:
            t = "📋 آخر 5:\n\n"
            for o in ords:
                t += f"#{o[0]} - {o[1]}ج عمولة {o[2]}ج {o[3]}\n"
            edit(chat, mid, t, [[{"text":"🔙 رجوع","callback_data":"sales"}]])
        answer(c["id"])
        return
    if data.startswith("buy:"):
        if check_debt_and_block(chat, uid):
            answer(c["id"], "عليك عمولة مستحقة")
            return
        pid = int(data.split(":")[1])
        p = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
        if not p:
            answer(c["id"], "غير موجود")
            return
        base_price = p[9] if len(p) > 9 and p[9] else int(round(p[3] * 100 / (100 + COMMISSION_RATE)))
        comm = p[3] - base_price
        set_state(uid, "await_cod_info", {"pid":p[0],"mid":p[1],"price":p[3],"pname":p[2],"commission":comm})
        send(chat, f"اسم المنتج: {p[2]}\nسعر المنتج: {p[3]} جنيه\nالدفع بعد الاستلام\n\nأرسل اسمك كاملًا ورقمين للتواصل وموقعك بدقة:")
        answer(c["id"])
        return
    if data.startswith("m_ok:"):
        mid_t = int(data.split(":")[1])
        db.execute("UPDATE merchants SET status='approved', reject_reason='' WHERE user_id=?", (mid_t,))
        db.commit()
        edit(chat, mid, f"✅ تم قبول التاجر {mid_t}", [])
        try:
            send(mid_t, "🎉 تم قبول متجرك بعد مراجعة المستند.\nاستخدم /start لفتح لوحة التاجر وإضافة المنتجات ومتابعة الطلبات.", main_kb=True)
        except:
            pass
        answer(c["id"])
        return
    if data.startswith("m_reject_temp:"):
        target = int(data.split(":")[1])
        set_state(uid, f"await_reject_reason_temp_m_{target}", {"review_message_id": mid})
        edit(chat, mid, f"⏳ رفض مؤقت للتاجر {target}\nأرسل السبب:", [])
        answer(c["id"])
        return
    if data.startswith("m_reject_perm:"):
        target = int(data.split(":")[1])
        set_state(uid, f"await_reject_reason_perm_m_{target}", {"review_message_id": mid})
        edit(chat, mid, f"🚫 رفض نهائي للتاجر {target}\nأرسل السبب:", [])
        answer(c["id"])
        return
    if data.startswith("m_no:"):
        mid_t = int(data.split(":")[1])
        db.execute("UPDATE merchants SET status='rejected_temp', reject_reason='رفض صامت' WHERE user_id=?", (mid_t,))
        db.commit()
        edit(chat, mid, f"🔇 تم إلغاء طلب التاجر {mid_t}.", [])
        answer(c["id"])
        return
    if data.startswith("p_ok:"):
        pid = int(data.split(":")[1])
        db.execute("UPDATE products SET status='approved', reject_reason='' WHERE id=?", (pid,))
        db.commit()
        p = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
        edit(chat, mid, f"✅ تم نشر {p[2] if p else pid}", [])
        if p:
            try:
                send(p[1], f"✅ تم نشر منتجك {p[2]}", main_kb=True)
            except:
                pass
        answer(c["id"])
        return
    if data.startswith("p_reject_temp:"):
        target = int(data.split(":")[1])
        set_state(uid, f"await_reject_reason_temp_p_{target}", {"review_message_id": mid})
        edit(chat, mid, f"⏳ رفض مؤقت للمنتج {target}\nأرسل السبب:", [])
        answer(c["id"])
        return
    if data.startswith("p_reject_perm:"):
        target = int(data.split(":")[1])
        set_state(uid, f"await_reject_reason_perm_p_{target}", {"review_message_id": mid})
        edit(chat, mid, f"🚫 رفض نهائي للمنتج {target}\nأرسل السبب:", [])
        answer(c["id"])
        return
    if data.startswith("p_no:"):
        pid = int(data.split(":")[1])
        db.execute("UPDATE products SET status='rejected_temp', reject_reason='كانسل' WHERE id=?", (pid,))
        db.commit()
        edit(chat, mid, f"🔇 تم إلغاء طلب المنتج {pid}.", [])
        answer(c["id"])
        return
    if data=="home":
        merchant_row = db.execute("SELECT status FROM merchants WHERE user_id=?", (uid,)).fetchone()
        if merchant_row and merchant_row[0] in ["approved", "pending", "banned"]:
            open_merchant(chat, uid, mid)
        else:
            edit(chat, mid, "مرحبا بك في سوق السودان\nهنا ستجد ما تريده إن شاء الله وبأقل الأسعار.", [])
            send(chat, "مرحبا بك في سوق السودان\nهنا ستجد ما تريده إن شاء الله وبأقل الأسعار.", main_kb=True)
        answer(c["id"])
        return

def main():
    keep_alive()
    setup()
    off = 0
    print(f"Bot Started Successfully - Commission: {COMMISSION_RATE}%")
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

