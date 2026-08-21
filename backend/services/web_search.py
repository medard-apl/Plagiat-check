"""
Module de vérification web ponctuelle (DuckDuckGo + scraping).

Rôle : pour un segment de texte, chercher sur le web ouvert (via DuckDuckGo,
gratuit et sans quota strict — contrairement à Google Custom Search) des
pages qui pourraient contenir un passage identique ou très proche, puis
récupérer le texte de ces pages pour la comparaison (fingerprint + embeddings).

Contrairement à academic_sources.py (bases académiques), ici on cherche sur
le web ouvert en général : blogs, sites de cours, forums, etc. — utile pour
couvrir les cas hors du champ académique, ou le simple copier-coller depuis
un site quelconque.
"""

import time

import trafilatura
from ddgs import DDGS
from ddgs.exceptions import RatelimitException

MAX_RETRIES = 2
RETRY_BACKOFF_SECONDS = 3


def extract_signature(segment_text: str, num_words: int = 10) -> str:
    """
    Extrait une "phrase signature" d'un segment : une séquence de mots
    consécutifs assez longue pour être distinctive, mais assez courte pour
    fonctionner comme requête de recherche exacte.

    On prend simplement les num_words premiers mots du segment. Voir
    extract_signatures (au pluriel) ci-dessous pour la version qui couvre
    tout le segment plutôt que juste son début.
    """
    words = segment_text.split()
    return " ".join(words[:num_words])


def extract_signatures(segment_text: str, num_words: int = 12, num_windows: int = 3) -> list[str]:
    """
    Extrait plusieurs "phrases signatures" réparties sur TOUT le segment
    (début, milieu, fin...), plutôt qu'une seule au début.

    Pourquoi : une citation copiée n'est pas forcément en tête de segment —
    un étudiant qui insère une phrase empruntée au MILIEU d'un paragraphe
    par ailleurs original est un cas courant (et c'est justement le cas qui
    a révélé ce problème : une citation à la position 26 sur 61 mots n'était
    jamais incluse dans la requête de recherche, qui ne portait que sur les
    12 premiers mots). En interrogeant plusieurs fenêtres réparties sur le
    segment, on augmente fortement les chances de tomber sur la citation
    réelle, quelle que soit sa position.

    Les fenêtres sont espacées uniformément et dédupliquées (un segment
    plus court que num_windows * num_words aura naturellement des fenêtres
    qui se chevauchent, voire un seul résultat si le segment est très court).
    """
    words = segment_text.split()
    total = len(words)

    if total <= num_words:
        return [" ".join(words)]

    # Position de départ de chaque fenêtre, répartie uniformément sur le
    # segment (la dernière fenêtre est calée pour ne pas dépasser la fin).
    max_start = max(total - num_words, 0)
    if num_windows <= 1:
        starts = [0]
    else:
        step = max_start / (num_windows - 1)
        starts = [round(i * step) for i in range(num_windows)]

    signatures = []
    seen = set()
    for start in starts:
        window = " ".join(words[start:start + num_words])
        if window and window not in seen:
            signatures.append(window)
            seen.add(window)

    return signatures


def search_web(query: str, max_results: int = 5) -> list[dict]:
    """
    Recherche une phrase sur DuckDuckGo et renvoie les résultats bruts
    (titre, url, extrait).

    La requête est envoyée ENTRE GUILLEMETS pour forcer une recherche de
    correspondance exacte de la phrase plutôt qu'une recherche par
    mots-clés dispersés — c'est ce qui donne les meilleurs résultats pour
    repérer du copier-coller.

    DuckDuckGo (via ddgs, une librairie non officielle qui scrape la page
    de résultats) est connu pour bloquer temporairement en cas de volume
    de requêtes inhabituel — on retente donc une fois après une courte
    pause avant d'abandonner.
    """
    for attempt in range(MAX_RETRIES):
        try:
            with DDGS() as ddgs:
                results = ddgs.text(f'"{query}"', max_results=max_results)
            return results or []
        except RatelimitException:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
                continue
            return []
        except Exception:
            # Autre échec (page HTML de DuckDuckGo qui change, etc.) : pas
            # la peine de bloquer le pipeline pour ça.
            return []

    return []


def fetch_page_text(url: str) -> str | None:
    """
    Télécharge une page web et en extrait le texte "utile" (sans menus,
    publicités, scripts...) grâce à trafilatura, spécialisé dans
    l'extraction de contenu principal depuis du HTML brut.

    Renvoie None si la page n'a pas pu être récupérée ou si trafilatura
    n'a rien pu en extraire (page vide, contenu généré en JavaScript, etc.).
    """
    try:
        downloaded = trafilatura.fetch_url(url)
    except Exception:
        return None

    if downloaded is None:
        return None

    return trafilatura.extract(downloaded)


def search_web_and_extract(segment_text: str, max_results_per_window: int = 2) -> list[dict]:
    """
    Point d'entrée principal du module.

    Enchaîne : extraction de plusieurs phrases signatures réparties sur le
    segment (extract_signatures) -> recherche DuckDuckGo pour CHACUNE
    -> récupération et extraction du texte de chaque page trouvée (les
    URLs en double entre les différentes fenêtres ne sont récupérées
    qu'une seule fois).

    Renvoie une liste de candidats au même format que academic_sources.py,
    pour être traités de façon identique par la suite du pipeline :
    {"source": "web", "title": ..., "text": ..., "url": ...}

    max_results_per_window est volontairement plus bas que l'ancien
    max_results à 5 : avec 3 fenêtres, on multiplie déjà le nombre de
    requêtes DuckDuckGo par 3 — réduire les résultats par fenêtre limite
    la casse côté rate-limit tout en couvrant mieux tout le segment.
    """
    signatures = extract_signatures(segment_text)

    seen_urls: set[str] = set()
    raw_results = []
    for i, query in enumerate(signatures):
        if i > 0:
            # Petite pause entre deux fenêtres du MÊME segment, pour ne pas
            # envoyer plusieurs requêtes DuckDuckGo coup sur coup — c'est ce
            # genre de rafale qui déclenche le plus facilement un blocage
            # temporaire (constaté en conditions réelles). Ce délai ralentit
            # l'analyse d'un document entier (potentiellement plusieurs
            # dizaines de secondes de plus sur un long mémoire), mais réduit
            # le risque de tout bloquer d'un coup — compromis assumé face
            # aux limites d'un service gratuit non officiel.
            time.sleep(3)

        for result in search_web(query, max_results=max_results_per_window):
            url = result.get("href") or result.get("url")
            if url and url not in seen_urls:
                seen_urls.add(url)
                raw_results.append(result)

    candidates = []
    for result in raw_results:
        url = result.get("href") or result.get("url")
        page_text = fetch_page_text(url)
        if not page_text:
            continue

        candidates.append({
            "source": "web",
            "title": result.get("title", ""),
            "text": page_text,
            "url": url,
        })

    return candidates