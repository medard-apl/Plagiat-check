r"""
Diagnostic approfondi — fait tourner le VRAI pipeline de récupération de
candidats (celui utilisé par scoring.py) sur un vrai segment du document
de test, en affichant le détail de CHAQUE étape :

1. Le segment choisi et la requête construite à partir de lui.
2. Semantic Scholar / CrossRef / arXiv : combien de candidats chacun renvoie.
3. DuckDuckGo : combien d'URLs brutes sont trouvées.
4. Pour chaque URL trouvée : est-ce que trafilatura arrive à en extraire
   du texte (et combien de caractères) ?
5. Le nombre final de candidats après web_search.search_web_and_extract.

Objectif : savoir PRÉCISÉMENT à quelle étape ça tombe à zéro, plutôt que
de le découvrir seulement au bout de la chaîne (comme "0 source trouvée"
dans le rapport final, qui ne dit pas laquelle des 4 sources est en cause,
ni si c'est la recherche elle-même ou l'extraction du contenu des pages
qui échoue).

Lancer avec :
    python3 tests/debug_pipeline.py
    python3 tests/debug_pipeline.py "C:\chemin\vers\ton\document.pdf"   (chemin personnalisé)
"""

import sys
import traceback
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from services.extraction import extract_document
from services.segmentation import segment_document
from services.academic_sources import search_semantic_scholar, search_crossref, search_arxiv
from services.web_search import extract_signature, search_web, fetch_page_text

DEFAULT_FIXTURE = BACKEND_DIR / "tests" / "fixtures" / "document_test.pdf"


def main():
    # Si un chemin est passé en argument, on l'utilise ; sinon on retombe
    # sur le fixture par défaut.
    target_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_FIXTURE

    if not target_path.exists():
        print(f"ERREUR : fichier introuvable -> {target_path}")
        print("Donne le chemin complet du PDF en argument, par exemple :")
        print(r'  python tests/debug_pipeline.py "C:\Users\LENOVO\Downloads\document_test.pdf"')
        return

    print(f"Document utilisé : {target_path}\n")
    doc = extract_document(str(target_path))
    segments = segment_document(doc["paragraphs"])

    # On cible le segment §1 (page 2, contient la citation DUDH) — c'est
    # celui qui a le plus de chances d'avoir un vrai résultat côté web.
    target = next((s for s in segments if "êtres humains" in s["text"]), segments[0])

    print(f"Segment ciblé (page {target['page']}) :")
    print(f"  {target['text'][:120]}...\n")

    query = extract_signature(target["text"], num_words=12)
    print(f"Requête construite (12 premiers mots) : {query!r}\n")

    print("=" * 70)
    print("SOURCES ACADÉMIQUES")
    print("=" * 70)

    for name, func in [
        ("Semantic Scholar", search_semantic_scholar),
        ("CrossRef", search_crossref),
        ("arXiv", search_arxiv),
    ]:
        results = func(query)
        print(f"{name} : {len(results)} candidat(s)")
        for r in results:
            print(f"   - {r['title'][:70]!r}  ({len(r['text'])} caractères de texte)")

    print("\n" + "=" * 70)
    print("RECHERCHE WEB (DuckDuckGo)")
    print("=" * 70)

    raw_results = search_web(query, max_results=5)
    print(f"{len(raw_results)} URL(s) brute(s) trouvée(s) par DuckDuckGo :")
    for r in raw_results:
        url = r.get("href") or r.get("url")
        print(f"   - {url}")

    if not raw_results:
        print("   (rien à extraire, DuckDuckGo n'a renvoyé aucun résultat)")
        return

    print("\nExtraction du contenu de chaque page (trafilatura) :")
    web_candidates = []
    for r in raw_results:
        url = r.get("href") or r.get("url")
        text = fetch_page_text(url)
        status = f"{len(text)} caractères extraits" if text else "ÉCHEC (rien d'extractible)"
        print(f"   - {url}\n     -> {status}")
        if text:
            web_candidates.append({"source": "web", "title": r.get("title", ""), "text": text, "url": url})

    # ---------------------------------------------------------------
    # ÉTAPE FINALE : appelle RÉELLEMENT is_exact_copy et is_semantic_match
    # sur les vrais candidats trouvés ci-dessus, SANS avaler les erreurs
    # (contrairement à scoring.find_best_match, qui les avale volontairement
    # en production). C'est ici qu'on doit voir si le problème vient de là.
    # ---------------------------------------------------------------
    print("\n" + "=" * 70)
    print("COMPARAISON RÉELLE (fingerprint + embeddings) SUR CES CANDIDATS")
    print("=" * 70)

    from services.fingerprint import is_exact_copy
    from services.embeddings import is_semantic_match

    for candidate in web_candidates:
        print(f"\n--- Candidat : {candidate['url']} ({len(candidate['text'])} caractères) ---")

        try:
            is_copy, fp_score = is_exact_copy(target["text"], candidate["text"])
            print(f"  Fingerprint : is_copy={is_copy}  score={fp_score:.3f}")
        except Exception:
            print("  Fingerprint : EXCEPTION —")
            traceback.print_exc()

        try:
            is_match, sem_score = is_semantic_match(target["text"], candidate["text"], threshold=0.90)
            print(f"  Embeddings  : is_match={is_match}  score={sem_score:.3f}")
        except Exception:
            print("  Embeddings  : EXCEPTION —")
            traceback.print_exc()


if __name__ == "__main__":
    main()