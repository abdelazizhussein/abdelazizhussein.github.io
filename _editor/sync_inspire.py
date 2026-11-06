"""Add new papers from your INSPIRE-HEP profile to the homepage.

Run from the repo root:   python3 _editor/sync_inspire.py
A GitHub Action also runs it every day (.github/workflows/sync-inspire.yml).

It adds papers that are on INSPIRE but not on the site, and fills in the journal,
DOI and arXiv number once INSPIRE has them. It never removes or rewrites a paper
that's already there, so hand edits, hidden papers and papers that aren't on
INSPIRE stay as they are. To drop a paper, hide it in the editor (untick "Show")
rather than deleting it, or the next sync will add it back.
"""
import datetime, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server  # noqa: E402

SITEMAP = os.path.join(server.REPO, "sitemap.xml")


def bump_sitemap():
    """Set the homepage's <lastmod> in sitemap.xml to today."""
    s = open(SITEMAP, encoding="utf-8").read()
    today = datetime.date.today().isoformat()
    s = re.sub(r"(<loc>https://abdelazizhussein\.github\.io/</loc><lastmod>)[^<]*", r"\g<1>" + today, s)
    open(SITEMAP, "w", encoding="utf-8").write(s)


def main():
    m = json.load(open(server.RESEARCH_DATA, encoding="utf-8"))
    author = m["me"].get("inspire")
    if not author:
        sys.exit('No INSPIRE author ID: add "inspire" under "me" in _editor/research.json')
    found = server.fetch_inspire(author)
    added, updated = server.merge_publications(m, found)
    if not (added or updated):
        print(f"Up to date ({len(found)} papers on INSPIRE)")
        return
    server.write_research(m)
    bump_sitemap()
    for p in added:
        print(f"New: {p['title']} ({'arXiv:' + p['arxiv'] if p['arxiv'] else p['doi']})")
    for p in updated:
        print(f"Updated: {p['title']} ({p['venue'] or p['doi'] or 'arXiv:' + p['arxiv']})")


if __name__ == "__main__":
    main()
