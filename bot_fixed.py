from flask import Flask
import threading

app = Flask('')
@app.route('/')
def home():
    return "Bot is Alive!"

def run():
    app.run(host='0.0.0.0', port=10000)

threading.Thread(target=run).start()
from keep_alive import keep_alive
import os
import json
import time
import sqlite3
import re
import unicodedata
from difflib import SequenceMatcher
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

PAYMENT_ACCOUNT_NUMBER = "7696230"
PAYMENT_ACCOUNT_NAME = "بدور عبدالكريم عيسى النعيم"

CATEGORIES = ["👕 ملابس", "🍳 أواني منزلية", "🔥 عروض وخصم", "⭐ رائج", "👗 موضة", "📦 أخرى", "🌾 أعلاف حيوانات", "💄 منتجات تجميل", "🌱 أسمدة زراعية", "💪 منتجات جيم"]

db = sqlite3.connect(DB, check_same_thread=False)
db.executescript('''
CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY, state TEXT, temp TEXT, points INTEGER DEFAULT 0, purchases INTEGER DEFAULT 0, sales INTEGER DEFAULT 0, referred_by INTEGER, is_banned INTEGER DEFAULT 0, profit_active INTEGER DEFAULT 0, referral_earnings INTEGER DEFAULT 0, referral_balance INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS merchants(user_id INTEGER PRIMARY KEY, store_name TEXT, phone TEXT, city TEXT, doc_photo TEXT, status TEXT DEFAULT 'pending', reject_reason TEXT);
CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY AUTOINCREMENT, merchant_id INTEGER, name TEXT, price INTEGER, photo_id TEXT, description TEXT, category TEXT, status TEXT DEFAULT 'pending', reject_reason TEXT, base_price INTEGER);
CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT, buyer_id INTEGER, product_id INTEGER, merchant_id INTEGER, price INTEGER, commission INTEGER, referral_comm INTEGER, buyer_info TEXT, status TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS referrals(id INTEGER PRIMARY KEY AUTOINCREMENT, referrer_id INTEGER, referred_id INTEGER, created_at TEXT);
CREATE TABLE IF NOT EXISTS referral_profits(id INTEGER PRIMARY KEY AUTOINCREMENT, referrer_id INTEGER, buyer_id INTEGER, order_id INTEGER, amount INTEGER, created_at TEXT);
CREATE TABLE IF NOT EXISTS commission_payments(id INTEGER PRIMARY KEY AUTOINCREMENT, merchant_id INTEGER, amount INTEGER, proof_photo TEXT, status TEXT DEFAULT 'pending', created_at TEXT, reviewed_at TEXT);
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


def get_merchant_dues(uid):
    total_commission = db.execute(
        "SELECT SUM(commission) FROM orders WHERE merchant_id=? AND status='completed'",
        (uid,)
    ).fetchone()[0] or 0
    total_paid = db.execute(
        "SELECT SUM(amount) FROM commission_payments WHERE merchant_id=? AND status='approved'",
        (uid,)
    ).fetchone()[0] or 0
    pending_pay = db.execute(
        "SELECT SUM(amount) FROM commission_payments WHERE merchant_id=? AND status='pending'",
        (uid,)
    ).fetchone()[0] or 0
    due = total_commission - total_paid
    return {
        "total_commission": total_commission,
        "total_paid": total_paid,
        "pending_pay": pending_pay,
        "due": due if due > 0 else 0
    }


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
            dues = get_merchant_dues(uid)
            due_text = ""
            if dues["due"] > 0:
                due_text = f"\n\n💰 عمولات مستحقة عليك: {dues['due']}ج\n⚠️ سدد العمولة لرفع منتجات جديدة أو استلام طلبات."
                if dues["pending_pay"] > 0:
                    due_text += f"\n⏳ عندك دفعة قيد المراجعة: {dues['pending_pay']}ج"
            elif dues["pending_pay"] > 0:
                due_text = f"\n\n⏳ عندك دفعة قيد المراجعة: {dues['pending_pay']}ج"
            else:
                due_text = "\n\n✅ لا توجد عمولات مستحقة عليك."
            text = f"أهلاً يا صاحب متجر {merchant[1]} ✅\nمنتجاتك: {product_count}\nطلبات قيد الشحن: {pending_orders}{due_text}"
            keyboard = []
            if dues["due"] > 0:
                keyboard.append([{"text": f"💳 تسديد العمولة ({dues['due']}ج)", "callback_data": "pay_commission"}])
                keyboard.append([{"text": "📊 مبيعاتي", "callback_data": "sales"}])
            else:
                keyboard.append([{"text": "➕ إضافة منتج", "callback_data": "add"}, {"text": "📊 مبيعاتي", "callback_data": "sales"}])
            keyboard.append([{"text": f"📦 طلبات تحت الشحن ({pending_orders})", "callback_data": "my_pending"}])
            keyboard.append([{"text": "💳 سجل مدفوعاتي", "callback_data": "my_payments"}])
            keyboard.append([{"text": "🛍️ تصفح السوق", "callback_data": "buyer"}])
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
