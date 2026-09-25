import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


# ============================================================
# KONFIGURATION
# ============================================================

SEARCH_TERMS = [
    "wingo",
    "swisscom",
    "sunrise",
   "salt",
   "yallo",
   "quickline",
    "coop mobile",
    "migros mobile",
   "chmobile",
    "gomo",
    "spusu",
    "post mobile",
    "talktalk",

]

OUTPUT_FILE = "20min_articles_comments.json"

# Anzahl Suchseiten pro Suchbegriff (per "mehr laden"-Klicks simuliert)
MAX_SEARCH_PAGES = 10

# Anzahl Kommentare pro API-Request
COMMENT_LIMIT = 100

# Pause zwischen Requests
REQUEST_DELAY = 5

# Timeout für Playwright-Navigation/Warten (ms)
PW_TIMEOUT = 15000

BASE_URL = "https://www.20min.ch"

COMMENT_API = (
    "https://api.20min.ch/comment/v1/comments"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/153.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "de-CH,de;q=0.9,en;q=0.8",
}

COMMENT_HEADERS = {
    **HEADERS,
    "Accept": "application/json",
    "Origin": "https://www.20min.ch",
    "Referer": "https://www.20min.ch/",
}


# ============================================================
# SESSION (für Artikel-HTML + Kommentar-API; kein JS nötig dort)
# ============================================================

session = requests.Session()
session.headers.update(HEADERS)


# ============================================================
# HILFSFUNKTIONEN
# ============================================================

def clean_text(value):

    if value is None:
        return None

    return re.sub(
        r"\s+",
        " ",
        str(value)
    ).strip()


def now_utc():

    return datetime.now(
        timezone.utc
    ).isoformat()


def save_json(data):

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )


# ============================================================
# ARTICLE ID AUS URL
# ============================================================

def extract_content_id(url):

    """
    Beispiel:

    https://www.20min.ch/story/
    nach-preiserhoehung-...-103609886

    -> 103609886
    """

    match = re.search(
        r"-(\d+)(?:[/?#]|$)",
        url
    )

    if match:
        return match.group(1)

    # Fallback: letzte Nummer in URL
    match = re.search(
        r"/(\d+)(?:[/?#]|$)",
        url
    )

    if match:
        return match.group(1)

    return None


# ============================================================
# ARTIKEL-SUCHE (Playwright, JS-gerendert)
# ============================================================

# Passe diesen Selektor bei Bedarf an den tatsächlichen
# Ergebnis-Container an (per DevTools -> Rechtsklick auf einen
# Treffer -> "Untersuchen" -> im Elementbaum nach oben zum
# umschliessenden Container gehen). Standard: ganze Seite ("body"),
# da der Titel-Filter (is_relevant) bereits zuverlässig irrelevante
# Treffer aussortiert und ein falscher Container sonst zu 0
# Ergebnissen führt, ohne dass das auffällt.
RESULTS_CONTAINER_SELECTOR = "body"

# Bekannte Bereiche, die fälschlicherweise /story/-Links enthalten
# können, obwohl sie NICHT zu den Suchergebnissen gehören.
# Falls RESULTS_CONTAINER_SELECTOR nicht präzise genug scopen kann,
# werden Links, die innerhalb dieser Selektoren liegen, zusätzlich
# ausgeschlossen.
EXCLUDE_CONTAINER_SELECTORS = [
    "[data-testid='most-read']",
    "[class*='meistgelesen']",
    "[class*='empfehlung']",
    "[class*='recommendation']",
    "nav",
    "footer",
    "header",
]


def collect_story_links(page):

    """
    Extrahiert /story/-Links NUR innerhalb des Ergebnis-Containers,
    unter Ausschluss bekannter Nicht-Ergebnis-Bereiche.
    """

    anchors = page.eval_on_selector_all(
        f"{RESULTS_CONTAINER_SELECTOR} a[href*='/story/']",
        """
        (els, excludeSelectors) => {
            const isExcluded = (el) => {
                for (const sel of excludeSelectors) {
                    if (el.closest(sel)) return true;
                }
                return false;
            };

            return els
                .filter(e => !isExcluded(e))
                .map(e => ({
                    href: e.getAttribute('href'),
                    text: e.innerText
                }));
        }
        """,
        EXCLUDE_CONTAINER_SELECTORS,
    )

    return anchors


def is_relevant(title, search_term):

    """
    Zusätzlicher Relevanz-Check: prüft, ob der VOLLSTÄNDIGE
    Suchbegriff (als zusammenhängender Substring, case-insensitive)
    im Titel vorkommt -- nicht nur ein einzelnes Wort davon.

    Grund: 20min liefert bei der Suche teils generische/verwandte
    Treffer zurück, auch wenn es keine echten Treffer für den
    Begriff gibt (z.B. "100 Treffer" trotz irrelevanter Ergebnisse).
    Ein einzelnes übereinstimmendes Wort (z.B. "mobile" bei
    "coop mobile") reicht daher NICHT mehr aus.

    Gibt bei leerem/None-Titel bewusst False zurück -- ohne
    Linktext lässt sich Relevanz nicht bestätigen, und der
    finale Metadaten-Check (siehe main()) entscheidet ohnehin
    nochmals anhand des echten Artikel-Titels/-Teasers.
    """

    if not title:
        return False

    return search_term.lower().strip() in title.lower()


def search_20min(search_term, browser):

    print()
    print("=" * 70)
    print(f"SEARCH: {search_term}")
    print("=" * 70)

    articles = []
    seen_urls = set()

    search_url = (
        f"{BASE_URL}/search"
        f"?q={quote(search_term)}"
    )

    print(f"Opening: {search_url}")

    page = browser.new_page(
        user_agent=HEADERS["User-Agent"],
        locale="de-CH",
    )

    try:

        page.goto(
            search_url,
            timeout=PW_TIMEOUT,
            wait_until="domcontentloaded",
        )

        # Auf erste Ergebnisse warten
        try:
            page.wait_for_selector(
                "a[href*='/story/']",
                timeout=PW_TIMEOUT,
            )
        except Exception:
            print("  Keine Ergebnisse-Links gefunden (Timeout).")

        # ------------------------------------------------
        # DIAGNOSE: Gesamtzahl /story/-Links auf der Seite
        # vs. innerhalb des gescopten Containers. Hilft zu
        # erkennen, ob RESULTS_CONTAINER_SELECTOR zu eng ist.
        # ------------------------------------------------
        try:
            total_links = page.eval_on_selector_all(
                "a[href*='/story/']", "els => els.length"
            )
            scoped_links = page.eval_on_selector_all(
                f"{RESULTS_CONTAINER_SELECTOR} a[href*='/story/']",
                "els => els.length",
            )
            print(
                f"  DEBUG: {total_links} /story/-Links total, "
                f"{scoped_links} davon im Container "
                f"'{RESULTS_CONTAINER_SELECTOR}'"
            )
            if total_links > 0 and scoped_links == 0:
                print(
                    "  WARNUNG: RESULTS_CONTAINER_SELECTOR trifft "
                    "den Ergebnisbereich nicht -> Selektor prüfen!"
                )
        except Exception as e:
            print(f"  DEBUG-Fehler: {e}")

        # Cookie-Banner wegklicken (falls vorhanden)
        for selector in [
            "button:has-text('Akzeptieren')",
            "button:has-text('Alle akzeptieren')",
            "#onetrust-accept-btn-handler",
        ]:
            try:
                if page.is_visible(selector, timeout=1000):
                    page.click(selector, timeout=1000)
                    page.wait_for_timeout(500)
                    break
            except Exception:
                pass

        stagnant_rounds = 0
        prev_count = 0

        for round_idx in range(MAX_SEARCH_PAGES):

            anchors = collect_story_links(page)

            new_in_round = 0
            skipped_by_title = 0

            for a in anchors:

                href = a.get("href")

                if not href:
                    continue

                if href.startswith("/"):
                    url = BASE_URL + href
                elif href.startswith(BASE_URL + "/story/"):
                    url = href
                else:
                    continue

                url = url.split("?")[0].split("#")[0]

                if url in seen_urls:
                    continue

                content_id = extract_content_id(url)

                if not content_id:
                    continue

                title = clean_text(a.get("text"))

                if not is_relevant(title, search_term):
                    skipped_by_title += 1
                    continue

                articles.append({
                    "url": url,
                    "content_id": content_id,
                    "title": title,
                    "search_terms": [search_term],
                })

                seen_urls.add(url)
                new_in_round += 1

            print(
                f"  Round {round_idx + 1}: "
                f"+{new_in_round} (total {len(articles)}), "
                f"{skipped_by_title} wegen Titel-Filter übersprungen"
            )

            if len(articles) == prev_count:
                stagnant_rounds += 1
            else:
                stagnant_rounds = 0

            prev_count = len(articles)

            if stagnant_rounds >= 2:
                # Zwei Runden ohne neue Artikel -> fertig
                break

            # "Mehr laden" / Paginierungs-Button versuchen
            clicked = False

            for selector in [
                "button:has-text('Mehr laden')",
                "button:has-text('Mehr anzeigen')",
                "[data-testid='load-more']",
            ]:
                try:
                    if page.is_visible(selector, timeout=1000):
                        page.click(selector, timeout=1000)
                        clicked = True
                        break
                except Exception:
                    pass

            if not clicked:
                # Fallback: ans Seitenende scrollen (Infinite Scroll)
                page.mouse.wheel(0, 3000)

            page.wait_for_timeout(int(REQUEST_DELAY * 1000) + 800)

    except Exception as e:

        print(f"  ERROR search: {e}")

    finally:

        page.close()

    print(f"Total for '{search_term}': {len(articles)}")

    return articles


# ============================================================
# ARTIKEL SEITE (statisches HTML reicht für Metadaten)
# ============================================================

def get_article(url):

    try:

        response = session.get(
            url,
            timeout=30
        )

        response.raise_for_status()

        return response.text

    except Exception as e:

        print(
            f"  Article error: {e}"
        )

        return None


# ============================================================
# ARTIKEL-METADATEN
# ============================================================

def extract_metadata(
    html,
    url
):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    title = None
    description = None
    published = None

    # --------------------------------------------------------
    # OpenGraph
    # --------------------------------------------------------

    tag = soup.find(
        "meta",
        property="og:title"
    )

    if tag:
        title = tag.get(
            "content"
        )

    tag = soup.find(
        "meta",
        property="og:description"
    )

    if tag:
        description = tag.get(
            "content"
        )

    # --------------------------------------------------------
    # JSON-LD
    # --------------------------------------------------------

    for script in soup.find_all(
        "script",
        type="application/ld+json"
    ):

        try:

            raw = (
                script.string
                or script.get_text()
            )

            data = json.loads(raw)

            if isinstance(
                data,
                list
            ):

                items = data

            else:

                items = [data]

            for item in items:

                if not isinstance(
                    item,
                    dict
                ):
                    continue

                if not title:

                    title = item.get(
                        "headline"
                    )

                if not description:

                    description = item.get(
                        "description"
                    )

                if not published:

                    published = item.get(
                        "datePublished"
                    )

        except Exception:
            pass

    return {
        "url": url,
        "title": clean_text(title),
        "description": clean_text(
            description
        ),
        "published": published
    }


# ============================================================
# EINEN KOMMENTAR-REQUEST MACHEN
# ============================================================

def get_comments_page(
    content_id,
    offset=0
):

    params = {
        "tenantId": 6,
        "contentId": content_id,
        "limit": COMMENT_LIMIT,
        "sortBy": "highlighted",
        "sortOrder": "desc",
    }

    if offset > 0:
        params["offset"] = offset

    try:

        response = session.get(
            COMMENT_API,
            params=params,
            headers=COMMENT_HEADERS,
            timeout=30
        )

        response.raise_for_status()

        return response.json()

    except Exception as e:

        print(
            f"    Comment API error "
            f"(offset={offset}): {e}"
        )

        return None


# ============================================================
# ALLE KOMMENTARE HOLEN
# ============================================================

def get_all_comments(content_id):

    comments = []

    offset = 0

    while True:

        print(
            f"    Loading comments "
            f"offset={offset}"
        )

        data = get_comments_page(
            content_id,
            offset
        )

        if not data:
            break

        page_comments = data.get(
            "comments",
            []
        )

        comments.extend(
            page_comments
        )

        print(
            f"      received: "
            f"{len(page_comments)}"
        )

        # ----------------------------------------------------
        # nextLink verwenden
        # ----------------------------------------------------

        next_link = data.get(
            "nextLink"
        )

        if not next_link:
            break

        # ----------------------------------------------------
        # Offset aus nextLink
        # ----------------------------------------------------

        match = re.search(
            r"[?&]offset=(\d+)",
            next_link
        )

        if match:

            new_offset = int(
                match.group(1)
            )

        else:

            break

        if new_offset == offset:
            break

        offset = new_offset

        time.sleep(
            REQUEST_DELAY
        )

    return comments


# ============================================================
# KOMMENTARE FLACH ZUSAMMENFASSEN
# ============================================================

def count_all_comments(comments):

    total = 0

    for comment in comments:

        total += 1

        replies = comment.get(
            "replies",
            []
        )

        total += len(
            replies
        )

    return total


# ============================================================
# HAUPTPROGRAMM
# ============================================================

def main():

    print()
    print("=" * 70)
    print("20MIN.CH ARTICLE + COMMENT SCRAPER")
    print("=" * 70)

    # --------------------------------------------------------
    # 1. ARTIKEL SAMMELN (via Playwright / JS-Rendering)
    # --------------------------------------------------------

    articles_by_url = {}

    with sync_playwright() as p:

        browser = p.chromium.launch(headless=True)

        try:

            for search_term in SEARCH_TERMS:

                found = search_20min(
                    search_term,
                    browser,
                )

                for article in found:

                    url = article["url"]

                    if url not in articles_by_url:

                        articles_by_url[url] = article

                    else:

                        # Wenn derselbe Artikel bei
                        # mehreren Suchbegriffen erscheint,
                        # Suchbegriffe zusammenführen.

                        existing = (
                            articles_by_url[url]
                        )

                        if search_term not in (
                            existing["search_terms"]
                        ):

                            existing[
                                "search_terms"
                            ].append(
                                search_term
                            )

        finally:

            browser.close()

    articles = list(
        articles_by_url.values()
    )

    print()
    print("=" * 70)
    print(
        f"UNIQUE ARTICLES: {len(articles)}"
    )
    print("=" * 70)

    # --------------------------------------------------------
    # Ergebnis
    # --------------------------------------------------------

    results = []

    # --------------------------------------------------------
    # 2. ARTIKEL VERARBEITEN
    # --------------------------------------------------------

    for index, article in enumerate(
        articles,
        start=1
    ):

        print()
        print("-" * 70)
        print(
            f"[{index}/{len(articles)}]"
        )
        print(
            article["url"]
        )

        content_id = article[
            "content_id"
        ]

        # ----------------------------------------------------
        # Artikel laden
        # ----------------------------------------------------

        html = get_article(
            article["url"]
        )

        metadata = {}

        if html:

            metadata = extract_metadata(
                html,
                article["url"]
            )

        # ----------------------------------------------------
        # Finaler Relevanz-Check anhand echter Metadaten
        # (Titel + Beschreibung), um False Positives aus der
        # Linksammlung endgültig auszusortieren.
        # ----------------------------------------------------

        # ----------------------------------------------------
        # Finaler Relevanz-Check anhand des echten Artikel-Titels.
        # Der Suchbegriff muss als vollständiger Substring im
        # Titel vorkommen -- sortiert generische/verwandte
        # Treffer aus, die 20min trotz "100 Treffer"-Anzeige
        # ohne echten Bezug zurückgibt.
        # ----------------------------------------------------

        article_title = (metadata.get("title") or "").lower()

        matches_any_term = any(
            term.lower().strip() in article_title
            for term in article["search_terms"]
        )

        if article_title and not matches_any_term:

            print(
                "    SKIP (Suchbegriff nicht im Titel): "
                f"{metadata.get('title')}"
            )

            continue

        # ----------------------------------------------------
        # Kommentare
        # ----------------------------------------------------

        comments = get_all_comments(
            content_id
        )

        total_comments = (
            count_all_comments(
                comments
            )
        )

        print(
            f"    Total comments + replies: "
            f"{total_comments}"
        )

        # ----------------------------------------------------
        # Ergebnisobjekt
        # ----------------------------------------------------

        result = {

            "source": "20min",

            "content_id":
                content_id,

            "search_terms":
                article[
                    "search_terms"
                ],

            "article": metadata,

            "comments": comments,

            "comment_count":
                len(comments),

            "comment_and_reply_count":
                total_comments,

            "scraped_at":
                now_utc()
        }

        results.append(
            result
        )

        # ----------------------------------------------------
        # SOFORT SPEICHERN
        # ----------------------------------------------------

        save_json(
            results
        )

        time.sleep(
            REQUEST_DELAY
        )

    # --------------------------------------------------------
    # FINAL
    # --------------------------------------------------------

    total_comments = sum(
        x["comment_and_reply_count"]
        for x in results
    )

    print()
    print("=" * 70)
    print("FINISHED")
    print("=" * 70)

    print(
        f"Articles:  {len(results)}"
    )

    print(
        f"Comments:  {total_comments}"
    )

    print(
        f"Output:    {OUTPUT_FILE}"
    )

    print("=" * 70)


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()
