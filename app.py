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
JSONBIN_API_KEY = "$2a$10$XUdDdy6MCxieCkCAWObx4ePMOlywZwUomubwIamPKO3QJ1aJyY8dO"
JSONBIN_BIN_ID = os.getenv("JSONBIN_BIN_ID", "")
ADMIN_IDS = set(id.strip() for id in os.getenv("ADMIN_IDS", "").split(",") if id.strip())

# Mémoire et état du jeu
user_memory = defaultdict(lambda: deque(maxlen=10))
user_list = set()
game_sessions = {}

# Variables globales pour le stockage
_saving_lock = threading.Lock()
_last_save_time = 0
_save_needed = False

class JSONBinStorage:
    """Classe pour gérer le stockage JSONBin.io avec corrections"""
    
    def __init__(self, api_key, bin_id=None):
        self.api_key = api_key
        self.bin_id = bin_id
        self.base_url = "https://api.jsonbin.io/v3"
        self.headers = {
            "Content-Type": "application/json",
            "X-Master-Key": api_key
        }
        logger.info(f"🔧 JSONBin initialisé avec bin_id: {bin_id}")
    
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
            headers = self.headers.copy()
            headers["X-Bin-Private"] = "true"
            headers["X-Bin-Name"] = "NakamaBot-Data"
            
            logger.info("📦 Création d'un nouveau bin JSONBin...")
            response = requests.post(
                f"{self.base_url}/b",
                headers=headers,
                json=data,
                timeout=20
            )
            
            logger.info(f"🔍 Réponse création bin: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                self.bin_id = result['metadata']['id']
                logger.info(f"✅ Nouveau bin JSONBin créé: {self.bin_id}")
                logger.info(f"🔑 IMPORTANT: Ajoutez cette variable d'environnement: JSONBIN_BIN_ID={self.bin_id}")
                return True
            else:
                logger.error(f"❌ Erreur création bin: {response.status_code}")
                logger.error(f"Réponse: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Erreur création bin: {e}")
            return False
    
    def save_data(self, data):
        """Sauvegarder avec gestion d'erreurs améliorée"""
        if not self.bin_id:
            logger.warning("⚠️ Pas de bin_id, création automatique...")
            if not self.create_bin(data):
                return False
        
        try:
            # Préparer les données sérialisables
            serializable_data = self._make_serializable(data)
            
            data_to_save = {
                **serializable_data,
                'timestamp': datetime.now().isoformat(),
                'version': '3.0',
                'creator': 'Durand'
            }
            
            # Test de sérialisation
            json.dumps(data_to_save)
            logger.info("📦 Préparation des données pour sauvegarde...")
            
        except Exception as e:
            logger.error(f"❌ Erreur préparation données: {e}")
            return False
        
        # Sauvegarde avec retry
        max_retries = 3
        for attempt in range(max_retries):
            try:
                logger.info(f"💾 Tentative de sauvegarde {attempt + 1}/{max_retries}...")
                
                response = requests.put(
                    f"{self.base_url}/b/{self.bin_id}",
                    headers=self.headers,
                    json=data_to_save,
                    timeout=25
                )
                
                logger.info(f"🔍 Status sauvegarde: {response.status_code}")
                
                if response.status_code == 200:
                    logger.info("✅ Données sauvegardées avec succès sur JSONBin!")
                    return True
                elif response.status_code == 401:
                    logger.error("❌ Clé API JSONBin invalide")
                    return False
                elif response.status_code == 404:
                    logger.warning("⚠️ Bin introuvable, création d'un nouveau...")
                    self.bin_id = None
                    return self.save_data(data)
                else:
                    logger.warning(f"⚠️ Erreur {response.status_code}: {response.text}")
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 3
                        logger.info(f"⏳ Attente {wait_time}s avant retry...")
                        time.sleep(wait_time)
                        continue
                        
            except requests.Timeout:
                logger.warning(f"⏱️ Timeout tentative {attempt + 1}")
                if attempt < max_retries - 1:
                    time.sleep((attempt + 1) * 2)
                    continue
            except Exception as e:
                logger.error(f"❌ Erreur sauvegarde: {e}")
                if attempt < max_retries - 1:
                    time.sleep((attempt + 1) * 2)
                    continue
                break
        
        logger.error("❌ Échec de toutes les tentatives de sauvegarde")
        return False
    
    def load_data(self):
        """Charger les données avec validation"""
        if not self.bin_id:
            logger.warning("⚠️ Pas de bin_id pour le chargement")
            return None
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                logger.info(f"📥 Tentative de chargement {attempt + 1}/{max_retries}...")
                
                response = requests.get(
                    f"{self.base_url}/b/{self.bin_id}/latest",
                    headers=self.headers,
                    timeout=20
                )
                
                logger.info(f"🔍 Status chargement: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()['record']
                    if self._validate_data(data):
                        logger.info(f"✅ Données chargées (v{data.get('version', '1.0')})")
                        return data
                    else:
                        logger.warning("⚠️ Données invalides")
                        return None
                        
                elif response.status_code == 401:
                    logger.error("❌ Clé API invalide")
                    return None
                elif response.status_code == 404:
                    logger.error("❌ Bin introuvable")
                    return None
                else:
                    logger.warning(f"⚠️ Erreur {response.status_code}")
                    if attempt < max_retries - 1:
                        time.sleep((attempt + 1) * 2)
                        continue
                        
            except Exception as e:
                logger.warning(f"❌ Erreur chargement: {e}")
                if attempt < max_retries - 1:
                    time.sleep((attempt + 1) * 2)
                    continue
                break
        
        logger.error("❌ Échec chargement après tous les essais")
        return None
    
    def _make_serializable(self, data):
        """Convertir en format JSON sérialisable"""
        serializable = {}
        
        # Convertir user_memory
        if 'user_memory' in data:
            serializable['user_memory'] = {}
            for user_id, messages in data['user_memory'].items():
                if hasattr(messages, '__iter__'):
                    serializable['user_memory'][str(user_id)] = list(messages)
                else:
                    serializable['user_memory'][str(user_id)] = []
        
        # Convertir user_list
        if 'user_list' in data:
            if hasattr(data['user_list'], '__iter__'):
                serializable['user_list'] = list(data['user_list'])
            else:
                serializable['user_list'] = []
        
        # Copier game_sessions
        if 'game_sessions' in data:
            serializable['game_sessions'] = dict(data['game_sessions'])
        
        return serializable
    
    def _validate_data(self, data):
        """Valider la structure des données"""
        if not isinstance(data, dict):
            logger.warning("❌ Données ne sont pas un dictionnaire")
            return False
        
        required_fields = ['user_memory', 'user_list', 'game_sessions']
        for field in required_fields:
            if field not in data:
                logger.warning(f"❌ Champ manquant: {field}")
                return False
        
        return True

# Initialiser le stockage
storage = None

def init_jsonbin_storage():
    """Initialiser JSONBin avec validation complète et diagnostics détaillés"""
    global storage
    
    logger.info("🔧 Début initialisation JSONBin...")
    logger.info(f"🔍 JSONBIN_API_KEY présente: {'✅' if JSONBIN_API_KEY else '❌'}")
    logger.info(f"🔍 JSONBIN_BIN_ID présent: {'✅' if JSONBIN_BIN_ID else '❌'}")
    
    if not JSONBIN_API_KEY:
        logger.error("❌ JSONBIN_API_KEY manquante dans les variables d'environnement!")
        logger.error("💡 Vérifiez que la variable est bien définie dans votre environnement")
        storage = None
        return False
    
    try:
        # Créer l'instance de stockage
        logger.info("🏗️ Création de l'instance JSONBinStorage...")
        storage = JSONBinStorage(JSONBIN_API_KEY, JSONBIN_BIN_ID)
        logger.info("✅ Instance JSONBinStorage créée")
        
        # Test de connectivité réseau de base
        logger.info("🌐 Test de connectivité réseau...")
        try:
            test_response = requests.get("https://httpbin.org/status/200", timeout=5)
            logger.info("✅ Connectivité réseau OK")
        except:
            logger.warning("⚠️ Problème de connectivité réseau détecté")
        
        # Test de la clé API
        logger.info("🔑 Test de la clé API JSONBin...")
        test_headers = {"X-Master-Key": JSONBIN_API_KEY}
        
        try:
            test_response = requests.get(
                "https://api.jsonbin.io/v3/b",
                headers=test_headers,
                timeout=15
            )
            
            logger.info(f"🔍 Réponse test API: {test_response.status_code}")
            
            if test_response.status_code == 401:
                logger.error("❌ Clé API JSONBin invalide ou expirée!")
                logger.error("💡 Vérifiez votre clé sur jsonbin.io")
                storage = None
                return False
            elif test_response.status_code == 200:
                logger.info("✅ Clé API JSONBin validée")
            else:
                logger.warning(f"⚠️ Réponse inattendue de l'API: {test_response.status_code}")
                # Continuer quand même, parfois l'API peut retourner d'autres codes
                
        except requests.Timeout:
            logger.error("❌ Timeout lors du test de la clé API")
            logger.warning("⚠️ Continuons quand même...")
        except Exception as e:
            logger.error(f"❌ Erreur test clé API: {e}")
            logger.warning("⚠️ Continuons quand même...")
        
        # Si bin_id existe, tester le chargement
        if JSONBIN_BIN_ID and JSONBIN_BIN_ID.strip():
            logger.info(f"🔍 Test du bin existant: {JSONBIN_BIN_ID}")
            try:
                test_data = storage.load_data()
                if test_data is not None:
                    logger.info("✅ JSONBin connecté au bin existant avec succès!")
                    return True
                else:
                    logger.warning("⚠️ Bin inaccessible ou vide, création d'un nouveau...")
            except Exception as e:
                logger.warning(f"⚠️ Erreur test bin existant: {e}")
                logger.info("🔄 Tentative de création d'un nouveau bin...")
        else:
            logger.info("ℹ️ Pas de bin_id fourni, création d'un nouveau bin...")
        
        # Créer un nouveau bin
        logger.info("🆕 Création d'un nouveau bin JSONBin...")
        try:
            if storage.create_bin():
                logger.info("✅ JSONBin initialisé avec succès! Nouveau bin créé.")
                logger.info(f"📝 IMPORTANT: Notez ce bin_id pour la prochaine fois: {storage.bin_id}")
                return True
            else:
                logger.error("❌ Impossible de créer un nouveau bin")
                storage = None
                return False
        except Exception as e:
            logger.error(f"❌ Erreur création bin: {e}")
            storage = None
            return False
            
    except Exception as e:
        logger.error(f"❌ Erreur générale initialisation JSONBin: {e}")
        logger.error(f"🔍 Type d'erreur: {type(e).__name__}")
        storage = None
        return False

def save_to_storage(force=False):
    """Sauvegarde avec diagnostics améliorés"""
    global _last_save_time, _save_needed
    
    # Vérification de l'état du stockage
    if storage is None:
        logger.error("❌ Stockage non initialisé - storage = None")
        logger.error("💡 Vérifiez les variables JSONBIN_API_KEY et l'initialisation")
        return False
    
    if not hasattr(storage, 'bin_id') or not storage.bin_id:
        logger.error("❌ Pas de bin_id configuré dans storage")
        logger.error("💡 Le stockage semble mal initialisé")
        return False
    
    current_time = time.time()
    
    # Throttling (sauf si forcé)
    if not force and current_time - _last_save_time < 10:
        logger.debug("🔄 Sauvegarde throttled")
        _save_needed = True
        return True
    
    with _saving_lock:
        try:
            logger.info(f"💾 Démarrage sauvegarde (bin_id: {storage.bin_id})...")
            
            data = {
                'user_memory': dict(user_memory),
                'user_list': user_list,
                'game_sessions': game_sessions
            }
            
            logger.info(f"📦 Données à sauvegarder: {len(data['user_list'])} users, {len(data['user_memory'])} conversations")
            
            success = storage.save_data(data)
            if success:
                _last_save_time = current_time
                _save_needed = False
                logger.info("✅ Sauvegarde réussie!")
            else:
                logger.error("❌ Échec de la sauvegarde")
            
            return success
            
        except Exception as e:
            logger.error(f"❌ Erreur sauvegarde: {e}")
            logger.error(f"🔍 État storage: {storage}")
            logger.error(f"🔍 bin_id: {getattr(storage, 'bin_id', 'UNDEFINED')}")
            return False

def load_from_storage():
    """Chargement avec diagnostics détaillés"""
    global user_memory, user_list, game_sessions
    
    if storage is None:
        logger.error("❌ Stockage non initialisé pour le chargement")
        return False
    
    if not hasattr(storage, 'bin_id') or not storage.bin_id:
        logger.error("❌ Pas de bin_id pour le chargement")
        return False
    
    try:
        logger.info(f"📥 Chargement depuis bin_id: {storage.bin_id}...")
        data = storage.load_data()
        if not data:
            logger.info("📁 Aucune donnée à charger (bin vide ou nouveau)")
            return False
        
        logger.info("🔄 Reconstruction des structures de données...")
        
        # Reconstruire user_memory
        user_memory.clear()
        loaded_memory = data.get('user_memory', {})
        for user_id, messages in loaded_memory.items():
            if isinstance(messages, list):
                valid_messages = []
                for msg in messages:
                    if isinstance(msg, dict) and 'type' in msg and 'content' in msg:
                        valid_messages.append(msg)
                user_memory[str(user_id)] = deque(valid_messages, maxlen=10)
        
        # Reconstruire user_list
        user_list.clear()
        loaded_users = data.get('user_list', [])
        if isinstance(loaded_users, list):
            for uid in loaded_users:
                if uid:
                    user_list.add(str(uid))
        
        # Reconstruire game_sessions
        game_sessions.clear()
        loaded_games = data.get('game_sessions', {})
        if isinstance(loaded_games, dict):
            game_sessions.update(loaded_games)
        
        logger.info(f"📊 Données restaurées avec succès:")
        logger.info(f"  👥 {len(user_list)} utilisateurs")
        logger.info(f"  💾 {len(user_memory)} conversations") 
        logger.info(f"  🎲 {len(game_sessions)} jeux actifs")
        logger.info(f"  📅 Version: {data.get('version', '1.0')}")
        logger.info(f"  🕐 Timestamp: {data.get('timestamp', 'N/A')}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Erreur chargement: {e}")
        logger.error(f"🔍 État storage: {storage}")
        logger.error(f"🔍 bin_id: {getattr(storage, 'bin_id', 'UNDEFINED')}")
        return False

def auto_save():
    """Système de sauvegarde automatique optimisé"""
    global _save_needed
    
    logger.info("🔄 Auto-save démarré")
    
    while True:
        try:
            time.sleep(120)  # Vérifier toutes les 2 minutes
            
            # Sauvegarder si nécessaire ou périodiquement
            if _save_needed or time.time() - _last_save_time > 300:  # 5 minutes max
                if user_memory or user_list or game_sessions:
                    logger.info("🔄 Déclenchement auto-save...")
                    save_to_storage(force=True)
                    
        except Exception as e:
            logger.error(f"❌ Erreur auto-save: {e}")
            time.sleep(60)

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
    """Ajouter à la mémoire avec déclenchement de sauvegarde"""
    global _save_needed
    
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
    
    # Marquer qu'une sauvegarde est nécessaire
    _save_needed = True
    
    # Déclencher sauvegarde immédiate parfois
    if random.random() < 0.05:  # 5% de chance
        threading.Thread(target=lambda: save_to_storage(), daemon=True).start()

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


# Dictionnaire global pour empêcher les broadcasts en double
_broadcast_locks = {}
_broadcast_history = {}

def broadcast_message(text):
    """Diffusion de messages avec protection contre les envois multiples"""
    if not text or not user_list:
        return {"sent": 0, "total": 0, "errors": 0}
    
    # Créer une signature unique pour ce message
    message_signature = f"{hash(text)}_{len(user_list)}"
    current_time = time.time()
    
    # Vérifier si ce message exact a déjà été envoyé récemment (dans les 30 dernières secondes)
    if message_signature in _broadcast_history:
        last_sent_time = _broadcast_history[message_signature]
        if current_time - last_sent_time < 30:  # 30 secondes de protection
            logger.warning(f"🚫 Broadcast dupliqué bloqué! Signature: {message_signature}")
            return {"sent": 0, "total": 0, "errors": 0, "blocked": True}
    
    # Vérifier si un broadcast est déjà en cours avec un lock
    if message_signature in _broadcast_locks:
        logger.warning(f"🚫 Broadcast déjà en cours! Signature: {message_signature}")
        return {"sent": 0, "total": 0, "errors": 0, "already_running": True}
    
    # Créer un lock pour ce broadcast
    _broadcast_locks[message_signature] = threading.Lock()
    
    try:
        with _broadcast_locks[message_signature]:
            # Marquer ce message comme envoyé
            _broadcast_history[message_signature] = current_time
            
            # Nettoyer l'historique (garder seulement les 10 derniers)
            if len(_broadcast_history) > 10:
                oldest_key = min(_broadcast_history.keys(), key=lambda k: _broadcast_history[k])
                del _broadcast_history[oldest_key]
            
            success = 0
            errors = 0
            total_users = len(user_list)
            
            logger.info(f"📢 Début broadcast unique vers {total_users} utilisateurs")
            logger.info(f"🔒 Signature: {message_signature}")
            
            for user_id in list(user_list):  # Copie pour éviter la modification pendant l'itération
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
            
    finally:
        # Nettoyer le lock après utilisation
        if message_signature in _broadcast_locks:
            del _broadcast_locks[message_signature]


##################IMAGES###########################
def cmd_image(sender_id, args=""):
    """Générateur d'images anime/otaku gratuites"""
    if not args.strip():
        return """🎨🎌 GÉNÉRATEUR D'IMAGES OTAKU! 🎌🎨

🖼️ /image [description] - Génère une image
🎨 /image anime girl pink hair - Exemple
🌸 /image kawaii cat with sword - Exemple  
⚡ /image random - Image aléatoire

✨ Décris ton rêve otaku nakama! 🎭"""
    
    prompt = args.strip().lower()
    sender_id = str(sender_id)
    
    # Images aléatoires si demandé
    if prompt == "random":
        random_prompts = [
            "anime girl with blue hair and katana",
            "kawaii cat girl in school uniform", 
            "epic dragon in anime style",
            "cute anime boy with glasses",
            "magical girl transformation",
            "ninja in cherry blossom forest",
            "robot mech in cyberpunk city",
            "anime princess with crown"
        ]
        prompt = random.choice(random_prompts)
    
    try:
        # Nettoyer et formater le prompt
        clean_prompt = prompt.replace(' ', '+').replace(',', '%2C')
        
        # Utiliser l'API gratuite Picsum + overlay text pour simuler la génération
        # En réalité, on utilise une API de placeholder avec du texte
        base_url = "https://picsum.photos/512/512"
        
        # Alternative: utiliser une vraie API gratuite comme Pollinations
        # Cette API est gratuite et génère de vraies images à partir de prompts
        image_url = f"https://image.pollinations.ai/prompt/{clean_prompt}?width=512&height=512&seed={random.randint(1, 10000)}"
        
        # Créer la réponse avec l'URL de l'image
        response = f"""🎨✨ IMAGE GÉNÉRÉE! ✨🎨

🖼️ Prompt: {prompt}
🌸 Voici ton image otaku nakama!

{image_url}

🎭 Tape /image pour une nouvelle création!
⚡ Ou /image random pour surprendre! 💖"""
        
        # Ajouter à la mémoire qu'une image a été générée
        add_to_memory(sender_id, 'bot', f"Image générée: {prompt}")
        
        return response
        
    except Exception as e:
        logger.error(f"❌ Erreur génération image: {e}")
        return """🎨💥 Erreur de génération!

🔧 Les serveurs d'images sont occupés!
⚡ Retry dans quelques secondes nakama!
🎌 Ou essaie /image random! ✨"""

# Alternative avec une vraie API de génération d'images gratuite
def cmd_image_advanced(sender_id, args=""):
    """Version avancée avec vraie génération d'images"""
    if not args.strip():
        return """🎨🎌 AI IMAGE GENERATOR! 🎌🎨

🖼️ /image [description] - Génère une image IA
🎨 Styles: anime, kawaii, cyberpunk, fantasy
🌸 Exemple: /image anime girl pink hair magic
⚡ /image random - Surprise aléatoire

✨ Décris ton monde otaku nakama! 🎭"""
    
    prompt = args.strip()
    sender_id = str(sender_id)
    
    if prompt.lower() == "random":
        random_prompts = [
            "beautiful anime girl with long blue hair holding a glowing sword",
            "kawaii neko girl in magical school uniform with sparkles",
            "epic mecha robot in futuristic cyberpunk city at sunset", 
            "cute anime boy with glasses reading a magic book",
            "magical girl transformation with rainbow energy aura",
            "ninja warrior in cherry blossom forest with katana",
            "dragon girl with horns and wings in fantasy landscape",
            "anime princess with crown in crystal palace"
        ]
        prompt = random.choice(random_prompts)
    
    try:
        # Optimiser le prompt pour l'anime
        enhanced_prompt = f"anime style, {prompt}, high quality, detailed, colorful, kawaii"
        
        # Encoder le prompt pour l'URL
        import urllib.parse
        encoded_prompt = urllib.parse.quote(enhanced_prompt)
        
        # Utiliser l'API Pollinations (gratuite et sans limite)
        seed = random.randint(1, 999999)
        image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=768&height=768&seed={seed}&enhance=true"
        
        # Créer la réponse
        response = f"""🎨⚡ IMAGE IA GÉNÉRÉE! ⚡🎨

🖼️ "{prompt}"
🎌 Style: Anime Optimisé
🌸 Seed: {seed}

{image_url}

✨ Sauvegarde ton image nakama!
🎭 /image pour une nouvelle création! 💖"""
        
        return response
        
    except Exception as e:
        logger.error(f"❌ Erreur génération image avancée: {e}")
        return """🎨💥 Erreur IA temporaire!

🔧 L'intelligence artificielle se repose!
⚡ Essaie /image random ou retry!
🎌 Ton image arrive bientôt! ✨"""

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

# Fonction helper pour valider les prompts
def validate_image_prompt(prompt):
    """Valider et nettoyer les prompts d'images"""
    if not prompt or len(prompt.strip()) < 3:
        return False, "Prompt trop court! Minimum 3 caractères! 📝"
    
    if len(prompt) > 200:
        return False, "Prompt trop long! Maximum 200 caractères! ✂️"
    
    # Mots interdits (optionnel, pour éviter le contenu inapproprié)
    forbidden_words = ['nsfw', 'nude', 'explicit', 'xxx']
    for word in forbidden_words:
        if word in prompt.lower():
            return False, "🚫 Contenu inapproprié détecté! Reste kawaii! 🌸"
    
    return True, prompt.strip()

# Version finale optimisée pour le bot
def cmd_image_final(sender_id, args=""):
    """Commande image finale optimisée pour NakamaBot"""
    if not args.strip():
        return """🎨🎌 NAKAMABOT IMAGE AI! 🎌🎨

🖼️ /image [description] - Génère ton image
🎨 /image anime girl blue hair - Exemple
🌸 /image kawaii cat ninja - Exemple
⚡ /image random - Surprise otaku
🎭 /image styles - Voir les styles

✨ Imagine, je crée nakama! 💖"""
    
    prompt = args.strip().lower()
    sender_id = str(sender_id)
    
    # Commandes spéciales
    if prompt == "styles":
        return """🎨 STYLES DISPONIBLES:

🌸 anime - Style anime classique
⚡ kawaii - Super mignon
🔥 cyberpunk - Futuriste néon
🌙 fantasy - Monde magique
🗾 traditional - Art japonais
🤖 mecha - Robots géants
👘 kimono - Style traditionnel
🌈 colorful - Explosion de couleurs

💡 Combine les styles: "anime cyberpunk girl" ✨"""
    
    if prompt == "random":
        themes = [
            "anime girl with magical powers and glowing eyes",
            "kawaii cat wearing samurai armor in bamboo forest", 
            "cyberpunk ninja with neon katana in tokyo streets",
            "cute anime boy with dragon companion",
            "magical girl in sailor outfit with moon tiara",
            "mecha pilot girl in futuristic cockpit",
            "fox girl shrine maiden with spiritual energy",
            "anime princess with crystal wings in castle"
        ]
        prompt = random.choice(themes)
    
    # Valider le prompt
    is_valid, validated_prompt = validate_image_prompt(prompt)
    if not is_valid:
        return f"❌ {validated_prompt}"
    
    try:
        # Améliorer le prompt automatiquement
        enhanced_prompt = f"anime style, high quality, detailed, {validated_prompt}, beautiful, kawaii aesthetic"
        
        # Encoder pour l'URL
        import urllib.parse
        encoded_prompt = urllib.parse.quote(enhanced_prompt)
        
        # Générer l'image
        seed = random.randint(100000, 999999)
        image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=768&height=768&seed={seed}&enhance=true&model=flux"
        
        # Sauvegarder dans la mémoire
        add_to_memory(sender_id, 'user', f"Image demandée: {validated_prompt}")
        add_to_memory(sender_id, 'bot', f"Image générée pour: {validated_prompt}")
        
        # Retourner directement l'URL de l'image avec un message simple
        return {
            "type": "image",
            "url": image_url,
            "caption": f"🎨✨ Voici ton image otaku nakama!\n\n🖼️ \"{validated_prompt}\"\n\n🎌 Tape /image pour une nouvelle création! ⚡"
        }
        
    except Exception as e:
        logger.error(f"❌ Erreur génération image: {e}")
        return """🎨💥 Erreur temporaire!

🔧 L'IA artistique se repose un moment!
⚡ Retry dans 10 secondes nakama!
🎲 Ou essaie /image random! 

🌸 Tes images arrivent bientôt! ✨"""
###########################################


def cmd_broadcast(sender_id, args=""):
    """Diffusion admin avec protection anti-spam renforcée"""
    if not is_admin(sender_id):
        return f"🔐 Accès refusé! Admins seulement! ❌\nTon ID: {sender_id}"
    
    if not args.strip():
        return f"""📢 COMMANDE BROADCAST
Usage: /broadcast [message]

📊 État actuel:
• Utilisateurs: {len(user_list)}
• Broadcasts récents: {len(_broadcast_history)}

⚠️ Protection anti-spam activée (30s entre messages identiques)
🔐 Commande admin uniquement"""
    
    message_text = args.strip()
    
    # Vérifications de sécurité
    if len(message_text) > 1800:
        return "❌ Message trop long! Maximum 1800 caractères."
    
    if not user_list:
        return "📢 Aucun utilisateur à notifier! Liste vide."
    
    # Créer le message final
    formatted_message = f"📢🎌 ANNONCE NAKAMA!\n\n{message_text}\n\n⚡ Message officiel de Durand 💖"
    
    # Log de l'action admin AVANT l'envoi
    logger.info(f"📢 Admin {sender_id} demande broadcast: '{message_text[:50]}...'")
    
    # Vérifier si c'est un doublon récent
    message_signature = f"{hash(formatted_message)}_{len(user_list)}"
    current_time = time.time()
    
    if message_signature in _broadcast_history:
        last_sent = _broadcast_history[message_signature]
        time_diff = current_time - last_sent
        if time_diff < 30:
            return f"🚫 Message identique envoyé il y a {int(time_diff)}s! Attendez {int(30-time_diff)}s."
    
    try:
        # Envoyer le broadcast (UNE SEULE FOIS)
        result = broadcast_message(formatted_message)
        
        # Vérifier si c'était bloqué
        if result.get("blocked"):
            return "🚫 Broadcast bloqué - message identique détecté!"
        
        if result.get("already_running"):
            return "🚫 Un broadcast identique est déjà en cours!"
        
        # Calculer le taux de succès
        success_rate = (result['sent'] / result['total'] * 100) if result['total'] > 0 else 0
        
        response = f"""📊 BROADCAST ENVOYÉ!

✅ Succès: {result['sent']}
📱 Total: {result['total']}
❌ Erreurs: {result['errors']}
📈 Taux: {success_rate:.1f}%

🔒 Message protégé contre les doublons pendant 30s"""

        if result['sent'] == 0:
            response += "\n\n💡 Aucun envoi! Vérifiez la connectivité."
        
        return response
        
    except Exception as e:
        logger.error(f"❌ Erreur critique broadcast: {e}")
        return f"💥 Erreur: {str(e)[:100]}"
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
    sender_id = str(sender_id)
    
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
            "Quel personnage d'anime ressemble le plus à toi? 🪞",
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
        "content": "Tu es NakamaBot, créé par Durand. Tu es un bot otaku kawaii et énergique Nous sommes en 2025 ainsi que que ta base de donées. Présente-toi avec joie en français, mentionne ton créateur Durand si on te le demande. Utilise des emojis anime. INTERDIT: aucune description d'action entre *étoiles*. Parle directement, maximum 300 caractères."
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
        "content": "Tu es NakamaBot, créé par Durand. IA otaku kawaii Nous sommes en 2025 ainsi que que ta base de donées. Réponds en français avec des emojis anime. Si on demande ton créateur, c'est Durand. STRICTEMENT INTERDIT: aucune description d'action entre *étoiles*. Parle directement comme un vrai personnage, maximum 400 caractères."
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
    sender_id = str(sender_id)
    if not user_memory.get(sender_id):
        return "💾 Aucune conversation précédente! C'est notre premier échange! ✨"
    
    text = "💾🎌 MÉMOIRE DE NOS AVENTURES!\n\n"
    for i, msg in enumerate(user_memory[sender_id], 1):
        emoji = "🗨️" if msg['type'] == 'user' else "🤖"
        preview = msg['content'][:60] + "..." if len(msg['content']) > 60 else msg['content']
        text += f"{emoji} {i}. {preview}\n"
    
    text += f"\n💭 {len(user_memory[sender_id])}/10 messages"
    
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
        return f"""🔐 PANNEAU ADMIN v3.0
• /admin stats - Statistiques
• /admin save - Force sauvegarde
• /admin load - Recharge données
• /admin games - Stats jeux
• /admin test - Test connexions
• /broadcast [msg] - Diffusion

📊 ÉTAT:
Utilisateurs: {len(user_list)}
Mémoire: {len(user_memory)}
Jeux actifs: {len(game_sessions)}
Stockage: {'✅' if storage else '❌'}"""
    
    action = args.strip().lower()
    
    if action == "stats":
        return f"""📊 STATISTIQUES COMPLÈTES
👥 Utilisateurs: {len(user_list)}
💾 Conversations: {len(user_memory)}
🎲 Jeux actifs: {len(game_sessions)}
🌐 Stockage: {'✅' if storage else '❌'}
🔐 Admin ID: {sender_id}
👨‍💻 Créateur: Durand
📝 Version: 3.0"""
    
    elif action == "save":
        success = save_to_storage(force=True)
        return f"{'✅ Sauvegarde réussie!' if success else '❌ Échec sauvegarde!'}"
    
    elif action == "load":
        success = load_from_storage()
        return f"{'✅ Chargement réussi!' if success else '❌ Échec chargement!'}"
    
    elif action == "games":
        if not game_sessions:
            return "🎲 Aucun jeu actif!"
        
        text = "🎲 JEUX ACTIFS:\n"
        for user_id, session in list(game_sessions.items()):
            score = session.get('score', 0)
            text += f"👤 {user_id}: {score} pts\n"
        return text
    
    elif action == "test":
        results = []
        
        # Test stockage
        if storage:
            test_data = storage.load_data()
            results.append(f"Stockage: {'✅' if test_data is not None else '❌'}")
        else:
            results.append("Stockage: ❌ Non initialisé")
        
        # Test Mistral
        if MISTRAL_API_KEY:
            test_response = call_mistral_api([{"role": "user", "content": "Test"}], max_tokens=10)
            results.append(f"IA: {'✅' if test_response else '❌'}")
        else:
            results.append("IA: ❌ Pas de clé")
        
        # Test Facebook
        results.append(f"Facebook: {'✅' if PAGE_ACCESS_TOKEN else '❌'}")
        
        return "🔍 TESTS CONNEXIONS:\n" + "\n".join(results)
    
    return f"❓ Action '{action}' inconnue!"

def cmd_help(sender_id, args=""):
    """Aide du bot (simplifiée)"""
    commands = {
    "/start": "🌟 Présentation du bot",
    "/ia [message]": "🧠 Chat libre avec IA",
    "/story [theme]": "📖 Histoires anime/manga",
    "/waifu": "👸 Génère ta waifu",
    "/actionverite": "🎲 Jeu Action ou Vérité",
    "/image [prompt]": "🎨 Génère des images AI",  # 👈 AJOUTER
    "/memory": "💾 Voir l'historique",
    "/help": "❓ Cette aide"
    }
    
    text = "🎌⚡ NAKAMABOT v3.0 GUIDE! ⚡🎌\n\n"
    for cmd, desc in commands.items():
        text += f"{cmd} - {desc}\n"
    
    if is_admin(sender_id):
        text += "\n🔐 ADMIN:\n/admin - Panneau admin\n/broadcast - Diffusion"
    
    text += "\n👨‍💻 Créé par Durand"
    text += "\n✨ Ton compagnon otaku kawaii! 💖"
    return text

# Dictionnaire des commandes
COMMANDS = {
    'start': cmd_start,
    'ia': cmd_ia,
    'story': cmd_story,
    'waifu': cmd_waifu,
    'actionverite': cmd_actionverite,
    'image': cmd_image_final,  # 👈 AJOUTER CETTE LIGNE
    'memory': cmd_memory,
    'broadcast': cmd_broadcast,
    'admin': cmd_admin,
    'help': cmd_help
}

def process_command(sender_id, message_text):
    """Traiter les commandes utilisateur avec validation"""
    sender_id = str(sender_id)
    
    if not message_text or not isinstance(message_text, str):
        return "🎌 Message vide! Tape /start ou /help! ✨"
    
    message_text = message_text.strip()
    
    if not message_text.startswith('/'):
        return cmd_ia(sender_id, message_text) if message_text else "🎌 Konnichiwa! Tape /start ou /help! ✨"
    
    parts = message_text[1:].split(' ', 1)
    command = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""
    
    if command in COMMANDS:
        try:
            return COMMANDS[command](sender_id, args)
        except Exception as e:
            logger.error(f"❌ Erreur commande {command}: {e}")
            return f"💥 Erreur dans /{command}! Retry onegaishimasu! 🥺"
    
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
        "storage_connected": bool(storage and storage.bin_id),
        "admins": len(ADMIN_IDS),
        "version": "3.0",
        "last_update": datetime.now().isoformat(),
        "endpoints": ["/", "/webhook", "/stats", "/health"],
        "features": ["Chat IA", "Histoires", "Jeu Action/Vérité", "Mémoire", "Broadcast Admin"]
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
                            ###############################################
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
                            #################################################################
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
        "storage_connected": bool(storage and storage.bin_id),
        "version": "3.0",
        "creator": "Durand",
        "last_save": _last_save_time if _last_save_time else "Never"
    })

@app.route("/health", methods=['GET'])
def health():
    """Route de santé pour monitoring"""
    health_status = {
        "status": "healthy",
        "services": {
            "storage": bool(storage and storage.bin_id),
            "ai": bool(MISTRAL_API_KEY),
            "facebook": bool(PAGE_ACCESS_TOKEN)
        },
        "data": {
            "users": len(user_list),
            "conversations": len(user_memory),
            "games": len(game_sessions)
        },
        "timestamp": datetime.now().isoformat()
    }
    
    # Vérifier la santé
    issues = []
    if not storage or not storage.bin_id:
        issues.append("Stockage non connecté")
    if not MISTRAL_API_KEY:
        issues.append("Clé IA manquante")
    if not PAGE_ACCESS_TOKEN:
        issues.append("Token Facebook manquant")
    
    if issues:
        health_status["status"] = "degraded"
        health_status["issues"] = issues
    
    status_code = 200 if health_status["status"] == "healthy" else 503
    return jsonify(health_status), status_code

@app.route("/force-save", methods=['POST'])
def force_save():
    """Route pour forcer une sauvegarde"""
    if request.method == 'POST':
        success = save_to_storage(force=True)
        return jsonify({
            "success": success,
            "message": "Sauvegarde forcée réussie" if success else "Échec sauvegarde forcée",
            "timestamp": datetime.now().isoformat()
        })

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
    if not JSONBIN_API_KEY:
        missing_vars.append("JSONBIN_API_KEY")
    
    if missing_vars:
        logger.error(f"❌ Variables manquantes: {', '.join(missing_vars)}")
        logger.error("🔧 Le bot ne fonctionnera pas correctement!")
    else:
        logger.info("✅ Toutes les variables d'environnement sont présentes")
    
    # Initialiser le stockage avec diagnostics détaillés
    logger.info("🔄 === INITIALISATION DU STOCKAGE ===")
    storage_success = init_jsonbin_storage()
    
    if storage_success:
        logger.info("✅ Stockage JSONBin initialisé avec succès")
        logger.info("📁 Tentative de chargement des données existantes...")
        
        if load_from_storage():
            logger.info("✅ Données restaurées depuis JSONBin")
        else:
            logger.info("ℹ️  Démarrage avec données vides (normal pour le premier lancement)")
        
        # Démarrer l'auto-save
        logger.info("🔄 Démarrage du système de sauvegarde automatique...")
        threading.Thread(target=auto_save, daemon=True).start()
        logger.info("💾 Auto-save activé")
        
        # Test de sauvegarde initiale
        logger.info("🧪 Test de sauvegarde initiale...")
        if save_to_storage(force=True):
            logger.info("✅ Test de sauvegarde réussi")
        else:
            logger.warning("⚠️ Test de sauvegarde échoué")
            
    else:
        logger.error("❌ ÉCHEC D'INITIALISATION DU STOCKAGE!")
        logger.error("⚠️  Le bot fonctionnera SANS sauvegarde!")
        logger.error("🔧 Vérifications à faire:")
        logger.error("   1. Variable JSONBIN_API_KEY définie?")
        logger.error("   2. Connectivité internet OK?")
        logger.error("   3. Clé API JSONBin valide?")
        logger.error("   4. Quotas JSONBin non dépassés?")
        
        # Forcer storage à None pour éviter les erreurs
        storage = None
    # Informations de démarrage
    logger.info(f"🎌 {len(COMMANDS)} commandes chargées")
    logger.info(f"🔐 {len(ADMIN_IDS)} administrateurs configurés")
    
    if storage and storage.bin_id:
        logger.info(f"📦 Bin actif: {storage.bin_id}")
    
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
        if storage:
            logger.info("💾 Sauvegarde finale...")
            save_to_storage(force=True)
            logger.info("👋 Sayonara nakamas!")
    except Exception as e:
        logger.error(f"❌ Erreur critique: {e}")
        raise
