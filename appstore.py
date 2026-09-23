import requests
import json
import time

APPS = [
    ("mywingo", "wingo", "1673683621"),
    ("wingo tv", "wingo", "6463395406"),

    ("myswisscom", "swisscom", "444087594"),
    ("blue tv", "swisscom", "798597407"),

    ("my yallo", "yallo", "1365009736"),
    ("yallo tv", "yallo", "1569382476"),

    ("spusu", "spusu", "6473386899"),

    ("mysunrise", "sunrise", "466738063"),
    ("sunrise tv", "sunrise", "1292688012"),

    ("salt", "salt", "969561743"),
    ("salt tv", "salt", "1258680285"),

    ("quickline tv", "quickline", "1157724348"),

    ("coop mobile", "coop mobile", "6737056226"),

    ("chmobile", "chmobile", "6755728316"),
]

all_rows = []

for app_name, provider, app_id in APPS:

    print(f"Lade {app_name}")

    reviews = []
    page = 1

    while True:

        url = (
            f"https://itunes.apple.com/ch/rss/customerreviews/"
            f"page={page}/id={app_id}/sortby=mostrecent/json"
        )

        try:

            response = requests.get(
                url,
                timeout=30,
                headers={
                    "User-Agent": "Mozilla/5.0"
                }
            )

            if response.status_code != 200:
                break

            data = response.json()

            feed = data.get("feed", {})
            entries = feed.get("entry", [])

            page_reviews = [
                entry
                for entry in entries
                if "im:rating" in entry
            ]

            if not page_reviews:
                break

            reviews.extend(page_reviews)

            print(
                f"  Seite {page}: "
                f"{len(page_reviews)} Reviews"
            )

            page += 1

            time.sleep(0.5)

        except Exception as e:

            print(
                f"Fehler {app_id}: {e}"
            )

            break

    seen = set()

    for review in reviews:

        review_id = (
            review.get("id", {})
            .get("label")
        )

        if review_id in seen:
            continue

        seen.add(review_id)

        all_rows.append({
            "app_name": app_name,
            "provider": provider,
            "app_id": app_id,
            "language": "n/a",
            "review_id": review_id,
            "user": (
                review.get("author", {})
                .get("name", {})
                .get("label")
            ),
            "score": (
                review.get("im:rating", {})
                .get("label")
            ),
            "date": (
                review.get("updated", {})
                .get("label")
            ),
            "title": (
                review.get("title", {})
                .get("label")
            ),
            "content": (
                review.get("content", {})
                .get("label")
            ),
            "thumbs_up": None,
            "app_version": (
                review.get("im:version", {})
                .get("label")
            ),
            "reply": None
        })

all_rows.sort(
    key=lambda x: x.get("date", ""),
    reverse=True
)

with open(
    "reviews.json",
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        all_rows,
        f,
        ensure_ascii=False,
        indent=2
    )

print(
    f"reviews.json erstellt "
    f"({len(all_rows)} Reviews)"
)
