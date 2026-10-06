from keep_alive import keep_alive
import os, json, time, sqlite3
from urllib.request import Request, urlopen
from urllib.parse import urlencode

TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
BOT_USERNAME = os.environ.get("BOT_USERNAME", "your_bot") # اكتب يوزر البوت هنا بدون @
API = f"https://api.telegram.org/bot{TOKEN}"
DB = "marketplace.db"

CATEGORIES = ["👕 ملابس", "🍳 أواني منزلية", "🔥 عروض وخصم", "⭐ رائج", "👗 موضة", "📦 أخرى"]

db = sqlite3.connect(DB, check_same_thread=False)
db.executescript("""
CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY, state TEXT, temp TEXT, points INTEGER DEFAULT 0, purchases INTEGER DEFAULT 0, sales INTEGER DEFAULT 0, referred_by INTEGER);
CREATE TABLE IF NOT EXISTS merchants(user_id INTEGER PRIMARY KEY, store_name TEXT, phone TEXT, city TEXT, status TEXT DEFAULT 'pending');
CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY AUTOINCREMENT, merchant_id INTEGER, name TEXT, price INTEGER, photo_id TEXT, description TEXT, category TEXT, status TEXT DEFAULT 'pending');
CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT, buyer_id INTEGER, product_id INTEGER, merchant_id INTEGER, buyer_info TEXT, payment_type TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS referrals(id INTEGER PRIMARY KEY AUTOINCREMENT, referrer_id INTEGER, referred_id INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
""")
db.commit()

# --- دوال تليجرام ---
def api(m,d=None):
    d=d or {}
    try:
        r=Request(API+"/"+m,data=urlencode(d).encode(),headers={"Content-Type":"application/x-www-form-urlencoded"})
        with urlopen(r,timeout=30) as x: return json.loads(x.read())
    except Exception as e:
        print(e); return {}

def send(chat,text,kb=None,photo=None,reply_kb=False):
    if photo:
        d={"chat_id":chat,"photo":photo,"caption":text}
        if kb: d["reply_markup"]=json.dumps({"inline_keyboard":kb},ensure_ascii=False)
        return api("sendPhoto",d)
    d={"chat_id":chat,"text":text}
    if kb:
        d["reply_markup"]=json.dumps({"inline_keyboard":kb},ensure_ascii=False)
    elif reply_kb:
        # زر التحديث المقترح
        d["reply_markup"]=json.dumps({"keyboard":[["🔄 تحديث الصفحة /start"],["📊 حسابي ونقاطي"]],"resize_keyboard":True},ensure_ascii=False)
    return api("sendMessage",d)

def edit(chat,msg,text,kb=None):
    d={"chat_id":chat,"message_id":msg,"text":text}
    if kb: d["reply_markup"]=json.dumps({"inline_keyboard":kb},ensure_ascii=False)
    try: return api("editMessageText",d)
    except:
        d2={"chat_id":chat,"message_id":msg,"caption":text}
        if kb: d2["reply_markup"]=json.dumps({"inline_keyboard":kb},ensure_ascii=False)
        try: return api("editMessageCaption",d2)
        except: return None

def answer(cid,txt=""): return api("answerCallbackQuery",{"callback_query_id":cid,"text":txt})
def get_temp(uid):
    row=db.execute("SELECT temp FROM users WHERE user_id=?",(uid,)).fetchone()
    if row and row[0]:
        try: return json.loads(row[0])
        except: return {}
    return {}
def set_state(uid,st,tmp=None):
    db.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)",(uid,))
    if tmp is not None: db.execute("UPDATE users SET state=?, temp=? WHERE user_id=?",(st,json.dumps(tmp,ensure_ascii=False),uid))
    else: db.execute("UPDATE users SET state=? WHERE user_id=?",(st,uid))
    db.commit()
def get_state(uid):
    row=db.execute("SELECT state FROM users WHERE user_id=?",(uid,)).fetchone()
    return row[0] if row else None
def cat_kb(pref):
    kb=[]
    for i in range(0,len(CATEGORIES),2):
        r=[{"text":CATEGORIES[i],"callback_data":f"{pref}:{CATEGORIES[i]}"}]
        if i+1<len(CATEGORIES): r.append({"text":CATEGORIES[i+1],"callback_data":f"{pref}:{CATEGORIES[i+1]}"})
        kb.append(r)
    return kb

def setup_bot():
    # يخلي /start مقترح فوق
    try:
        cmds=json.dumps([{"command":"start","description":"🏠 الرئيسية - تحديث الصفحة"}],ensure_ascii=False)
        api("setMyCommands",{"commands":cmds})
    except: pass

# --- معالجة الرسائل ---
def handle_msg(m):
    uid=m["from"]["id"]; chat=m["chat"]["id"]; txt=m.get("text",""); st=get_state(uid); tmp=get_temp(uid)
    db.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)",(uid,)); db.commit()

    # زر التحديث المقترح
    if txt in ["🔄 تحديث الصفحة /start","🔄 تحديث الصفحة","/start","تحديث","start"]:
        txt="/start"

    if txt.startswith("/start"):
        # نظام الإحالة
        parts=txt.split()
        if len(parts)>1 and parts[1].isdigit():
            ref_id=int(parts[1])
            if ref_id!=uid:
                already=db.execute("SELECT * FROM referrals WHERE referred_id=?",(uid,)).fetchone()
                user_ref=db.execute("SELECT referred_by FROM users WHERE user_id=?",(uid,)).fetchone()
                if not already and (not user_ref or not user_ref[0]):
                    db.execute("INSERT INTO referrals(referrer_id,referred_id) VALUES(?,?)",(ref_id,uid))
                    db.execute("UPDATE users SET points=points+10 WHERE user_id=?",(ref_id,))
                    db.execute("UPDATE users SET referred_by=? WHERE user_id=?",(ref_id,uid))
                    db.commit()
                    try: send(ref_id,f"🎉 مبروك! شخص جديد سجل برابطك وحصلت على 10 نقاط!\nنقاطك الآن: {db.execute('SELECT points FROM users WHERE user_id=?',(ref_id,)).fetchone()[0]}")
                    except: pass

        merch=db.execute("SELECT * FROM merchants WHERE user_id=?",(uid,)).fetchone()
        if merch and merch[4]=="approved":
            cnt=db.execute("SELECT COUNT(*) FROM products WHERE merchant_id=? AND status='approved'",(uid,)).fetchone()[0]
            kb=[[{"text":"➕ إضافة منتج","callback_data":"add"},{"text":"📊 مبيعاتي","callback_data":"sales"}],[{"text":"🛍️ تصفح السوق","callback_data":"buyer"}],[{"text":"📊 حسابي ونقاطي","callback_data":"my_account"}]]
            send(chat,f"أهلا بك يا صاحب متجر {merch[1]} ✅\n\nمنتجاتك: {cnt}\n\nلو الصفحة علقت دوس 🔄 تحديث تحت",kb,reply_kb=True); return
        if merch and merch[4]=="pending": send(chat,f"متجرك '{merch[1]}' قيد المراجعة ⏳",reply_kb=True); return
        kb=[[{"text":"🛍️ أنا مشتري","callback_data":"buyer"},{"text":"🏪 أنا تاجر","callback_data":"merchant"}],[{"text":"📊 حسابي ونقاطي","callback_data":"my_account"}]]
        send(chat,"أهلا بك في سوق طوّر نفسك 🌟\n\nاختر هل أنت مشتري أم تاجر؟\n\n💡 لو علقت الصفحة دوس زر التحديث تحت",kb,reply_kb=True); return

    if txt=="📊 حسابي ونقاطي" or txt=="حسابي":
        row=db.execute("SELECT points,purchases,sales FROM users WHERE user_id=?",(uid,)).fetchone()
        points=row[0] if row else 0; purch=row[1] if row else 0; sales=row[2] if row else 0
        ref_link=f"https://t.me/{BOT_USERNAME}?start={uid}" if BOT_USERNAME!="your_bot" else f"رابطك: /start {uid}"
        txt_acc=f"📊 حسابك:\n\n🛒 منتجات اشتريتها: {purch}\n📦 منتجات بعتها: {sales}\n⭐ نقاط الإحالة: {points}\n\n🔗 رابط الإحالة الخاص بك:\n{ref_link}\n\nكل شخص يسجل برابطك تاخد 10 نقاط!\nقريبا حنضيف متجر نقاط وعروض 🎁"
        send(chat,txt_acc,reply_kb=True); return

    # رفض بتعليق
    if st and st.startswith("await_reject_reason_"):
        reason=txt
        typ=st.split("_")[-2] # m or p
        target_id=int(st.split("_")[-1])
        if typ=="m":
            db.execute("UPDATE merchants SET status='rejected' WHERE user_id=?",(target_id,)); db.commit()
            send(chat,f"تم رفض التاجر {target_id} مع إرسال السبب.")
            send(target_id,f"❌ تم رفض متجرك للسبب التالي:\n\n{reason}\n\nيمكنك التعديل وإعادة التقديم.")
        else:
            db.execute("UPDATE products SET status='rejected' WHERE id=?",(target_id,)); db.commit()
            prod=db.execute("SELECT merchant_id,name FROM products WHERE id=?",(target_id,)).fetchone()
            send(chat,f"تم رفض المنتج {target_id} مع إرسال السبب.")
            if prod: send(prod[0],f"❌ تم رفض منتجك '{prod[1]}' للسبب:\n\n{reason}")
        set_state(uid,None,{}); return

    if st=="await_store_name": tmp["store_name"]=txt; set_state(uid,"await_phone",tmp); send(chat,"تمام ✅\nالآن أرسل رقم واتساب:"); return
    if st=="await_phone": tmp["phone"]=txt; set_state(uid,"await_city",tmp); send(chat,"أرسل مدينتك:"); return
    if st=="await_city":
        tmp["city"]=txt; db.execute("INSERT OR REPLACE INTO merchants VALUES(?,?,?,?,?)",(uid,tmp["store_name"],tmp["phone"],tmp["city"],"pending")); db.commit(); set_state(uid,None,{})
        send(chat,"✅ تم إرسال طلبك للإدارة.",reply_kb=True)
        kb=[[{"text":"✅ موافقة","callback_data":f"m_ok:{uid}"}],[{"text":"❌ رفض بتعليق","callback_data":f"m_reject:{uid}"},{"text":"🔇 كانسل (رفض صامت)","callback_data":f"m_no:{uid}"}]]
        if ADMIN_ID: send(ADMIN_ID,f"🔔 تاجر جديد:\n{tmp['store_name']}\n{tmp['phone']}\n{tmp['city']}\nID:{uid}",kb)
        return
    if st=="await_prod_name": tmp["name"]=txt; set_state(uid,"await_prod_price",tmp); send(chat,"أرسل السعر أرقام فقط:"); return
    if st=="await_prod_price":
        if not txt.isdigit(): send(chat,"أرقام فقط:"); return
        tmp["price"]=int(txt); set_state(uid,"await_prod_cat",tmp); send(chat,"اختر قسم المنتج:",cat_kb("setcat")); return
    if st=="await_prod_desc":
        tmp["desc"]=txt; db.execute("INSERT INTO products(merchant_id,name,price,photo_id,description,category,status) VALUES(?,?,?,?,?,?,?)",(uid,tmp["name"],tmp["price"],tmp["photo"],tmp["desc"],tmp.get("cat","📦 أخرى"),"pending")); db.commit(); pid=db.execute("SELECT last_insert_rowid()").fetchone()[0]; set_state(uid,None,{})
        send(chat,f"✅ تم رفع المنتج في {tmp.get('cat')} بانتظار الموافقة.",reply_kb=True)
        kb=[[{"text":"✅ موافقة","callback_data":f"p_ok:{pid}"}],[{"text":"❌ رفض بتعليق","callback_data":f"p_reject:{pid}"},{"text":"🔇 كانسل","callback_data":f"p_no:{pid}"}]]
        if ADMIN_ID: send(ADMIN_ID,f"🔔 منتج جديد:\n{tmp['name']} - {tmp['price']}ج\n🏷️ {tmp.get('cat')}\n📝 {tmp['desc']}",kb,photo=tmp["photo"])
        return
    if st=="await_cod":
        db.execute("INSERT INTO orders(buyer_id,product_id,merchant_id,buyer_info,payment_type,status) VALUES(?,?,?,?,?,?)",(uid,tmp["pid"],tmp["mid"],txt,"عند الاستلام","confirmed")); db.commit(); db.execute("UPDATE users SET purchases=purchases+1 WHERE user_id=?",(uid,)); db.execute("UPDATE users SET sales=sales+1 WHERE user_id=?",(tmp["mid"],)); db.commit()
        oid=db.execute("SELECT last_insert_rowid()").fetchone()[0]; set_state(uid,None,{}); send(chat,f"✅ تم تأكيد طلبك #{oid}\n💵 عند الاستلام\nسيتواصل البائع قريبا.",reply_kb=True); send(tmp["mid"],f"🔔 طلب جديد #{oid} 💵 COD\n📦 {tmp['pname']}\n👤 {txt}"); return
    if st=="await_pre":
        info=f"رقم: {txt}"; db.execute("INSERT INTO orders(buyer_id,product_id,merchant_id,buyer_info,payment_type,status) VALUES(?,?,?,?,?,?)",(uid,tmp["pid"],tmp["mid"],info,"قبل الاستلام","pending_call")); db.commit(); db.execute("UPDATE users SET purchases=purchases+1 WHERE user_id=?",(uid,)); db.execute("UPDATE users SET sales=sales+1 WHERE user_id=?",(tmp["mid"],)); db.commit()
        oid=db.execute("SELECT last_insert_rowid()").fetchone()[0]; set_state(uid,None,{}); send(chat,f"✅ طلبك #{oid} محفوظ\n💳 قبل الاستلام\n📞 {txt}\nالبائع سيتصل بك.",reply_kb=True); send(tmp["mid"],f"🔔 طلب #{oid} 💳 prepaid\n📦 {tmp['pname']}\n📞 {txt}\nاتصل الآن!"); return
    if "photo" in m and st=="await_prod_photo": tmp["photo"]=m["photo"][-1]["file_id"]; set_state(uid,"await_prod_name",tmp); send(chat,"الصورة وصلت ✅\nأرسل اسم المنتج:"); return

def handle_cb(c):
    uid=c["from"]["id"]; chat=c["message"]["chat"]["id"]; mid=c["message"]["message_id"]; data=c["data"]
    if data=="buyer":
        kb=cat_kb("browse"); kb.append([{"text":"🔍 كل المنتجات","callback_data":"browse:all"}]); kb.append([{"text":"🏠 الرئيسية","callback_data":"home"}]); edit(chat,mid,"🛍️ اختر القسم:",kb); answer(c["id"]); return
    if data.startswith("browse:"):
        cat=data.split(":",1)[1]
        if cat=="all": prods=db.execute("SELECT * FROM products WHERE status='approved' ORDER BY id DESC LIMIT 15").fetchall(); title="كل المنتجات"
        else: prods=db.execute("SELECT * FROM products WHERE status='approved' AND category=? ORDER BY id DESC LIMIT 15",(cat,)).fetchall(); title=f"قسم {cat}"
        if not prods: edit(chat,mid,f"{title}\n\nما في منتجات 🌙",[[{"text":"🔙 رجوع","callback_data":"buyer"}]])
        else:
            edit(chat,mid,f"{title} - {len(prods)} منتج 👇")
            for p in prods:
                store=db.execute("SELECT store_name FROM merchants WHERE user_id=?",(p[1],)).fetchone(); sname=store[0] if store else "متجر"
                kb=[[{"text":f"🛒 شراء - {p[3]} جنيه","callback_data":f"buy:{p[0]}"}]]
                send(chat,f"📦 {p[2]}\n💰 {p[3]}ج\n🏷️ {p[6]}\n📝 {p[5]}\n🏪 {sname}",kb,photo=p[4])
        answer(c["id"]); return
    if data=="merchant":
        merch=db.execute("SELECT * FROM merchants WHERE user_id=?",(uid,)).fetchone()
        if merch and merch[4]=="pending": edit(chat,mid,"طلبك قيد المراجعة ⏳")
        elif merch and merch[4]=="approved":
            cnt=db.execute("SELECT COUNT(*) FROM products WHERE merchant_id=? AND status='approved'",(uid,)).fetchone()[0]
            edit(chat,mid,f"أهلا {merch[1]} ✅\nمنتجاتك: {cnt}",[[{"text":"➕ إضافة منتج","callback_data":"add"},{"text":"📊 مبيعاتي","callback_data":"sales"}],[{"text":"📊 حسابي","callback_data":"my_account"}]])
        else: set_state(uid,"await_store_name",{}); edit(chat,mid,"أرسل اسم المتجر:")
        answer(c["id"]); return
    if data.startswith("setcat:"): cat=data.split(":",1)[1]; tmp=get_temp(uid); tmp["cat"]=cat; set_state(uid,"await_prod_desc",tmp); edit(chat,mid,f"اخترت {cat} ✅\nأرسل وصف المنتج:"); answer(c["id"]); return
    if data=="add": set_state(uid,"await_prod_photo",{}); send(chat,"أرسل صورة المنتج:"); answer(c["id"]); return
    if data=="sales":
        total=db.execute("SELECT COUNT(*) FROM orders WHERE merchant_id=?",(uid,)).fetchone()[0]
        conf=db.execute("SELECT COUNT(*) FROM orders WHERE merchant_id=? AND status='confirmed'",(uid,)).fetchone()[0]
        cnt=db.execute("SELECT COUNT(*) FROM products WHERE merchant_id=? AND status='approved'",(uid,)).fetchone()[0]
        edit(chat,mid,f"📊 مبيعاتك:\n\n📦 منتجاتك: {cnt}\n🛒 طلبات: {total}\n✅ مؤكدة: {conf}",[[{"text":"📋 آخر الطلبات","callback_data":"orders"},{"text":"🏠 الرئيسية","callback_data":"home"}]]); answer(c["id"]); return
    if data=="orders":
        ords=db.execute("SELECT * FROM orders WHERE merchant_id=? ORDER BY id DESC LIMIT 5",(uid,)).fetchall()
        if not ords: edit(chat,mid,"ما جاك طلبات 🌙",[[{"text":"🔙 رجوع","callback_data":"sales"}]])
        else:
            t="📋 آخر 5 طلبات:\n\n"
            for o in ords: prod=db.execute("SELECT name FROM products WHERE id=?",(o[2],)).fetchone(); pn=prod[0] if prod else o[2]; t+=f"{'✅' if o[6]=='confirmed' else '⏳'} #{o[0]} - {pn}\nالدفع: {o[5]}\n{o[4][:30]}\n\n"
            edit(chat,mid,t,[[{"text":"🔙 رجوع","callback_data":"sales"}]])
        answer(c["id"]); return
    if data=="my_account":
        row=db.execute("SELECT points,purchases,sales FROM users WHERE user_id=?",(uid,)).fetchone()
        points=row[0] if row else 0; purch=row[1] if row else 0; sales=row[2] if row else 0
        ref_link=f"https://t.me/{BOT_USERNAME}?start={uid}" if BOT_USERNAME!="your_bot" else f"/start {uid}"
        edit(chat,mid,f"📊 حسابك:\n\n🛒 اشتريت: {purch} منتج\n📦 بعت: {sales} منتج\n⭐ نقاطك: {points}\n\n🔗 رابط الإحالة:\n{ref_link}\n\nكل إحالة = 10 نقاط 🎁",[[{"text":"🏠 الرئيسية","callback_data":"home"}]]); answer(c["id"]); return
    if data.startswith("buy:"):
        pid=int(data.split(":")[1]); p=db.execute("SELECT * FROM products WHERE id=?",(pid,)).fetchone()
        if not p: answer(c["id"],"غير موجود"); return
        set_state(uid,"choice",{"pid":p[0],"mid":p[1],"price":p[3],"pname":p[2]})
        kb=[[{"text":"💵 عند الاستلام","callback_data":f"cod:{p[0]}"}],[{"text":"💳 قبل الاستلام","callback_data":f"pre:{p[0]}"}]]
        send(chat,f"📦 {p[2]}\n💰 {p[3]}ج\n\nاختر طريقة الدفع:",kb); answer(c["id"]); return
    if data.startswith("cod:"): tmp=get_temp(uid); set_state(uid,"await_cod",tmp); send(chat,"💵 الدفع عند الاستلام\n\nأرسل الاسم - الهاتف - العنوان:"); answer(c["id"]); return
    if data.startswith("pre:"): tmp=get_temp(uid); set_state(uid,"await_pre",tmp); send(chat,"💳 الدفع قبل الاستلام\n\nأرسل رقم هاتفك، البائع سيتصل بك:"); answer(c["id"]); return

    # --- نظام الموافقة / الرفض الجديد ---
    if data.startswith("m_ok:"):
        mid_t=int(data.split(":")[1]); db.execute("UPDATE merchants SET status='approved' WHERE user_id=?",(mid_t,)); db.commit(); edit(chat,mid,f"✅ تم قبول التاجر {mid_t}"); send(mid_t,"🎉 مبروك! تم قبول متجرك. /start",reply_kb=True); answer(c["id"]); return
    if data.startswith("m_reject:"):
        target=int(data.split(":")[1]); set_state(uid,f"await_reject_reason_m_{target}",{}); edit(chat,mid,f"✍️ أرسل سبب رفض التاجر {target}:\nسيتم إرساله للمستخدم."); answer(c["id"]); return
    if data.startswith("m_no:"):
        mid_t=int(data.split(":")[1]); db.execute("UPDATE merchants SET status='rejected' WHERE user_id=?",(mid_t,)); db.commit(); edit(chat,mid,f"🔇 تم رفض التاجر {mid_t} بصمت (ما وصلتو رسالة)"); answer(c["id"]); return

    if data.startswith("p_ok:"):
        pid=int(data.split(":")[1]); db.execute("UPDATE products SET status='approved' WHERE id=?",(pid,)); db.commit(); p=db.execute("SELECT * FROM products WHERE id=?",(pid,)).fetchone(); edit(chat,mid,f"✅ تم نشر {p[2] if p else pid}");
        if p: send(p[1],f"✅ تم نشر منتجك {p[2]}",reply_kb=True); answer(c["id"]); return
    if data.startswith("p_reject:"):
        target=int(data.split(":")[1]); set_state(uid,f"await_reject_reason_p_{target}",{}); edit(chat,mid,f"✍️ أرسل سبب رفض المنتج {target}:"); answer(c["id"]); return
    if data.startswith("p_no:"):
        pid=int(data.split(":")[1]); db.execute("UPDATE products SET status='rejected' WHERE id=?",(pid,)); db.commit(); edit(chat,mid,f"🔇 تم رفض المنتج {pid} بصمت - ما وصلت رسالة للمستخدم (كانسل)"); answer(c["id"]); return

    if data=="home":
        merch=db.execute("SELECT * FROM merchants WHERE user_id=?",(uid,)).fetchone()
        if merch and merch[4]=="approved": edit(chat,mid,f"🏠 لوحة التاجر {merch[1]}",[[{"text":"➕ إضافة منتج","callback_data":"add"},{"text":"📊 مبيعاتي","callback_data":"sales"}],[{"text":"🛍️ تصفح كمشتري","callback_data":"buyer"}]])
        else: edit(chat,mid,"🏠 الرئيسية",[[{"text":"🛍️ مشتري","callback_data":"buyer"},{"text":"🏪 تاجر","callback_data":"merchant"}]])
        answer(c["id"]); return

def main():
    keep_alive(); setup_bot(); off=0; print("Bot V6 بكل المميزات يعمل...")
    while True:
        try:
            r=api("getUpdates",{"timeout":30,"offset":off})
            for u in r.get("result",[]):
                off=u["update_id"]+1
                if "message" in u: handle_msg(u["message"])
                elif "callback_query" in u: handle_cb(u["callback_query"])
        except Exception as e: print(e); time.sleep(2)

if __name__=="__main__": main()
