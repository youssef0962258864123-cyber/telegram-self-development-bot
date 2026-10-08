import os, subprocess
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from pydub import AudioSegment

TOKEN = "8838869811:AAGhtswVRV3W47KoqzkNRLX-98cmIeTX9m8"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎤 أرسل لي أغنية وأنا برجع ليك الصوت بدون موسيقى")

async def remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ شغال بالذكاء الاصطناعي... دقيقة بس")

    file = await update.message.effective_attachment.get_file()
    in_file = f"in_{update.message.id}.mp3"
    await file.download_to_drive(in_file)

    # أهم سطر - إزالة الموسيقى
    subprocess.run(f"python -m demucs --two-stems=vocals {in_file} -o out", shell=True)

    base = os.path.splitext(in_file)[0]
    vocal = f"out/htdemucs/{base}/vocals.wav"

    if os.path.exists(vocal):
        out_mp3 = f"out_{update.message.id}.mp3"
        AudioSegment.from_wav(vocal).export(out_mp3, format="mp3")
        await update.message.reply_audio(audio=open(out_mp3, 'rb'), title="بدون موسيقى")
        os.remove(out_mp3)
    else:
        await update.message.reply_text("فشل، جرب ملف تاني")

    # تنظيف
    try:
        os.remove(in_file)
        import shutil; shutil.rmtree("out", ignore_errors=True)
    except: pass
    await msg.delete()

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.AUDIO | filters.VOICE | filters.VIDEO | filters.Document.AUDIO, remove))
app.run_polling()
