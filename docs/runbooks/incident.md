# Incident

1. Fermer l'entrée réseau du service touché. Activer sa maintenance, suspendre ses processus
   et conserver les preuves minimisées dans le périmètre de son opérateur.
2. Classer l'incident : authentification, exposition privée, notification ambiguë, données
   manquantes, clés ou infrastructure. Ne jamais copier de permutation, jeton ou contenu
   privé dans un ticket, écran organisateur ou journal partagé.
3. Si un tirage déjà disponible manque après restauration, garder la maintenance. Rechercher
   un point récupérable contenant exactement le même résultat et les bonnes clés. Aucun
   nouveau tirage sous la même identité d'événement n'est une réparation acceptable.
4. Si la récupération échoue, informer le groupe par un canal autorisé et appliquer
   l'annulation explicite ; l'opérateur ne doit pas reconstruire des associations à la main.
5. Si l'envoi est ambigu, consulter le fournisseur sans renvoyer. Conserver honnêtement
   l'incertitude lorsque SMTP ne permet pas de prouver la remise.
6. Restaurer selon [restore.md](restore.md), requalifier les fonctions touchées et documenter
   cause, intervalle, données exposées éventuelles, mesures et critères de reprise.

La communication réelle avec le groupe relève de l'organisateur/opérateur et requiert
son action explicite. Le code de cette phase ne transmet aucun message d'incident.
