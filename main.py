import os
import re
import asyncio
import tempfile
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import pysrt
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
import edge_tts

# ==================== DUMMY WEB SERVER FOR RENDER PORT BINDING ====================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK - Khmer TTS Bot is running!")

    def log_message(self, format, *args):
        # បិទ Log របស់ HTTP Server ដើម្បីកុំឱ្យរំខាន Terminal Log
        return

def start_health_check_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    print(f"🌐 Health Check Server running on port {port}")
    server.serve_forever()

# ==================== CONFIGURATION ====================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN_HERE")

VOICE_PISETH = "km-KH-PisethNeural"
VOICE_SREYMOM = "km-KH-SreymomNeural"

DEFAULT_SETTINGS = {
    "voice": VOICE_PISETH,
    "pitch": "+0Hz",
    "speed_mode": "auto",
}

user_settings = {}


def get_user_config(user_id: int):
    if user_id not in user_settings:
        user_settings[user_id] = DEFAULT_SETTINGS.copy()
    return user_settings[user_id]


def calculate_speed(text: str, config: dict) -> str:
    """គណនាល្បឿនស្វ័យប្រវត្តិតាមប្រវែងអក្សរ"""
    if config["speed_mode"] != "auto":
        return config["speed_mode"]

    length = len(text.strip())
    if 1 <= length < 30:
        return "+0%"
    elif 30 <= length <= 80:
        return "+45%"
    else:
        return "+0%"


async def convert_text_to_audio(text: str, voice: str, rate: str, pitch: str, output_path: str):
    """បំប្លែង Text ទៅជា Audio MP3 ដោយប្រើ Edge-TTS"""
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
    await communicate.save(output_path)


# ==================== BOT HANDLERS ====================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """បញ្ជា /start"""
    welcome_text = (
        "សូមស្វាគមន៍មកកាន់ **Khmer Text-to-Speech Bot**! 🇰🇭\n\n"
        "លោកអ្នកអាច៖\n"
        "1. ផ្ញើសារអត្ថបទជាភាសាខ្មែរមកទីនេះភ្លាមៗ\n"
        "2. ផ្ញើឯកសារអត្ថបទចម្រៀង/ចំណងជើងរឿងប្រភេទ **.srt**\n\n"
        "⚙️ ចុច /settings ដើម្បីកំណត់សំឡេង, Pitch និង Speed"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """បញ្ជា /settings សម្រាប់ជ្រើសរើសសំឡេង និងការកំណត់"""
    user_id = update.effective_user.id
    config = get_user_config(user_id)

    voice_name = "Piseth (ប្រុស)" if config["voice"] == VOICE_PISETH else "Sreymom (ស្រី)"
    
    keyboard = [
        [
            InlineKeyboardButton("🎙️ Piseth (ប្រុស)", callback_data="set_voice_piseth"),
            InlineKeyboardButton("🎙️ Sreymom (ស្រី)", callback_data="set_voice_sreymom"),
        ],
        [
            InlineKeyboardButton("⚡ Speed: Auto (30-80 char = 1.4x)", callback_data="set_speed_auto"),
            InlineKeyboardButton("⚡ Speed: Normal (1.0x)", callback_data="set_speed_normal"),
        ],
        [
            InlineKeyboardButton("🎶 Pitch: +0Hz", callback_data="set_pitch_0"),
            InlineKeyboardButton("🎶 Pitch: +5Hz", callback_data="set_pitch_5"),
            InlineKeyboardButton("🎶 Pitch: -5Hz", callback_data="set_pitch_minus5"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    status_text = (
        f"⚙️ **ការកំណត់បច្ចុប្បន្ន:**\n"
        f"- សំឡេង: **{voice_name}**\n"
        f"- Speed Mode: **{config['speed_mode']}**\n"
        f"- Pitch: **{config['pitch']}**"
    )
    await update.message.reply_text(status_text, reply_markup=reply_markup, parse_mode="Markdown")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ទទួលការចុចប៊ូតុង Inline Keyboards"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    config = get_user_config(user_id)

    data = query.data
    if data == "set_voice_piseth":
        config["voice"] = VOICE_PISETH
    elif data == "set_voice_sreymom":
        config["voice"] = VOICE_SREYMOM
    elif data == "set_speed_auto":
        config["speed_mode"] = "auto"
    elif data == "set_speed_normal":
        config["speed_mode"] = "+0%"
    elif data == "set_pitch_0":
        config["pitch"] = "+0Hz"
    elif data == "set_pitch_5":
        config["pitch"] = "+5Hz"
    elif data == "set_pitch_minus5":
        config["pitch"] = "-5Hz"

    voice_name = "Piseth (ប្រុស)" if config["voice"] == VOICE_PISETH else "Sreymom (ស្រី)"
    await query.edit_message_text(
        f"✅ **បានផ្លាស់ប្តូរការកំណត់រួចរាល់!**\n\n"
        f"- សំឡេង: **{voice_name}**\n"
        f"- Speed Mode: **{config['speed_mode']}**\n"
        f"- Pitch: **{config['pitch']}**",
        parse_mode="Markdown"
    )


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ដំណើរការអត្ថបទធម្មតាដែលផ្ញើចូល"""
    text = update.message.text
    if not text or text.startswith("/"):
        return

    user_id = update.effective_user.id
    config = get_user_config(user_id)
    
    calculated_rate = calculate_speed(text, config)

    status_msg = await update.message.reply_text("⏳ កំពុងបំប្លែងអត្ថបទទៅជាសំឡេង...")

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_file:
            output_file = tmp_file.name

        await convert_text_to_audio(
            text=text,
            voice=config["voice"],
            rate=calculated_rate,
            pitch=config["pitch"],
            output_path=output_file
        )

        caption = f"🔊 **សំឡេងខ្មែរ (Edge-TTS)**\n📏 អក្សរ: {len(text)} តួ\n⚡ Speed: {calculated_rate}"
        
        with open(output_file, "rb") as audio:
            await update.message.reply_audio(audio=audio, caption=caption, parse_mode="Markdown")

        await status_msg.delete()
        if os.path.exists(output_file):
            os.remove(output_file)

    except Exception as e:
        await status_msg.edit_text(f"❌ មានបញ្ហាក្នុងការបំប្លែងសំឡេង៖ {str(e)}")


async def handle_document_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ដំណើរការការ Upload ឯកសារ .srt"""
    doc = update.message.document
    if not doc.file_name.endswith(".srt"):
        await update.message.reply_text("⚠️ សូមផ្ញើតែឯកសារប្រភេទ `.srt` ប៉ុណ្ណោះ!")
        return

    user_id = update.effective_user.id
    config = get_user_config(user_id)

    status_msg = await update.message.reply_text("⏳ កំពុងទាញយក និងអានឯកសារ .SRT...")

    try:
        file = await context.bot.get_file(doc.file_id)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".srt") as tmp_srt:
            srt_path = tmp_srt.name

        await file.download_to_drive(srt_path)

        subs = pysrt.open(srt_path, encoding="utf-8")
        full_text = " ".join([sub.text_without_tags.replace("\n", " ") for sub in subs])

        if not full_text.strip():
            await status_msg.edit_text("❌ ឯកសារ SRT នេះគ្មានអត្ថបទឡើយ!")
            return

        await status_msg.edit_text("⏳ កំពុងបង្កើតសំឡេងចេញពី SRT...")

        calculated_rate = calculate_speed(full_text, config)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_mp3:
            mp3_path = tmp_mp3.name

        await convert_text_to_audio(
            text=full_text,
            voice=config["voice"],
            rate=calculated_rate,
            pitch=config["pitch"],
            output_path=mp3_path
        )

        caption = f"🎬 **បំប្លែងពី SRT រួចរាល់!**\n📄 ឯកសារ: `{doc.file_name}`\n⚡ Speed: {calculated_rate}"

        with open(mp3_path, "rb") as audio:
            await update.message.reply_audio(audio=audio, caption=caption, parse_mode="Markdown")

        await status_msg.delete()

        if os.path.exists(srt_path):
            os.remove(srt_path)
        if os.path.exists(mp3_path):
            os.remove(mp3_path)

    except Exception as e:
        await status_msg.edit_text(f"❌ មានបញ្ហាក្នុងការដំណើរការឯកសារ SRT៖ {str(e)}")


# ==================== MAIN EXECUTION ====================

def main():
    """ចាប់ផ្តើម Bot"""
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        print("❌ សូមដាក់ TELEGRAM BOT TOKEN នៅក្នុង Environment Variable (BOT_TOKEN)!")
        return

    # បង្កើត Background Thread សម្រាប់រត់ Web Server Bind Port Render
    health_thread = threading.Thread(target=start_health_check_server, daemon=True)
    health_thread.start()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CallbackQueryHandler(button_callback))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document_message))

    print("🤖 Telegram Bot កំពុងដំណើរការ...")
    app.run_polling()


if __name__ == "__main__":
    main()
