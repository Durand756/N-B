import os
import logging
import json
from flask import Flask, request, jsonify
import requests
from datetime import datetime

# Configuration du logging plus détaillée
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# 🔑 Configuration avec validation
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "nakamaverifytoken")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "")

# Validation des tokens au démarrage
if not PAGE_ACCESS_TOKEN:
    logger.error("❌ PAGE_ACCESS_TOKEN is missing!")
else:
    logger.info(f"✅ PAGE_ACCESS_TOKEN configuré (longueur: {len(PAGE_ACCESS_TOKEN)})")

logger.info(f"✅ VERIFY_TOKEN: {VERIFY_TOKEN}")

@app.route("/", methods=['GET'])
def home():
    return jsonify({
        "status": "NakamaBot is alive! 🤖",
        "timestamp": datetime.now().isoformat(),
        "verify_token_set": bool(VERIFY_TOKEN),
        "page_token_set": bool(PAGE_ACCESS_TOKEN)
    })

@app.route("/webhook", methods=['GET', 'POST'])
def webhook():
    logger.info(f"📨 Webhook appelé - Méthode: {request.method}")
    logger.info(f"📨 Headers reçus: {dict(request.headers)}")
    
    if request.method == 'GET':
        # ✅ Vérification du webhook avec débogage détaillé
        mode = request.args.get('hub.mode', 'NON_DEFINI')
        token = request.args.get('hub.verify_token', 'NON_DEFINI')
        challenge = request.args.get('hub.challenge', 'NON_DEFINI')
        
        logger.info(f"🔍 Paramètres GET reçus:")
        logger.info(f"   - hub.mode: {mode}")
        logger.info(f"   - hub.verify_token: {token}")
        logger.info(f"   - hub.challenge: {challenge}")
        logger.info(f"   - Token attendu: {VERIFY_TOKEN}")
        
        if mode == "subscribe" and token == VERIFY_TOKEN:
            logger.info("✅ Webhook vérifié avec succès!")
            return challenge, 200
        else:
            logger.error(f"❌ Échec de vérification - mode={mode}, token_match={token == VERIFY_TOKEN}")
            return "Verification token mismatch", 403
            
    elif request.method == 'POST':
        # ✅ Réception des messages avec débogage complet
        try:
            # Log de la requête brute
            raw_data = request.get_data(as_text=True)
            logger.info(f"📨 Données brutes reçues: {raw_data}")
            
            data = request.get_json()
            logger.info(f"📨 JSON parsé: {json.dumps(data, indent=2)}")
            
            if not data:
                logger.error("❌ Aucune donnée JSON reçue")
                return jsonify({"error": "No data received"}), 400
            
            # Vérifier la structure des données
            if 'entry' not in data:
                logger.error("❌ Pas de champ 'entry' dans les données")
                return jsonify({"error": "No entry field"}), 400
                
            logger.info(f"📊 Nombre d'entrées à traiter: {len(data.get('entry', []))}")
            
            for i, entry in enumerate(data.get('entry', [])):
                logger.info(f"🔄 Traitement de l'entrée {i+1}: {json.dumps(entry, indent=2)}")
                
                if 'messaging' not in entry:
                    logger.warning(f"⚠️ Pas de champ 'messaging' dans l'entrée {i+1}")
                    continue
                
                for j, messaging_event in enumerate(entry.get('messaging', [])):
                    logger.info(f"📝 Événement messaging {j+1}: {json.dumps(messaging_event, indent=2)}")
                    
                    # Vérifier la présence du sender
                    if 'sender' not in messaging_event:
                        logger.warning("⚠️ Pas de champ 'sender' dans l'événement")
                        continue
                        
                    sender_id = messaging_event['sender']['id']
                    logger.info(f"👤 Sender ID: {sender_id}")
                    
                    # Traiter les messages reçus
                    if 'message' in messaging_event:
                        message_data = messaging_event['message']
                        message_text = message_data.get('text', '')
                        
                        logger.info(f"💬 Message reçu de {sender_id}: '{message_text}'")
                        logger.info(f"📋 Données complètes du message: {json.dumps(message_data, indent=2)}")
                        
                        # Éviter les boucles infinies (ignorer nos propres messages)
                        if 'is_echo' in message_data and message_data['is_echo']:
                            logger.info("🔄 Message écho ignoré")
                            continue
                        
                        # Réponses selon le contenu
                        if message_text.lower() in ["/start", "start", "hello", "hi", "bonjour", "salut"]:
                            response_text = "👋 Konnichiwa, nakama ! Je suis NakamaBot, prêt à te guider aujourd'hui."
                        elif message_text.lower() == "test":
                            response_text = f"🧪 Test réussi ! Message reçu à {datetime.now().isoformat()}"
                        elif message_text.strip() == "":
                            logger.info("📎 Message sans texte (probablement une pièce jointe)")
                            response_text = "📎 J'ai reçu votre message mais je ne peux traiter que du texte pour le moment."
                        else:
                            response_text = f"📨 Message reçu: {message_text}\n⏰ Traité à: {datetime.now().strftime('%H:%M:%S')}"
                        
                        # Envoyer la réponse
                        send_result = send_message(sender_id, response_text)
                        logger.info(f"📤 Résultat d'envoi: {send_result}")
                    
                    # Traiter les postbacks (boutons)
                    elif 'postback' in messaging_event:
                        postback_data = messaging_event['postback']
                        payload = postback_data.get('payload', '')
                        title = postback_data.get('title', '')
                        
                        logger.info(f"🔲 Postback reçu de {sender_id}:")
                        logger.info(f"   - Payload: {payload}")
                        logger.info(f"   - Title: {title}")
                        
                        response_text = f"🔲 Bouton cliqué: {title}\n📋 Payload: {payload}"
                        send_result = send_message(sender_id, response_text)
                        logger.info(f"📤 Résultat d'envoi postback: {send_result}")
                    
                    # Traiter les livraisons de messages
                    elif 'delivery' in messaging_event:
                        logger.info(f"✅ Confirmation de livraison reçue pour {sender_id}")
                    
                    # Traiter les lectures de messages
                    elif 'read' in messaging_event:
                        logger.info(f"👁️ Confirmation de lecture reçue pour {sender_id}")
                    
                    else:
                        logger.warning(f"❓ Type d'événement inconnu: {list(messaging_event.keys())}")
                        
        except json.JSONDecodeError as e:
            logger.error(f"❌ Erreur de parsing JSON: {str(e)}")
            return jsonify({"error": "Invalid JSON"}), 400
        except Exception as e:
            logger.error(f"❌ Erreur lors du traitement du webhook: {str(e)}")
            logger.error(f"❌ Type d'erreur: {type(e).__name__}")
            import traceback
            logger.error(f"❌ Traceback: {traceback.format_exc()}")
            return jsonify({"error": "Error processing request", "details": str(e)}), 500
            
        return jsonify({"status": "ok", "processed_at": datetime.now().isoformat()}), 200

def send_message(recipient_id, text):
    """Envoie un message à un utilisateur Facebook avec débogage complet"""
    logger.info(f"📤 Tentative d'envoi de message à {recipient_id}")
    logger.info(f"📤 Texte à envoyer: '{text}'")
    
    if not PAGE_ACCESS_TOKEN:
        logger.error("❌ PAGE_ACCESS_TOKEN manquant pour l'envoi")
        return {"success": False, "error": "Missing access token"}
    
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
        "messaging_type": "RESPONSE"
    }
    
    logger.info(f"📤 URL d'envoi: {url}")
    logger.info(f"📤 Paramètres: access_token=[MASQUÉ]")
    logger.info(f"📤 Headers: {headers}")
    logger.info(f"📤 Données: {json.dumps(data, indent=2)}")
    
    try:
        response = requests.post(url, params=params, headers=headers, json=data, timeout=10)
        
        logger.info(f"📤 Réponse HTTP: {response.status_code}")
        logger.info(f"📤 Headers de réponse: {dict(response.headers)}")
        
        try:
            response_data = response.json()
            logger.info(f"📤 Réponse JSON: {json.dumps(response_data, indent=2)}")
        except:
            logger.info(f"📤 Réponse texte: {response.text}")
        
        if response.status_code == 200:
            logger.info(f"✅ Message envoyé avec succès à {recipient_id}")
            return {"success": True, "status_code": response.status_code}
        else:
            logger.error(f"❌ Erreur d'envoi: HTTP {response.status_code}")
            logger.error(f"❌ Détails: {response.text}")
            return {"success": False, "status_code": response.status_code, "error": response.text}
            
    except requests.exceptions.Timeout as e:
        logger.error(f"⏰ Timeout lors de l'envoi: {str(e)}")
        return {"success": False, "error": "Timeout"}
    except requests.exceptions.ConnectionError as e:
        logger.error(f"🌐 Erreur de connexion: {str(e)}")
        return {"success": False, "error": "Connection error"}
    except requests.exceptions.RequestException as e:
        logger.error(f"📡 Erreur de requête: {str(e)}")
        return {"success": False, "error": str(e)}

@app.route("/health", methods=['GET'])
def health_check():
    """Endpoint de santé détaillé pour Render"""
    health_data = {
        "status": "healthy",
        "bot": "NakamaBot",
        "timestamp": datetime.now().isoformat(),
        "config": {
            "verify_token_set": bool(VERIFY_TOKEN),
            "page_token_set": bool(PAGE_ACCESS_TOKEN),
            "page_token_length": len(PAGE_ACCESS_TOKEN) if PAGE_ACCESS_TOKEN else 0
        },
        "environment": {
            "port": os.environ.get("PORT", "5000"),
            "python_version": os.sys.version,
            "flask_version": getattr(__import__('flask'), '__version__', 'unknown')
        }
    }
    
    logger.info(f"🏥 Health check effectué: {json.dumps(health_data, indent=2)}")
    return jsonify(health_data), 200

@app.route("/test-send/<recipient_id>/<message>", methods=['GET'])
def test_send(recipient_id, message):
    """Endpoint de test pour envoyer un message manuellement"""
    logger.info(f"🧪 Test d'envoi manuel à {recipient_id}: {message}")
    result = send_message(recipient_id, f"🧪 Test manuel: {message}")
    return jsonify(result)

# Gestionnaire d'erreurs global
@app.errorhandler(Exception)
def handle_exception(e):
    logger.error(f"💥 Erreur non gérée: {str(e)}")
    logger.error(f"💥 Type: {type(e).__name__}")
    import traceback
    logger.error(f"💥 Traceback: {traceback.format_exc()}")
    return jsonify({"error": "Internal server error", "details": str(e)}), 500

if __name__ == "__main__":
    # Configuration pour le déploiement avec logs de démarrage
    port = int(os.environ.get("PORT", 5000))
    
    logger.info("🚀 Démarrage de NakamaBot...")
    logger.info(f"🌐 Port: {port}")
    logger.info(f"🔑 VERIFY_TOKEN défini: {bool(VERIFY_TOKEN)}")
    logger.info(f"🔑 PAGE_ACCESS_TOKEN défini: {bool(PAGE_ACCESS_TOKEN)}")
    
    if PAGE_ACCESS_TOKEN:
        logger.info(f"🔑 Longueur du token: {len(PAGE_ACCESS_TOKEN)}")
        logger.info(f"🔑 Token commence par: {PAGE_ACCESS_TOKEN[:10]}...")
    
    app.run(host="0.0.0.0", port=port, debug=False)
