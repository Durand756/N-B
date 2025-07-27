def execute(sender_id, args=""):
    """Panneau administrateur"""
    if not is_admin(sender_id):
        return f"🔐 Accès refusé! Admins seulement! ❌\nVotre ID: {sender_id}"
    
    if not args.strip():
        return f"""🔐 PANNEAU ADMIN v3.0

📊 COMMANDES DISPONIBLES:
• /admin stats - Statistiques détaillées
• /admin users - Liste des utilisateurs  
• /admin games - Statistiques des jeux
• /admin memory - État de la mémoire
• /admin test - Test des services
• /broadcast [msg] - Diffusion générale

📈 ÉTAT ACTUEL:
👥 Utilisateurs: {len(user_list)}
💾 Conversations: {len(user_memory)}
🎲 Jeux actifs: {len(game_sessions)}
🔐 Admin ID: {sender_id}

✅ Système opérationnel
👨‍💻 Créé par Durand"""
    
    action = args.strip().lower()
    
    if action == "stats":
        # Calculer des statistiques détaillées
        total_messages = sum(len(messages) for messages in user_memory.values())
        active_users = len([uid for uid in user_list if uid in user_memory])
        
        return f"""📊 STATISTIQUES COMPLÈTES

👥 UTILISATEURS:
• Total: {len(user_list)}
• Actifs: {active_users}
• Ratio activité: {(active_users/len(user_list)*100):.1f}%

💬 CONVERSATIONS:
• Sessions: {len(user_memory)}
• Messages total: {total_messages}
• Moyenne/user: {(total_messages/len(user_memory)):.1f}

🎲 JEUX:
• Sessions actives: {len(game_sessions)}
• Participation: {(len(game_sessions)/len(user_list)*100):.1f}%

🔐 SYSTÈME:
• Admin ID: {sender_id}
• Version: 3.0
• Créateur: Durand"""
    
    elif action == "users":
        if not user_list:
            return "👥 Aucun utilisateur enregistré!"
        
        text = f"👥 LISTE DES UTILISATEURS ({len(user_list)}):\n\n"
        for i, user_id in enumerate(list(user_list)[:20], 1):  # Limiter à 20 pour éviter les messages trop longs
            status = "🎲" if user_id in game_sessions else ("💬" if user_id in user_memory else "👤")
            text += f"{status} {i}. {user_id}\n"
        
        if len(user_list) > 20:
            text += f"\n... et {len(user_list) - 20} autres utilisateurs"
            
        return text
    
    elif action == "games":
        if not game_sessions:
            return "🎲 Aucun jeu actif actuellement!"
        
        text = f"🎲 JEUX ACTIFS ({len(game_sessions)}):\n\n"
        for user_id, session in list(game_sessions.items()):
            score = session.get('score', 0)
            started = session.get('started', 'Inconnu')
            text += f"👤 {user_id}: {score} points\n"
            if started != 'Inconnu':
                try:
                    from datetime import datetime
                    start_time = datetime.fromisoformat(started)
                    text += f"   📅 Démarré: {start_time.strftime('%d/%m %H:%M')}\n"
                except:
                    pass
        
        return text
    
    elif action == "memory":
        if not user_memory:
            return "💾 Aucune conversation en mémoire!"
        
        total_messages = sum(len(messages) for messages in user_memory.values())
        avg_messages = total_messages / len(user_memory) if user_memory else 0
        
        text = f"💾 ÉTAT DE LA MÉMOIRE:\n\n"
        text += f"📊 Sessions: {len(user_memory)}\n"
        text += f"📨 Messages total: {total_messages}\n"
        text += f"📈 Moyenne/session: {avg_messages:.1f}\n"
        text += f"💽 Capacité/session: 10 messages max\n\n"
        
        # Top 5 des utilisateurs les plus actifs
        top_users = sorted(user_memory.items(), key=lambda x: len(x[1]), reverse=True)[:5]
        text += "🏆 TOP 5 ACTIFS:\n"
        for i, (user_id, messages) in enumerate(top_users, 1):
            text += f"{i}. {user_id}: {len(messages)} msgs\n"
        
        return text
    
    elif action == "test":
        results = []
        
        # Test IA Mistral
        try:
            test_response = call_mistral_api([{"role": "user", "content": "Test"}], max_tokens=10)
            results.append(f"🧠 IA Mistral: {'✅' if test_response else '❌'}")
        except Exception as e:
            results.append(f"🧠 IA Mistral: ❌ ({str(e)[:30]})")
        
        # Test Facebook API
        results.append(f"📱 Facebook API: {'✅' if 'PAGE_ACCESS_TOKEN' in globals() and globals()['PAGE_ACCESS_TOKEN'] else '❌'}")
        
        # Test structure des données
        results.append(f"💾 Mémoire utilisateurs: {'✅' if user_memory else '❌'}")
        results.append(f"👥 Liste utilisateurs: {'✅' if user_list else '❌'}")
        results.append(f"🎲 Sessions de jeu: {'✅' if isinstance(game_sessions, dict) else '❌'}")
        
        return "🔍 TESTS SYSTÈME:\n\n" + "\n".join(results)
    
    elif action == "clear":
        # Commande dangereuse - demander confirmation
        return """⚠️ COMMANDE DANGEREUSE!

Pour effacer les données, utilisez:
• /admin clear-memory - Vider la mémoire
• /admin clear-users - Vider la liste d'utilisateurs  
• /admin clear-games - Arrêter tous les jeux

⚠️ Ces actions sont irréversibles!"""
    
    elif action == "clear-memory":
        count = len(user_memory)
        user_memory.clear()
        return f"🗑️ Mémoire effacée! {count} conversations supprimées."
    
    elif action == "clear-users":
        count = len(user_list)
        user_list.clear()
        return f"🗑️ Liste utilisateurs effacée! {count} utilisateurs supprimés."
    
    elif action == "clear-games":
        count = len(game_sessions)
        game_sessions.clear()
        return f"🗑️ Jeux arrêtés! {count} sessions fermées."
    
    else:
        return f"❓ Action '{action}' inconnue!\n\nUtilisez /admin sans paramètre pour voir les options disponibles."
