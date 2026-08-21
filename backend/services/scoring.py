"""
Module d'agrégation et de calcul du score final.

Rôle : orchestrer tous les modules précédents (segmentation, sources
académiques, recherche web, fingerprinting, embeddings) pour produire le
rapport final attendu par le frontend : un score global de similarité
(0-100) et une liste de "matches" (passages suspects avec leur source).

C'est ce module qui décide, pour chaque segment, quelle est la MEILLEURE
correspondance trouvée parmi toutes les sources, et qui construit le
format de sortie exact attendu par script.js (voir la fonction
analyze_document plus bas pour le format précis).
"""

import time

from services.segmentation import segment_document
from services.academic_sources import search_academic_sources
from services.web_search import search_web_and_extract, extract_signature
from services.fingerprint import is_exact_copy
from services.embeddings import is_semantic_match


# Nombre minimum de k-grammes (séquences de 8 mots) partagés pour
# déclencher une détection de copie exacte — voir fingerprint.is_exact_copy.
MIN_SHARED_KGRAMS = 3

# Seuil de similarité sémantique, calibré via tests/test_calibration.py sur
# un jeu de 16 paires étiquetées (16 aout 2026) :
#   0.85 (valeur initiale, non calibrée) -> 4 faux positifs sur 8 cas
#         "même sujet mais pas de plagiat" (100% d'erreur sur cette classe)
#   0.90 -> meilleur F1 (0.89), rappel 100%, 1 seul faux positif
#   0.92 -> zéro faux positif, mais rappel à 75% (1 vraie paraphrase manquée)
# Choix de 0.90 : pour un outil dont le but premier est de repérer du
# plagiat, un faux négatif (plagiat manqué) est jugé plus coûteux qu'un
# faux positif occasionnel — d'autant que chaque "match" reste soumis à
# relecture humaine avant toute conséquence. À revoir si le jeu de
# calibration s'enrichit (actuellement seulement 4 paires positives,
# faible puissance statistique).
EMBEDDING_THRESHOLD = 0.90

# Un segment plus court que ça n'est pas envoyé aux sources externes :
# une requête réseau coûte du temps pour peu de bénéfice sur un texte
# trop court pour être vraiment distinctif.
MIN_WORDS_FOR_EXTERNAL_CHECK = 15

# Nombre maximum de segments d'un même document pour lesquels on interroge
# DuckDuckGo. Au-delà, DuckDuckGo finit par bloquer l'IP (constaté en
# conditions réelles sur un document de 8 segments éligibles x 3 fenêtres
# = 24 requêtes en quelques minutes) — un simple espacement des requêtes
# n'a pas suffi à l'éviter. Les segments au-delà de ce budget sont quand
# même vérifiés contre les sources académiques (qui tiennent la charge
# sans problème constaté à ce jour).
MAX_SEGMENTS_WITH_WEB_SEARCH = 5


def find_best_match(segment: dict, candidates: list[dict]) -> dict | None:
    """
    Compare un segment (dict avec "text" et "page") à une liste de
    candidats (sources académiques et/ou web) et renvoie la MEILLEURE
    correspondance trouvée, déjà au format attendu par le frontend —
    voir _build_match pour le détail des champs.

    Renvoie None si aucun candidat ne dépasse les seuils de détection.
    """
    segment_text = segment["text"]
    best_match = None
    best_score = 0.0

    for candidate in candidates:
        candidate_text = candidate["text"]

        # Étape 1 : copie exacte (fingerprinting). Prioritaire : si trouvée,
        # pas besoin de tester les embeddings sur ce même candidat.
        is_copy, fp_score = is_exact_copy(segment_text, candidate_text, min_shared_kgrams=MIN_SHARED_KGRAMS)
        if is_copy and fp_score > best_score:
            best_score = fp_score
            best_match = _build_match(segment, candidate, match_type="exact", score=fp_score)
            continue

        # Étape 2 : similarité sémantique (paraphrase), si pas de copie exacte trouvée.
        try:
            is_match, sem_score = is_semantic_match(segment_text, candidate_text, threshold=EMBEDDING_THRESHOLD)
        except Exception:
            # Le modèle d'embeddings peut échouer (indisponible, erreur
            # réseau au premier chargement...) : on ignore ce candidat
            # plutôt que de faire planter toute l'analyse du document.
            continue

        if is_match and sem_score > best_score:
            best_score = sem_score
            best_match = _build_match(segment, candidate, match_type="semantic", score=sem_score)

    return best_match


def _build_match(segment: dict, candidate: dict, match_type: str, score: float) -> dict:
    """Construit un dictionnaire de match au format attendu par le frontend."""
    return {
        "type": match_type,
        "score": round(score * 100, 1),  # conversion 0-1 -> 0-100, attendu par script.js
        "text": segment["text"],
        "source_url": candidate.get("url", ""),
        "source_title": candidate.get("title") or candidate.get("source", "Source inconnue"),
        # Numéro de page d'origine dans le document uploadé (None pour un
        # DOCX, qui n'a pas de vraie notion de page — voir extraction.py).
        # Permet à l'utilisateur de localiser le passage sans avoir à
        # chercher le texte dans tout le document.
        "page": segment.get("page"),
    }


def gather_candidates(segment_text: str, allow_web_search: bool = True) -> list[dict]:
    """
    Récupère tous les candidats de comparaison pour un segment donné, en
    interrogeant les sources académiques ET (si allow_web_search) le web.

    Les deux utilisent des requêtes différentes, à dessein :
    - academic_sources : requête plus longue (30 mots), le segment entier
      dans la plupart des cas. Ces API font une recherche par pertinence,
      pas par correspondance exacte de phrase — une requête plus longue
      leur donne plus de contexte pour bien classer les résultats.
    - web_search : plusieurs requêtes courtes (12 mots), réparties sur
      TOUT le segment (voir web_search.extract_signatures). DuckDuckGo est
      interrogé en recherche de phrase EXACTE (entre guillemets) : une
      requête trop longue ne matcherait jamais rien mot pour mot, donc il
      faut rester court — mais comme une citation copiée peut se trouver
      n'importe où dans le segment (pas seulement au début), plusieurs
      fenêtres réparties sont nécessaires pour ne pas la manquer.

    allow_web_search=False permet de sauter complètement DuckDuckGo pour ce
    segment — voir MAX_SEGMENTS_WITH_WEB_SEARCH dans analyze_document : au
    delà d'un budget de segments par analyse, DuckDuckGo bloque purement et
    simplement l'IP (constaté en conditions réelles, un simple espacement
    des requêtes n'a pas suffi à l'éviter sur un document entier). Les
    sources académiques, elles, continuent normalement quel que soit le
    nombre de segments.

    Une panne sur une des deux sources ne bloque pas l'autre : chaque
    fonction sous-jacente gère déjà ses propres erreurs (voir
    academic_sources.py et web_search.py).
    """
    academic_query = extract_signature(segment_text, num_words=30)

    candidates = []
    candidates.extend(search_academic_sources(academic_query))
    if allow_web_search:
        candidates.extend(search_web_and_extract(segment_text))
    return candidates


def analyze_document(paragraphs: list[dict], forced_lang: str | None = None) -> dict:
    """
    Point d'entrée principal du module.

    Prend la liste de paragraphes d'un mémoire (déjà sans bibliographie,
    tel que renvoyé par extraction.extract_document, champ "paragraphs")
    et renvoie le rapport complet :
    {
        "global_score": 0-100,
        "matches": [ {...}, {...}, ... ],
        "segment_count": nombre total de segments analysés,
    }

    Le score global est calculé comme la proportion de MOTS appartenant à
    des segments détectés (copie ou paraphrase), pas juste le nombre de
    segments détectés — un segment de 60 mots détecté pèse plus qu'un
    segment de 15 mots dans le score final, ce qui reflète mieux l'ampleur
    réelle du plagiat dans le document.
    """
    segments = segment_document(paragraphs, forced_lang=forced_lang)

    matches = []
    total_words = 0
    flagged_words = 0
    is_first_external_check = True
    web_search_budget_used = 0

    for segment in segments:
        word_count = len(segment["text"].split())
        total_words += word_count

        if word_count < MIN_WORDS_FOR_EXTERNAL_CHECK:
            continue

        if not is_first_external_check:
            # Pause entre deux SEGMENTS (pas seulement entre les fenêtres
            # d'un même segment, voir web_search.search_web_and_extract) :
            # sans ça, la dernière requête d'un segment et la première du
            # suivant se suivent sans délai, ce qui annule une bonne partie
            # de l'effet du throttling sur un document à plusieurs segments.
            time.sleep(2)
        is_first_external_check = False

        allow_web_search = web_search_budget_used < MAX_SEGMENTS_WITH_WEB_SEARCH
        if allow_web_search:
            web_search_budget_used += 1

        candidates = gather_candidates(segment["text"], allow_web_search=allow_web_search)
        match = find_best_match(segment, candidates)

        if match:
            matches.append(match)
            flagged_words += word_count

    global_score = round((flagged_words / total_words) * 100, 1) if total_words else 0.0

    return {
        "global_score": global_score,
        "matches": matches,
        "segment_count": len(segments),
    }