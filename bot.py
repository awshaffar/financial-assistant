from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime
import asyncio
import contextlib
import logging
from typing import Tuple, Optional

from telegram import Bot, Update
from telegram.error import Forbidden, NetworkError

# Constants
TELEGRAM_TOKEN = '7619232693:AAHbWMdK-dI7qoLcse7rZBpswpT-LbhFFcI'
SPREADSHEET_ID = '174hcUZViEmj-d33mh655C-xig6KZQTZOA_e9vf4t3yw'
CREDENTIALS_FILE = 'telegrambot-447103-ecb491824734.json'
SHEET_NAME = "Expenses"  # Name of your worksheet

# Google Sheets setup
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
creds = service_account.Credentials.from_service_account_file(
    CREDENTIALS_FILE, 
    scopes=SCOPES
)
sheets_service = build('sheets', 'v4', credentials=creds)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

def process_message(text: str) -> Tuple[Optional[Tuple[float, str, str]], Optional[str]]:
    """
    Parses expense message in format: 
    "amount category description"
    Example: "15.50 coffee breakfast with friends"
    """
    parts = text.strip().split(maxsplit=2)
    if len(parts) < 3:
        return None, "❌ Invalid format. Please use:\n<amount> <category> <description>\nExample: 15.50 food lunch with friends"
    
    try:
        amount = float(parts[0])
    except ValueError:
        return None, "❌ Invalid amount. Please enter a valid number"
    
    return (amount, parts[1], parts[2]), None

def append_to_sheet(data: Tuple[float, str, str]) -> None:
    """Appends expense data to Google Sheet"""
    date_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    amount, category, description = data
    
    values = [
        date_time,
        amount,
        category,
        description
    ]
    
    body = {"values": [values]}
    
    sheets_service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A:D",
        valueInputOption="USER_ENTERED",
        body=body
    ).execute()

async def handle_message(bot: Bot, message: str, chat_id: int) -> None:
    """Processes and responds to user messages"""
    data, error = process_message(message)
    if error:
        await bot.send_message(chat_id=chat_id, text=error)
        return
    
    try:
        await asyncio.to_thread(append_to_sheet, data)
        response = (
            "✅ Expense recorded!\n"
            f"• Amount: {data[0]}\n"
            f"• Category: {data[1]}\n"
            f"• Description: {data[2]}"
        )
    except Exception as e:
        logger.error("Sheet update failed: %s", e)
        response = "❌ Failed to save expense. Please try again later."
    
    await bot.send_message(chat_id=chat_id, text=response)

async def main() -> None:
    """Main bot loop"""
    async with Bot(TELEGRAM_TOKEN) as bot:
        update_id = None
        while True:
            try:
                updates = await bot.get_updates(offset=update_id, timeout=10)
                for update in updates:
                    update_id = update.update_id + 1
                    if update.message and update.message.text:
                        await handle_message(
                            bot,
                            update.message.text,
                            update.message.chat_id
                        )
            except NetworkError:
                await asyncio.sleep(1)
            except Forbidden:
                update_id += 1
            except Exception as e:
                logger.error("Unexpected error: %s", e)
                await asyncio.sleep(5)

if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())