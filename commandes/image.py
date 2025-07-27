import urllib.parse

def validate_image_prompt(prompt):
    """Valider et nettoyer les prompts d'images"""
    if not prompt or len(prompt.strip()) < 3:
        return False, "Prompt trop court! Minimum 3 caractères! 📝"
    
    if len(prompt) > 200:
        return False, "Prompt trop long! Maximum 200 caractères! ✂️"
    
    # Mots interdits (optionnel, pour éviter le contenu inapproprié)
    forbidden_words = ['nsfw', 'nude', 'explicit', 'xxx', 'sexual', 'porn']
    for word in forbidden_words:
        if word in prompt.lower():
            return False, "🚫 Contenu inapproprié détecté! Restez respectueux! 🌸"
    
    return True, prompt.strip()

def execute(sender_id, args=""):
    """Générateur d'images IA - Version finale optimisée"""
    if not args.strip():
        return """🎨🎌 GÉNÉRATEUR D'IMAGES IA! 🎌🎨

🖼️ /image [description] - Génère ton image
🎨 /image beautiful sunset mountain - Exemple
🌸 /image cute cat wearing hat - Exemple
⚡ /image random - Surprise aléatoire
🎭 /image styles - Voir les styles

✨ Décris ton imagination, je la créé! 💖"""
    
    prompt = args.strip().lower()
    sender_id = str(sender_id)
    
    # Commandes spéciales
    if prompt == "styles":
        return """🎨 STYLES DISPONIBLES:

🌸 anime - Style anime classique
⚡ realistic - Photo-réaliste
🔥 cyberpunk - Futuriste néon
🌙 fantasy - Monde magique
🎭 artistic - Style artistique
🤖 sci-fi - Science-fiction
🌈 colorful - Explosion de couleurs
🖼️ portrait - Portrait détaillé

💡 Combine les styles: "anime cyberpunk girl" ✨"""
    
    if prompt == "random":
        themes = [
            "beautiful landscape with mountains and sunset",
            "cute cat wearing a wizard hat with magical sparkles", 
            "futuristic cyberpunk city with neon lights at night",
            "fantasy dragon flying over a medieval castle",
            "colorful abstract art with geometric patterns",
            "peaceful forest with sunlight filtering through trees",
            "space scene with planets and galaxies",
            "vintage car on a scenic coastal road"
        ]
        prompt = random.choice(themes)
    
    # Valider le prompt
    is_valid, validated_prompt = validate_image_prompt(prompt)
    if not is_valid:
        return f"❌ {validated_prompt}"
    
    try:
        # Améliorer le prompt automatiquement
        enhanced_prompt = f"high quality, detailed, beautiful, {validated_prompt}, masterpiece, trending"
        
        # Encoder pour l'URL
        encoded_prompt = urllib.parse.quote(enhanced_prompt)
        
        # Générer l'image avec API gratuite Pollinations
        seed = random.randint(100000, 999999)
        image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=768&height=768&seed={seed}&enhance=true&model=flux&nologo=true"
