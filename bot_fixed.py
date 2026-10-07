import os
import asyncio
import shutil
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
# الإعدادات
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("لم يتم العثور على BOT_TOKEN في متغيرات البيئة.")

BASE_DIR = Path("work")
BASE_DIR.mkdir(exist_ok=True)


# =========================================================
# أوامر البوت
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 أهلاً بك!\n\n"
        "🎬 أرسل لي فيديو، وسأحاول إزالة الموسيقى منه "
        "مع إبقاء الكلام/الصوت.\n\n"
        "⏳ قد تستغرق العملية بعض الوقت حسب حجم الفيديو."
    )


# =========================================================
# تشغيل أمر النظام
# =========================================================

async def run_command(command):
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        error = stderr.decode(errors="ignore")
        raise RuntimeError(error)

    return stdout.decode(errors="ignore")


# =========================================================
# معالجة الفيديو
# =========================================================

async def process_video(input_video: Path, output_video: Path):

    video_dir = input_video.parent

    audio_file = video_dir / "audio.wav"
    separated_dir = video_dir / "separated"

    # -----------------------------------------------------
    # 1. استخراج الصوت من الفيديو
    # -----------------------------------------------------

    await run_command([
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
    ])

    # -----------------------------------------------------
    # 2. فصل الصوت باستخدام Demucs
    #
    # htdemucs يعطي:
    # vocals.wav
    # drums.wav
    # bass.wav
    # other.wav
    #
    # نستخدم vocals كالصوت الأساسي ونحذف الموسيقى.
    # -----------------------------------------------------

    await run_command([
        "python",
        "-m",
        "demucs",
        "--two-stems=vocals",
        "-n",
        "htdemucs",
        "-o",
        str(separated_dir),
        str(audio_file),
    ])

    # مكان vocals الناتج من Demucs
    vocals_file = (
        separated_dir
        / "htdemucs"
        / audio_file.stem
        / "vocals.wav"
    )

    if not vocals_file.exists():
        raise RuntimeError(
            "لم يتم العثور على ملف الصوت بعد عملية الفصل."
        )

    # -----------------------------------------------------
    # 3. تركيب الصوت الجديد مع الفيديو
    # -----------------------------------------------------

    await run_command([
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
    ])


# =========================================================
# استقبال الفيديو
# =========================================================

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):

    message = update.message

    if not message or not message.video:
        return

    user_id = message.from_user.id

    user_dir = BASE_DIR / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)

    input_video = user_dir / "input.mp4"
    output_video = user_dir / "output.mp4"

    # تنظيف الملفات القديمة
    for item in user_dir.iterdir():
        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        except Exception:
            pass

    user_dir.mkdir(parents=True, exist_ok=True)

    status = await
