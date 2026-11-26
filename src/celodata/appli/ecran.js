"use strict";
const $ = id => document.getElementById(id);
const api = () => window.pywebview.api;
const FAMILLES = {
  PERSONNE: "personne", LOGIN: "personne", FONCTION: "personne", ROLE: "personne", AGE: "personne",
  COMMUN: "autre",
  ORGANISATION: "lieu", ADRESSE: "lieu", VILLE: "lieu", LIEU: "lieu", PROJET: "lieu",
  SANTE: "sensible", SYNDICAT: "sensible", SECRET: "secret",
};
const NUMEROS = ["TELEPHONE","MAIL","NIR","IBAN","BIC","SIRET","TVA","PLAQUE","IP","MAC","MACHINE","URL",
  "IDENTIFIANT","MATRICULE","NUM_CLIENT","NUM_CONTRAT","DATE","DATE_NAISSANCE","DATE_LOI","DUREE","MONTANT"];
const famille = t => FAMILLES[t] || (NUMEROS.includes(t) ? "numero" : "autre");
const LEGENDE = [["personne", "Personnes"], ["lieu", "Lieux"], ["numero", "Numéros"], ["sensible", "Sensibles"], ["secret", "Secrets"], ["autre", "Autres"]];
const NOMS = {
  PERSONNE: "Personne", ORGANISATION: "Organisation", ADRESSE: "Adresse", VILLE: "Ville", LIEU: "Lieu",
  TELEPHONE: "Téléphone", MAIL: "Courriel", DATE: "Date", DATE_NAISSANCE: "Date de naissance",
  NIR: "N° de sécurité sociale", IBAN: "IBAN", BIC: "BIC", SIRET: "SIRET ou SIREN", TVA: "N° de TVA",
  PLAQUE: "Plaque", IP: "Adresse IP", MAC: "Adresse MAC", MACHINE: "Machine", URL: "Lien",
  IDENTIFIANT: "Identifiant", LOGIN: "Identifiant de connexion", MATRICULE: "Matricule",
  NUM_CLIENT: "N° client", NUM_CONTRAT: "N° de contrat", MONTANT: "Montant", PROJET: "Projet",
  ROLE: "Rôle ou métier", COMMUN: "Terme générique", DUREE: "Durée", DATE_LOI: "Date d'un texte de loi", AGE: "Âge",
  SANTE: "Santé", SYNDICAT: "Syndicat", SECRET: "Secret (supprimé)", FONCTION: "Fonction", AUTRE: "Autre",
};
const nomType = t => NOMS[t] || t.toLowerCase().replace(/_/g, " ");
const pluriel = (n, mot, s = "s") => `${n} ${mot}${n > 1 ? s : ""}`;

let texte = "";          // texte analysé
let passages = [];       // {debut, fin, type, actif, suggestion, hors} ; hors : catégorie laissée en clair
let traitement = "pseudonymisation";
let prereglages = {courant: "", categories: [], liste: []};
let selection = null;    // {debut, fin} en attente d'ajout
let fichier = "";        // nom du fichier chargé
let formate = false;     // Word, Excel ou PDF : enregistré dans un format de document
let estPdf = false;
let scan = 0;            // pages lues par reconnaissance de caractères
let zones = [];          // PDF : zones sans texte lu {page, cadre, actif, manuel}
let nbPages = 0;         // PDF : nombre de pages
let pagesFaites = false; // les images des pages ont été demandées

async function copier(contenu) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    try {
      await navigator.clipboard.writeText(contenu);
      return true;
    } catch (_) {
      // Repli ci-dessous si le contexte WebView bloque l'API Clipboard.
    }
  }
  const z = document.createElement("textarea");
  z.value = contenu; z.style.position = "fixed"; z.style.opacity = "0";
  document.body.appendChild(z); z.select();
  const ok = document.execCommand("copy");
  z.remove();
  return ok;
}
function cellule(tr, contenu, classe) {
  const td = document.createElement("td");
  if (classe) td.className = classe;
  td.append(contenu); tr.append(td);
  return td;
}
function ligneVide(corps, colonnes, message) {
  const tr = document.createElement("tr");
  cellule(tr, message, "vide").colSpan = colonnes;
  corps.append(tr);
}
function etiquette(contenu, genre) {
  const s = document.createElement("span");
  s.className = "etiquette" + (genre ? " " + genre : "");
  s.textContent = contenu;
  return s;
}
let minuteur = 0;
function annoncer(message) {
  $("toast-texte").textContent = message; $("toast").classList.add("vu");
  clearTimeout(minuteur); minuteur = setTimeout(() => $("toast").classList.remove("vu"), 2800);
}

// ---------- thème ----------
function appliquerTheme(theme) {
  if (theme) document.documentElement.dataset.theme = theme;
  else delete document.documentElement.dataset.theme;
  $("theme").querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.t === (theme || ""))));
}
$("theme").addEventListener("click", e => {
  const b = e.target.closest("button");
  if (!b) return;
  appliquerTheme(b.dataset.t);
  api().choisir_theme(b.dataset.t);
});

// ---------- ouverture ----------
async function demarrer() {
  const e = await api().etat();
  appliquerTheme(e.theme);
  if (e.ouverte) return entrer();
  $("porte-titre").textContent = e.table_existe ? "Ouvrir la table" : "Créer votre table";
  $("porte-aide").textContent = e.table_existe
    ? "Entrez le mot de passe de votre table de correspondance."
    : "La table garde la correspondance entre vos données et leurs jetons. Elle reste chiffrée sur ce poste.";
  $("porte-ok").textContent = e.table_existe ? "Ouvrir la table" : "Créer la table";
  $("bloc-confirmation").hidden = e.table_existe;
  $("porte").dataset.nouvelle = e.table_existe ? "" : "1";
  $("mdp").focus();
}
$("oeil").addEventListener("click", () => {
  const visible = $("mdp").type === "text";
  $("mdp").type = $("mdp2").type = visible ? "password" : "text";
  $("oeil").setAttribute("aria-label", visible ? "Afficher le mot de passe" : "Masquer le mot de passe");
});
$("mdp").addEventListener("input", () => {
  const v = $("mdp").value;
  const n = !v ? 0 : v.length < 8 ? 1 : v.length < 12 ? 2 : (v.length >= 16 || /\s|-/.test(v)) ? 4 : 3;
  $("jauge").dataset.n = n;
  $("jauge-txt").textContent = [
    "Au moins 8 caractères. Une phrase de plusieurs mots est le plus simple à retenir.",
    "Trop court : il faut au moins 8 caractères.",
    "Correct. Quelques caractères de plus le rendraient solide.",
    "Solide.",
    "Très solide.",
  ][n];
});
$("porte-form").addEventListener("submit", async ev => {
  ev.preventDefault();
  const erreur = $("porte-erreur");
  erreur.textContent = "";
  if ($("porte").dataset.nouvelle && $("mdp").value !== $("mdp2").value) {
    erreur.textContent = "Les deux mots de passe sont différents."; return;
  }
  const bouton = $("porte-ok"), libelle = bouton.textContent;
  bouton.disabled = true;
  bouton.textContent = "Ouverture… Windows peut vous demander de confirmer";
  const r = await api().ouvrir($("mdp").value);
  bouton.disabled = false;
  bouton.textContent = libelle;
  $("mdp").value = $("mdp2").value = "";
  if (!r.ok) { erreur.textContent = r.erreur; return; }
  entrer();
});
function direProtection(p) {
  const lien = p.liee
    ? "La table est liée à ce poste : copiée ailleurs, elle ne s'ouvre pas, même avec le mot de passe."
    : "La table n'est protégée que par son mot de passe.";
  const hello = p.hello
    ? " Windows Hello est demandé à chaque ouverture."
    : " Ce poste n'a pas Windows Hello : seul le mot de passe est demandé.";
  $("table-etat").textContent = lien + hello + (p.liee ? " Si votre session Windows est perdue ou réinstallée, la table l'est aussi." : "");
  $("protection").textContent = (p.liee ? "Table liée à ce poste" : "Table chiffrée") + (p.hello ? ", Windows Hello" : "") + ", aucune connexion sortante.";
}
$("table-form").addEventListener("submit", async ev => {
  ev.preventDefault();
  const message = $("table-message");
  message.textContent = ""; message.className = "message";
  const r = await api().deplacer_table($("table-mdp").value);
  $("table-mdp").value = "";
  if (r.annule) return;
  if (r.ok) message.className = "message bon";
  message.textContent = r.ok ? `Copie enregistrée : ${r.chemin}` : r.erreur;
});
$("mdp-form").addEventListener("submit", async ev => {
  ev.preventDefault();
  const message = $("mdp-message");
  message.textContent = ""; message.className = "message";
  const ancien = $("mdp-ancien").value, nouveau = $("mdp-nouveau").value, confirm = $("mdp-confirm").value;
  if (nouveau !== confirm) { message.textContent = "Les deux nouveaux mots de passe sont différents."; return; }
  const r = await api().changer_mot_de_passe(ancien, nouveau);
  $("mdp-ancien").value = $("mdp-nouveau").value = $("mdp-confirm").value = "";
  if (!r.ok) { message.textContent = r.erreur; return; }
  message.className = "message bon";
  message.textContent = "Mot de passe modifié.";
  annoncer("Mot de passe modifié");
});
$("purge-form").addEventListener("submit", async ev => {
  ev.preventDefault();
  const message = $("purge-message");
  message.textContent = ""; message.className = "message";
  const jours = Number($("purge-jours").value);
  const r = await api().purger_table(jours);
  if (!r.ok) { message.textContent = r.erreur; return; }
  message.className = "message bon";
  message.textContent = r.supprimees
    ? `${pluriel(r.supprimees, "valeur")} supprimée${r.supprimees > 1 ? "s" : ""} (${pluriel(r.restantes, "restante")}).`
    : `Aucune valeur à purger (${pluriel(r.restantes, "valeur")} dans la table).`;
  annoncer("Table purgée");
});
function entrer() {
  api().protection().then(direProtection);
  $("porte").hidden = true; $("rail").hidden = false; $("filtrer").hidden = false;
  $("etat").textContent = "Chargement du modèle…";
  api().preparer().then(r => {
    $("etat").textContent = r.modele ? "Noms et numéros détectés" : "Règles seules : les noms ne sont pas détectés";
    $("etat").className = r.modele ? "pret" : "limite";
  });
  suivreSurveillance();
  setInterval(suivreSurveillance, 3000);
  choisirTraitement(traitement);
  chargerPrereglages();
}

// ---------- traitement et préréglage ----------
function rappel() {
  const nom = traitement === "caviardage" ? "Caviardage" : "Pseudonymisation";
  $("doc-traitement").textContent = prereglages.courant ? `${nom} · ${prereglages.courant}` : nom;
  $("dossier-rappel").textContent = `${nom}${prereglages.courant ? `, préréglage ${prereglages.courant}` : ""} : le choix fait plus haut.`;
}
function choisirTraitement(t) {
  traitement = t;
  document.querySelectorAll("#traitement button").forEach(b => b.setAttribute("aria-pressed", b.dataset.t === t));
  $("traitement-aide").textContent = t === "caviardage"
    ? "Les données sont retirées pour de bon, sans retour possible : gardez l'original à part."
    : "Chaque donnée devient un jeton. Celodata remettra les vraies valeurs dans la réponse de l'IA.";
  rappel();
  if (texte) lister();
}
document.querySelectorAll("#traitement button").forEach(b => b.addEventListener("click", () => choisirTraitement(b.dataset.t)));
async function chargerPrereglages() {
  prereglages = await api().prereglages();
  ["prereglage", "pre-choix"].forEach(id => {
    const s = $(id);
    s.textContent = "";
    prereglages.liste.forEach(x => {
      const o = document.createElement("option");
      o.value = x.nom; o.textContent = x.nom + (x.modifie ? " (modifié)" : "");
      s.append(o);
    });
    s.value = prereglages.courant;
  });
  const p = prereglages.liste.find(x => x.nom === prereglages.courant);
  const cases = $("pre-cases");
  cases.textContent = "";
  prereglages.categories.forEach(type => {
    const l = document.createElement("label"), c = document.createElement("input");
    c.type = "checkbox"; c.dataset.t = type; c.checked = !p.laisses.includes(type);
    l.append(c, nomType(type));
    cases.append(l);
  });
  $("pre-nom").value = p.nom;
  $("pre-etat").textContent = `${prereglages.categories.length - p.laisses.length} catégories masquées sur ${prereglages.categories.length}`;
  $("pre-supprimer").hidden = p.origine && !p.modifie;
  $("pre-supprimer").textContent = p.origine ? "Remettre comme au départ" : "Supprimer ce préréglage";
  $("pre-erreur").textContent = "";
  rappel();
}
async function choisirPrereglage(nom) {
  await api().choisir_prereglage(nom);
  await chargerPrereglages();
}
$("prereglage").addEventListener("change", ev => choisirPrereglage(ev.target.value));
$("pre-choix").addEventListener("change", ev => choisirPrereglage(ev.target.value));
$("pre-enregistrer").addEventListener("click", async () => {
  const nom = $("pre-nom").value.trim();
  const laisses = [...document.querySelectorAll("#pre-cases input")].filter(c => !c.checked).map(c => c.dataset.t);
  const r = await api().enregistrer_prereglage(nom, laisses);
  if (!r.ok) { $("pre-erreur").textContent = r.erreur; return; }
  await choisirPrereglage(nom);
  annoncer("Préréglage enregistré");
});
$("pre-supprimer").addEventListener("click", async () => {
  await api().supprimer_prereglage(prereglages.courant);
  await chargerPrereglages();
  annoncer("Préréglage retiré");
});
const ONGLETS = ["filtrer", "restaurer", "surveille", "regles", "journal"];
function onglet(nom) {
  document.querySelectorAll("nav button").forEach(x => x.setAttribute("aria-selected", x.dataset.onglet === nom));
  ONGLETS.forEach(o => { $(o).hidden = nom !== o; });
  $("ajout").hidden = true;
  if (nom === "regles") chargerRegles();
  if (nom === "journal") chargerJournal();
  if (nom === "surveille") suivreSurveillance();
}
document.querySelectorAll("nav button").forEach(b => b.addEventListener("click", () => onglet(b.dataset.onglet)));

// ---------- les quatre vues de « Protéger un document » ----------
function vue(nom) {
  $("vue-deposer").hidden = nom !== "deposer";
  $("attente").hidden = nom !== "attente";
  $("verifier").hidden = nom !== "verifier";
  $("vue-exporter").hidden = nom !== "exporter";
  $("ajout").hidden = true;
  document.querySelector("main").scrollTop = 0;
}
function attendre(titre) {
  $("attente-titre").textContent = titre;
  if ($("attente").hidden) { avancer({etape: ""}); vue("attente"); }
}

// ---------- avancement et annulation ----------
let course = 0;          // numéro du travail en cours : le résultat d'un travail annulé est ignoré
let minuteurSuivi = null;
function duree(s) {
  if (s < 55) return `${Math.max(5, Math.ceil(s / 5) * 5)} s`;
  return `${Math.round(s / 60)} min`;
}
function avancer(a) {
  const barre = $("progres");
  const mesure = a.total > 1;
  barre.classList.toggle("vague", !mesure);
  barre.firstElementChild.style.width = mesure ? `${Math.round(100 * a.fait / a.total)}%` : "";
  if (mesure) barre.setAttribute("aria-valuenow", Math.round(100 * a.fait / a.total)); else barre.removeAttribute("aria-valuenow");
  const page = `page ${Math.min(a.fait + 1, a.total)} sur ${a.total}`;
  let detail = {
    lecture: mesure ? `Lecture du document, ${page}` : "Lecture du document",
    zones: mesure ? `Recherche des tampons et signatures, ${page}` : "Recherche des tampons et signatures",
    modele: "Chargement du modèle d'entités, une seule fois par ouverture",
    attente: "En attente : un autre document est en cours d'analyse",
    analyse: mesure ? `Recherche des données, ${Math.round(100 * a.fait / a.total)} %` : "Recherche des données",
  }[a.etape] || "";
  // Le temps restant est estimé sur l'étape en cours, dès qu'une part mesurable est faite.
  if (mesure && a.fait >= 1 && a.depuis >= 2) {
    const reste = a.depuis * (a.total - a.fait) / a.fait;
    if (reste >= 3) detail += `. Encore environ ${duree(reste)}`;
  }
  $("attente-detail").textContent = detail;
}
function finSuivi() { clearInterval(minuteurSuivi); minuteurSuivi = null; }
function suivre() {
  finSuivi();
  const moi = ++course;
  minuteurSuivi = setInterval(async () => {
    const a = await api().avancement();
    if (moi !== course || !a.etape) return;
    if ($("attente").hidden) vue("attente");
    avancer(a);
  }, 400);
  return moi;
}
$("btn-annuler-analyse").addEventListener("click", () => {
  course++; finSuivi();
  api().annuler();
  api().oublier();
  vue("deposer");
  annoncer("Analyse annulée");
});
function vider() {
  texte = ""; passages = []; fichier = ""; formate = false; estPdf = false; scan = 0; zones = []; nbPages = 0;
  $("source").value = ""; $("bloc-coller").hidden = true; $("depot-erreur").textContent = "";
  $("apercu").textContent = ""; $("liste").textContent = ""; $("filtre").textContent = "";
  api().oublier();
  vue("deposer");
}
function refuser(message) { vue("deposer"); $("depot-erreur").textContent = message; }

// ---------- déposer ----------
$("btn-coller").addEventListener("click", () => { $("bloc-coller").hidden = false; $("source").focus(); });
$("btn-annuler-coller").addEventListener("click", () => { $("bloc-coller").hidden = true; $("source").value = ""; });
$("btn-analyser").addEventListener("click", async () => {
  const colle = $("source").value.replace(/\r\n?/g, "\n");
  if (!colle.trim()) { $("source").focus(); return; }
  await api().oublier();
  fichier = ""; formate = false; estPdf = false; scan = 0; zones = []; nbPages = 0;
  analyser(colle, "Analyse du texte…");
});
async function analyser(contenu, titre, dejaFaite, enCours) {
  $("depot-erreur").textContent = "";
  const moi = enCours || suivre();
  attendre(titre);
  try {
    const r = dejaFaite || await api().analyser(contenu);
    if (moi !== course) return;
    finSuivi();
    if (r.annule) { vue("deposer"); return; }
    texte = contenu;
    passages = [
      ...r.detections.map(d => ({...d, actif: !d.hors, suggestion: false, hors: !!d.hors})),
      ...r.suggestions.map(d => ({...d, actif: false, suggestion: true})),
    ].sort((a, b) => a.debut - b.debut);
    $("doc-nom").textContent = fichier || "Texte collé";
    $("doc-nom").title = fichier || "";
    $("avert-scan").textContent = scan
      ? `Document scanné : ${pluriel(scan, "page")} ${scan > 1 ? "ont été lues" : "a été lue"} par reconnaissance de caractères. Une lecture de scan n'est jamais parfaite : un nom ou un numéro mal lu n'est pas masqué. Relisez tout le document avant de continuer.`
      : (r.modele ? "" : "Modèle d'entités absent : seules les règles ont tourné, les noms ne sont pas détectés.");
    $("filtre-liste").value = ""; $("autre-info").textContent = "";
    pagesFaites = false; $("pages-liste").textContent = ""; $("outils-doc").hidden = !estPdf; affichage("texte");
    dessiner();
    vue("verifier");
    $("apercu").parentElement.scrollTop = 0;
  } catch (e) {
    if (moi !== course) return;
    finSuivi();
    refuser("Erreur pendant l'analyse : " + e);
  }
}
function charger(r, moi) {
  if (moi && moi !== course) return;
  if (r.annule) { finSuivi(); vue("deposer"); return; }
  if (!r.ok) { finSuivi(); refuser(r.erreur); return; }
  fichier = r.nom; formate = !!r.format; estPdf = !!r.pdf; scan = r.pages_scannees || 0;
  zones = (r.zones || []).map(z => ({...z, actif: true, manuel: false})); nbPages = r.pages || 0;
  analyser(r.texte, `Analyse de ${r.nom}…`, r.analyse, moi);
}
$("btn-ouvrir").addEventListener("click", async () => {
  $("depot-erreur").textContent = "";
  // L'écran d'attente s'affiche dès que la lecture commence, une fois le fichier choisi.
  const moi = suivre();
  $("attente-titre").textContent = "Lecture du document…";
  charger(await api().ouvrir_fichier(), moi);
});
// Dépôt d'un fichier n'importe où dans la vue.
const depot = $("depot");
window.addEventListener("dragover", ev => ev.preventDefault());
window.addEventListener("drop", ev => ev.preventDefault());
$("vue-deposer").addEventListener("dragover", ev => { ev.preventDefault(); depot.classList.add("survol"); });
$("vue-deposer").addEventListener("dragleave", ev => { if (!$("vue-deposer").contains(ev.relatedTarget)) depot.classList.remove("survol"); });
$("vue-deposer").addEventListener("drop", async ev => {
  ev.preventDefault(); depot.classList.remove("survol");
  const f = ev.dataTransfer.files[0];
  if (!f) return;
  const moi = suivre();
  attendre(`Lecture de ${f.name}…`);
  // Le fichier est lu en mémoire puis confié au moteur : rien n'est écrit sur disque.
  const octets = new Uint8Array(await f.arrayBuffer());
  let binaire = "";
  for (let i = 0; i < octets.length; i += 0x8000) binaire += String.fromCharCode.apply(null, octets.subarray(i, i + 0x8000));
  charger(await api().lire_fichier(f.name, btoa(binaire)), moi);
});

// Dossier entier, sans aperçu.
$("btn-dossier").addEventListener("click", async () => {
  const boutons = ["btn-dossier", "btn-ouvrir", "btn-coller"];
  boutons.forEach(b => { $(b).disabled = true; });
  $("info-dossier").textContent = "Traitement en cours : quelques secondes par document…";
  try {
    const r = await api().filtrer_dossier(traitement);
    if (!r.annule) {
      const corps = $("dossier-lignes");
      const caviar = r.traitement === "caviardage";
      corps.textContent = "";
      r.fichiers.forEach(f => {
        const tr = document.createElement("tr");
        cellule(tr, f.fichier);
        cellule(tr, f.ok ? String(f.masques) : "", "nombre");
        cellule(tr, f.ok && f.a_verifier ? String(f.a_verifier) : "", "nombre");
        if (f.ok) cellule(tr, etiquette((caviar ? "Caviardé" : "Pseudonymisé") + (f.remarque ? ` (${f.remarque})` : ""), f.remarque ? "scan" : "bon"));
        else cellule(tr, f.erreur, "erreur");
        corps.append(tr);
      });
      if (!r.fichiers.length) ligneVide(corps, 4, "Aucun document lisible dans ce dossier.");
      const faits = r.fichiers.filter(f => f.ok).length, rates = r.fichiers.length - faits;
      $("dossier-aide").textContent = `${pluriel(faits, "document")} ${caviar ? "caviardé" : "pseudonymisé"}${faits > 1 ? "s" : ""}`
        + (rates ? `, ${rates} non traité${rates > 1 ? "s" : ""}` : "")
        + `. Les fichiers sont dans ${r.sortie}. Ils n'ont pas été vérifiés à l'écran : relisez-les avant de les transmettre.`
        + (r.modele ? "" : " Modèle d'entités absent : les noms n'ont pas été détectés.");
      $("bloc-dossier").hidden = false;
      $("bloc-dossier").scrollIntoView({behavior: "smooth", block: "nearest"});
      annoncer(`Dossier traité : ${pluriel(faits, "document")}`);
    }
    $("info-dossier").textContent = "";
  } catch (e) {
    $("info-dossier").textContent = "Erreur : " + e;
  }
  boutons.forEach(b => { $(b).disabled = false; });
});

// ---------- vérifier ----------
const valeur = p => texte.slice(p.debut, p.fin);
function dessiner() {
  const zone = $("apercu");
  zone.textContent = "";
  let position = 0;
  passages.forEach((p, i) => {
    zone.append(texte.slice(position, p.debut));
    const m = document.createElement("mark");
    m.textContent = valeur(p);
    m.dataset.i = i; m.tabIndex = 0; m.setAttribute("role", "button");
    m.className = p.actif ? famille(p.type) : (p.suggestion ? "suggestion" : p.hors ? "hors" : "inactif");
    m.title = `${nomType(p.type)} · ` + (p.actif ? "cliquer pour laisser en clair" : p.hors ? "catégorie laissée en clair, cliquer pour masquer" : "cliquer pour masquer");
    zone.append(m);
    position = p.fin;
  });
  zone.append(texte.slice(position));
  lister();
}
function lister() {
  const liste = $("liste"), cherche = $("filtre-liste").value.trim().toLowerCase();
  liste.textContent = "";
  // Un groupe par type ; les fonctions « à vérifier » non cochées ont leur propre groupe, en tête.
  const groupes = new Map();
  passages.forEach((p, i) => {
    const cle = p.suggestion && !p.actif ? "?" : p.type;
    if (!groupes.has(cle)) groupes.set(cle, new Map());
    const g = groupes.get(cle), v = valeur(p);
    if (!g.has(v)) g.set(v, {n: 0, actif: p.actif, premier: i});
    g.get(v).n++;
  });
  const actifs = cle => [...groupes.get(cle).values()].filter(x => x.actif).length;
  const rang = cle => cle === "?" ? 0 : actifs(cle) ? 1 : 2;
  const ordre = [...groupes.keys()].sort((a, b) => rang(a) - rang(b) || nomType(a).localeCompare(nomType(b), "fr"));
  let montres = 0;
  ordre.forEach(cle => {
    const lignes = [...groupes.get(cle)].filter(([v]) => !cherche || v.toLowerCase().includes(cherche));
    if (!lignes.length) return;
    const bloc = document.createElement("div");
    bloc.className = "groupe " + (cle === "?" ? "averifier" : famille(cle)) + (rang(cle) === 2 ? " eteint" : "");
    const titre = document.createElement("h4");
    if (cle !== "?") {
      // Une case pour toute la catégorie : cochée si tout est masqué, entre deux si une partie l'est.
      const tout = document.createElement("input"), n = actifs(cle), total = groupes.get(cle).size;
      tout.type = "checkbox"; tout.checked = n === total; tout.indeterminate = n > 0 && n < total;
      tout.title = n === total ? "Laisser toute la catégorie en clair" : "Masquer toute la catégorie";
      tout.setAttribute("aria-label", `${tout.title} : ${nomType(cle)}`);
      tout.addEventListener("change", () => basculerCategorie(cle, tout.checked));
      titre.append(tout);
    }
    titre.append(document.createElement("i"), cle === "?" ? "À vérifier" : nomType(cle));
    const compte = document.createElement("span"); compte.textContent = lignes.length; titre.append(compte);
    bloc.append(titre);
    lignes.forEach(([v, x]) => {
      const ligne = document.createElement("div");
      ligne.className = "ligne" + (x.actif || cle === "?" ? "" : " non");
      const case_ = document.createElement("input");
      case_.type = "checkbox"; case_.checked = x.actif;
      case_.setAttribute("aria-label", (x.actif ? "Laisser en clair " : "Masquer ") + v);
      case_.addEventListener("change", () => basculer(x.premier));
      const b = document.createElement("button");
      b.type = "button"; b.textContent = v; b.title = "Voir dans le document";
      b.addEventListener("click", () => viser(x.premier));
      ligne.append(case_, b);
      if (x.n > 1) { const n = document.createElement("small"); n.textContent = "×" + x.n; ligne.append(n); }
      bloc.append(ligne);
      montres++;
    });
    liste.append(bloc);
  });
  if (!montres) {
    const vide = document.createElement("p");
    vide.className = "info"; vide.style.padding = "12px 8px";
    vide.textContent = passages.length ? "Rien ne correspond à cette recherche." : "Aucune donnée repérée. Sélectionnez du texte dans le document pour le masquer.";
    liste.append(vide);
  }
  // Légende : valeurs distinctes masquées, par famille de couleur.
  const parFamille = {};
  passages.filter(p => p.actif).forEach(p => { (parFamille[famille(p.type)] ||= new Set()).add(valeur(p)); });
  const n = new Set(passages.filter(p => p.actif).map(valeur)).size;
  const v = new Set(passages.filter(p => p.suggestion && !p.actif).map(valeur)).size;
  const z = zones.filter(x => x.actif).length;
  const legende = $("legende");
  legende.textContent = "";
  LEGENDE.forEach(([cle, nom]) => {
    if (!parFamille[cle]) return;
    const s = document.createElement("span"); s.className = "lg-" + cle; s.textContent = `${nom} ${parFamille[cle].size}`; legende.append(s);
  });
  if (v) { const s = document.createElement("span"); s.className = "lg-averifier"; s.textContent = `À vérifier ${v}`; legende.append(s); }
  $("titre-liste").textContent = n ? `${pluriel(n, "donnée")} à masquer` : "Rien à masquer pour l'instant";
  $("btn-continuer").textContent = n ? `${traitement === "caviardage" ? "Caviarder" : "Pseudonymiser"} ${pluriel(n, "donnée")}` : "Exporter sans rien masquer";
  $("doc-bilan").textContent = [v ? `${pluriel(v, "fonction")} à vérifier, laissée${v > 1 ? "s" : ""} en clair` : "", z ? `${pluriel(z, "zone")} sans texte à recouvrir` : ""].filter(Boolean).join(". ");
  $("nb-zones").hidden = !z; $("nb-zones").textContent = z;
}
$("filtre-liste").addEventListener("input", lister);
function viser(i) {
  const m = $("apercu").querySelector(`mark[data-i="${i}"]`);
  if (!m) return;
  document.querySelectorAll("mark.vise").forEach(x => x.classList.remove("vise"));
  m.classList.add("vise");
  m.scrollIntoView({behavior: "smooth", block: "center"});
}
function basculer(i) {
  const v = valeur(passages[i]), actif = !passages[i].actif;
  // Une même valeur est masquée partout ou nulle part.
  passages.forEach(p => { if (valeur(p) === v) p.actif = actif; });
  const haut = $("liste").scrollTop;
  dessiner();
  $("liste").scrollTop = haut;
}
function basculerCategorie(type, actif) {
  passages.forEach(p => {
    if (p.type !== type || (p.suggestion && !p.actif)) return;
    p.actif = actif;
    // Une catégorie décochée n'est pas une correction : ses valeurs ne sont pas retenues comme « à ne plus masquer ».
    if (!actif && !p.suggestion) p.hors = true;
  });
  const haut = $("liste").scrollTop;
  dessiner();
  $("liste").scrollTop = haut;
}
$("apercu").addEventListener("click", ev => {
  const m = ev.target.closest("mark");
  if (m && window.getSelection().isCollapsed) basculer(+m.dataset.i);
});
$("apercu").addEventListener("keydown", ev => {
  if ((ev.key === "Enter" || ev.key === " ") && ev.target.matches("mark")) { ev.preventDefault(); basculer(+ev.target.dataset.i); }
});
function masquerPartout(terme, type) {
  const nouveaux = [];
  for (let i = texte.indexOf(terme); i !== -1; i = texte.indexOf(terme, i + terme.length))
    nouveaux.push({debut: i, fin: i + terme.length, type, actif: true, suggestion: false});
  if (!nouveaux.length) return 0;
  passages = passages
    .filter(p => nouveaux.every(n => p.fin <= n.debut || p.debut >= n.fin))
    .concat(nouveaux).sort((a, b) => a.debut - b.debut);
  dessiner();
  return nouveaux.length;
}
// Sélection à la souris : proposer de masquer le passage.
function position(noeud, decalage) {
  const r = document.createRange();
  r.selectNodeContents($("apercu"));
  r.setEnd(noeud, decalage);
  return r.toString().length;
}
document.addEventListener("mouseup", ev => {
  if ($("ajout").contains(ev.target)) return;
  const s = window.getSelection();
  if (s.isCollapsed || !s.rangeCount || !$("apercu").contains(s.anchorNode) || !$("apercu").contains(s.focusNode)) {
    $("ajout").hidden = true; selection = null; return;
  }
  const r = s.getRangeAt(0);
  let debut = position(r.startContainer, r.startOffset), fin = position(r.endContainer, r.endOffset);
  while (debut < fin && /\s/.test(texte[debut])) debut++;
  while (fin > debut && /\s/.test(texte[fin - 1])) fin--;
  if (fin <= debut) { $("ajout").hidden = true; return; }
  selection = {debut, fin};
  const boite = $("ajout");
  boite.hidden = false;
  boite.style.left = Math.max(8, Math.min(ev.clientX, window.innerWidth - boite.offsetWidth - 8)) + "px";
  boite.style.top = Math.min(ev.clientY + 14, window.innerHeight - boite.offsetHeight - 8) + "px";
});
$("ajout-ok").addEventListener("click", () => {
  if (!selection) return;
  const terme = texte.slice(selection.debut, selection.fin);
  const n = masquerPartout(terme, $("ajout-type").value);
  selection = null; $("ajout").hidden = true; window.getSelection().removeAllRanges();
  if (n) annoncer(n > 1 ? `« ${terme} » masqué ${n} fois` : `« ${terme} » masqué`);
});
$("autre-type").innerHTML = $("ajout-type").innerHTML;
$("autre-type").value = "AUTRE";
$("autre").addEventListener("submit", ev => {
  ev.preventDefault();
  const terme = $("autre-terme").value.trim();
  if (!terme) return;
  const n = masquerPartout(terme, $("autre-type").value);
  $("autre-info").textContent = n ? `« ${terme} » masqué ${n} fois.` : `« ${terme} » ne figure pas dans le document (les majuscules comptent).`;
  if (n) $("autre-terme").value = "";
});
$("btn-retour-depot").addEventListener("click", vider);

// ---------- vue « Pages » d'un PDF : zones sans texte lu ----------
function affichage(v) {
  document.querySelectorAll("#bascule button").forEach(b => b.setAttribute("aria-pressed", b.dataset.v === v));
  $("apercu").hidden = v !== "texte"; $("pages").hidden = v !== "pages"; $("ajout").hidden = true;
  if (v === "pages" && !pagesFaites) chargerPages();
}
document.querySelectorAll("#bascule button").forEach(b => b.addEventListener("click", () => affichage(b.dataset.v)));
async function chargerPages() {
  pagesFaites = true;
  const liste = $("pages-liste"), nom = fichier;
  liste.textContent = "";
  for (let n = 0; n < nbPages; n++) {
    const vuePage = document.createElement("div");
    vuePage.className = "pagevue"; vuePage.dataset.page = n;
    const img = document.createElement("img"); img.alt = `Page ${n + 1}`;
    vuePage.append(img); liste.append(vuePage);
  }
  dessinerZones();
  for (let n = 0; n < nbPages; n++) {
    const r = await api().image_page(n);
    if (fichier !== nom || !pagesFaites) return;   // un autre document a été ouvert entre-temps
    if (r.ok) liste.children[n].querySelector("img").src = r.image;
  }
}
function dessinerZones() {
  document.querySelectorAll("#pages-liste .zg").forEach(x => x.remove());
  zones.forEach((z, i) => {
    const vuePage = $("pages-liste").children[z.page];
    if (!vuePage) return;
    const [g, h, d, b] = z.cadre, bloc = document.createElement("div");
    bloc.className = "zg" + (z.actif ? "" : " non"); bloc.dataset.i = i;
    bloc.style.cssText = `left:${g * 100}%;top:${h * 100}%;width:${(d - g) * 100}%;height:${(b - h) * 100}%`;
    bloc.title = z.manuel ? "Cliquer pour retirer cette zone" : (z.actif ? "Cliquer pour laisser visible" : "Cliquer pour recouvrir");
    vuePage.append(bloc);
  });
  lister();
}
let trace = null;   // rectangle en cours de tracé
$("pages-liste").addEventListener("mousedown", ev => {
  const vuePage = ev.target.closest(".pagevue");
  if (!vuePage || ev.button !== 0) return;
  ev.preventDefault();
  const zone = ev.target.closest(".zg");
  if (zone) {
    const z = zones[+zone.dataset.i];
    if (z.manuel) zones.splice(+zone.dataset.i, 1); else z.actif = !z.actif;
    dessinerZones();
    return;
  }
  const r = vuePage.getBoundingClientRect();
  const bloc = document.createElement("div"); bloc.className = "zg trace"; vuePage.append(bloc);
  trace = {vuePage, r, bloc, x: (ev.clientX - r.left) / r.width, y: (ev.clientY - r.top) / r.height, cadre: null};
});
document.addEventListener("mousemove", ev => {
  if (!trace) return;
  const borne = v => Math.max(0, Math.min(1, v));
  const x = borne((ev.clientX - trace.r.left) / trace.r.width), y = borne((ev.clientY - trace.r.top) / trace.r.height);
  const g = Math.min(x, trace.x), h = Math.min(y, trace.y), d = Math.max(x, trace.x), b = Math.max(y, trace.y);
  trace.cadre = [g, h, d, b];
  trace.bloc.style.cssText = `left:${g * 100}%;top:${h * 100}%;width:${(d - g) * 100}%;height:${(b - h) * 100}%`;
});
document.addEventListener("mouseup", () => {
  if (!trace) return;
  const {cadre, vuePage, bloc} = trace;
  trace = null; bloc.remove();
  // Un simple clic n'ajoute rien : il faut un rectangle d'une taille visible.
  if (cadre && cadre[2] - cadre[0] > 0.01 && cadre[3] - cadre[1] > 0.004)
    zones.push({page: +vuePage.dataset.page, cadre, actif: true, manuel: true});
  dessinerZones();
});

// ---------- exporter ----------
const mode = () => traitement;
// Aperçu local, sans rien écrire dans la table : les numéros des jetons sont attribués à l'export.
function apercuExport() {
  const caviar = mode() === "caviardage", avant = $("avant"), apres = $("apres");
  avant.textContent = ""; apres.textContent = "";
  let position = 0;
  passages.forEach(p => {
    const entre = texte.slice(position, p.debut), v = valeur(p);
    avant.append(entre); apres.append(entre);
    if (p.actif) {
      const m = document.createElement("mark"); m.className = famille(p.type); m.textContent = v; avant.append(m);
      const s = document.createElement("span");
      if (caviar) { s.className = "noir"; s.textContent = v; }
      else { s.className = "jeton"; s.textContent = p.type === "SECRET" ? "[SECRET_SUPPRIMÉ]" : `${p.type}_n`; }
      apres.append(s);
    } else { avant.append(v); apres.append(v); }
    position = p.fin;
  });
  avant.append(texte.slice(position)); apres.append(texte.slice(position));
  $("titre-apres").textContent = caviar ? "Ce que le destinataire recevra" : "Ce que l'IA recevra";
  $("apercu-note").textContent = caviar
    ? (estPdf ? "Dans le PDF, chaque donnée est couverte d'un rectangle noir." : "Chaque donnée devient une marque █████.")
    : "Chaque jeton reçoit son numéro à l'export, par exemple PERSONNE_12. Une même valeur garde toujours le même jeton.";
}
function decrireExport() {
  const caviar = mode() === "caviardage", ext = (fichier.match(/\.[^.]+$/) || [""])[0].toLowerCase();
  $("export-titre").textContent = caviar ? "Exporter le document caviardé" : "Exporter pour l'IA";
  $("export-mode-nom").textContent = caviar ? "Caviardage" : "Pseudonymisation";
  $("export-mode-tag").textContent = caviar ? "Définitif" : "Réversible";
  $("export-mode-tag").className = "etiquette " + (caviar ? "alerte" : "bon");
  $("export-mode-desc").textContent = caviar
    ? "Les données sont retirées pour de bon. Aucun retour possible : gardez l'original à part."
    : "Chaque donnée devient un jeton. Celodata remettra les vraies valeurs dans la réponse.";
  $("btn-changer-traitement").textContent = caviar ? "Basculer vers la pseudonymisation" : "Basculer vers le caviardage";
  let produit;
  const z = zones.filter(x => x.actif).length;
  if (estPdf) produit = caviar
    ? "Le fichier enregistré sera un PDF fait d'images : des rectangles noirs couvrent les données, et il ne reste aucun texte dessous."
      + (z ? ` ${pluriel(z, "zone")} sans texte lu (tampon, signature, passage illisible) ${z > 1 ? "seront aussi recouvertes" : "sera aussi recouverte"} : voir « Pages » à l'étape Vérifier.` : "")
    : "Le fichier enregistré sera un Word neuf avec le texte pseudonymisé. La mise en page, les images, les tampons et les signatures du PDF n'y sont pas repris.";
  else if (formate) produit = `Le fichier enregistré sera un ${ext === ".xlsx" ? "Excel" : "Word"} ${caviar ? "caviardé" : "pseudonymisé"}, mise en forme gardée, propriétés (auteur, société) vidées.`;
  else produit = `Le fichier enregistré sera un fichier texte ${caviar ? "caviardé" : "pseudonymisé"}.`;
  $("export-aide").textContent = produit;
  $("btn-filtrer").textContent = caviar ? "Copier le texte" : "Copier pour l'IA";
  const libelle = estPdf ? (caviar ? "le PDF" : "le Word") : formate ? (ext === ".xlsx" ? "l'Excel" : "le Word") : "le fichier";
  $("btn-enregistrer").textContent = `Enregistrer ${libelle}`;
  $("filtre-erreur").textContent = ""; $("export-ok").textContent = ""; $("bloc-filtre").hidden = true;
  apercuExport();
}
$("btn-changer-traitement").addEventListener("click", () => {
  choisirTraitement(traitement === "caviardage" ? "pseudonymisation" : "caviardage");
  decrireExport();
});
$("btn-continuer").addEventListener("click", () => {
  const n = passages.filter(p => p.actif).length, v = passages.filter(p => p.suggestion && !p.actif).length;
  $("export-bilan").textContent = `${fichier || "Texte collé"} : ${pluriel(n, "passage")} masqué${n > 1 ? "s" : ""}`
    + (v ? `, ${pluriel(v, "fonction")} à vérifier laissée${v > 1 ? "s" : ""} en clair` : "") + ".";
  decrireExport();
  vue("exporter");
});
$("btn-retour-verif").addEventListener("click", () => vue("verifier"));
$("btn-nouveau").addEventListener("click", vider);
const retenus = () => passages.filter(p => p.actif).map(({debut, fin, type}) => ({debut, fin, type}));
// Les passages d'une catégorie laissée en clair ne sont pas des corrections : ils ne sont pas retenus.
const retires = () => [...new Set(passages.filter(p => !p.actif && !p.suggestion && !p.hors).map(valeur))];
$("btn-filtrer").addEventListener("click", async () => {
  $("filtre-erreur").textContent = ""; $("export-ok").textContent = "";
  const r = await api().filtrer(texte, retenus(), retires(), fichier, mode());
  if (!r.ok) { $("filtre-erreur").textContent = r.erreur; return; }
  $("filtre").textContent = r.texte; $("bloc-filtre").hidden = false;
  if (await copier(r.texte)) annoncer(mode() === "caviardage" ? "Texte caviardé copié" : "Texte copié, prêt à coller dans l'IA");
  else $("filtre-erreur").textContent = "Copie impossible : sélectionnez le texte ci-dessous.";
  $("bloc-filtre").scrollIntoView({behavior: "smooth", block: "nearest"});
});
$("btn-enregistrer").addEventListener("click", async () => {
  $("filtre-erreur").textContent = ""; $("export-ok").textContent = "";
  $("btn-enregistrer").disabled = true;
  try {
    const aCouvrir = estPdf ? zones.filter(z => z.actif).map(({page, cadre}) => ({page, cadre})) : null;
    const r = await api().enregistrer_filtre(texte, retenus(), retires(), mode(), fichier, aCouvrir);
    if (r.annule) return;
    if (!r.ok) { $("filtre-erreur").textContent = r.erreur; return; }
    $("export-ok").textContent = `Fichier enregistré : ${r.chemin}`
      + (r.avertissements.length ? ` Attention : ${r.avertissements.join(", ")}.` : "");
    annoncer("Fichier enregistré");
    suivreSurveillance();
  } catch (e) {
    $("filtre-erreur").textContent = "Erreur : " + e;
  } finally {
    $("btn-enregistrer").disabled = false;
  }
});

// ---------- dossier surveillé ----------
function ouvrirSurveille(d) {
  return async () => {
    const doc = await api().ouvrir_surveille(d.id);
    onglet("filtrer");
    charger(doc);
  };
}
function afficherSurveillance(r) {
  const actif = !!r.dossier;
  $("btn-arreter").hidden = !actif;
  $("btn-surveiller").textContent = actif ? "Changer de dossier" : "Choisir un dossier";
  $("btn-surveiller").className = actif ? "second" : "action";
  const chemin = $("surveille-chemin");
  chemin.textContent = "";
  if (actif) {
    const c = document.createElement("code"); c.textContent = r.dossier;
    chemin.append(c, " ", etiquette("Surveillé", "bon"));
  } else { const s = document.createElement("span"); s.className = "info"; s.textContent = "Aucun dossier surveillé."; chemin.append(s); }
  $("surveille-bloc").hidden = !actif;
  const prets = r.documents.filter(d => d.etat === "pret");
  $("pastille").hidden = !prets.length; $("pastille").textContent = prets.length;
  const corps = $("surveille-lignes");
  corps.textContent = "";
  r.documents.forEach(d => {
    const tr = document.createElement("tr");
    cellule(tr, d.nom);
    if (d.etat === "erreur") cellule(tr, d.erreur, "erreur");
    else if (d.etat === "pret") cellule(tr, etiquette((d.pages_scannees ? "Scan à relire · " : "Prêt · ") + pluriel(d.masques, "passage"), d.pages_scannees ? "scan" : "pret"));
    else cellule(tr, etiquette(d.etat === "traite" ? "Exporté" : "Analyse en cours…", d.etat === "traite" ? "bon" : ""));
    const fin = cellule(tr, "", "nombre");
    if (d.etat === "pret" || d.etat === "traite") {
      const b = document.createElement("button");
      b.className = d.etat === "pret" ? "action" : "second";
      b.textContent = d.etat === "pret" ? "Vérifier" : "Rouvrir";
      b.setAttribute("aria-label", `${b.textContent} ${d.nom}`);
      b.addEventListener("click", ouvrirSurveille(d));
      fin.append(b);
    }
    corps.append(tr);
  });
  if (!r.documents.length) ligneVide(corps, 3, "Le dossier est vide pour l'instant. Déposez-y un document : il apparaîtra ici, prêt à vérifier.");
  // Les documents prêts remontent aussi sur l'écran de dépôt.
  const recents = $("recents-liste");
  recents.textContent = "";
  prets.forEach(d => {
    const ligne = document.createElement("div"); ligne.className = "recent";
    const corpsLigne = document.createElement("div");
    const nom = document.createElement("strong"); nom.textContent = d.nom;
    const detail = document.createElement("span"); detail.className = "info";
    detail.textContent = `${pluriel(d.masques, "passage")} repéré${d.masques > 1 ? "s" : ""}` + (d.pages_scannees ? " · scan à relire en entier" : "");
    corpsLigne.append(nom, detail);
    const b = document.createElement("button"); b.className = "second"; b.textContent = "Vérifier";
    b.setAttribute("aria-label", `Vérifier ${d.nom}`);
    b.addEventListener("click", ouvrirSurveille(d));
    ligne.append(corpsLigne, b); recents.append(ligne);
  });
  $("recents").hidden = !prets.length;
}
let surveillanceVue = "";
async function suivreSurveillance() {
  const r = await api().surveillance();
  const image = JSON.stringify(r);
  if (image === surveillanceVue) return;   // rien de neuf : l'écran n'est pas redessiné
  surveillanceVue = image;
  afficherSurveillance(r);
}
$("btn-surveiller").addEventListener("click", async () => { const r = await api().choisir_dossier_surveille(); if (!r.annule) suivreSurveillance(); });
$("btn-arreter").addEventListener("click", async () => { await api().arreter_surveillance(); suivreSurveillance(); });

// ---------- règles du projet ----------
const GENRES = {terme: "Toujours masquer", motif: "Motif", jamais: "Ne jamais masquer"};
const AIDES = {
  terme: "Le terme est masqué partout où il apparaît en entier, majuscules ou non.",
  motif: "Expression régulière. Exemple : TCK-\\d{6} masque les références du type TCK-204815.",
  jamais: "Le terme n'est plus proposé, même si un détecteur le trouve. Les majuscules comptent.",
};
const EXEMPLES = {terme: "Projet Hélios, nom d'un client…", motif: "TCK-\\d{6}", jamais: "Service client"};
$("regle-type").innerHTML = $("ajout-type").innerHTML;
function majGenre() {
  const g = $("regle-genre").value;
  document.querySelectorAll("#genres button").forEach(b => b.setAttribute("aria-pressed", b.dataset.g === g));
  $("regle-type").hidden = g === "jamais";
  $("regle-aide").textContent = AIDES[g];
  $("regle-texte").placeholder = EXEMPLES[g];
}
document.querySelectorAll("#genres button").forEach(b => b.addEventListener("click", () => { $("regle-genre").value = b.dataset.g; majGenre(); }));
$("regle-genre").addEventListener("change", majGenre);
majGenre();
async function chargerRegles() {
  const r = await api().regles();
  const corps = $("regle-lignes");
  corps.textContent = "";
  const ligne = (genre, contenu, type, retirer) => {
    const tr = document.createElement("tr");
    cellule(tr, etiquette(GENRES[genre], genre === "jamais" ? "" : "pret"));
    const code = document.createElement("code"); code.textContent = contenu;
    cellule(tr, code); cellule(tr, type ? nomType(type) : "");
    const b = document.createElement("button");
    b.className = "lien"; b.textContent = "Retirer"; b.setAttribute("aria-label", "Retirer la règle " + contenu);
    b.addEventListener("click", async () => { await retirer(); chargerRegles(); annoncer("Règle retirée"); });
    cellule(tr, b, "nombre");
    corps.append(tr);
  };
  r.regles.forEach(x => ligne(x.genre, x.texte, x.type, () => api().supprimer_regle(x.id)));
  r.jamais.forEach(t => ligne("jamais", t, "", () => api().ne_plus_ignorer(t)));
  if (!r.regles.length && !r.jamais.length) ligneVide(corps, 4, "Aucune règle pour l'instant. Ajoutez un nom de projet ou de client à masquer partout, ou laissez un passage en clair à la vérification.");
}
$("regle-form").addEventListener("submit", async ev => {
  ev.preventDefault();
  $("regle-erreur").textContent = "";
  const r = await api().ajouter_regle($("regle-genre").value, $("regle-texte").value, $("regle-type").value);
  if (!r.ok) { $("regle-erreur").textContent = r.erreur; return; }
  $("regle-texte").value = "";
  chargerRegles();
  annoncer("Règle ajoutée");
});

// ---------- journal ----------
const SOURCES = {regles: "règles", projet: "règles du projet", table: "table", manuel: "ajout à la main"};
const decompte = (o, noms) => Object.entries(o || {}).map(([k, n]) => `${noms ? (noms[k] || k) : nomType(k)} ${n}`).join(", ");
function quand(iso) {
  const d = new Date(iso), jour = x => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const ecart = Math.round((jour(new Date()) - jour(d)) / 864e5);
  const heure = d.toLocaleTimeString("fr-FR", {hour: "2-digit", minute: "2-digit"});
  if (ecart === 0) return `Aujourd'hui, ${heure}`;
  if (ecart === 1) return `Hier, ${heure}`;
  return d.toLocaleString("fr-FR", {day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit"});
}
async function chargerJournal() {
  const lignes = await api().journal();
  const corps = $("journal-lignes");
  corps.textContent = "";
  lignes.forEach(l => {
    const tr = document.createElement("tr");
    cellule(tr, quand(l.date)).title = new Date(l.date).toLocaleString("fr-FR");
    const filtrage = l.action === "filtrage";
    const caviar = l.traitement === "caviardage";
    cellule(tr, etiquette(filtrage
      ? (caviar ? "Caviardage" : "Pseudonymisation") + (l.mode === "lot" ? " (dossier)" : l.mode === "passerelle" ? " (passerelle)" : "")
      : "Restauration", filtrage ? (caviar ? "alerte" : "pret") : "bon"));
    cellule(tr, l.fichier || "Texte collé");
    cellule(tr, filtrage
      ? (decompte(l.par_type) || "Rien à masquer")
      : (l.inconnus || l.approximatifs
        ? `${pluriel(l.inconnus, "jeton")} inconnu${l.inconnus > 1 ? "s" : ""}, ${l.approximatifs} approché${l.approximatifs > 1 ? "s" : ""}`
        : "Tous les jetons retrouvés"));
    cellule(tr, filtrage ? decompte(l.par_source, SOURCES) + (l.score_min == null ? "" : ` · score mini ${l.score_min}`) : "");
    corps.append(tr);
  });
  if (!lignes.length) ligneVide(corps, 5, "Aucun traitement pour l'instant. Chaque document protégé ou restauré ajoutera une ligne ici.");
}
$("btn-exporter-journal").addEventListener("click", async () => {
  const message = $("journal-message");
  message.textContent = ""; message.className = "message";
  const r = await api().exporter_journal();
  if (r.annule) return;
  if (!r.ok) { message.textContent = r.erreur; return; }
  message.className = "message bon";
  message.textContent = `Journal enregistré (${pluriel(r.lignes, "ligne")}) : ${r.chemin}`;
  annoncer("Journal exporté");
});

// ---------- restauration ----------
$("btn-restaurer").addEventListener("click", async () => {
  const reponse = $("reponse").value;
  if (!reponse.trim()) { $("reponse").focus(); return; }
  const r = await api().restaurer(reponse);
  $("restaure").textContent = r.texte; $("bloc-restaure").hidden = false; $("restaure-vide").hidden = true;
  $("btn-copier-restaure").hidden = false; $("info-copie").textContent = ""; $("info-restaure").textContent = "";
  const alertes = $("alertes-restaure");
  alertes.textContent = "";
  const bloc = (titre, liste) => {
    if (!liste.length) return;
    const p = document.createElement("div"); p.textContent = titre;
    const ul = document.createElement("ul"); ul.className = "liste";
    liste.forEach(x => { const li = document.createElement("li"); li.textContent = x; ul.append(li); });
    alertes.append(p, ul);
  };
  bloc("Jetons absents de la table, laissés tels quels (l'IA les a peut-être inventés) :", r.inconnus);
  bloc("Jetons reconnus sous une forme approchée, à vérifier :", r.approximatifs);
  annoncer("Réponse restaurée");
});
$("btn-restaurer-fichier").addEventListener("click", async () => {
  const r = await api().restaurer_fichier();
  if (r.annule) return;
  $("bloc-restaure").hidden = true; $("restaure-vide").hidden = false; $("btn-copier-restaure").hidden = true;
  if (!r.ok) { $("info-restaure").textContent = r.erreur; return; }
  const n = r.inconnus.length, a = r.approximatifs.length;
  $("info-restaure").textContent = `Fichier restauré enregistré : ${r.chemin}`
    + (n ? ` ${pluriel(n, "jeton")} absent${n > 1 ? "s" : ""} de la table, laissé${n > 1 ? "s" : ""} tel${n > 1 ? "s" : ""} quel${n > 1 ? "s" : ""}.` : "")
    + (a ? ` ${pluriel(a, "jeton")} reconnu${a > 1 ? "s" : ""} sous une forme approchée, à vérifier.` : "");
  annoncer("Fichier restauré enregistré");
});
$("btn-copier-restaure").addEventListener("click", async () => {
  if (await copier($("restaure").textContent)) annoncer("Réponse copiée");
  else $("info-copie").textContent = "Copie impossible : sélectionnez le texte.";
});

if (window.pywebview && window.pywebview.api) demarrer();
else window.addEventListener("pywebviewready", demarrer);
