from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime
import asyncio
import contextlib
import logging
from typing import Tuple, Optional

from telegram import Bot, Update
from telegram.error import Forbidden, NetworkError

import json

with open('config.json') as f:
    config = json.load(f)

# Constants
TELEGRAM_TOKEN = config['telegram_token']
SPREADSHEET_ID = config['spreadsheet_id']
CREDENTIALS_FILE = config['credentials_file']
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

def process_message(text: str) -> Tuple[list[Tuple[float, str, str]], list[str]]:
    """
    Parses newline-separated expense messages in the format:
    "15.50 coffee latte
    20 food lunch
    5 transport bus"
    """
    valid_entries = []
    errors = []

    # Split into individual entries by newline
    entries = [e.strip() for e in text.split('\n') if e.strip()]
    
    for idx, entry in enumerate(entries, 1):
        parts = entry.split(maxsplit=2)
        if len(parts) < 3:
            errors.append(f"❌ Line {idx}: '{entry}' - Needs 3 components (amount, category, description)")
            continue
        
        try:
            amount = float(parts[0])
            category = parts[1]
            description = parts[2] if len(parts) > 2 else ""
            valid_entries.append((amount, category, description))
        except ValueError:
            errors.append(f"❌ Line {idx}: Invalid amount '{parts[0]}'")

    return valid_entries, errors

def append_to_sheet(data: list[Tuple[float, str, str]]) -> int:
    """Appends multiple expense records to Google Sheet"""
    date_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    values = [
        [date_time, amount, category, description]
        for amount, category, description in data
    ]
    
    body = {"values": values}
    
    result = sheets_service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A:D",
        valueInputOption="USER_ENTERED",
        body=body
    ).execute()
    
    return result.get('updates', {}).get('updatedCells', 0) // 4  # Return number of rows added

async def handle_message(bot: Bot, message: str, chat_id: int) -> None:
    """Processes and responds to user messages"""
    entries, errors = process_message(message)
    
    if not entries and not errors:
        await bot.send_message(chat_id, "⚠️ No valid entries found. Format:\n<amount> <category> <description>\nExample: 15.50 food lunch, 20 transport taxi")
        return

    response = []
    
    try:
        if entries:
            rows_added = await asyncio.to_thread(append_to_sheet, entries)
            response.append(f"✅ Successfully added {rows_added} expense(s):")
            response.extend([
                f"• {amount} {category}: {desc}"
                for amount, category, desc in entries
            ])
        
        if errors:
            response.append("\n⚠️ Errors:")
            response.extend(errors)
            
        await bot.send_message(chat_id, "\n".join(response))
        
    except Exception as e:
        logger.error("Sheet update failed: %s", e)
        await bot.send_message(chat_id, "❌ Failed to save expenses. Please try again later.")

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