import os
import shutil
import asyncio
import subprocess
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)


# =========================================================
# إعدادات
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN غير موجود في Environment Variables")


BASE_DIR = Path("/tmp/video_bot")
BASE_DIR.mkdir(parents=True, exist_ok=True)


# =========================================================
# تشغيل أوامر النظام
# =========================================================

async def run_command(command):
    print("RUNNING:", " ".join(map(str, command)))

    process = await asyncio.create_subprocess_exec(
        *[str(x) for x in command],
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        error = stderr.decode("utf-8", errors="ignore")

        print("COMMAND ERROR:")
        print(error)

        raise RuntimeError(error)

    return stdout.decode("utf-8", errors="ignore")


# =========================================================
# /start
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "👋 أهلاً بك في بوت إزالة الموسيقى.\n\n"
        "🎬 أرسل لي فيديو.\n\n"
        "🎵 سأحاول فصل الموسيقى عن الصوت "
        "وإرجاع الفيديو بدون الموسيقى.\n\n"
        "⏳ المعالجة قد تستغرق بعض الوقت."
    )


# =========================================================
# معالجة الفيديو
# =========================================================

async def process_video(input_video, output_video):

    work_dir = input_video.parent

    audio_file = work_dir / "audio.wav"

    demucs_output = work_dir / "separated"

    # -----------------------------------------------------
    # استخراج الصوت من الفيديو
    # -----------------------------------------------------

    await run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_video),
            "-vn",
            "-ac",
            "2",
            "-ar",
            "44100",
            str(audio_file),
        ]
    )

    # -----------------------------------------------------
    # فصل الكلام/الغناء عن الموسيقى
    # -----------------------------------------------------

    await run_command(
        [
            "python",
            "-m",
            "demucs",
            "-d",
            "cpu",
            "--two-stems=vocals",
            "-n",
            "htdemucs",
            "-o",
            str(demucs_output),
            str(audio_file),
        ]
    )

    vocals_file = (
        demucs_output
        / "htdemucs"
        / audio_file.stem
        / "vocals.wav"
    )

    if not vocals_file.exists():

        raise RuntimeError(
            "Demucs لم ينشئ ملف vocals.wav"
        )

    # -----------------------------------------------------
    # تركيب الصوت الجديد مع الفيديو
    # -----------------------------------------------------

    await run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_video),
            "-i",
            str(vocals_file),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            str(output_video),
        ]
    )

    if not output_video.exists():

        raise RuntimeError(
            "لم يتم إنشاء الفيديو النهائي"
        )


# =========================================================
# استقبال الفيديو
# =========================================================

async def handle_video(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.message

    if not message or not message.video:
        return

    user_id = message.from_user.id

    user_dir = BASE_DIR / str(user_id)

    # تنظيف ملفات المستخدم القديمة
    if user_dir.exists():

        shutil.rmtree(
            user_dir,
            ignore_errors=True
        )

    user_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    input_video = user_dir / "input.mp4"

    output_video = user_dir / "output.mp4"

    status = await message.reply_text(
        "📥 جاري تحميل الفيديو..."
    )

    try:

        # -------------------------------------------------
        # تحميل الفيديو
        # -------------------------------------------------

        telegram_file = await message.video.get_file()

        await telegram_file.download_to_drive(
            custom_path=str(input_video)
        )

        await status.edit_text(
            "🎧 تم تحميل الفيديو.\n\n"
            "🤖 جاري فصل الموسيقى عن الصوت...\n"
            "⏳ انتظر..."
        )

        # -------------------------------------------------
        # المعالجة
        # -------------------------------------------------

        await process_video(
            input_video,
            output_video
        )

        await status.edit_text(
            "✅ انتهت المعالجة.\n"
            "📤 جاري إرسال الفيديو..."
        )

        # -------------------------------------------------
        # إرسال الفيديو
        # -------------------------------------------------

        with open(output_video, "rb") as video:

            await message.reply_video(
                video=video,
                caption=(
                    "✅ تم تجهيز الفيديو.\n\n"
                    "🎵 تمت محاولة إزالة الموسيقى."
                ),
                supports_streaming=True
            )

        await status.delete()

    except Exception as error:

        print("ERROR:")
        print(error)

        await status.edit_text(
            "❌ حدث خطأ أثناء معالجة الفيديو.\n\n"
            "حاول إرسال فيديو أقصر."
        )

    finally:

        # تنظيف الملفات
        try:

            if user_dir.exists():

                shutil.rmtree(
                    user_dir,
                    ignore_errors=True
                )

        except Exception as error:

            print("CLEANUP ERROR:")
            print(error)


# =========================================================
# استقبال الفيديو كـ Document
# =========================================================

async def handle_document(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.message

    if not message or not message.document:
        return

    mime_type = message.document.mime_type or ""

    if not mime_type.startswith("video/"):

        await message.reply_text(
            "⚠️ أرسل ملف فيديو فقط."
        )

        return

    user_id = message.from_user.id

    user_dir = BASE_DIR / str(user_id)

    if user_dir.exists():

        shutil.rmtree(
            user_dir,
            ignore_errors=True
        )

    user_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    input_video = user_dir / "input.mp4"

    output_video = user_dir / "output.mp4"

    status = await message.reply_text(
        "📥 جاري تحميل الفيديو..."
    )

    try:

        telegram_file = await message.document.get_file()

        await telegram_file.download_to_drive(
            custom_path=str(input_video)
        )

        await status.edit_text(
            "🎧 جاري فصل الموسيقى عن الصوت...\n"
            "⏳ انتظر..."
        )

        await process_video(
            input_video,
            output_video
        )

        await status.edit_text(
            "📤 انتهت المعالجة، جاري إرسال الفيديو..."
        )

        with open(output_video, "rb") as video:

            await message.reply_video(
                video=video,
                caption="✅ تم تجهيز الفيديو.",
                supports_streaming=True
            )

        await status.delete()

    except Exception as error:

        print("ERROR:")
        print(error)

        await status.edit_text(
            "❌ حدث خطأ أثناء معالجة الفيديو."
        )

    finally:

        if user_dir.exists():

            shutil.rmtree(
                user_dir,
                ignore_errors=True
            )


# =========================================================
# تشغيل البوت
# =========================================================

def main():

    print("================================")
    print("🚀 Telegram Bot Starting...")
    print("================================")

    application = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    application.add_handler(
        MessageHandler(
            filters.VIDEO,
            handle_video
        )
    )

    application.add_handler(
        MessageHandler(
            filters.Document.VIDEO,
            handle_document
        )
    )

    print("✅ Bot is running.")

    application.run_polling(
        drop_pending_updates=True
    )


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":
    main()
