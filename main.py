import os
import re
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


def detect_voice_tag(text: str) -> tuple:
    """រក (men) ឬ (girl) នៅដើមឃ្លា ហើយវាចេញ"""
    text = text.strip()
    if text.startswith("(men)"):
        return VOICE_PISETH, text[5:].strip()
    elif text.startswith("(girl)"):
        return VOICE_SREYMOM, text[6:].strip()
    return None, text


def calculate_chunk_speed(text: str, duration_ms: int) -> str:
    """គណនាល្បឿនតាម chunk (អក្សរ + ពេលវេលា)"""
    if duration_ms <= 0:
        return "+0%"
    text_length = len(text.strip())
    duration_sec = duration_ms / 1000.0
    chars_per_sec = text_length / duration_sec
    if chars_per_sec > 30:
        return "+80%"
    elif chars_per_sec > 22:
        return "+60%"
    elif chars_per_sec > 17:
        return "+40%"
    elif chars_per_sec > 12:
        return "+20%"
    elif chars_per_sec > 8:
        return "+0%"
    elif chars_per_sec > 5:
        return "-15%"
    else:
        return "-30%"


async def convert_text_to_audio(text: str, voice: str, rate: str, pitch: str, output_path: str):
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
    await communicate.save(output_path)


async def merge_audio_files(audio_files: list, output_path: str):
    """បញ្ចូល MP3 ច្រើនឯកសារជាឯកសារតែមួយ"""
    from pydub import AudioSegment
    combined = AudioSegment.empty()
    for f in audio_files:
        combined += AudioSegment.from_mp3(f)
    combined.export(output_path, format="mp3")


# ==================== BOT HANDLERS ====================

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
        "-30%": "Slow 0.7x",
        "-15%": "Slow 0.85x",
        "+0%": "Normal 1.0x",
        "+20%": "Fast 1.2x",
        "+40%": "Fast 1.4x",
        "+60%": "Fast 1.6x",
        "+80%": "Fast 1.8x",
    }.get(config["speed"], config["speed"])
    keyboard = [
        [
            InlineKeyboardButton("🎙️ Piseth (ប្រុស)", callback_data="set_voice_piseth"),
            InlineKeyboardButton("🎙️ Sreymom (ស្រី)", callback_data="set_voice_sreymom"),
        ],
        [
            InlineKeyboardButton("⚡ Speed: Auto", callback_data="set_speed_auto"),
            InlineKeyboardButton("⚡ 0.7x", callback_data="set_speed_-30%"),
        ],
        [
            InlineKeyboardButton("⚡ 0.85x", callback_data="set_speed_-15%"),
            InlineKeyboardButton("⚡ 1.0x (ធម្មតា)", callback_data="set_speed_+0%"),
        ],
        [
            InlineKeyboardButton("⚡ 1.2x", callback_data="set_speed_+20%"),
            InlineKeyboardButton("⚡ 1.4x", callback_data="set_speed_+40%"),
        ],
        [
            InlineKeyboardButton("⚡ 1.6x", callback_data="set_speed_+60%"),
            InlineKeyboardButton("⚡ 1.8x (លឿន)", callback_data="set_speed_+80%"),
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
        f"_ចំណាំ: សម្រាប់ SRT ល្បឿននឹងគណនាស្វ័យប្រវត្តិតាម chunk ជានិច្ច_"
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
        "-30%": "Slow 0.7x",
        "-15%": "Slow 0.85x",
        "+0%": "Normal 1.0x",
        "+20%": "Fast 1.2x",
        "+40%": "Fast 1.4x",
        "+60%": "Fast 1.6x",
        "+80%": "Fast 1.8x",
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
    
    # រក voice tag នៅដើមឃ្លា
    voice_override, clean_text = detect_voice_tag(text)
    voice = voice_override if voice_override else config["voice"]
    
    # គណនាល្បឿនតាមប្រវែងអក្សរ (text ធម្មតា)
    length = len(clean_text.strip())
    if config["speed"] == "auto":
        if length < 20:
            calculated_rate = "-10%"
        elif length < 50:
            calculated_rate = "+0%"
        elif length < 100:
            calculated_rate = "+20%"
        elif length < 200:
            calculated_rate = "+40%"
        else:
            calculated_rate = "+60%"
    else:
        calculated_rate = config["speed"]

    status_msg = await update.message.reply_text("⏳ កំពុងបំប្លែងអត្ថបទទៅជាសំឡេង...")
    output_file = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_file:
            output_file = tmp_file.name
        await convert_text_to_audio(
            text=clean_text,
            voice=voice,
            rate=calculated_rate,
            pitch=config["pitch"],
            output_path=output_file
        )
        speed_label = {
            "auto": "Auto", "-30%": "0.7x", "-15%": "0.85x", "+0%": "1.0x",
            "+20%": "1.2x", "+40%": "1.4x", "+60%": "1.6x", "+80%": "1.8x",
        }.get(config["speed"], config["speed"])
        caption = (
            f"🔊 **សំឡេងខ្មែរ (Edge-TTS)**\n"
            f"📏 អក្សរ: {len(clean_text)} តួ\n"
            f"🎙️ សំឡេង: {'Piseth' if voice == VOICE_PISETH else 'Sreymom'}\n"
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
    chunk_files = []

    try:
        file = await context.bot.get_file(doc.file_id)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".srt") as tmp_srt:
            srt_path = tmp_srt.name
        await file.download_to_drive(srt_path)

        subs = pysrt.open(srt_path, encoding="utf-8")
        if not subs:
            await status_msg.edit_text("❌ ឯកសារ SRT នេះគ្មានអត្ថបទឡើយ!")
            return

        # បែងចែក chunk និមួយៗ
        chunks = []
        for sub in subs:
            text = sub.text_without_tags.replace("\n", " ").strip()
            if not text:
                continue
            
            # រក voice tag
            voice_override, clean_text = detect_voice_tag(text)
            voice = voice_override if voice_override else config["voice"]
            
            # គណនា duration និង speed
            duration_ms = sub.end.ordinal - sub.start.ordinal
            speed = calculate_chunk_speed(clean_text, duration_ms)
            
            chunks.append({
                "text": clean_text,
                "voice": voice,
                "speed": speed,
                "duration_ms": duration_ms,
            })

        if not chunks:
            await status_msg.edit_text("❌ ឯកសារ SRT នេះគ្មានអត្ថបទឡើយ!")
            return

        await status_msg.edit_text(f"⏳ កំពុងបង្កើតសំឡេង {len(chunks)} chunk...")

        # បង្កើតសំឡេងដាច់ដោយឡែកសម្រាប់ chunk នីមួយៗ
        for i, chunk in enumerate(chunks):
            with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{i}.mp3") as tmp:
                chunk_path = tmp.name
            await convert_text_to_audio(
                text=chunk["text"],
                voice=chunk["voice"],
                rate=chunk["speed"],
                pitch=config["pitch"],
                output_path=chunk_path
            )
            chunk_files.append(chunk_path)

        # បញ្ចូល MP3 ទាំងអស់ជាឯកសារតែមួយ
        mp3_path = None
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_mp3:
            mp3_path = tmp_mp3.name
        
        await merge_audio_files(chunk_files, mp3_path)

        # បង្កើត caption បង្ហាញព័ត៌មាន chunk
        chunk_info = []
        for i, chunk in enumerate(chunks[:5]):  # បង្ហាញតែ 5 chunk ដំបូង
            v_name = "ប្រុស" if chunk["voice"] == VOICE_PISETH else "ស្រី"
            chunk_info.append(f"#{i+1}: {chunk['speed']} ({v_name})")
        
        chunk_summary = " | ".join(chunk_info)
        if len(chunks) > 5:
            chunk_summary += f" ... (+{len(chunks)-5} ទៀត)"

        total_duration_sec = sum(c["duration_ms"] for c in chunks) / 1000.0
        minutes = int(total_duration_sec // 60)
        seconds = int(total_duration_sec % 60)

        caption = (
            f"🎬 **បំប្លែងពី SRT រួចរាល់!**\n"
            f"📄 ឯកសារ: `{doc.file_name}`\n"
            f"🔢 Chunk: {len(chunks)}\n"
            f"⏱️ រយៈពេល SRT: {minutes}m {seconds}s\n"
            f"⚡ Speed per chunk: {chunk_summary}\n"
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
        for f in chunk_files:
            if os.path.exists(f):
                os.remove(f)
        if 'mp3_path' in dir() and mp3_path and os.path.exists(mp3_path):
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
