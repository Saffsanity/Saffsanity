"""Pull the current Sill numbers shown on the resume.

    python3 scripts/fetch_stats.py [resume_dir]

Prints JSON with the raw numbers and the resume-style display values.
Secrets (API keys, App Store Connect IDs, vendor number) are read from
files in resume_dir that are kept out of git; see config.example.json.

Needs: curl, openssl, and the GitHub CLI (gh) signed in.
HTTP goes through curl because some Python installs on macOS lack CA certs.
"""
import datetime as dt
import gzip
import json
import math
import os
import subprocess
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from asc_jwt import make_token  # noqa: E402

# Public identifiers (not secrets).
GITHUB_OWNER = "Saffsanity"
GITHUB_REPO = "Saffsanity/sill"
APP_STORE_APP_ID = "6816359860"
YOUTUBE_CHANNEL_ID = "UC53v6R2VJhB1AbQgCx4adQg"
LAUNCH_DATE = dt.date(2026, 10, 9)  # first day with App Store sales


def curl(url, headers=None, binary=False):
    cmd = ["curl", "-s", "-w", "\n%{http_code}", url]
    for k, v in (headers or {}).items():
        cmd[1:1] = ["-H", f"{k}: {v}"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    body, _, code = raw.rpartition(b"\n")
    return int(code), (body if binary else body.decode())


def gh_lines(path, jq):
    out = subprocess.run(["gh", "api", path, "--paginate", "--jq", jq],
                         capture_output=True, text=True, check=True).stdout
    return [line for line in out.splitlines() if line]


# ---------------------------------------------------------------- GitHub

def github_stats():
    stars = int(gh_lines(f"repos/{GITHUB_REPO}", ".stargazers_count")[0])
    # "Community contributors" = unique PR authors other than the owner and bots.
    authors = set(gh_lines(f"repos/{GITHUB_REPO}/pulls?state=all&per_page=100",
                           ".[] | .user.login"))
    contributors = len({a for a in authors
                        if a != GITHUB_OWNER and not a.endswith("[bot]")})
    # "Mac downloads" = .dmg + .zip downloads on stable (v*) releases.
    counts = gh_lines(
        f"repos/{GITHUB_REPO}/releases?per_page=100",
        '.[] | select(.tag_name|startswith("v")) | .assets[]'
        ' | select(.name|test("\\\\.(dmg|zip)$")) | .download_count')
    mac_downloads = sum(int(c) for c in counts)
    return {"stars": stars, "contributors": contributors,
            "mac_downloads": mac_downloads}


# ---------------------------------------------------------------- App Store rating

def itunes_rating():
    code, body = curl(f"https://itunes.apple.com/lookup?id={APP_STORE_APP_ID}&country=us")
    r = json.loads(body)["results"][0]
    return {"rating": r["averageUserRating"], "reviews": r["userRatingCount"]}


# ---------------------------------------------------------------- YouTube

def youtube_views(api_key):
    q = urllib.parse.urlencode
    base = "https://www.googleapis.com/youtube/v3"
    _, body = curl(f"{base}/channels?" + q({"part": "contentDetails",
                                            "id": YOUTUBE_CHANNEL_ID, "key": api_key}))
    uploads = json.loads(body)["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, token = [], None
    while True:
        params = {"part": "contentDetails", "maxResults": 50,
                  "playlistId": uploads, "key": api_key}
        if token:
            params["pageToken"] = token
        page = json.loads(curl(f"{base}/playlistItems?" + q(params))[1])
        ids += [i["contentDetails"]["videoId"] for i in page["items"]]
        token = page.get("nextPageToken")
        if not token:
            break
    total = 0
    for i in range(0, len(ids), 50):
        _, body = curl(f"{base}/videos?" + q({"part": "statistics",
                                              "id": ",".join(ids[i:i + 50]),
                                              "key": api_key}))
        total += sum(int(v["statistics"].get("viewCount", 0))
                     for v in json.loads(body)["items"])
    return {"youtube_views": total, "youtube_videos": len(ids)}


# ---------------------------------------------------------------- App Store Connect

def asc_ios_users(cfg, resume_dir):
    """First-time iPhone + iPad downloads (type 1F) summed over daily sales reports.

    Reports are cached in .cache/sales (gitignored). Apple publishes each day's
    report the following day, so the newest day may be missing.
    """
    token = make_token(os.path.join(resume_dir, cfg["asc_key_file"]),
                       cfg["asc_key_id"], cfg["asc_issuer_id"])
    cache = os.path.join(resume_dir, ".cache", "sales")
    os.makedirs(cache, exist_ok=True)
    day, last_day, total = LAUNCH_DATE, None, 0
    yesterday = dt.date.today() - dt.timedelta(days=1)
    while day <= yesterday:
        path = os.path.join(cache, f"{day}.tsv")
        if not os.path.exists(path):
            params = urllib.parse.urlencode({
                "filter[frequency]": "DAILY", "filter[reportType]": "SALES",
                "filter[reportSubType]": "SUMMARY", "filter[version]": "1_0",
                "filter[vendorNumber]": cfg["asc_vendor_number"],
                "filter[reportDate]": str(day)})
            code, body = curl("https://api.appstoreconnect.apple.com/v1/salesReports?" + params,
                              {"Authorization": f"Bearer {token}",
                               "Accept": "application/a-gzip"}, binary=True)
            if code == 404:  # no sales that day, or not published yet
                day += dt.timedelta(days=1)
                continue
            if code != 200:
                raise RuntimeError(f"sales report {day}: HTTP {code}")
            with open(path, "wb") as f:
                f.write(gzip.decompress(body))
        with open(path) as f:
            rows = [line.rstrip("\n").split("\t") for line in f][1:]
        for r in rows:
            # 14 = Apple Identifier, 6 = Product Type, 7 = Units, 22 = Device
            if r[14] == APP_STORE_APP_ID and r[6] == "1F" and r[22] in ("iPhone", "iPad"):
                total += int(r[7])
        last_day = day
        day += dt.timedelta(days=1)
    return {"ios_users": total, "ios_users_through": str(last_day)}


# ---------------------------------------------------------------- formatting

def floor_to(n, step):
    return n // step * step


def display(s):
    """Resume-style values. Rounds down so the resume never overstates."""
    d = {
        "stars": f"{floor_to(s['stars'], 100):,}+",
        "contributors": str(s["contributors"]),
        "mac_downloads": f"{s['mac_downloads'] // 1000}K+",
        "rating": f"{math.floor(s['rating'] * 10) / 10:.1f} stars",
        "reviews": f"{s['reviews']} reviews",
        "youtube_views": f"{s['youtube_views'] // 1000}K",
    }
    if "ios_users" in s:
        d["ios_users"] = f"{s['ios_users'] // 1000}K+"
    return d


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    resume_dir = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, ".."))
    with open(os.path.join(resume_dir, "config.local.json")) as f:
        cfg = json.load(f)
    with open(os.path.join(resume_dir, cfg["youtube_key_file"])) as f:
        yt_key = f.read().strip()

    stats = {"fetched_at": dt.datetime.now().isoformat(timespec="seconds")}
    stats.update(github_stats())
    stats.update(itunes_rating())
    stats.update(youtube_views(yt_key))
    stats.update(asc_ios_users(cfg, resume_dir))
    print(json.dumps({"raw": stats, "display": display(stats)}, indent=2))


if __name__ == "__main__":
    main()
