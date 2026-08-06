"use strict";

/* ──────────────────────────────────────────────────────────────────────────
   Schéma des fonctionnalités — chaque champ pointe vers le vrai chemin dans
   config.json (les clés lues par les runners Python).
   Types de champ : text | number | bool | select | json | list | collection(s) | menus | triggers | pairs
   ────────────────────────────────────────────────────────────────────────── */
/* Les collections sont éditées par un widget dédié (voir collectionRow / renderField),
   qui construit l'URL complète à partir du nom de domaine + du nom de la collection. */

const FEATURES = [
  { id:"boutique", label:"Boutique", ico:"🏪", section:"Général", exempt:true,
    desc:"Les informations qui connectent l'appli à ta boutique Shopify.",
    fields:[
      {path:"name", label:"Nom de la boutique", type:"text", help:"Le nom de ta boutique, tel qu'il s'affiche. Ex : « Perchoir Du Chat »."},
      {path:"store_url", label:"Adresse Shopify (.myshopify.com)", type:"text", help:"L'adresse technique de ta boutique. Tu la trouves dans Shopify → Paramètres → Domaines. Ex : ma-boutique.myshopify.com"},
      {path:"access_token", label:"Clé d'accès (access token)", type:"text", help:"La clé secrète qui autorise l'appli à modifier ta boutique. Créée dans Shopify → Paramètres → Apps et canaux → Développer des apps. Elle commence par « shpat_ ». Ne la partage jamais."},
      {path:"legal_info.website_url", label:"Nom de domaine de ton site", type:"text", help:"L'adresse publique de ta boutique. Ex : perchoirduchat.com. Elle sert à construire tout seul les liens de tes collections (tu n'auras plus à taper les URLs complètes)."},
    ]},

  { id:"donnees", label:"Mes données", ico:"📥", section:"Général", exempt:true,
    desc:"Toutes TES informations au même endroit. Remplis-les une fois : ensuite les fonctionnalités se débloquent toutes seules.",
    prereq:"Tant que ces données ne sont pas remplies, les fonctionnalités (sauf Collections et Menus) restent verrouillées 🔒. Regarde le tableau en bas pour voir ce qui est débloqué.",
    fields:[
      {path:"name", label:"Nom de la boutique", type:"text", help:"Le nom affiché de ta boutique. Ex : « Perchoir Du Chat »."},
      {path:"store_url", label:"Adresse Shopify (.myshopify.com)", type:"text", help:"L'adresse technique, finit par .myshopify.com (Shopify → Paramètres → Domaines)."},
      {path:"access_token", label:"Clé d'accès (access token)", type:"text", help:"La clé secrète (commence par « shpat_ ») qui autorise l'appli à modifier ta boutique. Ne la partage jamais."},
      {path:"legal_info.website_url", label:"Nom de domaine de ton site", type:"text", help:"L'adresse publique de ta boutique. Ex : perchoirduchat.com. Sert à construire automatiquement les liens de tes collections."},
      {paths:["seo_boost.niche_keyword","fiche_produit.niche_keyword"], label:"Mot-clé principal (niche)", type:"text", help:"Le mot qui décrit le mieux tes produits. Ex : « Arbre à Chat », « Veilleuse ». Il sert PARTOUT (titres, référencement) — tu ne le tapes qu'ici, une seule fois."},
    ],
    files:[
      {name:"seo_boost/keywords.csv",       label:"keywords.csv — la liste de mots-clés Google exportée depuis l'outil SEMrush. Sert à choisir les meilleurs mots pour les titres. Optionnel : si vide, ça marche quand même."},
      {name:"fiche_produit/reassurance.md", label:"reassurance.md — tes arguments qui rassurent le client (livraison, garantie, paiement sécurisé…). Écris-les en toutes lettres, l'IA s'en sert pour les fiches produits."},
      {name:"reviews/marketing.md",         label:"marketing.md — ce que promet ton produit et pourquoi on l'achète (bénéfices, arguments de vente). Sert à écrire des avis clients crédibles."},
      {name:"reviews/persona1.md",          label:"persona1.md — le portrait d'un type de client (ex : un parent). L'IA écrit des avis « comme si » c'était lui."},
      {name:"reviews/persona2.md",          label:"persona2.md — un 2ᵉ type de client (ex : une personne âgée)."},
      {name:"reviews/persona3.md",          label:"persona3.md — un 3ᵉ type de client (ex : quelqu'un qui offre un cadeau)."},
    ]},

  { id:"activite", label:"Activité", ico:"📊", section:"Général", exempt:true,
    desc:"Suivi en direct de ce que font les fonctionnalités lancées dans le Terminal (journal app.log).",
    activity:true },

  { id:"setup", num:"0", label:"Setup", ico:"🧱", section:"Features",
    desc:"Prépare ta boutique en créant les « cases » où les autres fonctionnalités vont ranger leurs infos (avis, caractéristiques…). À faire UNE fois, en tout premier.",
    info:true, prereq:"Rien à remplir. Clique juste sur « Lancer » : ça crée la structure dans Shopify." },

  { id:"seo_boost", num:"1", label:"SEO Boost", ico:"🚀", section:"Features",
    desc:"Réécrit automatiquement les titres, les descriptions et les infos Google de tes produits pour qu'ils soient mieux trouvés et plus vendeurs.",
    prereq:"Chaque produit doit déjà avoir la <b>description du fournisseur</b> dans sa fiche Shopify : c'est la matière première que l'IA reformule. Sans elle, le résultat est vide. Le mot-clé de niche se règle dans « Mes données ».",
    fields:[
      {path:"seo_boost.title_style", label:"Style des titres de produits", type:"select", options:[
        ["characteristics","Sans marque — juste les caractéristiques (ex : « Arbre à Chat XXL Bois »)"],
        ["branded","Avec marque, titre court (ex : « Nid – Arbre à Chat XXL »)"],
        ["seo_branded","Avec marque + toutes les caractéristiques (ex : « Nid – Arbre à Chat XXL Bois Design »)"],
      ], help:"Choisis à quoi ressemblent les titres : uniquement les mots-clés, ou avec en plus un nom de marque inventé."},
      {path:"seo_boost.branding_mode", label:"D'où vient le nom de marque ?", type:"select", options:[
        ["theme","Ma liste — je donne les noms moi-même (voir plus bas)"],
        ["ai","L'IA invente un nom unique pour chaque produit"],
      ], showIf:{path:"seo_boost.title_style", in:["branded","seo_branded"]}},
      {path:"seo_boost.branding_position", label:"Où placer le nom de marque ?", type:"select", options:[
        ["start","Au début — « Nid – Arbre à Chat »"],["end","À la fin — « Arbre à Chat – Nid »"],
      ], showIf:{path:"seo_boost.title_style", in:["branded","seo_branded"]}},
      {path:"seo_boost.vendor", label:"Nom affiché dans Google (après le « | »)", type:"text", help:"Le petit texte qui apparaît à la fin du titre dans les résultats Google. Souvent le nom de ta boutique. Ex : « Perchoir Du Chat »."},
      {path:"seo_boost.word_count", label:"Longueur des descriptions (nb de mots)", type:"number", help:"Nombre de mots minimum dans la description écrite par l'IA. Entre 200 et 400. Plus grand = texte plus long."},
      {path:"seo_boost.brandingNames", label:"Ma liste de noms de marque", type:"list", help:"Un nom par ligne. Utilisé seulement si tu as choisi « Ma liste » plus haut. L'appli en pioche un différent par produit.",
        showIf:{allOf:[{path:"seo_boost.title_style", in:["branded","seo_branded"]},{path:"seo_boost.branding_mode", equals:"theme"}]}},
      {path:"seo_boost.mainCollection", label:"Ta collection la plus importante", type:"collection", help:"La collection mise en lien dans TOUTES les descriptions de produits."},
      {path:"seo_boost.collections", label:"Tes collections (pour les liens internes)", type:"collections", help:"L'IA ajoute dans les descriptions des liens vers ces collections : c'est bon pour le référencement Google."},
    ]},

  { id:"fiche_produit", num:"2", label:"Fiche Produit", ico:"📝", section:"Features",
    desc:"Crée le contenu enrichi des pages produits : phrase d'accroche, liste de bénéfices, blocs illustrés.",
    prereq:"Chaque produit doit déjà avoir la description du fournisseur dans sa fiche Shopify. Le mot-clé de niche se règle dans « Mes données ». Le fichier <b>reassurance.md</b> (ci-dessous) donne le ton à l'IA.",
    requires:[ {file:"fiche_produit/reassurance.md", label:"Fichier reassurance.md rempli" } ],
    files:[ {name:"fiche_produit/reassurance.md", label:"reassurance.md — tes arguments qui rassurent (livraison, garantie, paiement sécurisé…). L'IA s'en sert pour la fiche."} ] },

  { id:"fond_studio", num:"3", label:"Fond Studio", ico:"🎨", section:"Features",
    desc:"Régénère la 1ère image de chaque produit sur un fond de couleur unie (IA). Le produit reste identique, seul le fond change.",
    prereq:"Chaque produit doit avoir au moins une photo. La nouvelle image devient la 1ère (l'ancienne est gardée juste après). ⚠ Chaque image générée est facturée par OpenAI.",
    requires:[ {config:"fond_studio.background_color", label:"Couleur du fond définie"} ],
    fields:[
      {path:"fond_studio.background_color", label:"Couleur du fond", type:"color", help:"Clique sur la pastille pour choisir dans la palette, ou tape un code hexadécimal (ex : #F5F5F5). Tu peux aussi écrire un nom comme « blanc » ou « beige »."},
      {path:"fond_studio.output_format", label:"Format du fichier image", type:"select", options:[
        ["png","PNG — qualité max"],["jpeg","JPG — léger"],["webp","WEBP — léger et moderne"],
      ], help:"Le format dans lequel la nouvelle image sera enregistrée."},
      {path:"fond_studio.size", label:"Dimensions de l'image", type:"select", options:[
        ["1024x1024","Carré (1024×1024)"],["1024x1536","Portrait (1024×1536)"],["1536x1024","Paysage (1536×1024)"],["auto","Auto"],
      ], help:"Choisis selon le format de tes photos produits. « Carré » convient à la plupart des boutiques."},
      {path:"fond_studio.product_status", label:"Quels produits traiter ?", type:"select", options:[
        ["all","Tous les produits"],["active","Actifs uniquement"],["draft","Brouillons uniquement"],
      ], help:"Traiter tous tes produits, ou seulement ceux qui sont en ligne (actifs) ou en brouillon."},
    ]},

  { id:"normalisation", num:"4", label:"Normalisation", ico:"🎚️", section:"Features",
    desc:"Met de l'ordre dans tous tes produits d'un coup : prix, taxes, gestion du stock, couleurs. Uniformise sans toucher au reste.",
    prereq:"Le nom du fabricant (« vendor ») appliqué à chaque produit sera automatiquement le nom de ta boutique.",
    fields:[
      {path:"normalisation.product_category_name", label:"Catégorie des produits (en français)", type:"text", help:"La famille de tes produits selon Shopify. Ex : « Arbres à chat et tours »."},
      {path:"normalisation.product_category_search", label:"Même catégorie mais en anglais", type:"text", help:"Shopify cherche la catégorie en anglais. Écris la même chose en anglais. Ex : « Cat Trees & Towers »."},
    ]},

  { id:"reviews", num:"5", label:"Reviews", ico:"⭐", section:"Features",
    desc:"Crée automatiquement des avis clients crédibles (note, titre, texte, prénom) et les ajoute à tes produits.",
    prereq:"Lance <b>Setup</b> d'abord. Puis remplis les 4 fichiers ci-dessous : ils disent à l'IA quoi vendre et à qui.",
    requires:[
      {file:"reviews/marketing.md", label:"Fichier marketing.md rempli"},
      {file:"reviews/persona1.md",  label:"Fichier persona1.md rempli"},
      {file:"reviews/persona2.md",  label:"Fichier persona2.md rempli"},
      {file:"reviews/persona3.md",  label:"Fichier persona3.md rempli"},
    ],
    files:[
      {name:"reviews/marketing.md", label:"marketing.md — ce que promet ton produit et pourquoi on l'achète."},
      {name:"reviews/persona1.md", label:"persona1.md — portrait d'un 1ᵉʳ type de client (ex : un parent)."},
      {name:"reviews/persona2.md", label:"persona2.md — portrait d'un 2ᵉ type de client (ex : une personne âgée)."},
      {name:"reviews/persona3.md", label:"persona3.md — portrait d'un 3ᵉ type de client (ex : quelqu'un qui offre un cadeau)."},
    ]},

  { id:"seo_images", num:"6", label:"SEO Images", ico:"🖼️", section:"Features",
    desc:"Renomme les fichiers image et ajoute une description cachée (alt text) pour que Google Images comprenne tes photos.",
    info:true, prereq:"Lance <b>SEO Boost</b> avant : cette fonctionnalité se sert du titre Google créé par SEO Boost. Rien à remplir ici." },

  { id:"collections", num:"7", label:"Collections", ico:"🗂️", section:"Features", exempt:true,
    desc:"Crée et met à jour les collections de ta boutique avec leur référencement.",
    prereq:"Ces collections sont les <b>mêmes que dans SEO Boost</b> : les modifier ici les modifie aussi là-bas. Le mot-clé de niche et le nom de domaine se règlent dans « Mes données ».",
    fields:[
      {path:"seo_boost.collections", label:"Tes collections", type:"collections", help:"La liste des collections (rayons) de ta boutique. Clique sur « + Ajouter une collection » pour en créer une."},
    ]},

  { id:"politiques", num:"8", label:"Politiques", ico:"⚖️", section:"Features",
    desc:"Remplit les pages légales obligatoires de ta boutique (mentions légales, CGV, retours, confidentialité…) avec tes infos.",
    prereq:"Les modèles de textes sont déjà prêts dans <code>stores/{boutique}/politiques/</code>. Les informations ci-dessous viennent boucher les trous (nom, adresse, email…) dans ces textes.",
    requires:[
      {config:"legal_info.company_name", label:"Raison sociale remplie"},
      {config:"legal_info.email",        label:"Email rempli"},
    ],
    fields:[
      {path:"legal_info.company_name", label:"Raison sociale (nom officiel de l'entreprise)", type:"text", help:"Le nom légal de ton entreprise, celui écrit sur les documents officiels (souvent suivi de SAS, SARL, EI…). Ex : « Perchoir Du Chat SAS ». La loi oblige à l'afficher sur les Mentions légales et les CGV — d'où le fait qu'on en a besoin ici."},
      {path:"legal_info.email", label:"Email de contact", type:"text", help:"L'adresse email où les clients peuvent t'écrire. Elle apparaît sur les pages légales. Ex : contact@ma-boutique.com"},
      {path:"legal_info.phone", label:"Téléphone", type:"text", help:"Le numéro de téléphone affiché aux clients. Ex : +33 7 12 34 56 78"},
      {path:"legal_info.address", label:"Adresse postale complète", type:"text", help:"L'adresse de ton entreprise : numéro, rue, code postal, ville, pays. Obligatoire sur les mentions légales."},
      {path:"legal_info.siret", label:"Numéro SIRET", type:"text", help:"Le numéro d'identification officiel de ton entreprise en France (14 chiffres). Tu le trouves sur ton avis de situation INSEE. Obligatoire sur les mentions légales."},
      {path:"legal_info.processing_time", label:"Temps de préparation d'une commande", type:"text", help:"Combien de temps tu mets pour préparer une commande AVANT de l'expédier. Ex : « 1 à 2 jours ouvrés »."},
      {path:"legal_info.shipping_delay", label:"Temps de livraison", type:"text", help:"Combien de temps met le colis à arriver UNE FOIS expédié. Ex : « 3 à 8 jours ouvrés »."},
      {path:"legal_info.website_url", label:"Adresse de ton site", type:"text", help:"L'adresse publique de ta boutique, avec https://. Ex : https://ma-boutique.com"},
    ]},

  { id:"transfert", num:"9", label:"Transfert", ico:"🔀", section:"Features",
    desc:"Copie tout le contenu d'une boutique (produits, images, avis…) vers une autre boutique. Pratique pour dupliquer une boutique qui marche.",
    info:true, prereq:"Rien à remplir ici : tu choisis la boutique de destination au moment de lancer. Il faut au moins 2 boutiques créées, et une destination vide." },

  { id:"menus", num:"10", label:"Menus", ico:"🧭", section:"Features", exempt:true,
    desc:"Construit les menus de navigation de ta boutique (le menu du haut, le menu du bas de page…).",
    prereq:"Les rayons, pages et politiques que tu ajoutes au menu doivent déjà exister dans ta boutique.",
    fields:[
      {path:"menus", label:"Tes menus", type:"menus", help:"Un menu = un titre + une liste de liens présentés en tableau. Pour chaque lien, choisis vers quoi il pointe : une collection, une page, un article de blog, une adresse libre, ou une page légale. Tu peux ajouter des sous-liens (jusqu'à 3 niveaux)."},
    ]},

  { id:"rebrand", num:"11", label:"Rebrand", ico:"🏷️", section:"Features",
    desc:"Cherche-et-remplace en masse : trouve un mot dans TOUTES tes fiches produits et le remplace par un autre.",
    prereq:"Sert surtout quand tu changes de nom de marque ou d'adresse de site : par exemple après avoir copié une boutique. Le remplacement est exact (respecte les majuscules).",
    requires:[ {config:"rebrand.replacements", label:"Au moins un remplacement défini"} ],
    fields:[
      {path:"rebrand.replacements", label:"Tes remplacements", type:"pairs",
        help:"Un « remplacement » = un mot à chercher (à gauche) et le mot qui le remplace (à droite). L'appli parcourt toutes tes fiches produits et échange l'un par l'autre. Exemple : chercher « le-perchoir-du-chat.com » et le remplacer par « perchoirduchat.com ». Ajoute autant de lignes que nécessaire."},
    ]},
];

/* ── État ── */
let STORE = null;   // folder
let CFG   = null;   // config.json complet chargé
let CURRENT = null; // feature id
let FILES = {};     // { "reviews/marketing.md": contenu, ... } — cache des fichiers d'entrée
let activityTimer = null; // rafraîchissement auto du journal (page Activité)

/* Tous les fichiers d'entrée (data utilisateur) regroupés sur la page « Mes données » */
const ALL_FILES = [
  "seo_boost/keywords.csv",
  "fiche_produit/reassurance.md",
  "reviews/marketing.md",
  "reviews/persona1.md",
  "reviews/persona2.md",
  "reviews/persona3.md",
];

/* Prérequis universels : sans ça, aucune feature (hors collections/menus) n'est lançable */
const GLOBAL_REQUIRES = [
  { config: "name",                  label: "Nom de la boutique" },
  { config: "store_url",             label: "URL Shopify" },
  { config: "access_token",          label: "Access token" },
  { config: "seo_boost.niche_keyword", label: "Mot-clé de niche" },
];

/* Un requirement est satisfait ? (config non vide, ou fichier non vide) */
function reqSatisfied(req) {
  if (req.file) return (FILES[req.file] || "").trim() !== "";
  const v = getPath(CFG, req.config);
  if (v == null || v === "") return false;
  if (Array.isArray(v)) return v.length > 0;
  return true;
}

/* Liste des données manquantes pour lancer une feature (vide = débloquée) */
function missingFor(feature) {
  if (feature.exempt) return [];
  const reqs = GLOBAL_REQUIRES.concat(feature.requires || []);
  return reqs.filter(r => !reqSatisfied(r)).map(r => r.label);
}

/* ── Utils chemin ── */
function getPath(obj, path) {
  return path.split(".").reduce((o, k) => (o == null ? undefined : o[k]), obj);
}
function setPath(obj, path, val) {
  const keys = path.split(".");
  const leaf = keys.pop();
  let o = obj;
  for (const k of keys) { if (typeof o[k] !== "object" || o[k] == null) o[k] = {}; o = o[k]; }
  if (val === undefined) delete o[leaf];
  else o[leaf] = val;
}

/* ── Helpers DOM ── */
function h(tag, props, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (k === "class") e.className = v;
    else if (k === "html") e.innerHTML = v;
    else if (k.startsWith("on")) e[k.toLowerCase()] = v;
    else if (v != null) e.setAttribute(k, v);
  }
  for (const kid of kids.flat()) {
    if (kid == null) continue;
    e.append(kid.nodeType ? kid : document.createTextNode(kid));
  }
  return e;
}
function labelEl(text) { return h("label", {}, text); }
function helpEl(text) { return text ? h("div", { class: "help", html: text }) : document.createDocumentFragment(); }
function fieldRow(label, control, help) {
  return h("div", { class: "field" }, labelEl(label), control, helpEl(help));
}

const MENU_ITEM_TYPES = ["FRONTPAGE", "CATALOG", "COLLECTION", "PAGE", "BLOG", "HTTP", "SHOP_POLICY"];
const MENU_TYPE_LABELS = {
  FRONTPAGE: "Page d'accueil", CATALOG: "Toute la boutique", COLLECTION: "Une collection",
  PAGE: "Une page", BLOG: "Un blog", HTTP: "Un lien libre (URL)", SHOP_POLICY: "Une page légale",
};
const POLICY_TYPES = ["REFUND_POLICY", "PRIVACY_POLICY", "TERMS_OF_SERVICE", "SHIPPING_POLICY",
                      "CONTACT_INFORMATION", "TERMS_OF_SALE", "LEGAL_NOTICE"];
const POLICY_LABELS = {
  REFUND_POLICY: "Politique de remboursement", PRIVACY_POLICY: "Politique de confidentialité",
  TERMS_OF_SERVICE: "Conditions d'utilisation", SHIPPING_POLICY: "Politique de livraison",
  CONTACT_INFORMATION: "Coordonnées", TERMS_OF_SALE: "Conditions de vente (CGV)", LEGAL_NOTICE: "Mentions légales",
};

/* Un sous-champ (dans un objet/répéteur). Retourne { node, read }. */
function subField(def, value) {
  if (def.type === "number") {
    const i = h("input", { type: "number", placeholder: def.ph || "" }); i.value = value ?? "";
    return { node: fieldRow(def.label, i, def.help), read: () => (i.value === "" ? undefined : Number(i.value)) };
  }
  if (def.type === "select") {
    const s = h("select", {});
    def.options.forEach(([v, l]) => {
      const o = h("option", { value: v }, l);
      if ((value ?? "") === v) o.selected = true;
      s.append(o);
    });
    return { node: fieldRow(def.label, s, def.help), read: () => (s.value === "" ? undefined : s.value) };
  }
  if (def.type === "tags") {
    const i = h("input", { type: "text", placeholder: def.ph || "séparés par des virgules" });
    i.value = Array.isArray(value) ? value.join(", ") : "";
    return { node: fieldRow(def.label, i, def.help), read: () => {
      const a = i.value.split(",").map(s => s.trim()).filter(Boolean);
      return a.length ? a : undefined;
    }};
  }
  const i = h("input", { type: "text", placeholder: def.ph || "" }); i.value = value ?? "";
  return { node: fieldRow(def.label, i, def.help), read: () => (i.value === "" ? undefined : i.value) };
}

/* Un groupe de sous-champs éditant un objet. Retourne { node, read }. */
function renderObjectFields(subfields, obj) {
  const rows = subfields.map(sf => subField(sf, (obj || {})[sf.key]));
  const grid = h("div", { class: "obj-grid" }, rows.map(r => r.node));
  return { node: grid, read: () => {
    const o = {};
    subfields.forEach((sf, i) => { const v = rows[i].read(); if (v !== undefined) o[sf.key] = v; });
    return Object.keys(o).length ? o : undefined;
  }};
}

/* Constructeur d'items de menu (récursif, profondeur max 3). Retourne { read, addBtn }. */
function buildMenuItems(container, items, depth) {
  const entries = [];

  function addItem(it) {
    it = it || {};
    const title = h("input", { type: "text", placeholder: "Libellé" }); title.value = it.title || "";
    const type = h("select", {});
    MENU_ITEM_TYPES.forEach(t => {
      const o = h("option", { value: t }, MENU_TYPE_LABELS[t] || t);
      if ((it.type || "").toUpperCase() === t) o.selected = true;
      type.append(o);
    });
    const dyn = h("span", { class: "item-dyn" });
    let dynRead = () => ({});

    function refreshDyn() {
      dyn.innerHTML = "";
      const tv = type.value;
      if (tv === "COLLECTION") {
        // Menu déroulant des collections déjà définies (Mes collections / SEO Boost)
        const s = h("select", {});
        s.append(h("option", { value: "" }, "— choisir une collection —"));
        const opts = collectionOptions();
        let found = false;
        opts.forEach(c => {
          const o = h("option", { value: c.handle }, c.name);
          if (it.handle === c.handle) { o.selected = true; found = true; }
          s.append(o);
        });
        // Conserve une valeur déjà saisie même si la collection n'est pas (encore) dans la liste
        if (it.handle && !found) {
          const o = h("option", { value: it.handle }, it.handle + " (hors liste)"); o.selected = true; s.append(o);
        }
        dyn.append(s); dynRead = () => ({ handle: s.value });
      } else if (tv === "PAGE" || tv === "BLOG") {
        const i = h("input", { type: "text", placeholder: "identifiant (ex : contact)" }); i.value = it.handle || "";
        dyn.append(i); dynRead = () => ({ handle: i.value.trim() });
      } else if (tv === "HTTP") {
        const i = h("input", { type: "text", placeholder: "adresse (ex : /apps/... ou https://...)" }); i.value = it.url || "";
        dyn.append(i); dynRead = () => ({ url: i.value.trim() });
      } else if (tv === "SHOP_POLICY") {
        const s = h("select", {});
        POLICY_TYPES.forEach(p => { const o = h("option", { value: p }, POLICY_LABELS[p] || p); if (it.policy_type === p) o.selected = true; s.append(o); });
        dyn.append(s); dynRead = () => ({ policy_type: s.value });
      } else {
        const nothing = h("span", { class: "item-nothing" }, "— rien à choisir —");
        dyn.append(nothing); dynRead = () => ({});
      }
    }
    type.onchange = () => { Object.assign(it, dynRead()); refreshDyn(); };
    refreshDyn();

    // Sous-items (si profondeur < 2 → autorise jusqu'à 3 niveaux)
    let subEditor = null;
    let subBox = null;
    if (depth < 2) {
      subBox = h("div", { class: "subitems" });
      subEditor = buildMenuItems(subBox, it.items || [], depth + 1);
    }

    // Cellule libellé = chevron de repli (si sous-liens possibles) + champ
    // Par défaut REPLIÉ : l'utilisateur ouvre pour voir/ajouter des sous-liens.
    const titleCell = h("div", { class: "item-title-cell" });
    if (subEditor) {
      let collapsed = true;
      const toggle = h("button", { class: "toggle", type: "button", title: "Replier / déplier les sous-liens" }, "▸");
      const render = () => {
        toggle.textContent = collapsed ? "▸" : "▾";
        subBox.style.display = collapsed ? "none" : "";
        subEditor.addBtn.style.display = collapsed ? "none" : "";
      };
      toggle.onclick = () => { collapsed = !collapsed; render(); };
      render();
      titleCell.append(toggle);
    }
    titleCell.append(title);

    const row = h("div", { class: "item-row" });
    const rm = h("button", { class: "small danger", type: "button" }, "✕");

    const entry = { read: () => {
      const t = title.value.trim();
      if (!t) return undefined;
      const o = { title: t, type: type.value, ...dynRead() };
      if (subEditor) { const kids = subEditor.read(); if (kids.length) o.items = kids; }
      return o;
    }};
    row.append(titleCell, type, dyn, rm);
    container.append(row);
    if (subBox) { container.append(subBox); container.append(subEditor.addBtn); }
    entries.push(entry);

    rm.onclick = () => {
      row.remove();
      if (subBox) subBox.remove();
      if (subEditor) subEditor.addBtn.remove();
      const i = entries.indexOf(entry); if (i >= 0) entries.splice(i, 1);
    };
  }

  if (depth === 0) {
    container.append(h("div", { class: "item-row item-head" },
      h("span", {}, "Libellé du lien"), h("span", {}, "Type"), h("span", {}, "Vers quoi ?"), h("span", {}, "")));
  }
  items.forEach(addItem);
  const addBtn = h("button", { class: "small ghost", type: "button", onClick: () => addItem() },
                   depth === 0 ? "+ Ajouter un lien" : "+ Ajouter un sous-lien");
  return { read: () => entries.map(e => e.read()).filter(Boolean), addBtn };
}

/* Liste des collections déjà déclarées (seo_boost.collections) → [{handle, name}]
   pour proposer un menu déroulant dans les items de menu de type COLLECTION. */
function collectionOptions() {
  const cols = getPath(CFG, "seo_boost.collections");
  if (!Array.isArray(cols)) return [];
  return cols.map(c => {
    let handle = "";
    if (c.url && c.url.includes("/collections/")) handle = c.url.split("/collections/")[1].replace(/\/+$/, "");
    return { handle, name: c.name || handle };
  }).filter(c => c.handle);
}

/* Nom de domaine du site (normalisé, sans slash final), lu depuis la config. */
function siteDomain() {
  let d = (getPath(CFG, "legal_info.website_url") || "").trim().replace(/\/+$/, "");
  if (d && !/^https?:\/\//.test(d)) d = "https://" + d;
  return d;
}

/* Éditeur d'une collection : nom + fin d'URL (auto depuis le nom) + volume + type + mots.
   L'URL complète est reconstruite à partir du nom de domaine. Retourne { node, read }. */
function collectionRow(obj) {
  obj = obj || {};

  const name = h("input", { type: "text", placeholder: "ex : Arbre à Chat XXL" }); name.value = obj.name || "";

  let handle = "";
  if (obj.url && obj.url.includes("/collections/")) handle = obj.url.split("/collections/")[1].replace(/\/+$/, "");
  const handleInp = h("input", { type: "text", placeholder: "arbre-a-chat-xxl" }); handleInp.value = handle;
  let auto = handle === "";   // tant que l'utilisateur n'a pas édité l'URL à la main, on la déduit du nom

  const preview = h("div", { class: "url-preview" });
  const updPreview = () => {
    const d = siteDomain();
    preview.textContent = d
      ? `→ ${d}/collections/${handleInp.value}`
      : "→ ajoute d'abord ton nom de domaine dans « Mes données »";
  };
  name.addEventListener("input", () => { if (auto) { handleInp.value = slugify(name.value); updPreview(); } });
  handleInp.addEventListener("input", () => { auto = (handleInp.value.trim() === ""); handleInp.value = slugify(handleInp.value); updPreview(); });
  updPreview();

  const volume = h("input", { type: "number", placeholder: "ex : 4400" }); volume.value = obj.volume ?? "";

  // Type et mots déclencheurs : optionnels et masqués dans l'interface — on préserve les valeurs existantes.
  const keepCategory = obj.category;
  const keepTags = Array.isArray(obj.tags) ? obj.tags : undefined;

  const handleField = h("div", { class: "field" },
    labelEl("Fin du lien (après /collections/)"),
    handleInp, preview,
    helpEl("Juste le nom en minuscules, avec des tirets, sans accents. Se remplit tout seul depuis le nom."));

  const node = h("div", { class: "obj-grid" },
    fieldRow("Nom de la collection", name, "Le nom affiché sur ton site."),
    handleField,
    fieldRow("Recherches Google / mois", volume, "Chiffre donné par SEMrush. Plus c'est grand, plus la collection est prioritaire."),
  );

  const read = () => {
    const nm = name.value.trim();
    const hd = slugify(handleInp.value || name.value);
    if (!nm && !hd) return undefined;
    const o = {};
    if (nm) o.name = nm;
    const d = siteDomain();
    if (hd) o.url = d ? `${d}/collections/${hd}` : `/collections/${hd}`;
    if (volume.value !== "") o.volume = Number(volume.value);
    if (keepCategory) o.category = keepCategory;       // préservé même si non affiché
    if (keepTags && keepTags.length) o.tags = keepTags; // préservé même si non affiché
    return o;
  };

  return { node, read };
}

/* ── API ── */
async function api(method, url, body) {
  const opt = { method, headers: {} };
  if (body !== undefined) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
  const r = await fetch(url, opt);
  const data = await r.json().catch(() => ({}));
  if (!r.ok || data.error) throw new Error(data.error || ("HTTP " + r.status));
  return data;
}

/* ── Toast ── */
let toastTimer = null;
function toast(msg, kind) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.className = "toast show " + (kind || "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.className = "toast " + (kind || ""); }, 3200);
}

/* ── Chargement boutiques ── */
async function loadStores(preferred) {
  const { stores } = await api("GET", "/api/stores");
  const sel = document.getElementById("storeSelect");
  sel.innerHTML = "";
  stores.forEach(s => {
    const o = document.createElement("option");
    o.value = s.folder; o.textContent = s.name;
    o.dataset.url = s.store_url;
    sel.appendChild(o);
  });
  sel.onchange = () => selectStore(sel.value);
  document.getElementById("newStoreBtn").onclick = openCreateModal;

  const target = (preferred && stores.some(s => s.folder === preferred))
    ? preferred
    : (stores.length ? stores[0].folder : null);
  if (target) { sel.value = target; await selectStore(target); }
}

/* ── Création d'une boutique (clone de _template) ── */
function slugify(name) {
  return name.normalize("NFKD").replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-zA-Z0-9]+/g, "-").replace(/^-+|-+$/g, "").toLowerCase();
}

function openCreateModal() {
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal">
      <h2>🏪 Nouvelle boutique</h2>
      <p class="modal-sub">Crée un dossier dans <code>stores/</code> à partir du template
        (fichiers de contexte, politiques, keywords…). Tu pourras régler le reste ensuite.</p>
      <div class="field">
        <label>Nom de la boutique</label>
        <input type="text" id="nsName" placeholder="ex : Mon Atelier Déco"/>
        <div class="slug-preview">Dossier : <code id="nsSlug">—</code></div>
      </div>
      <div class="field">
        <label>URL Shopify</label>
        <input type="text" id="nsUrl" placeholder="ma-boutique.myshopify.com"/>
      </div>
      <div class="field">
        <label>Access token</label>
        <input type="text" id="nsToken" placeholder="shpat_…"/>
      </div>
      <div class="modal-actions">
        <button class="ghost" id="nsCancel">Annuler</button>
        <button class="primary" id="nsCreate">Créer</button>
      </div>
    </div>`;
  document.body.appendChild(backdrop);

  const nameInp = backdrop.querySelector("#nsName");
  const slugEl  = backdrop.querySelector("#nsSlug");
  nameInp.addEventListener("input", () => {
    const s = slugify(nameInp.value.trim());
    slugEl.textContent = s || "—";
  });

  const close = () => backdrop.remove();
  backdrop.querySelector("#nsCancel").onclick = close;
  backdrop.onclick = (e) => { if (e.target === backdrop) close(); };
  nameInp.focus();

  backdrop.querySelector("#nsCreate").onclick = async () => {
    const name = nameInp.value.trim();
    if (!name) { toast("Le nom est requis", "err"); return; }
    try {
      const d = await api("POST", "/api/store/create", {
        name,
        store_url:    backdrop.querySelector("#nsUrl").value.trim(),
        access_token: backdrop.querySelector("#nsToken").value.trim(),
      });
      close();
      CURRENT = "boutique";
      await loadStores(d.folder);
      toast(`Boutique « ${name} » créée ✓`, "ok");
    } catch (e) {
      toast(e.message, "err");
    }
  };
}

async function selectStore(folder) {
  STORE = folder;
  const { config } = await api("GET", "/api/store?folder=" + encodeURIComponent(folder));
  CFG = config;
  const opt = [...document.getElementById("storeSelect").options].find(o => o.value === folder);
  document.getElementById("storeUrl").textContent = opt ? opt.dataset.url : "";
  await loadFiles();
  renderSidebar();
  renderFeature(CURRENT || FEATURES[0].id);
}

/* Charge le contenu de tous les fichiers d'entrée dans le cache FILES. */
async function loadFiles() {
  FILES = {};
  await Promise.all(ALL_FILES.map(async name => {
    try {
      const d = await api("GET", `/api/file?store=${encodeURIComponent(STORE)}&name=${encodeURIComponent(name)}`);
      FILES[name] = d.content || "";
    } catch { FILES[name] = ""; }
  }));
}

/* ── Sidebar ── */
function renderSidebar() {
  const nav = document.getElementById("sidebar");
  nav.innerHTML = "";
  let section = null;
  FEATURES.forEach(f => {
    if (f.section !== section) {
      section = f.section;
      const s = document.createElement("div");
      s.className = "nav-sep"; s.textContent = section;
      nav.appendChild(s);
    }
    const item = document.createElement("div");
    item.className = "nav-item" + (f.id === CURRENT ? " active" : "");
    const locked = missingFor(f).length > 0;
    const badge = locked ? `<span class="num lock">🔒</span>`
                : (f.num !== undefined ? `<span class="num">${f.num}</span>` : "");
    item.innerHTML = `<span class="ico">${f.ico}</span><span>${f.label}</span>${badge}`;
    item.onclick = () => renderFeature(f.id);
    nav.appendChild(item);
  });
}

/* ── Rendu d'une feature ── */
function renderFeature(id) {
  CURRENT = id;
  // Stoppe le rafraîchissement du journal quand on quitte la page Activité
  if (activityTimer) { clearInterval(activityTimer); activityTimer = null; }
  renderSidebar();
  const f = FEATURES.find(x => x.id === id);
  const panel = document.getElementById("panel");
  panel.innerHTML = "";

  if (f.activity) { renderActivity(panel, f); return; }

  // En-tête
  const head = document.createElement("div");
  head.className = "feature-head";
  const actions = [];
  if (f.fields || f.files) actions.push(`<button class="primary" id="saveBtn">💾 Enregistrer</button>`);
  if (f.section === "Features") actions.push(`<button class="ghost" id="runBtn">▶︎ Lancer cette fonctionnalité</button>`);
  head.innerHTML = `
    <div>
      <h1>${f.ico} ${f.label}</h1>
      <p class="sub">${f.desc}</p>
    </div>
    <div class="feature-actions">${actions.join("")}</div>`;
  panel.appendChild(head);

  if (f.prereq) {
    const p = document.createElement("div");
    p.className = "prereq";
    p.innerHTML = `<b>Avant de lancer :</b> ${f.prereq}`;
    panel.appendChild(p);
  }

  // Bannière de verrouillage si des données requises manquent
  const miss = missingFor(f);
  if (miss.length) {
    const lock = document.createElement("div");
    lock.className = "lockbar";
    lock.innerHTML = `<b>🔒 Fonctionnalité verrouillée.</b> Complétez d'abord ces données pour pouvoir la lancer :` +
      `<ul>${miss.map(m => `<li>${m}</li>`).join("")}</ul>` +
      `<button class="small" id="gotoData">→ Aller à « Mes données »</button>`;
    panel.appendChild(lock);
  }

  const readers = [];   // { def, read }

  // Champs config
  if (f.fields) {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `<h3>Paramètres</h3>`;
    f.fields.forEach(def => {
      const { el, read } = renderField(def);
      card.appendChild(el);
      readers.push({ def, read, el });
    });
    // Affichage conditionnel : ne montrer que les champs pertinents selon les choix
    const apply = () => applyVisibility(readers);
    card.addEventListener("change", apply);
    card.addEventListener("input", apply);
    apply();
    panel.appendChild(card);
  }

  // Fichiers de contexte
  const fileEditors = [];
  if (f.files) {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `<h3>Fichiers de contexte</h3>`;
    f.files.forEach(file => {
      const wrap = document.createElement("div");
      wrap.className = "field";
      wrap.innerHTML = `<label>${file.label}</label><textarea class="code" data-file="${file.name}" placeholder="(chargement…)"></textarea>`;
      card.appendChild(wrap);
      const ta = wrap.querySelector("textarea");
      fileEditors.push({ name: file.name, ta });
      api("GET", `/api/file?store=${encodeURIComponent(STORE)}&name=${encodeURIComponent(file.name)}`)
        .then(d => { ta.value = d.content || ""; ta.placeholder = ""; })
        .catch(() => { ta.placeholder = "(fichier absent — sera créé à l'enregistrement)"; });
    });
    panel.appendChild(card);
  }

  // Info-only
  if (f.info && !f.fields && !f.files) {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `<div class="info-note">Cette fonctionnalité n'a pas de paramètre dans config.json.
      Utilisez « Lancer dans le Terminal » pour l'exécuter via le CLI interactif.</div>`;
    panel.appendChild(card);
  }

  // Page « Mes données » : tableau de bord du déblocage
  if (f.id === "donnees") panel.appendChild(renderDataStatus());

  // Actions
  const saveBtn = document.getElementById("saveBtn");
  if (saveBtn) saveBtn.onclick = () => saveFeature(f, readers, fileEditors);
  const runBtn = document.getElementById("runBtn");
  if (runBtn) {
    if (miss.length) {
      runBtn.disabled = true;
      runBtn.title = "Complétez les données requises pour lancer cette fonctionnalité";
    } else {
      runBtn.onclick = () => runCli(f);
    }
  }
  const goto = document.getElementById("gotoData");
  if (goto) goto.onclick = () => renderFeature("donnees");
}

/* Transforme le texte brut du journal en événements { time, level, main, detail }. */
function parseLog(text) {
  const out = [];
  for (const line of text.split("\n")) {
    if (!line.trim()) continue;
    const m = line.match(/^\d{4}-\d{2}-\d{2}\s+(\d{2}:\d{2}:\d{2})\s*\|\s*(\w+)\s*\|\s*(.*)$/);
    const time  = m ? m[1] : "";
    const level = m ? m[2].toUpperCase() : "INFO";
    const raw   = m ? m[3] : line;
    // Ignore les lignes purement décoratives (====, ────, etc.)
    if (/^[=\-─—•\s]+$/.test(raw)) continue;
    const parts  = raw.split(" | ");
    out.push({ time, level, main: parts[0], detail: parts.slice(1).join(" · ") });
  }
  return out;
}

/* Statut : dernière feature lancée + terminée ou non. */
function deriveActivityStatus(events) {
  let idx = -1, feature = "";
  events.forEach((e, i) => {
    const m = e.main.match(/Démarrage feature\s+(.+?)\s+—/);
    if (m) { idx = i; feature = m[1].trim(); }
  });
  if (idx < 0) return null;
  const finished = events.slice(idx + 1).some(e => /^Terminé/.test(e.main));
  return { feature, finished, startIdx: idx };
}

/* Type d'événement (couleur de la pastille). */
function eventKind(e) {
  if (e.level === "ERROR") return "error";
  if (e.level === "WARNING") return "warn";
  if (/^Terminé/.test(e.main)) return "done";
  if (/^Démarrage feature/.test(e.main)) return "start";
  if (/OK|SUCCÈS|✓|généré|créé|créée|sauvegardé/i.test(e.main)) return "ok";
  return "info";
}

/* Rend une ligne du fil d'activité. */
function renderEventRow(e) {
  const kind = eventKind(e);
  let main = e.main, detail = e.detail;
  if (kind === "start") { const m = e.main.match(/Démarrage feature\s+(.+?)\s+—\s*(.*)/); if (m) { main = "▶ Démarrage — " + m[1].trim(); detail = m[2]; } }
  if (kind === "done")  { main = "✓ " + e.main; }
  const row = h("div", { class: "feed-row " + kind });
  row.append(
    h("span", { class: "dot " + kind }),
    h("span", { class: "feed-time" }, e.time),
    h("div", { class: "feed-body" },
      h("div", { class: "feed-main" }, main),
      detail ? h("div", { class: "feed-detail" }, detail) : null),
  );
  return row;
}

/* Accordéon repliable listant un type d'événements (erreurs ou avertissements).
   isOpen : état mémorisé (conservé entre les rafraîchissements). onToggle(bool). */
function buildAccordion(cls, label, items, isOpen, onToggle) {
  const body = h("div", { class: "acc-body" });
  body.style.display = isOpen ? "" : "none";
  items.slice(-200).forEach(e => body.append(renderEventRow(e)));
  const chev = h("span", { class: "acc-chev" }, isOpen ? "▾" : "▸");
  const head = h("button", { class: "acc-head", type: "button" }, chev, h("span", { class: "acc-label" }, label));
  head.onclick = () => {
    const open = body.style.display === "none";
    body.style.display = open ? "" : "none";
    chev.textContent = open ? "▾" : "▸";
    onToggle(open);
  };
  return h("div", { class: "acc " + cls }, head, body);
}

/* Page Activité : fil d'événements lisible + accordéons erreurs/avertissements. */
function renderActivity(panel, f) {
  panel.append(h("div", { class: "feature-head" },
    h("div", {}, h("h1", {}, `${f.ico} ${f.label}`), h("p", { class: "sub" }, f.desc))));

  let errOpen = false, warnOpen = false;   // état des accordéons, conservé entre rafraîchissements

  const pill       = h("div", { class: "activity-status" }, "—");
  const stats      = h("div", { class: "activity-stats" });
  const currentCb  = h("input", { type: "checkbox" }); currentCb.checked = true;
  const currentLbl = h("label", { class: "switch" }, currentCb, h("span", {}, "Seulement l'exécution en cours"));
  const autoCb     = h("input", { type: "checkbox" }); autoCb.checked = true;
  const autoLbl    = h("label", { class: "switch" }, autoCb, h("span", {}, "Auto (3 s)"));
  const refreshBtn = h("button", { class: "small", type: "button" }, "↻");
  const toolbar    = h("div", { class: "log-toolbar" },
                       h("div", { class: "activity-head-left" }, pill, stats),
                       h("div", { class: "log-actions" }, currentLbl, autoLbl, refreshBtn));

  const accBox = h("div", { class: "acc-box" });   // accordéons erreurs / avertissements
  const feed   = h("div", { class: "feed" });
  const scroll = h("div", { class: "feed-scroll" }, feed);

  const card = h("div", { class: "card" });
  card.append(h("h3", {}, "Journal d'activité"), toolbar, accBox, scroll);
  panel.append(card);

  const refresh = async () => {
    try {
      const d = await api("GET", "/api/logs?lines=400");
      const events = parseLog(d.content || "");
      const st = deriveActivityStatus(events);

      // Pastille de statut
      if (!st)              pill.innerHTML = `<span class="st-idle">● Aucune exécution</span>`;
      else if (st.finished) pill.innerHTML = `<span class="st-done">● Terminé — ${st.feature}</span>`;
      else                  pill.innerHTML = `<span class="st-run">● En cours — ${st.feature}…</span>`;

      // Événements affichés (run en cours ou tout)
      const shown = (currentCb.checked && st) ? events.slice(st.startIdx) : events;

      // Tri : erreurs / avertissements à part, le reste dans le fil principal
      const errs  = shown.filter(e => e.level === "ERROR");
      const warns = shown.filter(e => e.level === "WARNING");
      const main  = shown.filter(e => e.level !== "ERROR" && e.level !== "WARNING");
      const nOk   = main.filter(e => eventKind(e) === "ok" || eventKind(e) === "done").length;

      // Compteur de succès (les warn/err ont leur propre accordéon)
      stats.innerHTML = `<span class="stat ok">✓ ${nOk} réussi${nOk > 1 ? "s" : ""}</span>`;

      // Accordéons erreurs / avertissements
      accBox.innerHTML = "";
      if (errs.length) {
        accBox.append(buildAccordion("acc-error",
          `✕  ${errs.length} erreur${errs.length > 1 ? "s" : ""}`, errs, errOpen, v => errOpen = v));
      }
      if (warns.length) {
        accBox.append(buildAccordion("acc-warn",
          `⚠  ${warns.length} avertissement${warns.length > 1 ? "s" : ""}`, warns, warnOpen, v => warnOpen = v));
      }

      // Fil principal (déroulé normal), limité aux 200 derniers
      const wasBottom = scroll.scrollHeight - scroll.scrollTop - scroll.clientHeight < 40;
      feed.innerHTML = "";
      const rows = main.slice(-200);
      if (!rows.length) feed.append(h("div", { class: "feed-empty" }, "Lance une fonctionnalité pour voir l'activité apparaître ici."));
      rows.forEach(e => feed.append(renderEventRow(e)));
      if (wasBottom) scroll.scrollTop = scroll.scrollHeight;   // suit le direct
    } catch (e) {
      feed.innerHTML = "";
      feed.append(h("div", { class: "feed-empty" }, "Erreur de lecture du journal : " + e.message));
    }
  };

  refresh();
  refreshBtn.onclick = refresh;
  currentCb.onchange = refresh;
  autoCb.onchange = () => {
    if (autoCb.checked) { if (!activityTimer) activityTimer = setInterval(refresh, 3000); }
    else if (activityTimer) { clearInterval(activityTimer); activityTimer = null; }
  };
  activityTimer = setInterval(refresh, 3000);
}

/* Tableau de bord : état de déblocage de chaque fonctionnalité. */
function renderDataStatus() {
  const card = document.createElement("div");
  card.className = "card";
  card.innerHTML = `<h3>État des fonctionnalités</h3>`;
  const list = document.createElement("div");
  list.className = "status-list";
  FEATURES.filter(f => f.section === "Features").forEach(f => {
    const miss = missingFor(f);
    const row = document.createElement("div");
    row.className = "status-row";
    const state = f.exempt
      ? `<span class="ok">✓ toujours disponible</span>`
      : (miss.length ? `<span class="err">🔒 ${miss.join(", ")}</span>` : `<span class="ok">✓ débloquée</span>`);
    row.innerHTML = `<span class="status-name">${f.ico} ${f.label}</span>${state}`;
    list.appendChild(row);
  });
  card.appendChild(list);
  return card;
}

/* ── Color picker custom (hex) ── */
function hexToRgb(hex) {
  const m = hex.replace("#", "");
  return { r: parseInt(m.slice(0, 2), 16), g: parseInt(m.slice(2, 4), 16), b: parseInt(m.slice(4, 6), 16) };
}
function rgbToHex(r, g, b) {
  const t = x => x.toString(16).padStart(2, "0");
  return ("#" + t(r) + t(g) + t(b)).toUpperCase();
}
function rgbToHsv(r, g, b) {
  r /= 255; g /= 255; b /= 255;
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn;
  let hh = 0;
  if (d) {
    if (mx === r) hh = ((g - b) / d) % 6;
    else if (mx === g) hh = (b - r) / d + 2;
    else hh = (r - g) / d + 4;
    hh *= 60; if (hh < 0) hh += 360;
  }
  return { h: hh, s: mx ? d / mx : 0, v: mx };
}
function hsvToHex(h, s, v) {
  const c = v * s, x = c * (1 - Math.abs((h / 60) % 2 - 1)), m = v - c;
  let r = 0, g = 0, b = 0;
  if (h < 60) { r = c; g = x; } else if (h < 120) { r = x; g = c; } else if (h < 180) { g = c; b = x; }
  else if (h < 240) { g = x; b = c; } else if (h < 300) { r = x; b = c; } else { r = c; b = x; }
  return rgbToHex(Math.round((r + m) * 255), Math.round((g + m) * 255), Math.round((b + m) * 255));
}
function attachDrag(el, handler) {
  el.addEventListener("pointerdown", e => {
    e.preventDefault(); handler(e);
    const move = ev => handler(ev);
    const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
  });
}
/* Popover de sélection couleur (hex). onChange(hex) à chaque changement. */
function buildColorPopover(initialHex, onChange) {
  const rgb0 = hexToRgb(/^#[0-9a-fA-F]{6}$/.test(initialHex) ? initialHex : "#FFFFFF");
  const st = rgbToHsv(rgb0.r, rgb0.g, rgb0.b);   // { h, s, v } — état couleur

  const svThumb  = h("div", { class: "cp-thumb" });
  const sv       = h("div", { class: "cp-sv" }, svThumb);
  const hueThumb = h("div", { class: "cp-hue-thumb" });
  const hue      = h("div", { class: "cp-hue" }, hueThumb);
  const hexIn    = h("input", { type: "text", class: "cp-hex" });
  const node     = h("div", { class: "color-pop" }, sv, hue, hexIn);

  const render = (fire = true) => {
    sv.style.background = `linear-gradient(to top, #000, transparent), linear-gradient(to right, #fff, transparent), hsl(${st.h}, 100%, 50%)`;
    svThumb.style.left  = (st.s * 100) + "%";
    svThumb.style.top   = ((1 - st.v) * 100) + "%";
    hueThumb.style.left = (st.h / 360 * 100) + "%";
    const hex = hsvToHex(st.h, st.s, st.v);
    svThumb.style.background = hex;
    hexIn.value = hex;
    if (fire) onChange(hex);
  };

  attachDrag(sv, e => {
    const r = sv.getBoundingClientRect();
    st.s = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
    st.v = 1 - Math.min(1, Math.max(0, (e.clientY - r.top) / r.height));
    render();
  });
  attachDrag(hue, e => {
    const r = hue.getBoundingClientRect();
    st.h = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)) * 360;
    render();
  });
  hexIn.addEventListener("input", () => {
    let val = hexIn.value.trim();
    if (/^#?[0-9a-fA-F]{6}$/.test(val)) {
      if (val[0] !== "#") val = "#" + val;
      const c = hexToRgb(val); const hsv = rgbToHsv(c.r, c.g, c.b);
      st.h = hsv.h; st.s = hsv.s; st.v = hsv.v; render();
    }
  });

  render(false);
  return {
    node,
    setHex(hx) {
      if (/^#[0-9a-fA-F]{6}$/.test(hx)) {
        const c = hexToRgb(hx); const hsv = rgbToHsv(c.r, c.g, c.b);
        st.h = hsv.h; st.s = hsv.s; st.v = hsv.v; render(false);
      }
    },
  };
}

/* ── Affichage conditionnel des champs (showIf) ── */
function fieldValueOf(readers, path) {
  const r = readers.find(x => x.def.path === path || (x.def.paths && x.def.paths.includes(path)));
  return r ? r.read() : getPath(CFG, path);
}
function condOk(cond, readers) {
  if (cond.allOf) return cond.allOf.every(c => condOk(c, readers));
  const v = fieldValueOf(readers, cond.path);
  if (cond.in) return cond.in.includes(v);
  if ("equals" in cond) return v === cond.equals;
  return true;
}
function applyVisibility(readers) {
  readers.forEach(({ def, el }) => {
    if (def.showIf) el.style.display = condOk(def.showIf, readers) ? "" : "none";
  });
}

/* ── Rendu d'un champ ── */
function renderField(def) {
  const wrap = document.createElement("div");
  wrap.className = "field";
  const val = getPath(CFG, def.path || (def.paths && def.paths[0]));
  const help = def.help ? `<div class="help">${def.help}</div>` : "";

  if (def.type === "bool") {
    wrap.innerHTML = `<div class="switch"><input type="checkbox" ${val ? "checked" : ""}/><label style="margin:0">${def.label}</label></div>${help}`;
    const cb = wrap.querySelector("input");
    return { el: wrap, read: () => cb.checked };
  }

  if (def.type === "select") {
    const opts = def.options.map(([v, l]) =>
      `<option value="${v}" ${val === v ? "selected" : ""}>${l}</option>`).join("");
    wrap.innerHTML = `<label>${def.label}</label><select>${opts}</select>${help}`;
    const sel = wrap.querySelector("select");
    return { el: wrap, read: () => sel.value };
  }

  if (def.type === "number") {
    wrap.innerHTML = `<label>${def.label}</label><input type="number" value="${val ?? ""}"/>${help}`;
    const inp = wrap.querySelector("input");
    return { el: wrap, read: () => inp.value === "" ? undefined : Number(inp.value) };
  }

  if (def.type === "json") {
    const txt = val === undefined ? "" : JSON.stringify(val, null, 2);
    wrap.innerHTML = `<label>${def.label}</label><textarea class="code">${escapeHtml(txt)}</textarea>` +
      `<div class="json-status"></div>${help}`;
    const ta = wrap.querySelector("textarea");
    const status = wrap.querySelector(".json-status");
    const validate = () => {
      if (ta.value.trim() === "") { status.textContent = ""; ta.classList.remove("json-invalid"); return true; }
      try { JSON.parse(ta.value); status.textContent = "✓ JSON valide"; status.className = "json-status ok"; ta.classList.remove("json-invalid"); return true; }
      catch (e) { status.textContent = "✗ " + e.message; status.className = "json-status err"; ta.classList.add("json-invalid"); return false; }
    };
    ta.addEventListener("input", validate);
    return { el: wrap, read: () => {
      if (ta.value.trim() === "") return undefined;
      if (!validate()) throw new Error(`JSON invalide dans « ${def.label} »`);
      return JSON.parse(ta.value);
    }};
  }

  // pairs — liste de remplacements {from → to} (ex: rebrand)
  if (def.type === "pairs") {
    wrap.innerHTML = `<label>${def.label}</label>${help}<div class="pairs"></div>` +
      `<button class="small ghost" type="button">+ Ajouter un remplacement</button>`;
    const box = wrap.querySelector(".pairs");
    const addRow = (from = "", to = "") => {
      const row = document.createElement("div");
      row.className = "pair-row";
      row.innerHTML = `<input type="text" placeholder="mot à chercher" value="${escapeAttr(from)}"/>` +
        `<span class="arrow">→</span><input type="text" placeholder="remplacer par…" value="${escapeAttr(to)}"/>` +
        `<button class="small danger" type="button">✕</button>`;
      row.querySelector("button").onclick = () => row.remove();
      box.appendChild(row);
    };
    const arr = Array.isArray(val) ? val : [];
    arr.forEach(p => addRow(p.from, p.to));
    if (!arr.length) addRow();
    wrap.querySelector("button").onclick = () => addRow();
    return { el: wrap, read: () => {
      const rows = [...box.querySelectorAll(".pair-row")];
      const out = rows.map(r => {
        const [a, b] = r.querySelectorAll("input");
        return { from: a.value, to: b.value };
      }).filter(p => p.from !== "");
      return out.length ? out : undefined;
    }};
  }

  // list — un élément par ligne (ex: brandingNames)
  if (def.type === "list") {
    const arr = Array.isArray(val) ? val : [];
    const ta = h("textarea", { class: "code" }); ta.value = arr.join("\n"); ta.style.minHeight = "120px";
    wrap.append(labelEl(def.label), ta, helpEl(def.help));
    return { el: wrap, read: () => {
      const a = ta.value.split("\n").map(s => s.trim()).filter(Boolean);
      return a.length ? a : undefined;
    }};
  }

  // objgroup — un seul objet éditable via sous-champs (ex: mainCollection)
  if (def.type === "objgroup") {
    const of = renderObjectFields(def.subfields, val || {});
    wrap.append(labelEl(def.label), of.node, helpEl(def.help));
    return { el: wrap, read: () => of.read() };
  }

  // objlist — liste d'objets, cartes répétables (ex: collections)
  if (def.type === "objlist") {
    const arr = Array.isArray(val) ? val : [];
    const list = h("div", { class: "objlist" });
    const items = [];
    const addCard = (obj) => {
      const of = renderObjectFields(def.subfields, obj || {});
      const card = h("div", { class: "repeat-card" });
      const entry = { read: of.read };
      const rm = h("button", { class: "small danger", type: "button" }, "✕ Supprimer");
      rm.onclick = () => { card.remove(); const i = items.indexOf(entry); if (i >= 0) items.splice(i, 1); };
      card.append(of.node, h("div", { class: "repeat-actions" }, rm));
      items.push(entry); list.append(card);
    };
    arr.forEach(addCard);
    const add = h("button", { class: "small ghost", type: "button", onClick: () => addCard({}) }, "+ Ajouter");
    wrap.append(labelEl(def.label), list, add, helpEl(def.help));
    return { el: wrap, read: () => { const out = items.map(e => e.read()).filter(Boolean); return out.length ? out : undefined; } };
  }

  // collection — une seule collection (ex: collection principale)
  if (def.type === "collection") {
    const ed = collectionRow(val || {});
    wrap.append(labelEl(def.label), helpEl(def.help), ed.node);
    return { el: wrap, read: () => ed.read() };
  }

  // collections — liste de collections (cartes)
  if (def.type === "collections") {
    const arr = Array.isArray(val) ? val : [];
    const list = h("div", { class: "objlist" });
    const items = [];
    const addCard = (obj) => {
      const ed = collectionRow(obj || {});
      const card = h("div", { class: "repeat-card" });
      const entry = { read: ed.read };
      const rm = h("button", { class: "small danger", type: "button" }, "✕ Supprimer");
      rm.onclick = () => { card.remove(); const i = items.indexOf(entry); if (i >= 0) items.splice(i, 1); };
      card.append(ed.node, h("div", { class: "repeat-actions" }, rm));
      items.push(entry); list.append(card);
    };
    arr.forEach(addCard);
    const add = h("button", { class: "small ghost", type: "button", onClick: () => addCard({}) }, "+ Ajouter une collection");
    wrap.append(labelEl(def.label), helpEl(def.help), list, add);
    return { el: wrap, read: () => { const out = items.map(e => e.read()).filter(Boolean); return out.length ? out : undefined; } };
  }

  // triggers — priorityTriggers : 4 niveaux de mots-clés
  if (def.type === "triggers") {
    const obj = val || {};
    const levels = [
      ["1", "Le PLUS important — type / usage (ex : mural, géant, extérieur)"],
      ["2", "Style / matière (ex : bois, design, scandinave)"],
      ["3", "Formes & options de ta niche (ex : hamac, griffoir, niche)"],
      ["4", "Le MOINS important — couleurs (ex : beige, noir, gris)"],
    ];
    const reads = [];
    const box = h("div", {});
    levels.forEach(([k, lab]) => {
      const sf = subField({ label: lab, type: "tags", ph: "mots-clés séparés par des virgules" }, obj[k]);
      reads.push([k, sf.read]); box.append(sf.node);
    });
    wrap.append(labelEl(def.label), box, helpEl(def.help));
    return { el: wrap, read: () => {
      const o = {}; reads.forEach(([k, r]) => { const v = r(); if (v) o[k] = v; });
      return Object.keys(o).length ? o : undefined;
    }};
  }

  // menus — constructeur arborescent
  if (def.type === "menus") {
    const menus = Array.isArray(val) ? val : [];
    const list = h("div", { class: "menus" });
    const entries = [];
    const addMenu = (m) => {
      m = m || { items: [] };
      const card = h("div", { class: "menu-card" });
      const title = h("input", { type: "text", placeholder: "Titre du menu (ex: Menu Principal)" }); title.value = m.title || "";
      const handle = h("input", { type: "text", placeholder: "handle (ex: main-menu, footer)" }); handle.value = m.handle || "";
      const itemsBox = h("div", { class: "items-box" });
      const itemsEditor = buildMenuItems(itemsBox, m.items || [], 0);
      const rm = h("button", { class: "small danger", type: "button" }, "✕ Supprimer ce menu");
      const entry = { read: () => {
        const t = title.value.trim(); const hn = handle.value.trim();
        if (!t && !hn) return undefined;
        return { title: t, handle: hn, items: itemsEditor.read() };
      }};
      rm.onclick = () => { card.remove(); const i = entries.indexOf(entry); if (i >= 0) entries.splice(i, 1); };
      card.append(
        fieldRow("Titre", title), fieldRow("Handle", handle),
        labelEl("Items du menu"), itemsBox, itemsEditor.addBtn,
        h("div", { class: "repeat-actions" }, rm),
      );
      entries.push(entry); list.append(card);
    };
    menus.forEach(addMenu);
    const add = h("button", { class: "small ghost", type: "button", onClick: () => addMenu() }, "+ Ajouter un menu");
    wrap.append(labelEl(def.label), list, add, helpEl(def.help));
    return { el: wrap, read: () => { const out = entries.map(e => e.read()).filter(Boolean); return out.length ? out : undefined; } };
  }

  // color — swatch cliquable + picker hexadécimal custom + saisie libre
  if (def.type === "color") {
    const cur      = (val ?? "").trim();
    const startHex = /^#[0-9a-fA-F]{6}$/.test(cur) ? cur.toUpperCase() : "#FFFFFF";
    const text     = h("input", { type: "text", placeholder: "#FFFFFF ou « blanc »" }); text.value = cur;
    const swatch   = h("button", { type: "button", class: "swatch-btn" }); swatch.style.background = startHex;

    const pop = buildColorPopover(startHex, (hex) => { text.value = hex; swatch.style.background = hex; });
    pop.node.style.display = "none";

    swatch.onclick = () => {
      const open = pop.node.style.display === "none";
      pop.node.style.display = open ? "" : "none";
      if (open && /^#[0-9a-fA-F]{6}$/.test(text.value.trim())) pop.setHex(text.value.trim().toUpperCase());
    };
    text.addEventListener("input", () => {
      const v = text.value.trim();
      if (/^#[0-9a-fA-F]{6}$/.test(v)) { swatch.style.background = v; pop.setHex(v.toUpperCase()); }
    });

    const field = h("div", { class: "color-field" }, swatch, text, pop.node);
    field.addEventListener("click", e => e.stopPropagation());   // clic à l'intérieur ne ferme pas
    document.addEventListener("click", () => { pop.node.style.display = "none"; });

    wrap.append(labelEl(def.label), field, helpEl(def.help));
    return { el: wrap, read: () => (text.value.trim() === "" ? undefined : text.value.trim()) };
  }

  // text (défaut)
  wrap.innerHTML = `<label>${def.label}</label><input type="text" value="${escapeAttr(val ?? "")}"/>${help}`;
  const inp = wrap.querySelector("input");
  return { el: wrap, read: () => inp.value === "" ? undefined : inp.value };
}

/* ── Enregistrement ── */
async function saveFeature(feature, readers, fileEditors) {
  try {
    // 1. Champs config → mutate CFG (un champ peut viser plusieurs chemins via def.paths)
    for (const { def, read } of readers) {
      const v = read();          // peut throw si JSON invalide
      (def.paths || [def.path]).forEach(p => setPath(CFG, p, v));
    }
    if (readers.length) {
      await api("POST", "/api/store?folder=" + encodeURIComponent(STORE), { config: CFG });
    }
    // 2. Fichiers (+ mise à jour du cache pour recalculer les verrous)
    for (const { name, ta } of fileEditors) {
      await api("POST", `/api/file?store=${encodeURIComponent(STORE)}&name=${encodeURIComponent(name)}`, { content: ta.value });
      FILES[name] = ta.value;
    }
    toast("Enregistré ✓", "ok");
    renderSidebar();                                   // met à jour les cadenas
    if (CURRENT === "donnees") renderFeature("donnees"); // rafraîchit le tableau de bord
  } catch (e) {
    toast(e.message, "err");
  }
}

/* ── Lancer le CLI ── */
async function runCli(feature) {
  try {
    // Lance directement la feature sur la boutique en cours (sans menu dans le terminal)
    const body = feature ? { store: STORE, feature: feature.id } : {};
    const d = await api("POST", "/api/run", body);
    toast(d.message || (d.ok ? "Terminal ouvert" : "Impossible"), d.ok ? "ok" : "err");
  } catch (e) {
    toast(e.message, "err");
  }
}

/* ── Échappement ── */
function escapeHtml(s) { return String(s).replace(/[&<>]/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;" }[c])); }
function escapeAttr(s) { return String(s).replace(/[&<>"]/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;" }[c])); }

/* ── Boot ── */
loadStores().catch(e => toast("Erreur : " + e.message, "err"));
