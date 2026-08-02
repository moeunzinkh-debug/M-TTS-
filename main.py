import os
import re
import asyncio
import tempfile
import pysrt
from aiohttp import web
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

# ==================== CONFIGURATION ====================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN_HERE")
PORT = int(os.environ.get("PORT", 8080))

VOICE_PISETH = "km-KH-PisethNeural"
VOICE_SREYMOM = "km-KH-SreymomNeural"

DEFAULT_SETTINGS = {
    "voice": VOICE_PISETH,
    "pitch": "+0Hz",
    "speed_mode": "auto",  # 'auto' ឬ percentage ជាក់លាក់ដូចជា '+0%', '+45%'
}

user_settings = {}


def get_user_config(user_id: int):
    if user_id not in user_settings:
        user_settings[user_id] = DEFAULT_SETTINGS.copy()
    return user_settings[user_id]


def calculate_speed(text: str, config: dict) -> str:
    """គណនាល្បឿនស្វ័យប្រវត្តិតាមប្រវែងអក្សរ (Auto Speed Detection)"""
    if config["speed_mode"] != "auto":
        return config["speed_mode"]

    length = len(text.strip())
    # 1 - 30 characters -> Normal speed (+0%)
    if 1 <= length < 30:
        return "+0%"
    # 30 - 80 characters -> Speed (+45%)
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

        caption = f"🔊 **សំឡេងខ្មែរ (Edge-TTS)**\n📏 អក្សរ: {len(text)} តួ\n⚡ Speed: {calculated_rate}\n🎶 Pitch: {config['pitch']}"
        
        with open(output_file, "rb") as audio:
            await update.message.reply_audio(audio=audio, caption=caption, parse_mode="Markdown")

        await status_msg.delete()
        if os.path.exists(output_file):
            os.remove(output_file)

    except Exception as e:
        await status_msg.edit_text(f"❌ មានបញ្ហាក្នុងការបំប្លែងសំឡេង៖ {str(e)}")


async def handle_document_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ដំណើរការការ Upload ឯកសារ .srt ស្គាល់ប្រភេទ Subtitle Timeline"""
    doc = update.message.document
    if not doc.file_name.lower().endswith(".srt"):
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

        # អាន Subtitle ពី SRT File
        subs = pysrt.open(srt_path, encoding="utf-8")
        if not subs:
            await status_msg.edit_text("❌ ឯកសារ SRT នេះគ្មានអត្ថបទឡើយ!")
            return

        # អានអត្ថបទទាំងអស់ដោយរក្សាចន្លោះ Subtitle តាម Timeline
        full_text_list = []
        for sub in subs:
            text = sub.text_without_tags.replace("\n", " ").strip()
            if text:
                full_text_list.append(text)

        full_text = " ".join(full_text_list)

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

        caption = f"🎬 **បំប្លែងពី SRT រួចរាល់!**\n📄 ឯកសារ: `{doc.file_name}`\n⚡ Speed: {calculated_rate}\n🎶 Pitch: {config['pitch']}"

        with open(mp3_path, "rb") as audio:
            await update.message.reply_audio(audio=audio, caption=caption, parse_mode="Markdown")

        await status_msg.delete()

        if os.path.exists(srt_path):
            os.remove(srt_path)
        if os.path.exists(mp3_path):
            os.remove(mp3_path)

    except Exception as e:
        await status_msg.edit_text(f"❌ មានបញ្ហាក្នុងការដំណើរការឯកសារ SRT៖ {str(e)}")


# ==================== DUMMY WEB SERVER FOR PORT BINDING ====================

async def handle_health_check(request):
    """Endpoint សម្រាប់ឆ្លើយតប Render មើល Port status"""
    return web.Response(text="Bot is running live!")


async def start_dummy_web_server():
    """បើក Web Server តូចមួយដើម្បី Bind Port សម្រាប់ Render"""
    app = web.Application()
    app.router.add_get("/", handle_health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"🌐 Fake Web Server listening on port {PORT}")


# ==================== MAIN EXECUTION ====================

async def main_async():
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        print("❌ សូមដាក់ TELEGRAM BOT TOKEN នៅក្នុង Environment Variable (BOT_TOKEN)!")
        return

    # ១. ចាប់ផ្តើម Web Server ឱ្យ Render ស្គាល់ Port
    await start_dummy_web_server()

    # ២. បង្កើត និងរត់ Telegram Bot
    app = Application.builder().token(BOT_TOKEN).build()

    # Commands Handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CallbackQueryHandler(button_callback))

    # Messages Handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document_message))

    print("🤖 Telegram Bot កំពុងដំណើរការ...")
    async with app:
        await app.start()
        await app.updater.start_polling()
        # រក្សា Async Loop ឱ្យដំណើការរហូត
        await asyncio.Event().wait()


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
