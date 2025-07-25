import logging
import asyncio
import re
from os import environ
from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from langdetect import detect, LangDetectException

# Configure logging for errors and info
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize Pyrogram client
SESSION = environ.get("SESSION", "")
if not SESSION:
    raise ValueError("SESSION environment variable is not set")
User = Client(name="AcceptUser", session_string=SESSION)

# Store running tasks to allow stopping
running_tasks = {}

# Regular expression to detect URLs (including Telegram t.me links)
URL_PATTERN = re.compile(r'(?:http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+|t\.me/(?:[a-zA-Z0-9_+]+))')

async def has_links_in_bio(client, user_id):
    try:
        user = await client.get_users(user_id)
        if user.bio:
            return bool(URL_PATTERN.search(user.bio))
        return False
    except Exception as e:
        logging.error(f"Error checking user bio for {user_id}: {e}")
        return False

async def is_bio_english(client, user_id):
    """Check if the user's bio is in English using langdetect."""
    try:
        user = await client.get_users(user_id)
        if user.bio:
            return detect(user.bio) == 'en'
        return True  # Treat empty bio as acceptable
    except LangDetectException as e:
        logging.warning(f"Language detection failed for user {user_id}: {e}")
        return True  # Allow user if language detection fails
    except Exception as e:
        logging.error(f"Error checking user bio language for {user_id}: {e}")
        return True

@User.on_message(filters.command(["run", "approve"], [".", "/"]))
async def approve(client, message):
    chat_id = message.chat.id
    await message.delete()

    if chat_id in running_tasks:
        await client.send_message(chat_id, "Approval task is already running!")
        return

    logging.info(f"Starting approval task for chat {chat_id}")
    running_tasks[chat_id] = True

    try:
        while running_tasks.get(chat_id, False):
            try:
                async for request in client.get_chat_join_requests(chat_id):
                    user_id = request.user.id
                    if await has_links_in_bio(client, user_id):
                        logging.info(f"Skipped user {user_id} due to links in bio")
                        continue
                    # Optional: Uncomment the following lines to enable English-only bio filtering
                    # if not await is_bio_english(client, user_id):
                    #     logging.info(f"Skipped user {user_id} due to non-English bio")
                    #     continue
                    await client.approve_chat_join_request(chat_id, user_id)
                    logging.info(f"Approved user {user_id} in chat {chat_id}")
                await asyncio.sleep(1)  # Prevent excessive API calls
            except FloodWait as e:
                logging.info(f"FloodWait: Sleeping for {e.value} seconds")
                await asyncio.sleep(e.value)
            except Exception as e:
                logging.error(f"Error in approval task: {e}")
                await asyncio.sleep(1)  # Avoid rapid error loops
    finally:
        running_tasks.pop(chat_id, None)  # Clean up
        await client.send_message(chat_id, "**Task Stopped** ✓ **Approved All Eligible Pending Join Requests**")

@User.on_message(filters.command(["stop"], [".", "/"]))
async def stop_approve(client, message):
    chat_id = message.chat.id
    await message.delete()

    if chat_id not in running_tasks:
        await client.send_message(chat_id, "No approval task is running!")
        return

    running_tasks[chat_id] = False
    logging.info(f"Stopping approval task for chat {chat_id}")
    await client.send_message(chat_id, "Approval task stopped!")

logging.info("Bot Started...")
User.run()
