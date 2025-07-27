import os
import glob

def execute(sender_id, args=""):
    """Aide du bot - Liste automatiquement toutes les commandes disponibles"""
    
    # Découvrir automatiquement toutes les commandes
    commands_dir = "Commandes"
    command_files = glob.glob(f"{commands_dir}/*.py")
    
    # Descriptions personnalisées pour certaines commandes
    command_descriptions = {
        "start": "🌟 Présentation du bot",
        "ai": "🧠 Chat libre avec IA",
        "story": "📖 Histoires anime/manga",
        "waifu": "👸 Génère ta waifu",
        "actionverite": "🎲 Jeu Action ou Vérité",
        "image": "🎨 Génère des images AI",
        "memory": "💾 Voir l'historique",
        "help": "❓ Cette aide",
        "admin": "🔐 Panneau admin",
        "broadcast": "📢 Diffusion admin"
    }
    
    # Construire la liste des commandes
    available_commands = {}
    for file_path in command_files:
        command_name = os.path.basename(file_path)[:-3]  # Enlever .py
        description = command_descriptions.get(command_name, "📄 Commande disponible")
        available_commands[command_name] = description
    
    # Trier les commandes
    sorted_commands = dict(sorted(available_commands.items()))
    
    # Construire le message d'aide
    text = "🎌⚡ NAKAMABOT v3.0 GUIDE! ⚡🎌\n\n"
    
    # Commandes principales
    main_commands = ["start", "ai", "story", "waifu", "actionverite", "image", "memory", "help"]
    text += "📋 COMMANDES PRINCIPALES:\n"
    for cmd in main_commands:
        if cmd in sorted_commands:
            text += f"/{cmd} - {sorted_commands[cmd]}\n"
    
    # Autres commandes disponibles
    other_commands = {k: v for k, v in sorted_commands.items() if k not in main_commands}
    if other_commands:
        text += "\n📦 AUTRES COMMANDES:\n"
        for cmd, desc in other_commands.items():
            text += f"/{cmd} - {desc}\n"
    
    # Section admin si applicable
    if is_admin(sender_id):
        admin_commands = ["admin", "broadcast"]
        admin_available = [cmd for cmd in admin_commands if cmd in sorted_commands]
        if admin_available:
            text += "\n🔐 COMMANDES ADMIN:\n"
            for cmd in admin_available:
                text += f"/{cmd} - {sorted_commands[cmd]}\n"
    
    # Footer
    text += f"\n📊 Total: {len(sorted_commands)} commandes"
    text += "\n👨‍💻 Créé par Durand"
    text += "\n✨ Ton compagnon otaku! 💖"
    
    return text
