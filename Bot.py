import os
import json
import logging
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# --- Logging ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Load token dari config.json ---
with open("config.json") as f:
    TOKEN = json.load(f)["BOT_TOKEN"]

# --- Session user ---
user_links = {}          # simpan link terakhir per user
progress_messages = {}   # simpan pesan progress per user


# --- Hook progress download ---
async def progress_hook(d, update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Dijalankan otomatis oleh yt-dlp tiap kali progress update"""
    if d["status"] == "downloading":
        percent = d.get("_percent_str", "").strip()
        speed = d.get("_speed_str", "").strip()
        eta = d.get("_eta_str", "").strip()
        msg = f"⏳ Sedang mendownload...\n\n📊 Progress: {percent}\n⚡ Speed: {speed}\n⏱ ETA: {eta}"

        if user_id in progress_messages:
            try:
                await progress_messages[user_id].edit_text(msg)
            except Exception:
                pass

    elif d["status"] == "finished":
        if user_id in progress_messages:
            try:
                await progress_messages[user_id].edit_text("📦 Proses finishing...")
            except Exception:
                pass


# --- Fungsi download ---
def download_media(url: str, mode: str, update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> str:
    os.makedirs("downloads", exist_ok=True)

    # Opsi sesuai mode
    if mode == "mp4":
        ydl_opts = {
            "outtmpl": "downloads/%(title).100s.%(ext)s",
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": "mp4",
            "progress_hooks": [lambda d: context.application.create_task(progress_hook(d, update, context, user_id))],
        }
    elif mode == "mp3":
        ydl_opts = {
            "outtmpl": "downloads/%(title).100s.%(ext)s",
            "format": "bestaudio/best",
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}
            ],
            "progress_hooks": [lambda d: context.application.create_task(progress_hook(d, update, context, user_id))],
        }
    elif mode == "jpg":
        ydl_opts = {
            "skip_download": True,
            "writethumbnail": True,
            "outtmpl": "downloads/%(title).100s.%(ext)s",
        }
    else:
        raise ValueError("Mode tidak valid")

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        file_path = ydl.prepare_filename(info)

        # Normalisasi nama file
        if mode == "mp3":
            file_path = os.path.splitext(file_path)[0] + ".mp3"
        if mode == "mp4":
            file_path = os.path.splitext(file_path)[0] + ".mp4"
        if mode == "jpg":
            for ext in [".jpg", ".webp", ".png"]:
                candidate = os.path.splitext(file_path)[0] + ext
                if os.path.exists(candidate):
                    return candidate

        return file_path


# --- /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🎬 Mulai Download", callback_data="menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 Halo! Selamat datang di *Downloader Bot*.\n\n"
        "Saya bisa download dari *YouTube, TikTok, Instagram, Facebook*.\n"
        "Kirim link, lalu pilih format (🎥 MP4 / 🎵 MP3 / 🖼 JPG).",
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )


# --- Menu utama ---
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text("📥 Kirim link video untuk saya proses.")


# --- Handler link ---
async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    user_id = update.message.from_user.id
    user_links[user_id] = url

    keyboard = [
        [
            InlineKeyboardButton("🎥 MP4", callback_data="mp4"),
            InlineKeyboardButton("🎵 MP3", callback_data="mp3"),
        ],
        [
            InlineKeyboardButton("🖼 JPG", callback_data="jpg"),
            InlineKeyboardButton("🔙 Kembali", callback_data="menu"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Pilih format download:", reply_markup=reply_markup)


# --- Handler pilihan format ---
async def download_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if user_id not in user_links:
        await query.edit_message_text("⚠️ Silakan kirim link dulu.")
        return

    url = user_links[user_id]
    mode = query.data

    if mode == "menu":
        await menu(update, context)
        return

    try:
        # kirim pesan awal untuk progress
        progress_messages[user_id] = await query.edit_message_text("⏳ Sedang mendownload...")

        # proses download
        file_path = download_media(url, mode, update, context, user_id)

        # kirim hasil
        if mode == "mp4":
            await query.message.reply_video(video=open(file_path, "rb"))
        elif mode == "mp3":
            await query.message.reply_audio(audio=open(file_path, "rb"))
        elif mode == "jpg":
            await query.message.reply_photo(photo=open(file_path, "rb"))

        # hapus file setelah terkirim
        if os.path.exists(file_path):
            os.remove(file_path)

        await progress_messages[user_id].edit_text("✅ Download selesai! Kirim link lain untuk download lagi.")

    except Exception as e:
        logger.error(f"Error: {e}")
        await query.edit_message_text(f"❌ Error: {e}")


# --- Main ---
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(menu, pattern="^menu$"))
    app.add_handler(CallbackQueryHandler(download_choice, pattern="^(mp4|mp3|jpg|menu)$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))

    app.run_polling()


if __name__ == "__main__":
    main()
