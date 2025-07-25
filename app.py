import os
import logging
import json
import random
import inspect
import time
import threading
from flask import Flask, request, jsonify
import requests
from datetime import datetime, timedelta
from openai import OpenAI

# Configuration du logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# 🔑 Configuration Multi-API
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "nakamaverifytoken")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "")

# Configuration des clés API multiples
API_CONFIGS = [
    {
        "name": "Mistral-1",
        "key": os.getenv("MISTRAL_API_KEY_1", ""),
        "base_url": "https://api.mistral.ai/v1",
        "models": ["mistral-small", "mistral-medium", "mistral-large"]
    },
    {
        "name": "Mistral-2", 
        "key": os.getenv("MISTRAL_API_KEY_2", ""),
        "base_url": "https://api.mistral.ai/v1",
        "models": ["mistral-small", "mistral-medium", "mistral-large"]
    },
    {
        "name": "OpenAI",
        "key": os.getenv("OPENAI_API_KEY", ""),
        "base_url": None,
        "models": ["gpt-3.5-turbo", "gpt-4"]
    }
]

# Validation et initialisation des clients
active_clients = []
for config in API_CONFIGS:
    if config["key"]:
        try:
            if config["name"].startswith("Mistral"):
                client = OpenAI(
                    api_key=config["key"],
                    base_url=config["base_url"]
                )
            else:
                client = OpenAI(api_key=config["key"])
            
            config["client"] = client
            active_clients.append(config)
            logger.info(f"✅ {config['name']} configuré avec succès")
        except Exception as e:
            logger.error(f"❌ Erreur {config['name']}: {e}")
    else:
        logger.warning(f"⚠️ Clé manquante pour {config['name']}")

logger.info(f"🤖 {len(active_clients)} clients AI actifs")

# 🎯 Système de Quiz Interactif
active_quizzes = {}
quiz_lock = threading.Lock()

class QuizSession:
    def __init__(self, sender_id, question, choices, correct_answer, explanation=""):
        self.sender_id = sender_id
        self.question = question
        self.choices = choices
        self.correct_answer = correct_answer
        self.explanation = explanation
        self.created_at = datetime.now()
        self.expires_at = datetime.now() + timedelta(seconds=30)
        self.answered = False
        
        # Timer pour expiration automatique
        timer = threading.Timer(30.0, self.expire_quiz)
        timer.start()
    
    def expire_quiz(self):
        with quiz_lock:
            if self.sender_id in active_quizzes and not self.answered:
                self.answered = True
                # Envoyer la réponse automatiquement
                response = f"⏰ TEMPS ÉCOULÉ!\n\n🎯 La bonne réponse était: {self.correct_answer}\n{self.explanation}\n\n💪 Tape /animequiz pour un nouveau défi!"
                send_message(self.sender_id, response)
                del active_quizzes[self.sender_id]

def get_ai_response(messages, max_tokens=200, temperature=0.8, model_preference="mistral"):
    """Système de failover intelligent entre les APIs"""
    
    # Trier les clients par préférence
    sorted_clients = sorted(active_clients, key=lambda x: (
        0 if model_preference in x["name"].lower() else 1,
        random.random()
    ))
    
    for config in sorted_clients:
        for model in config["models"]:
            try:
                logger.info(f"🔄 Tentative {config['name']} avec {model}")
                
                response = config["client"].chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    timeout=10
                )
                
                logger.info(f"✅ Succès avec {config['name']} - {model}")
                return response.choices[0].message.content
                
            except Exception as e:
                logger.warning(f"⚠️ Échec {config['name']}-{model}: {str(e)[:100]}")
                continue
    
    # Si tous échouent
    logger.error("❌ Tous les clients AI ont échoué")
    return None

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
    if not active_clients:
        return "❌ Mes pouvoirs ne sont pas encore activés, gomen nasai!"
    
    ai_response = get_ai_response([{
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
    }], max_tokens=150, temperature=0.9)
    
    if ai_response:
        return f"🎌 {ai_response}\n\n✨ Tape /help pour découvrir toutes mes techniques secrètes, nakama! ⚡"
    else:
        return "🌟 Konnichiwa, nakama! Je suis NakamaBot! ⚡\n🎯 Ton compagnon otaku ultime pour parler anime, manga et bien plus!\n✨ Tape /help pour mes super pouvoirs! 🚀"

@command('ia', '🧠 Discussion libre avec une IA otaku kawaii')
def cmd_ia(sender_id, message_text=""):
    """Chat libre avec personnalité otaku"""
    if not active_clients:
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
    
    ai_response = get_ai_response([{
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
    }], max_tokens=200, temperature=0.8)
    
    if ai_response:
        return f"💖 {ai_response}"
    else:
        return "💭 Mon cerveau otaku bug un peu là... Retry, onegaishimasu! 🥺"

@command('waifu', '👸 Génère ta waifu parfaite avec IA!')
def cmd_waifu(sender_id, message_text=""):
    """Génère une waifu unique"""
    if not active_clients:
        return "❌ Le générateur de waifu est en maintenance!"
    
    ai_response = get_ai_response([{
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
    }], max_tokens=180, temperature=0.9)
    
    if ai_response:
        return f"👸✨ Voici ta waifu générée!\n\n{ai_response}\n\n💕 Elle t'attend, nakama!"
    else:
        return "👸 Akari-chan, 19 ans, tsundere aux cheveux roses! Elle adore la pâtisserie mais fait semblant de ne pas s'intéresser à toi... 'B-baka! Ce n'est pas comme si j'avais fait ces cookies pour toi!' 💕"

@command('husbando', '🤵 Génère ton husbando de rêve!')
def cmd_husbando(sender_id, message_text=""):
    """Génère un husbando unique"""
    if not active_clients:
        return "❌ Le générateur de husbando fait une pause!"
    
    ai_response = get_ai_response([{
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
    }], max_tokens=180, temperature=0.9)
    
    if ai_response:
        return f"🤵⚡ Ton husbando t'attend!\n\n{ai_response}\n\n💙 Il ne te décevra jamais!"
    else:
        return "🤵 Takeshi, 24 ans, capitaine stoïque aux yeux d'acier! Épéiste légendaire qui cache un cœur tendre. 'Je protégerai toujours ceux qui me sont chers... y compris toi.' ⚔️💙"

@command('animequiz', '🧩 Quiz épique sur les anime avec timer 30s!')
def cmd_animequiz(sender_id, message_text=""):
    """Quiz anime interactif avec système de timeout"""
    if not active_clients:
        return "❌ Le quiz-sensei n'est pas disponible!"
    
    # Vérifier si l'utilisateur a un quiz actif
    with quiz_lock:
        if sender_id in active_quizzes:
            quiz = active_quizzes[sender_id]
            if not quiz.answered and datetime.now() < quiz.expires_at:
                remaining = int((quiz.expires_at - datetime.now()).total_seconds())
                return f"⏰ Tu as déjà un quiz en cours! Plus que {remaining}s pour répondre!\n\n{quiz.question}\n{chr(10).join(quiz.choices)}"
    
    # Créer un nouveau quiz
    ai_response = get_ai_response([{
        "role": "system",
        "content": """Crée un quiz anime original au format JSON strict :
        {
          "question": "Question intéressante sur anime/manga populaire",
          "choices": ["A) Réponse 1", "B) Réponse 2", "C) Réponse 3"],
          "correct": "A",
          "explanation": "Explication courte de la réponse"
        }
        Difficulté moyenne, style énergique, question claire."""
    }, {
        "role": "user",
        "content": "Crée un quiz anime au format JSON!"
    }], max_tokens=200, temperature=0.8)
    
    if not ai_response:
        # Quiz de secours
        quiz_data = {
            "question": "🧩 Dans quel anime trouve-t-on les 'Piliers'?",
            "choices": ["A) Attack on Titan", "B) Demon Slayer", "C) Naruto"],
            "correct": "B",
            "explanation": "Les Piliers (Hashira) sont les épéistes d'élite dans Demon Slayer! ⚔️"
        }
    else:
        try:
            # Nettoyer la réponse et parser le JSON
            clean_response = ai_response.strip()
            if clean_response.startswith('```json'):
                clean_response = clean_response[7:-3]
            elif clean_response.startswith('```'):
                clean_response = clean_response[3:-3]
            
            quiz_data = json.loads(clean_response)
        except:
            # Quiz de secours en cas d'erreur de parsing
            quiz_data = {
                "question": "🧩 Quel est le vrai nom de 'L' dans Death Note?",
                "choices": ["A) Light Yagami", "B) L Lawliet", "C) Ryuk"],
                "correct": "B",
                "explanation": "L Lawliet est le véritable nom du détective génial! 🕵️"
            }
    
    # Créer la session de quiz
    with quiz_lock:
        quiz_session = QuizSession(
            sender_id=sender_id,
            question=quiz_data["question"],
            choices=quiz_data["choices"],
            correct_answer=quiz_data["correct"],
            explanation=quiz_data.get("explanation", "Bonne réponse! 🎯")
        )
        active_quizzes[sender_id] = quiz_session
    
    return f"🧩⚡ QUIZ TIME! (30 secondes)\n\n{quiz_data['question']}\n{chr(10).join(quiz_data['choices'])}\n\n🎯 Réponds juste avec la lettre (A, B ou C)!"

@command('otakufact', '📚 Fun facts otaku ultra intéressants!')
def cmd_otakufact(sender_id, message_text=""):
    """Fun facts otaku"""
    if not active_clients:
        return "❌ La base de données otaku est en maintenance!"
    
    ai_response = get_ai_response([{
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
    }], max_tokens=120, temperature=0.7)
    
    if ai_response:
        return f"📚✨ OTAKU FACT!\n\n{ai_response}\n\n🤓 Incroyable, non?"
    else:
        return "📚 Saviez-vous que Akira Toriyama a créé Dragon Ball en s'inspirant du 'Voyage vers l'Ouest', un classique chinois? Son Goku = Sun Wukong! 🐒⚡"

@command('recommend', '🎬 Recommandations anime/manga personnalisées!')
def cmd_recommend(sender_id, message_text=""):
    """Recommandations selon genre"""
    if not active_clients:
        return "❌ Mon catalogue d'animes fait une pause!"
    
    genre = message_text.strip() or "aléatoire"
    
    ai_response = get_ai_response([{
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
    }], max_tokens=200, temperature=0.8)
    
    if ai_response:
        return f"🎬✨ RECOMMANDATIONS {genre.upper()}!\n\n{ai_response}\n\n⭐ Bon visionnage, nakama!"
    else:
        return f"🎬 Pour {genre}:\n• Attack on Titan - Epic & sombre! ⚔️\n• Your Name - Romance qui fait pleurer 😭\n• One Piece - Aventure infinie! 🏴‍☠️\n\nBon anime time! ✨"

@command('story', '📖 Histoires courtes isekai/shonen sur mesure!')
def cmd_story(sender_id, message_text=""):
    """Histoires courtes personnalisées"""
    if not active_clients:
        return "❌ Mon carnet d'histoires est fermé!"
    
    theme = message_text.strip() or "isekai"
    
    ai_response = get_ai_response([{
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
    }], max_tokens=250, temperature=0.9)
    
    if ai_response:
        return f"📖⚡ HISTOIRE {theme.upper()}!\n\n{ai_response}\n\n✨ Suite au prochain épisode?"
    else:
        return "📖 Akira se réveille dans un monde magique où ses connaissances d'otaku deviennent des sorts! Son premier ennemi? Un démon qui déteste les animes! 'Maudit otaku!' crie-t-il. Akira sourit: 'KAMEHAMEHA!' ⚡✨"

@command('shipwar', '💕 ULTIMATE SHIP BATTLE! Défends ton couple préféré!')
def cmd_shipwar(sender_id, message_text=""):
    """Commande ultra-attractive pour les otakus - Battle de ships!"""
    if not active_clients:
        return "❌ L'arène des ships est fermée!"
    
    # Si l'utilisateur propose un ship
    if message_text.strip():
        user_ship = message_text.strip()
        
        ai_response = get_ai_response([{
            "role": "system",
            "content": f"""Tu es un expert otaku passionné de ships! L'utilisateur propose le ship '{user_ship}'.
            
            Réponds avec :
            - Analyse passionnée du ship (pourquoi c'est génial ou problématique)
            - Propose un ship rival du même anime/manga
            - Crée un débat épique entre les deux
            - Style dramatique et passionné comme les vrais otakus
            - Beaucoup d'emojis et références
            - Maximum 500 caractères
            - Termine par un défi de défendre leur ship"""
        }, {
            "role": "user",
            "content": f"Analyse ce ship: {user_ship}"
        }], max_tokens=250, temperature=0.9)
        
        if ai_response:
            return f"⚔️💕 SHIP WAR ACTIVATED!\n\n{ai_response}\n\n🔥 Défends ton ship, nakama!"
        else:
            return f"⚔️ {user_ship}? Intéressant choice! Mais peux-tu le défendre contre tous les haters? 💕\n\n🔥 Explique pourquoi ce ship est SUPERIOR! ⚡"
    
    # Sinon, proposer des ships populaires pour débat
    ai_response = get_ai_response([{
        "role": "system",
        "content": """Crée un post provocateur sur les ships anime avec :
        - 3 ships controversés/populaires récents
        - Questions qui vont créer des débats passionnés
        - Style dramatique et engageant
        - Emojis et langage otaku
        - Encourage les utilisateurs à défendre leurs choix
        - Maximum 400 caractères"""
    }, {
        "role": "user",
        "content": "Lance un débat épique sur les ships anime!"
    }], max_tokens=200, temperature=0.9)
    
    if ai_response:
        return f"💕⚔️ SHIP WAR ARENA!\n\n{ai_response}\n\n🔥 Tape /shipwar [ton ship] pour entrer dans la bataille!"
    else:
        return "💕⚔️ SHIP WAR TIME!\n\n🔥 Naruto x Hinata VS Naruto x Sakura?\n💥 Deku x Ochako VS Deku x Todoroki?\n⚡ Edward x Winry VS Edward x Roy?\n\n💀 Tape /shipwar [ton ship] et DÉFENDS-LE!"

@command('otakutest', '🎭 Test ultime: Quel type d\'otaku es-tu?')
def cmd_otakutest(sender_id, message_text=""):
    """Test de personnalité otaku ultra-engageant"""
    if not active_clients:
        return "❌ Le laboratoire otaku est fermé!"
    
    ai_response = get_ai_response([{
        "role": "system",
        "content": """Crée un test de personnalité otaku engageant avec :
        - Question psychologique sur les préférences anime/manga
        - 4 choix de réponse qui révèlent des archétypes otaku
        - Style fun et addictif
        - Question qui fait réfléchir sur sa personnalité
        - Maximum 350 caractères
        Format: Question + 4 choix A/B/C/D avec descriptions courtes"""
    }, {
        "role": "user",
        "content": "Crée une question de test otaku personality!"
    }], max_tokens=180, temperature=0.8)
    
    if ai_response:
        return f"🎭✨ TEST OTAKU PERSONALITY!\n\n{ai_response}\n\n🔮 Réponds avec la lettre pour découvrir ton type!"
    else:
        return "🎭 Tu regardes un nouvel anime, que fais-tu d'abord?\n\nA) J'analyse le studio et staff 🎬\nB) Je ship déjà les persos 💕\nC) Je critique le plot 📝\nD) Je vibe avec la musique 🎵\n\n🔮 Réponds pour connaître ton type otaku!"

@command('animebattle', '⚔️ Fais combattre tes persos préférés!')
def cmd_animebattle(sender_id, message_text=""):
    """Battle épique entre personnages d'anime"""
    if not active_clients:
        return "❌ L'arène de combat est en maintenance!"
    
    if message_text.strip():
        fighters = message_text.strip()
        
        ai_response = get_ai_response([{
            "role": "system",
            "content": f"""Crée un combat épique entre les personnages: '{fighters}'
            
            Écris :
            - Combat détaillé et dramatique
            - Utilise leurs techniques/pouvoirs canoniques
            - Style shonen battle intense
            - Issue surprenante mais logique
            - Beaucoup d'onomatopées et action
            - Maximum 500 caractères"""
        }, {
            "role": "user",
            "content": f"Fais combattre: {fighters}"
        }], max_tokens=250, temperature=0.9)
        
        if ai_response:
            return f"⚔️💥 EPIC BATTLE!\n\n{ai_response}\n\n🏆 GG! Tape /animebattle [perso1 vs perso2] pour un nouveau combat!"
        else:
            return f"⚔️ {fighters} s'affrontent dans une bataille légendaire! Les coups fusent, les techniques secrètes pleuvent! 💥 Qui gagnera? À toi de l'imaginer! ⚡"
    
    return "⚔️ Fais combattre tes héros!\n\n💥 Ex: /animebattle Goku vs Saitama\n🔥 Ex: /animebattle Naruto vs Luffy\n⚡ Ex: /animebattle Light vs Lelouch\n\n🏆 Qui sera le champion?"

@command('help', '❓ Guide complet de toutes mes techniques secrètes!')
def cmd_help(sender_id, message_text=""):
    """Génère automatiquement l'aide basée sur toutes les commandes"""
    help_text = "🎌⚡ NAKAMA BOT - GUIDE ULTIME! ⚡🎌\n\n"
    
    for cmd_name, cmd_info in COMMANDS.items():
        help_text += f"/{cmd_name} - {cmd_info['description']}\n"
    
    help_text += "\n🔥 Utilisation: Tape / + commande"
    help_text += "\n💡 Ex: /waifu, /ia salut!, /recommend shonen"
    help_text += f"\n🤖 {len(active_clients)} AI clients actifs"
    help_text += "\n\n⚡ Créé avec amour pour les otakus! 💖"
    
    return help_text

# 🌐 ROUTES FLASK 🌐

@app.route("/", methods=['GET'])
def home():
    return jsonify({
        "status": "🎌 NakamaBot Otaku Edition is alive! ⚡",
        "timestamp": datetime.now().isoformat(),
        "commands_loaded": len(COMMANDS),
        "ai_clients_active": len(active_clients),
        "active_quizzes": len(active_quizzes)
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
    """Traite les commandes de façon modulaire avec gestion des quiz"""
    
    # Vérifier si c'est une réponse à un quiz actif
    with quiz_lock:
        if sender_id in active_quizzes:
            quiz = active_quizzes[sender_id]
            if not quiz.answered and datetime.now() < quiz.expires_at:
                # Traiter la réponse du quiz
                user_answer = message_text.upper().strip()
                quiz.answered = True
                
                if user_answer == quiz.correct_answer:
                    response = f"🎉 BRAVO! Bonne réponse!\n\n{quiz.explanation}\n\n🏆 Tu es un vrai otaku! Tape /animequiz pour un nouveau défi!"
                elif user_answer in ['A', 'B', 'C', 'D']:
                    response = f"❌ Dommage! La bonne réponse était: {quiz.correct_answer}\n\n{quiz.explanation}\n\n💪 Tape /animequiz pour te rattraper!"
                else:
                    response = f"🤔 Réponse invalide! La bonne réponse était: {quiz.correct_answer}\n\n{quiz.explanation}\n\n⚡ Tape /animequiz pour un nouveau quiz!"
                
                del active_quizzes[sender_id]
                return response
    
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
        "ai_clients": len(active_clients),
        "active_quizzes": len(active_quizzes),
        "client_status": [{"name": c["name"], "models": len(c["models"])} for c in active_clients],
        "config": {
            "verify_token_set": bool(VERIFY_TOKEN),
            "page_token_set": bool(PAGE_ACCESS_TOKEN),
            "total_api_keys": len([c for c in API_CONFIGS if c["key"]])
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
        "commands": commands_info,
        "ai_clients_active": len(active_clients)
    })

@app.route("/quiz/stats", methods=['GET'])
def quiz_stats():
    """Statistiques des quiz actifs"""
    with quiz_lock:
        stats = []
        for sender_id, quiz in active_quizzes.items():
            remaining = max(0, int((quiz.expires_at - datetime.now()).total_seconds()))
            stats.append({
                "sender_id": sender_id,
                "question": quiz.question[:50] + "..." if len(quiz.question) > 50 else quiz.question,
                "remaining_seconds": remaining,
                "answered": quiz.answered
            })
    
    return jsonify({
        "active_quizzes": len(active_quizzes),
        "quizzes": stats
    })

@app.route("/api/status", methods=['GET'])
def api_status():
    """Status détaillé de tous les clients API"""
    clients_status = []
    
    for config in active_clients:
        try:
            # Test simple pour vérifier si le client fonctionne
            test_response = config["client"].chat.completions.create(
                model=config["models"][0],
                messages=[{"role": "user", "content": "test"}],
                max_tokens=1,
                timeout=5
            )
            status = "online"
        except Exception as e:
            status = f"error: {str(e)[:50]}"
        
        clients_status.append({
            "name": config["name"],
            "status": status,
            "models": config["models"],
            "base_url": config.get("base_url", "OpenAI default")
        })
    
    return jsonify({
        "timestamp": datetime.now().isoformat(),
        "total_clients": len(active_clients),
        "clients": clients_status
    })

# 🎌 NOUVELLES COMMANDES ULTRA-ATTRACTIVES 🎌

@command('waifurat', '🐭 Ton classement personnel de waifus!')
def cmd_waifurat(sender_id, message_text=""):
    """Système de ranking de waifus personnel"""
    if not active_clients:
        return "❌ Le système de ranking est offline!"
    
    if message_text.strip():
        waifu_name = message_text.strip()
        
        ai_response = get_ai_response([{
            "role": "system",
            "content": f"""L'utilisateur soumet '{waifu_name}' pour son ranking de waifus.
            
            Réponds avec :
            - Note sur 10 avec justification otaku
            - Analyse des qualités de cette waifu
            - Comparaison subtile avec d'autres waifus populaires
            - Style passionné et expert
            - Encourage à soumettre d'autres waifus
            - Maximum 400 caractères"""
        }, {
            "role": "user",
            "content": f"Rate cette waifu: {waifu_name}"
        }], max_tokens=200, temperature=0.8)
        
        if ai_response:
            return f"🐭📊 WAIFU RATING!\n\n{ai_response}\n\n⭐ Soumets d'autres waifus avec /waifurat [nom]!"
        else:
            return f"🐭 {waifu_name}? Excellent taste! 9/10 pour moi! 💕\n\n📊 Continue ton ranking avec /waifurat [autre waifu]!"
    
    return "🐭⭐ WAIFU RATING SYSTEM!\n\n💕 Soumets tes waifus préférées et je les raterai comme un vrai connaisseur!\n\n🎯 Ex: /waifurat Nezuko\n✨ Ex: /waifurat Zero Two\n\n📊 Construis ton tier list personnel!"

@command('animemood', '🎭 Anime parfait selon ton humeur!')
def cmd_animemood(sender_id, message_text=""):
    """Recommandation basée sur l'humeur"""
    if not active_clients:
        return "❌ Le mood detector est en panne!"
    
    mood = message_text.strip() or "aléatoire"
    
    ai_response = get_ai_response([{
        "role": "system",
        "content": f"""L'utilisateur se sent '{mood}'. Recommande 2-3 anime parfaits pour cette humeur avec :
        - Analyse psychologique de pourquoi ces anime matchent l'humeur
        - Descriptions émotionnelles des anime
        - Impact thérapeutique/émotionnel
        - Style empathique et expert
        - Maximum 450 caractères"""
    }, {
        "role": "user",
        "content": f"Je me sens {mood}, quel anime regarder?"
    }], max_tokens=230, temperature=0.8)
    
    if ai_response:
        return f"🎭💫 MOOD MATCH!\n\n{ai_response}\n\n🌟 Ton mood va changer avec ces pépites!"
    else:
        return f"🎭 Mood: {mood}?\n\n✨ Je recommande:\n• Your Name (émotions pures) 😭\n• Mob Psycho (développement perso) 💪\n• Nichijou (pur fun) 😂\n\n💫 Perfect match pour ton état d'esprit!"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    
    logger.info("🚀 Démarrage NakamaBot Otaku Edition Enhanced...")
    logger.info(f"🎌 Commandes chargées: {len(COMMANDS)}")
    logger.info(f"📋 Liste: {list(COMMANDS.keys())}")
    logger.info(f"🤖 Clients AI actifs: {len(active_clients)}")
    logger.info(f"🔧 Configurations API: {[c['name'] for c in active_clients]}")
    
    app.run(host="0.0.0.0", port=port, debug=False)
