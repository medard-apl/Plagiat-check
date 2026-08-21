"""
Module de détection de copie exacte par empreintes (algorithme Winnowing).

Rôle : détecter rapidement si un segment de texte est une copie exacte
(ou quasi exacte) d'un autre texte, sans faire de comparaison sémantique
coûteuse. C'est la première passe du pipeline : rapide, fiable pour le
copier-coller, mais aveugle à la reformulation (c'est embeddings.py qui
s'en charge ensuite).

Principe du Winnowing (Schleimer, Wilkerson, Aiken, 2003) :
1. On découpe le texte en k-grammes (séquences de k mots consécutifs).
2. On hash chaque k-gramme.
3. Plutôt que de garder TOUS les hashs (lourd et redondant), on ne garde
   que le hash minimum dans chaque fenêtre glissante de w hashs
   consécutifs. Ça réduit fortement le nombre d'empreintes tout en
   garantissant mathématiquement qu'une correspondance d'au moins
   w + k - 1 mots consécutifs sera détectée.
4. Comparer deux textes revient alors à comparer deux petits ensembles
   de hashs (indice de Jaccard), au lieu de comparer tout le texte mot à mot.
"""

import hashlib


def _hash_kgram(kgram: str) -> int:
    """
    Hash un k-gramme en un entier.

    MD5 tronqué à 8 octets (64 bits) : pas besoin de cryptographie forte
    ici, juste d'un hash rapide avec très peu de collisions pour des
    courtes séquences de mots.
    """
    digest = hashlib.md5(kgram.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big")


def _normalize(text: str) -> list[str]:
    """
    Normalise le texte avant hashing : minuscules, ponctuation retirée.

    Deux textes "identiques au sens du plagiat" mais avec une casse ou
    une ponctuation différente doivent quand même matcher, donc on
    normalise avant de comparer.
    """
    text = text.lower()
    cleaned = "".join(c if c.isalnum() or c.isspace() else " " for c in text)
    return cleaned.split()


def generate_kgrams(text: str, k: int = 5) -> list[str]:
    """
    Découpe le texte (normalisé) en k-grammes de k mots consécutifs.

    Exemple avec k=3 sur "le chat mange la souris" :
    -> ["le chat mange", "chat mange la", "mange la souris"]
    """
    words = _normalize(text)
    if len(words) < k:
        return [" ".join(words)] if words else []
    return [" ".join(words[i:i + k]) for i in range(len(words) - k + 1)]


def winnow(kgrams: list[str], window_size: int = 4) -> set[int]:
    """
    Applique l'algorithme Winnowing sur une liste de k-grammes.

    Pour chaque fenêtre glissante de `window_size` hashs consécutifs, on
    garde uniquement le hash minimum (en cas d'égalité, on garde le plus
    à droite — convention standard de l'algorithme original).

    Renvoie l'ensemble des hashs sélectionnés : c'est l'empreinte du texte.
    """
    if not kgrams:
        return set()

    hashes = [_hash_kgram(kg) for kg in kgrams]

    if len(hashes) <= window_size:
        return {min(hashes)}

    fingerprints = set()
    for i in range(len(hashes) - window_size + 1):
        window = hashes[i:i + window_size]
        # min avec priorité au hash le plus à droite en cas d'égalité (convention Winnowing)
        min_index = len(window) - 1 - window[::-1].index(min(window))
        fingerprints.add(window[min_index])

    return fingerprints


def get_fingerprint(text: str, k: int = 5, window_size: int = 4) -> set[int]:
    """
    Point d'entrée principal : calcule l'empreinte Winnowing d'un texte.

    Avec k=5 et window_size=4, une correspondance d'au moins
    5 + 4 - 1 = 8 mots consécutifs entre deux textes est garantie d'être
    détectée par au moins un hash commun.
    """
    kgrams = generate_kgrams(text, k=k)
    return winnow(kgrams, window_size=window_size)


def count_shared_kgrams(text_a: str, text_b: str, k: int = 8) -> int:
    """
    Compte le nombre de k-grammes (séquences de k mots consécutifs)
    identiques entre deux textes, SANS passer par le Winnowing.

    Pourquoi pas Winnowing ici ? Winnowing est fait pour réduire le
    volume d'empreintes à STOCKER quand on indexe un grand nombre de
    documents (utile pour comparer un mémoire à toute une base interne,
    par exemple). Mais pour comparer un segment à une poignée de
    candidats récupérés à la volée (API académiques, pages web), il n'y
    a rien à indexer : autant garder TOUS les k-grammes, ce qui donne un
    signal beaucoup plus précis pour une citation embarquée dans un
    texte par ailleurs original (voir is_exact_copy).
    """
    kgrams_a = set(_hash_kgram(kg) for kg in generate_kgrams(text_a, k=k))
    kgrams_b = set(_hash_kgram(kg) for kg in generate_kgrams(text_b, k=k))
    return len(kgrams_a & kgrams_b)


def jaccard_similarity(fingerprint_a: set[int], fingerprint_b: set[int]) -> float:
    """
    Similarité de Jaccard entre deux empreintes : intersection / union.
    Renvoie une valeur entre 0 (aucun recouvrement) et 1 (identiques).

    Utile pour comparer deux documents de longueur comparable dans leur
    ensemble (ex : comparaison contre une base interne de mémoires
    similaires). Pas adapté pour détecter une citation embarquée dans un
    texte par ailleurs original — voir is_exact_copy et
    count_shared_kgrams pour ce cas.
    """
    if not fingerprint_a or not fingerprint_b:
        return 0.0

    intersection = len(fingerprint_a & fingerprint_b)
    union = len(fingerprint_a | fingerprint_b)
    return intersection / union


def is_exact_copy(
    text_a: str, text_b: str, min_shared_kgrams: int = 3, k: int = 8
) -> tuple[bool, float]:
    """
    Détecte si text_a contient une citation quasi exacte de text_b (ou
    inversement), qu'elle représente ou non une grande partie du texte.

    Principe : on compte le nombre de séquences de k=8 mots consécutifs
    identiques entre les deux textes (count_shared_kgrams). On déclenche
    la détection dès que ce nombre atteint min_shared_kgrams=3, ce qui
    correspond à une séquence verbatim d'au moins k + min_shared_kgrams - 1
    = 10 mots consécutifs — largement suffisant pour exclure une
    coïncidence de langage courant, tout en restant sensible à une
    citation de quelques phrases embarquée dans un paragraphe par
    ailleurs original (contrairement à une mesure proportionnelle comme
    Jaccard ou le containment, qui diluent ce signal quand le reste du
    segment ou du candidat est volumineux).

    Renvoie (est_une_copie, score) où score est le nombre de k-grammes
    partagés normalisé sur 0-1 (utile pour classer plusieurs candidats
    entre eux ; 1.0 dès que min_shared_kgrams est atteint ou dépassé).
    """
    shared = count_shared_kgrams(text_a, text_b, k=k)
    is_copy = shared >= min_shared_kgrams
    score = min(shared / min_shared_kgrams, 1.0)
    return is_copy, score