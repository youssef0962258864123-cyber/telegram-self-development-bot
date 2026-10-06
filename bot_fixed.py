from keep_alive import keep_alive
import os, json, time, sqlite3
from datetime import date
from urllib.request import Request, urlopen
from urllib.parse import urlencode

TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise SystemExit("BOT_TOKEN غير موجود")

API = f"https://api.telegram.org/bot{TOKEN}"
DB = "tawer_nfs.db"

FACE_GOALS = [
"إزالة حب الشباب وآثاره","التخلص من الهالات السوداء","إزالة الرؤوس السوداء والبيضاء",
"التخلص من مسامات الوجه الواسعة","إزالة الدهون واللمعان من الوجه","تحديد الفك وإبرازه",
"تنحيف الوجه المنفخ","رفع الخدود المترهلة","تكثيف الحواجب وترتيبها",
"حل مشكلة شعر الوجه الخفيف","تصغير الأنف طبيعياً بدون عملية","توريد الشفايف وإزالة السواد",
"تبييض الأسنان للابتسامة","التخلص من رائحة الفم","منع تساقط الشعر تكثيف الشعر","التخلص من القشرة"
]
HABITS = [
"السهر وقلة النوم","عدم شرب كمية كافية من الماء","الإكثار من السكر والحلويات",
"الإكثار من الملح والأكل المالح","لمس الوجه باليد بشكل متكرر","النوم على وسادة غير نظيفة",
"غسل الوجه بصابون الجسم","إهمال واقي الشمس","التدخين","شرب المشروبات الغازية",
"تناول الوجبات السريعة يوميا","عدم ممارسة الرياضة",
"الجلوس والرأس منحني على الهاتف طوال الوقت","مقارنة نفسك بالآخرين على مواقع التواصل",
"عدم الاهتمام بالنظافة الشخصية","التوتر والقلق المستمر"
]
BODY=["بناء العضلات","إبراز عضلات البطن","تحديد الفك وإبرازه","تحسين اللياقة"]

db=sqlite3.connect(DB)
db.executescript("""
CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY,gender TEXT,xp INTEGER DEFAULT 0,level INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS selections(user_id INTEGER,kind TEXT,item TEXT,PRIMARY KEY(user_id,kind,item));
CREATE TABLE IF NOT EXISTS done(user_id INTEGER,day TEXT,task TEXT,PRIMARY KEY(user_id,day,task));
""")
db.commit()

def api(method, data=None, timeout=20):
    data = data or {}
    req = Request(
        API + "/" + method,
        data=urlencode(data).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())

def ensure(uid):
    db.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)",(uid,)); db.commit()

def get(uid):
    ensure(uid); return db.execute("SELECT * FROM users WHERE user_id=?",(uid,)).fetchone()

def chosen(uid,kind):
    return [x[0] for x in db.execute("SELECT item FROM selections WHERE user_id=? AND kind=? ORDER BY rowid",(uid,kind))]

def toggle(uid,kind,item):
    if db.execute("SELECT 1 FROM selections WHERE user_id=? AND kind=? AND item=?",(uid,kind,item)).fetchone():
        db.execute("DELETE FROM selections WHERE user_id=? AND kind=? AND item=?",(uid,kind,item))
    else: db.execute("INSERT INTO selections VALUES(?,?,?)",(uid,kind,item))
    db.commit()

def xp(uid,n):
    r=get(uid); new=max(0,r[2]+n); db.execute("UPDATE users SET xp=?,level=? WHERE user_id=?",(new,1+new//100,uid)); db.commit()

def send(chat,text,kb=None):
    d={"chat_id":chat,"text":text}
    if kb: d["reply_markup"]=json.dumps({"inline_keyboard":kb},ensure_ascii=False)
    return api("sendMessage",d)

def edit(chat,msg,text,kb=None):
    d={"chat_id":chat,"message_id":msg,"text":text}
    if kb: d["reply_markup"]=json.dumps({"inline_keyboard":kb},ensure_ascii=False)
    return api("editMessageText",d)

def answer(cid,text=""):
    return api("answerCallbackQuery",{"callback_query_id":cid,"text":text})

def main_kb():
    return [[{"text":"📋 مهام اليوم","callback_data":"home:tasks"},{"text":"🎯 خططي","callback_data":"home:plans"}],
            [{"text":"🏋️ تماريني","callback_data":"home:workouts"},{"text":"📊 تقدمي","callback_data":"home:progress"}],
            [{"text":"👤 ملفي","callback_data":"home:profile"}]]

def home(uid):
    r=get(uid); return f"🏠 طوّر نفسك\n\nالمستوى: {r[3]}\nXP: {r[2]}\n\nاختر قسمًا:"

def picker(uid,kind,items,prefix):
    s=chosen(uid,kind); rows=[]
    for i,x in enumerate(items):
        rows.append([{"text":("✅ " if x in s else "⬜ ")+x,"callback_data":f"{prefix}:{i}"}])
    rows.append([{"text":"💾 حفظ","callback_data":f"save:{kind}"}])
    rows.append([{"text":"↩️ الرئيسية","callback_data":"home:main"}])
    return rows

def tasks(uid):
    a=[]
    if chosen(uid,"face"): a.append("اتبعت نصائح تحسين الوجه")
    for h in chosen(uid,"habit"): a.append("تجنبت: "+h)
    if chosen(uid,"body"): a.append("أنجزت تمرين اليوم")
    return a or ["شربت كمية كافية من الماء"]

def isdone(uid,t):
    return db.execute("SELECT 1 FROM done WHERE user_id=? AND day=? AND task=?",(uid,date.today().isoformat(),t)).fetchone() is not None

def task_kb(uid):
    rows=[]
    for i,t in enumerate(tasks(uid)): rows.append([{"text":("✅ " if isdone(uid,t) else "⬜ ")+t,"callback_data":f"task:{i}"}])
    rows.append([{"text":"🏠 الرئيسية","callback_data":"home:main"}]); return rows

def handle_message(m):
    uid=m["from"]["id"]; chat=m["chat"]["id"]; text=m.get("text","")
    ensure(uid)
    if text.startswith("/start"):
        r=get(uid)
        if not r[1]:
            send(chat,"مرحبًا بك في «طوّر نفسك» 🌟\n\nسنحوّل أهدافك إلى خطط ومهام يومية.\n\nاختر النوع:",
                 [[{"text":"ولد","callback_data":"gender:male"},{"text":"بنت","callback_data":"gender:female"}]])
        else: send(chat,home(uid),main_kb())

def handle_callback(c):
    uid=c["from"]["id"]; chat=c["message"]["chat"]["id"]; mid=c["message"]["message_id"]; data=c["data"]
    ensure(uid)
    if data.startswith("gender:"):
        db.execute("UPDATE users SET gender=? WHERE user_id=?",(data.split(":")[1],uid));db.commit()
        edit(chat,mid,home(uid),main_kb()); answer(c["id"]); return
    if data=="home:main": edit(chat,mid,home(uid),main_kb());answer(c["id"]);return
    if data=="home:plans":
        edit(chat,mid,"🎯 خططي\n\nاختر الخطة:",[
            [{"text":f"✨ تحسين شكل الوجه ({len(chosen(uid,'face'))})","callback_data":"plans:face"}],
            [{"text":f"🚫 التخلص من العادات السيئة ({len(chosen(uid,'habit'))})","callback_data":"plans:habit"}],
            [{"text":f"🏋️ بناء جسم مثالي ({len(chosen(uid,'body'))})","callback_data":"plans:body"}],
            [{"text":"🏠 الرئيسية","callback_data":"home:main"}]])
        answer(c["id"]);return
    if data=="plans:face":
        edit(chat,mid,"✨ تحسين شكل الوجه\n\nاختر كل ما تريد العمل عليه:",picker(uid,"face",FACE_GOALS,"face"));answer(c["id"]);return
    if data.startswith("face:"):
        toggle(uid,"face",FACE_GOALS[int(data.split(":")[1])]);edit(chat,mid,"✨ تحسين شكل الوجه\n\nاختر كل ما تريد العمل عليه:",picker(uid,"face",FACE_GOALS,"face"));answer(c["id"],"تم");return
    if data=="save:face":
        if not chosen(uid,"face"): answer(c["id"],"اختر طلبًا واحدًا على الأقل");return
        edit(chat,mid,"تم حفظ خطة تحسين شكل الوجه ✅\nيمكنك إضافة خطة أخرى من «خططي».",main_kb());answer(c["id"]);return
    if data=="plans:habit":
        edit(chat,mid,"🚫 التخلص من العادات السيئة\n\nاختر العادات التي تريد التخلص منها:",picker(uid,"habit",HABITS,"habit"));answer(c["id"]);return
    if data.startswith("habit:"):
        toggle(uid,"habit",HABITS[int(data.split(":")[1])]);edit(chat,mid,"🚫 التخلص من العادات السيئة\n\nاختر العادات التي تريد التخلص منها:",picker(uid,"habit",HABITS,"habit"));answer(c["id"],"تم");return
    if data=="save:habit":
        edit(chat,mid,"تم حفظ العادات ✅\nستظهر كمهام يومية.",main_kb());answer(c["id"]);return
    if data=="plans:body":
        edit(chat,mid,"🏋️ بناء جسم مثالي\n\nاختر أهدافك:",picker(uid,"body",BODY,"body"));answer(c["id"]);return
    if data.startswith("body:"):
        toggle(uid,"body",BODY[int(data.split(":")[1])]);edit(chat,mid,"🏋️ بناء جسم مثالي\n\nاختر أهدافك:",picker(uid,"body",BODY,"body"));answer(c["id"]);return
    if data=="save:body":
        edit(chat,mid,"تم حفظ أهداف الجسم ✅\nيمكنك الآن فتح «تماريني».",main_kb());answer(c["id"]);return
    if data=="home:tasks":
        edit(chat,mid,"📋 مهام اليوم\n\nكل مهمة مكتملة = +10 XP.",task_kb(uid));answer(c["id"]);return
    if data.startswith("task:"):
        t=tasks(uid)[int(data.split(":")[1])]; day=date.today().isoformat()
        if isdone(uid,t):
            db.execute("DELETE FROM done WHERE user_id=? AND day=? AND task=?",(uid,day,t));xp(uid,-10)
        else:
            db.execute("INSERT INTO done VALUES(?,?,?)",(uid,day,t));xp(uid,10)
        db.commit();edit(chat,mid,"📋 مهام اليوم\n\nكل مهمة مكتملة = +10 XP.",task_kb(uid));answer(c["id"]);return
    if data=="home:progress":
        r=get(uid); n=db.execute("SELECT COUNT(*) FROM done WHERE user_id=?",(uid,)).fetchone()[0]
        edit(chat,mid,f"📊 تقدمي\n\nالمستوى: {r[3]}\nXP: {r[2]}\nالمهام المكتملة: {n}",main_kb());answer(c["id"]);return
    if data=="home:profile":
        r=get(uid);edit(chat,mid,f"👤 ملفي\n\nالمستوى: {r[3]}\nXP: {r[2]}\nطلبات الوجه: {len(chosen(uid,'face'))}\nالعادات: {len(chosen(uid,'habit'))}\nأهداف الجسم: {len(chosen(uid,'body'))}",main_kb());answer(c["id"]);return
    if data=="home:workouts":
        edit(chat,mid,"🏋️ تماريني\n\nنظام 30 يومًا سيبدأ من الأسهل ثم يتدرج للأصعب.\n\nاليوم 1:\n• Squat × 8\n• Push-up على سطح مرتفع × 6\n• Plank 15 ثانية\n\nسنضيف مكتبة التمارين الكاملة في المرحلة التالية.",main_kb());answer(c["id"]);return
def main():
    keep_alive()
    offset = 0
    print("البوت يعمل...")
    while True:
        try:
            r = api("getUpdates", {"timeout": 30, "offset": offset})
            for u in r.get("result", []):
                offset = u["update_id"] + 1
                if "message" in u:
                    handle_message(u["me
                elif "callback_query" in u:
                    handle_callback(u["c
        except Exception as e:
            print("خطأ اتصال مؤقت:", e)
            time.sleep(2)
if __name__=="__main__": main()
