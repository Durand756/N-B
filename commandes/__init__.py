# -*- coding: utf-8 -*-
"""
Package des commandes pour NakamaBot v3.0
Créé par Durand

Ce package contient toutes les commandes disponibles pour le bot.
Chaque fichier Python dans ce dossier représente une commande.

Structure attendue d'une commande:
- Nom du fichier: nom_commande.py
- Fonction principale: execute(sender_id, args)
- Retour: string (texte) ou dict (pour images)

Exemple de commande:
```python
def execute(sender_id, args):
    '''Description de la commande'''
    return "Réponse de la commande"
```

Variables globales disponibles dans chaque commande:
- user_memory: Mémoire des conversations
- user_list: Liste des utilisateurs
- game_sessions: Sessions de jeu actives
- ADMIN_IDS: IDs des administrateurs
- call_mistral_api: Fonction pour appeler l'IA
- add_to_memory: Ajouter à la mémoire
- get_memory_context: Récupérer le contexte
- is_admin: Vérifier si admin
- broadcast_message: Diffuser un message
- send_message: Envoyer un message
- send_image_message: Envoyer une image
- logger: Logger pour debug
- datetime, random, requests, time, os, json: Modules utiles
"""

__version__ = "3.0"
__author__ = "Durand"
__description__ = "Package des commandes NakamaBot"

# Liste des commandes disponibles (sera remplie automatiquement)
__all__ = []

import os
import glob

# Découvrir automatiquement toutes les commandes
current_dir = os.path.dirname(__file__)
command_files = glob.glob(os.path.join(current_dir, "*.py"))

for file_path in command_files:
    filename = os.path.basename(file_path)
    if filename != "__init__.py":
        command_name = filename[:-3]  # Enlever .py
        __all__.append(command_name)

# Informations pour le logging
COMMANDS_INFO = {
    "package_version": __version__,
    "total_commands": len(__all__),
    "commands_list": sorted(__all__),
    "package_path": current_dir
}

def get_command_info():
    """Retourne les informations sur les commandes disponibles"""
    return COMMANDS_INFO

def list_commands():
    """Retourne la liste des commandes disponibles"""
    return sorted(__all__)

# Message de debug au chargement du package
if __name__ != "__main__":
    print(f"📦 Package de commandes NakamaBot v{__version__} initialisé")
    print(f"📋 {len(__all__)} commandes découvertes: {', '.join(sorted(__all__))}")
