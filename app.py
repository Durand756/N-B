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

# Mémoire
user_memory = defaultdict(lambda: deque(maxlen=10))
user_list = set()
drive_service = None

# Initialisation Google Drive depuis JSON
def init_google_drive():
    global drive_service
    try:
        # Lire le fichier drive.json
        with open('drive.json', 'r') as f:
            credentials_info = json.load(f)
        
        scopes = ['https://www.googleapis.com/auth/drive.file']
        credentials = Credentials.from_service_account_info(credentials_info, scopes=scopes)
        drive_service = build('drive', 'v3', credentials=credentials)
        
        # Test de connexion
        drive_service.about().get(fields="user").execute()
        logger.info("✅ Google Drive connecté")
        return True
    except Exception as e:
        logger.error(f"❌ Erreur Google Drive: {e}")
        return False

# Sauvegarde sur Drive
def save_to_drive():
    if not drive_service:
        return False
    try:
        data = {
            'user_memory': {k: list(v) for k, v in user_memory.items()},
            'user_list': list(user_list),
            'timestamp': datetime.now().isoformat()
        }
        
        json_data = json.dumps(data, indent=2, ensure_ascii=False)
        media = MediaIoBaseUpload(io.BytesIO(json_data.encode('utf-8')), mimetype='application/json')
        
        # Rechercher fichier existant
        results = drive_service.files().list(q="name='nakamabot_memory.json'").execute()
        files = results.get('files', [])
        
        if files:
            # Mettre à jour
            drive_service.files().update(fileId=files[0]['id'], media_body=media).execute()
        else:
            # Créer nouveau
            file_metadata = {'name': 'nakamabot_memory.json'}
            drive_service.files().create(body=file_metadata, media_body=media).execute()
        
        logger.info("💾 Sauvegarde Drive réussie")
        return True
    except Exception as e:
        logger.error(f"❌ Erreur sauvegarde: {e}")
        return False

# Chargement depuis Drive
def load_from_drive():
    global user_memory, user_list
    if not drive_service:
        return False
    try:
        results = drive_service.files().list(q="name='nakamabot_memory.json'").execute()
        files = results.get('files', [])
        
        if not files:
            logger.info("📁 Aucune sauvegarde trouvée")
            return False
        
        request_download = drive_service.files().get_media(fileId=files[0]['id'])
        file_stream = io.BytesIO()
        downloader = MediaIoBaseDownload(file_stream, request_download)
        
        done = False
        while not done:
            status, done = downloader.next_chunk()
        
        file_stream.seek(0)
        data = json.loads(file_stream.read().decode('utf-8'))
        
        # Restaurer données
        user_memory.clear()
        for user_id, messages in data.get('user_memory', {}).items():
            user_memory[user_id] = deque(messages, maxlen=10)
        
        user_list.update(data.get('user_list', []))
        logger.info("✅ Données chargées depuis Drive")
        return True
    except Exception as e:
        logger.error(f"❌ Erreur chargement: {e}")
        return False

# Sauvegarde automatique
def auto_save():
    while True:
        time.sleep(300)  # 5 minutes
        if user_memory or user_list:
            save_to_drive()

# API Mistral avec restrictions sur les descriptions
def call_mistral_api(messages, max_tokens=200, temperature=0.8):
    if not MISTRAL_API_KEY:
        return None
    
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {MISTRAL_API_KEY}"}
    data = {
        "model": "mistral-medium",
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature
    }
    
    try:
        response = requests.post("https://api.mistral.ai/v1/chat/completions", 
                               headers=headers, json=data, timeout=30)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"Erreur Mistral: {e}")
    return None

def add_to_memory(user_id, msg_type, content):
    user_memory[user_id].append({
        'type': msg_type,
        'content': content,
        'timestamp': datetime.now().isoformat()
    })
    # Sauvegarde asynchrone
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
    for user_id in user_list:
        if send_message(user_id, text).get("success"):
            success += 1
    return {"sent": success, "total": len(user_list)}

# Commandes simplifiées
def cmd_start(sender_id, args=""):
    messages = [{
        "role": "system",
        "content": "Tu es NakamaBot, un bot otaku kawaii. Présente-toi avec énergie en français. Utilise des emojis anime. INTERDIT: aucune description d'action entre *étoiles* ou **gras**. Parle directement, maximum 300 caractères."
    }, {"role": "user", "content": "Présente-toi!"}]
    
    response = call_mistral_api(messages, max_tokens=150, temperature=0.9)
    return response or "🌟 Konnichiwa nakama! Je suis NakamaBot, ton compagnon otaku! ⚡ Tape /help pour mes commandes! 🎌"

def cmd_ia(sender_id, args=""):
    if not args.strip():
        topics = [
            "Quel est ton anime préféré?",
            "Raconte-moi ton personnage d'anime favori!",
            "Manga ou anime? Et pourquoi? 🤔"
        ]
        return f"💭 {random.choice(topics)} ✨"
    
    context = get_memory_context(sender_id)
    messages = [{
        "role": "system", 
        "content": "Tu es NakamaBot, IA otaku kawaii. Réponds en français avec des emojis anime. STRICTEMENT INTERDIT: aucune description d'action entre *étoiles*, **gras** ou autre. Parle directement comme un vrai personnage, maximum 400 caractères."
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
        "content": f"Conteur otaku. {'Continue l\'histoire' if has_story else 'Nouvelle histoire'} {theme}. Style anime/manga. INTERDIT: descriptions d'actions entre *étoiles*. Raconte directement, maximum 500 caractères."
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
    return text

def cmd_broadcast(sender_id, args=""):
    if not is_admin(sender_id):
        return f"🔐 Accès refusé! Admins seulement! ❌\nTon ID: {sender_id}"
    
    if not args.strip():
        return "📢 Usage: /broadcast [message]\n🔐 Commande admin"
    
    text = f"📢🎌 ANNONCE NAKAMA!\n\n{args}\n\n⚡ Message officiel 💖"
    result = broadcast_message(text)
    return f"📊 Envoyé à {result['sent']}/{result['total']} nakamas! ✨"

def cmd_admin(sender_id, args=""):
    if not is_admin(sender_id):
        return f"🔐 Accès refusé! ID: {sender_id}"
    
    if not args.strip():
        return f"""🔐 PANNEAU ADMIN
• /admin stats - Statistiques
• /admin save - Force sauvegarde
• /admin load - Recharge Drive
• /broadcast [msg] - Diffusion

Drive: {'✅' if drive_service else '❌'}
Utilisateurs: {len(user_list)}
Mémoire: {len(user_memory)}"""
    
    action = args.strip().lower()
    
    if action == "stats":
        return f"""📊 STATS ADMIN
👥 Utilisateurs: {len(user_list)}
💾 Mémoire: {len(user_memory)}
🌐 Drive: {'✅' if drive_service else '❌'}
🔐 Admin: {sender_id}"""
    
    elif action == "save":
        success = save_to_drive()
        return f"{'✅ Sauvegarde réussie!' if success else '❌ Échec sauvegarde!'}"
    
    elif action == "load":
        success = load_from_drive()
        return f"{'✅ Chargement réussi!' if success else '❌ Échec chargement!'}"
    
    return f"❓ Action '{action}' inconnue!"

def cmd_help(sender_id, args=""):
    commands = {
        "/start": "🌟 Présentation du bot",
        "/ia [message]": "🧠 Chat libre avec IA",
        "/story [theme]": "📖 Histoires anime/manga",
        "/waifu": "👸 Génère ta waifu",
        "/memory": "💾 Voir l'historique",
        "/help": "❓ Cette aide"
    }
    
    text = "🎌⚡ NAKAMABOT GUIDE! ⚡🎌\n\n"
    for cmd, desc in commands.items():
        text += f"{cmd} - {desc}\n"
    
    if is_admin(sender_id):
        text += "\n🔐 ADMIN:\n/admin - Panneau admin\n/broadcast - Diffusion"
    
    text += f"\n💾 Mémoire: {'✅' if drive_service else '❌'}"
    text += "\n⚡ Powered by Mistral AI! 💖"
    return text

# Dictionnaire des commandes
COMMANDS = {
    'start': cmd_start,
    'ia': cmd_ia,
    'story': cmd_story,
    'waifu': cmd_waifu,
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
        "commands": len(COMMANDS),
        "users": len(user_list),
        "drive": bool(drive_service),
        "admins": len(ADMIN_IDS)
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
    
    logger.info("🚀 Démarrage NakamaBot...")
    
    # Initialiser Google Drive
    if init_google_drive():
        load_from_drive()
        threading.Thread(target=auto_save, daemon=True).start()
        logger.info("💾 Sauvegarde automatique activée")
    
    logger.info(f"🎌 {len(COMMANDS)} commandes chargées")
    logger.info(f"🔐 {len(ADMIN_IDS)} admins configurés")
    
    app.run(host="0.0.0.0", port=port, debug=False)
