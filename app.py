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
            "content": f"Tu es NakamaBot, une assistante IA très gentille et amicale qui aide avec les recherches. Nous sommes en 2025. Réponds à cette recherche: '{query}' avec tes connaissances de 2025. Si tu ne sais pas, dis-le gentiment. Réponds en français avec une personnalité amicale et bienveillante, maximum 300 caractères."
        }]
        
        return call_mistral_api(messages, max_tokens=150, temperature=0.3)
    except Exception as e:
        logger.error(f"❌ Erreur recherche: {e}")
        return "Oh non ! Une petite erreur de recherche... Désolée ! 💕"

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
    return f"""💖 Coucou ! Je suis NakamaBot, créée avec amour par Durand ! 

✨ Voici ce que je peux faire pour toi :
🎨 /image [description] - Je crée de magnifiques images avec l'IA !
💬 /chat [message] - On peut papoter de tout et de rien !
❓ /help - Toutes mes commandes (tape ça pour voir tout !)

🌸 Je suis là pour t'aider avec le sourire ! N'hésite pas à me demander tout ce que tu veux ! 💕"""

def cmd_image(sender_id, args=""):
    """Générateur d'images avec IA"""
    
    if not args.strip():
        return f"""🎨 OH OUI ! Je peux générer des images magnifiques ! ✨

🖼️ /image [ta description] - Je crée ton image de rêve !
🎨 /image chat robot mignon - Exemple adorable
🌸 /image paysage féerique coucher soleil - Exemple poétique
⚡ /image random - Une surprise image !

💕 Je suis super douée pour créer des images ! Décris-moi ton rêve et je le dessine pour toi !
🎭 Tous les styles : réaliste, cartoon, anime, artistique...

💡 Plus tu me donnes de détails, plus ton image sera parfaite !
❓ Besoin d'aide ? Tape /help pour voir toutes mes capacités ! 🌟"""
    
    prompt = args.strip()
    sender_id = str(sender_id)
    
    # Images aléatoires si demandé
    if prompt.lower() == "random":
        random_prompts = [
            "beautiful fairy garden with sparkling flowers and butterflies",
            "cute magical unicorn in enchanted forest with rainbow", 
            "adorable robot princess with jeweled crown in castle",
            "dreamy space goddess floating among stars and galaxies",
            "magical mermaid palace underwater with pearl decorations",
            "sweet vintage tea party with pastel colors and roses",
            "cozy cottagecore house with flower gardens and sunshine",
            "elegant anime girl with flowing dress in cherry blossoms"
        ]
        prompt = random.choice(random_prompts)
    
    # Valider le prompt
    if len(prompt) < 3:
        return f"❌ Oh là là ! Ta description est un peu courte ! Donne-moi au moins 3 lettres pour que je puisse créer quelque chose de beau ! 💕"
    
    if len(prompt) > 200:
        return f"❌ Oups ! Ta description est trop longue ! Maximum 200 caractères s'il te plaît ! 🌸"
    
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
            "caption": f"🎨 Tadaaa ! Voici ton image créée avec amour ! ✨\n\n📝 \"{prompt}\"\n🔢 Seed magique: {seed}\n\n💕 J'espère qu'elle te plaît ! Tape /image pour une nouvelle création ou /help pour voir tout ce que je sais faire ! 🌟"
        }
        
    except Exception as e:
        logger.error(f"❌ Erreur génération image: {e}")
        return f"""🎨 Oh non ! Une petite erreur temporaire dans mon atelier artistique ! 😅

🔧 Mon pinceau magique est un peu fatigué, réessaie dans quelques secondes !
🎲 Ou essaie /image random pour une surprise !
❓ Tape /help si tu as besoin d'aide ! 💖"""

def cmd_chat(sender_id, args=""):
    """Chat IA libre"""
    
    if not args.strip():
        return f"💬 Coucou ! Dis-moi tout ce qui te passe par la tête ! Je suis là pour papoter avec toi ! ✨ N'hésite pas à taper /help pour voir tout ce que je peux faire ! 💕"
    
    # Vérifier si on demande le créateur
    if any(word in args.lower() for word in ['créateur', 'createur', 'qui t\'a', 'créé', 'créee', 'maker', 'développeur']):
        return f"👨‍💻 Mon adorable créateur c'est Durand ! Il m'a conçue avec tellement d'amour et de tendresse ! Je l'adore énormément ! 💖 C'est grâce à lui que je peux être là pour t'aider aujourd'hui ! ✨"
    
    # Vérifier si on demande les images
    if any(word in args.lower() for word in ['image', 'images', 'photo', 'photos', 'dessiner', 'créer', 'génerer', 'generer']):
        return f"🎨 OH OUI ! Je peux créer des images magnifiques grâce à /image ! ✨ Donne-moi une description et je te crée la plus belle image ! Essaie /image [ta description] ou tape /help pour voir toutes mes commandes ! 💕"
    
    # Recherche si c'est une question sur 2025 ou récente
    if any(word in args.lower() for word in ['2025', 'actualité', 'récent', 'nouveau', 'maintenant', 'aujourd\'hui']):
        search_result = web_search(args)
        if search_result:
            add_to_memory(sender_id, 'user', args)
            add_to_memory(sender_id, 'bot', search_result)
            return f"🔍 Voici ce que j'ai trouvé pour toi : {search_result} ✨\n\n❓ Tape /help pour voir tout ce que je peux faire ! 💕"
    
    context = get_memory_context(sender_id)
    
    messages = [{
        "role": "system", 
        "content": f"Tu es NakamaBot, une assistante IA très gentille et amicale créée par Durand en 2025. Tu es comme une très bonne amie bienveillante. Tu es super enthousiaste et tu utilises beaucoup d'emojis mignons. Tu proposes souvent aux utilisateurs de taper /help. Si on demande ton créateur, c'est Durand que tu adores. Tu peux créer des images avec /image. Nous sommes en 2025. Réponds en français avec une personnalité amicale et douce, sans expressions romantiques. Maximum 400 caractères."
    }]
    messages.extend(context)
    messages.append({"role": "user", "content": args})
    
    response = call_mistral_api(messages, max_tokens=200, temperature=0.7)
    
    if response:
        add_to_memory(sender_id, 'user', args)
        add_to_memory(sender_id, 'bot', response)
        # Ajouter souvent une proposition d'aide
        if random.random() < 0.3:  # 30% de chance
            response += f"\n\n❓ N'hésite pas à taper /help pour voir tout ce que je peux faire pour toi ! 💕"
        return response
    else:
        return f"🤔 Oh là là ! J'ai un petit souci technique ! Peux-tu reformuler ta question ? 💕 Ou tape /help pour voir mes commandes ! ✨"

def cmd_stats(sender_id, args=""):
    """Statistiques du bot - RÉSERVÉ AUX ADMINS"""
    if not is_admin(sender_id):
        return f"🔐 Oh ! Cette commande est réservée aux admins seulement !\nTon ID: {sender_id}\n💕 Mais tu peux utiliser /help pour voir mes autres commandes !"
    
    return f"""📊 MES PETITES STATISTIQUES ADMIN ! ✨

👥 Mes amis utilisateurs : {len(user_list)} 💕
💾 Conversations en cours : {len(user_memory)}
🤖 Créée avec amour par : Durand 💖
📅 Version : 4.0 Amicale (2025)
🎨 Génération d'images : ✅ JE SUIS DOUÉE !
💬 Chat intelligent : ✅ ON PEUT TOUT SE DIRE !
🔐 Accès admin autorisé ✅

⚡ Je suis en ligne et super heureuse de t'aider !
❓ Tape /help pour voir toutes mes capacités ! 🌟"""

def cmd_broadcast(sender_id, args=""):
    """Diffusion admin"""
    if not is_admin(sender_id):
        return f"🔐 Oh ! Accès réservé aux admins seulement !\nTon ID: {sender_id}\n💕 Mais tu peux utiliser /help pour voir mes autres commandes !"
    
    if not args.strip():
        return f"""📢 COMMANDE BROADCAST ADMIN
Usage: /broadcast [message]

📊 Mes petits utilisateurs connectés: {len(user_list)} 💕
🔐 Commande réservée aux admins"""
    
    message_text = args.strip()
    
    if len(message_text) > 1800:
        return "❌ Oh non ! Ton message est trop long ! Maximum 1800 caractères s'il te plaît ! 💕"
    
    if not user_list:
        return "📢 Aucun utilisateur connecté pour le moment ! 🌸"
    
    # Message final
    formatted_message = f"📢 ANNONCE OFFICIELLE DE NAKAMABOT 💖\n\n{message_text}\n\n— Avec tout mon amour, NakamaBot (créée par Durand) ✨"
    
    # Envoyer
    result = broadcast_message(formatted_message)
    success_rate = (result['sent'] / result['total'] * 100) if result['total'] > 0 else 0
    
    return f"""📊 BROADCAST ENVOYÉ AVEC AMOUR ! 💕

✅ Messages réussis : {result['sent']}
📱 Total d'amis : {result['total']}
❌ Petites erreurs : {result['errors']}
📈 Taux de réussite : {success_rate:.1f}% 🌟"""

def cmd_restart(sender_id, args=""):
    """Redémarrage pour admin (Render)"""
    if not is_admin(sender_id):
        return f"🔐 Oh ! Cette commande est réservée aux admins !\nTon ID: {sender_id}\n💕 Tape /help pour voir ce que tu peux faire !"
    
    try:
        logger.info(f"🔄 Redémarrage demandé par admin {sender_id}")
        
        # Envoyer confirmation avant redémarrage
        send_message(sender_id, "🔄 Je redémarre avec amour... À très bientôt ! 💖✨")
        
        # Forcer l'arrêt du processus (Render va le redémarrer automatiquement)
        threading.Timer(2.0, lambda: os._exit(0)).start()
        
        return "🔄 Redémarrage initié avec tendresse ! Je reviens dans 2 secondes ! 💕"
        
    except Exception as e:
        logger.error(f"❌ Erreur redémarrage: {e}")
        return f"❌ Oups ! Petite erreur lors du redémarrage : {str(e)} 💕"

def cmd_admin(sender_id, args=""):
    """Panneau admin simplifié"""
    if not is_admin(sender_id):
        return f"🔐 Oh ! Accès réservé aux admins ! ID: {sender_id}\n💕 Tape /help pour voir mes autres talents !"
    
    if not args.strip():
        return f"""🔐 PANNEAU ADMIN v4.0 AMICALE 💖

• /admin stats - Mes statistiques détaillées
• /stats - Statistiques publiques admin
• /broadcast [msg] - Diffusion pleine d'amour
• /restart - Me redémarrer en douceur

📊 MON ÉTAT ACTUEL :
👥 Mes utilisateurs : {len(user_list)}
💾 Conversations en cours : {len(user_memory)}
🤖 IA intelligente : {'✅ JE SUIS BRILLANTE !' if MISTRAL_API_KEY else '❌'}
📱 Facebook connecté : {'✅ PARFAIT !' if PAGE_ACCESS_TOKEN else '❌'}
👨‍💻 Mon créateur adoré : Durand 💕"""
    
    if args.strip().lower() == "stats":
        return f"""📊 MES STATISTIQUES DÉTAILLÉES AVEC AMOUR 💖

👥 Utilisateurs totaux : {len(user_list)} 💕
💾 Conversations actives : {len(user_memory)}
🔐 Admin ID : {sender_id}
👨‍💻 Mon créateur adoré : Durand ✨
📅 Version : 4.0 Amicale (2025)
🎨 Images générées : ✅ JE SUIS ARTISTE !
💬 Chat IA : ✅ ON PAPOTE !
🌐 Statut API : {'✅ Tout fonctionne parfaitement !' if MISTRAL_API_KEY and PAGE_ACCESS_TOKEN else '❌ Quelques petits soucis'}

⚡ Je suis opérationnelle et heureuse ! 🌟"""
    
    return f"❓ Oh ! L'action '{args}' m'est inconnue ! 💕"

def cmd_help(sender_id, args=""):
    """Aide du bot"""
    
    commands = {
        "/start": "🤖 Ma présentation toute mignonne",
        "/image [description]": "🎨 Je crée des images magnifiques avec l'IA !", 
        "/chat [message]": "💬 On papote de tout avec gentillesse",
        "/help": "❓ Cette aide pleine d'amour"
    }
    
    text = f"🤖 NAKAMABOT v4.0 AMICALE - GUIDE COMPLET 💖\n\n"
    text += f"✨ Voici tout ce que je peux faire pour toi :\n\n"
    for cmd, desc in commands.items():
        text += f"{cmd} - {desc}\n"
    
    if is_admin(sender_id):
        text += "\n🔐 COMMANDES ADMIN SPÉCIALES :\n"
        text += "/stats - Mes statistiques (admin seulement)\n"
        text += "/admin - Mon panneau admin\n"
        text += "/broadcast [msg] - Diffusion avec amour\n"
        text += "/restart - Me redémarrer en douceur\n"
    
    text += f"\n🎨 JE PEUX CRÉER DES IMAGES ! Utilise /image [ta description] !"
    text += f"\n👨‍💻 Créée avec tout l'amour du monde par Durand 💕"
    text += f"\n✨ Je suis là pour t'aider avec le sourire !"
    text += f"\n💖 N'hésite jamais à me demander quoi que ce soit !"
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
        return f"🤖 Oh là là ! Message vide ! Tape /start ou /help pour commencer notre belle conversation ! 💕"
    
    message_text = message_text.strip()
    
    # Si ce n'est pas une commande, traiter comme un chat normal
    if not message_text.startswith('/'):
        return cmd_chat(sender_id, message_text) if message_text else f"🤖 Coucou ! Tape /start ou /help pour découvrir ce que je peux faire ! ✨"
    
    # Parser la commande
    parts = message_text[1:].split(' ', 1)
    command = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""
    
    if command in COMMANDS:
        try:
            return COMMANDS[command](sender_id, args)
        except Exception as e:
            logger.error(f"❌ Erreur commande {command}: {e}")
            return f"💥 Oh non ! Petite erreur dans /{command} ! Réessaie ou tape /help ! 💕"
    
    return f"❓ Oh ! La commande /{command} m'est inconnue ! Tape /help pour voir tout ce que je sais faire ! ✨💕"

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
        text = text[:1950] + "...\n✨ [Message tronqué avec amour]"
    
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
        "status": "🤖 NakamaBot v4.0 Amicale Online ! 💖",
        "creator": "Durand",
        "personality": "Super gentille et amicale, comme une très bonne amie",
        "year": "2025",
        "commands": len(COMMANDS),
        "users": len(user_list),
        "conversations": len(user_memory),
        "version": "4.0 Amicale",
        "features": ["Génération d'images IA", "Chat intelligent et doux", "Broadcast admin", "Recherche 2025", "Stats réservées admin"],
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
                                        send_message(sender_id, f"🎨 Image créée avec amour mais petite erreur d'envoi ! Réessaie /image ! 💕")
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
    """Statistiques publiques limitées"""
    return jsonify({
        "users_count": len(user_list),
        "conversations_count": len(user_memory),
        "commands_available": len(COMMANDS),
        "version": "4.0 Amicale",
        "creator": "Durand",
        "personality": "Super gentille et amicale, comme une très bonne amie",
        "year": 2025,
        "features": ["AI Image Generation", "Friendly Chat", "Admin Stats", "Help Suggestions"],
        "note": "Statistiques détaillées réservées aux admins via /stats"
    })

@app.route("/health", methods=['GET'])
def health():
    """Santé du bot"""
    health_status = {
        "status": "healthy",
        "personality": "Super gentille et amicale, comme une très bonne amie 💖",
        "services": {
            "ai": bool(MISTRAL_API_KEY),
            "facebook": bool(PAGE_ACCESS_TOKEN)
        },
        "data": {
            "users": len(user_list),
            "conversations": len(user_memory)
        },
        "version": "4.0 Amicale",
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
    
    logger.info("🚀 Démarrage NakamaBot v4.0 Amicale")
    logger.info("💖 Personnalité super gentille et amicale, comme une très bonne amie")
    logger.info("👨‍💻 Créée par Durand")
    logger.info("📅 Année: 2025")
    logger.info("🔐 Commande /stats réservée aux admins")
    
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
    logger.info("🎉 NakamaBot Amicale prête à aider avec gentillesse !")
    
    try:
        app.run(
            host="0.0.0.0", 
            port=port, 
            debug=False,
            threaded=True
        )
    except KeyboardInterrupt:
        logger.info("🛑 Arrêt du bot avec tendresse")
    except Exception as e:
        logger.error(f"❌ Erreur critique: {e}")
        raise
