import logging
import asyncio
from os import environ
from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import ChatJoinRequest
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

# Define sudo users (replace with your actual sudo user IDs or load from config/database)
SUDO_USERS = [5900873171]  # Updated with user ID from log; add other IDs as needed

# Allowed and restricted language codes
ALLOWED_LANGUAGES = {'en', 'hi', 'bn', 'ta', 'te', 'mr', 'gu', 'ml', 'kn', 'or', 'pa', 'as', 'si'}  # English, Hindi, Bengali, Tamil, Telugu, Marathi, Gujarati, Malayalam, Kannada, Odia, Punjabi, Assamese, Sinhala
RESTRICTED_LANGUAGES = {'my', 'uz', 'ar'}  # Burmese (Myanmar), Uzbek (Uzbekistan), Arabic

def is_allowed_user(user):
    """Check if user is allowed by analyzing language of each profile field."""
    profile_fields = []
    if user.first_name:
        profile_fields.append(("first_name", user.first_name))
    if user.last_name:
        profile_fields.append(("last_name", user.last_name))
    if user.username:
        profile_fields.append(("username", user.username))
    if user.bio:
        profile_fields.append(("bio", user.bio))

    if not profile_fields:
        logging.info(f"User {user.id} has no profile data, approving as non-restricted")
        return True  # Approve users with no profile data (neutral case)

    for field_name, field_text in profile_fields:
        try:
            detected_lang = detect(field_text)
            logging.info(f"Detected language for user {user.id} in {field_name}: {detected_lang}")
            
            if detected_lang in RESTRICTED_LANGUAGES:
                logging.info(f"User {user.id} declined due to restricted language in {field_name}: {detected_lang}")
                return False  # Decline if any field is in a restricted language
        except LangDetectException:
            logging.info(f"Could not detect language for user {user.id} in {field_name}, treating as non-restricted")
            continue  # Treat undetectable fields as non-restricted

    logging.info(f"User {user.id} approved (no restricted languages detected)")
    return True  # Approve if no restricted languages are found

@User.on_chat_join_request()
async def handle_join_request(client, join_request):
    if not isinstance(join_request, ChatJoinRequest):
        logging.error(f"Invalid join request object for user {join_request.from_user.id}: {type(join_request)}")
        return

    chat_id = join_request.chat.id
    user = join_request.from_user
    
    if not running_tasks.get(chat_id, False):
        return  # Only process join requests if approval task is running

    try:
        if is_allowed_user(user):
            await client.approve_chat_join_request(chat_id, user.id)
            logging.info(f"Approved join request for user {user.id} in chat {chat_id}")
        else:
            await client.decline_chat_join_request(chat_id, user.id)
            logging.info(f"Declined join request for user {user.id} in chat {chat_id} (restricted language detected)")
    except FloodWait as e:
        logging.info(f"FloodWait: Sleeping for {e.value} seconds")
        await asyncio.sleep(e.value)
    except Exception as e:
        logging.error(f"Error processing join request for user {user.id}: {e}")

@User.on_message(filters.command(["run", "approve"], [".", "/"]) & filters.user(SUDO_USERS))
async def approve(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    await message.delete()

    if chat_id in running_tasks:
        await client.send_message(chat_id, "Approval task is already running!")
        return

    logging.info(f"Starting approval task for chat {chat_id} by sudo user {user_id}")
    running_tasks[chat_id] = True

    try:
        # Process existing pending requests
        async for join_request in client.get_chat_join_requests(chat_id):
            if not running_tasks.get(chat_id, False):
                break
            if not isinstance(join_request, ChatJoinRequest):
                logging.error(f"Invalid join request object in chat {chat_id}: {type(join_request)}")
                continue
            await handle_join_request(client, join_request)
            await asyncio.sleep(1)  # Prevent excessive API calls
    except Exception as e:
        logging.error(f"Error processing pending join requests in chat {chat_id}: {e}")
    finally:
        running_tasks.pop(chat_id, None)  # Clean up
        await client.send_message(chat_id, "**Task Stopped** ✓ **Processed All Pending Join Requests**")

@User.on_message(filters.command(["stop"], [".", "/"]) & filters.user(SUDO_USERS))
async def stop_approve(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    await message.delete()

    if chat_id not in running_tasks:
        await client.send_message(chat_id, "No approval task is running!")
        return

    running_tasks[chat_id] = False
    logging.info(f"Stopping approval task for chat {chat_id} by sudo user {user_id}")
    await client.send_message(chat_id, "Approval task stopped!")

logging.info("Bot Started...")
User.run()
