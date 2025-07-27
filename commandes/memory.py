def execute(sender_id, args=""):
    """Afficher la mémoire de conversation"""
    sender_id = str(sender_id)
    
    # Vérifier s'il y a des conversations précédentes
    if not user_memory.get(sender_id):
        return "💾 Aucune conversation précédente! C'est notre premier échange! ✨"
    
    # Construire l'affichage de la mémoire
    text = "💾🎌 MÉMOIRE DE NOS CONVERSATIONS!\n\n"
    
    # Parcourir les messages dans l'ordre
    for i, msg in enumerate(user_memory[sender_id], 1):
        # Choisir l'emoji selon le type de message
        emoji = "🗨️" if msg['type'] == 'user' else "🤖"
        
        # Créer un aperçu du message (limité à 60 caractères)
        preview = msg['content'][:60] + "..." if len(msg['content']) > 60 else msg['content']
        
        # Ajouter au texte
        text += f"{emoji} {i}. {preview}\n"
    
    # Ajouter les statistiques
    text += f"\n💭 {len(user_memory[sender_id])}/10 messages sauvegardés"
    
    # Ajouter info sur les jeux actifs si applicable
    if sender_id in game_sessions:
        game_info = game_sessions[sender_id]
        score = game_info.get('score', 0)
        text += f"\n🎲 Jeu actif: {score} points"
    
    # Ajouter timestamp du dernier message si disponible
    if user_memory[sender_id]:
        last_msg = user_memory[sender_id][-1]
        if 'timestamp' in last_msg:
            try:
                # Convertir l'ISO timestamp en format lisible
                from datetime import datetime
                timestamp = datetime.fromisoformat(last_msg['timestamp'].replace('Z', '+00:00'))
                text += f"\n🕐 Dernière activité: {timestamp.strftime('%d/%m %H:%M')}"
            except:
                pass
    
    text += "\n\n💡 La mémoire se vide automatiquement après 10 messages!"
    
    return text
