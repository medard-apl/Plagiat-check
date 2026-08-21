"""
Module de recherche dans les sources académiques gratuites.

Rôle : pour un segment de texte jugé "à risque" (technique, dense, avec du
vocabulaire spécialisé), interroger trois bases académiques gratuites et
sans clé API pour trouver des publications dont le titre/résumé pourrait
correspondre : Semantic Scholar, CrossRef, arXiv.

Important : on n'envoie JAMAIS le mémoire entier à ces API. On envoie
seulement un extrait du segment comme requête de recherche, et on récupère
des CANDIDATS (titre + résumé) sur lesquels la vraie comparaison
(fingerprint + embeddings, dans scoring.py) sera faite ensuite, en local.
"""

import re
import time
import xml.etree.ElementTree as ET

import requests

# Délai raisonnable pour ne pas bloquer tout le pipeline si une API est lente/indisponible.
REQUEST_TIMEOUT = 15

# Nombre de tentatives avant d'abandonner une source (1 = pas de retry).
MAX_RETRIES = 2
# Délai de base entre deux tentatives, en secondes (doublé à chaque nouvel essai).
RETRY_BACKOFF_SECONDS = 2


def _get_with_retry(url: str, params: dict) -> requests.Response | None:
    """
    Fait un GET avec un nombre limité de tentatives en cas de problème
    transitoire (429 "trop de requêtes", timeout réseau).

    Sur un 429, on respecte l'en-tête "Retry-After" renvoyé par le serveur
    quand il est présent (c'est littéralement fait pour ça), sinon on
    utilise un délai croissant (2s, puis 4s...). Sur un timeout, même
    logique de délai croissant.

    Renvoie None si toutes les tentatives ont échoué — c'est ensuite aux
    fonctions appelantes (search_semantic_scholar, etc.) de traiter ça
    comme "pas de résultat" plutôt que de faire planter le pipeline.
    """
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        except requests.RequestException:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
                continue
            return None

        if response.status_code == 429:
            if attempt < MAX_RETRIES - 1:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else RETRY_BACKOFF_SECONDS * (attempt + 1)
                time.sleep(delay)
                continue
            return None

        return response

    return None


def search_semantic_scholar(query: str, limit: int = 3) -> list[dict]:
    """
    Interroge l'API Semantic Scholar (gratuite, sans clé nécessaire pour
    un usage modéré — environ 100 requêtes/5 min sans clé).

    On récupère uniquement titre + résumé (abstract) + url : c'est tout
    ce dont on a besoin pour la comparaison sémantique qui suit.
    """
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {"query": query, "limit": limit, "fields": "title,abstract,url"}

    response = _get_with_retry(url, params)
    if response is None or response.status_code != 200:
        return []

    try:
        data = response.json()
    except ValueError:
        return []

    return _parse_semantic_scholar_response(data)


def _parse_semantic_scholar_response(data: dict) -> list[dict]:
    """
    Transforme la réponse JSON de Semantic Scholar en une liste de
    candidats au format commun utilisé partout dans le pipeline :
    {"source": ..., "title": ..., "text": ..., "url": ...}

    Un papier sans résumé (ça arrive souvent, l'abstract n'est pas
    toujours disponible) est ignoré : sans texte, il n'y a rien à comparer.
    """
    candidates = []
    for paper in data.get("data", []):
        abstract = paper.get("abstract")
        if not abstract:
            continue
        candidates.append({
            "source": "semantic_scholar",
            "title": paper.get("title", ""),
            "text": abstract,
            "url": paper.get("url", ""),
        })
    return candidates


def search_crossref(query: str, rows: int = 3) -> list[dict]:
    """
    Interroge l'API CrossRef (gratuite, sans clé, pas de limite stricte
    documentée pour un usage raisonnable).

    CrossRef donne surtout des métadonnées (titre, DOI, auteurs) ; le
    résumé n'est présent que pour une partie des publications, et souvent
    balisé en JATS-XML (ex: "<jats:p>...</jats:p>") qu'il faut nettoyer.
    """
    url = "https://api.crossref.org/works"
    params = {"query": query, "rows": rows}

    response = _get_with_retry(url, params)
    if response is None or response.status_code != 200:
        return []

    try:
        data = response.json()
    except ValueError:
        return []

    return _parse_crossref_response(data)


def _strip_jats_tags(text: str) -> str:
    """Retire les balises JATS-XML (<jats:p>, </jats:p>, etc.) d'un résumé CrossRef."""
    return re.sub(r"<[^>]+>", "", text).strip()


def _parse_crossref_response(data: dict) -> list[dict]:
    """
    Transforme la réponse JSON de CrossRef en candidats au format commun.

    Le titre est une LISTE dans le JSON de CrossRef (parfois plusieurs
    variantes de titre pour une même publication) : on prend le premier élément.
    """
    candidates = []
    items = data.get("message", {}).get("items", [])

    for item in items:
        abstract = item.get("abstract")
        if not abstract:
            continue

        titles = item.get("title", [])
        title = titles[0] if titles else ""

        candidates.append({
            "source": "crossref",
            "title": title,
            "text": _strip_jats_tags(abstract),
            "url": item.get("URL", ""),
        })

    return candidates


ARXIV_NAMESPACE = {"atom": "http://www.w3.org/2005/Atom"}


def search_arxiv(query: str, max_results: int = 3) -> list[dict]:
    """
    Interroge l'API arXiv (gratuite, sans clé), pertinente pour les
    filières scientifiques/techniques.

    Particularité : contrairement aux deux autres, arXiv répond en XML
    (format Atom), pas en JSON — d'où le parsing différent.
    """
    # HTTPS, pas HTTP : le simple HTTP est parfois ralenti ou bloqué
    # silencieusement par certains réseaux/box internet, ce qui produit
    # exactement le genre de timeout observé en test.
    url = "https://export.arxiv.org/api/query"
    params = {"search_query": f"all:{query}", "max_results": max_results}

    response = _get_with_retry(url, params)
    if response is None or response.status_code != 200:
        return []

    return _parse_arxiv_response(response.text)


def _parse_arxiv_response(xml_text: str) -> list[dict]:
    """
    Transforme la réponse XML (Atom) d'arXiv en candidats au format commun.

    arXiv fournit quasi systématiquement un résumé ("summary"), contrairement
    à Semantic Scholar/CrossRef où il est parfois absent — c'est souvent la
    source la plus fiable des trois, quand le sujet du mémoire correspond
    à son domaine (informatique, physique, maths, IA...).
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    candidates = []
    for entry in root.findall("atom:entry", ARXIV_NAMESPACE):
        title_el = entry.find("atom:title", ARXIV_NAMESPACE)
        summary_el = entry.find("atom:summary", ARXIV_NAMESPACE)
        id_el = entry.find("atom:id", ARXIV_NAMESPACE)

        if summary_el is None or not summary_el.text:
            continue

        candidates.append({
            "source": "arxiv",
            "title": (title_el.text or "").strip() if title_el is not None else "",
            "text": summary_el.text.strip(),
            "url": (id_el.text or "").strip() if id_el is not None else "",
        })

    return candidates


def search_academic_sources(query: str, max_results_per_source: int = 3) -> list[dict]:
    """
    Point d'entrée principal : interroge les trois sources et fusionne
    les résultats dans une seule liste de candidats.

    Chaque source est appelée indépendamment. Une panne sur l'une d'elles
    n'empêche pas les autres de fonctionner : chaque fonction renvoie []
    en cas d'erreur plutôt que de lever une exception qui ferait tomber
    tout le pipeline.
    """
    candidates = []
    candidates.extend(search_semantic_scholar(query, limit=max_results_per_source))
    candidates.extend(search_crossref(query, rows=max_results_per_source))
    candidates.extend(search_arxiv(query, max_results=max_results_per_source))
    return candidates