"""
Module de segmentation du texte.

Rôle : découper le texte nettoyé du mémoire en "segments" comparables
(des groupes de phrases d'environ 40 à 60 mots), après avoir détecté
la langue du document. C'est sur ces segments que les étapes suivantes
(fingerprinting, embeddings) travailleront.
"""

import spacy
from langdetect import detect, LangDetectException


# Cache des pipelines spaCy déjà chargés, pour ne pas recréer un pipeline
# à chaque appel (spacy.blank() a un petit coût, autant le payer une seule fois par langue).
_NLP_CACHE: dict[str, "spacy.language.Language"] = {}


def detect_language(text: str) -> str:
    """
    Détecte la langue du texte (ex : "fr", "en", "es"...).

    On utilise seulement les 3000 premiers caractères : c'est largement
    suffisant pour détecter la langue de façon fiable, et ça évite de
    ralentir sur un mémoire de 80 pages.

    Si la détection échoue (texte trop court, vide, etc.), on retombe
    sur le français par défaut plutôt que de faire planter le pipeline.
    """
    sample = text[:3000].strip()
    if not sample:
        return "fr"

    try:
        return detect(sample)
    except LangDetectException:
        return "fr"


def _get_sentencizer(lang: str) -> "spacy.language.Language":
    """
    Renvoie un pipeline spaCy "vide" (juste tokenizer + découpeur de phrases)
    pour la langue donnée.

    On utilise spacy.blank(lang) + un "sentencizer" à base de règles
    (ponctuation) plutôt qu'un modèle de langue complet téléchargé :
    - pas besoin de télécharger un modèle par langue (léger, rapide)
    - fonctionne raisonnablement bien pour du découpage de phrases,
      même si c'est moins fin qu'un vrai modèle entraîné.
    Si spaCy ne connaît pas le code de langue détecté, on retombe sur
    un tokenizer générique multilingue ("xx").
    """
    if lang not in _NLP_CACHE:
        try:
            nlp = spacy.blank(lang)
        except Exception:
            nlp = spacy.blank("xx")  # pipeline multilingue générique de secours
        nlp.add_pipe("sentencizer")
        _NLP_CACHE[lang] = nlp

    return _NLP_CACHE[lang]


def split_into_sentences(text: str, lang: str) -> list[str]:
    """
    Découpe le texte en phrases, en utilisant le tokenizer adapté à la langue.
    """
    nlp = _get_sentencizer(lang)
    doc = nlp(text)
    sentences = [sent.text.strip() for sent in doc.sents if sent.text.strip()]
    return sentences


def group_into_chunks(sentences: list[str], min_words: int = 40, max_words: int = 60) -> list[str]:
    """
    Regroupe des phrases consécutives en segments d'environ 40 à 60 mots.

    Pourquoi regrouper plutôt que comparer phrase par phrase ?
    - Une phrase seule est souvent trop courte pour qu'un embedding
      capture bien son sens, et trop facile à faire "matcher" par hasard.
    - Un segment de 40-60 mots donne un contexte plus riche, donc une
      comparaison (fingerprinting et sémantique) plus fiable.

    Le regroupement s'arrête dès qu'on atteint min_words, sauf si la
    prochaine phrase fait dépasser max_words de peu (on essaie de rester
    proche de la fourchette plutôt que de couper trop court).
    """
    chunks = []
    current_words: list[str] = []

    for sentence in sentences:
        sentence_word_count = len(sentence.split())
        current_words.extend(sentence.split())

        # On extrait la version texte reconstituée à la volée pour le chunk courant
        if len(current_words) >= min_words:
            if len(current_words) <= max_words:
                chunks.append(" ".join(current_words))
                current_words = []
            else:
                # On a dépassé la fourchette haute : on clôture le chunk
                # AVANT d'ajouter cette dernière phrase, pour ne pas trop
                # déborder de max_words. Simplification : on accepte que
                # certains chunks dépassent légèrement max_words.
                chunks.append(" ".join(current_words))
                current_words = []

    # S'il reste des mots non regroupés à la fin (dernier chunk trop court),
    # on les rattache au dernier chunk plutôt que de créer un micro-segment.
    if current_words:
        if chunks:
            chunks[-1] += " " + " ".join(current_words)
        else:
            chunks.append(" ".join(current_words))

    return chunks


def segment_document(
    paragraphs: list[dict], min_words: int = 40, max_words: int = 60, forced_lang: str | None = None
) -> list[dict]:
    """
    Point d'entrée principal du module.

    Prend la liste de paragraphes issue de extraction.py (chacun avec son
    numéro de page, voir extraction.extract_document) et renvoie une liste
    de segments, chacun avec un identifiant, son texte, la langue détectée
    et la page d'origine :
    [
        {"id": 0, "text": "...", "lang": "fr", "page": 2},
        {"id": 1, "text": "...", "lang": "fr", "page": 2},
        ...
    ]
    "page" vaut None si le document ne fournit pas cette information
    (cas d'un DOCX — voir extraction.py).

    forced_lang : si l'utilisateur a explicitement choisi une langue dans
    le frontend (dropdown "Langue du document"), on l'utilise directement
    au lieu de faire tourner detect_language. Si forced_lang est None
    (valeur "Détection automatique" du dropdown), on détecte comme avant.

    Important : le regroupement en chunks se fait PARAGRAPHE PAR PARAGRAPHE,
    jamais à cheval sur deux paragraphes. Sans cette contrainte, un
    paragraphe court se retrouverait fusionné avec le paragraphe suivant
    (sans rapport avec lui, et potentiellement sur une AUTRE PAGE) juste
    pour atteindre min_words. Cette contrainte a le mérite supplémentaire
    de garantir qu'un segment ne s'étale jamais sur deux pages différentes
    — chaque segment a donc un numéro de page non ambigu.
    """
    combined_text = "\n".join(p["text"] for p in paragraphs)
    lang = forced_lang if forced_lang else detect_language(combined_text)

    all_chunks: list[tuple[str, int | None]] = []
    for paragraph in paragraphs:
        sentences = split_into_sentences(paragraph["text"], lang)
        if not sentences:
            continue
        chunks = group_into_chunks(sentences, min_words=min_words, max_words=max_words)
        for chunk in chunks:
            all_chunks.append((chunk, paragraph["page"]))

    return [
        {"id": i, "text": text, "lang": lang, "page": page}
        for i, (text, page) in enumerate(all_chunks)
    ]