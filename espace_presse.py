#!/usr/bin/env python3
"""Espace presse personnel : génère index.html (onglets par rubrique) depuis des flux RSS.
Aucune installation requise (bibliothèque standard uniquement).
Lancez-le chaque jour (voir tâche planifiée Windows) ou à la main.
"""
import html
import os
import random
import urllib.request
import webbrowser
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path

ARTICLES_PAR_SOURCE = 8
EN_LIGNE = bool(os.environ.get("GITHUB_ACTIONS"))  # vrai quand lancé par GitHub
DOSSIER = Path("docs") if EN_LIGNE else Path.home() / "espace_presse"
OUVRIR_NAVIGATEUR = not EN_LIGNE


def par_source(d):
    """Une colonne par source."""
    return [(nom, [(nom, url)]) for nom, url in d.items()]


# ============ À PERSONNALISER : rubriques > colonnes > sources (flux RSS) ============
RUBRIQUES = [
    ("💶 Économie", par_source({
        "Le Monde Éco": "https://www.lemonde.fr/economie/rss_full.xml",
        "Le Figaro Éco": "https://www.lefigaro.fr/rss/figaro_economie.xml",
        "Franceinfo Éco": "https://www.francetvinfo.fr/economie.rss",
        "Les Echos": "https://www.lesechos.fr/rss/rss_une.xml",
    })),
    ("🌍 Géopolitique", par_source({
        "Le Monde International": "https://www.lemonde.fr/international/rss_full.xml",
        "RFI": "https://www.rfi.fr/fr/rss",
        "France 24": "https://www.france24.com/fr/rss",
        "Courrier international": "https://www.courrierinternational.com/feed/all/rss.xml",
    })),
    ("🏛️ Politique française", [
        ("➡️ Droite", [
            ("Le Figaro Politique", "https://www.lefigaro.fr/rss/figaro_politique.xml"),
            ("Valeurs actuelles", "https://www.valeursactuelles.com/feed"),
        ]),
        ("⚪ Neutre / généraliste", [
            ("Franceinfo Politique", "https://www.francetvinfo.fr/politique.rss"),
            ("Le Monde Politique", "https://www.lemonde.fr/politique/rss_full.xml"),
        ]),
        ("⬅️ Gauche", [
            ("Libération Politique", "https://www.liberation.fr/arc/outboundfeeds/rss-all/category/politique/?outputType=xml"),
            ("L'Humanité", "https://www.humanite.fr/rss/actu.rss"),
            ("Mediapart", "https://www.mediapart.fr/articles/feed"),
        ]),
    ]),
    ("🛂 Politique étrangère", par_source({
        "BBC World": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "The Guardian": "https://www.theguardian.com/world/rss",
        "DW (français)": "https://rss.dw.com/rdf/rss-fr-all",
        "Politico Europe": "https://www.politico.eu/feed/",
    })),
    ("⚽ Sport", [
        ("⚽ Football", [
            ("L'Équipe Football", "https://dwh.lequipe.fr/api/edito/rss?path=/Football"),
            ("Franceinfo Sport", "https://www.francetvinfo.fr/sports.rss"),
        ]),
        ("🏀 Basket", [
            ("L'Équipe Basket", "https://dwh.lequipe.fr/api/edito/rss?path=/Basket"),
            ("BasketUSA", "https://www.basketusa.com/feed/"),
        ]),
    ]),
    ("🤖 IA & Jeux vidéo", [
        ("🤖 Intelligence artificielle", [
            ("ActuIA", "https://www.actuia.com/feed/"),
            ("Numerama", "https://www.numerama.com/feed/"),
        ]),
        ("🎮 Jeux vidéo", [
            ("JeuxVideo.com", "https://www.jeuxvideo.com/rss/rss.xml"),
            ("Journal du Geek", "https://www.journaldugeek.com/feed/"),
        ]),
    ]),
    ("🍷 Bordeaux", par_source({
        "Sud Ouest Bordeaux": "https://www.sudouest.fr/gironde/bordeaux/rss.xml",
        "Rue89 Bordeaux": "https://rue89bordeaux.com/feed/",
        "ici Gironde": "https://www.francebleu.fr/rss/gironde/a-la-une.xml",
    })),
]

# Onglet « Détente » : insolite (RSS) + blague du jour + horoscope
INSOLITE = [
    ("Le Parisien Insolite", "https://www.leparisien.fr/insolite/rss.xml"),
    ("20 Minutes", "https://www.20minutes.fr/feeds/rss-une.xml"),
]
BLAGUES = [
    "Pourquoi les plongeurs plongent-ils toujours en arrière ? Parce que sinon ils tombent dans le bateau.",
    "Quel est le comble pour un électricien ? De ne pas être au courant.",
    "Que fait une fraise sur un cheval ? Tagada tagada.",
    "Pourquoi les poissons détestent l'ordinateur ? À cause du net.",
    "Quel est le comble pour un jardinier ? De raconter des salades.",
    "Que dit un escargot sur le dos d'une tortue ? Youpiii !",
    "Pourquoi le livre de maths est-il triste ? Il a trop de problèmes.",
    "Quel est le comble pour un boulanger ? De se faire rouler dans la farine.",
    "Comment appelle-t-on un chat tombé dans un pot de peinture le jour de Noël ? Un chat-peint de Noël.",
    "Que dit un fantôme quand il est ému ? C'est trop drap !",
    "Pourquoi les canards sont-ils toujours à l'heure ? Parce qu'ils sont dans l'étang.",
    "Quel est le sport préféré des insectes ? Le cricket.",
    "Que fait un geek quand il se perd ? Il se Wi-Fi.",
    "Pourquoi Bordeaux est-elle la ville la plus sage ? Parce qu'elle est toujours bien rouge… de vin.",
]
SIGNES = ["Bélier", "Taureau", "Gémeaux", "Cancer", "Lion", "Vierge",
          "Balance", "Scorpion", "Sagittaire", "Capricorne", "Verseau", "Poissons"]
# =====================================================================================

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]
NS = "{http://www.w3.org/2005/Atom}"
_cache = {}


def lire_flux(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            racine = ET.fromstring(r.read())
        items = [(i.findtext("title", ""), i.findtext("link", "")) for i in racine.iter("item")]
        for e in racine.iter(NS + "entry"):
            lien = e.find(NS + "link")
            items.append((e.findtext(NS + "title", ""), lien.get("href") if lien is not None else ""))
        return [(t.strip(), l.strip()) for t, l in items if t and l][:ARTICLES_PAR_SOURCE], None
    except Exception as ex:
        return [], str(ex)


def charger_tout(urls):
    with ThreadPoolExecutor(max_workers=12) as pool:
        for url, res in zip(urls, pool.map(lire_flux, urls)):
            _cache[url] = res


def bloc_source(nom, url):
    items, err = _cache[url]
    if err:
        corps = f"<li class='err'>Source indisponible</li>"
    else:
        corps = "".join(
            f'<li><a href="{html.escape(l)}" target="_blank" rel="noopener">{html.escape(t)}</a></li>'
            for t, l in items)
    return f"<h3>{html.escape(nom)}</h3><ul>{corps}</ul>"


def colonne(titre, sources):
    return f"<section><h2>{html.escape(titre)}</h2>{''.join(bloc_source(n, u) for n, u in sources)}</section>"


def onglet_detente():
    rnd = random.Random(date.today().toordinal())
    blague = rnd.choice(BLAGUES)
    signes = "".join(
        f'<a class="signe" target="_blank" rel="noopener" '
        f'href="https://www.google.com/search?q=horoscope+{s.lower()}+aujourd%27hui">{s}</a>'
        for s in SIGNES)
    return (
        f"<section><h2>😂 Blague du jour</h2><p class='blague'>{html.escape(blague)}</p></section>"
        f"<section><h2>🔮 Horoscope</h2><p>Cliquez sur votre signe :</p><div class='signes'>{signes}</div></section>"
        + "".join(colonne("🤪 Insolite — " + n, [(n, u)]) for n, u in INSOLITE)
    )


MODELE = """<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Espace presse</title>
<style>
 body{font-family:Georgia,serif;background:#f6f4ef;color:#222;margin:0}
 header{padding:1.2rem 2rem 0}
 h1{margin:0}.date{color:#777;margin:.2rem 0 1rem}
 nav{display:flex;flex-wrap:wrap;gap:.4rem;padding:0 2rem 1rem;position:sticky;top:0;background:#f6f4ef;z-index:1}
 nav button{border:1px solid #c0392b;background:#fff;color:#c0392b;padding:.5rem .9rem;border-radius:20px;cursor:pointer;font-size:1rem}
 nav button.actif{background:#c0392b;color:#fff}
 main{padding:0 2rem 2rem}
 .onglet{display:none;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:1.2rem}
 .onglet.actif{display:grid}
 section{background:#fff;padding:1rem 1.4rem;border-radius:8px;box-shadow:0 1px 4px #0002}
 h2{margin-top:0;border-bottom:2px solid #c0392b;padding-bottom:.3rem}
 h3{margin:1rem 0 .2rem;font-size:.9rem;color:#888;text-transform:uppercase;letter-spacing:.05em}
 ul{padding-left:1.1rem;margin:.3rem 0}li{margin:.45rem 0}
 a{color:#222;text-decoration:none}a:hover{color:#c0392b;text-decoration:underline}
 .err{color:#a00}.blague{font-size:1.2rem}
 .signes{display:flex;flex-wrap:wrap;gap:.4rem}
 .signe{border:1px solid #ccc;border-radius:6px;padding:.3rem .6rem}
 .note{color:#888;font-size:.8rem;padding:0 2rem 2rem}
 @media(prefers-color-scheme:dark){body,nav{background:#1b1b1b;color:#eee}
  section,nav button{background:#262626}a{color:#eee}.signe{border-color:#555}}
</style></head><body>
<header><h1>📰 Espace presse</h1><div class="date">__DATE__</div></header>
<nav>__NAV__</nav>
<main>__CONTENU__</main>
<p class="note">Le classement droite / neutre / gauche est une simplification : variez vos sources pour vous faire votre propre avis.</p>
<script>
 const b=[...document.querySelectorAll('nav button')],o=[...document.querySelectorAll('.onglet')];
 function show(i){b.forEach((x,k)=>x.classList.toggle('actif',k==i));o.forEach((x,k)=>x.classList.toggle('actif',k==i));location.hash=i}
 b.forEach((x,k)=>x.onclick=()=>show(k));show(parseInt(location.hash.slice(1))||0);
</script></body></html>"""


def construire_page():
    urls = [u for _, cols in RUBRIQUES for _, srcs in cols for _, u in srcs] + [u for _, u in INSOLITE]
    charger_tout(list(dict.fromkeys(urls)))

    noms = [r[0] for r in RUBRIQUES] + ["🎭 Détente"]
    nav = "".join(f"<button>{html.escape(n)}</button>" for n in noms)
    contenus = [f"<div class='onglet'>{''.join(colonne(t, s) for t, s in cols)}</div>"
                for _, cols in RUBRIQUES]
    contenus.append(f"<div class='onglet'>{onglet_detente()}</div>")

    n = datetime.now()
    d = f"{JOURS[n.weekday()].capitalize()} {n.day} {MOIS[n.month - 1]} {n.year}, mis à jour à {n:%H:%M}"
    return MODELE.replace("__DATE__", d).replace("__NAV__", nav).replace("__CONTENU__", "".join(contenus))


if __name__ == "__main__":
    DOSSIER.mkdir(exist_ok=True)
    sortie = DOSSIER / "index.html"
    sortie.write_text(construire_page(), encoding="utf-8")
    ko = [u for u, (_, e) in _cache.items() if e]
    print("Page générée :", sortie)
    if ko:
        print(f"{len(ko)} flux en erreur (à corriger dans le script) :")
        for u in ko:
            print("  -", u)
    if OUVRIR_NAVIGATEUR:
        webbrowser.open(sortie.as_uri())
