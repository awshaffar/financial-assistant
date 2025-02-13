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

def is_date(text, fmt="%d/%m"):
    try:
        datetime.strptime(text, fmt)
        return True
    except ValueError:
        return False

def normalize_date(date_str: str) -> str:
    current_date = datetime.now()
    default_iso = current_date.strftime("%Y-%m-%d")
    try:
        # Already in correct format validation
        parsed = datetime.strptime(date_str, "%Y-%m-%d")
        return date_str
    except ValueError:
        pass

    try:
        # Handle day/month format (e.g., "12/2" → 12 February)
        day, month = map(int, date_str.split('/', 1))
        normalized = current_date.replace(month=month, day=day)
        return normalized.strftime("%Y-%m-%d")
    except (ValueError, TypeError, AttributeError):
        return default_iso  # Fallback to current date
    
def process_message(text: str) -> Tuple[list[Tuple[float, str, str]], list[str]]:
    """
    Parses two input formats:
    1. With date: "DD/MM AMOUNT CATEGORY DESCRIPTION" (e.g., "12/2 10440 medicine vitamin D")
    2. Without date: "AMOUNT CATEGORY DESCRIPTION" (e.g., "10440 medicine vitamin D")
    """
    valid_entries = []
    errors = []

    entries = [e.strip() for e in text.split('\n') if e.strip()]
    
    for idx, entry in enumerate(entries, 1):
        parts = entry.split()
        
        if not parts:
            errors.append(f"❌ Line {idx}: Empty entry")
            continue

        try:
            # Case 1: Entry starts with a date (XX/XX format)
            if is_date(parts[0]):
                if len(parts) < 4:
                    errors.append(f"❌ Line {idx}: Date format requires 4 components (DATE AMOUNT CATEGORY DESCRIPTION)")
                    continue
                
                date_str = normalize_date(parts[0])
                amount = float(parts[1])
                category = parts[2]
                description = ' '.join(parts[3:])  # Handle multi-word descriptions
                valid_entries.append((date_str, amount, category, description))
                
            # Case 2: Default format without date
            else:
                if len(parts) < 3:
                    errors.append(f"❌ Line {idx}: Needs 3 components (AMOUNT CATEGORY DESCRIPTION)")
                    continue
                
                amount = float(parts[0])
                category = parts[1]
                description = ' '.join(parts[2:])  # Handle multi-word descriptions
                valid_entries.append((amount, category, description))
                
        except ValueError as e:
            errors.append(f"❌ Line {idx}: Invalid numeric format '{parts[0]}'")
        except Exception as e:
            errors.append(f"❌ Line {idx}: Unexpected error - {str(e)}")

    return valid_entries, errors


def append_to_sheet(data: list[Tuple[float, str, str]]) -> int:
    """Appends multiple expense records to Google Sheet"""
    date_time = datetime.now().strftime("%Y-%m-%d")
    
    values = [
      # For 4-component tuples (existing_date, amount, category, description)
      [item[0], item[1], item[2], item[3]] if len(item) == 4 
      # For 3-component tuples (amount, category, description)
      else [date_time, item[0], item[1], item[2]] 
      for item in data
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
            
            # Fixed unpacking logic for both formats
            for entry in entries:
                if len(entry) == 4:
                    date_str, amount, category, description = entry
                    response.append(f"• [{date_str}] {amount:.2f} {category}: {description}")
                else:
                    amount, category, description = entry
                    response.append(f"• {amount:.2f} {category}: {description}")
        
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