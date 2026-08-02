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
from pydub import AudioSegment

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
        return "+45%"


def calculate_speed_for_duration(text_length: int, duration_ms: int) -> str:
    """
    គណនាល្បឿនស្វ័យប្រវត្តិដើម្បីឱ្យ audio ត្រូវលេងក្នុងរយៈពេលដែលបានកំណត់
    """
    if duration_ms <= 0 or text_length <= 0:
        return "+0%"
    
    duration_sec = duration_ms / 1000.0
    estimated_normal_duration_ms = text_length * 150
    estimated_normal_duration_sec = estimated_normal_duration_ms / 1000.0
    
    speed_ratio = estimated_normal_duration_sec / duration_sec
    speed_percent = int((speed_ratio - 1) * 100)
    speed_percent = max(-90, min(100, speed_percent))
    
    if speed_percent > 0:
        return f"+{speed_percent}%"
    else:
        return f"{speed_percent}%"


async def convert_text_to_audio(text: str, voice: str, rate: str, pitch: str, output_path: str):
    """បំប្លែង Text ទៅជា Audio MP3 ដោយប្រើ Edge-TTS"""
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
    await communicate.save(output_path)


def srt_time_to_ms(time_obj) -> int:
    """បំប្លែង pysrt SubtitleTime ទៅជា Milliseconds"""
    return (time_obj.hours * 3600 + time_obj.minutes * 60 + time_obj.seconds) * 1000 + time_obj.milliseconds


def build_timeline_audio(subtitles_data: list, output_path: str) -> bool:
    """
    បង្កើត Audio រួមមួយដែលតម្រឹមតាម Timeline ពិតប្រាកដនៃ SRT (រួមទាំង Silence/Gaps)
    subtitles_data: list នៃ dict {'file': path, 'start_ms': int, 'end_ms': int}
    """
    try:
        if not subtitles_data:
            return False
        
        # បង្កើត Audio ទទេ។ ដើមដំបូងឡើយគឺ 0ms
        final_audio = AudioSegment.silent(duration=0)
        current_timeline_ms = 0

        for item in subtitles_data:
            audio_path = item['file']
            start_ms = item['start_ms']
            end_ms = item['end_ms']
            slot_duration = end_ms - start_ms

            if not os.path.exists(audio_path):
                continue

            # ១. ប្រសិនបើ Timeline បច្ចុប្បន្នទាន់ដល់ Start Time នៃ Subtitle បន្ទាប់ ត្រូវបន្ថែម Sile[...]
            if start_ms > current_timeline_ms:
                gap_duration = start_ms - current_timeline_ms
                final_audio += AudioSegment.silent(duration=gap_duration)
                current_timeline_ms = start_ms

            # ២. ផ្ទុកឯកសារ Audio Segment នៃ Subtitle នោះ
            sub_audio = AudioSegment.from_mp3(audio_path)
            
            # ប្រសិនបើ Audio វែងជាង Slot duration ដែលមាន ត្រូវ Trim ឬ កាត់ ដើម្បីកុំឱ្យ Overlap
            if len(sub_audio) > slot_duration and slot_duration > 0:
                sub_audio = sub_audio[:slot_duration]

            # ៣. បន្ថែម Audio ទៅក្នុង Final Audio Timeline
            final_audio += sub_audio
            current_timeline_ms += len(sub_audio)

        # រក្សាទុកឯកសារលទ្ធផល final output
        final_audio.export(output_path, format="mp3", bitrate="192k")
        print(f"[TIMELINE] បង្កើត Audio តាម Timeline SRT រួចរាល់: {output_path}")
        return True

    except Exception as e:
        print(f"[ERROR] បញ្ហាក្នុងការបង្កើត Timeline Audio: {str(e)}")
        return False


def is_srt_file(filename: str) -> bool:
    """Check if file is SRT format"""
    if not filename:
        return False
    return filename.lower().endswith('.srt')


def is_srt_content(text: str) -> bool:
    """Detect if text content is SRT format by checking for SRT pattern"""
    if not text or len(text.strip()) < 20:
        return False
    
    srt_pattern = r'\d+\s*\n\s*\d{2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{2}:\d{2}:\d{2},\d{3}'
    return bool(re.search(srt_pattern, text))


# ==================== BOT HANDLERS ====================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """បញ្ជា /start"""
    welcome_text = (
        "សូមស្វាគមន៍មកកាន់ **Khmer Text-to-Speech Bot**! 🇰🇭\n\n"
        "លោកអ្នកអាច៖\n"
        "1. ផ្ញើសារអត្ថបទជាភាសាខ្មែរមកទីនេះភ្លាមៗ\n"
        "2. ផ្ញើឯកសារអត្ថបទចម្រៀង/ចំណងជើងរឿងប្រភេទ **.srt**\n"
        "3. ផ្ញើផ្នែក SRT ដោយ Paste ដោយផ្ទាល់ (វាលេងតាមពេលវេលា SRT ដែលបានកំណត់)\n\n"
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
            InlineKeyboardButton("⚡ Speed: Auto (Timeline)", callback_data="set_speed_auto"),
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


async def process_srt_subs(subs, update: Update, config: dict, status_msg):
    """អនុវត្តការបង្កើត Audio តាម Timeline ចេញពី Subtitles Object"""
    if not subs:
        await status_msg.edit_text("❌ មិនមានអត្ថបទក្នុង SRT នេះទេ!")
        return

    await status_msg.edit_text(f"⏳ កំពុងបង្កើតសំឡេង {len(subs)} subtitle(s)...")

    subtitles_data = []
    temp_files_to_clean = []

    try:
        for idx, sub in enumerate(subs):
            text_content = sub.text_without_tags.replace("\n", " ").strip()
            if not text_content:
                continue

            start_ms = srt_time_to_ms(sub.start)
            end_ms = srt_time_to_ms(sub.end)
            duration_ms = max(100, end_ms - start_ms)

            if config["speed_mode"] == "auto":
                calculated_rate = calculate_speed_for_duration(len(text_content), duration_ms)
            else:
                calculated_rate = config["speed_mode"]

            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_file:
                output_file = tmp_file.name
                temp_files_to_clean.append(output_file)

            await convert_text_to_audio(
                text=text_content,
                voice=config["voice"],
                rate=calculated_rate,
                pitch=config["pitch"],
                output_path=output_file
            )

            subtitles_data.append({
                'file': output_file,
                'start_ms': start_ms,
                'end_ms': end_ms
            })

        await status_msg.edit_text("⏳ កំពុងផ្គុំ Audio តាម Timeline SRT...")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_merged:
            merged_file = tmp_merged.name
            temp_files_to_clean.append(merged_file)

        if build_timeline_audio(subtitles_data, merged_file):
            caption = f"🎬 **SRT Content បំប្លែងរួចរាល់!**\n📊 Subtitles: {len(subtitles_data)}\n⏱️ Synced accurately to timeline"

            with open(merged_file, "rb") as audio:
                await update.message.reply_audio(audio=audio, caption=caption, parse_mode="Markdown")

            await status_msg.delete()
        else:
            await status_msg.edit_text("❌ មានបញ្ហាក្នុងការរួមបញ្ចូល Audio តាម Timeline!")

    except Exception as e:
        print(f"[ERROR] {str(e)}")
        await status_msg.edit_text(f"❌ មានបញ្ហាក្នុងការដំណើរការ SRT៖ {str(e)}")

    finally:
        # Clean up all temp generated audio files
        for fpath in temp_files_to_clean:
            if os.path.exists(fpath):
                try:
                    os.remove(fpath)
                except Exception:
                    pass


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ដំណើរការអត្ថបទធម្មតាដែលផ្ញើចូល"""
    text = update.message.text
    if not text or text.startswith("/"):
        return

    user_id = update.effective_user.id
    config = get_user_config(user_id)
    
    # Check if this is SRT content pasted as text
    if is_srt_content(text):
        status_msg = await update.message.reply_text("⏳ កំពុងវិភាគ SRT Content...")
        subs = pysrt.from_string(text)
        await process_srt_subs(subs, update, config, status_msg)
    else:
        # Regular text message
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
    doc = getattr(update.message, 'document', None)

    if not doc:
        await update.message.reply_text("⚠️ មិនមានឯកសារ ទទួលបាន។")
        return

    filename = getattr(doc, 'file_name', '') or ''
    if not is_srt_file(filename):
        await update.message.reply_text("⚠️ សូមផ្ញើតែឯកសារប្រភេទ `.srt` ប៉ុណ្ណោះ!")
        return

    user_id = update.effective_user.id
    config = get_user_config(user_id)

    status_msg = await update.message.reply_text("⏳ កំពុងទាញយក និងវិភាគឯកសារ .SRT...")

    srt_path = None
    try:
        file = await context.bot.get_file(doc.file_id)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".srt") as tmp_srt:
            srt_path = tmp_srt.name

        await file.download_to_drive(srt_path)

        # Try to parse with pysrt, with fallback to reading file as string
        try:
            subs = pysrt.open(srt_path, encoding="utf-8")
        except Exception:
            with open(srt_path, "r", encoding="utf-8", errors="ignore") as f:
                srt_content = f.read()
            subs = pysrt.from_string(srt_content)

        await process_srt_subs(subs, update, config, status_msg)

    except Exception as e:
        print(f"[ERROR] {str(e)}")
        try:
            await status_msg.edit_text(f"❌ មានបញ្ហាក្នុងការដំណើរការឯកសារ SRT៖ {str(e)}")
        except Exception:
            pass

    finally:
        # Ensure the uploaded SRT temp file is removed
        if srt_path and os.path.exists(srt_path):
            try:
                os.remove(srt_path)
            except Exception:
                pass


# ==================== MAIN EXECUTION ====================

def main():
    """ចាប់ផ្តើម Bot"""
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        print("❌ សូមដាក់ TELEGRAM BOT TOKEN នៅក្នុង Environment Variable (BOT_TOKEN)!")
        return

    health_thread = threading.Thread(target=start_health_check_server, daemon=True)
    health_thread.start()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CallbackQueryHandler(button_callback))

    app.add_handler(MessageHandler(filters.Document.ALL, handle_document_message))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    print("🤖 Telegram Bot កំពុងដំណើរការ...")
    app.run_polling()


if __name__ == "__main__":
    main()
