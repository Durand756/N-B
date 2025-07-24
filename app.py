from flask import Flask, request

app = Flask(__name__)

VERIFY_TOKEN = "nakamaverifytoken"  # 🔑 définis ton token ici
PAGE_ACCESS_TOKEN = "TON_PAGE_ACCESS_TOKEN_ICI"

@app.route("/", methods=['GET'])
def home():
    return "NakamaBot is alive!"

@app.route("/webhook", methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        # ✅ Vérification du webhook
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        if mode == "subscribe" and token == VERIFY_TOKEN:
            return challenge, 200
        else:
            return "Verification token mismatch", 403

    elif request.method == 'POST':
        # ✅ Réception des messages
        data = request.get_json()
        for entry in data.get('entry', []):
            for messaging_event in entry.get('messaging', []):
                sender_id = messaging_event['sender']['id']
                if 'message' in messaging_event:
                    message_text = messaging_event['message'].get('text')
                    if message_text == "/start":
                        send_message(sender_id, "👋 Konnichiwa, nakama ! Je suis NakamaBot, prêt à te guider aujourd'hui.")
        return "ok", 200

import requests
def send_message(recipient_id, text):
    params = {
        "access_token": PAGE_ACCESS_TOKEN
    }
    headers = {
        "Content-Type": "application/json"
    }
    data = {
        "recipient": {"id": recipient_id},
        "message": {"text": text}
    }
    r = requests.post("https://graph.facebook.com/v18.0/me/messages", params=params, headers=headers, json=data)
    return r.status_code

if __name__ == "__main__":
    app.run()
