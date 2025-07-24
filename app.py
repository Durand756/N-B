import os
import logging
from flask import Flask, request
import requests

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# 🔑 Utilise les variables d'environnement pour la sécurité
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "nakamaverifytoken")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "")

@app.route("/", methods=['GET'])
def home():
    return "NakamaBot is alive! 🤖"

@app.route("/webhook", methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        # ✅ Vérification du webhook
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        
        logger.info(f"Webhook verification: mode={mode}, token={token}")
        
        if mode == "subscribe" and token == VERIFY_TOKEN:
            logger.info("Webhook verified successfully!")
            return challenge, 200
        else:
            logger.error("Verification token mismatch")
            return "Verification token mismatch", 403
            
    elif request.method == 'POST':
        # ✅ Réception des messages avec gestion d'erreurs
        try:
            data = request.get_json()
            logger.info(f"Received data: {data}")
            
            if not data:
                return "No data received", 400
                
            for entry in data.get('entry', []):
                for messaging_event in entry.get('messaging', []):
                    # Vérifier que l'événement contient un sender
                    if 'sender' not in messaging_event:
                        continue
                        
                    sender_id = messaging_event['sender']['id']
                    
                    # Traiter les messages reçus
                    if 'message' in messaging_event:
                        message_text = messaging_event['message'].get('text', '')
                        logger.info(f"Message from {sender_id}: {message_text}")
                        
                        if message_text.lower() in ["/start", "start", "hello", "hi"]:
                            send_message(sender_id, "👋 Konnichiwa, nakama ! Je suis NakamaBot, prêt à te guider aujourd'hui.")
                        else:
                            # Réponse par défaut
                            send_message(sender_id, f"Tu as dit: {message_text}")
                    
                    # Traiter les postbacks (boutons)
                    elif 'postback' in messaging_event:
                        payload = messaging_event['postback']['payload']
                        logger.info(f"Postback from {sender_id}: {payload}")
                        send_message(sender_id, f"Postback reçu: {payload}")
                        
        except Exception as e:
            logger.error(f"Error processing webhook: {str(e)}")
            return "Error processing request", 500
            
        return "ok", 200

def send_message(recipient_id, text):
    """Envoie un message à un utilisateur Facebook"""
    url = "https://graph.facebook.com/v18.0/me/messages"
    
    params = {
        "access_token": PAGE_ACCESS_TOKEN
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    data = {
        "recipient": {"id": recipient_id},
        "message": {"text": text},
        "messaging_type": "RESPONSE"  # Obligatoire pour les réponses
    }
    
    try:
        response = requests.post(url, params=params, headers=headers, json=data, timeout=10)
        logger.info(f"Message sent to {recipient_id}: {response.status_code}")
        
        if response.status_code != 200:
            logger.error(f"Error sending message: {response.text}")
            
        return response.status_code
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed: {str(e)}")
        return 500

@app.route("/health", methods=['GET'])
def health_check():
    """Endpoint de santé pour Render"""
    return {"status": "healthy", "bot": "NakamaBot"}, 200

if __name__ == "__main__":
    # Configuration pour le déploiement
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
