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

# 🔐 Configuration Admin et Google Drive - VARIABLES SÉPARÉES
ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = set(id.strip() for id in ADMIN_IDS_RAW.split(",") if id.strip())

# Variables Google Drive séparées pour éviter les problèmes JSON
DRIVE_TYPE = os.getenv("DRIVE_TYPE", "service_account")
DRIVE_PROJECT_ID = os.getenv("DRIVE_PROJECT_ID", "")
DRIVE_PRIVATE_KEY_ID = os.getenv("DRIVE_PRIVATE_KEY_ID", "")
DRIVE_PRIVATE_KEY = "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDkXG3qYl04SxGN\nrDW7HoIP13upkh6DVQN2B0Bl4bU+zseYzWWB0PG269T2xT4WucRZmFol5DbZYlwG\nWLhh2gqgLC+o6DO66onOw5ZWXD8oV8dToKOwIkDbiHAA2V4QrOwXRUJYro8j8dkl\nCOC0U6OYxOyT7tUNYJyohgVnrxvw05ojsf9Ujr/Y04WBc9u2TzGtBk8Njw30SAP7\nVg7mjAypLO7Pza9Qni+VQww+dPyH7suegLFFAJym+wDkMoMSb+hv1P+xfP452usK\n60mAoavK67duZWFpIsU7m2aY06vHaYcLSThP4eksdTorTBiswILnbtsb5Oe23qyC\nB/6hE1u1AgMBAAECggEACoJDZPoeV+5tHMksQX5uVfwgsCVt2zWGFCrSGJjUs6gl\n5h8A+Rf3C6faKXoFuQYsUO2H1n8O/sgokSUzj6iOUnUow1Ezkjo5Wccalmz702eI\ntXfqwyVXDpM+iOzNMp9r5PKWZ/OD2aUHTQ2VyPlMCcYkLKGcyIG7QS5xC2ay9o0x\nXE5rBMGaN0hCM/qYlGpWv5pXHMptkFqbXrn2lj57GKmzhoBaALjP5msLMFNX09kt\nrD9n9EENkfakJyKqLPvk/Slr8i6dNLutLVmN+Gs/GzBsaUu8dj9kdvkgTfR2H2oH\nWYRJqAEskGKoDGSv/gsyv/OADfepIXZPMHVn/7+heQKBgQD/8uGkPKu1fyI5GWBg\n/JzrrCBZZOujFs6kL1KCf0IyKQ6JmZq+GFEGJQ78gMQN5gA9aCp1w7Oi76gaZC0h\n8coO9dY23oGa7Hys9kIdI+EsmYwJSuL90Xwk4qqYBW8PKsI3EOT5Vz1X+XH/7937\nJmgGlHWsZ4daHvZ+aFmnBTQPTQKBgQDkaCJKM3E+NaI0Zl4AbeN93lfnX4W6Uel4\nsijw7DWhKfj9CTixVtjBdyPnRuxJqQ3wb2n4yaCg3tqyOysIsfRY7G6jDnrXlWpc\nLwLwKxrzoSXhau7Tje4UbeKHtKpxUWnFZUwPlO1Dfa1A8qTo8P30SVUC3YBTWJ4d\nKFYhlPUaCQKBgFmlDhbiERoOn0P0eWc+0w9QSDxHNqj2kgW7dWCzhdHfw3G6VRKD\nnc1TKX6S8xgTGL5pP4Xjt4U3/17O+2fKMgUvYYnyQN6sObaywdFHAdUHKp8OlZZk\nyuB4a1u3e4CKb1+uESSrw5aOjbkgoFUYzJKRaO2rjSKpeZgooE35apR5AoGAEC9g\n3qkuiR371IK8foNK74xl5jtamo1bYfYd+JSEaFs1DZktr0NcMLlkjer0q3OTTUpX\n1A1VmJCyJpcSwZb6naKDZIKOKeConMeoCaTEUCdHK+YL7mnMSR5QQxWGTmlaeWZo\nMWJ4PaQWNtf635bUKA9aOs2/XiiVa7OEBvUrOSECgYEA7y3Ef5kaBLJ6mKTkS/ne\n67aC7lPLXkSc/NRLYG5QsfiTrEHR+S35FKSMQy0WzwrMoG+SBEegTjVRPqDo+bjE\nhTYWwTWx/AuLeMCuczrsaeSG8AMU9wqd/ZEmGk0o2YF0o2QDPIt/2tWG6ro2H8D9\ngidZ8AJ/F+mAN0nVPHkIazU=\n-----END PRIVATE KEY-----\n"
DRIVE_CLIENT_EMAIL = os.getenv("DRIVE_CLIENT_EMAIL", "")
DRIVE_CLIENT_ID = os.getenv("DRIVE_CLIENT_ID", "")
DRIVE_AUTH_URI = os.getenv("DRIVE_AUTH_URI", "")
DRIVE_TOKEN_URI = os.getenv("DRIVE_TOKEN_URI", "")
DRIVE_CLIENT_CERT_URL = os.getenv("DRIVE_CLIENT_CERT_URL", "")
DRIVE_FOLDER_ID = os.getenv("DRIVE_FOLDER_ID", "")

# 💾 SYSTÈME DE MÉMOIRE
user_memory = defaultdict(lambda: deque(maxlen=10))
user_list = set()

# 🌐 Service Google Drive
drive_service = None

def check_drive_config():
    """Vérifie si toutes les variables Google Drive sont présentes"""
    required_vars = {
        'DRIVE_PROJECT_ID': DRIVE_PROJECT_ID,
        'DRIVE_PRIVATE_KEY': DRIVE_PRIVATE_KEY,
        'DRIVE_CLIENT_EMAIL': DRIVE_CLIENT_EMAIL,
        'DRIVE_CLIENT_ID': DRIVE_CLIENT_ID,
        'DRIVE_FOLDER_ID': DRIVE_FOLDER_ID
    }
    
    missing_vars = []
    for var_name, var_value in required_vars.items():
        if not var_value.strip():
            missing_vars.append(var_name)
    
    if missing_vars:
        logger.error(f"❌ Variables Google Drive manquantes: {missing_vars}")
        logger.info("💡 Variables requises pour Google Drive:")
        logger.info("   DRIVE_PROJECT_ID - ID du projet Google Cloud")
        logger.info("   DRIVE_PRIVATE_KEY - Clé privée (avec \\n pour les retours à la ligne)")
        logger.info("   DRIVE_CLIENT_EMAIL - Email du service account")
        logger.info("   DRIVE_CLIENT_ID - ID du client")
        logger.info("   DRIVE_FOLDER_ID - ID du dossier Drive de destination")
        return False
    
    logger.info("✅ Toutes les variables Google Drive sont présentes")
    return True

def init_google_drive():
    """Initialise le service Google Drive avec variables séparées"""
    global drive_service
    
    if not check_drive_config():
        logger.warning("⚠️ Google Drive non configuré - Variables manquantes")
        return False
    
    try:
        logger.info("🔄 Initialisation Google Drive avec variables séparées...")
        
        # Construction des credentials à partir des variables
        credentials_info = {
            "type": DRIVE_TYPE,
            "project_id": DRIVE_PROJECT_ID,
            "private_key_id": DRIVE_PRIVATE_KEY_ID,
            "private_key": DRIVE_PRIVATE_KEY.replace('\\n', '\n'),  # Convertir \\n en vrais retours à la ligne
            "client_email": DRIVE_CLIENT_EMAIL,
            "client_id": DRIVE_CLIENT_ID,
            "auth_uri": DRIVE_AUTH_URI or "https://accounts.google.com/o/oauth2/auth",
            "token_uri": DRIVE_TOKEN_URI or "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": DRIVE_CLIENT_CERT_URL
        }
        
        logger.info(f"🔍 Project ID: {credentials_info['project_id']}")
        logger.info(f"🔍 Client Email: {credentials_info['client_email']}")
        logger.info(f"🔍 Folder ID: {DRIVE_FOLDER_ID}")
        
        # Créer les credentials avec les bonnes permissions
        scopes = [
            'https://www.googleapis.com/auth/drive.file',
            'https://www.googleapis.com/auth/drive'
        ]
        
        credentials = Credentials.from_service_account_info(
            credentials_info,
            scopes=scopes
        )
        
        # Créer le service
        drive_service = build('drive', 'v3', credentials=credentials)
        
        # Test de connexion
        logger.info("🧪 Test de connexion Google Drive...")
        about = drive_service.about().get(fields="user").execute()
        logger.info(f"✅ Connecté comme: {about.get('user', {}).get('emailAddress', 'Inconnu')}")
        
        # Vérifier l'accès au dossier
        try:
            folder_info = drive_service.files().get(fileId=DRIVE_FOLDER_ID, fields="name,id").execute()
            logger.info(f"✅ Accès au dossier: {folder_info.get('name')} (ID: {folder_info.get('id')})")
        except Exception as folder_error:
            logger.error(f"❌ Erreur accès dossier {DRIVE_FOLDER_ID}: {folder_error}")
            return False
        
        logger.info("✅ Google Drive initialisé avec succès")
        return True
        
    except Exception as e:
        logger.error(f"❌ Erreur initialisation Google Drive: {e}")
        logger.error(f"Type d'erreur: {type(e).__name__}")
        
        # Debug des variables pour diagnostiquer
        logger.debug("🔍 Debug variables Drive:")
        logger.debug(f"  PROJECT_ID présent: {bool(DRIVE_PROJECT_ID)}")
        logger.debug(f"  PRIVATE_KEY présent: {bool(DRIVE_PRIVATE_KEY)}")
        logger.debug(f"  CLIENT_EMAIL présent: {bool(DRIVE_CLIENT_EMAIL)}")
        logger.debug(f"  FOLDER_ID présent: {bool(DRIVE_FOLDER_ID)}")
        
        return False

def save_memory_to_drive():
    """Sauvegarde la mémoire sur Google Drive"""
    if not drive_service:
        logger.warning("⚠️ Google Drive service non disponible pour sauvegarde")
        return False
    
    try:
        logger.info("💾 Début sauvegarde mémoire sur Google Drive...")
        
        # Préparer les données à sauvegarder
        memory_data = {
            'user_memory': {},
            'user_list': list(user_list),
            'timestamp': datetime.now().isoformat(),
            'version': '2.0',
            'total_users': len(user_list),
            'users_with_memory': len(user_memory)
        }
        
        # Convertir deque en list pour JSON
        for user_id, messages in user_memory.items():
            memory_data['user_memory'][user_id] = list(messages)
        
        logger.info(f"📊 Données à sauvegarder: {len(user_memory)} utilisateurs, {len(user_list)} contacts")
        
        # Créer le contenu JSON
        json_data = json.dumps(memory_data, indent=2, ensure_ascii=False)
        
        # Chercher si le fichier existe déjà
        filename = "nakamabot_memory.json"
        query = f"name='{filename}' and parents in '{DRIVE_FOLDER_ID}' and trashed=false"
        results = drive_service.files().list(q=query, fields="files(id,name)").execute()
        files = results.get('files', [])
        
        # Préparer le média upload
        media = MediaIoBaseUpload(
            io.BytesIO(json_data.encode('utf-8')),
            mimetype='application/json',
            resumable=True
        )
        
        if files:
            # Mettre à jour le fichier existant
            file_id = files[0]['id']
            logger.info(f"🔄 Mise à jour fichier existant: {file_id}")
            
            updated_file = drive_service.files().update(
                fileId=file_id,
                media_body=media,
                fields='id,name,modifiedTime'
            ).execute()
            
            logger.info(f"✅ Mémoire mise à jour sur Drive (ID: {updated_file.get('id')})")
            
        else:
            # Créer un nouveau fichier
            logger.info("📁 Création nouveau fichier de sauvegarde...")
            
            file_metadata = {
                'name': filename,
                'parents': [DRIVE_FOLDER_ID],
                'description': f'NakamaBot Memory Backup - {datetime.now().isoformat()}'
            }
            
            created_file = drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id,name'
            ).execute()
            
            logger.info(f"✅ Nouvelle sauvegarde créée sur Drive (ID: {created_file.get('id')})")
        
        logger.info("💾 Sauvegarde terminée avec succès")
        return True
        
    except Exception as e:
        logger.error(f"❌ Erreur sauvegarde Drive: {e}")
        logger.error(f"Type d'erreur: {type(e).__name__}")
        return False

def load_memory_from_drive():
    """Charge la mémoire depuis Google Drive"""
    global user_memory, user_list
    
    if not drive_service:
        logger.warning("⚠️ Google Drive service non disponible pour chargement")
        return False
    
    try:
        logger.info("🔄 Début chargement mémoire depuis Google Drive...")
        
        # Chercher le fichier de mémoire
        filename = "nakamabot_memory.json"
        query = f"name='{filename}' and parents in '{DRIVE_FOLDER_ID}' and trashed=false"
        results = drive_service.files().list(
            q=query, 
            fields="files(id,name,modifiedTime)",
            orderBy="modifiedTime desc"
        ).execute()
        files = results.get('files', [])
        
        if not files:
            logger.info("📁 Aucune sauvegarde trouvée sur Drive")
            return False
        
        # Prendre le fichier le plus récent
        file_to_load = files[0]
        file_id = file_to_load['id']
        modified_time = file_to_load.get('modifiedTime', 'Inconnu')
        
        logger.info(f"📥 Chargement fichier: {file_id} (modifié: {modified_time})")
        
        # Télécharger le fichier
        request_download = drive_service.files().get_media(fileId=file_id)
        file_stream = io.BytesIO()
        downloader = MediaIoBaseDownload(file_stream, request_download)
        
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            if status:
                logger.info(f"📥 Téléchargement: {int(status.progress() * 100)}%")
        
        # Parser les données
        file_stream.seek(0)
        file_content = file_stream.read().decode('utf-8')
        memory_data = json.loads(file_content)
        
        logger.info(f"📊 Données chargées: version {memory_data.get('version', '1.0')}")
        
        # Restaurer la mémoire avec validation
        user_memory.clear()
        loaded_users = 0
        
        for user_id, messages in memory_data.get('user_memory', {}).items():
            if isinstance(messages, list):
                valid_messages = []
                for msg in messages:
                    if isinstance(msg, dict) and 'type' in msg and 'content' in msg:
                        valid_messages.append(msg)
                
                if valid_messages:
                    user_memory[user_id] = deque(valid_messages, maxlen=10)
                    loaded_users += 1
        
        # Restaurer la liste d'utilisateurs
        old_user_count = len(user_list)
        restored_users = memory_data.get('user_list', [])
        
        if isinstance(restored_users, list):
            user_list.update(restored_users)
        
        # Stats de chargement
        saved_time = memory_data.get('timestamp', 'Inconnu')
        logger.info(f"✅ Mémoire chargée depuis Drive")
        logger.info(f"📊 {loaded_users} utilisateurs avec mémoire restaurés")
        logger.info(f"📊 {len(user_list) - old_user_count} nouveaux contacts ajoutés")
        logger.info(f"📅 Sauvegarde du: {saved_time}")
        
        return True
        
    except json.JSONDecodeError as e:
        logger.error(f"❌ Erreur parsing JSON sauvegardé: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Erreur chargement Drive: {e}")
        logger.error(f"Type d'erreur: {type(e).__name__}")
        return False

def auto_save_memory():
    """Sauvegarde automatique périodique"""
    def save_loop():
        logger.info("🔄 Démarrage thread de sauvegarde automatique")
        while True:
            try:
                time.sleep(300)  # Sauvegarder toutes les 5 minutes
                if user_memory or user_list:
                    logger.info("🔄 Tentative sauvegarde automatique...")
                    success = save_memory_to_drive()
                    if success:
                        logger.info("✅ Sauvegarde automatique réussie")
                    else:
                        logger.warning("⚠️ Échec sauvegarde automatique")
                else:
                    logger.debug("💤 Aucune donnée à sauvegarder")
            except Exception as e:
                logger.error(f"❌ Erreur dans le thread de sauvegarde: {e}")
    
    if drive_service:
        thread = threading.Thread(target=save_loop, daemon=True)
        thread.start()
        logger.info("🔄 Sauvegarde automatique activée (toutes les 5 min)")
    else:
        logger.warning("⚠️ Sauvegarde automatique désactivée - Google Drive non disponible")

# Validation des tokens
if not PAGE_ACCESS_TOKEN:
    logger.error("❌ PAGE_ACCESS_TOKEN is missing!")
else:
    logger.info(f"✅ PAGE_ACCESS_TOKEN configuré (longueur: {len(PAGE_ACCESS_TOKEN)})")

if not MISTRAL_API_KEY:
    logger.error("❌ MISTRAL_API_KEY is missing!")
else:
    logger.info(f"✅ MISTRAL_API_KEY configuré (longueur: {len(MISTRAL_API_KEY)})")

# Validation Admin
logger.info(f"🔐 ADMIN_IDS raw: '{ADMIN_IDS_RAW}'")
logger.info(f"🔐 ADMIN_IDS parsed: {ADMIN_IDS}")

if ADMIN_IDS and any(id.strip() for id in ADMIN_IDS):
    logger.info(f"🔐 {len(ADMIN_IDS)} administrateur(s) configuré(s): {list(ADMIN_IDS)}")
else:
    logger.warning("⚠️ Aucun administrateur configuré - Broadcast désactivé")

# Configuration Mistral API
MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"
MISTRAL_MODEL = "mistral-medium"

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
        'type': message_type,
        'content': content,
        'timestamp': datetime.now().isoformat()
    })
    logger.info(f"💾 Mémoire {user_id}: {len(user_memory[user_id])} messages")
    
    # Sauvegarde asynchrone seulement si Drive est disponible
    if drive_service:
        def async_save():
            try:
                save_memory_to_drive()
            except Exception as e:
                logger.error(f"❌ Erreur sauvegarde asynchrone: {e}")
        
        threading.Thread(target=async_save, daemon=True).start()

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
    user_id_str = str(user_id).strip()
    is_admin_result = user_id_str in ADMIN_IDS
    logger.debug(f"🔐 Vérification admin pour {user_id_str}: {is_admin_result} (admins: {ADMIN_IDS})")
    return is_admin_result

def broadcast_message(message_text):
    """Envoie un message à tous les utilisateurs connus"""
    success_count = 0
    total_users = len(user_list)
    
    logger.info(f"📢 Broadcast à {total_users} utilisateurs: {message_text[:100]}...")
    
    for user_id in user_list.copy():
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
        "content": """Tu es NakamaBot, un bot otaku kawaii et énergique. Crée une présentation épique style anime opening en français, SANS descriptions d'actions (pas de *actions* ou **descriptions**). Parle directement avec :
        - Beaucoup d'emojis anime/manga
        - Style énergique comme Luffy ou Naruto
        - Présente tes capacités de façon cool
        - Maximum 300 caractères
        - Termine par une phrase motivante d'anime
        - PAS de descriptions de ce que tu fais"""
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
    if not message_text.strip():
        topics = [
            "Quel est ton anime préféré de cette saison?",
            "Si tu pouvais être transporté dans un isekai, lequel choisirais-tu?",
            "Raconte-moi ton personnage d'anime favori!",
            "Manga ou anime? Et pourquoi? 🤔",
            "As-tu déjà rêvé d'avoir un stand de JoJo?"
        ]
        return f"💭 {random.choice(topics)} ✨"
    
    memory_context = get_memory_context(sender_id)
    
    messages = [{
        "role": "system",
        "content": """Tu es NakamaBot, une IA otaku kawaii et énergique. Tu as une mémoire persistante des conversations précédentes. Réponds en français SANS décrire tes actions (pas de *actions* ou **descriptions**). Parle directement avec:
        - Personnalité mélange de Nezuko (mignon), Megumin (dramatique), et Zero Two (taquine)
        - Beaucoup d'emojis anime
        - Références anime/manga naturelles
        - Style parfois tsundere ou badass selon le contexte
        - Utilise le contexte des messages précédents pour une conversation fluide
        - Maximum 400 caractères
        - PAS de descriptions de ce que tu fais, juste parle directement"""
    }]
    
    messages.extend(memory_context)
    messages.append({
        "role": "user",
        "content": message_text
    })
    
    ai_response = call_mistral_api(messages, max_tokens=200, temperature=0.8)
    
    if ai_response:
        return f"💖 {ai_response}"
    else:
        return "💭 Mon cerveau otaku bug un peu là... Retry, onegaishimasu! 🥺"

@command('drive_config', '🔧 [ADMIN] Diagnostic complet de la configuration Google Drive')
def cmd_drive_config(sender_id, message_text=""):
    """Diagnostic détaillé de Google Drive pour les admins"""
    if not is_admin(sender_id):
        return f"🔐 Accès refusé! Seuls les admins peuvent utiliser cette commande! ❌\n🔍 Ton ID: {sender_id}"
    
    config_status = f"""🔧🔐 DIAGNOSTIC GOOGLE DRIVE ADMIN

📋 Variables d'environnement:
✅ DRIVE_TYPE: {DRIVE_TYPE or '❌ MANQUANT'}
{'✅' if DRIVE_PROJECT_ID else '❌'} DRIVE_PROJECT_ID: {DRIVE_PROJECT_ID[:20] + '...' if DRIVE_PROJECT_ID else 'MANQUANT'}
{'✅' if DRIVE_PRIVATE_KEY_ID else '❌'} DRIVE_PRIVATE_KEY_ID: {DRIVE_PRIVATE_KEY_ID[:20] + '...' if DRIVE_PRIVATE_KEY_ID else 'MANQUANT'}
{'✅' if DRIVE_PRIVATE_KEY else '❌'} DRIVE_PRIVATE_KEY: {'Présente (' + str(len(DRIVE_PRIVATE_KEY)) + ' chars)' if DRIVE_PRIVATE_KEY else 'MANQUANTE'}
{'✅' if DRIVE_CLIENT_EMAIL else '❌'} DRIVE_CLIENT_EMAIL: {DRIVE_CLIENT_EMAIL or 'MANQUANT'}
{'✅' if DRIVE_CLIENT_ID else '❌'} DRIVE_CLIENT_ID: {DRIVE_CLIENT_ID or 'MANQUANT'}
{'✅' if DRIVE_FOLDER_ID else '❌'} DRIVE_FOLDER_ID: {DRIVE_FOLDER_ID or 'MANQUANT'}

🌐 Statut du service:
{'✅ Connecté' if drive_service else '❌ Non connecté'}

💡 Pour configurer Google Drive:
1. Créer un projet Google Cloud
2. Activer l'API Google Drive
3. Créer un Service Account
4. Télécharger le fichier JSON des credentials
5. Extraire chaque champ dans une variable séparée

🔍 Tentative de reconnexion..."""
    
    # Tenter une reconnexion
    if message_text.strip().lower() == "reconnect":
        success = init_google_drive()
        config_status += f"\n\n🔄 Résultat reconnexion: {'✅ Succès' if success else '❌ Échec'}"
    
    return config_status

# Continuer avec toutes les autres commandes existantes...
@command('story', '📖 Histoires courtes isekai/shonen sur mesure (avec suite persistante!)')
def cmd_story(sender_id, message_text=""):
    """Histoires courtes personnalisées avec continuité"""
    theme = message_text.strip() or "isekai"
    memory_context = get_memory_context(sender_id)
    has_previous_story = any("📖" in msg.get("content", "") for msg in memory_context)
    
    messages = [{
        "role": "system",
        "content": f"""Tu es un conteur otaku. {'Continue l\'histoire précédente' if has_previous_story else 'Écis une nouvelle histoire'} {theme} SANS décrire tes actions (pas de *actions* ou **descriptions**). Raconte directement avec :
        - Protagoniste attachant
        - Situation intéressante
        - Style anime/manga
        - {'Suite logique de l\'histoire' if has_previous_story else 'Début captivant'}
        - Maximum 500 caractères
        - Beaucoup d'action et d'émotion
        - PAS de descriptions de ce que tu fais, juste raconte l'histoire"""
    }]
    
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
    
    memory_text += f"\n💭 {len(user_memory[sender_id])}/10 messages en mémoire"
    memory_text += f"\n🌐 Sauvegarde Google Drive: {'✅ Active' if drive_service else '❌ Désactivée'}"
    memory_text += "\n✨ Je me souviens de tout, même après redémarrage!"
    
    return memory_text

@command('broadcast', '📢 [ADMIN ONLY] Envoie un message à tous les nakamas!')
def cmd_broadcast(sender_id, message_text=""):
    """Fonction broadcast sécurisée pour admins seulement"""
    logger.info(f"🔐 Tentative broadcast par {sender_id}, admin check: {is_admin(sender_id)}")
    
    if not is_admin(sender_id):
        return f"🔐 Accès refusé! Seuls les admins peuvent utiliser cette commande, nakama! ❌\n✨ Tu n'as pas les permissions nécessaires.\n🔍 Ton ID: {sender_id}"
    
    if not message_text.strip():
        return "📢 Usage: /broadcast [message]\n⚠️ Envoie à TOUS les utilisateurs!\n🔐 Commande admin seulement"
    
    broadcast_text = f"📢🎌 ANNONCE ADMIN NAKAMA!\n\n{message_text}\n\n⚡ - Message officiel des admins NakamaBot 💖"
    result = broadcast_message(broadcast_text)
    
    return f"📊 Broadcast admin envoyé à {result['sent']}/{result['total']} nakamas! ✨\n🔐 Action enregistrée comme admin."

@command('waifu', '👸 Génère ta waifu parfaite avec IA!')
def cmd_waifu(sender_id, message_text=""):
    """Génère une waifu unique"""
    messages = [{
        "role": "system",
        "content": """Crée une waifu originale SANS décrire tes actions (pas de *actions* ou **descriptions**). Présente directement avec :
        - Nom japonais mignon
        - Âge (18-25 ans)
        - Personnalité unique (kuudere, tsundere, dandere, etc.)
        - Apparence brève mais marquante
        - Hobby/talent spécial 
        - Une phrase qu'elle dirait
        Format en français, style kawaii, max 350 caractères
        PAS de descriptions de ce que tu fais, présente juste la waifu"""
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
        "content": """Crée un husbando original SANS décrire tes actions (pas de *actions* ou **descriptions**). Présente directement avec :
        - Nom japonais cool
        - Âge (20-28 ans)
        - Type de personnalité (kuudere, stoïque, protecteur, etc.)
        - Apparence marquante
        - Métier/talent
        - Citation caractéristique
        Format français, style badass/romantique, max 350 caractères
        PAS de descriptions de ce que tu fais, présente juste le husbando"""
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
    if message_text.strip():
        return f"🎯 Réponse reçue: '{message_text}'\n💡 Nouveau quiz en arrivant! Tape /animequiz ⚡"
    
    messages = [{
        "role": "system",
        "content": """Crée un quiz anime original SANS décrire tes actions (pas de *actions* ou **descriptions**). Pose directement avec :
        - Question intéressante sur anime/manga populaire
        - 3 choix multiples A, B, C
        - Difficulté moyenne
        - Style énergique
        - Maximum 300 caractères
        Format: Question + choix A/B/C
        PAS de descriptions de ce que tu fais, pose juste la question"""
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
        "content": """Donne un fun fact otaku intéressant SANS décrire tes actions (pas de *actions* ou **descriptions**). Partage directement avec :
        - Anime, manga, culture japonaise, studios d'animation
        - Fait surprenant et véridique
        - Style enthousiaste avec emojis
        - Maximum 250 caractères
        - Commence par 'Saviez-vous que...'
        PAS de descriptions de ce que tu fais, donne juste le fait"""
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
        "content": f"""Recommande 2-3 anime/manga du genre '{genre}' SANS décrire tes actions (pas de *actions* ou **descriptions**). Recommande directement avec :
        - Titres populaires ou cachés
        - Courte description enthousiaste de chacun
        - Pourquoi c'est génial
        - Style otaku passionné
        - Maximum 400 caractères
        PAS de descriptions de ce que tu fais, donne juste les recommandations"""
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
        "content": """Tu es un traducteur otaku spécialisé SANS décrire tes actions (pas de *actions* ou **descriptions**). Traduis directement :
        - Si c'est en français → traduis en japonais (avec romaji)
        - Si c'est en japonais/romaji → traduis en français
        - Ajoute le contexte anime/manga si pertinent
        - Style enthousiaste avec emojis
        - Maximum 300 caractères
        PAS de descriptions de ce que tu fais, traduis juste"""
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
        "content": """Analyse l'humeur de l'utilisateur SANS décrire tes actions (pas de *actions* ou **descriptions**). Réponds directement avec :
        - Identification de l'émotion principale
        - 1-2 anime/manga adaptés à ce mood
        - Phrase de réconfort style anime
        - Emojis appropriés
        - Style empathique et otaku
        - Maximum 350 caractères
        PAS de descriptions de ce que tu fais, analyse juste et conseille"""
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
        return f"🔐 Accès refusé! Tu n'es pas administrateur, nakama! ❌\n🔍 Ton ID: {sender_id}\n📋 Admins autorisés: {list(ADMIN_IDS)}"
    
    if not message_text.strip():
        return f"""🔐⚡ PANNEAU ADMIN NAKAMABOT! ⚡🔐

📊 Commandes disponibles:
• /admin stats - Statistiques détaillées
• /admin users - Liste des utilisateurs  
• /admin save - Force la sauvegarde Drive
• /admin load - Recharge depuis Drive
• /admin memory - Stats mémoire globale
• /drive_config - Diagnostic Google Drive
• /broadcast [message] - Diffusion générale

🌐 Google Drive: {'✅ Connecté' if drive_service else '❌ Déconnecté'}
💾 Utilisateurs en mémoire: {len(user_memory)}
📱 Utilisateurs actifs: {len(user_list)}
🔐 Ton ID admin: {sender_id}

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
🔍 Admin actuel: {sender_id}

🎌 Commandes disponibles: {len(COMMANDS)}
⚡ Bot status: Opérationnel
💖 Ready to serve, admin-sama!"""
    
    elif action == "users":
        if not user_list:
            return "👥 Aucun utilisateur enregistré pour le moment!"
        
        user_text = "👥🔐 LISTE DES UTILISATEURS:\n\n"
        for i, user_id in enumerate(list(user_list)[:10], 1):
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
        for user_id, messages in list(user_memory.items())[:5]:
            last_msg = messages[-1]['timestamp'] if messages else "Jamais"
            memory_details.append(f"• {user_id}: {len(messages)} msg (dernière: {last_msg[:10]})")
        
        return f"""💾🔐 MÉMOIRE GLOBALE:

📊 Total utilisateurs: {len(user_memory)}
💬 Messages en mémoire: {sum(len(m) for m in user_memory.values())}

🔝 Top 5 utilisateurs actifs:
{chr(10).join(memory_details)}

🌐 Sauvegarde auto: {'✅ Active' if drive_service else '❌ Désactivée'}
💾 Limite par utilisateur: 10 messages"""
    
    else:
        return f"❓ Action '{action}' inconnue!\n💡 Tape /admin pour voir les commandes disponibles."

@command('help', '❓ Guide complet de toutes mes techniques secrètes!')
def cmd_help(sender_id, message_text=""):
    """Génère automatiquement l'aide basée sur toutes les commandes"""
    help_text = "🎌⚡ NAKAMA BOT - GUIDE ULTIME! ⚡🎌\n\n"
    
    user_commands = []
    admin_commands = []
    
    for cmd_name, cmd_info in COMMANDS.items():
        if "[ADMIN" in cmd_info['description']:
            admin_commands.append(f"/{cmd_name} - {cmd_info['description']}")
        else:
            user_commands.append(f"/{cmd_name} - {cmd_info['description']}")
    
    for cmd in user_commands:
        help_text += f"{cmd}\n"
    
    if is_admin(sender_id) and admin_commands:
        help_text += f"\n🔐 COMMANDES ADMIN:\n"
        for cmd in admin_commands:
            help_text += f"{cmd}\n"
    
    help_text += "\n🔥 Utilisation: Tape / + commande"
    help_text += "\n💡 Ex: /waifu, /ia salut!, /recommend shonen"
    help_text += "\n💾 Mémoire persistante: Les 10 derniers messages sauvegardés!"
    help_text += f"\n🌐 Sauvegarde Google Drive: {'✅ Active' if drive_service else '❌ Désactivée'}"
    
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
        "admin_ids": list(ADMIN_IDS),
        "security": "Admin-secured broadcast",
        "drive_config": {
            "project_id_set": bool(DRIVE_PROJECT_ID),
            "client_email_set": bool(DRIVE_CLIENT_EMAIL),
            "private_key_set": bool(DRIVE_PRIVATE_KEY),
            "folder_id_set": bool(DRIVE_FOLDER_ID)
        }
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
                    
                    user_list.add(sender_id)
                    
                    if 'message' in messaging_event:
                        message_data = messaging_event['message']
                        
                        if message_data.get('is_echo'):
                            continue
                            
                        message_text = message_data.get('text', '').strip()
                        logger.info(f"💬 Message de {sender_id}: '{message_text}'")
                        
                        add_to_memory(sender_id, 'user', message_text)
                        response_text = process_command(sender_id, message_text)
                        add_to_memory(sender_id, 'bot', response_text)
                        
                        send_result = send_message(sender_id, response_text)
                        logger.info(f"📤 Envoi: {send_result}")
                        
        except Exception as e:
            logger.error(f"❌ Erreur webhook: {str(e)}")
            return jsonify({"error": str(e)}), 500
            
        return jsonify({"status": "ok"}), 200

def process_command(sender_id, message_text):
    """Traite les commandes de façon modulaire"""
    
    if not message_text.startswith('/'):
        if message_text.strip():
            return cmd_ia(sender_id, message_text)
        else:
            return "🎌 Konnichiwa! Tape /start pour commencer ou /help pour mes commandes! ✨"
    
    parts = message_text[1:].split(' ', 1)
    command_name = parts[0].lower()
    command_args = parts[1] if len(parts) > 1 else ""
    
    logger.info(f"🎯 Commande: {command_name}, Args: {command_args}")
    
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
        "admin_ids": list(ADMIN_IDS),
        "config": {
            "verify_token_set": bool(VERIFY_TOKEN),
            "page_token_set": bool(PAGE_ACCESS_TOKEN),
            "mistral_key_set": bool(MISTRAL_API_KEY),
            "drive_project_id_set": bool(DRIVE_PROJECT_ID),
            "drive_client_email_set": bool(DRIVE_CLIENT_EMAIL),
            "drive_private_key_set": bool(DRIVE_PRIVATE_KEY),
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
    auth_key = request.headers.get('Authorization')
    if auth_key != f"Bearer {VERIFY_TOKEN}":
        return jsonify({"error": "Unauthorized"}), 401
    
    message = "🎌⚡ MISE À JOUR NAKAMA COMPLETED! ⚡🎌\n\n✨ Votre NakamaBot préféré vient d'être upgradé par Durand-sensei!\n\n🆕 Nouvelles fonctionnalités:\n💾 Mémoire persistante (Google Drive variables séparées)\n🔄 Continuité des histoires permanente\n🔐 Système admin sécurisé\n📢 Broadcast admin seulement\n🔧 Diagnostic Google Drive amélioré\n\n🚀 Configuration Drive simplifiée avec variables séparées!\n\n⚡ Tape /help pour découvrir toutes mes nouvelles techniques secrètes, nakama! 💖"
    
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
            "admin_count": len(ADMIN_IDS),
            "admin_ids": list(ADMIN_IDS),
            "drive_config": {
                "project_id_set": bool(DRIVE_PROJECT_ID),
                "client_email_set": bool(DRIVE_CLIENT_EMAIL),
                "private_key_set": bool(DRIVE_PRIVATE_KEY),
                "folder_id_set": bool(DRIVE_FOLDER_ID)
            }
        })
    
    elif action == "test_drive":
        success = init_google_drive()
        return jsonify({
            "success": success, 
            "message": "Drive connection test attempted",
            "drive_connected": bool(drive_service)
        })
    
    else:
        return jsonify({"error": "Unknown action"}), 400

@app.route("/drive-debug", methods=['GET'])
def drive_debug():
    """Route de debug pour Google Drive"""
    auth_key = request.headers.get('Authorization')
    if auth_key != f"Bearer {VERIFY_TOKEN}":
        return jsonify({"error": "Unauthorized"}), 401
    
    debug_info = {
        "drive_service_status": bool(drive_service),
        "environment_variables": {
            "DRIVE_TYPE": bool(DRIVE_TYPE),
            "DRIVE_PROJECT_ID": bool(DRIVE_PROJECT_ID) and DRIVE_PROJECT_ID[:10] + "..." if DRIVE_PROJECT_ID else None,
            "DRIVE_PRIVATE_KEY_ID": bool(DRIVE_PRIVATE_KEY_ID) and DRIVE_PRIVATE_KEY_ID[:10] + "..." if DRIVE_PRIVATE_KEY_ID else None,
            "DRIVE_PRIVATE_KEY": bool(DRIVE_PRIVATE_KEY) and f"Present ({len(DRIVE_PRIVATE_KEY)} chars)" if DRIVE_PRIVATE_KEY else "Missing",
            "DRIVE_CLIENT_EMAIL": DRIVE_CLIENT_EMAIL if DRIVE_CLIENT_EMAIL else "Missing",
            "DRIVE_CLIENT_ID": bool(DRIVE_CLIENT_ID) and DRIVE_CLIENT_ID[:10] + "..." if DRIVE_CLIENT_ID else None,
            "DRIVE_FOLDER_ID": DRIVE_FOLDER_ID if DRIVE_FOLDER_ID else "Missing"
        },
        "config_check": check_drive_config(),
        "instructions": {
            "step_1": "Aller sur Google Cloud Console",
            "step_2": "Créer un projet ou sélectionner un existant", 
            "step_3": "Activer l'API Google Drive",
            "step_4": "Créer un Service Account dans IAM & Admin",
            "step_5": "Générer une clé JSON pour le Service Account",
            "step_6": "Extraire chaque champ du JSON vers les variables:",
            "variables_needed": [
                "DRIVE_PROJECT_ID (project_id du JSON)",
                "DRIVE_PRIVATE_KEY_ID (private_key_id du JSON)",
                "DRIVE_PRIVATE_KEY (private_key du JSON - remplacer \\n par des vrais retours)",
                "DRIVE_CLIENT_EMAIL (client_email du JSON)",
                "DRIVE_CLIENT_ID (client_id du JSON)",
                "DRIVE_FOLDER_ID (ID du dossier Drive de destination)"
            ],
            "step_7": "Partager le dossier Drive avec l'email du Service Account",
            "step_8": "Redémarrer l'application"
        }
    }
    
    return jsonify(debug_info)

def send_startup_notification():
    """Envoie automatiquement le message de mise à jour au démarrage"""
    if user_list:
        startup_message = f"""🎌⚡ SYSTÈME NAKAMA REDÉMARRÉ! ⚡🎌

✨ Durand-sensei vient de mettre à jour mes circuits!

🆕 Nouvelles capacités débloquées:
💾 Mémoire persistante Google Drive (variables séparées)
🔄 Mode histoire continue permanent
🔐 Système admin sécurisé
📢 Broadcast protégé
🔧 Diagnostic Drive amélioré
🚫 Plus de descriptions d'actions gênantes

🌐 Google Drive: {'✅ Connecté' if drive_service else '❌ Configuration requise'}

🚀 Je suis plus kawaii et naturel que jamais!

⚡ Prêt pour nos prochaines aventures, nakama! 💖"""
        
        result = broadcast_message(startup_message)
        logger.info(f"🚀 Message de démarrage envoyé à {result['sent']}/{result['total']} utilisateurs")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    
    logger.info("🚀 Démarrage NakamaBot Otaku Edition...")
    logger.info("🔧 Configuration Google Drive avec variables séparées...")
    
    # Afficher le statut des variables Drive au démarrage
    logger.info("📋 Variables Google Drive détectées:")
    logger.info(f"   DRIVE_PROJECT_ID: {'✅ Présent' if DRIVE_PROJECT_ID else '❌ Manquant'}")
    logger.info(f"   DRIVE_CLIENT_EMAIL: {'✅ Présent' if DRIVE_CLIENT_EMAIL else '❌ Manquant'}")
    logger.info(f"   DRIVE_PRIVATE_KEY: {'✅ Présent (' + str(len(DRIVE_PRIVATE_KEY)) + ' chars)' if DRIVE_PRIVATE_KEY else '❌ Manquant'}")
    logger.info(f"   DRIVE_FOLDER_ID: {'✅ Présent' if DRIVE_FOLDER_ID else '❌ Manquant'}")
    
    # Initialiser Google Drive
    drive_initialized = init_google_drive()
    
    if drive_initialized:
        logger.info("✅ Google Drive initialisé avec succès!")
        
        # Charger la mémoire depuis Drive si possible
        load_success = load_memory_from_drive()
        if load_success:
            logger.info("✅ Mémoire chargée depuis Google Drive")
        else:
            logger.info("📁 Aucune sauvegarde trouvée - Démarrage avec mémoire vide")
        
        auto_save_memory()
    else:
        logger.warning("⚠️ Google Drive non disponible - Mémoire non persistante")
        logger.info("💡 Pour configurer Google Drive:")
        logger.info("   1. Créer un projet Google Cloud")
        logger.info("   2. Activer l'API Google Drive") 
        logger.info("   3. Créer un Service Account")
        logger.info("   4. Extraire chaque champ du JSON vers les variables d'environnement")
        logger.info("   5. Utiliser /drive_config pour diagnostic détaillé")
    
    logger.info(f"🎌 Commandes chargées: {len(COMMANDS)}")
    logger.info(f"📋 Liste: {list(COMMANDS.keys())}")
    logger.info(f"🤖 Mistral AI ready: {bool(MISTRAL_API_KEY)}")
    logger.info(f"💾 Système de mémoire: Activé (10 messages) {'+ Google Drive' if drive_service else '+ Local seulement'}")
    logger.info(f"📢 Système de broadcast: {'🔐 Sécurisé admin' if ADMIN_IDS else '⚠️ Non sécurisé'}")
    logger.info(f"🔐 Administrateurs: {len(ADMIN_IDS)} configurés - {list(ADMIN_IDS)}")
    logger.info(f"👥 Utilisateurs en mémoire: {len(user_list)}")
    
    def delayed_startup_notification():
        time.sleep(5)
        send_startup_notification()
    
    notification_thread = threading.Thread(target=delayed_startup_notification)
    notification_thread.daemon = True
    notification_thread.start()
    
    app.run(host="0.0.0.0", port=port, debug=False)
