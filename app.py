import os
import logging
import json
import random
import inspect
from flask import Flask, request, jsonify
import requests
from datetime import datetime
from openai import OpenAI

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
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Validation des tokens
if not PAGE_ACCESS_TOKEN:
    logger.error("❌ PAGE_ACCESS_TOKEN is missing!")
else:
    logger.info(f"✅ PAGE_ACCESS_TOKEN configuré")

if not OPENAI_API_KEY:
    logger.error("❌ OPENAI_API_KEY is missing!")
else:
    logger.info("✅ OPENAI_API_KEY configuré")
    
# Initialisation OpenAI avec gestion d'erreur
client = None
if OPENAI_API_KEY:
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        logger.info("✅ Client OpenAI initialisé avec succès")
    except Exception as e:
        logger.error(f"❌ Erreur initialisation OpenAI: {e}")
        client = None

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
    if not client:
        return "❌ OpenAI non configuré pour cette commande, gomen nasai!"
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{
                "role": "system",
                "content": """Tu es NakamaBot, un bot otaku kawaii et énergique. Crée une présentation épique style anime opening en français, avec :
                - Beaucoup d'emojis anime/manga
                - Style énergique comme Luffy ou Naruto
                - Présente tes capacités de façon cool
                - Maximum 300 caractères
                - Termine par une phrase motivante d'anime"""
            }, {
                "role": "user", 
                "content": "Présente-toi de façon épique !"
            }],
            max_tokens=150,
            temperature=0.9
        )
        
        ai_response = response.choices[0].message.content
        return f"🎌 {ai_response}\n\n✨ Tape /help pour découvrir toutes mes techniques secrètes, nakama! ⚡"
        
    except Exception as e:
        logger.error(f"Erreur OpenAI start: {e}")
        return "🌟 Konnichiwa, nakama! Je suis NakamaBot! ⚡\n🎯 Ton compagnon otaku ultime pour parler anime, manga et bien plus!\n✨ Tape /help pour mes super pouvoirs! 🚀"

@command('ia', '🧠 Discussion libre avec une IA otaku kawaii')
def cmd_ia(sender_id, message_text=""):
    """Chat libre avec personnalité otaku"""
    if not client:
        return "❌ Mon cerveau otaku n'est pas connecté, gomen!"
    
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
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{
                "role": "system",
                "content": """Tu es NakamaBot, une IA otaku kawaii et énergique. Réponds en français avec :
                - Personnalité mélange de Nezuko (mignon), Megumin (dramatique), et Zero Two (taquine)
                - Beaucoup d'emojis anime
                - Références anime/manga naturelles
                - Style parfois tsundere ou badass selon le contexte
                - Maximum 400 caractères"""
            }, {
                "role": "user",
                "content": message_text
            }],
            max_tokens=200,
            temperature=0.8
        )
        
        return f"💖 {response.choices[0].message.content}"
        
    except Exception as e:
        logger.error(f"Erreur OpenAI ia: {e}")
        return "💭 Mon cerveau otaku bug un peu là... Retry, onegaishimasu! 🥺"

@command('waifu', '👸 Génère ta waifu parfaite avec IA!')
def cmd_waifu(sender_id, message_text=""):
    """Génère une waifu unique"""
    if not client:
        return "❌ Le générateur de waifu est en maintenance!"
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{
                "role": "system",
                "content": """Crée une waifu originale avec :
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
            }],
            max_tokens=180,
            temperature=0.9
        )
        
        return f"👸✨ Voici ta waifu générée!\n\n{response.choices[0].message.content}\n\n💕 Elle t'attend, nakama!"
        
    except Exception as e:
        logger.error(f"Erreur waifu: {e}")
        return "👸 Akari-chan, 19 ans, tsundere aux cheveux roses! Elle adore la pâtisserie mais fait semblant de ne pas s'intéresser à toi... 'B-baka! Ce n'est pas comme si j'avais fait ces cookies pour toi!' 💕"

@command('husbando', '🤵 Génère ton husbando de rêve!')
def cmd_husbando(sender_id, message_text=""):
    """Génère un husbando unique"""
    if not client:
        return "❌ Le générateur de husbando fait une pause!"
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{
                "role": "system", 
                "content": """Crée un husbando original avec :
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
            }],
            max_tokens=180,
            temperature=0.9
        )
        
        return f"🤵⚡ Ton husbando t'attend!\n\n{response.choices[0].message.content}\n\n💙 Il ne te décevra jamais!"
        
    except Exception as e:
        logger.error(f"Erreur husbando: {e}")
        return "🤵 Takeshi, 24 ans, capitaine stoïque aux yeux d'acier! Épéiste légendaire qui cache un cœur tendre. 'Je protégerai toujours ceux qui me sont chers... y compris toi.' ⚔️💙"

@command('animequiz', '🧩 Quiz épique sur les anime!')
def cmd_animequiz(sender_id, message_text=""):
    """Quiz anime interactif"""
    if not client:
        return "❌ Le quiz-sensei n'est pas disponible!"
    
    # Si c'est une réponse, on la traite (simplifiée pour cet exemple)
    if message_text.strip():
        return f"🎯 Réponse reçue: '{message_text}'\n💡 Nouveau quiz en arrivant! Tape /animequiz ⚡"
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{
                "role": "system",
                "content": """Crée un quiz anime original avec :
                - Question intéressante sur anime/manga populaire
                - 3 choix multiples A, B, C
                - Difficulté moyenne
                - Style énergique
                - Maximum 300 caractères
                Format: Question + choix A/B/C"""
            }, {
                "role": "user",
                "content": "Crée un quiz anime!"
            }],
            max_tokens=150,
            temperature=0.8
        )
        
        return f"🧩⚡ QUIZ TIME!\n\n{response.choices[0].message.content}\n\n🎯 Réponds-moi, nakama!"
        
    except Exception as e:
        logger.error(f"Erreur quiz: {e}")
        return "🧩 Dans quel anime trouve-t-on les 'Piliers'?\nA) Attack on Titan\nB) Demon Slayer\nC) Naruto\n\n⚡ À toi de jouer!"

@command('otakufact', '📚 Fun facts otaku ultra intéressants!')
def cmd_otakufact(sender_id, message_text=""):
    """Fun facts otaku"""
    if not client:
        return "❌ La base de données otaku est en maintenance!"
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{
                "role": "system",
                "content": """Donne un fun fact otaku intéressant sur :
                - Anime, manga, culture japonaise, studios d'animation
                - Fait surprenant et véridique
                - Style enthousiaste avec emojis
                - Maximum 250 caractères
                - Commence par 'Saviez-vous que...'"""
            }, {
                "role": "user",
                "content": "Donne-moi un fun fact otaku!"
            }],
            max_tokens=120,
            temperature=0.7
        )
        
        return f"📚✨ OTAKU FACT!\n\n{response.choices[0].message.content}\n\n🤓 Incroyable, non?"
        
    except Exception as e:
        logger.error(f"Erreur fact: {e}")
        return "📚 Saviez-vous que Akira Toriyama a créé Dragon Ball en s'inspirant du 'Voyage vers l'Ouest', un classique chinois? Son Goku = Sun Wukong! 🐒⚡"

@command('recommend', '🎬 Recommandations anime/manga personnalisées!')
def cmd_recommend(sender_id, message_text=""):
    """Recommandations selon genre"""
    if not client:
        return "❌ Mon catalogue d'animes fait une pause!"
    
    genre = message_text.strip() or "aléatoire"
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{
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
            }],
            max_tokens=200,
            temperature=0.8
        )
        
        return f"🎬✨ RECOMMANDATIONS {genre.upper()}!\n\n{response.choices[0].message.content}\n\n⭐ Bon visionnage, nakama!"
        
    except Exception as e:
        logger.error(f"Erreur recommend: {e}")
        return f"🎬 Pour {genre}:\n• Attack on Titan - Epic & sombre! ⚔️\n• Your Name - Romance qui fait pleurer 😭\n• One Piece - Aventure infinie! 🏴‍☠️\n\nBon anime time! ✨"

@command('story', '📖 Histoires courtes isekai/shonen sur mesure!')
def cmd_story(sender_id, message_text=""):
    """Histoires courtes personnalisées"""
    if not client:
        return "❌ Mon carnet d'histoires est fermé!"
    
    theme = message_text.strip() or "isekai"
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{
                "role": "system",
                "content": f"""Écris une histoire courte {theme} avec :
                - Protagoniste attachant
                - Situation intéressante
                - Style anime/manga
                - Fin ouverte ou épique
                - Maximum 500 caractères
                - Beaucoup d'action et d'émotion"""
            }, {
                "role": "user",
                "content": f"Raconte-moi une histoire {theme}!"
            }],
            max_tokens=250,
            temperature=0.9
        )
        
        return f"📖⚡ HISTOIRE {theme.upper()}!\n\n{response.choices[0].message.content}\n\n✨ Suite au prochain épisode?"
        
    except Exception as e:
        logger.error(f"Erreur story: {e}")
        return "📖 Akira se réveille dans un monde magique où ses connaissances d'otaku deviennent des sorts! Son premier ennemi? Un démon qui déteste les animes! 'Maudit otaku!' crie-t-il. Akira sourit: 'KAMEHAMEHA!' ⚡✨"

@command('help', '❓ Guide complet de toutes mes techniques secrètes!')
def cmd_help(sender_id, message_text=""):
    """Génère automatiquement l'aide basée sur toutes les commandes"""
    help_text = "🎌⚡ NAKAMA BOT - GUIDE ULTIME! ⚡🎌\n\n"
    
    for cmd_name, cmd_info in COMMANDS.items():
        help_text += f"/{cmd_name} - {cmd_info['description']}\n"
    
    help_text += "\n🔥 Utilisation: Tape / + commande"
    help_text += "\n💡 Ex: /waifu, /ia salut!, /recommend shonen"
    help_text += "\n\n⚡ Créé avec amour pour les otakus! 💖"
    
    return help_text

# 🌐 ROUTES FLASK 🌐

@app.route("/", methods=['GET'])
def home():
    return jsonify({
        "status": "🎌 NakamaBot Otaku Edition is alive! ⚡",
        "timestamp": datetime.now().isoformat(),
        "commands_loaded": len(COMMANDS),
        "ai_ready": bool(client)
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
                    
                    if 'message' in messaging_event:
                        message_data = messaging_event['message']
                        
                        # Ignorer les echos
                        if message_data.get('is_echo'):
                            continue
                            
                        message_text = message_data.get('text', '').strip()
                        logger.info(f"💬 Message de {sender_id}: '{message_text}'")
                        
                        # Traitement des commandes
                        response_text = process_command(sender_id, message_text)
                        
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
        "openai_ready": bool(client),
        "config": {
            "verify_token_set": bool(VERIFY_TOKEN),
            "page_token_set": bool(PAGE_ACCESS_TOKEN),
            "openai_key_set": bool(OPENAI_API_KEY)
        }
    }), 200

@app.route("/commands", methods=['GET'])
def list_commands():
    """API pour lister toutes les commandes disponibles"""
    commands_info = {}
    for name, info in COMMANDS.items():
        commands_info[name] = {
            'name': name,
            'description': info['description']
        }
    
    return jsonify({
        "total_commands": len(COMMANDS),
        "commands": commands_info
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    
    logger.info("🚀 Démarrage NakamaBot Otaku Edition...")
    logger.info(f"🎌 Commandes chargées: {len(COMMANDS)}")
    logger.info(f"📋 Liste: {list(COMMANDS.keys())}")
    logger.info(f"🤖 OpenAI ready: {bool(client)}")
    
    app.run(host="0.0.0.0", port=port, debug=False)
