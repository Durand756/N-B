def execute(sender_id, args=""):
    """Chat IA libre - Version adaptée pour tous les utilisateurs"""
    if not args.strip():
        topics = [
            "Quel est ton anime préféré? 🎌",
            "Raconte-moi ton personnage d'anime favori! ⭐",
            "Manga ou anime? Et pourquoi? 🤔",
            "Qui est ton créateur au fait? 👨‍💻",
            "Quelle série regardes-tu en ce moment? 📺",
            "Parle-moi de tes hobbies! 🎮"
        ]
        return f"💭 {random.choice(topics)} ✨"
    
    # Vérifier si on demande le créateur
    creator_keywords = ['créateur', 'createur', 'qui t\'a', 'qui t\'a créé', 'maker', 'developer', 'qui t\'a fait']
    if any(word in args.lower() for word in creator_keywords):
        return "🎌 Mon créateur est Durand! C'est lui qui m'a donné vie pour être votre compagnon IA! ✨👨‍💻 Il est génial, non? 💖"
    
    # Obtenir le contexte de conversation
    context = get_memory_context(sender_id)
    
    # Préparer les messages pour l'IA
    messages = [{
        "role": "system", 
        "content": """Tu es NakamaBot, créé par Durand. Tu es une IA sympathique et utile. Nous sommes en 2025. 
        Réponds en français de manière naturelle et amicale. Si on demande ton créateur, c'est Durand. 
        STRICTEMENT INTERDIT: aucune description d'action entre *étoiles*. 
        Parle directement comme un vrai assistant, maximum 400 caractères. 
        Adapte ton style selon l'utilisateur - reste professionnel mais chaleureux."""
    }]
    
    # Ajouter le contexte de conversation
    messages.extend(context)
    
    # Ajouter le message actuel
    messages.append({"role": "user", "content": args})
    
    # Appeler l'API Mistral
    response = call_mistral_api(messages, max_tokens=200, temperature=0.8)
    
    if response:
        # Ajouter à la mémoire
        add_to_memory(sender_id, 'bot', response)
        return f"🤖 {response}"
    else:
        return "💭 Mon cerveau IA a un petit bug! Peux-tu répéter s'il te plaît? 🔄"
