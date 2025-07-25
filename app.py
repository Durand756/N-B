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

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "nakamaverifytoken")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
JSONBIN_API_KEY = os.getenv("JSONBIN_API_KEY", "")
JSONBIN_BIN_ID = os.getenv("JSONBIN_BIN_ID", "")  # Optionnel
ADMIN_IDS = set(id.strip() for id in os.getenv("ADMIN_IDS", "").split(",") if id.strip())

# Mémoire et état du jeu
user_memory = defaultdict(lambda: deque(maxlen=10))
user_list = set()
game_sessions = {}  # Pour le jeu Action ou Vérité

class JSONBinStorage:
    """Classe pour gérer le stockage JSONBin.io"""
    
    def __init__(self, api_key, bin_id=None):
        self.api_key = api_key
        self.bin_id = bin_id
        self.base_url = "https://api.jsonbin.io/v3"
        self.headers = {
            "Content-Type": "application/json",
            "X-Master-Key": api_key
        }
    
    def create_bin(self, initial_data=None):
        """Créer un nouveau bin JSONBin"""
        data = initial_data or {
            'user_memory': {},
            'user_list': [],
            'game_sessions': {},
            'timestamp': datetime.now().isoformat(),
            'version': '3.0',
            'creator': 'Durand'
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/b",
                headers=self.headers,
                json=data,
                timeout=15
            )
            
            if response.status_code == 200:
                result = response.json()
                self.bin_id = result['metadata']['id']
                logger.info(f"✅ Nouveau bin JSONBin créé: {self.bin_id}")
                # Sauvegarder le bin_id pour la prochaine fois
                logger.info(f"🔑 Ajoutez cette variable: JSONBIN_BIN_ID={self.bin_id}")
                return True
            else:
                logger.error(f"❌ Erreur création bin: {response.status_code} - {response.text}")
                return False
                
        except requests.RequestException as e:
            logger.error(f"❌ Erreur réseau création bin: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Erreur générale création bin: {e}")
            return False
    
    def save_data(self, data):
        """Sauvegarder les données sur JSONBin"""
        if not self.bin_id:
            logger.warning("Pas de bin_id, création automatique...")
            if not self.create_bin(data):
                return False
        
        # Ajouter métadonnées
        data_to_save = {
            **data,
            'timestamp': datetime.now().isoformat(),
            'version': '3.0',
            'creator': 'Durand'
        }
        
        try:
            response = requests.put(
                f"{self.base_url}/b/{self.bin_id}",
                headers=self.headers,
                json=data_to_save,
                timeout=15
            )
            
            if response.status_code == 200:
                logger.info("✅ Données sauvegardées sur JSONBin")
                return True
            else:
                logger.error(f"❌ Erreur sauvegarde: {response.status_code} - {response.text}")
                return False
                
        except requests.RequestException as e:
            logger.error(f"❌ Erreur réseau sauvegarde: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Erreur générale sauvegarde: {e}")
            return False
    
    def load_data(self):
        """Charger les données depuis JSONBin"""
        if not self.bin_id:
            logger.warning("Pas de bin_id configuré")
            return None
        
        try:
            response = requests.get(
                f"{self.base_url}/b/{self.bin_id}/latest",
                headers=self.headers,
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()['record']
                logger.info(f"✅ Données chargées depuis JSONBin (v{data.get('version', '1.0')})")
                return data
            else:
                logger.error(f"❌ Erreur chargement: {response.status_code} - {response.text}")
                return None
                
        except requests.RequestException as e:
            logger.error(f"❌ Erreur réseau chargement: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Erreur générale chargement: {e}")
            return None
    
    def get_bin_info(self):
        """Obtenir les infos du bin"""
        if not self.bin_id:
            return None
        
        try:
            response = requests.get(
                f"{self.base_url}/b/{self.bin_id}",
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                return response.json()['metadata']
            return None
        except:
            return None

# Initialiser le stockage JSONBin
storage = None

def init_jsonbin_storage():
    """Initialiser le stockage JSONBin"""
    global storage
    
    if not JSONBIN_API_KEY:
        logger.error("❌ JSONBIN_API_KEY manquante dans les variables d'environnement")
        return False
    
    try:
        storage = JSONBinStorage(JSONBIN_API_KEY, JSONBIN_BIN_ID)
        
        # Tester la connexion
        if JSONBIN_BIN_ID:
            test_data = storage.load_data()
            if test_data is not None:
                logger.info("✅ JSONBin connecté avec succès")
                return True
            else:
                logger.warning("⚠️ Bin ID invalide, création d'un nouveau bin...")
        
        # Créer un nouveau bin si nécessaire
        if storage.create_bin():
            logger.info("✅ JSONBin initialisé avec succès")
            return True
        else:
            logger.error("❌ Impossible d'initialiser JSONBin")
            return False
            
    except Exception as e:
        logger.error(f"❌ Erreur initialisation JSONBin: {e}")
        return False

def save_to_storage():
    """Sauvegarde vers JSONBin"""
    if not storage:
        logger.warning("Stockage JSONBin non initialisé")
        return False
    
    try:
        data = {
            'user_memory': {k: list(v) for k, v in user_memory.items()},
            'user_list': list(user_list),
            'game_sessions': game_sessions
        }
        
        return storage.save_data(data)
        
    except Exception as e:
        logger.error(f"❌ Erreur sauvegarde: {e}")
        return False

def load_from_storage():
    """Chargement depuis JSONBin"""
    global user_memory, user_list, game_sessions
    
    if not storage:
        logger.warning("Stockage JSONBin non initialisé")
        return False
    
    try:
        data = storage.load_data()
        if not data:
            logger.info("📁 Aucune donnée à charger")
            return False
        
        # Restaurer les données avec vérifications
        user_memory.clear()
        for user_id, messages in data.get('user_memory', {}).items():
            user_memory[user_id] = deque(messages, maxlen=10)
        
        user_list.clear()
        user_list.update(data.get('user_list', []))
        
        game_sessions.clear()
        game_sessions.update(data.get('game_sessions', {}))
        
        logger.info(f"📊 Chargé: {len(user_list)} utilisateurs, {len(user_memory)} conversations, {len(game_sessions)} jeux")
        return True
        
    except Exception as e:
        logger.error(f"❌ Erreur chargement: {e}")
        return False

def auto_save():
    """Sauvegarde automatique améliorée"""
    save_interval = 300  # 5 minutes
    logger.info(f"🔄 Auto-save JSONBin démarré (intervalle: {save_interval}s)")
    
    while True:
        time.sleep(save_interval)
        if user_memory or user_list or game_sessions:
            success = save_to_storage()
            status = "✅" if success else "❌"
            logger.info(f"🔄 Auto-save: {status}")

# API Mistral avec gestion améliorée
def call_mistral_api(messages, max_tokens=200, temperature=0.8):
    """Appel API Mistral optimisé"""
    if not MISTRAL_API_KEY:
        logger.warning("Clé API Mistral manquante")
        return None
    
    headers = {
        "Content-Type": "application/json", 
        "Authorization": f"Bearer {MISTRAL_API_KEY}"
    }
    data = {
        "model": "mistral-small-latest",  # Modèle plus récent
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
    """Ajouter à la mémoire avec sauvegarde async"""
    user_memory[user_id].append({
        'type': msg_type,
        'content': content,
        'timestamp': datetime.now().isoformat()
    })
    
    # Sauvegarde asynchrone non-bloquante
    if storage:
        threading.Thread(target=save_to_storage, daemon=True).start()

def get_memory_context(user_id):
    """Obtenir le contexte mémoire pour l'IA"""
    context = []
    for msg in user_memory.get(user_id, []):
        role = "user" if msg['type'] == 'user' else "assistant"
        context.append({"role": role, "content": msg['content']})
    return context

def is_admin(user_id):
    """Vérifier si l'utilisateur est admin"""
    return str(user_id) in ADMIN_IDS

def broadcast_message(text):
    """Diffuser un message à tous les utilisateurs"""
    success = 0
    errors = 0
    for user_id in user_list:
        result = send_message(user_id, text)
        if result.get("success"):
            success += 1
        else:
            errors += 1
    return {"sent": success, "total": len(user_list), "errors": errors}

# === COMMANDES DU BOT ===

def cmd_actionverite(sender_id, args=""):
    """Jeu Action ou Vérité"""
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

def cmd_start(sender_id, args=""):
    """Commande de démarrage"""
    messages = [{
        "role": "system",
        "content": "Tu es NakamaBot, créé par Durand. Tu es un bot otaku kawaii et énergique. Présente-toi avec joie en français, mentionne ton créateur Durand si on te le demande. Utilise des emojis anime. INTERDIT: aucune description d'action entre *étoiles*. Parle directement, maximum 300 caractères."
    }, {"role": "user", "content": "Présente-toi!"}]
    
    response = call_mistral_api(messages, max_tokens=150, temperature=0.9)
    return response or "🌟 Konnichiwa nakama! Je suis NakamaBot, créé par Durand! Ton compagnon otaku kawaii! ⚡ Tape /help pour découvrir mes pouvoirs! 🎌✨"

def cmd_ia(sender_id, args=""):
    """Chat IA libre"""
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
    """Générateur d'histoires"""
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
    """Générateur de waifu"""
    messages = [{
        "role": "system",
        "content": "Crée une waifu originale. Format: nom, âge, personnalité, apparence, hobby, citation. INTERDIT: descriptions d'actions entre *étoiles*. Présente directement, français, max 350 caractères."
    }, {"role": "user", "content": "Crée ma waifu!"}]
    
    response = call_mistral_api(messages, max_tokens=180, temperature=0.9)
    return f"👸✨ Voici ta waifu!\n\n{response}\n\n💕 Elle t'attend nakama!" if response else "👸 Akari-chan, 19 ans, tsundere aux cheveux roses! Adore la pâtisserie. 'B-baka! Ce n'est pas pour toi!' 💕"

def cmd_memory(sender_id, args=""):
    """Afficher la mémoire"""
    if not user_memory.get(sender_id):
        return "💾 Aucune conversation précédente! C'est notre premier échange! ✨"
    
    text = "💾🎌 MÉMOIRE DE NOS AVENTURES!\n\n"
    for i, msg in enumerate(user_memory[sender_id], 1):
        emoji = "🗨️" if msg['type'] == 'user' else "🤖"
        preview = msg['content'][:60] + "..." if len(msg['content']) > 60 else msg['content']
        text += f"{emoji} {i}. {preview}\n"
    
    text += f"\n💭 {len(user_memory[sender_id])}/10 messages"
    text += f"\n🌐 JSONBin: {'✅' if storage else '❌'}"
    
    # Ajouter info jeu si actif
    if sender_id in game_sessions:
        text += f"\n🎲 Jeu actif: {game_sessions[sender_id]['score']} pts"
    
    return text

def cmd_broadcast(sender_id, args=""):
    """Diffusion admin"""
    if not is_admin(sender_id):
        return f"🔐 Accès refusé! Admins seulement! ❌\nTon ID: {sender_id}"
    
    if not args.strip():
        return "📢 Usage: /broadcast [message]\n🔐 Commande admin"
    
    text = f"📢🎌 ANNONCE NAKAMA!\n\n{args}\n\n⚡ Message officiel de Durand 💖"
    result = broadcast_message(text)
    return f"📊 Envoyé à {result['sent']}/{result['total']} nakamas! (Erreurs: {result['errors']}) ✨"

def cmd_admin(sender_id, args=""):
    """Panneau admin"""
    if not is_admin(sender_id):
        return f"🔐 Accès refusé! ID: {sender_id}"
    
    if not args.strip():
        bin_info = storage.get_bin_info() if storage else None
        return f"""🔐 PANNEAU ADMIN v3.0
• /admin stats - Statistiques
• /admin save - Force sauvegarde
• /admin load - Recharge données
• /admin games - Stats jeux
• /admin jsonbin - Info JSONBin
• /broadcast [msg] - Diffusion

📊 ÉTAT:
JSONBin: {'✅' if storage else '❌'}
Bin ID: {storage.bin_id if storage else 'Non configuré'}
Utilisateurs: {len(user_list)}
Mémoire: {len(user_memory)}
Jeux actifs: {len(game_sessions)}"""
    
    action = args.strip().lower()
    
    if action == "stats":
        return f"""📊 STATISTIQUES COMPLÈTES
👥 Utilisateurs: {len(user_list)}
💾 Conversations: {len(user_memory)}
🎲 Jeux actifs: {len(game_sessions)}
🌐 JSONBin: {'✅' if storage else '❌'}
🔐 Admin ID: {sender_id}
👨‍💻 Créateur: Durand
📝 Version: 3.0 (JSONBin)"""
    
    elif action == "save":
        success = save_to_storage()
        return f"{'✅ Sauvegarde JSONBin réussie!' if success else '❌ Échec sauvegarde JSONBin!'}"
    
    elif action == "load":
        success = load_from_storage()
        return f"{'✅ Chargement JSONBin réussi!' if success else '❌ Échec chargement JSONBin!'}"
    
    elif action == "games":
        if not game_sessions:
            return "🎲 Aucun jeu actif!"
        
        text = "🎲 JEUX ACTIFS:\n"
        for user_id, session in game_sessions.items():
            score = session.get('score', 0)
            text += f"👤 {user_id}: {score} pts\n"
        return text
    
    elif action == "jsonbin":
        if not storage:
            return "❌ JSONBin non initialisé!"
        
        bin_info = storage.get_bin_info()
        if bin_info:
            return f"""🌐 INFO JSONBIN:
📦 Bin ID: {storage.bin_id}
📅 Créé: {bin_info.get('createdAt', 'N/A')}
🔄 Modifié: {bin_info.get('updatedAt', 'N/A')}
👤 Privé: {'✅' if bin_info.get('private', True) else '❌'}"""
        else:
            return "❌ Impossible de récupérer les infos du bin"
    
    return f"❓ Action '{action}' inconnue!"

def cmd_help(sender_id, args=""):
    """Aide du bot"""
    commands = {
        "/start": "🌟 Présentation du bot",
        "/ia [message]": "🧠 Chat libre avec IA",
        "/story [theme]": "📖 Histoires anime/manga",
        "/waifu": "👸 Génère ta waifu",
        "/actionverite": "🎲 Jeu Action ou Vérité",
        "/memory": "💾 Voir l'historique",
        "/help": "❓ Cette aide"
    }
    
    text = "🎌⚡ NAKAMABOT v3.0 GUIDE! ⚡🎌\n\n"
    for cmd, desc in commands.items():
        text += f"{cmd} - {desc}\n"
    
    if is_admin(sender_id):
        text += "\n🔐 ADMIN:\n/admin - Panneau admin\n/broadcast - Diffusion"
    
    text += f"\n💾 JSONBin: {'✅' if storage else '❌'}"
    text += "\n👨‍💻 Créé par Durand"
    text += "\n⚡ Powered by Mistral AI!"
    text += "\n🆕 Nouveau: Stockage JSONBin.io! 💖"
    return text

# Dictionnaire des commandes
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
    """Traiter les commandes utilisateur"""
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
    """Envoyer un message Facebook"""
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

# === ROUTES FLASK ===

@app.route("/", methods=['GET'])
def home():
    """Route d'accueil avec informations"""
    bin_info = storage.get_bin_info() if storage else None
    
    return jsonify({
        "status": "🎌 NakamaBot v3.0 Online! ⚡",
        "creator": "Durand",
        "storage": "JSONBin.io",
        "commands": len(COMMANDS),
        "users": len(user_list),
        "conversations": len(user_memory),
        "active_games": len(game_sessions),
        "jsonbin_connected": bool(storage),
        "bin_id": storage.bin_id if storage else None,
        "admins": len(ADMIN_IDS),
        "version": "3.0",
        "last_update": datetime.now().isoformat()
    })

@app.route("/webhook", methods=['GET', 'POST'])
def webhook():
    """Webhook Facebook Messenger"""
    if request.method == 'GET':
        # Vérification du webhook
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        
        if mode == "subscribe" and token == VERIFY_TOKEN:
            logger.info("✅ Webhook vérifié avec succès")
            return challenge, 200
        else:
            logger.warning("❌ Échec vérification webhook")
            return "Verification failed", 403
        
    elif request.method == 'POST':
        try:
            data = request.get_json()
            
            if not data:
                return jsonify({"error": "No data received"}), 400
            
            # Traiter chaque entrée
            for entry in data.get('entry', []):
                for event in entry.get('messaging', []):
                    sender_id = event.get('sender', {}).get('id')
                    
                    if not sender_id:
                        continue
                    
                    # Ignorer les messages echo du bot
                    if 'message' in event and not event['message'].get('is_echo'):
                        # Ajouter l'utilisateur à la liste
                        user_list.add(sender_id)
                        
                        # Récupérer le texte du message
                        message_text = event['message'].get('text', '').strip()
                        
                        if message_text:  # Ignorer les messages vides
                            # Ajouter à la mémoire
                            add_to_memory(sender_id, 'user', message_text)
                            
                            # Traiter la commande
                            response = process_command(sender_id, message_text)
                            
                            # Ajouter la réponse à la mémoire
                            add_to_memory(sender_id, 'bot', response)
                            
                            # Envoyer la réponse
                            send_result = send_message(sender_id, response)
                            
                            if not send_result.get("success"):
                                logger.warning(f"Échec envoi message à {sender_id}")
                        
        except Exception as e:
            logger.error(f"Erreur webhook: {e}")
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
        "storage_type": "JSONBin.io",
        "storage_connected": bool(storage),
        "version": "3.0",
        "creator": "Durand"
    })

@app.route("/health", methods=['GET'])
def health():
    """Route de santé pour monitoring"""
    health_status = {
        "status": "healthy",
        "jsonbin": bool(storage),
        "mistral": bool(MISTRAL_API_KEY),
        "facebook": bool(PAGE_ACCESS_TOKEN),
        "timestamp": datetime.now().isoformat()
    }
    
    # Vérifier la santé des services
    issues = []
    if not storage:
        issues.append("JSONBin non connecté")
    if not MISTRAL_API_KEY:
        issues.append("Clé Mistral manquante")
    if not PAGE_ACCESS_TOKEN:
        issues.append("Token Facebook manquant")
    
    if issues:
        health_status["status"] = "degraded"
        health_status["issues"] = issues
    
    return jsonify(health_status)

# === DÉMARRAGE DE L'APPLICATION ===

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    
    logger.info("🚀 Démarrage NakamaBot v3.0 avec JSONBin.io...")
    logger.info("👨‍💻 Créé par Durand")
    
    # Vérifier les variables d'environnement critiques
    missing_vars = []
    if not PAGE_ACCESS_TOKEN:
        missing_vars.append("PAGE_ACCESS_TOKEN")
    if not MISTRAL_API_KEY:
        missing_vars.append("MISTRAL_API_KEY")
    if not JSONBIN_API_KEY:
        missing_vars.append("JSONBIN_API_KEY")
    
    if missing_vars:
        logger.error(f"❌ Variables manquantes: {', '.join(missing_vars)}")
        logger.error("Le bot ne fonctionnera pas correctement!")
    
    # Initialiser JSONBin
    if init_jsonbin_storage():
        logger.info("📁 Tentative de chargement des données...")
        if load_from_storage():
            logger.info("✅ Données restaurées avec succès")
        else:
            logger.info("ℹ️  Démarrage avec données vides")
        
        # Démarrer la sauvegarde automatique
        threading.Thread(target=auto_save, daemon=True).start()
        logger.info("💾 Sauvegarde automatique JSONBin activée")
    else:
        logger.warning("⚠️  Fonctionnement sans sauvegarde JSONBin")
    
    # Afficher les informations de configuration
    logger.info(f"🎌 {len(COMMANDS)} commandes chargées")
    logger.info(f"🔐 {len(ADMIN_IDS)} admins configurés")
    
    if storage and storage.bin_id:
        logger.info(f"📦 Bin JSONBin: {storage.bin_id}")
    
    logger.info(f"🌐 Serveur démarrant sur le port {port}")
    logger.info("🎯 Endpoints disponibles:")
    logger.info("   • GET  / - Informations du bot")
    logger.info("   • GET  /stats - Statistiques")
    logger.info("   • GET  /health - Santé du système")
    logger.info("   • POST /webhook - Webhook Facebook")
    
    # Démarrer l'application Flask
    app.run(
        host="0.0.0.0", 
        port=port, 
        debug=False,
        threaded=True
    )
