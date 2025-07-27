def execute(sender_id, args=""):
    """Commande de démarrage - Présentation du bot"""
    
    # Préparer les messages pour l'IA pour une présentation dynamique
    messages = [{
        "role": "system",
        "content": "Tu es NakamaBot, créé par Durand. Tu es un assistant IA sympathique et utile. Nous sommes en 2025. Présente-toi avec joie en français, mentionne ton créateur Durand si pertinent. Sois chaleureux mais professionnel. INTERDIT: aucune description d'action entre *étoiles*. Parle directement, maximum 300 caractères."
    }, {
        "role": "user", 
        "content": "Présente-toi!"
    }]
    
    # Essayer d'obtenir une présentation personnalisée via l'IA
    response = call_mistral_api(messages, max_tokens=150, temperature=0.9)
    
    # Si l'IA répond, utiliser sa réponse, sinon utiliser une présentation par défaut
    if response:
        # Ajouter les informations essentielles si elles ne sont pas présentes
        if "/help" not in response.lower():
            response += "\n\n✨ Tape /help pour découvrir toutes mes fonctionnalités!"
        return response
    else:
        # Présentation par défaut en cas d'échec de l'IA
        return """🌟 Salut! Je suis NakamaBot, créé par Durand! 

🤖 Je suis votre assistant IA personnel, prêt à vous aider avec:
• 💬 Conversations intelligentes
• 🎨 Génération d'images
• 📖 Création d'histoires
• 🎲 Jeux interactifs
• 💾 Et bien plus encore!

✨ Tapez /help pour découvrir toutes mes commandes!
🎌 Ravi de faire votre connaissance! 💖"""
