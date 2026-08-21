"""
Script de diagnostic — teste chaque source externe UNE PAR UNE, avec les
erreurs affichées en clair (contrairement à academic_sources.py et
web_search.py, qui avalent volontairement toute exception en production
pour ne jamais faire planter une analyse à cause d'une seule source en panne).

À lancer quand le pipeline complet renvoie "0 source trouvée" partout, pour
savoir laquelle des 4 sources est en cause et pourquoi.

Lancer avec :  python3 tests/debug_sources.py
"""

import sys
import traceback
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import requests

QUERY = "dominant sequence transduction models recurrent convolutional neural networks"


def test_semantic_scholar():
    print("\n--- Semantic Scholar ---")
    try:
        response = requests.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={"query": QUERY, "limit": 3, "fields": "title,abstract,url"},
            timeout=10,
        )
        print("Status code :", response.status_code)
        print("Corps (500 premiers caractères) :", response.text[:500])
    except Exception:
        print("EXCEPTION :")
        traceback.print_exc()


def test_crossref():
    print("\n--- CrossRef ---")
    try:
        response = requests.get(
            "https://api.crossref.org/works",
            params={"query": QUERY, "rows": 3},
            timeout=10,
        )
        print("Status code :", response.status_code)
        print("Corps (500 premiers caractères) :", response.text[:500])
    except Exception:
        print("EXCEPTION :")
        traceback.print_exc()


def test_arxiv():
    print("\n--- arXiv ---")
    try:
        response = requests.get(
            "http://export.arxiv.org/api/query",
            params={"search_query": f"all:{QUERY}", "max_results": 3},
            timeout=10,
        )
        print("Status code :", response.status_code)
        print("Corps (500 premiers caractères) :", response.text[:500])
    except Exception:
        print("EXCEPTION :")
        traceback.print_exc()


def test_duckduckgo():
    print("\n--- DuckDuckGo (ddgs) ---")
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(f'"{QUERY[:60]}"', max_results=3))
        print(f"{len(results)} résultat(s) :")
        for r in results:
            print(" -", r)
    except Exception:
        print("EXCEPTION :")
        traceback.print_exc()


if __name__ == "__main__":
    print(f"Requête de test : {QUERY!r}\n")
    test_semantic_scholar()
    test_crossref()
    test_arxiv()
    test_duckduckgo()