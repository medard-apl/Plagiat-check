"""
Module de détection sémantique par embeddings (paraphrase, multilingue).

Rôle : détecter les similarités de SENS entre deux segments de texte,
même s'ils ne partagent presque aucun mot en commun (reformulation,
changement de structure de phrase, traduction) — ce que le fingerprinting
(fingerprint.py) ne peut pas voir.

Modèle utilisé : multilingual-e5-base (intfloat/multilingual-e5-base).
Choisi car :
- gratuit, tourne en local (aucun appel API, aucun coût par requête)
- couvre une centaine de langues dans le même espace vectoriel, ce qui
  permet de comparer un segment en français à une source en anglais
  sans traduction préalable
"""

import numpy as np
from sentence_transformers import SentenceTransformer


_MODEL_NAME = "intfloat/multilingual-e5-base"
_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    """
    Charge le modèle une seule fois et le garde en mémoire (variable globale).

    Charger un modèle d'embedding prend plusieurs secondes : on ne veut
    surtout pas le recharger à chaque segment ou à chaque appel API.
    Le premier chargement télécharge aussi le modèle (~1 Go) depuis
    Hugging Face et le met en cache local — les appels suivants sont rapides.
    """
    global _model
    if _model is None:
        _model = SentenceTransformer(_MODEL_NAME)
    return _model


def _prefix_for_e5(texts: list[str]) -> list[str]:
    """
    Les modèles de la famille E5 attendent un préfixe devant chaque texte
    ("query: " ou "passage: ") : c'est une particularité de leur
    entraînement, pas un détail cosmétique — sans préfixe, les scores de
    similarité obtenus sont nettement moins bons.

    Pour une comparaison symétrique (on compare deux segments de mémoire
    entre eux, pas une requête contre un document), la documentation du
    modèle recommande "query: " des deux côtés.
    """
    return [f"query: {t}" for t in texts]


def embed_texts(texts: list[str]) -> np.ndarray:
    """
    Calcule les embeddings d'une liste de textes.

    normalize_embeddings=True fait en sorte que chaque vecteur ait une
    norme de 1 : ça permet de calculer la similarité cosinus avec un
    simple produit scalaire (plus rapide qu'une vraie formule cosinus).
    """
    model = get_model()
    prefixed = _prefix_for_e5(texts)
    embeddings = model.encode(prefixed, normalize_embeddings=True, show_progress_bar=False)
    return embeddings


def cosine_similarity(embedding_a: np.ndarray, embedding_b: np.ndarray) -> float:
    """
    Similarité cosinus entre deux embeddings déjà normalisés (norme 1).
    Dans ce cas, la similarité cosinus se réduit à un simple produit scalaire.
    """
    return float(np.dot(embedding_a, embedding_b))


def find_best_match(segment_text: str, candidate_texts: list[str]) -> tuple[int, float]:
    """
    Compare un segment à une liste de textes candidats (ex : résumés
    Semantic Scholar, paragraphes trouvés via DuckDuckGo) et renvoie
    l'index du meilleur match ainsi que son score de similarité.

    Renvoie (-1, 0.0) si la liste de candidats est vide.
    """
    if not candidate_texts:
        return -1, 0.0

    all_texts = [segment_text] + candidate_texts
    embeddings = embed_texts(all_texts)

    segment_embedding = embeddings[0]
    candidate_embeddings = embeddings[1:]

    scores = [cosine_similarity(segment_embedding, c) for c in candidate_embeddings]
    best_index = int(np.argmax(scores))
    return best_index, scores[best_index]


def is_semantic_match(segment_text: str, candidate_text: str, threshold: float = 0.85) -> tuple[bool, float]:
    """
    Compare deux textes et détermine s'ils sont sémantiquement proches
    (paraphrase suspecte), selon un seuil de similarité cosinus.
    """
    embeddings = embed_texts([segment_text, candidate_text])
    score = cosine_similarity(embeddings[0], embeddings[1])
    return score >= threshold, score