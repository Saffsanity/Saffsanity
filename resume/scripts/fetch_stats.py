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


def curl(url, headers=None, binary=False, compressed=False):
    cmd = ["curl", "-s", "--max-time", "60", "-w", "\n%{http_code}", url]
    for k, v in (headers or {}).items():
        cmd[1:1] = ["-H", f"{k}: {v}"]
    if compressed:  # some storefronts send gzip whether or not it was asked for
        cmd.insert(1, "--compressed")
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

def storefronts(token):
    """Two-letter codes for every App Store territory, from App Store Connect.

    ASC lists territories as ISO alpha-3; the iTunes Lookup API wants alpha-2,
    so map them with macOS's ICU library.
    """
    import ctypes
    icu = ctypes.CDLL("/usr/lib/libicucore.dylib")
    iso3 = icu.uloc_getISO3Country
    iso3.restype, iso3.argtypes = ctypes.c_char_p, [ctypes.c_char_p]
    alpha2 = {}
    for a in (chr(x) + chr(y) for x in range(65, 91) for y in range(65, 91)):
        alpha2.setdefault(iso3(f"en_{a}".encode()).decode(), a)
    alpha2["XKS"] = "XK"  # Kosovo isn't in ICU's table
    code, body = curl("https://api.appstoreconnect.apple.com/v1/territories?limit=200",
                      {"Authorization": f"Bearer {token}"})
    if code != 200:
        raise RuntimeError(f"territories: HTTP {code}")
    terrs = [t["id"] for t in json.loads(body)["data"]]
    missing = [t for t in terrs if t not in alpha2]
    if missing:
        raise RuntimeError(f"no alpha-2 code for territories {missing}")
    return sorted(alpha2[t] for t in terrs)


def itunes_rating(token):
    """Worldwide rating count and average: iTunes Lookup summed over every storefront.

    Each storefront only reports its own ratings, so the count is the sum and the
    average is weighted by each storefront's count.
    """
    total = weighted = 0
    for c in storefronts(token):
        url = f"https://itunes.apple.com/lookup?id={APP_STORE_APP_ID}&country={c.lower()}"
        for _ in range(3):
            code, body = curl(url, compressed=True)
            if code == 200:
                break
        if code != 200:
            raise RuntimeError(f"iTunes lookup {c}: HTTP {code}")
        results = json.loads(body)["results"]
        n = results[0].get("userRatingCount", 0) if results else 0
        if n:
            total += n
            weighted += n * results[0]["averageUserRating"]
    return {"rating": weighted / total, "reviews": total}


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
    views = likes = 0
    for i in range(0, len(ids), 50):
        _, body = curl(f"{base}/videos?" + q({"part": "statistics",
                                              "id": ",".join(ids[i:i + 50]),
                                              "key": api_key}))
        for v in json.loads(body)["items"]:
            views += int(v["statistics"].get("viewCount", 0))
            likes += int(v["statistics"].get("likeCount", 0))  # missing if likes are hidden
    return {"youtube_views": views, "youtube_likes": likes, "youtube_videos": len(ids)}


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


def floor_sig(x, sig=3):
    """Round down to `sig` significant figures (4.9249 -> 4.92, 1234 -> 1230)."""
    if x <= 0:
        return x
    step = 10 ** (math.floor(math.log10(x)) - sig + 1)
    return math.floor(x / step + 1e-9) * step


def display(s):
    """Resume-style values. Rounds down so the resume never overstates."""
    d = {
        "stars": f"{floor_to(s['stars'], 100):,}+",
        "contributors": str(s["contributors"]),
        "mac_downloads": f"{s['mac_downloads'] // 1000}K+",
        "rating": f"{floor_sig(s['rating']):.2f} stars",
        "reviews": (f"{s['reviews']} reviews" if s["reviews"] < 1000
                    else f"{int(floor_sig(s['reviews'])):,}+ reviews"),
        "youtube_views": f"{s['youtube_views'] // 1000}K",
        "youtube_likes": f"{s['youtube_likes'] // 1000}K likes",
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
    token = make_token(os.path.join(resume_dir, cfg["asc_key_file"]),
                       cfg["asc_key_id"], cfg["asc_issuer_id"])
    stats.update(itunes_rating(token))
    stats.update(youtube_views(yt_key))
    stats.update(asc_ios_users(cfg, resume_dir))
    print(json.dumps({"raw": stats, "display": display(stats)}, indent=2))


if __name__ == "__main__":
    main()
