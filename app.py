import os
import logging
import json
import random
import inspect
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
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# 🔑 Configuration
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "nakamaverifytoken")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")

# 🔐 Configuration Admin et Google Drive
ADMIN_IDS = set(os.getenv("ADMIN_IDS", "").split(","))  # IDs des admins séparés par virgules
GOOGLE_DRIVE_CREDENTIALS = os.getenv("GOOGLE_DRIVE_CREDENTIALS", "")  # JSON des credentials
DRIVE_FOLDER_ID = os.getenv("DRIVE_FOLDER_ID", "")  # ID du dossier Drive

# 💾 SYSTÈME DE MÉMOIRE
user_memory = defaultdict(lambda: deque(maxlen=10))  # Garde les 10 derniers messages par user
user_list = set()  # Liste des utilisateurs pour broadcast

# 🌐 Service Google Drive
drive_service = None

def init_google_drive():
    """Initialise le service Google Drive"""
    global drive_service
    
    if not GOOGLE_DRIVE_CREDENTIALS or not DRIVE_FOLDER_ID:
        logger.warning("⚠️ Google Drive non configuré - Les données ne seront pas sauvegardées")
        return False
    
    try:
        # Parser les credentials JSON
        if GOOGLE_DRIVE_CREDENTIALS.startswith('{'):
            credentials_info = json.loads(GOOGLE_DRIVE_CREDENTIALS)
        else:
            # Si c'est un fichier
            with open(GOOGLE_DRIVE_CREDENTIALS, 'r') as f:
                credentials_info = json.load(f)
        
        # Créer les credentials
        credentials = Credentials.from_service_account_info(
            credentials_info,
            scopes=['https://www.googleapis.com/auth/drive']
        )
        
        # Créer le service
        drive_service = build('drive', 'v3', credentials=credentials)
        
        logger.info("✅ Google Drive initialisé avec succès")
        return True
        
    except Exception as e:
        logger.error(f"❌ Erreur initialisation Google Drive: {e}")
        return False

def save_memory_to_drive():
    """Sauvegarde la mémoire sur Google Drive"""
    if not drive_service:
        return False
    
    try:
        # Préparer les données à sauvegarder
        memory_data = {
            'user_memory': {},
            'user_list': list(user_list),
            'timestamp': datetime.now().isoformat()
        }
        
        # Convertir deque en list pour JSON
        for user_id, messages in user_memory.items():
            memory_data['user_memory'][user_id] = list(messages)
        
        # Créer le fichier JSON
        json_data = json.dumps(memory_data, indent=2, ensure_ascii=False)
        file_stream = io.StringIO(json_data)
        
        # Chercher si le fichier existe déjà
        filename = "nakamabot_memory.json"
        query = f"name='{filename}' and parents in '{DRIVE_FOLDER_ID}'"
        results = drive_service.files().list(q=query).execute()
        files = results.get('files', [])
        
        media = MediaIoBaseUpload(
            io.BytesIO(json_data.encode('utf-8')),
            mimetype='application/json'
        )
        
        if files:
            # Mettre à jour le fichier existant
            file_id = files[0]['id']
            drive_service.files().update(
                fileId=file_id,
                media_body=media
            ).execute()
            logger.info(f"💾 Mémoire mise à jour sur Drive (ID: {file_id})")
        else:
            # Créer un nouveau fichier
            file_metadata = {
                'name': filename,
                'parents': [DRIVE_FOLDER_ID]
            }
            file = drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            logger.info(f"💾 Nouvelle sauvegarde créée sur Drive (ID: {file.get('id')})")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Erreur sauvegarde Drive: {e}")
        return False

def load_memory_from_drive():
    """Charge la mémoire depuis Google Drive"""
    global user_memory, user_list
    
    if not drive_service:
        return False
    
    try:
        # Chercher le fichier de mémoire
        filename = "nakamabot_memory.json"
        query = f"name='{filename}' and parents in '{DRIVE_FOLDER_ID}'"
        results = drive_service.files().list(q=query).execute()
        files = results.get('files', [])
        
        if not files:
            logger.info("📁 Aucune sauvegarde trouvée sur Drive")
            return False
        
        # Télécharger le fichier
        file_id = files[0]['id']
        request = drive_service.files().get_media(fileId=file_id)
        file_stream = io.BytesIO()
        downloader = MediaIoBaseDownload(file_stream, request)
        
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        
        # Parser les données
        file_stream.seek(0)
        memory_data = json.loads(file_stream.read().decode('utf-8'))
        
        # Restaurer la mémoire
        user_memory.clear()
        for user_id, messages in memory_data.get('user_memory', {}).items():
            user_memory[user_id] = deque(messages, maxlen=3)
        
        # Restaurer la liste d'utilisateurs
        user_list.update(memory_data.get('user_list', []))
        
        saved_time = memory_data.get('timestamp', 'Inconnu')
        logger.info(f"✅ Mémoire chargée depuis Drive - Sauvegarde du {saved_time}")
        logger.info(f"📊 {len(user_memory)} utilisateurs et {len(user_list)} contacts restaurés")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Erreur chargement Drive: {e}")
        return False

def auto_save_memory():
    """Sauvegarde automatique périodique"""
    def save_loop():
        while True:
            time.sleep(300)  # Sauvegarder toutes les 5 minutes
            if user_memory or user_list:
                success = save_memory_to_drive()
                if success:
                    logger.info("🔄 Sauvegarde automatique réussie")
    
    if drive_service:
        thread = threading.Thread(target=save_loop, daemon=True)
        thread.start()
        logger.info("🔄 Sauvegarde automatique activée (toutes les 5 min)")

# Validation des tokens
if not PAGE_ACCESS_TOKEN:
    logger.error("❌ PAGE_ACCESS_TOKEN is missing!")
else:
    logger.info(f"✅ PAGE_ACCESS_TOKEN configuré")

if not MISTRAL_API_KEY:
    logger.error("❌ MISTRAL_API_KEY is missing!")
else:
    logger.info("✅ MISTRAL_API_KEY configuré")

# Validation Admin
if ADMIN_IDS and list(ADMIN_IDS)[0]:  # Vérifier que ce n'est pas juste une chaîne vide
    logger.info(f"🔐 {len(ADMIN_IDS)} administrateurs configurés")
else:
    logger.warning("⚠️ Aucun administrateur configuré - Broadcast désactivé")

# Configuration Mistral API
MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"
MISTRAL_MODEL = "mistral-medium"  # ou "mistral-small" pour économiser

def call_mistral_api(messages, max_tokens=200, temperature=0.8):
    """Appel générique à l'API Mistral"""
    if not MISTRAL_API_KEY:
        return None
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {MISTRAL_API_KEY}"
    }
    
    data = {
        "model": MISTRAL_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature
    }
    
    try:
        response = requests.post(
            MISTRAL_API_URL,
            headers=headers,
            json=data,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            return result["choices"][0]["message"]["content"]
        else:
            logger.error(f"Erreur Mistral API: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Exception Mistral API: {e}")
        return None

def add_to_memory(user_id, message_type, content):
    """Ajoute un message à la mémoire de l'utilisateur et sauvegarde"""
    user_memory[user_id].append({
        'type': message_type,  # 'user' ou 'bot'
        'content': content,
        'timestamp': datetime.now().isoformat()
    })
    logger.info(f"💾 Mémoire {user_id}: {len(user_memory[user_id])} messages")
    
    # Sauvegarde asynchrone
    if drive_service:
        threading.Thread(target=save_memory_to_drive, daemon=True).start()

def get_memory_context(user_id):
    """Récupère le contexte des messages précédents"""
    if user_id not in user_memory or not user_memory[user_id]:
        return []
    
    context = []
    for msg in user_memory[user_id]:
        role = "user" if msg['type'] == 'user' else "assistant"
        context.append({
            "role": role,
            "content": msg['content']
        })
    
    return context

def is_admin(user_id):
    """Vérifie si un utilisateur est administrateur"""
    return str(user_id) in ADMIN_IDS

def broadcast_message(message_text):
    """Envoie un message à tous les utilisateurs connus"""
    success_count = 0
    total_users = len(user_list)
    
    logger.info(f"📢 Broadcast à {total_users} utilisateurs: {message_text}")
    
    for user_id in user_list.copy():  # Copie pour éviter les modifications pendant l'itération
        result = send_message(user_id, message_text)
        if result.get("success"):
            success_count += 1
        else:
            logger.warning(f"⚠️ Échec broadcast pour {user_id}")
    
    logger.info(f"📊 Broadcast terminé: {success_count}/{total_users} succès")
    return {"sent": success_count, "total": total_users}

# 🎭 Dictionnaire des commandes (auto-généré)
COMMANDS = {}

def command(name, description):
    """Décorateur pour enregistrer automatiquement les commandes"""
    def decorator(func):
        COMMANDS[name] = {
            'function': func,
            'description': description,
            'name': name
        }
        return func
    return decorator

# 🎌 SYSTÈME DE COMMANDES MODULAIRES 🎌

@command('start', '🌟 Présentation épique du bot en mode anime opening!')
def cmd_start(sender_id, message_text=""):
    """Présentation immersive style anime opening"""
    messages = [{
        "role": "system",
        "content": """Tu es NakamaBot, un bot otaku kawaii et énergique. Crée une présentation épique style anime opening en français, sans d'ecrire se que tu fais avec :
        - Beaucoup d'emojis anime/manga
        - Style énergique comme Luffy ou Naruto
        - Présente tes capacités de façon cool
        - Maximum 300 caractères
        - Termine par une phrase motivante d'anime"""
    }, {
        "role": "user", 
        "content": "Présente-toi de façon épique !"
    }]
    
    ai_response = call_mistral_api(messages, max_tokens=150, temperature=0.9)
    
    if ai_response:
        return f"🎌 {ai_response}\n\n✨ Tape /help pour découvrir toutes mes techniques secrètes, nakama! ⚡"
    else:
        return "🌟 Konnichiwa, nakama! Je suis NakamaBot! ⚡\n🎯 Ton compagnon otaku ultime pour parler anime, manga et bien plus!\n✨ Tape /help pour mes super pouvoirs! 🚀"

@command('ia', '🧠 Discussion libre avec une IA otaku kawaii (avec mémoire persistante!)')
def cmd_ia(sender_id, message_text=""):
    """Chat libre avec personnalité otaku et mémoire contextuelle"""
    # Si pas de texte, engage la conversation
    if not message_text.strip():
        topics = [
            "Quel est ton anime préféré de cette saison?",
            "Si tu pouvais être transporté dans un isekai, lequel choisirais-tu?",
            "Raconte-moi ton personnage d'anime favori!",
            "Manga ou anime? Et pourquoi? 🤔",
            "As-tu déjà rêvé d'avoir un stand de JoJo?"
        ]
        return f"💭 {random.choice(topics)} ✨"
    
    # Récupérer le contexte des messages précédents
    memory_context = get_memory_context(sender_id)
    
    # Construire les messages avec contexte
    messages = [{
        "role": "system",
        "content": """Tu es NakamaBot, une IA otaku kawaii et énergique. Tu as une mémoire persistante des conversations précédentes. Réponds en français sans d'ecrire se que tu fais avec:
        - Personnalité mélange de Nezuko (mignon), Megumin (dramatique), et Zero Two (taquine)
        - Beaucoup d'emojis anime
        - Références anime/manga naturelles
        - Style parfois tsundere ou badass selon le contexte
        - Utilise le contexte des messages précédents pour une conversation fluide
        - Maximum 400 caractères"""
    }]
    
    # Ajouter le contexte des messages précédents
    messages.extend(memory_context)
    
    # Ajouter le nouveau message
    messages.append({
        "role": "user",
        "content": message_text
    })
    
    ai_response = call_mistral_api(messages, max_tokens=200, temperature=0.8)
    
    if ai_response:
        return f"💖 {ai_response}"
    else:
        return "💭 Mon cerveau otaku bug un peu là... Retry, onegaishimasu! 🥺"

@command('story', '📖 Histoires courtes isekai/shonen sur mesure (avec suite persistante!)')
def cmd_story(sender_id, message_text=""):
    """Histoires courtes personnalisées avec continuité"""
    theme = message_text.strip() or "isekai"
    
    # Récupérer le contexte pour continuer une histoire
    memory_context = get_memory_context(sender_id)
    
    # Vérifier s'il y a une histoire en cours
    has_previous_story = any("📖" in msg.get("content", "") for msg in memory_context)
    
    messages = [{
        "role": "system",
        "content": f"""Tu es un conteur otaku. {'Continue l\'histoire précédente' if has_previous_story else 'Écris une nouvelle histoire'} {theme} sans d'ecrire se que tu fais avec :
        - Protagoniste attachant
        - Situation intéressante
        - Style anime/manga
        - {'Suite logique de l\'histoire' if has_previous_story else 'Début captivant'}
        - Maximum 500 caractères
        - Beaucoup d'action et d'émotion"""
    }]
    
    # Ajouter le contexte si histoire en cours
    if has_previous_story:
        messages.extend(memory_context)
    
    messages.append({
        "role": "user",
        "content": f"{'Continue l\'histoire' if has_previous_story else 'Raconte-moi une histoire'} {theme}!"
    })
    
    ai_response = call_mistral_api(messages, max_tokens=250, temperature=0.9)
    
    if ai_response:
        continuation_text = "🔄 SUITE" if has_previous_story else "📖⚡ NOUVELLE HISTOIRE"
        return f"{continuation_text} {theme.upper()}!\n\n{ai_response}\n\n✨ Tape /story pour la suite!"
    else:
        return "📖 Akira se réveille dans un monde magique où ses connaissances d'otaku deviennent des sorts! Son premier ennemi? Un démon qui déteste les animes! 'Maudit otaku!' crie-t-il. Akira sourit: 'KAMEHAMEHA!' ⚡✨"

@command('memory', '💾 Voir l\'historique persistant de nos conversations!')
def cmd_memory(sender_id, message_text=""):
    """Affiche la mémoire des conversations"""
    if sender_id not in user_memory or not user_memory[sender_id]:
        return "💾 Aucune conversation précédente, nakama! C'est notre premier échange! ✨"
    
    memory_text = "💾🎌 MÉMOIRE PERSISTANTE DE NOS AVENTURES!\n\n"
    
    for i, msg in enumerate(user_memory[sender_id], 1):
        emoji = "🗨️" if msg['type'] == 'user' else "🤖"
        content_preview = msg['content'][:80] + "..." if len(msg['content']) > 80 else msg['content']
        memory_text += f"{emoji} {i}. {content_preview}\n"
    
    memory_text += f"\n💭 {len(user_memory[sender_id])}/3 messages en mémoire"
    memory_text += "\n🌐 Sauvegardé sur Google Drive automatiquement!"
    memory_text += "\n✨ Je me souviens de tout, même après redémarrage!"
    
    return memory_text

@command('broadcast', '📢 [ADMIN ONLY] Envoie un message à tous les nakamas!')
def cmd_broadcast(sender_id, message_text=""):
    """Fonction broadcast sécurisée pour admins seulement"""
    # 🔐 VÉRIFICATION ADMIN OBLIGATOIRE
    if not is_admin(sender_id):
        return "🔐 Accès refusé! Seuls les admins peuvent utiliser cette commande, nakama! ❌\n✨ Tu n'as pas les permissions nécessaires."
    
    if not message_text.strip():
        return "📢 Usage: /broadcast [message]\n⚠️ Envoie à TOUS les utilisateurs!\n🔐 Commande admin seulement"
    
    # Message style NakamaBot avec signature admin
    broadcast_text = f"📢🎌 ANNONCE ADMIN NAKAMA!\n\n{message_text}\n\n⚡ - Message officiel des admins NakamaBot 💖"
    
    result = broadcast_message(broadcast_text)
    
    return f"📊 Broadcast admin envoyé à {result['sent']}/{result['total']} nakamas! ✨\n🔐 Action enregistrée comme admin."

@command('waifu', '👸 Génère ta waifu parfaite avec IA!')
def cmd_waifu(sender_id, message_text=""):
    """Génère une waifu unique"""
    messages = [{
        "role": "system",
        "content": """Crée une waifu originale sans d'ecrire se que tu fais avec :
        - Nom japonais mignon
        - Âge (18-25 ans)
        - Personnalité unique (kuudere, tsundere, dandere, etc.)
        - Apparence brève mais marquante
        - Hobby/talent spécial 
        - Une phrase qu'elle dirait
        Format en français, style kawaii, max 350 caractères"""
    }, {
        "role": "user",
        "content": "Crée ma waifu parfaite!"
    }]
    
    ai_response = call_mistral_api(messages, max_tokens=180, temperature=0.9)
    
    if ai_response:
        return f"👸✨ Voici ta waifu générée!\n\n{ai_response}\n\n💕 Elle t'attend, nakama!"
    else:
        return "👸 Akari-chan, 19 ans, tsundere aux cheveux roses! Elle adore la pâtisserie mais fait semblant de ne pas s'intéresser à toi... 'B-baka! Ce n'est pas comme si j'avais fait ces cookies pour toi!' 💕"

@command('husbando', '🤵 Génère ton husbando de rêve!')
def cmd_husbando(sender_id, message_text=""):
    """Génère un husbando unique"""
    messages = [{
        "role": "system", 
        "content": """Crée un husbando original sans d'ecrire se que tu fais avec :
        - Nom japonais cool
        - Âge (20-28 ans)
        - Type de personnalité (kuudere, stoïque, protecteur, etc.)
        - Apparence marquante
        - Métier/talent
        - Citation caractéristique
        Format français, style badass/romantique, max 350 caractères"""
    }, {
        "role": "user",
        "content": "Crée mon husbando parfait!"
    }]
    
    ai_response = call_mistral_api(messages, max_tokens=180, temperature=0.9)
    
    if ai_response:
        return f"🤵⚡ Ton husbando t'attend!\n\n{ai_response}\n\n💙 Il ne te décevra jamais!"
    else:
        return "🤵 Takeshi, 24 ans, capitaine stoïque aux yeux d'acier! Épéiste légendaire qui cache un cœur tendre. 'Je protégerai toujours ceux qui me sont chers... y compris toi.' ⚔️💙"

@command('animequiz', '🧩 Quiz épique sur les anime!')
def cmd_animequiz(sender_id, message_text=""):
    """Quiz anime interactif"""
    # Si c'est une réponse, on la traite (simplifiée pour cet exemple)
    if message_text.strip():
        return f"🎯 Réponse reçue: '{message_text}'\n💡 Nouveau quiz en arrivant! Tape /animequiz ⚡"
    
    messages = [{
        "role": "system",
        "content": """Crée un quiz anime original sans d'ecrire se que tu fais avec :
        - Question intéressante sur anime/manga populaire
        - 3 choix multiples A, B, C
        - Difficulté moyenne
        - Style énergique
        - Maximum 300 caractères
        Format: Question + choix A/B/C"""
    }, {
        "role": "user",
        "content": "Crée un quiz anime!"
    }]
    
    ai_response = call_mistral_api(messages, max_tokens=150, temperature=0.8)
    
    if ai_response:
        return f"🧩⚡ QUIZ TIME!\n\n{ai_response}\n\n🎯 Réponds-moi, nakama!"
    else:
        return "🧩 Dans quel anime trouve-t-on les 'Piliers'?\nA) Attack on Titan\nB) Demon Slayer\nC) Naruto\n\n⚡ À toi de jouer!"

@command('otakufact', '📚 Fun facts otaku ultra intéressants!')
def cmd_otakufact(sender_id, message_text=""):
    """Fun facts otaku"""
    messages = [{
        "role": "system",
        "content": """Donne un fun fact otaku intéressant sans d'ecrire se que tu fais sur :
        - Anime, manga, culture japonaise, studios d'animation
        - Fait surprenant et véridique
        - Style enthousiaste avec emojis
        - Maximum 250 caractères
        - Commence par 'Saviez-vous que...'"""
    }, {
        "role": "user",
        "content": "Donne-moi un fun fact otaku!"
    }]
    
    ai_response = call_mistral_api(messages, max_tokens=120, temperature=0.7)
    
    if ai_response:
        return f"📚✨ OTAKU FACT!\n\n{ai_response}\n\n🤓 Incroyable, non?"
    else:
        return "📚 Saviez-vous que Akira Toriyama a créé Dragon Ball en s'inspirant du 'Voyage vers l'Ouest', un classique chinois? Son Goku = Sun Wukong! 🐒⚡"

@command('recommend', '🎬 Recommandations anime/manga personnalisées!')
def cmd_recommend(sender_id, message_text=""):
    """Recommandations selon genre"""
    genre = message_text.strip() or "aléatoire"
    
    messages = [{
        "role": "system",
        "content": f"""Recommande 2-3 anime/manga du genre '{genre}' avec :
        - Titres populaires ou cachés
        - Courte description enthousiaste de chacun
        - Pourquoi c'est génial
        - Style otaku passionné
        - Maximum 400 caractères"""
    }, {
        "role": "user",
        "content": f"Recommande-moi des anime {genre}!"
    }]
    
    ai_response = call_mistral_api(messages, max_tokens=200, temperature=0.8)
    
    if ai_response:
        return f"🎬✨ RECOMMANDATIONS {genre.upper()}!\n\n{ai_response}\n\n⭐ Bon visionnage, nakama!"
    else:
        return f"🎬 Pour {genre}:\n• Attack on Titan - Epic & sombre! ⚔️\n• Your Name - Romance qui fait pleurer 😭\n• One Piece - Aventure infinie! 🏴‍☠️\n\nBon anime time! ✨"

@command('translate', '🌐 Traduction otaku FR ↔ JP avec style!')
def cmd_translate(sender_id, message_text=""):
    """Traduction avec style otaku"""
    if not message_text.strip():
        return "🌐 Utilisation: /translate [texte à traduire]\n💡 Ex: /translate konnichiwa nakama!\n✨ Je traduis FR→JP et JP→FR!"
    
    messages = [{
        "role": "system",
        "content": """Tu es un traducteur otaku spécialisé. Traduis le texte donné :
        - Si c'est en français → traduis en japonais (avec romaji)
        - Si c'est en japonais/romaji → traduis en français
        - Ajoute le contexte anime/manga si pertinent
        - Style enthousiaste avec emojis
        - Maximum 300 caractères"""
    }, {
        "role": "user",
        "content": f"Traduis: {message_text}"
    }]
    
    ai_response = call_mistral_api(messages, max_tokens=150, temperature=0.7)
    
    if ai_response:
        return f"🌐✨ TRADUCTION!\n\n{ai_response}\n\n📝 Arigatou gozaimasu!"
    else:
        return f"🌐 Traduction basique:\n'{message_text}'\n\n💭 Désolé, mon dictionnaire otaku fait une pause! 🥺"

@command('mood', '😊 Analyseur d\'humeur otaku + conseils anime!')
def cmd_mood(sender_id, message_text=""):
    """Analyse l'humeur et recommande selon le mood"""
    if not message_text.strip():
        return "😊 Comment tu te sens aujourd'hui, nakama?\n💡 Ex: /mood je suis triste\n✨ Je vais analyser ton mood et te conseiller!"
    
    messages = [{
        "role": "system",
        "content": """Analyse l'humeur de l'utilisateur sans d'ecrire se que tu fais et recommande  :
        - Identification de l'émotion principale
        - 1-2 anime/manga adaptés à ce mood
        - Phrase de réconfort style anime
        - Emojis appropriés
        - Style empathique et otaku
        - Maximum 350 caractères"""
    }, {
        "role": "user",
        "content": f"Mon mood: {message_text}"
    }]
    
    ai_response = call_mistral_api(messages, max_tokens=180, temperature=0.8)
    
    if ai_response:
        return f"😊💫 ANALYSE MOOD!\n\n{ai_response}\n\n🤗 Tu n'es pas seul, nakama!"
    else:
        return f"😊 Je sens que tu as besoin de réconfort!\n🎬 Regarde 'Your Name' ou 'Spirited Away'\n💝 Tout ira mieux, nakama! Ganbatte!"

@command('admin', '🔐 [ADMIN] Commandes d\'administration du bot!')
def cmd_admin(sender_id, message_text=""):
    """Commandes d'administration sécurisées"""
    if not is_admin(sender_id):
        return "🔐 Accès refusé! Tu n'es pas administrateur, nakama! ❌"
    
    if not message_text.strip():
        return """🔐⚡ PANNEAU ADMIN NAKAMABOT! ⚡🔐

📊 Commandes disponibles:
• /admin stats - Statistiques détaillées
• /admin users - Liste des utilisateurs  
• /admin save - Force la sauvegarde Drive
• /admin load - Recharge depuis Drive
• /admin memory - Stats mémoire globale
• /broadcast [message] - Diffusion générale

🌐 Google Drive: {'✅ Connecté' if drive_service else '❌ Déconnecté'}
💾 Utilisateurs en mémoire: {len(user_memory)}
📱 Utilisateurs actifs: {len(user_list)}

⚡ Tu as le pouvoir, admin-sama! 💖"""
    
    action = message_text.strip().lower()
    
    if action == "stats":
        total_messages = sum(len(messages) for messages in user_memory.values())
        return f"""📊🔐 STATISTIQUES ADMIN

👥 Utilisateurs total: {len(user_list)}
💾 Utilisateurs avec mémoire: {len(user_memory)}
💬 Messages total stockés: {total_messages}
🌐 Google Drive: {'✅ Opérationnel' if drive_service else '❌ Indisponible'}
🔐 Admins configurés: {len(ADMIN_IDS)}

🎌 Commandes exécutées: {len(COMMANDS)}
⚡ Bot status: Opérationnel depuis le démarrage
💖 Ready to serve, admin-sama!"""
    
    elif action == "users":
        if not user_list:
            return "👥 Aucun utilisateur enregistré pour le moment!"
        
        user_text = "👥🔐 LISTE DES UTILISATEURS:\n\n"
        for i, user_id in enumerate(list(user_list)[:10], 1):  # Limite à 10 pour éviter les messages trop longs
            admin_marker = " 🔐" if is_admin(user_id) else ""
            memory_count = len(user_memory.get(user_id, []))
            user_text += f"{i}. {user_id}{admin_marker} ({memory_count} msg)\n"
        
        if len(user_list) > 10:
            user_text += f"\n... et {len(user_list) - 10} autres utilisateurs"
        
        return user_text
    
    elif action == "save":
        if not drive_service:
            return "❌ Google Drive non configuré! Impossible de sauvegarder."
        
        success = save_memory_to_drive()
        if success:
            return f"✅ Sauvegarde forcée réussie!\n💾 {len(user_memory)} utilisateurs et {len(user_list)} contacts sauvegardés"
        else:
            return "❌ Échec de la sauvegarde! Vérifiez les logs."
    
    elif action == "load":
        if not drive_service:
            return "❌ Google Drive non configuré! Impossible de charger."
        
        success = load_memory_from_drive()
        if success:
            return f"✅ Mémoire rechargée depuis Drive!\n💾 {len(user_memory)} utilisateurs et {len(user_list)} contacts restaurés"
        else:
            return "❌ Échec du chargement! Aucune sauvegarde trouvée ou erreur."
    
    elif action == "memory":
        memory_details = []
        for user_id, messages in list(user_memory.items())[:5]:  # Top 5
            last_msg = messages[-1]['timestamp'] if messages else "Jamais"
            memory_details.append(f"• {user_id}: {len(messages)} msg (dernière: {last_msg[:10]})")
        
        return f"""💾🔐 MÉMOIRE GLOBALE:

📊 Total utilisateurs: {len(user_memory)}
💬 Messages en mémoire: {sum(len(m) for m in user_memory.values())}

🔝 Top 5 utilisateurs actifs:
{chr(10).join(memory_details)}

🌐 Sauvegarde auto: {'✅ Active' if drive_service else '❌ Désactivée'}
💾 Limite par utilisateur: 3 messages"""
    
    else:
        return f"❓ Action '{action}' inconnue!\n💡 Tape /admin pour voir les commandes disponibles."

@command('help', '❓ Guide complet de toutes mes techniques secrètes!')
def cmd_help(sender_id, message_text=""):
    """Génère automatiquement l'aide basée sur toutes les commandes"""
    help_text = "🎌⚡ NAKAMA BOT - GUIDE ULTIME! ⚡🎌\n\n"
    
    # Séparer les commandes admin et utilisateur
    user_commands = []
    admin_commands = []
    
    for cmd_name, cmd_info in COMMANDS.items():
        if "[ADMIN" in cmd_info['description']:
            admin_commands.append(f"/{cmd_name} - {cmd_info['description']}")
        else:
            user_commands.append(f"/{cmd_name} - {cmd_info['description']}")
    
    # Afficher les commandes utilisateur
    for cmd in user_commands:
        help_text += f"{cmd}\n"
    
    # Afficher les commandes admin seulement si l'utilisateur est admin
    if is_admin(sender_id) and admin_commands:
        help_text += f"\n🔐 COMMANDES ADMIN:\n"
        for cmd in admin_commands:
            help_text += f"{cmd}\n"
    
    help_text += "\n🔥 Utilisation: Tape / + commande"
    help_text += "\n💡 Ex: /waifu, /ia salut!, /recommend shonen"
    help_text += "\n💾 Mémoire persistante: Les 3 derniers messages sauvegardés!"
    help_text += "\n🌐 Sauvegarde Google Drive automatique"
    
    if is_admin(sender_id):
        help_text += f"\n🔐 Statut admin confirmé - Accès total débloqué!"
    
    help_text += "\n\n⚡ Powered by Mistral AI + Google Drive - Créé avec amour pour les otakus! 💖"
    
    return help_text

# 🌐 ROUTES FLASK 🌐

@app.route("/", methods=['GET'])
def home():
    return jsonify({
        "status": "🎌 NakamaBot Otaku Edition is alive! ⚡",
        "timestamp": datetime.now().isoformat(),
        "commands_loaded": len(COMMANDS),
        "ai_ready": bool(MISTRAL_API_KEY),
        "ai_provider": "Mistral AI",
        "active_users": len(user_list),
        "memory_enabled": True,
        "google_drive": bool(drive_service),
        "admin_count": len(ADMIN_IDS),
        "security": "Admin-secured broadcast"
    })

@app.route("/webhook", methods=['GET', 'POST'])
def webhook():
    logger.info(f"📨 Webhook appelé - Méthode: {request.method}")
    
    if request.method == 'GET':
        mode = request.args.get('hub.mode', '')
        token = request.args.get('hub.verify_token', '')
        challenge = request.args.get('hub.challenge', '')
        
        logger.info(f"🔍 Vérification webhook - mode: {mode}, token match: {token == VERIFY_TOKEN}")
        
        if mode == "subscribe" and token == VERIFY_TOKEN:
            logger.info("✅ Webhook vérifié!")
            return challenge, 200
        else:
            logger.error("❌ Échec vérification webhook")
            return "Verification failed", 403
            
    elif request.method == 'POST':
        try:
            data = request.get_json()
            logger.info(f"📨 Données reçues: {json.dumps(data, indent=2)}")
            
            if not data or 'entry' not in data:
                return jsonify({"error": "Invalid data"}), 400
                
            for entry in data.get('entry', []):
                for messaging_event in entry.get('messaging', []):
                    sender_id = messaging_event.get('sender', {}).get('id')
                    
                    # Ajouter l'utilisateur à la liste
                    user_list.add(sender_id)
                    
                    if 'message' in messaging_event:
                        message_data = messaging_event['message']
                        
                        # Ignorer les echos
                        if message_data.get('is_echo'):
                            continue
                            
                        message_text = message_data.get('text', '').strip()
                        logger.info(f"💬 Message de {sender_id}: '{message_text}'")
                        
                        # Ajouter le message de l'utilisateur à la mémoire
                        add_to_memory(sender_id, 'user', message_text)
                        
                        # Traitement des commandes
                        response_text = process_command(sender_id, message_text)
                        
                        # Ajouter la réponse du bot à la mémoire
                        add_to_memory(sender_id, 'bot', response_text)
                        
                        # Envoi de la réponse
                        send_result = send_message(sender_id, response_text)
                        logger.info(f"📤 Envoi: {send_result}")
                        
        except Exception as e:
            logger.error(f"❌ Erreur webhook: {str(e)}")
            return jsonify({"error": str(e)}), 500
            
        return jsonify({"status": "ok"}), 200

def process_command(sender_id, message_text):
    """Traite les commandes de façon modulaire"""
    
    # Si le message ne commence pas par /, traiter comme /ia
    if not message_text.startswith('/'):
        if message_text.strip():
            return cmd_ia(sender_id, message_text)
        else:
            return "🎌 Konnichiwa! Tape /start pour commencer ou /help pour mes commandes! ✨"
    
    # Parser la commande
    parts = message_text[1:].split(' ', 1)
    command_name = parts[0].lower()
    command_args = parts[1] if len(parts) > 1 else ""
    
    logger.info(f"🎯 Commande: {command_name}, Args: {command_args}")
    
    # Exécuter la commande si elle existe
    if command_name in COMMANDS:
        try:
            return COMMANDS[command_name]['function'](sender_id, command_args)
        except Exception as e:
            logger.error(f"❌ Erreur commande {command_name}: {e}")
            return f"💥 Oups! Erreur dans /{command_name}. Retry, onegaishimasu! 🥺"
    else:
        return f"❓ Commande /{command_name} inconnue! Tape /help pour voir toutes mes techniques! ⚡"

def send_message(recipient_id, text):
    """Envoie un message Facebook avec gestion d'erreurs"""
    if not PAGE_ACCESS_TOKEN:
        logger.error("❌ PAGE_ACCESS_TOKEN manquant")
        return {"success": False, "error": "No access token"}
    
    url = "https://graph.facebook.com/v18.0/me/messages"
    
    # Diviser les messages trop longs
    max_length = 2000
    if len(text) > max_length:
        text = text[:max_length-50] + "...\n\n✨ Message tronqué! 💫"
    
    data = {
        "recipient": {"id": recipient_id},
        "message": {"text": text},
        "messaging_type": "RESPONSE"
    }
    
    try:
        response = requests.post(
            url,
            params={"access_token": PAGE_ACCESS_TOKEN},
            headers={"Content-Type": "application/json"},
            json=data,
            timeout=10
        )
        
        logger.info(f"📤 Réponse HTTP: {response.status_code}")
        
        if response.status_code == 200:
            return {"success": True}
        else:
            logger.error(f"❌ Erreur envoi: {response.text}")
            return {"success": False, "error": response.text}
            
    except Exception as e:
        logger.error(f"❌ Exception envoi: {e}")
        return {"success": False, "error": str(e)}

@app.route("/health", methods=['GET'])
def health_check():
    """Health check avec infos détaillées"""
    return jsonify({
        "status": "healthy",
        "bot": "NakamaBot Otaku Edition",
        "timestamp": datetime.now().isoformat(),
        "commands_count": len(COMMANDS),
        "commands_list": list(COMMANDS.keys()),
        "mistral_ready": bool(MISTRAL_API_KEY),
        "ai_provider": "Mistral AI",
        "active_users": len(user_list),
        "memory_enabled": True,
        "google_drive_connected": bool(drive_service),
        "admin_security": bool(ADMIN_IDS),
        "config": {
            "verify_token_set": bool(VERIFY_TOKEN),
            "page_token_set": bool(PAGE_ACCESS_TOKEN),
            "mistral_key_set": bool(MISTRAL_API_KEY),
            "drive_credentials_set": bool(GOOGLE_DRIVE_CREDENTIALS),
            "drive_folder_set": bool(DRIVE_FOLDER_ID),
            "admin_ids_set": bool(ADMIN_IDS)
        }
    }), 200

@app.route("/commands", methods=['GET'])
def list_commands():
    """API pour lister toutes les commandes disponibles"""
    commands_info = {}
    for name, info in COMMANDS.items():
        commands_info[name] = {
            'name': name,
            'description': info['description'],
            'admin_only': '[ADMIN' in info['description']
        }
    
    return jsonify({
        "total_commands": len(COMMANDS),
        "commands": commands_info,
        "ai_provider": "Mistral AI",
        "memory_enabled": True,
        "google_drive_enabled": bool(drive_service),
        "admin_security": bool(ADMIN_IDS),
        "active_users": len(user_list)
    })

@app.route("/startup-broadcast", methods=['POST'])
def startup_broadcast():
    """Route pour envoyer le message de mise à jour au démarrage"""
    # Vérifier si c'est un appel autorisé (vous pouvez ajouter une clé API ici)
    auth_key = request.headers.get('Authorization')
    if auth_key != f"Bearer {VERIFY_TOKEN}":
        return jsonify({"error": "Unauthorized"}), 401
    
    message = "🎌⚡ MISE À JOUR NAKAMA COMPLETED! ⚡🎌\n\n✨ Votre NakamaBot préféré vient d'être upgradé par Durand-sensei!\n\n🆕 Nouvelles fonctionnalités:\n💾 Mémoire persistante (Google Drive)\n🔄 Continuité des histoires permanente\n🔐 Système admin sécurisé\n📢 Broadcast admin seulement\n\n🚀 Prêt pour de nouvelles aventures otaku!\n\n⚡ Tape /help pour découvrir toutes mes nouvelles techniques secrètes, nakama! 💖"
    
    result = broadcast_message(message)
    
    return jsonify({
        "status": "broadcast_sent",
        "message": "Mise à jour annoncée",
        "sent_to": result['sent'],
        "total_users": result['total'],
        "google_drive": bool(drive_service),
        "admin_security": bool(ADMIN_IDS)
    })

@app.route("/memory-stats", methods=['GET'])
def memory_stats():
    """Statistiques sur la mémoire des utilisateurs"""
    stats = {
        "total_users_with_memory": len(user_memory),
        "total_users_active": len(user_list),
        "google_drive_connected": bool(drive_service),
        "last_save_attempt": "Automatic every 5 minutes",
        "memory_details": {}
    }
    
    for user_id, memory in user_memory.items():
        stats["memory_details"][user_id] = {
            "messages_count": len(memory),
            "last_interaction": memory[-1]['timestamp'] if memory else None,
            "is_admin": is_admin(user_id)
        }
    
    return jsonify(stats)

@app.route("/admin-control", methods=['POST'])
def admin_control():
    """API pour les contrôles admin externes"""
    data = request.get_json()
    action = data.get('action')
    admin_key = request.headers.get('Admin-Key')
    
    # Vérification de sécurité simple (vous pouvez améliorer ceci)
    if admin_key != VERIFY_TOKEN:
        return jsonify({"error": "Unauthorized admin access"}), 401
    
    if action == "force_save":
        success = save_memory_to_drive()
        return jsonify({"success": success, "message": "Force save attempted"})
    
    elif action == "force_load":
        success = load_memory_from_drive()
        return jsonify({"success": success, "message": "Force load attempted"})
    
    elif action == "get_stats":
        return jsonify({
            "users_count": len(user_list),
            "memory_count": len(user_memory),
            "drive_connected": bool(drive_service),
            "admin_count": len(ADMIN_IDS)
        })
    
    else:
        return jsonify({"error": "Unknown action"}), 400

def send_startup_notification():
    """Envoie automatiquement le message de mise à jour au démarrage"""
    if user_list:  # Seulement s'il y a des utilisateurs
        startup_message = "🎌⚡ SYSTÈME NAKAMA REDÉMARRÉ! ⚡🎌\n\n✨ Durand-sensei vient de mettre à jour mes circuits!\n\n🆕 Nouvelles capacités débloquées:\n💾 Mémoire persistante Google Drive\n🔄 Mode histoire continue permanent\n🔐 Système admin sécurisé\n📢 Broadcast protégé\n\n🚀 Je suis plus kawaii et sécurisé que jamais!\n\n⚡ Prêt pour nos prochaines aventures, nakama! 💖"
        
        result = broadcast_message(startup_message)
        logger.info(f"🚀 Message de démarrage envoyé à {result['sent']}/{result['total']} utilisateurs")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    
    logger.info("🚀 Démarrage NakamaBot Otaku Edition...")
    
    # Initialiser Google Drive
    drive_initialized = init_google_drive()
    
    # Charger la mémoire depuis Drive si possible
    if drive_initialized:
        load_success = load_memory_from_drive()
        if load_success:
            logger.info("✅ Mémoire chargée depuis Google Drive")
        else:
            logger.info("📁 Aucune sauvegarde trouvée - Démarrage avec mémoire vide")
        
        # Démarrer la sauvegarde automatique
        auto_save_memory()
    else:
        logger.warning("⚠️ Google Drive non disponible - Mémoire non persistante")
    
    logger.info(f"🎌 Commandes chargées: {len(COMMANDS)}")
    logger.info(f"📋 Liste: {list(COMMANDS.keys())}")
    logger.info(f"🤖 Mistral AI ready: {bool(MISTRAL_API_KEY)}")
    logger.info(f"💾 Système de mémoire: Activé (3 messages) {'+ Google Drive' if drive_service else '+ Local seulement'}")
    logger.info(f"📢 Système de broadcast: {'🔐 Sécurisé admin' if ADMIN_IDS else '⚠️ Non sécurisé'}")
    logger.info(f"🔐 Administrateurs: {len(ADMIN_IDS)} configurés")
    logger.info(f"👥 Utilisateurs en mémoire: {len(user_list)}")
    
    # Envoyer le message de démarrage après un court délai
    def delayed_startup_notification():
        time.sleep(5)  # Attendre 5 secondes que le serveur soit prêt
        send_startup_notification()
    
    # Lancer la notification en arrière-plan
    notification_thread = threading.Thread(target=delayed_startup_notification)
    notification_thread.daemon = True
    notification_thread.start()
    
    app.run(host="0.0.0.0", port=port, debug=False)
