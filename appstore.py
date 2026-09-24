import os
import json
import time
import requests

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
# OUTPUT LOCATION
# --------------------------------------------------

REPO_ROOT = os.getenv("GITHUB_WORKSPACE", os.getcwd())
OUTPUT_JSON = os.path.join(REPO_ROOT, "reviews.json")

print(f"Repository root: {REPO_ROOT}")
print(f"Output file: {OUTPUT_JSON}")

# --------------------------------------------------
# DOWNLOAD REVIEWS
# --------------------------------------------------

all_reviews = []

for app_name, provider, app_id in APPS:

    print("=" * 60)
    print(f"App: {app_name}")
    print("=" * 60)

    page = 1
    seen = set()

    while True:

        url = (
            f"https://itunes.apple.com/ch/rss/customerreviews/"
            f"page={page}/id={app_id}/sortby=mostrecent/json"
        )

        try:

            response = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=30
            )

            if response.status_code != 200:
                break

            feed = response.json().get("feed", {})
            entries = feed.get("entry", [])

            reviews = [
                entry for entry in entries
                if "im:rating" in entry
            ]

            if not reviews:
                break

            print(f"Page {page}: {len(reviews)} reviews")

            for review in reviews:

                review_id = review.get("id", {}).get("label")

                if not review_id or review_id in seen:
                    continue

                seen.add(review_id)

                all_reviews.append({
                    "AppName": app_name,
                    "Provider": provider,
                    "AppID": app_id,
                    "ReviewID": review_id,
                    "UserName": review.get("author", {})
                                     .get("name", {})
                                     .get("label"),
                    "Score": review.get("im:rating", {})
                                   .get("label"),
                    "Date": review.get("updated", {})
                                  .get("label"),
                    "Title": review.get("title", {})
                                   .get("label"),
                    "Content": review.get("content", {})
                                     .get("label"),
                    "AppVersion": review.get("im:version", {})
                                        .get("label")
                })

            page += 1
            time.sleep(0.5)

        except Exception as e:
            print(f"Error: {e}")
            break

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

with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
    json.dump(
        all_reviews,
        f,
        ensure_ascii=False,
        indent=2
    )

print("\nFinished")
print(f"Reviews collected: {len(all_reviews)}")
print(f"JSON created: {OUTPUT_JSON}")
print(f"File exists: {os.path.exists(OUTPUT_JSON)}")
