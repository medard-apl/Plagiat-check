"""
Point d'entrée FastAPI du service PlagiatCheck.

Expose un unique endpoint métier : POST /analyze
Reçoit un fichier (PDF/DOCX) + la langue choisie par l'utilisateur (envoyés
en FormData par script.js), renvoie le rapport d'analyse au format que le
frontend attend déjà : { global_score, matches, segment_count }.
"""

import tempfile
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from services.extraction import extract_document
from services.scoring import analyze_document

app = FastAPI(title="PlagiatCheck API")

# CORS : nécessaire car le frontend (fichier HTML statique, ou servi par un
# autre outil en développement) et l'API FastAPI tournent sur des origines
# différentes. "*" est pratique en développement ; à restreindre à l'URL
# exacte du frontend une fois en production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ces deux constantes DOIVENT rester synchronisées avec ALLOWED_EXTENSIONS
# et MAX_FILE_SIZE côté script.js — le frontend filtre déjà côté client,
# mais le backend doit re-vérifier (le client ne fait jamais foi).
ALLOWED_EXTENSIONS = {".pdf", ".docx"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 Mo


@app.post("/analyze")
async def analyze(file: UploadFile = File(...), language: str = Form("auto")):
    """
    Endpoint appelé par analyzeDocument() dans script.js via FormData.

    "language" est déjà accepté dans le contrat même s'il n'est pas encore
    utilisé activement : la détection de langue est automatique côté
    segmentation.py. On garde le paramètre pour ne pas avoir à changer le
    contrat plus tard si on décide de s'en servir (ex : forcer une langue
    quand l'utilisateur sait que la détection automatique se trompe sur
    son document).

    En cas d'erreur, on lève une HTTPException avec un "detail" explicite :
    c'est précisément ce que script.js va chercher dans errorData.detail
    pour afficher un message clair à l'utilisateur.
    """
    extension = Path(file.filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Format non supporté. Utilisez un fichier PDF ou DOCX.")

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Le fichier est trop volumineux. Taille maximale : 20 Mo.")

    # extraction.py a besoin d'un CHEMIN de fichier sur disque (PyMuPDF et
    # python-docx fonctionnent avec des chemins, pas des bytes en mémoire).
    # On écrit donc le fichier dans un dossier temporaire, supprimé
    # automatiquement à la sortie du bloc "with".
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir) / file.filename
        tmp_path.write_bytes(file_bytes)

        try:
            document = extract_document(str(tmp_path))
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error))

    if not document["body"].strip():
        raise HTTPException(status_code=400, detail="Aucun texte n'a pu être extrait de ce document.")

    # "auto" (valeur par défaut du dropdown) -> détection automatique (None).
    # Toute autre valeur ("fr", "en"...) est transmise telle quelle pour
    # forcer la langue de segmentation.
    forced_lang = None if language in ("auto", "other") else language

    report = analyze_document(document["paragraphs"], forced_lang=forced_lang)
    return report


@app.get("/health")
async def health():
    """
    Endpoint de vérification simple (pas utilisé par le frontend).
    Utile pour un "health check" automatique une fois déployé sur
    Render/Railway, ou juste pour vérifier à la main que le service tourne.
    """
    return {"status": "ok"}