# Accessibilité — phase 9

Recette automatisée du run référencé dans report.md : Chromium natif et Axe avec tags WCAG 2 A/AA,
2.1 A/AA et 2.2 AA. Onze scans portail, vingt-deux coffre, zéro violation signalée. Les JSON sont
archivés dans le répertoire du run ; les captures synthétiques restent dans `.local/ui-results`.

Les parcours comprennent connexion par code, erreurs réseau, vraie absence de session puis reprise,
conflits dans deux fenêtres, profil, trois souhaits, règles, rappels, retrait, boutique, révélation,
masquage Échap/bouton et suppression du contenu d’un ancien onglet après annulation. Largeurs
360/390/768/1440 CSS pixels, texte long et accents, reflow équivalent 200 %, absence de débordement.
Le lien d’évitement, le focus d’erreur et le retour au bouton de révélation sont vérifiés au clavier.
Les animations sont désactivées pour cette recette et respectent prefers-reduced-motion.

T22 reste PARTIAL. La voix et les annonces d’un lecteur d’écran, le téléphone réel avec clavier
logiciel, le zoom du menu navigateur à 200 %, la qualité globale des titres et la lisibilité
assistive ne sont pas attestés par ces scans. Aucune conformité WCAG globale n’est annoncée.
Les étapes restantes et les traces à conserver sont dans manual-gates.md.
