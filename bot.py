import os
import re
import zipfile
import json
import io
from datetime import datetime
from collections import defaultdict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ================== CONFIGURATION ==================
# Read token from environment variable (recommended) or hardcode as fallback
TOKEN = os.getenv("BOT_TOKEN", "8745342136:AAFyxi-RLDLSlJpriWNiidbHHFdsZu__9NM")

if TOKEN == "YOUR_BOT_TOKEN_HERE":
    raise ValueError("❌ Please set the BOT_TOKEN environment variable or edit the script.")
# ===================================================

# ------------------- USER DATA -------------------
user_data = defaultdict(dict)

# ------------------- HELPERS -------------------
def extract_full_cookies(text: str) -> set:
    pattern = r'NetflixId=[^;\s]+'
    return set(re.findall(pattern, text))

def get_cookie_list(cookies: set) -> list:
    return sorted(cookies)

# ------------------- ARCHIVE GENERATORS -------------------
def create_zip_txt(cookies: list) -> bytes:
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for idx, cookie in enumerate(cookies, start=1):
            zf.writestr(f"cookie{idx}.txt", cookie)
    zip_buffer.seek(0)
    return zip_buffer.read()

def create_zip_json(cookies: list) -> bytes:
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        data = [{"cookie": c} for c in cookies]
        zf.writestr("cookies.json", json.dumps(data, indent=2))
    zip_buffer.seek(0)
    return zip_buffer.read()

def create_7z_txt(cookies: list) -> bytes:
    try:
        import py7zr
        buffer = io.BytesIO()
        with py7zr.SevenZipFile(buffer, 'w') as archive:
            for idx, cookie in enumerate(cookies, start=1):
                archive.writestr(f"cookie{idx}.txt", cookie)
        buffer.seek(0)
        return buffer.read()
    except ImportError:
        return None

def create_rar_txt(cookies: list) -> bytes:
    try:
        import patoolib
        import tempfile
        import shutil
        temp_dir = tempfile.mkdtemp()
        try:
            for idx, cookie in enumerate(cookies, start=1):
                with open(os.path.join(temp_dir, f"cookie{idx}.txt"), 'w', encoding='utf-8') as f:
                    f.write(cookie)
            rar_path = os.path.join(temp_dir, "cookies.rar")
            patoolib.create_archive(rar_path, (temp_dir,), verbosity=-1)
            with open(rar_path, 'rb') as f:
                rar_data = f.read()
            return rar_data
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
    except ImportError:
        return None

def create_single_txt(cookies: list) -> bytes:
    text = "\n\n".join(cookies)
    return text.encode('utf-8')

# ------------------- KEYBOARDS -------------------
def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("📤 Upload Cookie File", callback_data="upload")],
        [InlineKeyboardButton("❓ Help", callback_data="help")]
    ]
    return InlineKeyboardMarkup(keyboard)

def download_keyboard():
    keyboard = [
        [InlineKeyboardButton("📦 ZIP (txt)", callback_data="dl_zip_txt"),
         InlineKeyboardButton("📦 ZIP (json)", callback_data="dl_zip_json")],
        [InlineKeyboardButton("📦 7z (txt)", callback_data="dl_7z_txt"),
         InlineKeyboardButton("📦 RAR (txt)", callback_data="dl_rar_txt")],
        [InlineKeyboardButton("📄 Single TXT (all)", callback_data="dl_single_txt")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ------------------- HANDLERS -------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data[user_id].clear()
    await update.message.reply_text(
        "👋 Welcome! I extract NetflixId cookies from any file.\n"
        "Upload any file (text, log, CSV, etc.) – I'll scan for cookies.",
        reply_markup=main_menu_keyboard()
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    data = query.data
    cookies = user_data[user_id].get("cookies")

    if data == "upload":
        await query.edit_message_text(
            "📂 Please send me **any file** (e.g., .txt, .csv, .log) containing cookie data.\n"
            "You can also paste the text directly.",
            parse_mode="Markdown"
        )
        user_data[user_id]["state"] = "waiting_for_file"

    elif data == "help":
        await query.edit_message_text(
            "📖 How it works:\n"
            "1. Upload a file with cookie data.\n"
            "2. I extract every `NetflixId=...` string.\n"
            "3. Choose a download format from the buttons.\n\n"
            "All data is processed and never stored permanently.",
            reply_markup=main_menu_keyboard()
        )

    elif data.startswith("dl_"):
        if not cookies:
            await query.edit_message_text("⚠️ No cookies found. Please upload a file first.")
            return

        cookie_list = get_cookie_list(cookies)
        count = len(cookie_list)
        file_data = None
        file_name = None
        caption = f"✅ {count} cookies extracted."

        if data == "dl_zip_txt":
            file_data = create_zip_txt(cookie_list)
            file_name = f"extracted_{count}.zip"
        elif data == "dl_zip_json":
            file_data = create_zip_json(cookie_list)
            file_name = f"extracted_{count}.zip"
        elif data == "dl_7z_txt":
            file_data = create_7z_txt(cookie_list)
            if file_data is None:
                await query.edit_message_text("❌ 7z support not installed. Please install `py7zr`.")
                return
            file_name = f"extracted_{count}.7z"
        elif data == "dl_rar_txt":
            file_data = create_rar_txt(cookie_list)
            if file_data is None:
                await query.edit_message_text("❌ RAR support not installed. Please install `patool` and `rarfile`.")
                return
            file_name = f"extracted_{count}.rar"
        elif data == "dl_single_txt":
            file_data = create_single_txt(cookie_list)
            file_name = f"extracted_{count}.txt"
        else:
            await query.edit_message_text("❌ Unknown format.")
            return

        await query.edit_message_text("⏳ Generating file...")
        await context.bot.send_document(
            chat_id=user_id,
            document=io.BytesIO(file_data),
            filename=file_name,
            caption=caption
        )
        await context.bot.send_message(
            chat_id=user_id,
            text="What would you like to do next?",
            reply_markup=main_menu_keyboard()
        )

    elif data == "cancel":
        user_data[user_id].clear()
        await query.edit_message_text(
            "🔄 Session cleared. Start over with /start",
            reply_markup=main_menu_keyboard()
        )

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_data[user_id].get("state") != "waiting_for_file":
        await update.message.reply_text("Please use the button to upload a file.")
        return

    document = update.message.document
    file = await document.get_file()
    file_content = await file.download_as_bytearray()
    text = file_content.decode('utf-8', errors='ignore')

    cookies = extract_full_cookies(text)
    if not cookies:
        await update.message.reply_text("❌ No `NetflixId=...` found in the file.")
        return

    user_data[user_id]["cookies"] = cookies
    user_data[user_id]["state"] = "extracted"

    await update.message.reply_text(
        f"🔍 Found **{len(cookies)}** unique cookie(s).\n"
        "Choose your download format:",
        parse_mode="Markdown",
        reply_markup=download_keyboard()
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_data[user_id].get("state") != "waiting_for_file":
        await update.message.reply_text("Please use the upload button first.")
        return

    text = update.message.text
    cookies = extract_full_cookies(text)
    if not cookies:
        await update.message.reply_text("❌ No `NetflixId=...` found in your message.")
        return

    user_data[user_id]["cookies"] = cookies
    user_data[user_id]["state"] = "extracted"

    await update.message.reply_text(
        f"🔍 Found **{len(cookies)}** unique cookie(s).\n"
        "Choose your download format:",
        parse_mode="Markdown",
        reply_markup=download_keyboard()
    )

# ------------------- MAIN -------------------
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("🤖 Bot is running... Press Ctrl+C to stop.")
    app.run_polling()

if __name__ == "__main__":
    main()