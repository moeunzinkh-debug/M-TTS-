import os
import asyncio
import tempfile
import logging
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

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
PORT = int(os.environ.get("PORT", 8080))
WEBHOOK_URL = os.environ.get("RENDER_EXTERNAL_URL", "")

VOICE_PISETH = "km-KH-PisethNeural"
VOICE_SREYMOM = "km-KH-SreymomNeural"

DEFAULT_SETTINGS = {
    "voice": VOICE_PISETH,
    "pitch": "+0Hz",
    "speed": "auto",
}

user_settings = {}


def get_user_config(user_id: int):
    if user_id not in user_settings:
        user_settings[user_id] = DEFAULT_SETTINGS.copy()
    return user_settings[user_id]


def calculate_speed(text: str, config: dict, is_srt: bool = False, srt_duration_ms: int = 0) -> str:
    speed_setting = config.get("speed", "auto")
    if speed_setting != "auto":
        return speed_setting
    if is_srt and srt_duration_ms > 0:
        text_length = len(text.strip())
        duration_sec = srt_duration_ms / 1000.0
        if duration_sec <= 0:
            return "+0%"
        chars_per_sec = text_length / duration_sec
        if chars_per_sec > 25:
            return "+60%"
        elif chars_per_sec > 20:
            return "+45%"
        elif chars_per_sec > 15:
            return "+30%"
        elif chars_per_sec < 8:
            return "-20%"
        else:
            return "+0%"
    length = len(text.strip())
    if length < 20:
        return "-10%"
    elif length < 50:
        return "+0%"
    elif length < 100:
        return "+20%"
    elif length < 200:
        return "+35%"
    else:
        return "+50%"


async def convert_text_to_audio(text: str, voice: str, rate: str, pitch: str, output_path: str):
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
    await communicate.save(output_path)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "សូមស្វាគមន៍មកកាន់ **Khmer Text-to-Speech Bot**! 🇰🇭\n\n"
        "លោកអ្នកអាច៖\n"
        "1. ផ្ញើសារអត្ថបទជាភាសាខ្មែរមកទីនេះភ្លាមៗ\n"
        "2. ផ្ញើឯកសារអត្ថបទចម្រៀង/ចំណងជើងរឿងប្រភេទ **.srt**\n\n"
        "⚙️ ចុច /settings ដើម្បីកំណត់សំឡេង, Pitch និង Speed"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    config = get_user_config(user_id)
    voice_name = "Piseth (ប្រុស)" if config["voice"] == VOICE_PISETH else "Sreymom (ស្រី)"
    speed_label = {
        "auto": "Auto (ស្វ័យប្រវត្តិ)",
        "-20%": "Slow 0.8x (យឺត)",
        "-10%": "Slow 0.9x (យឺតបន្តិច)",
        "+0%": "Normal 1.0x (ធម្មតា)",
        "+20%": "Fast 1.2x (លឿនបន្តិច)",
        "+35%": "Fast 1.35x (លឿន)",
        "+45%": "Fast 1.45x (លឿនខ្លាំង)",
        "+60%": "Fast 1.6x (លឿនខ្លាំងណាស់)",
    }.get(config["speed"], config["speed"])
    keyboard = [
        [
            InlineKeyboardButton("🎙️ Piseth (ប្រុស)", callback_data="set_voice_piseth"),
            InlineKeyboardButton("🎙️ Sreymom (ស្រី)", callback_data="set_voice_sreymom"),
        ],
        [
            InlineKeyboardButton("⚡ Speed: Auto", callback_data="set_speed_auto"),
            InlineKeyboardButton("⚡ 0.8x (យឺត)", callback_data="set_speed_-20%"),
        ],
        [
            InlineKeyboardButton("⚡ 0.9x", callback_data="set_speed_-10%"),
            InlineKeyboardButton("⚡ 1.0x (ធម្មតា)", callback_data="set_speed_+0%"),
        ],
        [
            InlineKeyboardButton("⚡ 1.2x", callback_data="set_speed_+20%"),
            InlineKeyboardButton("⚡ 1.35x", callback_data="set_speed_+35%"),
        ],
        [
            InlineKeyboardButton("⚡ 1.45x", callback_data="set_speed_+45%"),
            InlineKeyboardButton("⚡ 1.6x (លឿន)", callback_data="set_speed_+60%"),
        ],
        [
            InlineKeyboardButton("🎶 Pitch: -10Hz", callback_data="set_pitch_-10Hz"),
            InlineKeyboardButton("🎶 Pitch: -5Hz", callback_data="set_pitch_-5Hz"),
            InlineKeyboardButton("🎶 Pitch: +0Hz", callback_data="set_pitch_+0Hz"),
        ],
        [
            InlineKeyboardButton("🎶 Pitch: +5Hz", callback_data="set_pitch_+5Hz"),
            InlineKeyboardButton("🎶 Pitch: +10Hz", callback_data="set_pitch_+10Hz"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    status_text = (
        f"⚙️ **ការកំណត់បច្ចុប្បន្ន:**\n"
        f"- សំឡេង: **{voice_name}**\n"
        f"- Speed: **{speed_label}**\n"
        f"- Pitch: **{config['pitch']}**\n\n"
        f"_ចំណាំ: សម្រាប់ SRT ល្បឿននឹងគណនាស្វ័យប្រវត្តិតាមពេលវេលា subtitle ជានិច្ច_"
    )
    await update.message.reply_text(status_text, reply_markup=reply_markup, parse_mode="Markdown")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        config["speed"] = "auto"
    elif data.startswith("set_speed_"):
        config["speed"] = data.replace("set_speed_", "")
    elif data == "set_pitch_-10Hz":
        config["pitch"] = "-10Hz"
    elif data == "set_pitch_-5Hz":
        config["pitch"] = "-5Hz"
    elif data == "set_pitch_+0Hz":
        config["pitch"] = "+0Hz"
    elif data == "set_pitch_+5Hz":
        config["pitch"] = "+5Hz"
    elif data == "set_pitch_+10Hz":
        config["pitch"] = "+10Hz"
    voice_name = "Piseth (ប្រុស)" if config["voice"] == VOICE_PISETH else "Sreymom (ស្រី)"
    speed_label = {
        "auto": "Auto (ស្វ័យប្រវត្តិ)",
        "-20%": "Slow 0.8x",
        "-10%": "Slow 0.9x",
        "+0%": "Normal 1.0x",
        "+20%": "Fast 1.2x",
        "+35%": "Fast 1.35x",
        "+45%": "Fast 1.45x",
        "+60%": "Fast 1.6x",
    }.get(config["speed"], config["speed"])
    await query.edit_message_text(
        f"✅ **បានផ្លាស់ប្តូរការកំណត់រួចរាល់!**\n\n"
        f"- សំឡេង: **{voice_name}**\n"
        f"- Speed: **{speed_label}**\n"
        f"- Pitch: **{config['pitch']}**",
        parse_mode="Markdown"
    )


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text or text.startswith("/"):
        return
    user_id = update.effective_user.id
    config = get_user_config(user_id)
    calculated_rate = calculate_speed(text, config, is_srt=False)
    status_msg = await update.message.reply_text("⏳ កំពុងបំប្លែងអត្ថបទទៅជាសំឡេង...")
    output_file = None
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
        speed_label = {
            "auto": "Auto",
            "-20%": "0.8x", "-10%": "0.9x", "+0%": "1.0x",
            "+20%": "1.2x", "+35%": "1.35x", "+45%": "1.45x", "+60%": "1.6x",
        }.get(config["speed"], config["speed"])
        caption = (
            f"🔊 **សំឡេងខ្មែរ (Edge-TTS)**\n"
            f"📏 អក្សរ: {len(text)} តួ\n"
            f"⚡ Speed: {calculated_rate} ({speed_label})\n"
            f"🎶 Pitch: {config['pitch']}"
        )
        with open(output_file, "rb") as audio:
            await update.message.reply_audio(audio=audio, caption=caption, parse_mode="Markdown")
        await status_msg.delete()
    except Exception as e:
        logger.error(f"Error converting text: {e}")
        await status_msg.edit_text(f"❌ មានបញ្ហាក្នុងការបំប្លែងសំឡេង៖ {str(e)}")
    finally:
        if output_file and os.path.exists(output_file):
            os.remove(output_file)


async def handle_document_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc.file_name.lower().endswith(".srt"):
        await update.message.reply_text("⚠️ សូមផ្ញើតែឯកសារប្រភេទ `.srt` ប៉ុណ្ណោះ!")
        return
    user_id = update.effective_user.id
    config = get_user_config(user_id)
    status_msg = await update.message.reply_text("⏳ កំពុងទាញយក និងអានឯកសារ .SRT...")
    srt_path = None
    mp3_path = None
    try:
        file = await context.bot.get_file(doc.file_id)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".srt") as tmp_srt:
            srt_path = tmp_srt.name
        await file.download_to_drive(srt_path)
        subs = pysrt.open(srt_path, encoding="utf-8")
        if not subs:
            await status_msg.edit_text("❌ ឯកសារ SRT នេះគ្មានអត្ថបទឡើយ!")
            return
        full_text_list = []
        total_duration_ms = 0
        for i, sub in enumerate(subs):
            text = sub.text_without_tags.replace("\n", " ").strip()
            if text:
                full_text_list.append(text)
                start_time = sub.start.ordinal
                end_time = sub.end.ordinal
                duration = end_time - start_time
                total_duration_ms += duration
        full_text = " ".join(full_text_list)
        if not full_text:
            await status_msg.edit_text("❌ ឯកសារ SRT នេះគ្មានអត្ថបទឡើយ!")
            return
        await status_msg.edit_text("⏳ កំពុងបង្កើតសំឡេងចេញពី SRT...")
        calculated_rate = calculate_speed(full_text, config, is_srt=True, srt_duration_ms=total_duration_ms)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_mp3:
            mp3_path = tmp_mp3.name
        await convert_text_to_audio(
            text=full_text,
            voice=config["voice"],
            rate=calculated_rate,
            pitch=config["pitch"],
            output_path=mp3_path
        )
        total_sec = total_duration_ms / 1000.0
        minutes = int(total_sec // 60)
        seconds = int(total_sec % 60)
        caption = (
            f"🎬 **បំប្លែងពី SRT រួចរាល់!**\n"
            f"📄 ឯកសារ: `{doc.file_name}`\n"
            f"⏱️ រយៈពេល SRT: {minutes}m {seconds}s\n"
            f"⚡ Speed: {calculated_rate} (Auto-SRT)\n"
            f"🎶 Pitch: {config['pitch']}"
        )
        with open(mp3_path, "rb") as audio:
            await update.message.reply_audio(audio=audio, caption=caption, parse_mode="Markdown")
        await status_msg.delete()
    except Exception as e:
        logger.error(f"Error processing SRT: {e}")
        await status_msg.edit_text(f"❌ មានបញ្ហាក្នុងការដំណើរការឯកសារ SRT៖ {str(e)}")
    finally:
        if srt_path and os.path.exists(srt_path):
            os.remove(srt_path)
        if mp3_path and os.path.exists(mp3_path):
            os.remove(mp3_path)


def main():
    if not BOT_TOKEN:
        logger.error("❌ សូមដាក់ TELEGRAM BOT TOKEN នៅក្នុង Environment Variable (BOT_TOKEN)!")
        return
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document_message))
    if WEBHOOK_URL:
        webhook_path = f"/webhook/{BOT_TOKEN}"
        full_webhook_url = f"{WEBHOOK_URL.rstrip('/')}{webhook_path}"
        logger.info(f"✅ Webhook URL: {full_webhook_url}")
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=webhook_path,
            webhook_url=full_webhook_url,
        )
    else:
        logger.info("🚀 Bot running with Polling (local mode)")
        app.run_polling()


if __name__ == "__main__":
    main()
