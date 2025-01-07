from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime

# Konstanta
TELEGRAM_TOKEN = '7619232693:AAHbWMdK-dI7qoLcse7rZBpswpT-LbhFFcI'
SPREADSHEET_ID = '174hcUZViEmj-d33mh655C-xig6KZQTZOA_e9vf4t3yw'  # dari URL spreadsheet
CREDENTIALS_FILE = 'telegrambot-447103-ecb491824734.json'  # file yang tadi didownload

# Setup Google Sheets API
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
creds = service_account.Credentials.from_service_account_file(
    CREDENTIALS_FILE, 
    scopes=SCOPES
)
sheets_service = build('sheets', 'v4', credentials=creds)

async def hello(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f'Hello {update.effective_user.first_name}')


app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

app.add_handler(CommandHandler("hello", hello))

app.run_polling()