import requests
import json
import time
from datetime import datetime

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

OUTPUT_FILE = "reviews.json"

all_rows = []

# --------------------------------------------------
# DOWNLOAD REVIEWS
# --------------------------------------------------

for app_name, provider, app_id in APPS:

    print(f"\nProcessing: {app_name}")

    app_reviews = []
    page = 1

    while True:

        url = (
            f"https://itunes.apple.com/ch/rss/customerreviews/"
            f"page={page}/id={app_id}/sortby=mostrecent/json"
        )

        try:

            response = requests.get(url, timeout=30)

            if response.status_code != 200:
                break

            data = response.json()

            feed = data.get("feed", {})
            entries = feed.get("entry", [])

            reviews = [
                entry
                for entry in entries
                if "im:rating" in entry
            ]

            if not reviews:
                break

            app_reviews.extend(reviews)

            print(
                f"  Page {page}: {len(reviews)} reviews"
            )

            page += 1

            time.sleep(0.5)

        except Exception as e:
            print(f"Error: {e}")
            break

    # --------------------------------------------------
    # REMOVE DUPLICATES
    # --------------------------------------------------

    unique_reviews = []
    seen = set()

    for review in app_reviews:

        review_id = review.get(
            "id", {}
        ).get("label")

        if review_id not in seen:
            seen.add(review_id)
            unique_reviews.append(review)

    print(
        f"  Unique reviews: {len(unique_reviews)}"
    )

    # --------------------------------------------------
    # NORMALIZE DATA
    # --------------------------------------------------

    for review in unique_reviews:

        all_rows.append({
            "AppName": app_name,
            "Provider": provider,
            "AppID": app_id,
            "Language": "n/a",
            "ReviewID": review.get("id", {}).get("label"),
            "UserName": review.get("author", {})
                             .get("name", {})
                             .get("label"),
            "Score": review.get("im:rating", {})
                           .get("label"),
            "Date": review.get("updated", {})
                          .get("label"),
            "Content": review.get("content", {})
                             .get("label"),
            "ThumbsUpCount": None,
            "AppVersion": review.get("im:version", {})
                                .get("label"),
            "ReplyContent": None,
            "RepliedAt": None
        })

# --------------------------------------------------
# SORT BY DATE DESC
# --------------------------------------------------

all_rows.sort(
    key=lambda x: x.get("Date", ""),
    reverse=True
)

# --------------------------------------------------
# BUILD RESULT
# --------------------------------------------------

result = {
    "generated_at": datetime.utcnow().isoformat() + "Z",
    "total_reviews": len(all_rows),
    "reviews": all_rows
}

# --------------------------------------------------
# SAVE JSON
# --------------------------------------------------

with open(
    OUTPUT_FILE,
    "w",
    encoding="utf-8"
) as f:
    json.dump(
        result,
        f,
        ensure_ascii=False,
        indent=2
    )

print("\nDone")
print(f"Total Reviews: {len(all_rows)}")
print(f"Output File: {OUTPUT_FILE}")
