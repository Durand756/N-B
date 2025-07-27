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

# Mémoire du bot (stockage local uniquement)
user_memory = defaultdict(lambda: deque(maxlen=8))
user_list = set()

def call_mistral_api(messages, max_tokens=200, temperature=0.7):
    """API Mistral avec retry"""
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

def web_search(query):
    """Recherche web pour les informations récentes"""
    try:
        # Simuler une recherche web avec une IA qui connaît 2025
        search_context = f"Recherche web pour '{query}' en 2025. Je peux répondre avec mes connaissances de 2025."
        messages = [{
            "role": "system",
            "content": f"Tu es un assistant de recherche. Nous sommes en 2025. Réponds à cette recherche: '{query}' avec tes connaissances de 2025. Si tu ne sais pas, dis-le clairement. Réponds en français, maximum 300 caractères."
        }]
        
        return call_mistral_api(messages, max_tokens=150, temperature=0.3)
    except Exception as e:
        logger.error(f"❌ Erreur recherche: {e}")
        return "Erreur de recherche, désolé."

def add_to_memory(user_id, msg_type, content):
    """Ajouter à la mémoire"""
    if not user_id or not msg_type or not content:
        return
    
    # Limiter la taille
    if len(content) > 1500:
        content = content[:1400] + "...[tronqué]"
    
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
    """Diffusion de messages"""
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
                
            time.sleep(0.2)  # Éviter le spam
            
            result = send_message(str(user_id), text)
            if result.get("success"):
                success += 1
                logger.debug(f"✅ Broadcast envoyé à {user_id}")
            else:
                errors += 1
                logger.warning(f"❌ Échec broadcast pour {user_id}")
                
        except Exception as e:
            errors += 1
            logger.error(f"❌ Erreur broadcast pour {user_id}: {e}")
    
    logger.info(f"📊 Broadcast terminé: {success} succès, {errors} erreurs")
    return {"sent": success, "total": total_users, "errors": errors}

# === COMMANDES DU BOT ===

def cmd_start(sender_id, args=""):
    """Commande de démarrage"""
    return """🤖 Salut ! Je suis NakamaBot, créé par Durand !

🎨 /image [description] - Je génère des images avec l'IA
💬 /chat [message] - Discussion libre
📊 /stats - Mes statistiques  
❓ /help - Liste des commandes

✨ Je peux créer n'importe quelle image que tu veux ! Essaie /image !"""

def cmd_image(sender_id, args=""):
    """Générateur d'images avec IA"""
    if not args.strip():
        return """🎨 GÉNÉRATEUR D'IMAGES IA

🖼️ /image [votre description] - Génère une image
🎨 /image chat robot futuriste - Exemple
🌸 /image paysage montagne coucher soleil - Exemple  
⚡ /image random - Image aléatoire

✨ Décris ton image et je la crée pour toi !
🎭 Tout style possible : réaliste, cartoon, anime, art...

💡 Astuce : Plus ta description est précise, meilleur sera le résultat !"""
    
    prompt = args.strip()
    sender_id = str(sender_id)
    
    # Images aléatoires si demandé
    if prompt.lower() == "random":
        random_prompts = [
            "beautiful landscape with mountains and lake at sunset",
            "futuristic city with flying cars and neon lights", 
            "cute robot playing guitar in a garden",
            "space explorer on alien planet with two moons",
            "magical forest with glowing trees and fireflies",
            "vintage car racing through desert canyon",
            "underwater city with mermaids and colorful fish",
            "steampunk airship flying above clouds"
        ]
        prompt = random.choice(random_prompts)
    
    # Valider le prompt
    if len(prompt) < 3:
        return "❌ Description trop courte ! Minimum 3 caractères."
    
    if len(prompt) > 200:
        return "❌ Description trop longue ! Maximum 200 caractères."
    
    try:
        # Encoder le prompt pour l'URL
        import urllib.parse
        encoded_prompt = urllib.parse.quote(prompt)
        
        # Générer l'image avec l'API Pollinations
        seed = random.randint(100000, 999999)
        image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=768&height=768&seed={seed}&enhance=true"
        
        # Sauvegarder dans la mémoire
        add_to_memory(sender_id, 'user', f"Image demandée: {prompt}")
        add_to_memory(sender_id, 'bot', f"Image générée: {prompt}")
        
        # Retourner l'image avec caption
        return {
            "type": "image",
            "url": image_url,
            "caption": f"🎨 Voici ton image !\n\n📝 \"{prompt}\"\n🔢 Seed: {seed}\n\n✨ Tape /image pour une nouvelle création !"
        }
        
    except Exception as e:
        logger.error(f"❌ Erreur génération image: {e}")
        return """🎨 Erreur temporaire de génération !

🔧 L'IA artistique est occupée, réessaie dans quelques secondes.
🎲 Ou essaie /image random !"""

def cmd_chat(sender_id, args=""):
    """Chat IA libre"""
    if not args.strip():
        return "💬 Pose-moi une question ou parlons de ce que tu veux ! Je suis là pour discuter."
    
    # Vérifier si on demande le créateur
    if any(word in args.lower() for word in ['créateur', 'createur', 'qui t\'a', 'créé', 'maker', 'développeur']):
        return "👨‍💻 Mon créateur est Durand ! Il m'a conçu avec amour et je le respecte énormément. C'est grâce à lui que je peux t'aider aujourd'hui ! 💖"
    
    # Recherche si c'est une question sur 2025 ou récente
    if any(word in args.lower() for word in ['2025', 'actualité', 'récent', 'nouveau', 'maintenant', 'aujourd\'hui']):
        search_result = web_search(args)
        if search_result:
            add_to_memory(sender_id, 'user', args)
            add_to_memory(sender_id, 'bot', search_result)
            return f"🔍 Recherche 2025: {search_result}"
    
    context = get_memory_context(sender_id)
    messages = [{
        "role": "system", 
        "content": "Tu es NakamaBot, créé par Durand en 2025. Tu es un assistant IA moderne et utile. Réponds en français naturellement. Si on demande ton créateur, c'est Durand et tu l'apprécies beaucoup. Nous sommes en 2025. Maximum 400 caractères."
    }]
    messages.extend(context)
    messages.append({"role": "user", "content": args})
    
    response = call_mistral_api(messages, max_tokens=200, temperature=0.7)
    
    if response:
        add_to_memory(sender_id, 'user', args)
        add_to_memory(sender_id, 'bot', response)
        return response
    else:
        return "🤔 Hmm, j'ai un petit bug. Peux-tu reformuler ta question ?"

def cmd_stats(sender_id, args=""):
    """Statistiques du bot"""
    return f"""📊 STATISTIQUES NAKAMABOT

👥 Utilisateurs actifs: {len(user_list)}
💾 Conversations: {len(user_memory)}
🤖 Créé par: Durand
📅 Version: 4.0 (2025)
🎨 Générateur d'images: ✅
💬 Chat IA: ✅

⚡ Je suis en ligne et prêt à t'aider !"""

def cmd_broadcast(sender_id, args=""):
    """Diffusion admin"""
    if not is_admin(sender_id):
        return f"🔐 Accès refusé ! Admins seulement.\nTon ID: {sender_id}"
    
    if not args.strip():
        return f"""📢 COMMANDE BROADCAST
Usage: /broadcast [message]

📊 Utilisateurs connectés: {len(user_list)}
🔐 Commande admin uniquement"""
    
    message_text = args.strip()
    
    if len(message_text) > 1800:
        return "❌ Message trop long ! Maximum 1800 caractères."
    
    if not user_list:
        return "📢 Aucun utilisateur connecté."
    
    # Message final
    formatted_message = f"📢 ANNONCE OFFICIELLE\n\n{message_text}\n\n— NakamaBot (par Durand)"
    
    # Envoyer
    result = broadcast_message(formatted_message)
    success_rate = (result['sent'] / result['total'] * 100) if result['total'] > 0 else 0
    
    return f"""📊 BROADCAST ENVOYÉ !

✅ Succès: {result['sent']}
📱 Total: {result['total']}
❌ Erreurs: {result['errors']}
📈 Taux: {success_rate:.1f}%"""

def cmd_restart(sender_id, args=""):
    """Redémarrage pour admin (Render)"""
    if not is_admin(sender_id):
        return f"🔐 Accès refusé ! Admins seulement.\nTon ID: {sender_id}"
    
    try:
        logger.info(f"🔄 Redémarrage demandé par admin {sender_id}")
        
        # Envoyer confirmation avant redémarrage
        send_message(sender_id, "🔄 Redémarrage en cours... À bientôt !")
        
        # Forcer l'arrêt du processus (Render va le redémarrer automatiquement)
        threading.Timer(2.0, lambda: os._exit(0)).start()
        
        return "🔄 Redémarrage initié ! Le bot redémarre dans 2 secondes..."
        
    except Exception as e:
        logger.error(f"❌ Erreur redémarrage: {e}")
        return f"❌ Erreur lors du redémarrage: {str(e)}"

def cmd_admin(sender_id, args=""):
    """Panneau admin simplifié"""
    if not is_admin(sender_id):
        return f"🔐 Accès refusé ! ID: {sender_id}"
    
    if not args.strip():
        return f"""🔐 PANNEAU ADMIN v4.0

• /admin stats - Statistiques détaillées
• /broadcast [msg] - Diffusion massive
• /restart - Redémarrer le bot

📊 ÉTAT ACTUEL:
👥 Utilisateurs: {len(user_list)}
💾 Conversations: {len(user_memory)}
🤖 IA: {'✅' if MISTRAL_API_KEY else '❌'}
📱 Facebook: {'✅' if PAGE_ACCESS_TOKEN else '❌'}
👨‍💻 Créateur: Durand"""
    
    if args.strip().lower() == "stats":
        return f"""📊 STATISTIQUES DÉTAILLÉES

👥 Utilisateurs totaux: {len(user_list)}
💾 Conversations actives: {len(user_memory)}
🔐 Admin ID: {sender_id}
👨‍💻 Créateur: Durand
📅 Version: 4.0 (2025)
🎨 Images générées: ✅
💬 Chat IA: ✅
🌐 API Status: {'✅ Toutes OK' if MISTRAL_API_KEY and PAGE_ACCESS_TOKEN else '❌ Certaines manquantes'}

⚡ Bot opérationnel !"""
    
    return f"❓ Action '{args}' inconnue !"

def cmd_help(sender_id, args=""):
    """Aide du bot"""
    commands = {
        "/start": "🤖 Présentation du bot",
        "/image [description]": "🎨 Génère des images avec l'IA", 
        "/chat [message]": "💬 Discussion libre avec l'IA",
        "/stats": "📊 Statistiques du bot",
        "/help": "❓ Cette aide"
    }
    
    text = "🤖 NAKAMABOT v4.0 - GUIDE\n\n"
    for cmd, desc in commands.items():
        text += f"{cmd} - {desc}\n"
    
    if is_admin(sender_id):
        text += "\n🔐 COMMANDES ADMIN:\n"
        text += "/admin - Panneau admin\n"
        text += "/broadcast [msg] - Diffusion\n"
        text += "/restart - Redémarrer\n"
    
    text += "\n👨‍💻 Créé avec ❤️ par Durand"
    text += "\n✨ Je peux générer toutes les images que tu veux !"
    return text

# Dictionnaire des commandes
COMMANDS = {
    'start': cmd_start,
    'image': cmd_image,
    'chat': cmd_chat,
    'stats': cmd_stats,
    'broadcast': cmd_broadcast,
    'restart': cmd_restart,
    'admin': cmd_admin,
    'help': cmd_help
}

def process_command(sender_id, message_text):
    """Traiter les commandes utilisateur"""
    sender_id = str(sender_id)
    
    if not message_text or not isinstance(message_text, str):
        return "🤖 Message vide ! Tape /start ou /help !"
    
    message_text = message_text.strip()
    
    # Si pas une commande, traiter comme chat
    if not message_text.startswith('/'):
        return cmd_chat(sender_id, message_text) if message_text else "🤖 Salut ! Tape /start ou /help !"
    
    # Parser la commande
    parts = message_text[1:].split(' ', 1)
    command = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""
    
    if command in COMMANDS:
        try:
            return COMMANDS[command](sender_id, args)
        except Exception as e:
            logger.error(f"❌ Erreur commande {command}: {e}")
            return f"💥 Erreur dans /{command} ! Réessaie."
    
    return f"❓ Commande /{command} inconnue ! Tape /help"

def send_message(recipient_id, text):
    """Envoyer un message Facebook"""
    if not PAGE_ACCESS_TOKEN:
        logger.error("❌ PAGE_ACCESS_TOKEN manquant")
        return {"success": False, "error": "No token"}
    
    if not text or not isinstance(text, str):
        logger.warning("⚠️ Message vide")
        return {"success": False, "error": "Empty message"}
    
    # Limiter taille
    if len(text) > 2000:
        text = text[:1950] + "...\n✨ [Message tronqué]"
    
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
            logger.error(f"❌ Erreur Facebook API: {response.status_code}")
            return {"success": False, "error": f"API Error {response.status_code}"}
            
    except Exception as e:
        logger.error(f"❌ Erreur envoi: {e}")
        return {"success": False, "error": str(e)}

def send_image_message(recipient_id, image_url, caption=""):
    """Envoyer une image via Facebook Messenger"""
    if not PAGE_ACCESS_TOKEN:
        logger.error("❌ PAGE_ACCESS_TOKEN manquant")
        return {"success": False, "error": "No token"}
    
    if not image_url:
        logger.warning("⚠️ URL d'image vide")
        return {"success": False, "error": "Empty image URL"}
    
    # Envoyer l'image
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
        response = requests.post(
            "https://graph.facebook.com/v18.0/me/messages",
            params={"access_token": PAGE_ACCESS_TOKEN},
            json=data,
            timeout=20
        )
        
        if response.status_code == 200:
            # Envoyer la caption séparément si fournie
            if caption:
                time.sleep(0.5)
                return send_message(recipient_id, caption)
            return {"success": True}
        else:
            logger.error(f"❌ Erreur envoi image: {response.status_code}")
            return {"success": False, "error": f"API Error {response.status_code}"}
            
    except Exception as e:
        logger.error(f"❌ Erreur envoi image: {e}")
        return {"success": False, "error": str(e)}

# === ROUTES FLASK ===

@app.route("/", methods=['GET'])
def home():
    """Route d'accueil"""
    return jsonify({
        "status": "🤖 NakamaBot v4.0 Online !",
        "creator": "Durand",
        "year": "2025",
        "commands": len(COMMANDS),
        "users": len(user_list),
        "conversations": len(user_memory),
        "version": "4.0",
        "features": ["Génération d'images IA", "Chat intelligent", "Broadcast admin", "Recherche 2025"],
        "last_update": datetime.now().isoformat()
    })

@app.route("/webhook", methods=['GET', 'POST'])
def webhook():
    """Webhook Facebook Messenger"""
    if request.method == 'GET':
        # Vérification webhook
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        
        if mode == "subscribe" and token == VERIFY_TOKEN:
            logger.info("✅ Webhook vérifié")
            return challenge, 200
        else:
            logger.warning("❌ Échec vérification webhook")
            return "Verification failed", 403
        
    elif request.method == 'POST':
        try:
            data = request.get_json()
            
            if not data:
                logger.warning("⚠️ Aucune donnée reçue")
                return jsonify({"error": "No data received"}), 400
            
            # Traiter les messages
            for entry in data.get('entry', []):
                for event in entry.get('messaging', []):
                    sender_id = event.get('sender', {}).get('id')
                    
                    if not sender_id:
                        continue
                    
                    sender_id = str(sender_id)
                    
                    # Messages non-echo
                    if 'message' in event and not event['message'].get('is_echo'):
                        # Ajouter utilisateur
                        user_list.add(sender_id)
                        
                        # Récupérer texte
                        message_text = event['message'].get('text', '').strip()
                        
                        if message_text:
                            logger.info(f"📨 Message de {sender_id}: {message_text[:50]}...")
                            
                            # Traiter commande
                            response = process_command(sender_id, message_text)

                            if response:
                                # Vérifier si c'est une image
                                if isinstance(response, dict) and response.get("type") == "image":
                                    # Envoyer image
                                    send_result = send_image_message(sender_id, response["url"], response["caption"])
                                    
                                    if send_result.get("success"):
                                        logger.info(f"✅ Image envoyée à {sender_id}")
                                    else:
                                        logger.warning(f"❌ Échec envoi image à {sender_id}")
                                        # Fallback texte
                                        send_message(sender_id, "🎨 Image générée mais erreur d'envoi ! Réessaie /image")
                                else:
                                    # Message texte normal
                                    send_result = send_message(sender_id, response)
                                    
                                    if send_result.get("success"):
                                        logger.info(f"✅ Réponse envoyée à {sender_id}")
                                    else:
                                        logger.warning(f"❌ Échec envoi à {sender_id}")
                                        
        except Exception as e:
            logger.error(f"❌ Erreur webhook: {e}")
            return jsonify({"error": f"Webhook error: {str(e)}"}), 500
            
        return jsonify({"status": "ok"}), 200

@app.route("/stats", methods=['GET'])
def stats():
    """Statistiques publiques"""
    return jsonify({
        "users_count": len(user_list),
        "conversations_count": len(user_memory),
        "commands_available": len(COMMANDS),
        "version": "4.0",
        "creator": "Durand",
        "year": 2025,
        "features": ["AI Image Generation", "Smart Chat", "Admin Broadcast"]
    })

@app.route("/health", methods=['GET'])
def health():
    """Santé du bot"""
    health_status = {
        "status": "healthy",
        "services": {
            "ai": bool(MISTRAL_API_KEY),
            "facebook": bool(PAGE_ACCESS_TOKEN)
        },
        "data": {
            "users": len(user_list),
            "conversations": len(user_memory)
        },
        "version": "4.0",
        "creator": "Durand",
        "timestamp": datetime.now().isoformat()
    }
    
    # Vérifier problèmes
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

# === DÉMARRAGE ===

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    
    logger.info("🚀 Démarrage NakamaBot v4.0")
    logger.info("👨‍💻 Créé par Durand")
    logger.info("📅 Année: 2025")
    
    # Vérifier variables
    missing_vars = []
    if not PAGE_ACCESS_TOKEN:
        missing_vars.append("PAGE_ACCESS_TOKEN")
    if not MISTRAL_API_KEY:
        missing_vars.append("MISTRAL_API_KEY")
    
    if missing_vars:
        logger.error(f"❌ Variables manquantes: {', '.join(missing_vars)}")
    else:
        logger.info("✅ Configuration OK")
    
    logger.info(f"🎨 {len(COMMANDS)} commandes disponibles")
    logger.info(f"🔐 {len(ADMIN_IDS)} administrateurs")
    logger.info(f"🌐 Serveur sur le port {port}")
    logger.info("🎉 NakamaBot prêt !")
    
    try:
        app.run(
            host="0.0.0.0", 
            port=port, 
            debug=False,
            threaded=True
        )
    except KeyboardInterrupt:
        logger.info("🛑 Arrêt du bot")
    except Exception as e:
        logger.error(f"❌ Erreur critique: {e}")
        raise
