import os
import logging
import json
import random
from flask import Flask, request, jsonify
import requests
from datetime import datetime
from collections import defaultdict, deque
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
import io
import threading
import time

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "nakamaverifytoken")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
ADMIN_IDS = set(id.strip() for id in os.getenv("ADMIN_IDS", "").split(",") if id.strip())

# Mémoire et état du jeu
user_memory = defaultdict(lambda: deque(maxlen=10))
user_list = set()
drive_service = None
game_sessions = {}  # Pour le jeu Action ou Vérité

# Initialisation Google Drive depuis JSON
def init_google_drive():
    global drive_service
    try:
        # Lire le fichier Drive.json (avec D majuscule)
        with open('Drive.json', 'r', encoding='utf-8') as f:
            credentials_info = json.load(f)
        
        scopes = ['https://www.googleapis.com/auth/drive.file']
        credentials = Credentials.from_service_account_info(credentials_info, scopes=scopes)
        drive_service = build('drive', 'v3', credentials=credentials)
        
        # Test de connexion
        drive_service.about().get(fields="user").execute()
        logger.info("✅ Google Drive connecté avec succès")
        return True
    except FileNotFoundError:
        logger.error("❌ Fichier Drive.json introuvable")
        return False
    except json.JSONDecodeError:
        logger.error("❌ Erreur format JSON dans Drive.json")
        return False
    except Exception as e:
        logger.error(f"❌ Erreur Google Drive: {e}")
        return False

# Sauvegarde améliorée sur Drive
def save_to_drive():
    if not drive_service:
        logger.warning("Drive non initialisé - sauvegarde ignorée")
        return False
    
    try:
        # Préparer les données à sauver
        data = {
            'user_memory': {k: list(v) for k, v in user_memory.items()},
            'user_list': list(user_list),
            'game_sessions': game_sessions,
            'timestamp': datetime.now().isoformat(),
            'version': '2.0'
        }
        
        # Convertir en JSON avec encodage UTF-8
        json_data = json.dumps(data, indent=2, ensure_ascii=False)
        media = MediaIoBaseUpload(
            io.BytesIO(json_data.encode('utf-8')), 
            mimetype='application/json',
            resumable=True
        )
        
        # Rechercher fichier existant
        results = drive_service.files().list(
            q="name='nakamabot_memory.json' and trashed=false"
        ).execute()
        files = results.get('files', [])
        
        if files:
            # Mettre à jour le fichier existant
            updated_file = drive_service.files().update(
                fileId=files[0]['id'], 
                media_body=media
            ).execute()
            logger.info(f"💾 Sauvegarde Drive mise à jour - ID: {updated_file['id']}")
        else:
            # Créer nouveau fichier
            file_metadata = {
                'name': 'nakamabot_memory.json',
                'description': 'Données de sauvegarde NakamaBot'
            }
            created_file = drive_service.files().create(
                body=file_metadata, 
                media_body=media
            ).execute()
            logger.info(f"💾 Nouveau fichier Drive créé - ID: {created_file['id']}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Erreur sauvegarde Drive: {e}")
        return False

# Chargement amélioré depuis Drive
def load_from_drive():
    global user_memory, user_list, game_sessions
    
    if not drive_service:
        logger.warning("Drive non initialisé - chargement ignoré")
        return False
    
    try:
        # Rechercher le fichier de sauvegarde
        results = drive_service.files().list(
            q="name='nakamabot_memory.json' and trashed=false"
        ).execute()
        files = results.get('files', [])
        
        if not files:
            logger.info("📁 Aucune sauvegarde trouvée sur Drive")
            return False
        
        # Télécharger le fichier
        request_download = drive_service.files().get_media(fileId=files[0]['id'])
        file_stream = io.BytesIO()
        downloader = MediaIoBaseDownload(file_stream, request_download)
        
        done = False
        while not done:
            status, done = downloader.next_chunk()
        
        # Lire et parser les données
        file_stream.seek(0)
        data = json.loads(file_stream.read().decode('utf-8'))
        
        # Restaurer les données avec vérifications
        user_memory.clear()
        for user_id, messages in data.get('user_memory', {}).items():
            user_memory[user_id] = deque(messages, maxlen=10)
        
        user_list.clear()
        user_list.update(data.get('user_list', []))
        
        game_sessions.clear()
        game_sessions.update(data.get('game_sessions', {}))
        
        logger.info(f"✅ Données chargées depuis Drive - Version: {data.get('version', '1.0')}")
        logger.info(f"📊 {len(user_list)} utilisateurs, {len(user_memory)} conversations")
        return True
        
    except json.JSONDecodeError as e:
        logger.error(f"❌ Erreur format JSON lors du chargement: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Erreur chargement Drive: {e}")
        return False

# Sauvegarde automatique améliorée
def auto_save():
    save_interval = 300  # 5 minutes
    logger.info(f"🔄 Sauvegarde automatique démarrée (intervalle: {save_interval}s)")
    
    while True:
        time.sleep(save_interval)
        if user_memory or user_list or game_sessions:
            success = save_to_drive()
            if success:
                logger.info("🔄 Sauvegarde automatique réussie")
            else:
                logger.warning("⚠️ Échec sauvegarde automatique")

# API Mistral avec gestion améliorée
def call_mistral_api(messages, max_tokens=200, temperature=0.8):
    if not MISTRAL_API_KEY:
        logger.warning("Clé API Mistral manquante")
        return None
    
    headers = {
        "Content-Type": "application/json", 
        "Authorization": f"Bearer {MISTRAL_API_KEY}"
    }
    data = {
        "model": "mistral-medium",
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature
    }
    
    try:
        response = requests.post(
            "https://api.mistral.ai/v1/chat/completions", 
            headers=headers, 
            json=data, 
            timeout=30
        )
        
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        else:
            logger.error(f"Erreur API Mistral: {response.status_code}")
            return None
            
    except requests.RequestException as e:
        logger.error(f"Erreur réseau Mistral: {e}")
        return None
    except Exception as e:
        logger.error(f"Erreur générale Mistral: {e}")
        return None

def add_to_memory(user_id, msg_type, content):
    user_memory[user_id].append({
        'type': msg_type,
        'content': content,
        'timestamp': datetime.now().isoformat()
    })
    # Sauvegarde asynchrone non-bloquante
    if drive_service:
        threading.Thread(target=save_to_drive, daemon=True).start()

def get_memory_context(user_id):
    context = []
    for msg in user_memory.get(user_id, []):
        role = "user" if msg['type'] == 'user' else "assistant"
        context.append({"role": role, "content": msg['content']})
    return context

def is_admin(user_id):
    return str(user_id) in ADMIN_IDS

def broadcast_message(text):
    success = 0
    errors = 0
    for user_id in user_list:
        result = send_message(user_id, text)
        if result.get("success"):
            success += 1
        else:
            errors += 1
    return {"sent": success, "total": len(user_list), "errors": errors}

# Nouveau jeu Action ou Vérité
def cmd_actionverite(sender_id, args=""):
    if not args.strip():
        return """🎲🎌 JEU ACTION OU VÉRITÉ! 🎌🎲

🎯 /actionverite start - Commencer
🎯 /actionverite action - Défi action
🎯 /actionverite verite - Question vérité
🎯 /actionverite stop - Arrêter

⚡ Prêt pour l'aventure nakama? ✨"""
    
    action = args.strip().lower()
    
    if action == "start":
        game_sessions[sender_id] = {
            'active': True,
            'score': 0,
            'started': datetime.now().isoformat()
        }
        return "🎲✨ JEU LANCÉ! Tu es prêt nakama?\n🎯 /actionverite action ou /actionverite verite? ⚡"
    
    elif action == "stop":
        if sender_id in game_sessions:
            score = game_sessions[sender_id].get('score', 0)
            del game_sessions[sender_id]
            return f"🏁 Jeu terminé! Score final: {score} points! Arigatou nakama! 🎌✨"
        return "🤔 Aucun jeu en cours! Tape /actionverite start! ⚡"
    
    elif action == "action":
        if sender_id not in game_sessions:
            return "🎲 Pas de jeu actif! Tape /actionverite start d'abord! ✨"
        
        actions = [
            "Fais 10 pompes en criant 'NAKAMA POWER!' 💪",
            "Chante l'opening de ton anime préféré! 🎵",
            "Imite ton personnage d'anime favori pendant 1 minute! 🎭",
            "Dessine ton waifu/husbando en 30 secondes! ✏️",
            "Fais une danse otaku pendant 30 secondes! 💃",
            "Récite les noms de 10 animes sans t'arrêter! 📚",
            "Prends une pose héroïque et crie ton attaque spéciale! ⚡",
            "Mange quelque chose avec des baguettes comme un ninja! 🥢"
        ]
        
        game_sessions[sender_id]['score'] += 1
        selected_action = random.choice(actions)
        return f"🎯 ACTION DÉFI!\n\n{selected_action}\n\n⏰ Tu as relevé le défi? Bien joué nakama! +1 point! ✨"
    
    elif action == "verite":
        if sender_id not in game_sessions:
            return "🎲 Pas de jeu actif! Tape /actionverite start d'abord! ✨"
        
        verites = [
            "Quel anime t'a fait pleurer le plus? 😭",
            "Avoue: tu as déjà essayé de faire un jutsu en vrai? 🥷",
            "C'est quoi ton ship le plus embarrassant? 💕",
            "Tu préfères les tsundere ou les yandere? Et pourquoi? 🤔",
            "Quel personnage d'anime ressemble le plus à toi? �mirror",
            "Quel est ton guilty pleasure anime? 😳",
            "Tu as déjà rêvé d'être dans un anime? Lequel? 💭",
            "Quelle réplique d'anime tu cites le plus souvent? 💬"
        ]
        
        game_sessions[sender_id]['score'] += 1
        selected_verite = random.choice(verites)
        return f"💭 VÉRITÉ QUESTION!\n\n{selected_verite}\n\n🤗 Merci pour ta sincérité nakama! +1 point! ✨"
    
    return "❓ Action inconnue! Utilise: start, action, verite, ou stop! 🎲"

# Commandes existantes avec améliorations
def cmd_start(sender_id, args=""):
    messages = [{
        "role": "system",
        "content": "Tu es NakamaBot, créé par Durand. Tu es un bot otaku kawaii et énergique. Présente-toi avec joie en français, mentionne ton créateur Durand si on te le demande. Utilise des emojis anime. INTERDIT: aucune description d'action entre *étoiles*. Parle directement, maximum 300 caractères."
    }, {"role": "user", "content": "Présente-toi!"}]
    
    response = call_mistral_api(messages, max_tokens=150, temperature=0.9)
    return response or "🌟 Konnichiwa nakama! Je suis NakamaBot, créé par Durand! Ton compagnon otaku kawaii! ⚡ Tape /help pour découvrir mes pouvoirs! 🎌✨"

def cmd_ia(sender_id, args=""):
    if not args.strip():
        topics = [
            "Quel est ton anime préféré? 🎌",
            "Raconte-moi ton personnage d'anime favori! ⭐",
            "Manga ou anime? Et pourquoi? 🤔",
            "Qui est ton créateur au fait? 👨‍💻"
        ]
        return f"💭 {random.choice(topics)} ✨"
    
    # Vérifier si on demande le créateur
    if any(word in args.lower() for word in ['créateur', 'createur', 'qui t\'a', 'qui t\'a créé', 'maker', 'developer']):
        return "🎌 Mon créateur est Durand! C'est lui qui m'a donné vie pour être votre nakama otaku! ✨👨‍💻 Il est génial, non? 💖"
    
    context = get_memory_context(sender_id)
    messages = [{
        "role": "system", 
        "content": "Tu es NakamaBot, créé par Durand. IA otaku kawaii. Réponds en français avec des emojis anime. Si on demande ton créateur, c'est Durand. STRICTEMENT INTERDIT: aucune description d'action entre *étoiles*. Parle directement comme un vrai personnage, maximum 400 caractères."
    }]
    messages.extend(context)
    messages.append({"role": "user", "content": args})
    
    response = call_mistral_api(messages, max_tokens=200, temperature=0.8)
    return f"💖 {response}" if response else "💭 Mon cerveau otaku bug! Retry onegaishimasu! 🥺"

def cmd_story(sender_id, args=""):
    theme = args.strip() or "isekai"
    context = get_memory_context(sender_id)
    has_story = any("📖" in msg.get("content", "") for msg in context)
    
    messages = [{
        "role": "system",
        "content": f"Conteur otaku créé par Durand. {'Continue l\'histoire' if has_story else 'Nouvelle histoire'} {theme}. Style anime/manga. INTERDIT: descriptions d'actions entre *étoiles*. Raconte directement, maximum 500 caractères."
    }]
    
    if has_story:
        messages.extend(context)
    messages.append({"role": "user", "content": f"Histoire {theme}!"})
    
    response = call_mistral_api(messages, max_tokens=250, temperature=0.9)
    prefix = "🔄 SUITE" if has_story else "📖 NOUVELLE HISTOIRE"
    return f"{prefix} {theme.upper()}!\n\n{response}\n\n✨ Tape /story pour la suite!" if response else "📖 Histoire en cours de création... Retry! ⚡"

def cmd_waifu(sender_id, args=""):
    messages = [{
        "role": "system",
        "content": "Crée une waifu originale. Format: nom, âge, personnalité, apparence, hobby, citation. INTERDIT: descriptions d'actions entre *étoiles*. Présente directement, français, max 350 caractères."
    }, {"role": "user", "content": "Crée ma waifu!"}]
    
    response = call_mistral_api(messages, max_tokens=180, temperature=0.9)
    return f"👸✨ Voici ta waifu!\n\n{response}\n\n💕 Elle t'attend nakama!" if response else "👸 Akari-chan, 19 ans, tsundere aux cheveux roses! Adore la pâtisserie. 'B-baka! Ce n'est pas pour toi!' 💕"

def cmd_memory(sender_id, args=""):
    if not user_memory.get(sender_id):
        return "💾 Aucune conversation précédente! C'est notre premier échange! ✨"
    
    text = "💾🎌 MÉMOIRE DE NOS AVENTURES!\n\n"
    for i, msg in enumerate(user_memory[sender_id], 1):
        emoji = "🗨️" if msg['type'] == 'user' else "🤖"
        preview = msg['content'][:60] + "..." if len(msg['content']) > 60 else msg['content']
        text += f"{emoji} {i}. {preview}\n"
    
    text += f"\n💭 {len(user_memory[sender_id])}/10 messages"
    text += f"\n🌐 Drive: {'✅' if drive_service else '❌'}"
    
    # Ajouter info jeu si actif
    if sender_id in game_sessions:
        text += f"\n🎲 Jeu actif: {game_sessions[sender_id]['score']} pts"
    
    return text

def cmd_broadcast(sender_id, args=""):
    if not is_admin(sender_id):
        return f"🔐 Accès refusé! Admins seulement! ❌\nTon ID: {sender_id}"
    
    if not args.strip():
        return "📢 Usage: /broadcast [message]\n🔐 Commande admin"
    
    text = f"📢🎌 ANNONCE NAKAMA!\n\n{args}\n\n⚡ Message officiel de Durand 💖"
    result = broadcast_message(text)
    return f"📊 Envoyé à {result['sent']}/{result['total']} nakamas! (Erreurs: {result['errors']}) ✨"

def cmd_admin(sender_id, args=""):
    if not is_admin(sender_id):
        return f"🔐 Accès refusé! ID: {sender_id}"
    
    if not args.strip():
        return f"""🔐 PANNEAU ADMIN
• /admin stats - Statistiques
• /admin save - Force sauvegarde
• /admin load - Recharge Drive
• /admin games - Stats jeux
• /broadcast [msg] - Diffusion

Drive: {'✅' if drive_service else '❌'}
Utilisateurs: {len(user_list)}
Mémoire: {len(user_memory)}
Jeux actifs: {len(game_sessions)}"""
    
    action = args.strip().lower()
    
    if action == "stats":
        return f"""📊 STATS ADMIN
👥 Utilisateurs: {len(user_list)}
💾 Mémoire: {len(user_memory)}
🎲 Jeux actifs: {len(game_sessions)}
🌐 Drive: {'✅' if drive_service else '❌'}
🔐 Admin: {sender_id}
👨‍💻 Créateur: Durand"""
    
    elif action == "save":
        success = save_to_drive()
        return f"{'✅ Sauvegarde réussie!' if success else '❌ Échec sauvegarde!'}"
    
    elif action == "load":
        success = load_from_drive()
        return f"{'✅ Chargement réussi!' if success else '❌ Échec chargement!'}"
    
    elif action == "games":
        if not game_sessions:
            return "🎲 Aucun jeu actif!"
        
        text = "🎲 JEUX ACTIFS:\n"
        for user_id, session in game_sessions.items():
            score = session.get('score', 0)
            text += f"👤 {user_id}: {score} pts\n"
        return text
    
    return f"❓ Action '{action}' inconnue!"

def cmd_help(sender_id, args=""):
    commands = {
        "/start": "🌟 Présentation du bot",
        "/ia [message]": "🧠 Chat libre avec IA",
        "/story [theme]": "📖 Histoires anime/manga",
        "/waifu": "👸 Génère ta waifu",
        "/actionverite": "🎲 Jeu Action ou Vérité",
        "/memory": "💾 Voir l'historique",
        "/help": "❓ Cette aide"
    }
    
    text = "🎌⚡ NAKAMABOT GUIDE! ⚡🎌\n\n"
    for cmd, desc in commands.items():
        text += f"{cmd} - {desc}\n"
    
    if is_admin(sender_id):
        text += "\n🔐 ADMIN:\n/admin - Panneau admin\n/broadcast - Diffusion"
    
    text += f"\n💾 Drive: {'✅' if drive_service else '❌'}"
    text += "\n👨‍💻 Créé par Durand"
    text += "\n⚡ Powered by Mistral AI! 💖"
    return text

# Dictionnaire des commandes mis à jour
COMMANDS = {
    'start': cmd_start,
    'ia': cmd_ia,
    'story': cmd_story,
    'waifu': cmd_waifu,
    'actionverite': cmd_actionverite,
    'memory': cmd_memory,
    'broadcast': cmd_broadcast,
    'admin': cmd_admin,
    'help': cmd_help
}

def process_command(sender_id, message_text):
    if not message_text.startswith('/'):
        return cmd_ia(sender_id, message_text) if message_text.strip() else "🎌 Konnichiwa! Tape /start ou /help! ✨"
    
    parts = message_text[1:].split(' ', 1)
    command = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""
    
    if command in COMMANDS:
        try:
            return COMMANDS[command](sender_id, args)
        except Exception as e:
            logger.error(f"Erreur commande {command}: {e}")
            return f"💥 Erreur dans /{command}! Retry onegaishimasu! 🥺"
    
    return f"❓ Commande /{command} inconnue! Tape /help! ⚡"

def send_message(recipient_id, text):
    if not PAGE_ACCESS_TOKEN:
        return {"success": False, "error": "No token"}
    
    if len(text) > 2000:
        text = text[:1950] + "...\n✨ Message tronqué! 💫"
    
    data = {
        "recipient": {"id": recipient_id},
        "message": {"text": text}
    }
    
    try:
        response = requests.post(
            "https://graph.facebook.com/v18.0/me/messages",
            params={"access_token": PAGE_ACCESS_TOKEN},
            json=data,
            timeout=10
        )
        return {"success": response.status_code == 200}
    except Exception as e:
        logger.error(f"Erreur envoi: {e}")
        return {"success": False}

# Routes Flask
@app.route("/", methods=['GET'])
def home():
    return jsonify({
        "status": "🎌 NakamaBot Online! ⚡",
        "creator": "Durand",
        "commands": len(COMMANDS),
        "users": len(user_list),
        "active_games": len(game_sessions),
        "drive": bool(drive_service),
        "admins": len(ADMIN_IDS),
        "version": "2.0"
    })

@app.route("/webhook", methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        
        if mode == "subscribe" and token == VERIFY_TOKEN:
            return challenge, 200
        return "Verification failed", 403
        
    elif request.method == 'POST':
        try:
            data = request.get_json()
            for entry in data.get('entry', []):
                for event in entry.get('messaging', []):
                    sender_id = event.get('sender', {}).get('id')
                    
                    if 'message' in event and not event['message'].get('is_echo'):
                        user_list.add(sender_id)
                        message_text = event['message'].get('text', '').strip()
                        
                        add_to_memory(sender_id, 'user', message_text)
                        response = process_command(sender_id, message_text)
                        add_to_memory(sender_id, 'bot', response)
                        
                        send_message(sender_id, response)
                        
        except Exception as e:
            logger.error(f"Erreur webhook: {e}")
            return jsonify({"error": str(e)}), 500
            
        return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    
    logger.info("🚀 Démarrage NakamaBot v2.0...")
    logger.info("👨‍💻 Créé par Durand")
    
    # Initialiser Google Drive avec le fichier Drive.json
    if init_google_drive():
        logger.info("📁 Tentative de chargement des données...")
        if load_from_drive():
            logger.info("✅ Données restaurées avec succès")
        else:
            logger.info("ℹ️  Démarrage avec données vides")
        
        # Démarrer la sauvegarde automatique
        threading.Thread(target=auto_save, daemon=True).start()
        logger.info("💾 Sauvegarde automatique activée")
    else:
        logger.warning("⚠️  Fonctionnement sans Google Drive")
    
    logger.info(f"🎌 {len(COMMANDS)} commandes chargées")
    logger.info(f"🔐 {len(ADMIN_IDS)} admins configurés")
    
    app.run(host="0.0.0.0", port=port, debug=False)
