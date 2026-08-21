//# fetch() vers /analyze, affichage résultat

/* =========================================================
   CONFIGURATION
   ========================================================= */

/*
 * URL du backend FastAPI.
 *
 * En développement :
 *
 *     http://127.0.0.1:8000
 *
 * Si le frontend est servi directement par FastAPI,
 * tu peux simplement utiliser :
 *
 *     const API_URL = "";
 *
 * Le endpoint final sera alors :
 *
 *     /analyze
 */

const API_URL = "http://127.0.0.1:8000";


/*
 * Taille maximale autorisée.
 *
 * Ici : 20 Mo
 */

const MAX_FILE_SIZE = 20 * 1024 * 1024;


/*
 * Extensions acceptées.
 */

const ALLOWED_EXTENSIONS = [
    ".pdf",
    ".docx"
];


/* =========================================================
   RECUPERATION DES ELEMENTS HTML
   ========================================================= */

const dropZone = document.getElementById("dropZone");

const fileInput = document.getElementById("fileInput");

const filePreview = document.getElementById("filePreview");

const fileName = document.getElementById("fileName");

const fileSize = document.getElementById("fileSize");

const removeFileButton =
    document.getElementById("removeFile");

const analyzeButton =
    document.getElementById("analyzeButton");

const languageSelect =
    document.getElementById("language");

/*const analysisDepthSelect =
    document.getElementById("analysisDepth");*/


/*
 * Sections principales.
 */

const uploadSection =
    document.getElementById("uploadSection");

const loadingSection =
    document.getElementById("loadingSection");

const resultsSection =
    document.getElementById("resultsSection");


/*
 * Éléments de chargement.
 */

const loadingTitle =
    document.getElementById("loadingTitle");

const loadingMessage =
    document.getElementById("loadingMessage");

const progressBar =
    document.getElementById("progressBar");

const progressText =
    document.getElementById("progressText");


/*
 * Éléments des résultats.
 */

const resultDocumentName =
    document.getElementById("resultDocumentName");

const scoreValue =
    document.getElementById("scoreValue");

const scoreTitle =
    document.getElementById("scoreTitle");

const scoreDescription =
    document.getElementById("scoreDescription");

const exactMatches =
    document.getElementById("exactMatches");

const semanticMatches =
    document.getElementById("semanticMatches");

const sourceCount =
    document.getElementById("sourceCount");

const matchesList =
    document.getElementById("matchesList");

const matchCount =
    document.getElementById("matchCount");

const newAnalysisButton =
    document.getElementById("newAnalysisButton");


/*
 * Variable contenant le fichier actuellement sélectionné.
 */

let selectedFile = null;


/* =========================================================
   SELECTION D'UN FICHIER
   ========================================================= */

/*
 * Lorsque l'utilisateur sélectionne un fichier
 * via le bouton "Parcourir".
 */

fileInput.addEventListener("change", function (event) {

    const file = event.target.files[0];

    if (file) {

        handleFile(file);

    }

});


/* =========================================================
   DRAG & DROP
   ========================================================= */

/*
 * Empêche le navigateur d'ouvrir directement le fichier
 * lorsqu'on le dépose dans la page.
 */

dropZone.addEventListener("dragover", function (event) {

    event.preventDefault();

    dropZone.classList.add("dragover");

});


/*
 * Lorsque le curseur quitte la zone.
 */

dropZone.addEventListener("dragleave", function () {

    dropZone.classList.remove("dragover");

});


/*
 * Lorsqu'un fichier est déposé.
 */

dropZone.addEventListener("drop", function (event) {

    event.preventDefault();

    dropZone.classList.remove("dragover");

    const file = event.dataTransfer.files[0];

    if (file) {

        handleFile(file);

    }

});


/* =========================================================
   TRAITEMENT DU FICHIER
   ========================================================= */

/*
 * Cette fonction :
 *
 * 1. Vérifie l'extension
 * 2. Vérifie la taille
 * 3. Sauvegarde le fichier
 * 4. Affiche ses informations
 * 5. Active le bouton "Analyser"
 */

function handleFile(file) {

    /*
     * Vérification de l'extension.
     */

    const extension =
        "." + file.name.split(".").pop().toLowerCase();


    if (!ALLOWED_EXTENSIONS.includes(extension)) {

        showError(
            "Format non supporté. Utilisez un fichier PDF ou DOCX."
        );

        return;

    }


    /*
     * Vérification de la taille.
     */

    if (file.size > MAX_FILE_SIZE) {

        showError(
            "Le fichier est trop volumineux. Taille maximale : 20 Mo."
        );

        return;

    }


    /*
     * Tout est correct.
     */

    selectedFile = file;


    /*
     * Affichage des informations du fichier.
     */

    fileName.textContent = file.name;

    fileSize.textContent = formatFileSize(file.size);


    /*
     * Affichage de la carte du fichier.
     */

    filePreview.classList.remove("hidden");


    /*
     * Activation du bouton.
     */

    analyzeButton.disabled = false;

}


/* =========================================================
   FORMATAGE DE LA TAILLE
   ========================================================= */

function formatFileSize(bytes) {

    if (bytes === 0) {

        return "0 octet";

    }


    const units = [
        "octets",
        "Ko",
        "Mo",
        "Go"
    ];


    const index =
        Math.floor(
            Math.log(bytes) / Math.log(1024)
        );


    return (
        (bytes / Math.pow(1024, index))
            .toFixed(2)
        + " "
        + units[index]
    );

}


/* =========================================================
   SUPPRESSION DU FICHIER
   ========================================================= */

removeFileButton.addEventListener("click", function () {

    selectedFile = null;

    fileInput.value = "";

    filePreview.classList.add("hidden");

    analyzeButton.disabled = true;

});


/* =========================================================
   LANCEMENT DE L'ANALYSE
   ========================================================= */

/*
 * Cette fonction est le cœur de la communication
 * entre le frontend et FastAPI.
 */

analyzeButton.addEventListener("click", analyzeDocument);


async function analyzeDocument() {

    /*
     * Sécurité :
     * on vérifie qu'un fichier existe.
     */

    if (!selectedFile) {

        showError("Veuillez sélectionner un document.");

        return;

    }


    /*
     * On récupère les options.
     */

    const language =
        languageSelect.value;

    /*const depth =
        analysisDepthSelect.value;*/


    /*
     * FormData permet d'envoyer :
     *
     * - le fichier
     * - la langue
     * - le niveau d'analyse
     *
     * au backend.
     */

    const formData = new FormData();


    /*
     * IMPORTANT :
     *
     * Le nom "file" doit correspondre au paramètre
     * attendu par FastAPI.
     *
     * Exemple backend :
     *
     * async def analyze(file: UploadFile = File(...))
     */

    formData.append(
        "file",
        selectedFile
    );


    /*
     * Options supplémentaires.
     */

    formData.append(
        "language",
        language
    );


    /*formData.append(
        "depth",
        depth
    );*/


    /*
     * Passage à l'écran de chargement.
     */

    showLoading();


    /*
     * Animation visuelle de progression.
     *
     * Attention :
     *
     * cette progression est seulement indicative.
     *
     * Le véritable traitement est effectué par le backend.
     */

    startProgress();


    try {

        /*
         * Appel HTTP vers FastAPI.
         */

        const response = await fetch(
            `${API_URL}/analyze`,
            {
                method: "POST",
                body: formData
            }
        );


        /*
         * Si le backend renvoie une erreur HTTP.
         */

        if (!response.ok) {

            let errorMessage =
                "Une erreur est survenue pendant l'analyse.";

            /*
             * On essaie de récupérer le message
             * envoyé par FastAPI.
             */

            try {

                const errorData =
                    await response.json();

                if (errorData.detail) {

                    errorMessage =
                        errorData.detail;

                }

            } catch (error) {

                /*
                 * Rien à faire :
                 * on conserve le message générique.
                 */

            }


            throw new Error(errorMessage);

        }


        /*
         * Conversion de la réponse en JSON.
         */

        const data =
            await response.json();


        /*
         * Affichage des résultats.
         */

        stopProgress();

        displayResults(
            data,
            selectedFile.name
        );

    }


    catch (error) {

        /*
         * Arrêt du chargement.
         */

        stopProgress();


        /*
         * Retour à l'écran d'upload.
         */

        showUpload();


        /*
         * Affichage de l'erreur.
         */

        showError(
            error.message ||
            "Impossible de contacter le serveur."
        );

    }

}


/* =========================================================
   ECRAN DE CHARGEMENT
   ========================================================= */

function showLoading() {

    uploadSection.classList.add("hidden");

    resultsSection.classList.add("hidden");

    loadingSection.classList.remove("hidden");

}


/* =========================================================
   PROGRESSION
   ========================================================= */

let progressInterval = null;

let currentProgress = 0;


/*
 * Messages affichés pendant l'analyse.
 *
 * Ils correspondent directement aux grandes étapes
 * de ton architecture backend.
 */

const progressSteps = [

    {
        progress: 15,
        title: "Préparation du document",
        message: "Extraction du texte du mémoire..."
    },

    {
        progress: 30,
        title: "Segmentation",
        message: "Découpage du document en segments..."
    },

    {
        progress: 45,
        title: "Recherche de correspondances",
        message: "Recherche de sources potentielles..."
    },

    {
        progress: 60,
        title: "Analyse sémantique",
        message: "Comparaison des embeddings..."
    },

    {
        progress: 75,
        title: "Vérification des sources",
        message: "Double vérification des correspondances..."
    },

    {
        progress: 90,
        title: "Calcul du score",
        message: "Agrégation des résultats..."
    }

];


function startProgress() {

    currentProgress = 0;

    updateProgress(5);


    let stepIndex = 0;


    progressInterval = setInterval(function () {

        if (stepIndex >= progressSteps.length) {

            return;

        }


        const step =
            progressSteps[stepIndex];


        /*
         * Ne jamais dépasser 90 % avant que
         * le backend ait réellement répondu.
         */

        currentProgress =
            step.progress;


        updateProgress(
            currentProgress,
            step.title,
            step.message
        );


        stepIndex++;

    }, 1800);

}


function updateProgress(
    progress,
    title = "Analyse en cours...",
    message = "Traitement du document..."
) {

    progressBar.style.width =
        `${progress}%`;

    progressText.textContent =
        `${progress}%`;

    loadingTitle.textContent =
        title;

    loadingMessage.textContent =
        message;

}


function stopProgress() {

    if (progressInterval) {

        clearInterval(progressInterval);

        progressInterval = null;

    }


    updateProgress(
        100,
        "Analyse terminée",
        "Préparation du rapport..."
    );

}


/* =========================================================
   AFFICHAGE DES RESULTATS
   ========================================================= */

function displayResults(data, documentName) {

    /*
     * On cache l'écran de chargement.
     */

    loadingSection.classList.add("hidden");


    /*
     * On affiche les résultats.
     */

    resultsSection.classList.remove("hidden");


    /*
     * Nom du document.
     */

    resultDocumentName.textContent =
        documentName;


    /*
     * Score global.
     *
     * On accepte plusieurs noms possibles pour rendre
     * le frontend plus flexible.
     */

    const score =
        Number(
            data.global_score ??
            data.score ??
            data.similarity_score ??
            0
        );


    /*
     * Affichage du score.
     */

    scoreValue.textContent =
        `${Math.round(score)}%`;


    /*
     * Message associé au score.
     */

    updateScoreDescription(score);


    /*
     * Récupération des correspondances.
     */

    const matches =
        data.matches ??
        data.segments ??
        data.results ??
        [];


    /*
     * Statistiques.
     */

    updateStatistics(matches);


    /*
     * Affichage des passages.
     */

    renderMatches(matches);

}


/* =========================================================
   INTERPRETATION DU SCORE
   ========================================================= */

function updateScoreDescription(score) {

    if (score < 10) {

        scoreTitle.textContent =
            "Faible niveau de similarité";

        scoreDescription.textContent =
            "Peu de correspondances significatives ont été détectées.";

    }

    else if (score < 25) {

        scoreTitle.textContent =
            "Quelques correspondances détectées";

        scoreDescription.textContent =
            "Certaines parties du document présentent des similitudes.";

    }

    else if (score < 50) {

        scoreTitle.textContent =
            "Similarité importante";

        scoreDescription.textContent =
            "Plusieurs passages présentent des correspondances avec les sources analysées.";

    }

    else {

        scoreTitle.textContent =
            "Forte similarité détectée";

        scoreDescription.textContent =
            "Une part importante du document présente des correspondances. Une vérification humaine est recommandée.";

    }

}


/* =========================================================
   STATISTIQUES
   ========================================================= */

function updateStatistics(matches) {

    /*
     * Correspondances exactes.
     *
     * On considère comme exactes les correspondances
     * ayant un type :
     *
     * exact
     * fingerprint
     * copy
     */

    const exact =
        matches.filter(
            match =>
                [
                    "exact",
                    "fingerprint",
                    "copy"
                ].includes(
                    String(
                        match.type ??
                        ""
                    ).toLowerCase()
                )
        ).length;


    /*
     * Correspondances sémantiques.
     */

    const semantic =
        matches.filter(
            match =>
                [
                    "semantic",
                    "embedding",
                    "paraphrase"
                ].includes(
                    String(
                        match.type ??
                        ""
                    ).toLowerCase()
                )
        ).length;


    /*
     * Extraction des URLs uniques.
     */

    const urls =
        new Set(
            matches
                .map(
                    match =>
                        match.source_url ??
                        match.url ??
                        match.source
                )
                .filter(Boolean)
        );


    exactMatches.textContent =
        exact;

    semanticMatches.textContent =
        semantic;

    sourceCount.textContent =
        urls.size;

}


/* =========================================================
   AFFICHAGE DES PASSAGES
   ========================================================= */

function renderMatches(matches) {

    /*
     * Nettoyage de la liste.
     */

    matchesList.innerHTML = "";


    /*
     * Nombre de résultats.
     */

    matchCount.textContent =
        `${matches.length} résultat${matches.length > 1 ? "s" : ""}`;


    /*
     * Aucun résultat.
     */

    if (matches.length === 0) {

        matchesList.innerHTML = `

            <div class="empty-state">

                <h3>
                    Aucune correspondance détectée
                </h3>

                <p>
                    Aucun passage significatif n'a été identifié
                    dans les sources analysées.
                </p>

            </div>

        `;

        return;

    }


    /*
     * Création d'une carte pour chaque résultat.
     */

    matches.forEach(function (match) {

        const card =
            createMatchCard(match);

        matchesList.appendChild(card);

    });

}


/* =========================================================
   CREATION D'UNE CARTE DE CORRESPONDANCE
   ========================================================= */

function createMatchCard(match) {

    /*
     * Type de correspondance.
     */

    const rawType =
        String(
            match.type ??
            "semantic"
        ).toLowerCase();


    const isExact =
        [
            "exact",
            "fingerprint",
            "copy"
        ].includes(rawType);


    const typeClass =
        isExact
            ? "exact"
            : "semantic";


    const typeLabel =
        isExact
            ? "COPIE EXACTE"
            : "SIMILARITÉ SÉMANTIQUE";


    /*
     * Score de correspondance.
     */

    const similarity =
        Number(
            match.score ??
            match.similarity ??
            0
        );


    /*
     * Texte détecté.
     */

    const text =
        match.text ??
        match.segment ??
        match.excerpt ??
        "Texte non disponible.";


    /*
     * Source.
     */

    const sourceUrl =
        match.source_url ??
        match.url ??
        "";


    const sourceTitle =
        (match.source_title ??
        match.title ??
        sourceUrl) ||
        "Source inconnue";


    /*
     * Localisation dans le document (numéro de page).
     *
     * Disponible uniquement pour les PDF (un DOCX n'a pas de vraie
     * notion de page, voir extraction.py côté backend) : match.page
     * vaut alors null/undefined, et on n'affiche simplement rien.
     */

    const page =
        match.page ??
        null;


    /*
     * Création du conteneur.
     */

    const card =
        document.createElement("article");


    card.className =
        "match-card";


    /*
     * IMPORTANT :
     *
     * Le texte provenant du backend ne doit pas être
     * injecté avec innerHTML.
     *
     * On utilise textContent pour éviter une injection XSS.
     */

    card.innerHTML = `

        <div class="match-top">

            <span class="match-type ${typeClass}">
                ${typeLabel}
            </span>

            <div class="match-meta">

                <span class="match-score">
                    ${Math.round(similarity)}% similaire
                </span>

                ${
                    page !== null
                        ? `<span class="match-page">Page ${escapeHTML(page)}</span>`
                        : ""
                }

            </div>

        </div>

        <div class="match-text"></div>

        <div class="source">

            <span class="source-label">
                SOURCE
            </span>

            <a
                href="${escapeAttribute(sourceUrl)}"
                target="_blank"
                rel="noopener noreferrer"
            >
                ${escapeHTML(sourceTitle)}
            </a>

        </div>

    `;


    /*
     * Récupération du bloc de texte.
     */

    const textElement =
        card.querySelector(".match-text");


    /*
     * textContent protège le frontend contre
     * l'injection de HTML venant du backend.
     */

    textElement.textContent =
        text;


    return card;

}


/* =========================================================
   SECURITE
   ========================================================= */

/*
 * Échappe le HTML avant insertion dans innerHTML.
 */

function escapeHTML(value) {

    const div =
        document.createElement("div");

    div.textContent =
        String(value ?? "");

    return div.innerHTML;

}


/*
 * Échappe une valeur utilisée dans un attribut HTML.
 */

function escapeAttribute(value) {

    return escapeHTML(value)
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");

}


/* =========================================================
   NOUVELLE ANALYSE
   ========================================================= */

newAnalysisButton.addEventListener(
    "click",
    function () {

        /*
         * Retour à l'écran principal.
         */

        resultsSection.classList.add("hidden");

        uploadSection.classList.remove("hidden");


        /*
         * Réinitialisation du fichier.
         */

        selectedFile = null;

        fileInput.value = "";

        filePreview.classList.add("hidden");

        analyzeButton.disabled = true;


        /*
         * Réinitialisation de la progression.
         */

        updateProgress(0);

    }
);


/* =========================================================
   AFFICHER L'UPLOAD
   ========================================================= */

function showUpload() {

    loadingSection.classList.add("hidden");

    resultsSection.classList.add("hidden");

    uploadSection.classList.remove("hidden");

}


/* =========================================================
   AFFICHAGE DES ERREURS
   ========================================================= */

/*
 * Version simple pour le prototype.
 *
 * Plus tard, on pourra remplacer cela par une véritable
 * notification "toast".
 */

function showError(message) {

    alert(message);

}