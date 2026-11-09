# Resume source

LaTeX source for [`Saffer Resume.pdf`](../Saffer%20Resume.pdf), plus the scripts that keep its Sill numbers up to date.

## Files

| Path | What it is |
|---|---|
| `NoahSafferResume.tex` | The resume |
| `deedy-resume.cls`, `fonts/` | [Deedy Resume](https://github.com/deedy/Deedy-Resume) class with Lato and Raleway (SIL Open Font License) |
| `history/` | Dated copies of the `.tex` from before each update, and a diff for each update |
| `scripts/fetch_stats.py` | Pulls the current numbers and prints them in resume format |
| `scripts/asc_jwt.py` | Makes App Store Connect API tokens (used by `fetch_stats.py`) |
| `scripts/build.sh` | Backs up the `.tex`, renders the PDF, writes diffs |
| `scripts/make_qr.sh`, `scripts/qr_read.swift` | Makes the QR code for the PDF link and checks it scans |
| `config.example.json` | Template for the private `config.local.json` |

## Where the numbers come from

| Resume number | Source | How it's counted |
|---|---|---|
| App Store stars and reviews | iTunes Lookup API | US storefront average, rounded down to one decimal |
| Channel views | YouTube Data API | Views summed across every video on the Sill channel |
| Likes | YouTube Data API | Likes summed across every video on the Sill channel, shown as "(18K likes)" after channel views |
| iOS users | App Store Connect sales reports | First-time downloads (type 1F) on iPhone and iPad since launch |
| Mac downloads | GitHub releases | `.dmg` + `.zip` downloads on stable `v*` releases |
| GitHub stars | GitHub API | Stars on `Saffsanity/sill` |
| Community contributors | GitHub API | Unique pull request authors, not counting the owner or bots |

Counts are rounded down (4,730 stars shows as 4,700+) so the resume never overstates.

## Update steps

Needs `tectonic`, `qrencode` (both from Homebrew), and the GitHub CLI signed in.

1. Copy `config.example.json` to `config.local.json` and fill in the App Store Connect key ID, issuer ID and vendor number. Put the `.p8` key and a text file with the YouTube API key next to it. All of these are gitignored.
2. `scripts/build.sh backup` saves the current `.tex` to `history/` and prints its path.
3. `python3 scripts/fetch_stats.py` prints the latest numbers. Edit `NoahSafferResume.tex` to match.
4. `scripts/build.sh diff history/<backup>.tex` writes a diff for review.
5. `scripts/build.sh` renders `NoahSafferResume.pdf`. Copy it to the repo root as `Saffer Resume.pdf`.

The QR code at the repo root opens the PDF's GitHub page. It stays valid as long as the file name and path don't change. To regenerate it, run `scripts/make_qr.sh`.
