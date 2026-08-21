"""
Module d'extraction et de nettoyage du texte d'un mémoire.

Rôle : prendre un fichier PDF ou DOCX uploadé, en sortir le texte brut,
le nettoyer (en-têtes/pieds de page répétés, numéros de page), isoler la
section bibliographie, et conserver le NUMÉRO DE PAGE d'origine de chaque
paragraphe (pour les PDF) afin de pouvoir localiser un passage suspect dans
le rapport final.
"""

import re
from collections import Counter
from pathlib import Path

import pymupdf as fitz  # PyMuPDF, pour le PDF
import docx  # python-docx, pour le Word


# Mots-clés qui marquent le début de la bibliographie dans un mémoire francophone.
# On s'arrête au premier trouvé (insensible à la casse, en début de ligne).
BIBLIOGRAPHY_HEADINGS = [
    "bibliographie",
    "références bibliographiques",
    "références",
    "webographie",
]


def extract_text_from_pdf(path: str) -> list[list[str]]:
    """
    Extrait le texte d'un PDF, PAGE PAR PAGE, chaque page étant elle-même
    une liste de paragraphes (pas un seul bloc de texte).

    Piège important : page.get_text() (mode par défaut de PyMuPDF) insère
    un retour à la ligne à chaque RETOUR VISUEL du texte (l'habillage
    d'une ligne trop longue pour la largeur de page), pas seulement aux
    vraies fins de paragraphe. Sans précaution, un paragraphe de 4 lignes
    affichées deviendrait 4 "paragraphes" distincts.

    On utilise donc page.get_text("blocks"), qui regroupe le texte par
    bloc visuel (proche de la notion de paragraphe), et on aplatit les
    retours à la ligne À L'INTÉRIEUR d'un même bloc en simples espaces —
    seule la fin d'un bloc marque une vraie coupure de paragraphe.

    Garder la structure "liste de pages, chacune liste de paragraphes"
    (plutôt que de tout aplatir en une seule chaîne) est ce qui permet
    ensuite de savoir sur quelle page se trouve chaque paragraphe.
    """
    doc = fitz.open(path)
    pages = []
    for page in doc:
        blocks = page.get_text("blocks")
        # Chaque bloc est un tuple (x0, y0, x1, y1, texte, block_no, block_type).
        # On trie par position verticale puis horizontale pour garder l'ordre de lecture.
        blocks.sort(key=lambda b: (round(b[1], 1), b[0]))
        paragraphs = []
        for block in blocks:
            text = block[4]
            # Aplatit les retours à la ligne internes au bloc (habillage visuel)
            # en espaces, pour ne garder qu'un seul "paragraphe" par bloc.
            flattened = " ".join(line.strip() for line in text.split("\n") if line.strip())
            if flattened:
                paragraphs.append(flattened)
        pages.append(paragraphs)
    doc.close()
    return pages


def extract_text_from_docx(path: str) -> list[list[str]]:
    """
    Extrait le texte d'un DOCX.

    Un fichier Word n'a pas de notion de "page" au niveau du texte brut
    (la pagination dépend du rendu à l'affichage/l'impression, pas du
    contenu). On renvoie donc une seule "page" contenant tous les
    paragraphes — extract_document() saura qu'il s'agit d'un DOCX et
    n'attribuera pas de numéro de page dans le rapport final (mieux vaut
    ne rien afficher que d'afficher un numéro trompeur).
    """
    document = docx.Document(path)
    paragraphs = [p.text.strip() for p in document.paragraphs if p.text.strip()]
    return [paragraphs]


def remove_repeated_lines(pages: list[list[str]]) -> list[list[str]]:
    """
    Supprime les paragraphes qui se répètent sur (presque) toutes les
    pages : ce sont typiquement les en-têtes et pieds de page (nom de
    l'étudiant, titre du mémoire répété en haut de chaque page, etc.).

    Principe : on compte combien de pages contiennent chaque paragraphe
    exact. Si un paragraphe apparaît sur plus de 60% des pages, il est
    considéré comme un en-tête/pied de page et retiré partout.
    """
    if len(pages) <= 1:
        # Une seule "page" (cas DOCX) : rien à comparer, on renvoie tel quel.
        return pages

    paragraphs_per_page = [set(page) for page in pages]
    counts = Counter(p for page_paragraphs in paragraphs_per_page for p in page_paragraphs)

    threshold = len(pages) * 0.6
    repeated = {p for p, count in counts.items() if count >= threshold}

    return [[p for p in page if p not in repeated] for page in pages]


def remove_page_numbers(pages: list[list[str]]) -> list[list[str]]:
    """
    Supprime les paragraphes qui ne contiennent qu'un numéro de page
    (ex : un bloc avec juste "12" ou "- 12 -").
    """
    pattern = re.compile(r"^\s*[-–]?\s*\d{1,4}\s*[-–]?\s*$")
    return [[p for p in page if not pattern.match(p)] for page in pages]


def flatten_with_page_numbers(pages: list[list[str]], has_real_pages: bool) -> list[dict]:
    """
    Aplatit la liste de pages en une liste unique de paragraphes, chacun
    annoté avec son numéro de page (1-indexé) — ou None si le format
    n'a pas de vraie notion de page (DOCX).
    """
    result = []
    for page_index, page in enumerate(pages, start=1):
        page_number = page_index if has_real_pages else None
        for paragraph in page:
            result.append({"text": paragraph, "page": page_number})
    return result


def split_bibliography(paragraphs: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Sépare les paragraphes du corps du mémoire de ceux de la bibliographie.

    On cherche le premier paragraphe qui correspond (à peu près) à un des
    titres de section connus, et on considère que tout ce qui suit est la
    bibliographie. Si aucun titre n'est trouvé, tout est renvoyé comme
    "corps" et la bibliographie est vide.

    Retourne : (paragraphes_du_corps, paragraphes_de_la_bibliographie)
    """
    for i, paragraph in enumerate(paragraphs):
        normalized = paragraph["text"].strip().lower()
        if any(normalized.startswith(heading) for heading in BIBLIOGRAPHY_HEADINGS):
            return paragraphs[:i], paragraphs[i:]

    return paragraphs, []


def extract_document(path: str) -> dict:
    """
    Point d'entrée principal du module.

    Prend le chemin d'un fichier PDF ou DOCX et renvoie un dictionnaire :
    {
        "body": texte nettoyé du mémoire, en une seule chaîne (sans bibliographie),
        "bibliography": texte de la bibliographie, en une seule chaîne,
        "paragraphs": liste de {"text": str, "page": int | None}, dans l'ordre
                      de lecture, SANS la bibliographie — c'est cette liste
                      que segmentation.py utilise pour associer un numéro de
                      page à chaque segment.
    }
    """
    extension = Path(path).suffix.lower()

    if extension == ".pdf":
        pages = extract_text_from_pdf(path)
        has_real_pages = True
    elif extension == ".docx":
        pages = extract_text_from_docx(path)
        has_real_pages = False
    else:
        raise ValueError(f"Format non supporté : {extension} (seuls .pdf et .docx sont acceptés)")

    pages = remove_repeated_lines(pages)
    pages = remove_page_numbers(pages)

    all_paragraphs = flatten_with_page_numbers(pages, has_real_pages)
    body_paragraphs, bibliography_paragraphs = split_bibliography(all_paragraphs)

    body = "\n".join(p["text"] for p in body_paragraphs).strip()
    bibliography = "\n".join(p["text"] for p in bibliography_paragraphs).strip()

    return {"body": body, "bibliography": bibliography, "paragraphs": body_paragraphs}