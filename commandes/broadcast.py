def execute(sender_id, args=""):
    """Diffusion de messages - Commande admin uniquement"""
    if not is_admin(sender_id):
        return f"🔐 Accès refusé! Commande réservée aux administrateurs! ❌\nVotre ID: {sender_id}"
    
    if not args.strip():
        return f"""📢 COMMANDE BROADCAST

📋 USAGE:
/broadcast [votre message]

📊 ÉTAT ACTUEL:
• 👥 Utilisateurs: {len(user_list)}
• 📱 Prêt pour diffusion

⚠️ IMPORTANT:
• Message limité à 1800 caractères
• Protection anti-spam intégrée
• Commande admin uniquement

💡 EXEMPLE:
/broadcast Bonjour à tous! Mise à jour disponible 🎉"""
    
    message_text = args.strip()
    
    # Vérifications de sécurité
    if len(message_text) > 1800:
        return "❌ Message trop long! Maximum 1800 caractères.\n📏 Caractères actuels: " + str(len(message_text))
    
    if not user_list:
        return "📢 Aucun utilisateur à notifier! La liste est vide."
    
    # Créer le message final avec en-tête officiel
    formatted_message = f"📢🎌 ANNONCE OFFICIELLE!\n\n{message_text}\n\n⚡ Message de l'équipe NakamaBot 💖"
    
    # Log de l'action admin AVANT l'envoi
    logger.info(f"📢 Admin {sender_id} lance broadcast: '{message_text[:50]}...'")
    
    try:
        # Envoyer le broadcast
        result = broadcast_message(formatted_message)
        
        # Vérifier les résultats
        if result.get("blocked"):
            return "🚫 Broadcast bloqué - message identique détecté récemment!"
        
        if result.get("already_running"):
            return "🚫 Un broadcast identique est déjà en cours d'envoi!"
        
        # Calculer le taux de succès
        success_rate = (result['sent'] / result['total'] * 100) if result['total'] > 0 else 0
        
        # Construire la réponse détaillée
        response = f"""📊 BROADCAST TERMINÉ!

✅ Envoyés: {result['sent']}
📱 Total destinataires: {result['total']}
❌ Erreurs: {result['errors']}
📈 Taux de succès: {success_rate:.1f}%

📝 Message: "{message_text[:50]}{'...' if len(message_text) > 50 else ''}"
🕐 Envoyé par: Admin {sender_id}
⏰ Heure: {datetime.now().strftime('%H:%M:%S')}"""

        # Ajouter des conseils selon les résultats
        if result['sent'] == 0:
            response += "\n\n💡 Aucun envoi réussi! Vérifiez:\n• Connectivité réseau\n• Token Facebook valide\n• Utilisateurs actifs"
        elif result['errors'] > 0:
            response += f"\n\n⚠️ {result['errors']} erreurs détectées. Causes possibles:\n• Utilisateurs ayant bloqué le bot\n• Comptes désactivés\n• Limites API atteintes"
        else:
            response += "\n\n🎉 Broadcast parfaitement réussi!"
        
        return response
        
    except Exception as e:
        logger.error(f"❌ Erreur critique broadcast: {e}")
        return f"""💥 ERREUR CRITIQUE!

❌ Échec du broadcast: {str(e)[:100]}

🔧 Actions suggérées:
• Vérifier la connectivité
• Contrôler le token Facebook  
• Réessayer dans quelques minutes

📞 Contactez Durand si le problème persiste."""
