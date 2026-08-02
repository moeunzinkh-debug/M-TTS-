import os
import re
import asyncio
import tempfile
import pysrt
from pydub import AudioSegment
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

VOICE_PISETH = "km-KH-PisethNeural"
VOICE_SREYMOM = "km-KH-SreymomNeural"

DEFAULT_SETTINGS = {
    "voice": VOICE_PISETH,
    "pitch": "+0Hz",
    "speed_mode": "auto",  # 'auto', '+0%', '+20%', '+40%', '-20%'
}

user_settings = {}


def get_user_config(user_id: int):
    if user_id not in user_settings:
        user_settings[user_id] = DEFAULT_SETTINGS.copy()
    return user_settings[user_id]


def calculate_text_speed(text: str, config: dict) -> str:
    """គណនាល្បឿនស្វ័យប្រវត្តិតាមប្រវែងអក្សរសម្រាប់ Text ធម្មតា"""
    if config["speed_mode"] != "auto":
        return config["speed_mode"]

    length = len(text.strip())
    if length > 100:
        return "+30%"
    elif length > 50:
        return "+15%"
    else:
        return "+0%"


def calculate_srt_speed(text_len: int, duration_ms: float, config: dict) -> str:
    """គណនាល្បឿននិយាយតាម Timeline Subtitle នីមួយៗ (Auto SRT Detection)"""
    if config["speed_mode"] != "auto":
        return config["speed_mode"]

    if duration_ms <= 0 or text_len == 0:
        return "+0%"

    # ប្រហែល 12-15 characters ក្នុងមួយវិនាទីសម្រាប់ល្បឿនធម្មតា
    char_per_sec = text_len / (duration_ms / 1000.0)

    if char_per_sec > 18:
        return "+50%"
    elif char_per_sec > 14:
        return "+30%"
    elif char_per_sec > 10:
        return "+15%"
    elif char_per_sec < 5:
        return "-10%"
    else:
        return "+0%"


async def convert_text_to_audio(text: str, voice: str, rate: str, pitch: str, output_path: str):
    """បំប្លែង Text ទៅជា Audio MP3 ដោយប្រើ Edge-TTS"""
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
    await communicate.save(output_path)


# ==================== BOT HANDLERS ====================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "🇰🇭 **សូមស្វាគមន៍មកកាន់ Khmer Text-to-Speech & Subtitle Bot!**\n\n"
        "✨ **លក្ខណៈពិសេស៖**\n"
        "1. ផ្ញើសារអត្ថបទជាភាសាខ្មែរ ដើម្បីបំប្លែងជាសំឡេង\n"
        "2. ផ្ញើឯកសារ `.srt` Bot នឹងបំប្លែងសំឡេងត្រូវតាម **Timeline** ស្វ័យប្រវត្តិ\n\n"
        "⚙️ ចុច /settings ដើម្បីកំណត់សំឡេង Pitch និង Speed"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    config = get_user_config(user_id)

    voice_name = "Piseth (ប្រុស 👨)" if config["voice"] == VOICE_PISETH else "Sreymom (ស្រី 👩)"
    
    keyboard = [
        [
            InlineKeyboardButton("👨 Piseth", callback_data="set_voice_piseth"),
            InlineKeyboardButton("👩 Sreymom", callback_data="set_voice_sreymom"),
        ],
        [
            InlineKeyboardButton("⚡ Auto Speed", callback_data="set_speed_auto"),
            InlineKeyboardButton("⚡ 1.0x (Normal)", callback_data="set_speed_0"),
            InlineKeyboardButton("⚡ 1.3x (Fast)", callback_data="set_speed_30"),
        ],
        [
            InlineKeyboardButton("🎶 Pitch: -5Hz", callback_data="set_pitch_-5Hz"),
            InlineKeyboardButton("🎶 Pitch: Normal", callback_data="set_pitch_+0Hz"),
            InlineKeyboardButton("🎶 Pitch: +5Hz", callback_data="set_pitch_+5Hz"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    status_text = (
        f"⚙️ **ការកំណត់បច្ចុប្បន្ន (Current Settings):**\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🎙️ សំឡេង: **{voice_name}**\n"
        f"⚡ Speed Mode: **{config['speed_mode']}**\n"
        f"🎶 Pitch: **{config['pitch']}**"
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
        config["speed_mode"] = "auto"
    elif data == "set_speed_0":
        config["speed_mode"] = "+0%"
    elif data == "set_speed_30":
        config["speed_mode"] = "+30%"
    elif data.startswith("set_pitch_"):
        config["pitch"] = data.replace("set_pitch_", "")

    voice_name = "Piseth (ប្រុស 👨)" if config["voice"] == VOICE_PISETH else "Sreymom (ស្រី 👩)"
    await query.edit_message_text(
        f"✅ **បានធ្វើបច្ចុប្បន្នភាពការកំណត់!**\n\n"
        f"🎙️ សំឡេង: **{voice_name}**\n"
        f"⚡ Speed Mode: **{config['speed_mode']}**\n"
        f"🎶 Pitch: **{config['pitch']}**",
        parse_mode="Markdown"
    )


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text or text.startswith("/"):
        return

    user_id = update.effective_user.id
    config = get_user_config(user_id)
    calculated_rate = calculate_text_speed(text, config)

    status_msg = await update.message.reply_text("⏳ កំពុងបង្កើតសំឡេង...")

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

        caption = (
            f"🔊 **បំប្លែងសំឡេងរួចរាល់!**\n"
            f"📏 អក្សរ: `{len(text)}` តួ\n"
            f"⚡ Speed: `{calculated_rate}` | 🎶 Pitch: `{config['pitch']}`"
        )
        
        with open(output_file, "rb") as audio:
            await update.message.reply_audio(audio=audio, caption=caption, parse_mode="Markdown")

        await status_msg.delete()
        if os.path.exists(output_file):
            os.remove(output_file)

    except Exception as e:
        await status_msg.edit_text(f"❌ មានបញ្ហាក្នុងការបំប្លែងសំឡេង៖ {str(e)}")


async def handle_document_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc.file_name.lower().endswith(".srt"):
        await update.message.reply_text("⚠️ សូមផ្ញើតែឯកសារប្រភេទ `.srt` ប៉ុណ្ណោះ!")
        return

    user_id = update.effective_user.id
    config = get_user_config(user_id)

    status_msg = await update.message.reply_text("⏳ កំពុងអាន និងដំណើរការឯកសារ SRT តាម Timeline...")

    try:
        file = await context.bot.get_file(doc.file_id)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".srt") as tmp_srt:
            srt_path = tmp_srt.name

        await file.download_to_drive(srt_path)

        subs = pysrt.open(srt_path, encoding="utf-8")
        if not subs:
            await status_msg.edit_text("❌ ឯកសារ SRT នេះគ្មានទិន្នន័យឡើយ!")
            return

        combined_audio = AudioSegment.silent(duration=0)
        current_time_ms = 0

        total_subs = len(subs)
        for index, sub in enumerate(subs):
            sub_text = sub.text_without_tags.replace("\n", " ").strip()
            if not sub_text:
                continue

            start_ms = (sub.start.hours * 3600 + sub.start.minutes * 60 + sub.start.seconds) * 1000 + sub.start.milliseconds
            end_ms = (sub.end.hours * 3600 + sub.end.minutes * 60 + sub.end.seconds) * 1000 + sub.end.milliseconds
            duration_ms = max(end_ms - start_ms, 1000)

            item_rate = calculate_srt_speed(len(sub_text), duration_ms, config)

            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as item_tmp:
                item_audio_path = item_tmp.name

            await convert_text_to_audio(
                text=sub_text,
                voice=config["voice"],
                rate=item_rate,
                pitch=config["pitch"],
                output_path=item_audio_path
            )

            if start_ms > current_time_ms:
                silence_gap = start_ms - current_time_ms
                combined_audio += AudioSegment.silent(duration=silence_gap)
                current_time_ms = start_ms

            segment = AudioSegment.from_file(item_audio_path)
            combined_audio += segment
            current_time_ms += len(segment)

            if os.path.exists(item_audio_path):
                os.remove(item_audio_path)

            if (index + 1) % 5 == 0 or index == total_subs - 1:
                await status_msg.edit_text(f"⏳ កំពុងបំប្លែង Subtitle... ({index + 1}/{total_subs})")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as final_tmp:
            final_mp3_path = final_tmp.name

        combined_audio.export(final_mp3_path, format="mp3")

        caption = (
            f"🎬 **បំប្លែងពី SRT ត្រូវតាម Timeline រួចរាល់!**\n"
            f"📄 ឯកសារ: `{doc.file_name}`\n"
            f"🎙️ សំឡេង: `{config['voice']}`\n"
            f"⚡ Mode: `{config['speed_mode']}`"
        )

        with open(final_mp3_path, "rb") as audio:
            await update.message.reply_audio(audio=audio, caption=caption, parse_mode="Markdown")

        await status_msg.delete()

        if os.path.exists(srt_path):
            os.remove(srt_path)
        if os.path.exists(final_mp3_path):
            os.remove(final_mp3_path)

    except Exception as e:
        await status_msg.edit_text(f"❌ មានបញ្ហាក្នុងការដំណើរការឯកសារ SRT៖ {str(e)}")


# ==================== MAIN EXECUTION ====================

def main():
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        print("❌ សូមដាក់ TELEGRAM BOT TOKEN នៅក្នុង Environment Variable (BOT_TOKEN)!")
        return

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