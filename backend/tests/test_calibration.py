"""
Script de calibration des seuils de détection (étape 10 du plan).

Fait tourner chaque paire du jeu de données étiqueté (calibration_dataset.py)
à travers la même logique que scoring.py (fingerprint d'abord, puis
embeddings), et compare le résultat à l'étiquette attendue.

Deux choses différentes sont mesurées :
1. La détection de copie exacte (fingerprint.is_exact_copy) : déjà validée
   sur les cas critiques précédemment, on vérifie juste ici qu'elle continue
   de bien fonctionner sur ce jeu de données plus large (pas de seuil à
   régler, min_shared_kgrams reste fixe).
2. La détection sémantique (embeddings.is_semantic_match) : c'est LE seuil
   à calibrer. On teste plusieurs valeurs de EMBEDDING_THRESHOLD et on
   mesure, pour chacune, la précision et le rappel sur la distinction
   "paraphrase" (positif) vs "same_topic"/"unrelated" (négatif).

Lancer avec :  python3 tests/test_calibration.py
(depuis le dossier backend/, pour que les imports fonctionnent)
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from services.fingerprint import is_exact_copy
from services.embeddings import is_semantic_match
from services.scoring import EMBEDDING_THRESHOLD as CONFIGURED_THRESHOLD
from tests.calibration_dataset import CALIBRATION_PAIRS

# Seuils à comparer. 0.85 est la valeur utilisée jusqu'ici dans scoring.py.
THRESHOLDS_TO_TEST = [0.80, 0.83, 0.85, 0.87, 0.90, 0.92, 0.95]


def classify_pair(segment: str, candidate: str, embedding_threshold: float) -> tuple[str, float]:
    """
    Reproduit la logique de décision de scoring.find_best_match pour UNE
    seule paire : fingerprint d'abord (prioritaire), puis embeddings si pas
    de copie exacte détectée.

    Renvoie (label_predit, score) où label_predit est "exact", "semantic"
    ou "none".
    """
    is_copy, fp_score = is_exact_copy(segment, candidate)
    if is_copy:
        return "exact", fp_score

    try:
        is_match, sem_score = is_semantic_match(segment, candidate, threshold=embedding_threshold)
    except Exception as error:
        print(f"  ⚠ Embeddings indisponibles ({error}) — impossible de tester la classe 'semantic'.")
        return "unknown", 0.0

    if is_match:
        return "semantic", sem_score
    return "none", sem_score


def check_exact_detection() -> None:
    """
    Vérifie la détection de copie exacte sur toutes les paires "exact" du
    jeu de données (indépendant du seuil sémantique, donc testé à part).
    """
    print("=" * 70)
    print("PARTIE 1 — Détection de copie exacte (fingerprint)")
    print("=" * 70)

    exact_pairs = [p for p in CALIBRATION_PAIRS if p["category"] == "exact"]
    all_correct = True

    for pair in exact_pairs:
        is_copy, score = is_exact_copy(pair["segment"], pair["candidate"])
        status = "OK" if is_copy else "ECHEC"
        if not is_copy:
            all_correct = False
        print(f"  [{status}] {pair['id']} (score={score:.2f})")

    # Contrôle négatif : aucune des paires "same_topic"/"unrelated"/"paraphrase"
    # ne doit être détectée comme copie exacte (pas de citation verbatim dedans).
    non_exact_pairs = [p for p in CALIBRATION_PAIRS if p["category"] != "exact"]
    false_positives = []
    for pair in non_exact_pairs:
        is_copy, score = is_exact_copy(pair["segment"], pair["candidate"])
        if is_copy:
            false_positives.append(pair["id"])
            all_correct = False

    print(f"\n  Faux positifs (détectés à tort comme copie exacte) : {len(false_positives)}")
    for fp_id in false_positives:
        print(f"    - {fp_id}")

    print(f"\n  Résultat global : {'TOUT EST CORRECT' if all_correct else 'DES ECARTS SUBSISTENT'}")


def sweep_embedding_threshold() -> None:
    """
    Teste plusieurs valeurs de seuil sémantique et affiche précision/rappel
    pour chacune, sur la distinction paraphrase (positif) vs
    same_topic + unrelated (négatif).

    Les paires "exact" sont exclues de cette mesure : leur classification
    dépend du fingerprinting, pas du seuil sémantique testé ici.
    """
    print("\n" + "=" * 70)
    print("PARTIE 2 — Calibration du seuil sémantique (embeddings)")
    print("=" * 70)

    relevant_pairs = [p for p in CALIBRATION_PAIRS if p["category"] != "exact"]
    positive_pairs = [p for p in relevant_pairs if p["expected"] == "semantic"]
    negative_pairs = [p for p in relevant_pairs if p["expected"] == "none"]

    print(f"\n{len(positive_pairs)} paire(s) positive(s) (vraies paraphrases attendues)")
    print(f"{len(negative_pairs)} paire(s) négative(s) (same_topic + unrelated, aucun plagiat attendu)\n")

    print(f"{'Seuil':<8}{'Précision':<12}{'Rappel':<10}{'F1':<8}{'Faux positifs':<15}{'Faux négatifs'}")
    print("-" * 70)

    results = []
    for threshold in THRESHOLDS_TO_TEST:
        true_positives = 0
        false_positives = 0
        false_negatives = 0
        fp_ids = []
        fn_ids = []

        for pair in positive_pairs:
            label, _ = classify_pair(pair["segment"], pair["candidate"], threshold)
            if label == "unknown":
                print("Embeddings indisponibles, arrêt de la calibration.")
                return
            if label == "semantic":
                true_positives += 1
            else:
                false_negatives += 1
                fn_ids.append(pair["id"])

        for pair in negative_pairs:
            label, _ = classify_pair(pair["segment"], pair["candidate"], threshold)
            if label == "semantic":
                false_positives += 1
                fp_ids.append(pair["id"])

        precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) else 1.0
        recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) else 1.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

        results.append({
            "threshold": threshold, "precision": precision, "recall": recall,
            "f1": f1, "fp_ids": fp_ids, "fn_ids": fn_ids,
        })

        print(f"{threshold:<8}{precision:<12.2f}{recall:<10.2f}{f1:<8.2f}{len(fp_ids):<15}{len(fn_ids)}")

    best = max(results, key=lambda r: r["f1"])
    zero_fp = [r for r in results if len(r["fp_ids"]) == 0]
    safest = min(zero_fp, key=lambda r: r["threshold"]) if zero_fp else None

    print("\n" + "-" * 70)
    print(f"Meilleur F1        : seuil={best['threshold']}  (précision={best['precision']:.2f}, rappel={best['recall']:.2f})")
    if safest:
        print(f"Zéro faux positif  : seuil={safest['threshold']}  (le plus bas sans aucun faux positif, rappel={safest['recall']:.2f})")
    else:
        print("Zéro faux positif  : aucun seuil testé n'élimine complètement les faux positifs.")

    print(f"\nDétail des erreurs au seuil actuellement configuré dans scoring.py ({CONFIGURED_THRESHOLD}) :")
    current = next((r for r in results if r["threshold"] == CONFIGURED_THRESHOLD), None)
    if current is None:
        print(f"  (le seuil {CONFIGURED_THRESHOLD} n'est pas dans THRESHOLDS_TO_TEST, ajoute-le à la liste pour le voir ici)")
    else:
        if current["fp_ids"]:
            print("  Faux positifs (classés 'semantic' à tort) :")
            for pid in current["fp_ids"]:
                print(f"    - {pid}")
        if current["fn_ids"]:
            print("  Faux négatifs (paraphrase manquée) :")
            for pid in current["fn_ids"]:
                print(f"    - {pid}")
        if not current["fp_ids"] and not current["fn_ids"]:
            print("  Aucune erreur à ce seuil sur ce jeu de données.")


if __name__ == "__main__":
    check_exact_detection()
    sweep_embedding_threshold()