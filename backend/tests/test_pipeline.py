"""
Test bout-en-bout du pipeline : extraction -> segmentation -> fingerprinting -> embeddings.

Scénario : on a un document B qui reprend le contenu d'un document A de 3 façons
différentes (copie exacte / paraphrase / sans rapport), et on vérifie que le
pipeline classe chaque cas correctement.

Ce script ne teste PAS encore les sources externes (Semantic Scholar, DuckDuckGo...) :
uniquement la comparaison "locale" entre deux documents, ce qui correspond à ce
qu'on a codé jusqu'ici (étapes 2 à 5).

Lancer avec :  python3 tests/test_pipeline.py
(depuis le dossier backend/, pour que les imports fonctionnent)
"""

import sys
from pathlib import Path

# On ajoute le dossier backend/ au chemin de recherche des modules,
# pour pouvoir importer "services" quel que soit l'endroit d'où le script est lancé.
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from services.extraction import extract_document
from services.segmentation import segment_document
from services.fingerprint import is_exact_copy
from services.embeddings import is_semantic_match
from services.scoring import EMBEDDING_THRESHOLD

FIXTURES_DIR = Path(__file__).parent / "fixtures"



def ensure_fixtures_exist() -> None:
    """Génère les documents de test s'ils n'existent pas encore."""
    doc_a = FIXTURES_DIR / "doc_a.docx"
    doc_b = FIXTURES_DIR / "doc_b.docx"
    if not doc_a.exists() or not doc_b.exists():
        from fixtures.generate_fixtures import build_doc_a, build_doc_b
        build_doc_a()
        build_doc_b()


def compare_segment_to_source(segment_text: str, source_segments: list[dict]) -> dict:
    """
    Compare un segment de B à TOUS les segments de A, et renvoie le meilleur
    résultat trouvé (celui qui a le score le plus élevé, fingerprint ou embedding).

    C'est une version simplifiée de ce que fera le vrai pipeline plus tard
    (qui comparera aussi contre les sources académiques et le web) : ici on
    se concentre uniquement sur la logique de classification exact/paraphrase/aucun.
    """
    best_result = {"type": "aucun", "score": 0.0, "source_segment": None}

    for source_segment in source_segments:
        source_text = source_segment["text"]

        # Étape 1 : vérification rapide de copie exacte (fingerprinting)
        is_copy, fp_score = is_exact_copy(segment_text, source_text)
        if is_copy and fp_score > best_result["score"]:
            best_result = {"type": "copie exacte", "score": fp_score, "source_segment": source_text}
            continue  # pas besoin de tester les embeddings si on a déjà une copie exacte

        # Étape 2 : si pas de copie exacte, on tente la détection sémantique
        try:
            is_match, sem_score = is_semantic_match(segment_text, source_text, threshold=EMBEDDING_THRESHOLD)
        except Exception as error:
            # Le modèle d'embeddings peut ne pas être disponible (pas de connexion
            # internet au premier lancement, par exemple). On ne fait pas planter
            # tout le test pour autant : on signale juste que cette partie n'a
            # pas pu être vérifiée.
            best_result.setdefault("embedding_error", str(error))
            continue

        if is_match and sem_score > best_result["score"]:
            best_result = {"type": "paraphrase suspecte", "score": sem_score, "source_segment": source_text}

    return best_result


def run_test() -> None:
    ensure_fixtures_exist()

    print("=" * 70)
    print("ÉTAPE 1 — Extraction des deux documents")
    print("=" * 70)
    doc_a = extract_document(str(FIXTURES_DIR / "doc_a.docx"))
    doc_b = extract_document(str(FIXTURES_DIR / "doc_b.docx"))
    print(f"Doc A - corps : {len(doc_a['body'])} caractères, bibliographie isolée : {bool(doc_a['bibliography'])}")
    print(f"Doc B - corps : {len(doc_b['body'])} caractères, bibliographie isolée : {bool(doc_b['bibliography'])}")

    print("\n" + "=" * 70)
    print("ÉTAPE 2 — Segmentation des deux documents")
    print("=" * 70)
    segments_a = segment_document(doc_a["paragraphs"])
    segments_b = segment_document(doc_b["paragraphs"])
    print(f"Doc A : {len(segments_a)} segment(s)")
    print(f"Doc B : {len(segments_b)} segment(s)")

    print("\n" + "=" * 70)
    print("ÉTAPE 3 — Comparaison de chaque segment de B contre tous les segments de A")
    print("=" * 70)

    # Ce qu'on s'attend à voir, dans l'ordre des paragraphes de doc_b.docx :
    expected = ["copie exacte", "paraphrase suspecte", "aucun"]

    all_passed = True
    for i, segment_b in enumerate(segments_b):
        result = compare_segment_to_source(segment_b["text"], segments_a)
        expected_type = expected[i] if i < len(expected) else "?"
        status = "OK" if result["type"] == expected_type else "A VERIFIER"
        if status != "OK":
            all_passed = False

        print(f"\nSegment B[{i}] (attendu : {expected_type})")
        print(f"  Texte      : {segment_b['text'][:90]}...")
        print(f"  Détecté    : {result['type']} (score={result['score']:.3f})  [{status}]")
        if result.get("source_segment"):
            print(f"  Source (A) : {result['source_segment'][:90]}...")
        if result.get("embedding_error"):
            print(f"  ⚠ Détection sémantique indisponible : {result['embedding_error']}")
            print("    -> vérifie ta connexion internet (premier téléchargement du modèle e5)")

    print("\n" + "=" * 70)
    if all_passed:
        print("RÉSULTAT : tous les segments ont été classés comme attendu.")
    else:
        print("RÉSULTAT : au moins un segment n'a pas le classement attendu (voir 'A VERIFIER' ci-dessus).")
        print("Si c'est la détection sémantique qui a échoué faute de connexion, ce n'est pas un vrai échec.")
    print("=" * 70)


if __name__ == "__main__":
    run_test()