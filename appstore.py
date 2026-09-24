import requests
import json
import time
from pathlib import Path

# --------------------------------------------------
# APPS
# --------------------------------------------------

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

# --------------------------------------------------
# OUTPUT
# --------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
OUTPUT_JSON = SCRIPT_DIR / "reviews.json"

# --------------------------------------------------
# DOWNLOAD REVIEWS
# --------------------------------------------------

all_reviews = []

for app_name, provider, app_id in APPS:

    print("\n" + "=" * 60)
    print(f"App: {app_name}")
    print(f"Provider: {provider}")
    print(f"ID: {app_id}")
    print("=" * 60)

    page = 1
    app_reviews = []

    while True:

        url = (
            f"https://itunes.apple.com/ch/rss/customerreviews/"
            f"page={page}/id={app_id}/sortby=mostrecent/json"
        )

        print(f"Page {page}")

        try:
            response = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=30
            )

            if response.status_code != 200:
                print("No more pages.")
                break

            data = response.json()
            entries = data.get("feed", {}).get("entry", [])

            reviews = [
                e for e in entries
                if "im:rating" in e
            ]

            if not reviews:
                print("No more reviews.")
                break

            print(f"  -> {len(reviews)} reviews")

            app_reviews.extend(reviews)

            page += 1
            time.sleep(0.5)

        except Exception as e:
            print(f"Error: {e}")
            break

    # --------------------------------------------------
    # REMOVE DUPLICATES
    # --------------------------------------------------

    seen = set()

    for review in app_reviews:

        review_id = review.get("id", {}).get("label")

        if not review_id or review_id in seen:
            continue

        seen.add(review_id)

        all_reviews.append({
            "AppName": app_name,
            "Provider": provider,
            "AppID": app_id,
            "ReviewID": review_id,
            "UserName": review.get("author", {}).get("name", {}).get("label"),
            "Score": review.get("im:rating", {}).get("label"),
            "Date": review.get("updated", {}).get("label"),
            "Title": review.get("title", {}).get("label"),
            "Content": review.get("content", {}).get("label"),
            "AppVersion": review.get("im:version", {}).get("label"),
        })

# --------------------------------------------------
# SORT
# --------------------------------------------------

all_reviews.sort(
    key=lambda x: x.get("Date", ""),
    reverse=True
)

# --------------------------------------------------
# SAVE JSON
# --------------------------------------------------

with open(
    OUTPUT_JSON,
    "w",
    encoding="utf-8"
) as f:
    json.dump(
        all_reviews,
        f,
        ensure_ascii=False,
        indent=2
    )

# --------------------------------------------------
# FINISHED
# --------------------------------------------------

print("\n" + "=" * 60)
print("FINISHED")
print(f"Total reviews: {len(all_reviews)}")
print(f"JSON file: {OUTPUT_JSON}")
print("=" * 60)
