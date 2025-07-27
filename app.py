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
import importlib.util
import glob
import sys

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
    """Charger dynamiquement toutes les commandes - VERSION CORRIGÉE"""
    global COMMANDS
    COMMANDS = {}
    
    # Obtenir le répertoire de travail actuel (pas forcément le même que le script)
    current_dir = os.getcwd()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    logger.info(f"🔍 Répertoire de travail: {current_dir}")
    logger.info(f"🔍 Répertoire du script: {script_dir}")
    
    # Lister tous les fichiers et dossiers pour debug
    logger.info("📁 Contenu du répertoire de travail:")
    try:
        for item in os.listdir(current_dir):
            item_path = os.path.join(current_dir, item)
            if os.path.isdir(item_path):
                logger.info(f"  📁 {item}/")
                # Lister le contenu des sous-dossiers
                try:
                    sub_items = os.listdir(item_path)
                    if sub_items:
                        logger.info(f"    📋 Contenu: {', '.join(sub_items[:10])}")  # Limiter à 10 items
                except:
                    pass
            else:
                logger.info(f"  📄 {item}")
    except Exception as e:
        logger.error(f"❌ Erreur listing répertoire: {e}")
    
    # Chercher le dossier de commandes dans différents endroits
    possible_dirs = ["Commandes", "commandes", "Commands", "commands"]
    search_paths = [current_dir, script_dir]
    
    commands_dir = None
    
    for base_path in search_paths:
        for dir_name in possible_dirs:
            full_path = os.path.join(base_path, dir_name)
            logger.info(f"🔍 Vérification: {full_path}")
            
            if os.path.exists(full_path) and os.path.isdir(full_path):
                commands_dir = full_path
                logger.info(f"✅ Dossier de commandes trouvé: {full_path}")
                break
        
        if commands_dir:
            break
    
    if not commands_dir:
        logger.error(f"❌ Aucun dossier de commandes trouvé!")
        logger.error(f"🔍 Chemins vérifiés:")
        for base_path in search_paths:
            for dir_name in possible_dirs:
                logger.error(f"  - {os.path.join(base_path, dir_name)}")
        
        # Créer une commande de base par défaut
        COMMANDS['help'] = lambda sender_id, args: "🌟 Dossier de commandes non trouvé! Vérifiez votre structure de fichiers. ⚡"
        return
    
    # Ajouter le répertoire parent au sys.path
    parent_dir = os.path.dirname(commands_dir)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
        logger.info(f"📦 Ajouté au sys.path: {parent_dir}")
    
    # Créer un __init__.py s'il n'existe pas
    init_file = os.path.join(commands_dir, "__init__.py")
    if not os.path.exists(init_file):
        try:
            with open(init_file, 'w') as f:
                f.write("# Auto-generated __init__.py for commands\n")
            logger.info(f"✅ Créé {init_file}")
        except Exception as e:
            logger.warning(f"⚠️ Impossible de créer __init__.py: {e}")
    
    # Trouver tous les fichiers Python dans le dossier Commandes
    command_files = []
    try:
        for file_name in os.listdir(commands_dir):
            if file_name.endswith('.py') and file_name != '__init__.py':
                file_path = os.path.join(commands_dir, file_name)
                if os.path.isfile(file_path):
                    command_files.append(file_path)
                    logger.info(f"📄 Fichier de commande trouvé: {file_name}")
    except Exception as e:
        logger.error(f"❌ Erreur lecture dossier commandes: {e}")
        return
    
    logger.info(f"📦 {len(command_files)} fichiers de commandes trouvés")
    
    if not command_files:
        logger.warning("⚠️ Aucun fichier .py trouvé dans le dossier de commandes")
        # Créer une commande de base
        COMMANDS['help'] = lambda sender_id, args: "🌟 Aucune commande trouvée! Ajoutez des fichiers .py dans le dossier Commandes/ ⚡"
        return
    
    loaded_count = 0
    
    for file_path in command_files:
        try:
            # Extraire le nom de la commande du nom de fichier
            command_name = os.path.basename(file_path)[:-3]  # Enlever .py
            
            logger.info(f"🔄 Chargement de la commande: {command_name}")
            
            # Vérifier que le fichier n'est pas vide
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if not content:
                        logger.warning(f"⚠️ Fichier vide ignoré: {command_name}")
                        continue
            except Exception as e:
                logger.error(f"❌ Erreur lecture fichier {command_name}: {e}")
                continue
            
            # Créer un nom de module unique pour éviter les conflits
            module_name = f"commands.{command_name}"
            
            # Supprimer le module s'il existe déjà
            if module_name in sys.modules:
                del sys.modules[module_name]
            
            # Charger le module
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None or spec.loader is None:
                logger.error(f"❌ Impossible de créer spec pour {command_name}")
                continue
            
            module = importlib.util.module_from_spec(spec)
            
            # Injecter les variables globales et fonctions nécessaires
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
            module.send_image_message = send_image_message
            module.logger = logger
            module.datetime = datetime
            module.random = random
            module.requests = requests
            module.time = time
            module.os = os
            module.json = json
            
            # Exécuter le module
            spec.loader.exec_module(module)
            
            # Ajouter le module au sys.modules pour éviter les reimports
            sys.modules[module_name] = module
            
            # Chercher la fonction execute dans le module
            if hasattr(module, 'execute'):
                COMMANDS[command_name] = module.execute
                loaded_count += 1
                logger.info(f"✅ Commande '{command_name}' chargée avec succès")
            else:
                logger.warning(f"⚠️ Pas de fonction 'execute' dans {command_name}")
                
        except Exception as e:
            logger.error(f"❌ Erreur chargement {command_name}: {e}")
            import traceback
            logger.error(f"📋 Traceback: {traceback.format_exc()}")
    
    logger.info(f"📊 {loaded_count}/{len(command_files)} commandes chargées avec succès")
    logger.info(f"📋 Commandes disponibles: {list(COMMANDS.keys())}")
    
    # Ajouter une commande help par défaut si elle n'existe pas
    if 'help' not in COMMANDS:
        def default_help(sender_id, args):
            commands_text = ", ".join([f"/{cmd}" for cmd in sorted(COMMANDS.keys())])
            return f"🌟 Commandes disponibles:\n{commands_text}\n\n✨ NakamaBot v3.0 by Durand ⚡"
        
        COMMANDS['help'] = default_help
        logger.info("✅ Commande help par défaut ajoutée")

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
            import traceback
            logger.error(f"📋 Traceback: {traceback.format_exc()}")
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
        "commands_list": list(COMMANDS.keys()),
        "users": len(user_list),
        "conversations": len(user_memory),
        "active_games": len(game_sessions),
        "admins": len(ADMIN_IDS),
        "version": "3.0",
        "last_update": datetime.now().isoformat(),
        "endpoints": ["/", "/webhook", "/stats", "/health"],
        "features": ["Chat IA", "Histoires", "Jeu Action/Vérité", "Mémoire", "Images AI"],
        "working_directory": os.getcwd(),
        "script_directory": os.path.dirname(os.path.abspath(__file__))
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
            import traceback
            logger.error(f"📋 Traceback: {traceback.format_exc()}")
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
        "commands_list": list(COMMANDS.keys()),
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
        "timestamp": datetime.now().isoformat(),
        "commands_loaded": list(COMMANDS.keys()),
        "filesystem_info": {
            "working_dir": os.getcwd(),
            "script_dir": os.path.dirname(os.path.abspath(__file__))
        }
    }
    
    # Vérifier la santé
    issues = []
    if not MISTRAL_API_KEY:
        issues.append("Clé IA manquante")
    if not PAGE_ACCESS_TOKEN:
        issues.append("Token Facebook manquant")
    if len(COMMANDS) == 0:
        issues.append("Aucune commande chargée")
    
    if issues:
        health_status["status"] = "degraded"
        health_status["issues"] = issues
    
    status_code = 200 if health_status["status"] == "healthy" else 503
    return jsonify(health_status), status_code

# Route pour recharger les commandes (utile pour le développement)
@app.route("/reload-commands", methods=['POST'])
def reload_commands():
    """Recharger les commandes (pour admin uniquement si configuré)"""
    try:
        old_count = len(COMMANDS)
        load_commands()
        new_count = len(COMMANDS)
        
        return jsonify({
            "status": "success",
            "message": f"Commandes rechargées: {old_count} -> {new_count}",
            "commands": list(COMMANDS.keys())
        })
    except Exception as e:
        logger.error(f"❌ Erreur rechargement commandes: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

# Route de debug pour explorer le système de fichiers
@app.route("/debug/filesystem", methods=['GET'])
def debug_filesystem():
    """Route de debug pour explorer le système de fichiers"""
    try:
        current_dir = os.getcwd()
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Lister le contenu du répertoire de travail
        current_content = []
        try:
            for item in os.listdir(current_dir):
                item_path = os.path.join(current_dir, item)
                is_dir = os.path.isdir(item_path)
                current_content.append({
                    "name": item,
                    "type": "directory" if is_dir else "file",
                    "path": item_path
                })
        except Exception as e:
            current_content = [{"error": str(e)}]
        
        return jsonify({
            "working_directory": current_dir,
            "script_directory": script_dir,
            "current_directory_content": current_content,
            "python_path": sys.path[:5],  # Premier 5 éléments
            "loaded_commands": list(COMMANDS.keys())
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
    
    if len(COMMANDS) == 0:
        logger.warning("⚠️ Aucune commande chargée! Vérifiez votre dossier de commandes.")
    
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
