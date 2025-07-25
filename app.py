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

# Variable globale pour éviter les sauvegardes concurrentes
_saving_lock = threading.Lock()
_last_save_time = 0

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
            # Ajouter le header pour créer un bin privé
            headers = self.headers.copy()
            headers["X-Bin-Private"] = "true"
            
            response = requests.post(
                f"{self.base_url}/b",
                headers=headers,
                json=data,
                timeout=15
            )
            
            logger.info(f"🔍 Réponse création bin: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                self.bin_id = result['metadata']['id']
                logger.info(f"✅ Nouveau bin JSONBin créé: {self.bin_id}")
                logger.info(f"🔑 Ajoutez cette variable d'environnement: JSONBIN_BIN_ID={self.bin_id}")
                return True
            else:
                logger.error(f"❌ Erreur création bin: {response.status_code}")
                logger.error(f"Réponse: {response.text}")
                return False
                
        except requests.RequestException as e:
            logger.error(f"❌ Erreur réseau création bin: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Erreur générale création bin: {e}")
            return False
    
    def save_data(self, data):
        """Sauvegarder les données sur JSONBin avec retry"""
        if not self.bin_id:
            logger.warning("⚠️ Pas de bin_id, création automatique...")
            if not self.create_bin(data):
                return False
        
        # Ajouter métadonnées et validation
        try:
            # Validation des données avant sauvegarde
            serializable_data = self._make_serializable(data)
            
            data_to_save = {
                **serializable_data,
                'timestamp': datetime.now().isoformat(),
                'version': '3.0',
                'creator': 'Durand',
                'data_hash': hash(str(serializable_data))  # Pour vérifier l'intégrité
            }
            
            # Test de sérialisation JSON
            json.dumps(data_to_save)
            
        except (TypeError, ValueError) as e:
            logger.error(f"❌ Erreur sérialisation données: {e}")
            return False
        
        # Retry logic avec backoff exponentiel
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.put(
                    f"{self.base_url}/b/{self.bin_id}",
                    headers=self.headers,
                    json=data_to_save,
                    timeout=20
                )
                
                logger.info(f"🔍 Tentative {attempt + 1}: Status {response.status_code}")
                
                if response.status_code == 200:
                    logger.info("✅ Données sauvegardées sur JSONBin")
                    return True
                elif response.status_code == 401:
                    logger.error("❌ Clé API JSONBin invalide ou expirée")
                    return False
                elif response.status_code == 404:
                    logger.warning("⚠️ Bin introuvable, création d'un nouveau...")
                    self.bin_id = None  # Reset bin_id
                    return self.save_data(data)  # Récursion pour créer nouveau bin
                else:
                    logger.warning(f"⚠️ Erreur sauvegarde tentative {attempt + 1}: {response.status_code}")
                    logger.warning(f"Réponse: {response.text[:200]}")
                    
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)  # Backoff exponentiel
                        continue
                        
            except requests.Timeout:
                logger.warning(f"⏱️ Timeout tentative {attempt + 1}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
            except requests.RequestException as e:
                logger.warning(f"🌐 Erreur réseau tentative {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
            except Exception as e:
                logger.error(f"❌ Erreur inattendue sauvegarde: {e}")
                break
        
        logger.error("❌ Échec sauvegarde après tous les essais")
        return False
    
    def load_data(self):
        """Charger les données depuis JSONBin avec retry"""
        if not self.bin_id:
            logger.warning("⚠️ Pas de bin_id configuré")
            return None
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.get(
                    f"{self.base_url}/b/{self.bin_id}/latest",
                    headers=self.headers,
                    timeout=15
                )
                
                logger.info(f"🔍 Chargement tentative {attempt + 1}: Status {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()['record']
                    
                    # Validation des données chargées
                    if self._validate_data(data):
                        logger.info(f"✅ Données chargées depuis JSONBin (v{data.get('version', '1.0')})")
                        return data
                    else:
                        logger.warning("⚠️ Données corrompues détectées")
                        return None
                        
                elif response.status_code == 401:
                    logger.error("❌ Clé API JSONBin invalide")
                    return None
                elif response.status_code == 404:
                    logger.error("❌ Bin introuvable, vérifiez JSONBIN_BIN_ID")
                    return None
                else:
                    logger.warning(f"⚠️ Erreur chargement tentative {attempt + 1}: {response.status_code}")
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                        
            except requests.Timeout:
                logger.warning(f"⏱️ Timeout chargement tentative {attempt + 1}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
            except requests.RequestException as e:
                logger.warning(f"🌐 Erreur réseau chargement tentative {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
            except Exception as e:
                logger.error(f"❌ Erreur inattendue chargement: {e}")
                break
        
        logger.error("❌ Échec chargement après tous les essais")
        return None
    
    def _make_serializable(self, data):
        """Convertir les données en format sérialisable JSON"""
        serializable = {}
        
        # Convertir user_memory (deque -> list)
        if 'user_memory' in data:
            serializable['user_memory'] = {}
            for user_id, messages in data['user_memory'].items():
                serializable['user_memory'][str(user_id)] = list(messages)
        
        # Convertir user_list (set -> list)
        if 'user_list' in data:
            serializable['user_list'] = list(data['user_list'])
        
        # game_sessions devrait déjà être sérialisable
        if 'game_sessions' in data:
            serializable['game_sessions'] = data['game_sessions']
        
        return serializable
    
    def _validate_data(self, data):
        """Valider la structure des données chargées"""
        if not isinstance(data, dict):
            return False
        
        # Vérifications de base
        required_fields = ['user_memory', 'user_list', 'game_sessions']
        for field in required_fields:
            if field not in data:
                logger.warning(f"⚠️ Champ manquant: {field}")
                return False
        
        # Vérifier les types
        if not isinstance(data['user_memory'], dict):
            return False
        if not isinstance(data['user_list'], list):
            return False
        if not isinstance(data['game_sessions'], dict):
            return False
        
        return True
    
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
        except Exception as e:
            logger.error(f"Erreur récupération info bin: {e}")
            return None

# Initialiser le stockage JSONBin
storage = None

def init_jsonbin_storage():
    """Initialiser le stockage JSONBin avec validation"""
    global storage
    
    if not JSONBIN_API_KEY:
        logger.error("❌ JSONBIN_API_KEY manquante dans les variables d'environnement")
        logger.error("🔧 Ajoutez: JSONBIN_API_KEY=votre_cle_api")
        return False
    
    try:
        storage = JSONBinStorage(JSONBIN_API_KEY, JSONBIN_BIN_ID)
        
        # Test de la clé API avec un appel simple
        test_headers = {"X-Master-Key": JSONBIN_API_KEY}
        test_response = requests.get(
            "https://api.jsonbin.io/v3/b",
            headers=test_headers,
            timeout=10
        )
        
        if test_response.status_code == 401:
            logger.error("❌ Clé API JSONBin invalide")
            return False
        
        # Tester la connexion si bin_id existe
        if JSONBIN_BIN_ID:
            logger.info(f"🔍 Test du bin existant: {JSONBIN_BIN_ID}")
            test_data = storage.load_data()
            if test_data is not None:
                logger.info("✅ JSONBin connecté avec succès au bin existant")
                return True
            else:
                logger.warning("⚠️ Bin ID invalide ou inaccessible, création d'un nouveau bin...")
        
        # Créer un nouveau bin si nécessaire
        logger.info("🆕 Création d'un nouveau bin JSONBin...")
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
    """Sauvegarde vers JSONBin avec protection contre les appels concurrents"""
    global _last_save_time
    
    if not storage:
        logger.warning("⚠️ Stockage JSONBin non initialisé")
        return False
    
    # Éviter les sauvegardes trop fréquentes (throttling)
    current_time = time.time()
    if current_time - _last_save_time < 5:  # Minimum 5 secondes entre sauvegardes
        logger.debug("🔄 Sauvegarde ignorée (throttling)")
        return True
    
    with _saving_lock:
        try:
            data = {
                'user_memory': dict(user_memory),  # Convertir defaultdict en dict
                'user_list': user_list,
                'game_sessions': game_sessions
            }
            
            success = storage.save_data(data)
            if success:
                _last_save_time = current_time
            return success
            
        except Exception as e:
            logger.error(f"❌ Erreur sauvegarde: {e}")
            return False

def load_from_storage():
    """Chargement depuis JSONBin avec validation"""
    global user_memory, user_list, game_sessions
    
    if not storage:
        logger.warning("⚠️ Stockage JSONBin non initialisé")
        return False
    
    try:
        data = storage.load_data()
        if not data:
            logger.info("📁 Aucune donnée à charger")
            return False
        
        # Restaurer les données avec vérifications robustes
        user_memory.clear()
        loaded_memory = data.get('user_memory', {})
        for user_id, messages in loaded_memory.items():
            if isinstance(messages, list):
                # Valider chaque message
                valid_messages = []
                for msg in messages:
                    if isinstance(msg, dict) and 'type' in msg and 'content' in msg:
                        valid_messages.append(msg)
                user_memory[user_id] = deque(valid_messages, maxlen=10)
        
        user_list.clear()
        loaded_users = data.get('user_list', [])
        if isinstance(loaded_users, list):
            user_list.update(str(uid) for uid in loaded_users if uid)  # Convertir en string
        
        game_sessions.clear()
        loaded_games = data.get('game_sessions', {})
        if isinstance(loaded_games, dict):
            game_sessions.update(loaded_games)
        
        logger.info(f"📊 Chargé: {len(user_list)} utilisateurs, {len(user_memory)} conversations, {len(game_sessions)} jeux")
        return True
        
    except Exception as e:
        logger.error(f"❌ Erreur chargement: {e}")
        return False

def auto_save():
    """Sauvegarde automatique améliorée avec gestion d'erreurs"""
    save_interval = 300  # 5 minutes
    consecutive_failures = 0
    max_failures = 3
    
    logger.info(f"🔄 Auto-save JSONBin démarré (intervalle: {save_interval}s)")
    
    while True:
        try:
            time.sleep(save_interval)
            
            # Sauvegarder seulement s'il y a des données
            if user_memory or user_list or game_sessions:
                success = save_to_storage()
                
                if success:
                    consecutive_failures = 0
                    logger.info("🔄✅ Auto-save réussi")
                else:
                    consecutive_failures += 1
                    logger.warning(f"🔄❌ Auto-save échoué ({consecutive_failures}/{max_failures})")
                    
                    # Si trop d'échecs consécutifs, augmenter l'intervalle
                    if consecutive_failures >= max_failures:
                        save_interval = min(save_interval * 2, 1800)  # Max 30 minutes
                        logger.warning(f"⚠️ Intervalle auto-save augmenté à {save_interval}s")
                        consecutive_failures = 0
            
        except KeyboardInterrupt:
            logger.info("🛑 Auto-save arrêté")
            break
        except Exception as e:
            logger.error(f"❌ Erreur auto-save: {e}")
            time.sleep(60)  # Attendre 1 minute avant de retry

# API Mistral avec gestion améliorée
def call_mistral_api(messages, max_tokens=200, temperature=0.8):
    """Appel API Mistral optimisé avec retry"""
    if not MISTRAL_API_KEY:
        logger.warning("⚠️ Clé API Mistral manquante")
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
    
    max_retries = 2
    for attempt in range(max_retries):
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
                logger.warning(f"⚠️ Erreur API Mistral: {response.status_code}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                return None
                
        except requests.Timeout:
            logger.warning(f"⏱️ Timeout Mistral tentative {attempt + 1}")
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
        except requests.RequestException as e:
            logger.warning(f"🌐 Erreur réseau Mistral: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
        except Exception as e:
            logger.error(f"❌ Erreur générale Mistral: {e}")
            break
    
    return None

def add_to_memory(user_id, msg_type, content):
    """Ajouter à la mémoire avec sauvegarde async intelligente"""
    # Valider les paramètres
    if not user_id or not msg_type or not content:
        return
    
    # Limiter la taille du contenu
    if len(content) > 2000:
        content = content[:1900] + "...[tronqué]"
    
    user_memory[str(user_id)].append({
        'type': msg_type,
        'content': content,
        'timestamp': datetime.now().isoformat()
    })
    
    # Sauvegarde asynchrone intelligente (pas à chaque message)
    if storage and random.random() < 0.1:  # 10% de chance de déclencher une sauvegarde
        threading.Thread(target=save_to_storage, daemon=True).start()

def get_memory_context(user_id):
    """Obtenir le contexte mémoire pour l'IA"""
    context = []
    for msg in user_memory.get(str(user_id), []):
        role = "user" if msg['type'] == 'user' else "assistant"
        context.append({"role": role, "content": msg['content']})
    return context

def is_admin(user_id):
    """Vérifier si l'utilisateur est admin"""
    return str(user_id) in ADMIN_IDS

def broadcast_message(text):
    """Diffuser un message à tous les utilisateurs"""
    if not text or not user_list:
        return {"sent": 0, "total": 0, "errors": 0}
    
    success = 0
    errors = 0
    for user_id in list(user_list):  # Copie de la liste pour éviter les modifications concurrentes
        try:
            result = send_message(user_id, text)
            if result.get("success"):
                success += 1
            else:
                errors += 1
        except Exception as e:
            logger.error(f"Erreur broadcast vers {user_id}: {e}")
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
    sender_id = str(sender_id)  # Assurer que c'est une string
    
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
    sender_id = str(sender_id)
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
• /admin test - Test connexions
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
        for user_id, session in list(game_sessions.items()):
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
    
    elif action == "test":
        results = []
        
        # Test JSONBin
        if storage:
            test_data = storage.load_data()
            results.append(f"JSONBin: {'✅' if test_data is not None else '❌'}")
        else:
            results.append("JSONBin: ❌ Non initialisé")
        
        # Test Mistral
        if MISTRAL_API_KEY:
            test_response = call_mistral_api([{"role": "user", "content": "Test"}], max_tokens=10)
            results.append(f"Mistral: {'✅' if test_response else '❌'}")
        else:
            results.append("Mistral: ❌ Pas de clé")
        
        # Test Facebook
        results.append(f"Facebook: {'✅' if PAGE_ACCESS_TOKEN else '❌'}")
        
        return "🔍 TESTS CONNEXIONS:\n" + "\n".join(results)
    
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
    """Traiter les commandes utilisateur avec validation"""
    # Convertir sender_id en string pour cohérence
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
            
    except requests.Timeout:
        logger.error("⏱️ Timeout envoi message Facebook")
        return {"success": False, "error": "Timeout"}
    except Exception as e:
        logger.error(f"❌ Erreur envoi message: {e}")
        return {"success": False, "error": str(e)}

# === ROUTES FLASK ===

@app.route("/", methods=['GET'])
def home():
    """Route d'accueil avec informations détaillées"""
    bin_info = storage.get_bin_info() if storage else None
    
    return jsonify({
        "status": "🎌 NakamaBot v3.0 Online! ⚡",
        "creator": "Durand",
        "storage": "JSONBin.io",
        "commands": len(COMMANDS),
        "users": len(user_list),
        "conversations": len(user_memory),
        "active_games": len(game_sessions),
        "jsonbin_connected": bool(storage and storage.bin_id),
        "bin_id": storage.bin_id if storage else None,
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
            logger.warning(f"❌ Échec vérification webhook - Mode: {mode}, Token match: {token == VERIFY_TOKEN}")
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
                        logger.warning("⚠️ Message sans sender_id")
                        continue
                    
                    # Convertir sender_id en string
                    sender_id = str(sender_id)
                    
                    # Ignorer les messages echo du bot
                    if 'message' in event and not event['message'].get('is_echo'):
                        # Ajouter l'utilisateur à la liste
                        user_list.add(sender_id)
                        
                        # Récupérer le texte du message
                        message_text = event['message'].get('text', '').strip()
                        
                        if message_text:  # Ignorer les messages vides
                            logger.info(f"📨 Message de {sender_id}: {message_text[:50]}...")
                            
                            # Ajouter à la mémoire
                            add_to_memory(sender_id, 'user', message_text)
                            
                            # Traiter la commande
                            response = process_command(sender_id, message_text)
                            
                            if response:
                                # Ajouter la réponse à la mémoire
                                add_to_memory(sender_id, 'bot', response)
                                
                                # Envoyer la réponse
                                send_result = send_message(sender_id, response)
                                
                                if send_result.get("success"):
                                    logger.info(f"✅ Réponse envoyée à {sender_id}")
                                else:
                                    logger.warning(f"❌ Échec envoi message à {sender_id}: {send_result.get('error')}")
                            else:
                                logger.warning(f"⚠️ Aucune réponse générée pour {sender_id}")
                        else:
                            logger.debug(f"📭 Message vide ignoré de {sender_id}")
                    else:
                        # Messages non-texte ou echo
                        logger.debug(f"📍 Message non-texte de {sender_id}")
                        
        except json.JSONDecodeError as e:
            logger.error(f"❌ Erreur JSON webhook: {e}")
            return jsonify({"error": "Invalid JSON"}), 400
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
        "storage_type": "JSONBin.io",
        "storage_connected": bool(storage and storage.bin_id),
        "version": "3.0",
        "creator": "Durand",
        "uptime": "N/A",  # Pourrait être calculé si nécessaire
        "last_save": _last_save_time if _last_save_time else "Never"
    })

@app.route("/health", methods=['GET'])
def health():
    """Route de santé pour monitoring"""
    health_status = {
        "status": "healthy",
        "services": {
            "jsonbin": bool(storage and storage.bin_id),
            "mistral": bool(MISTRAL_API_KEY),
            "facebook": bool(PAGE_ACCESS_TOKEN)
        },
        "data": {
            "users": len(user_list),
            "conversations": len(user_memory),
            "games": len(game_sessions)
        },
        "timestamp": datetime.now().isoformat()
    }
    
    # Vérifier la santé des services
    issues = []
    if not storage or not storage.bin_id:
        issues.append("JSONBin non connecté")
    if not MISTRAL_API_KEY:
        issues.append("Clé Mistral manquante")
    if not PAGE_ACCESS_TOKEN:
        issues.append("Token Facebook manquant")
    
    if issues:
        health_status["status"] = "degraded"
        health_status["issues"] = issues
    
    status_code = 200 if health_status["status"] == "healthy" else 503
    return jsonify(health_status), status_code

@app.route("/force-save", methods=['POST'])
def force_save():
    """Route pour forcer une sauvegarde (utile pour debugging)"""
    if request.method == 'POST':
        success = save_to_storage()
        return jsonify({
            "success": success,
            "message": "Sauvegarde forcée réussie" if success else "Échec sauvegarde forcée",
            "timestamp": datetime.now().isoformat()
        })

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
        logger.error(f"❌ Variables d'environnement manquantes: {', '.join(missing_vars)}")
        logger.error("🔧 Le bot ne fonctionnera pas correctement sans ces variables!")
        logger.error("💡 Ajoutez-les dans votre configuration d'hébergement")
    else:
        logger.info("✅ Toutes les variables d'environnement critiques sont présentes")
    
    # Initialiser JSONBin
    logger.info("🔄 Initialisation du stockage JSONBin...")
    if init_jsonbin_storage():
        logger.info("📁 Tentative de chargement des données existantes...")
        if load_from_storage():
            logger.info("✅ Données restaurées avec succès depuis JSONBin")
        else:
            logger.info("ℹ️  Démarrage avec données vides (premier lancement)")
        
        # Démarrer la sauvegarde automatique
        logger.info("🔄 Démarrage du système de sauvegarde automatique...")
        threading.Thread(target=auto_save, daemon=True).start()
        logger.info("💾 Sauvegarde automatique JSONBin activée")
    else:
        logger.warning("⚠️  ATTENTION: Fonctionnement sans sauvegarde JSONBin!")
        logger.warning("🔧 Vérifiez JSONBIN_API_KEY et la connectivité réseau")
    
    # Afficher les informations de configuration
    logger.info(f"🎌 {len(COMMANDS)} commandes chargées: {', '.join(COMMANDS.keys())}")
    logger.info(f"🔐 {len(ADMIN_IDS)} administrateurs configurés")
    
    if storage and storage.bin_id:
        logger.info(f"📦 Bin JSONBin actif: {storage.bin_id}")
    
    logger.info(f"🌐 Serveur Flask démarrant sur le port {port}")
    logger.info("🎯 Endpoints disponibles:")
    logger.info("   • GET  / - Informations du bot")
    logger.info("   • GET  /stats - Statistiques publiques")
    logger.info("   • GET  /health - Santé du système")
    logger.info("   • POST /webhook - Webhook Facebook Messenger")
    logger.info("   • POST /force-save - Sauvegarde forcée")
    
    logger.info("🎉 NakamaBot prêt à servir les nakamas!")
    
    # Démarrer l'application Flask
    try:
        app.run(
            host="0.0.0.0", 
            port=port, 
            debug=False,
            threaded=True
        )
    except KeyboardInterrupt:
        logger.info("🛑 Arrêt du bot demandé")
        # Sauvegarde finale avant arrêt
        if storage:
            logger.info("💾 Sauvegarde finale...")
            save_to_storage()
            logger.info("👋 Sayonara nakamas!")
    except Exception as e:
        logger.error(f"❌ Erreur critique au démarrage: {e}")
        raise
