# SCImago snapshot

`scimagojr-2025.csv.gz` is the SCImago Journal & Country Rank "Download data"
CSV for 2025 (https://www.scimagojr.com/journalrank.php), gzip-compressed and
otherwise unchanged. Source: SCImago (n.d.), SJR — SCImago Journal & Country
Rank, retrieved from https://www.scimagojr.com; the indicators are computed
from Scopus data.

`journal_cli.py` reads it when no newer file was imported with `sjr-import`.
To refresh it, download the new year's CSV and replace this file with
`gzip -9 -n -c scimagojr-<year>.csv > scimagojr-<year>.csv.gz`.
