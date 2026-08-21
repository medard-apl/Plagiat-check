# -*- coding: utf-8 -*-
"""
Jeu de données de calibration pour le pipeline de détection.

Chaque entrée est une paire (segment du "mémoire", candidat trouvé par une
source) avec une étiquette attendue : "exact" (copie quasi mot pour mot),
"semantic" (paraphrase / reformulation du même contenu), ou "none" (pas de
plagiat, même si le sujet peut se ressembler).

Tous les textes sont écrits pour ce jeu de test (pas de contenu extrait
d'internet) : ce qu'on calibre ici, c'est la logique de comparaison LOCALE
(fingerprint.py + embeddings.py), pas la qualité des résultats renvoyés par
les API externes — ça, on ne le contrôle pas.

Catégorie la plus importante à surveiller : "same_topic" — des textes qui
parlent du même sujet mais ne sont PAS empruntés l'un à l'autre. C'est
exactement le cas qui a produit le faux positif à 86% observé en conditions
réelles (l'intro générique du mémoire de test contre un guide méthodologique
Scribbr) : deux textes sur le même thème, avec du vocabulaire académique
commun, mais sans reformulation de l'un vers l'autre.
"""

CALIBRATION_PAIRS = [
    # ============================================================
    # EXACT — citation quasi mot pour mot (avec ou sans texte autour)
    # ============================================================
    {
        "id": "exact_1_embedded",
        "category": "exact",
        "expected": "exact",
        "segment": (
            "Le stage de fin d'études permet aux étudiants de mettre en pratique les "
            "compétences acquises durant leur formation universitaire, tout en découvrant "
            "les réalités du monde professionnel avant leur insertion définitive sur le "
            "marché du travail."
        ),
        "candidate": (
            "Guide de préparation au stage professionnel. " * 8 +
            "Le stage de fin d'études permet aux étudiants de mettre en pratique les "
            "compétences acquises durant leur formation universitaire, tout en découvrant "
            "les réalités du monde professionnel avant leur insertion définitive sur le "
            "marché du travail. " +
            "Conseils supplémentaires pour réussir son entretien de stage. " * 8
        ),
        "note": "Citation intégrale, noyée dans un candidat 3x plus long des deux côtés.",
    },
    {
        "id": "exact_2_identical",
        "category": "exact",
        "expected": "exact",
        "segment": (
            "Les bases de données relationnelles organisent l'information en tables liées "
            "entre elles par des clés, ce qui permet d'éviter la duplication et de garantir "
            "la cohérence des données stockées."
        ),
        "candidate": (
            "Les bases de données relationnelles organisent l'information en tables liées "
            "entre elles par des clés, ce qui permet d'éviter la duplication et de garantir "
            "la cohérence des données stockées."
        ),
        "note": "Copie intégrale, tailles identiques (cas le plus simple).",
    },
    {
        "id": "exact_3_partial_start",
        "category": "exact",
        "expected": "exact",
        "segment": (
            "L'agriculture de conservation repose sur trois principes fondamentaux : la "
            "réduction du travail du sol, la couverture permanente et la diversification "
            "des cultures. Ces pratiques limitent l'érosion et améliorent la fertilité "
            "des sols sur le long terme."
        ),
        "candidate": (
            "L'agriculture de conservation repose sur trois principes fondamentaux : la "
            "réduction du travail du sol, la couverture permanente et la diversification "
            "des cultures. " +
            "Cette approche a été largement étudiée en Afrique de l'Ouest depuis les années 2000. " * 5
        ),
        "note": "Seule la première moitié du segment est copiée, le reste diverge.",
    },
    {
        "id": "exact_4_english",
        "category": "exact",
        "expected": "exact",
        "segment": (
            "Transfer learning allows a model trained on a large dataset to be fine-tuned "
            "on a smaller, task-specific dataset, considerably reducing the amount of "
            "labeled data required for training."
        ),
        "candidate": (
            "Deep learning fundamentals overview. " * 6 +
            "Transfer learning allows a model trained on a large dataset to be fine-tuned "
            "on a smaller, task-specific dataset, considerably reducing the amount of "
            "labeled data required for training. " +
            "Several benchmark results are discussed in the following sections. " * 6
        ),
        "note": "Citation en anglais, noyée dans un article plus long.",
    },

    # ============================================================
    # SEMANTIC — vraie paraphrase (même sens, formulation différente)
    # ============================================================
    {
        "id": "semantic_1_french",
        "category": "paraphrase",
        "expected": "semantic",
        "segment": (
            "La déforestation en Amazonie s'est accélérée ces dix dernières années, "
            "principalement à cause de l'expansion des terres agricoles et de l'élevage bovin."
        ),
        "candidate": (
            "Au cours de la dernière décennie, la forêt amazonienne a connu un recul "
            "important, largement dû à la conversion de zones boisées en pâturages et en "
            "surfaces cultivées."
        ),
        "note": "Même idée, vocabulaire et structure de phrase très différents.",
    },
    {
        "id": "semantic_2_french",
        "category": "paraphrase",
        "expected": "semantic",
        "segment": (
            "Le sommeil profond joue un rôle essentiel dans la consolidation de la mémoire, "
            "en permettant au cerveau de trier et de stabiliser les informations acquises "
            "durant la journée."
        ),
        "candidate": (
            "C'est pendant les phases de sommeil lent profond que le cerveau organise et "
            "fixe durablement les souvenirs formés au cours de la journée précédente."
        ),
        "note": "Reformulation assez proche, sujet neuroscience/sommeil.",
    },
    {
        "id": "semantic_3_cross_lingual",
        "category": "paraphrase",
        "expected": "semantic",
        "segment": (
            "La compression d'image sans perte permet de réduire la taille d'un fichier "
            "sans dégrader la qualité visuelle, contrairement aux méthodes avec perte."
        ),
        "candidate": (
            "Lossless image compression reduces file size while preserving the exact "
            "original visual quality, unlike lossy compression techniques."
        ),
        "note": "Paraphrase cross-lingue (français -> anglais), teste multilingual-e5.",
    },
    {
        "id": "semantic_4_loose",
        "category": "paraphrase",
        "expected": "semantic",
        "segment": (
            "Beaucoup de petites entreprises peinent à adopter le télétravail faute d'outils "
            "numériques adaptés et par crainte de perdre en contrôle sur la productivité "
            "de leurs équipes."
        ),
        "candidate": (
            "Le manque d'équipement technologique approprié, combiné à une certaine "
            "méfiance envers la gestion à distance des salariés, freine encore l'adoption "
            "du travail à domicile dans les PME."
        ),
        "note": "Paraphrase plus \"lâche\", peu de mots partagés — cas limite volontaire.",
    },

    # ============================================================
    # SAME_TOPIC — sujet commun, mais PAS de plagiat entre les deux
    # (catégorie la plus à risque de faux positif, voir docstring)
    # ============================================================
    {
        "id": "same_topic_1_memoire_intro",
        "category": "same_topic",
        "expected": "none",
        "segment": (
            "Ce document constitue un mémoire fictif, généré uniquement à des fins de test "
            "technique. Il ne présente aucune valeur académique et sert exclusivement à "
            "vérifier le bon fonctionnement du pipeline d'analyse anti-plagiat."
        ),
        "candidate": (
            "Rédiger un mémoire demande une méthodologie rigoureuse : définir une "
            "problématique claire, structurer un plan cohérent, et soigner la mise en "
            "forme finale avant le dépôt auprès du jury."
        ),
        "note": "Cas réel qui a produit un faux positif à 86% en conditions réelles.",
    },
    {
        "id": "same_topic_2_definitions",
        "category": "same_topic",
        "expected": "none",
        "segment": (
            "Une API (interface de programmation applicative) est un ensemble de règles "
            "qui permet à deux logiciels de communiquer entre eux de façon standardisée."
        ),
        "candidate": (
            "On appelle API le point d'accès qu'un service informatique met à disposition "
            "pour que d'autres programmes puissent l'utiliser sans connaître son "
            "fonctionnement interne."
        ),
        "note": "Deux définitions indépendantes d'un terme technique courant.",
    },
    {
        "id": "same_topic_3_climate",
        "category": "same_topic",
        "expected": "none",
        "segment": (
            "Le réchauffement climatique entraîne une hausse du niveau des mers, menaçant "
            "directement les infrastructures côtières des grandes métropoles."
        ),
        "candidate": (
            "Les canicules deviennent plus fréquentes et plus intenses, ce qui accroît la "
            "mortalité liée à la chaleur chez les populations les plus vulnérables."
        ),
        "note": "Même thème général (réchauffement climatique), conséquences différentes.",
    },
    {
        "id": "same_topic_4_ai_ethics",
        "category": "same_topic",
        "expected": "none",
        "segment": (
            "Les biais algorithmiques peuvent reproduire ou amplifier des discriminations "
            "existantes lorsque les données d'entraînement ne sont pas représentatives."
        ),
        "candidate": (
            "La transparence des modèles d'intelligence artificielle reste un défi majeur, "
            "notamment pour les systèmes de type boîte noire utilisés en santé."
        ),
        "note": "Même domaine (éthique de l'IA), problématiques distinctes.",
    },

    # ============================================================
    # UNRELATED — aucun rapport, contrôle négatif simple
    # ============================================================
    {
        "id": "unrelated_1",
        "category": "unrelated",
        "expected": "none",
        "segment": (
            "Les félins domestiques passent en moyenne seize heures par jour à dormir, un "
            "comportement hérité de leurs ancêtres chasseurs nocturnes."
        ),
        "candidate": (
            "La tour Eiffel a été construite pour l'Exposition universelle de 1889 et "
            "devait initialement être démontée vingt ans plus tard."
        ),
        "note": "Sujets totalement disjoints.",
    },
    {
        "id": "unrelated_2",
        "category": "unrelated",
        "expected": "none",
        "segment": (
            "La cuisson à basse température permet d'attendrir les morceaux de viande les "
            "plus fibreux sans les dessécher."
        ),
        "candidate": (
            "L'inflation mesure la hausse générale et durable des prix des biens et "
            "services dans une économie donnée."
        ),
        "note": "Cuisine vs économie.",
    },
    {
        "id": "unrelated_3",
        "category": "unrelated",
        "expected": "none",
        "segment": (
            "Le volcanisme sous-marin façonne continuellement de nouvelles formations "
            "rocheuses au fond des océans."
        ),
        "candidate": (
            "Le championnat local de football amateur regroupe une vingtaine d'équipes "
            "réparties en trois divisions régionales."
        ),
        "note": "Géologie vs sport.",
    },
    {
        "id": "unrelated_4",
        "category": "unrelated",
        "expected": "none",
        "segment": (
            "La typographie d'un document influence fortement sa lisibilité, en particulier "
            "sur les écrans de petite taille."
        ),
        "candidate": (
            "La migration des oiseaux se déclenche généralement en réponse aux variations "
            "de température et à la durée du jour."
        ),
        "note": "Design vs ornithologie.",
    },
]