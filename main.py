import os
import time
import requests

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    raise ValueError("Missing TELEGRAM_BOT_TOKEN")

URL = f"https://api.telegram.org/bot{TOKEN}"

offset = 0

print("ROJE AI TRADING BOT STARTED")

while True:
    try:
        response = requests.get(
            f"{URL}/getUpdates",
            params={"offset": offset, "timeout": 30},
            timeout=35
        ).json()

        for update in response.get("result", []):
            offset = update["update_id"] + 1

            message = update.get("message", {})
            chat_id = message.get("chat", {}).get("id")
            text = message.get("text", "")

            if chat_id and text.startswith("/start"):
                requests.post(
                    f"{URL}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": "🚀 أهلاً بك في ROJE AI TRADING!\nالبوت يعمل بنجاح."
                    }
                )

    except Exception as e:
        print("Error:", e)
        time.sleep(5)
