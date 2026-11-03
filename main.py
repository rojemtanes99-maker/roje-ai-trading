import os
import time
import requests
import threading

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    raise ValueError("Missing TELEGRAM_BOT_TOKEN")

URL = f"https://api.telegram.org/bot{TOKEN}"
offset = 0
GROUP_ID = os.getenv("TELEGRAM_CHAT_ID")

print("ROJE AI TRADING BOT STARTED")


def send_message(chat_id, message):
    try:
        requests.post(
            f"{URL}/sendMessage",
            json={"chat_id": chat_id, "text": message},
            timeout=15
        )
    except Exception as e:
        print("Send error:", e)


while True:
    try:
        response = requests.get(
            f"{URL}/getUpdates",
            params={"offset": offset, "timeout": 30},
            timeout=35
        ).json()

        if not response.get("ok"):
            print("Telegram error:", response)
            time.sleep(5)
            continue

        for update in response.get("result", []):
            offset = update["update_id"] + 1

            message = update.get("message", {})
            chat = message.get("chat", {})
            chat_id = chat.get("id")
            text = message.get("text", "")

            if chat_id and chat.get("type") in ("group", "supergroup"):
                if not GROUP_ID:
                    GROUP_ID = str(chat_id)
                    print("GROUP ID DETECTED:", GROUP_ID)

            if chat_id and text.startswith("/start"):
                send_message(
                    chat_id,
                    "🚀 أهلاً بك في ROJE AI TRADING!\n"
                    "البوت يعمل بنجاح.\n"
                    "Group connection detected."
                )

    except Exception as e:
        print("Error:", e)
        time.sleep(5)
