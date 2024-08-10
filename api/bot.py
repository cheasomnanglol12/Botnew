import os
import httpx
import random
import time
import uuid
import asyncio
from loguru import logger
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

logger.add(sys.stdout, format="<white>{time:YYYY-MM-DD HH:mm:ss}</white>"
                             " | <level>{level: <8}</level>"
                             " | <cyan><b>{line}</b></cyan>"
                             " - <white><b>{message}</b></white>", level="INFO")

games = {
    1: {
        'name': 'Riding Extreme 3D',
        'appToken': 'd28721be-fd2d-4b45-869e-9f253b554e50',
        'promoId': '43e35910-c168-4634-ad4f-52fd764a843f',
    },
    2: {
        'name': 'Chain Cube 2048',
        'appToken': 'd1690a07-3780-4068-810f-9b5bbf2931b2',
        'promoId': 'b4170868-cef0-424f-8eb9-be0622e8e8e3',
    },
    3: {
        'name': 'My Clone Army',
        'appToken': '74ee0b5b-775e-4bee-974f-63e7f4d5bacb',
        'promoId': 'fe693b26-b342-4159-8808-15e3ff7f8767',
    },
    4: {
        'name': 'Train Miner',
        'appToken': '82647f43-3f87-402d-88dd-09a90025313f',
        'promoId': 'c4480ac7-e178-4973-8061-9ed5b2e17954',
    }
}

async def load_proxies(file_path):
    if os.path.exists(file_path):
        with open(file_path, 'r') as file:
            proxies = [line.strip() for line in file if line.strip()]
            random.shuffle(proxies)
            return proxies
    else:
        logger.info(f"Proxy file {file_path} not found. No proxies will be used.")
        return []

async def generate_client_id():
    timestamp = int(time.time() * 1000)
    random_numbers = ''.join(str(random.randint(0, 9)) for _ in range(19))
    return f"{timestamp}-{random_numbers}"

async def login(client_id, app_token, proxies, retries=5):
    for attempt in range(retries):
        proxy = random.choice(proxies) if proxies else None
        async with httpx.AsyncClient(proxies=proxy) as client:
            try:
                logger.info(f"Attempting to log in with client ID: {client_id} (Attempt {attempt + 1}/{retries})")
                response = await client.post(
                    'https://api.gamepromo.io/promo/login-client',
                    json={'appToken': app_token, 'clientId': client_id, 'clientOrigin': 'deviceid'}
                )
                response.raise_for_status()
                data = response.json()
                logger.info(f"Login successful for client ID: {client_id}")
                return data['clientToken']
            except httpx.HTTPStatusError as e:
                logger.error(f"Failed to login (attempt {attempt + 1}/{retries}): {e.response.json()}")
            except Exception as e:
                logger.error(f"Unexpected error during login (attempt {attempt + 1}/{retries}): {e}")
        await asyncio.sleep(2)
    logger.error("Maximum login attempts reached. Returning None.")
    return None

async def emulate_progress(client_token, promo_id, proxies):
    proxy = random.choice(proxies) if proxies else None
    logger.info(f"Emulating progress for promo ID: {promo_id}")
    async with httpx.AsyncClient(proxies=proxy) as client:
        response = await client.post(
            'https://api.gamepromo.io/promo/register-event',
            headers={'Authorization': f'Bearer {client_token}'},
            json={'promoId': promo_id, 'eventId': str(uuid.uuid4()), 'eventOrigin': 'undefined'}
        )
        response.raise_for_status()
        data = response.json()
        return data['hasCode']

async def generate_key(client_token, promo_id, proxies):
    proxy = random.choice(proxies) if proxies else None
    logger.info(f"Generating key for promo ID: {promo_id}")
    async with httpx.AsyncClient(proxies=proxy) as client:
        response = await client.post(
            'https://api.gamepromo.io/promo/create-code',
            headers={'Authorization': f'Bearer {client_token}'},
            json={'promoId': promo_id}
        )
        response.raise_for_status()
        data = response.json()
        return data['promoCode']

async def generate_key_process(app_token, promo_id, proxies):
    client_id = await generate_client_id()
    logger.info(f"Generated client ID: {client_id}")
    client_token = await login(client_id, app_token, proxies)
    if not client_token:
        logger.error(f"Failed to generate client token for client ID: {client_id}")
        return None

    for i in range(11):
        logger.info(f"Emulating progress event {i + 1}/11 for client ID: {client_id}")
        await asyncio.sleep(20000 * (random.random() / 3 + 1))
        try:
            has_code = await emulate_progress(client_token, promo_id, proxies)
        except httpx.HTTPStatusError:
            logger.warning(f"Event {i + 1}/11 failed for client ID: {client_id}")
            continue

        if has_code:
            logger.info(f"Progress event triggered key generation for client ID: {client_id}")
            break

    try:
        key = await generate_key(client_token, promo_id, proxies)
        logger.info(f"Generated key: {key} for client ID: {client_id}")
        return key
    except httpx.HTTPStatusError as e:
        logger.error(f"Failed to generate key: {e.response.json()}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Welcome to the Game Key Generator bot!\n\n"
                                    "Commands:\n"
                                    "/games - List available games\n"
                                    "/generate [game_id] [key_count] - Generate keys\n"
                                    "/proxies [file_path] - Set proxies file")

async def list_games(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    game_list = "\n".join([f"{key}: {value['name']}" for key, value in games.items()])
    await update.message.reply_text(f"Available games:\n{game_list}")

async def generate_keys(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        game_choice = int(context.args[0])
        key_count = int(context.args[1])
    except (ValueError, IndexError):
        await update.message.reply_text("Usage: /generate [game_id] [key_count]\nExample: /generate 1 5")
        return

    proxies = await load_proxies(context.user_data.get('proxies_file', 'proxy.txt'))
    keys, game_name = await main(game_choice, key_count, proxies)

    if keys:
        response = f"Generated {len(keys)} key(s) for {game_name}:\n" + "\n".join(keys)
    else:
        response = "No keys were generated."
    await update.message.reply_text(response)

async def set_proxies(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.args:
        proxies_file = context.args[0]
        context.user_data['proxies_file'] = proxies_file
        await update.message.reply_text(f"Proxies file set to: {proxies_file}")
    else:
        await update.message.reply_text("Usage: /proxies [file_path]")

async def main(game_choice, key_count, proxies):
    game = games[game_choice]
    logger.info(f"Starting key generation for {game['name']}")

    tasks = [generate_key_process(game['appToken'], game['promoId'], proxies) for _ in range(key_count)]
    keys = await asyncio.gather(*tasks)

    logger.info(f"Key generation completed for {game['name']}")
    return [key for key in keys if key], game['name']

if __name__ == "__main__":
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("games", list_games))
    application.add_handler(CommandHandler("generate", generate_keys))
    application.add_handler(CommandHandler("proxies", set_proxies))

    application.run_polling()
