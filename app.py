import os
import logging
import json
import random
from flask import Flask, request, jsonify
import requests
from datetime import datetime
from collections import defaultdict, deque
import threading
import time
import importlib
import glob

# Configuration du logging 
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "nakamaverifytoken")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
ADMIN_IDS = set(id.strip() for id in os.getenv("ADMIN_IDS", "").split(",") if id.strip())

# Mémoire et état du jeu (variables globales accessibles aux commandes)
user_memory = defaultdict(lambda: deque(maxlen=10))
user_list = set()
game_sessions = {}

# Dictionnaire des commandes chargées dynamiquement
COMMANDS = {}

def call_mistral_api(messages, max_tokens=200, temperature=0.8):
    """API Mistral avec retry amélioré"""
    if not MISTRAL_API_KEY:
        return None
    
    headers = {
        "Content-Type": "application/json", 
        "Authorization": f"Bearer {MISTRAL_API_KEY}"
    }
    data = {
        "model": "mistral-small-latest",
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature
    }
    
    for attempt in range(2):
        try:
            response = requests.post(
                "https://api.mistral.ai/v1/chat/completions", 
                headers=headers, 
                json=data, 
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
            elif response.status_code == 401:
                logger.error("❌ Clé API Mistral invalide")
                return None
            else:
                if attempt == 0:
                    time.sleep(2)
                    continue
                return None
                
        except Exception as e:
            if attempt == 0:
                time.sleep(2)
                continue
            logger.error(f"❌ Erreur Mistral: {e}")
            return None
    
    return None

def add_to_memory(user_id, msg_type, content):
    """Ajouter à la mémoire"""
    if not user_id or not msg_type or not content:
        return
    
    # Limiter la taille
    if len(content) > 2000:
        content = content[:1900] + "...[tronqué]"
    
    user_memory[str(user_id)].append({
        'type': msg_type,
        'content': content,
        'timestamp': datetime.now().isoformat()
    })

def get_memory_context(user_id):
    """Obtenir le contexte mémoire"""
    context = []
    for msg in user_memory.get(str(user_id), []):
        role = "user" if msg['type'] == 'user' else "assistant"
        context.append({"role": role, "content": msg['content']})
    return context

def is_admin(user_id):
    """Vérifier admin"""
    return str(user_id) in ADMIN_IDS

def broadcast_message(text):
    """Diffusion de messages avec protection contre les envois multiples"""
    if not text or not user_list:
        return {"sent": 0, "total": 0, "errors": 0}
    
    success = 0
    errors = 0
    total_users = len(user_list)
    
    logger.info(f"📢 Début broadcast vers {total_users} utilisateurs")
    
    for user_id in list(user_list):
        try:
            if not user_id or not str(user_id).strip():
                continue
                
            # Petite pause pour éviter de spam l'API Facebook
            time.sleep(0.3)
            
            result = send_message(str(user_id), text)
            if result.get("success"):
                success += 1
                logger.debug(f"✅ Broadcast envoyé à {user_id}")
            else:
                errors += 1
                logger.warning(f"❌ Échec broadcast pour {user_id}: {result.get('error', 'Unknown')}")
                
        except Exception as e:
            errors += 1
            logger.error(f"❌ Erreur broadcast pour {user_id}: {e}")
    
    logger.info(f"📊 Broadcast terminé: {success} succès, {errors} erreurs")
    return {
        "sent": success, 
        "total": total_users, 
        "errors": errors
    }

def send_image_message(recipient_id, image_url, caption=""):
    """Envoyer une image via Facebook Messenger"""
    if not PAGE_ACCESS_TOKEN:
        logger.error("❌ PAGE_ACCESS_TOKEN manquant")
        return {"success": False, "error": "No token"}
    
    if not image_url:
        logger.warning("⚠️ URL d'image vide")
        return {"success": False, "error": "Empty image URL"}
    
    # Structure pour envoyer une image
    data = {
        "recipient": {"id": str(recipient_id)},
        "message": {
            "attachment": {
                "type": "image",
                "payload": {
                    "url": image_url,
                    "is_reusable": True
                }
            }
        }
    }
    
    try:
        # Envoyer l'image
        response = requests.post(
            "https://graph.facebook.com/v18.0/me/messages",
            params={"access_token": PAGE_ACCESS_TOKEN},
            json=data,
            timeout=20
        )
        
        if response.status_code == 200:
            # Si il y a une caption, l'envoyer séparément
            if caption:
                time.sleep(0.5)  # Petit délai
                return send_message(recipient_id, caption)
            return {"success": True}
        else:
            logger.error(f"❌ Erreur envoi image: {response.status_code} - {response.text}")
            return {"success": False, "error": f"API Error {response.status_code}"}
            
    except Exception as e:
        logger.error(f"❌ Erreur envoi image: {e}")
        return {"success": False, "error": str(e)}

def load_commands():
    """Charger dynamiquement toutes les commandes depuis le dossier Commandes/"""
    global COMMANDS
    COMMANDS = {}
    
    commands_dir = "Commandes"
    if not os.path.exists(commands_dir):
        logger.error(f"❌ Dossier {commands_dir} introuvable!")
        return
    
    # Trouver tous les fichiers Python dans le dossier Commandes
    command_files = glob.glob(f"{commands_dir}/*.py")
    
    for file_path in command_files:
        try:
            # Extraire le nom de la commande du nom de fichier
            command_name = os.path.basename(file_path)[:-3]  # Enlever .py
            
            # Importer le module
            module_name = f"{commands_dir}.{command_name}"
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            module = importlib.util.module_from_spec(spec)
            
            # Rendre les variables globales disponibles au module
            module.user_memory = user_memory
            module.user_list = user_list
            module.game_sessions = game_sessions
            module.ADMIN_IDS = ADMIN_IDS
            module.call_mistral_api = call_mistral_api
            module.add_to_memory = add_to_memory
            module.get_memory_context = get_memory_context
            module.is_admin = is_admin
            module.broadcast_message = broadcast_message
            module.send_message = lambda recipient_id, text: send_message(recipient_id, text)
            module.logger = logger
            module.datetime = datetime
            module.random = random
            module.requests = requests
            module.time = time
            
            spec.loader.exec_module(module)
            
            # Chercher la fonction execute dans le module
            if hasattr(module, 'execute'):
                COMMANDS[command_name] = module.execute
                logger.info(f"✅ Commande {command_name} chargée")
            else:
                logger.warning(f"⚠️ Pas de fonction 'execute' dans {command_name}")
                
        except Exception as e:
            logger.error(f"❌ Erreur chargement {command_name}: {e}")
    
    logger.info(f"📦 {len(COMMANDS)} commandes chargées")

def process_command(sender_id, message_text):
    """Traiter les commandes utilisateur avec validation"""
    sender_id = str(sender_id)
    
    if not message_text or not isinstance(message_text, str):
        return "🌟 Message vide! Tape /start ou /help! ✨"
    
    message_text = message_text.strip()
    
    if not message_text.startswith('/'):
        # Si pas de commande, utiliser la commande ai par défaut
        if 'ai' in COMMANDS:
            return COMMANDS['ai'](sender_id, message_text)
        else:
            return "🌟 Konnichiwa! Tape /start ou /help! ✨"
    
    parts = message_text[1:].split(' ', 1)
    command = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""
    
    if command in COMMANDS:
        try:
            return COMMANDS[command](sender_id, args)
        except Exception as e:
            logger.error(f"❌ Erreur commande {command}: {e}")
            return f"💥 Erreur dans /{command}! Retry! 🔄"
    
    return f"❓ Commande /{command} inconnue! Tape /help! ⚡"

def send_message(recipient_id, text):
    """Envoyer un message Facebook avec validation"""
    if not PAGE_ACCESS_TOKEN:
        logger.error("❌ PAGE_ACCESS_TOKEN manquant")
        return {"success": False, "error": "No token"}
    
    if not text or not isinstance(text, str):
        logger.warning("⚠️ Tentative d'envoi de message vide")
        return {"success": False, "error": "Empty message"}
    
    # Limiter la taille du message
    if len(text) > 2000:
        text = text[:1950] + "...\n✨ Message tronqué! 💫"
    
    data = {
        "recipient": {"id": str(recipient_id)},
        "message": {"text": text}
    }
    
    try:
        response = requests.post(
            "https://graph.facebook.com/v18.0/me/messages",
            params={"access_token": PAGE_ACCESS_TOKEN},
            json=data,
            timeout=15
        )
        
        if response.status_code == 200:
            return {"success": True}
        else:
            logger.error(f"❌ Erreur Facebook API: {response.status_code} - {response.text}")
            return {"success": False, "error": f"API Error {response.status_code}"}
            
    except Exception as e:
        logger.error(f"❌ Erreur envoi message: {e}")
        return {"success": False, "error": str(e)}

# === ROUTES FLASK ===

@app.route("/", methods=['GET'])
def home():
    """Route d'accueil avec informations détaillées"""
    return jsonify({
        "status": "🎌 NakamaBot v3.0 Online! ⚡",
        "creator": "Durand",
        "commands": len(COMMANDS),
        "users": len(user_list),
        "conversations": len(user_memory),
        "active_games": len(game_sessions),
        "admins": len(ADMIN_IDS),
        "version": "3.0",
        "last_update": datetime.now().isoformat(),
        "endpoints": ["/", "/webhook", "/stats", "/health"],
        "features": ["Chat IA", "Histoires", "Jeu Action/Vérité", "Mémoire", "Images AI"]
    })

@app.route("/webhook", methods=['GET', 'POST'])
def webhook():
    """Webhook Facebook Messenger avec gestion d'erreurs améliorée"""
    if request.method == 'GET':
        # Vérification du webhook
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        
        if mode == "subscribe" and token == VERIFY_TOKEN:
            logger.info("✅ Webhook vérifié avec succès")
            return challenge, 200
        else:
            logger.warning(f"❌ Échec vérification webhook")
            return "Verification failed", 403
        
    elif request.method == 'POST':
        try:
            data = request.get_json()
            
            if not data:
                logger.warning("⚠️ Aucune donnée reçue")
                return jsonify({"error": "No data received"}), 400
            
            # Traiter chaque entrée
            for entry in data.get('entry', []):
                for event in entry.get('messaging', []):
                    sender_id = event.get('sender', {}).get('id')
                    
                    if not sender_id:
                        continue
                    
                    sender_id = str(sender_id)
                    
                    # Traiter les messages non-echo
                    if 'message' in event and not event['message'].get('is_echo'):
                        # Ajouter l'utilisateur
                        user_list.add(sender_id)
                        
                        # Récupérer le texte
                        message_text = event['message'].get('text', '').strip()
                        
                        if message_text:
                            logger.info(f"📨 Message de {sender_id}: {message_text[:50]}...")
                            
                            # Ajouter à la mémoire
                            add_to_memory(sender_id, 'user', message_text)
                            
                            # Traiter la commande
                            response = process_command(sender_id, message_text)

                            if response:
                                # Vérifier si c'est une réponse image
                                if isinstance(response, dict) and response.get("type") == "image":
                                    # Envoyer l'image
                                    send_result = send_image_message(sender_id, response["url"], response["caption"])
                                    
                                    # Ajouter à la mémoire
                                    add_to_memory(sender_id, 'bot', f"Image envoyée: {response['caption'][:50]}...")
                                    
                                    if send_result.get("success"):
                                        logger.info(f"✅ Image envoyée à {sender_id}")
                                    else:
                                        logger.warning(f"❌ Échec envoi image à {sender_id}")
                                        # Fallback: envoyer juste le texte
                                        send_message(sender_id, "🎨 Image générée mais erreur d'envoi! Retry /image! ⚡")
                                else:
                                    # Réponse texte normale
                                    add_to_memory(sender_id, 'bot', response)
                                    send_result = send_message(sender_id, response)
                                    
                                    if send_result.get("success"):
                                        logger.info(f"✅ Réponse envoyée à {sender_id}")
                                    else:
                                        logger.warning(f"❌ Échec envoi message à {sender_id}")
                            
        except Exception as e:
            logger.error(f"❌ Erreur webhook: {e}")
            return jsonify({"error": f"Webhook error: {str(e)}"}), 500
            
        return jsonify({"status": "ok"}), 200

@app.route("/stats", methods=['GET'])
def stats():
    """Route des statistiques publiques"""
    return jsonify({
        "users_count": len(user_list),
        "conversations_count": len(user_memory),
        "active_games": len(game_sessions),
        "commands_available": len(COMMANDS),
        "version": "3.0",
        "creator": "Durand"
    })

@app.route("/health", methods=['GET'])
def health():
    """Route de santé pour monitoring"""
    health_status = {
        "status": "healthy",
        "services": {
            "ai": bool(MISTRAL_API_KEY),
            "facebook": bool(PAGE_ACCESS_TOKEN)
        },
        "data": {
            "users": len(user_list),
            "conversations": len(user_memory),
            "games": len(game_sessions),
            "commands": len(COMMANDS)
        },
        "timestamp": datetime.now().isoformat()
    }
    
    # Vérifier la santé
    issues = []
    if not MISTRAL_API_KEY:
        issues.append("Clé IA manquante")
    if not PAGE_ACCESS_TOKEN:
        issues.append("Token Facebook manquant")
    
    if issues:
        health_status["status"] = "degraded"
        health_status["issues"] = issues
    
    status_code = 200 if health_status["status"] == "healthy" else 503
    return jsonify(health_status), status_code

# === DÉMARRAGE DE L'APPLICATION ===

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    
    logger.info("🚀 Démarrage NakamaBot v3.0...")
    logger.info("👨‍💻 Créé par Durand")
    
    # Vérifier les variables d'environnement
    missing_vars = []
    if not PAGE_ACCESS_TOKEN:
        missing_vars.append("PAGE_ACCESS_TOKEN")
    if not MISTRAL_API_KEY:
        missing_vars.append("MISTRAL_API_KEY")
    
    if missing_vars:
        logger.error(f"❌ Variables manquantes: {', '.join(missing_vars)}")
        logger.error("🔧 Le bot ne fonctionnera pas correctement!")
    else:
        logger.info("✅ Variables d'environnement OK")
    
    # Charger les commandes
    logger.info("📦 Chargement des commandes...")
    load_commands()
    
    logger.info(f"🔐 {len(ADMIN_IDS)} administrateurs configurés")
    logger.info(f"🌐 Serveur Flask démarrant sur le port {port}")
    logger.info("🎉 NakamaBot prêt à servir!")
    
    # Démarrer Flask
    try:
        app.run(
            host="0.0.0.0", 
            port=port, 
            debug=False,
            threaded=True
        )
    except KeyboardInterrupt:
        logger.info("🛑 Arrêt du bot demandé")
        logger.info("👋 Sayonara nakamas!")
    except Exception as e:
        logger.error(f"❌ Erreur critique: {e}")
        raise
