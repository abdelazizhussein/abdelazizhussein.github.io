"""Local editors for the website (not published: Jekyll skips folders starting with "_").

Run from the repo root:   python3 _editor/server.py
Then open:                http://localhost:8765

  /research  edits About Me, Publications and Projects on projects.html
  /blog      edits the text of blogs.html
  /qa        turns answered Q&A emails into cards on qa.html
"""
import base64, html, json, os, re, shutil, urllib.parse, urllib.request
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
RESEARCH_PAGE = os.path.join(REPO, "projects.html")
RESEARCH_DATA = os.path.join(HERE, "research.json")
BLOG_PAGE = os.path.join(REPO, "blogs.html")
UPLOAD_DIR = os.path.join(REPO, "images", "research")
START, END = "<!-- EDITOR:START", "<!-- EDITOR:END -->"
PORT = 8765


# ---------------------------------------------------------------- rendering

def esc(s):
    return html.escape(s or "", quote=True)


def split_name(full):
    if "," in full:
        fam, giv = [x.strip() for x in full.split(",", 1)]
    else:
        parts = full.split()
        fam, giv = parts[-1], " ".join(parts[:-1])
    return fam, giv


def short_name(full):
    fam, giv = split_name(full)
    inits = []
    for tok in giv.replace(".", ". ").split():
        if "-" in tok and not tok.endswith("."):
            inits.append("-".join(t[0] + "." for t in tok.split("-") if t))
        else:
            inits.append(tok if tok.endswith(".") else tok[0] + ".")
    return (" ".join(inits) + " " + fam).strip()


def is_me(full, me):
    fam, giv = split_name(full)
    return fam.lower() == me["family"].lower() and giv.upper().startswith(me["initial"].upper())


def my_position(p, me):
    """1-based position of me in the author list (99 if not found)."""
    return next((i + 1 for i, a in enumerate(p.get("authors", [])) if is_me(a, me)), 99)


def render_authors(authors, me, max_shown=1000):
    names = [(short_name(a), is_me(a, me)) for a in authors]
    show = lambda n: f"<strong>{esc(n[0])}</strong>" if n[1] else esc(n[0])
    if len(names) <= max_shown:
        return ", ".join(map(show, names))
    out = ", ".join(map(show, names[:3]))
    mine = next((i for i, n in enumerate(names) if n[1]), None)
    if mine is not None and mine >= 3:
        out += ", &hellip;, " + show(names[mine])
    return out + f", <em>et al.</em> ({len(names)} authors)"


def render_pub(p, me):
    arxiv, doi = p.get("arxiv", "").strip(), p.get("doi", "").strip()
    url = f"https://doi.org/{doi}" if doi else (f"https://arxiv.org/abs/{arxiv}" if arxiv else p.get("url", ""))
    title = esc(p["title"])
    venue = p.get("venue") or (f"arXiv:{arxiv}" if arxiv else "")
    links = []
    if p.get("code"):
        links.append(f'<a href="{esc(p["code"])}">Code</a>')
    venue_line = " &middot; ".join(x for x in [f"<em>{esc(venue)}</em>" if venue else "", esc(p.get("year", ""))] if x)
    title_html = f'<a href="{esc(url)}">{title}</a>' if url else title
    return (
        '\t\t\t\t\t\t<li class="pub">\n'
        f'\t\t\t\t\t\t\t<p class="pub-title">{title_html}</p>\n'
        f'\t\t\t\t\t\t\t<p class="pub-authors">{render_authors(p.get("authors", []), me)}</p>\n'
        f'\t\t\t\t\t\t\t<p class="pub-venue">{venue_line}</p>\n'
        + (f'\t\t\t\t\t\t\t<p class="pub-links">{" ".join(links)}</p>\n' if links else "")
        + "\t\t\t\t\t\t</li>\n"
    )


ICONS = {
    "github": "brands fa-github", "paper": "solid fa-file-alt", "data": "solid fa-database",
    "slides": "solid fa-chalkboard", "video": "solid fa-video", "link": "solid fa-link",
}


def render_block(b):
    t = b.get("type")
    if t == "heading":
        return f"<h4>{esc(b.get('text'))}</h4>" if b.get("text", "").strip() else ""
    if t == "text":
        return b.get("html", "")
    if t == "list":
        return b.get("html", "")
    if t == "equation":
        if not b.get("latex", "").strip():
            return ""
        label = f'<span class="eq-label">{esc(b["label"])}</span>' if b.get("label") else ""
        return f'<div class="equation">\\[ {esc(b["latex"])} \\]{label}</div>'
    if t == "figure":
        if not b.get("src"):
            return ""
        cap = f"<figcaption>{b['caption']}</figcaption>" if b.get("caption", "").strip() else ""
        img = f'<img src="{esc(b["src"])}" alt="{esc(b.get("alt"))}" loading="lazy" />'
        if b.get("pdf"):
            # Clicking the figure opens the original vector PDF.
            img = f'<a class="fig-pdf" href="{esc(b["pdf"])}" title="Open the full-resolution PDF">{img}</a>'
        return f'<figure class="fig-{esc(b.get("size", "full"))}">{img}{cap}</figure>'
    return ""


def render_project(p):
    links = [l for l in p.get("links", []) if l.get("url", "").strip() not in ("", "#") and l.get("label")]
    out = ['\t\t\t\t\t\t<div class="col-12">',
           f'\t\t\t\t\t\t\t<details class="research-post" id="{esc(p["id"])}"{" open" if p.get("open") else ""}>',
           "\t\t\t\t\t\t\t\t<summary>",
           f"\t\t\t\t\t\t\t\t\t<h3>{esc(p['title'])}</h3>",
           f'\t\t\t\t\t\t\t\t\t<span class="research-meta">{esc(p.get("meta"))}</span>',
           '\t\t\t\t\t\t\t\t\t<span class="arrow">&#9654;</span>',
           "\t\t\t\t\t\t\t\t</summary>",
           '\t\t\t\t\t\t\t\t<div class="research-content">']
    if links:
        out.append('\t\t\t\t\t\t\t\t\t<ul class="actions">')
        for l in links:
            out.append(f'\t\t\t\t\t\t\t\t\t\t<li><a href="{esc(l["url"])}" class="button small icon '
                       f'{ICONS.get(l.get("icon"), ICONS["link"])}">{esc(l["label"])}</a></li>')
        out.append("\t\t\t\t\t\t\t\t\t</ul>")
    for b in p.get("blocks", []):
        h = render_block(b)
        if h:
            out.append("\t\t\t\t\t\t\t\t\t" + h)
    out += ["\t\t\t\t\t\t\t\t</div>", "\t\t\t\t\t\t\t</details>", "\t\t\t\t\t\t</div>"]
    return "\n".join(out) + "\n"


def render_main(m):
    me = m["me"]
    parts = []
    about = m.get("about", {})
    if re.sub(r"<[^>]+>|\s|&nbsp;", "", about.get("html", "")):
        parts.append(
            '\t\t\t<section id="about">\n\t\t\t\t<header class="major">\n'
            f'\t\t\t\t\t<h2>{esc(about.get("heading") or "About Me")}</h2>\n\t\t\t\t</header>\n'
            f'\t\t\t\t<div class="about-text">{about["html"]}</div>\n\t\t\t</section>\n')
    pubs = [p for p in m.get("publications", []) if not p.get("hidden")]
    pubs.sort(key=lambda p: p.get("date") or p.get("year") or "", reverse=True)
    if pubs:
        s = '\t\t\t<section id="publications">\n\t\t\t\t<header class="major">\n\t\t\t\t\t<h2>Publications</h2>\n\t\t\t\t</header>\n'
        main = [p for p in pubs if my_position(p, me) <= 2]
        nth = [p for p in pubs if my_position(p, me) > 2]
        for label, group in ((None, main), ("Nth author", nth)):
            if not group:
                continue
            if label:
                s += f'\t\t\t\t<h4 class="pub-group">{label}</h4>\n'
            s += '\t\t\t\t<ol class="pubs">\n' + "".join(render_pub(p, me) for p in group) + "\t\t\t\t</ol>\n"
        parts.append(s + "\t\t\t</section>\n")
    projects = [p for p in m.get("projects", []) if not p.get("hidden")]
    if projects:
        parts.append(
            '\t\t\t<section id="one">\n\t\t\t\t<header class="major">\n'
            f'\t\t\t\t\t<h2>{esc(m.get("projectsHeading") or "Research Projects")}</h2>\n\t\t\t\t</header>\n'
            '\t\t\t\t<section class="box alt">\n\t\t\t\t\t<div class="row gtr-uniform">\n'
            + "".join(render_project(p) for p in projects)
            + "\t\t\t\t\t</div>\n\t\t\t\t</section>\n\t\t\t</section>\n")
    return "\n".join(parts)


def splice(page, inner):
    a = page.index(START)
    a = page.index("-->", a) + 3
    b = page.index(END)
    return page[:a] + "\n" + inner + "\t\t\t" + page[b:]


def build_page(m):
    return splice(open(RESEARCH_PAGE, encoding="utf-8").read(), render_main(m))


# ---------------------------------------------------------------- ORCID sync

JOURNALS = {
    "Astrophys.J.": "The Astrophysical Journal", "Astrophys.J.Lett.": "The Astrophysical Journal Letters",
    "Astrophys.J.Suppl.": "The Astrophysical Journal Supplement Series",
    "Mon.Not.Roy.Astron.Soc.": "Monthly Notices of the Royal Astronomical Society",
    "JCAP": "Journal of Cosmology and Astroparticle Physics", "Phys.Rev.D": "Physical Review D",
    "Phys.Rev.Lett.": "Physical Review Letters", "Astron.Astrophys.": "Astronomy & Astrophysics",
    "Phys.Lett.B": "Physics Letters B", "JHEP": "Journal of High Energy Physics",
}
SKIP_INSPIRE = {"conference paper", "proceedings", "talk", "lectures", "note", "report", "thesis"}
SKIP_ORCID = {"conference-paper", "conference-abstract", "conference-poster", "conference-output",
              "lecture-speech", "presentation", "dissertation-thesis", "supervised-student-publication"}


def get_json(url, accept="application/json"):
    req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": "personal-site-editor (mailto:abdelh@mit.edu)"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def from_inspire(q):
    url = "https://inspirehep.net/api/literature?" + urllib.parse.urlencode(
        {"q": q, "fields": "titles,authors.full_name,document_type,publication_info,dois,preprint_date,arxiv_eprints,imprints"})
    hits = get_json(url)["hits"]["hits"]
    return hits[0]["metadata"] if hits else None


def sync_publications(orcid):
    works = get_json(f"https://pub.orcid.org/v3.0/{orcid}/works")
    found, skipped = [], []
    for g in works.get("group", []):
        s = g["work-summary"][0]
        title = s["title"]["title"]["value"]
        if s.get("type") in SKIP_ORCID:
            skipped.append(title); continue
        ids = {e["external-id-type"]: e["external-id-value"] for e in (s.get("external-ids") or {}).get("external-id", [])}
        arxiv = re.sub(r"^arxiv:", "", ids.get("arxiv", ""), flags=re.I)
        doi = ids.get("doi", "")
        pub = {"title": title, "authors": [], "arxiv": arxiv, "doi": doi, "venue": "", "code": "", "date": "", "year": ""}
        rec = None
        try:
            rec = from_inspire(f"arxiv:{arxiv}") if arxiv else (from_inspire(f"doi:{doi}") if doi else None)
        except Exception:
            pass
        if rec:
            if SKIP_INSPIRE & set(rec.get("document_type", [])):
                skipped.append(title); continue
            pub["title"] = rec["titles"][0]["title"]
            pub["authors"] = [a["full_name"] for a in rec.get("authors", [])]
            pub["date"] = rec.get("preprint_date") or ""
            info = next((i for i in rec.get("publication_info", []) if i.get("journal_title")), None)
            if info:
                j = JOURNALS.get(info["journal_title"], info["journal_title"])
                pub["venue"] = " ".join(x for x in [j, info.get("journal_volume", "") + ("," if info.get("artid") or info.get("page_start") else ""),
                                                    info.get("artid") or info.get("page_start", "")] if x).strip()
                pub["date"] = pub["date"] or str(info.get("year", ""))
            if rec.get("dois"):
                pub["doi"] = rec["dois"][0]["value"]
            if not pub["arxiv"] and rec.get("arxiv_eprints"):
                pub["arxiv"] = rec["arxiv_eprints"][0]["value"]
        elif doi:
            try:
                m = get_json(f"https://api.crossref.org/works/{urllib.parse.quote(doi)}")["message"]
                if m.get("type") in ("proceedings-article", "posted-content-talk"):
                    skipped.append(title); continue
                pub["authors"] = [f"{a.get('family', '')}, {a.get('given', '')}".strip(", ") for a in m.get("author", [])]
                pub["venue"] = " ".join(x for x in [(m.get("container-title") or [""])[0],
                                                    (m.get("volume") or "") + ("," if m.get("volume") else ""),
                                                    m.get("article-number") or m.get("page") or ""] if x).strip(" ,")
                dp = m["issued"]["date-parts"][0]
                pub["date"] = "-".join(f"{x:02d}" if i else str(x) for i, x in enumerate(dp))
            except Exception:
                pass
        if not pub["date"] and s.get("publication-date"):
            pub["date"] = (s["publication-date"].get("year") or {}).get("value", "")
        pub["year"] = pub["date"][:4]
        found.append(pub)
    return {"found": found, "skipped": skipped}


# ---------------------------------------------------------------- blog editor (blogs.html)

BLOCK_RE = re.compile(r'<(p|h2|h3|h4)(\s[^>]*?data-edit="([^"]+)"[^>]*)>(.*?)</\1>', re.S)


def blog_blocks():
    s = open(BLOG_PAGE, encoding="utf-8").read()
    sugg_path = os.path.join(HERE, "blog-suggestions.json")
    sugg = json.load(open(sugg_path, encoding="utf-8")) if os.path.exists(sugg_path) else {}
    return [{"id": m.group(3), "tag": m.group(1), "html": re.sub(r"\s+", " ", m.group(4)).strip(),
             "suggestion": sugg.get(m.group(3), {})} for m in BLOCK_RE.finditer(s)]


def blog_save(edits, added):
    s = open(BLOG_PAGE, encoding="utf-8").read()
    backup(BLOG_PAGE)
    existing = set(m.group(3) for m in BLOCK_RE.finditer(s))

    def repl(m):
        tag, attrs, bid, inner = m.groups()
        result = f"<{tag}{attrs}>{edits.get(bid, inner)}</{tag}>"
        line_start = s.rfind("\n", 0, m.start()) + 1
        indent = re.match(r"[ \t]*", s[line_start:]).group(0)
        post = bid.split("-")[0]
        for h in [h for h in added.get(bid, []) if h.strip()]:
            n = 1
            while f"{post}-p{n}" in existing:
                n += 1
            existing.add(f"{post}-p{n}")
            result += f'\n{indent}<p data-edit="{post}-p{n}">{h}</p>'
        return result

    open(BLOG_PAGE, "w", encoding="utf-8").write(BLOCK_RE.sub(repl, s))


# ---------------------------------------------------------------- Q&A page (qa.html)

QA_PAGE = os.path.join(REPO, "qa.html")
QA_DATA = os.path.join(HERE, "qa.json")


def text_to_html(text):
    """Plain text -> paragraphs (blank line = new paragraph, single newline = line break)."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", (text or "").strip()) if p.strip()]
    return "".join("<p>" + "<br />".join(esc(l.strip()) for l in p.split("\n")) + "</p>" for p in paras)


def nice_date(d):
    import datetime
    try:
        return datetime.date.fromisoformat(d).strftime("%b %-d, %Y")
    except Exception:
        return esc(d)


def render_qa(m, preview=False):
    items = [i for i in m.get("items", []) if i.get("published")]
    items.sort(key=lambda i: i.get("date", ""), reverse=True)
    cfg = json.dumps({
        "endpoint": "" if preview else m.get("formEndpoint", ""),
        "owner": m.get("ownerEmail", ""),
        "tag": m.get("subjectTag", "[Website Q&A]"),
    })
    out = f'''			<section id="qa">
				<header class="major">
					<h2>{esc(m.get("heading") or "Q&A")}</h2>
				</header>
				<div class="qa-intro">{m.get("intro", "")}</div>
			</section>

			<section id="ask">
				<form class="ask-box" id="ask-form" novalidate>
					<h3>Ask a question</h3>
					<p class="hint">{esc(m.get("formHint", ""))}</p>
					<div class="fields">
						<div>
							<label for="ask-name">Your name</label>
							<input type="text" id="ask-name" name="name" maxlength="80" autocomplete="name" required />
						</div>
						<div>
							<label for="ask-email">Your email <span class="opt">(never shown)</span></label>
							<input type="email" id="ask-email" name="email" maxlength="120" autocomplete="email" required />
						</div>
						<div class="full">
							<label for="ask-question">Your question</label>
							<textarea id="ask-question" name="question" maxlength="4000" required></textarea>
						</div>
						<input class="hp" type="text" name="_honey" tabindex="-1" autocomplete="off" aria-hidden="true" />
					</div>
					<ul class="actions"><li><button type="submit" class="button primary" id="ask-send">Send question</button></li></ul>
					<div class="ask-status" id="ask-status" role="status"></div>
				</form>
			</section>

			<section id="answers">
				<header class="major">
					<h2>Answered questions</h2>
				</header>
'''
    if not items:
        out += '\t\t\t\t<p class="qa-empty">No answered questions yet. Be the first to ask!</p>\n'
    for i in items:
        asker = f'<span class="qa-asker">Asked by {esc(i["name"])}</span>' if i.get("name", "").strip() else ""
        out += f'''				<article class="qa-card" id="{esc(i["id"])}">
					<p class="qa-meta">{nice_date(i.get("date", ""))}</p>
					<div class="qa-row q"><span class="qa-badge">Q</span><div class="qa-body">{text_to_html(i.get("question", ""))}{asker}</div></div>
					<div class="qa-row a"><span class="qa-badge">A</span><div class="qa-body">{i.get("answer", "")}</div></div>
				</article>
'''
    out += "\t\t\t</section>\n"
    out += "\t\t\t<script>window.QA_FORM = " + cfg + ";</script>\n" + QA_SCRIPT
    return out


QA_SCRIPT = r'''			<script>
			(function () {
				var cfg = window.QA_FORM || {};
				var form = document.getElementById("ask-form");
				var status = document.getElementById("ask-status");
				var send = document.getElementById("ask-send");
				function show(kind, html) { status.className = "ask-status " + kind; status.innerHTML = html; }
				if (form) form.addEventListener("submit", function (e) {
					e.preventDefault();
					if (form._honey.value) return;
					var q = form.question.value.trim();
					var name = form.name.value.trim(), email = form.email.value.trim();
					if (!name) return show("err", "Please add your name.");
					if (q.length < 10) return show("err", "Please write a bit more in your question.");
					if (!email) return show("err", "Please add your email.");
					if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return show("err", "That email address doesn't look right.");
					var subject = cfg.tag + " " + name + ": " + (q.length > 60 ? q.slice(0, 57) + "..." : q);
					var message = "Name: " + name + "\nEmail: " + email +
						"\n\nQUESTION-START\n" + q + "\nQUESTION-END";
					var mailto = "mailto:" + cfg.owner + "?subject=" + encodeURIComponent(subject) + "&body=" + encodeURIComponent(message);
					if (!cfg.endpoint) return show("ok", "Preview only: in the editor nothing is sent. On the live site this goes to your inbox.");
					var payload = { _subject: subject, _template: "box", _captcha: "false", _replyto: email, email: email,
						name: name, question: q, message: message };
					send.disabled = true; send.textContent = "Sending...";
					fetch(cfg.endpoint, { method: "POST", headers: { "Content-Type": "application/json", "Accept": "application/json" }, body: JSON.stringify(payload) })
						.then(function (r) { return r.json().then(function (d) { if (!r.ok || String(d.success) !== "true") throw new Error(d.message || r.status); }); })
						.then(function () { form.reset(); show("ok", "Thanks! Your question was sent. Answered questions show up below."); })
						.catch(function () { show("err", "Sorry, that didn't go through. You can <a href=\"" + mailto + "\">email the question instead</a>."); })
						.then(function () { send.disabled = false; send.textContent = "Send question"; });
				});
			})();
			</script>
'''


def build_qa_page(m, preview=False):
    return splice(open(QA_PAGE, encoding="utf-8").read(), render_qa(m, preview))


# Reading a replied-to question out of an email (.eml file or pasted text)

QUOTE_START = [
    re.compile(r"^\s*On\b.*\bwrote:\s*$"),
    re.compile(r"^\s*-{2,}\s*Original Message", re.I),
    re.compile(r"^\s*_{8,}\s*$"),
    re.compile(r"^\s*>"),
    re.compile(r"^\s*Begin forwarded message", re.I),
]


def html_to_text(h):
    h = re.sub(r"(?is)<(script|style|head)[^>]*>.*?</\1>", " ", h)
    h = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d|blockquote)>", "\n", h)
    h = re.sub(r"(?i)</t[dh]>", "\t", h)
    return html.unescape(re.sub(r"<[^>]+>", "", h))


def parse_reply(text="", eml_b64=""):
    import email, email.policy, email.utils, datetime
    subject, date = "", ""
    if eml_b64:
        msg = email.message_from_bytes(base64.b64decode(eml_b64.split(",", 1)[-1]), policy=email.policy.default)
        subject = str(msg.get("subject", ""))
        try:
            date = email.utils.parsedate_to_datetime(msg["date"]).date().isoformat()
        except Exception:
            pass
        part = msg.get_body(preferencelist=("plain", "html"))
        text = part.get_content() if part else ""
        if part and part.get_content_type() == "text/html":
            text = html_to_text(text)
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    # Your answer: everything above the quoted original (and above a "-- " signature).
    cut = len(lines)
    for i, l in enumerate(lines):
        two = l + " " + (lines[i + 1] if i + 1 < len(lines) else "")
        if any(p.match(l) for p in QUOTE_START) or re.match(r"^\s*On\b.*\bwrote:\s*$", two) \
                or (re.match(r"^\s*From:\s", l) and any(re.match(r"^\s*(Sent|Date|Subject|To):", x) for x in lines[i + 1:i + 5])):
            cut = i
            break
    answer_lines = lines[:cut]
    for i, l in enumerate(answer_lines):
        if l.rstrip() == "--":
            answer_lines = answer_lines[:i]
            break
    answer = "\n".join(answer_lines).strip()
    quoted = "\n".join(re.sub(r"^\s*(>\s?)+", "", l) for l in lines[cut:]) or text

    labels = r"(?:Category|Name|Email|Publish OK|QUESTION-START)"
    def grab(label):
        mm = re.search(label + r":\s*(.+?)\s*(?=\n|" + labels + r":|QUESTION-START|$)", quoted)
        return mm.group(1).strip() if mm else ""
    mm = re.search(r"QUESTION-START\s*(.*?)\s*QUESTION-END", quoted, re.S)
    question = mm.group(1) if mm else ""
    if not question:  # fall back to the "question" row of the form email
        mm = re.search(r"(?im)^\s*question\s*[:\t]\s*(.+?)(?=\n\s*\n|\n\s*(message|category|name|email)\b|$)", quoted, re.S)
        question = mm.group(1) if mm else ""
    # Re-flow lines that the mail client wrapped, keeping paragraph breaks.
    question = "\n\n".join(" ".join(x.split()) for x in re.split(r"\n\s*\n", question.strip()) if x.strip())
    name = grab("Name")
    return {
        "question": question,
        "category": grab("Category"),
        "name": "" if name.lower() in ("anonymous", "") else name,
        "answer": text_to_html(answer),
        "date": date or datetime.date.today().isoformat(),
        "subject": subject,
        "found": {"question": bool(question), "answer": bool(answer)},
    }


# ---------------------------------------------------------------- server

def backup(path):
    """Keep one backup of the page as it was before this editor session first saved it."""
    b = path + ".bak"
    if path not in backup.done:
        shutil.copy(path, b)
        backup.done.add(path)
backup.done = set()


def safe_filename(name):
    base, ext = os.path.splitext(os.path.basename(name))
    base = re.sub(r"[^A-Za-z0-9_-]+", "-", base).strip("-").lower() or "figure"
    ext = ext.lower()
    if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".pdf"):
        raise ValueError("Images or PDFs only (png, jpg, gif, webp, svg, pdf)")
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    cand, n = base + ext, 2
    while os.path.exists(os.path.join(UPLOAD_DIR, cand)):
        cand, n = f"{base}-{n}{ext}", n + 1
    return cand


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=REPO, **k)

    def log_message(self, *a):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send(self, body, ctype="application/json", code=200):
        if not isinstance(body, bytes):
            body = (json.dumps(body) if ctype == "application/json" else body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text") else ""))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def body(self):
        return json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/research"):
            self.send(open(os.path.join(HERE, "research.html"), "rb").read(), "text/html")
        elif path == "/qa":
            self.send(open(os.path.join(HERE, "qa-editor.html"), "rb").read(), "text/html")
        elif path == "/api/qa":
            self.send(json.load(open(QA_DATA, encoding="utf-8")))
        elif path == "/blog":
            self.send(open(os.path.join(HERE, "blog.html"), "rb").read(), "text/html")
        elif path == "/api/research":
            self.send(json.load(open(RESEARCH_DATA, encoding="utf-8")))
        elif path == "/api/blocks":
            self.send(blog_blocks())
        elif path in ("/vendor/pdf.min.mjs", "/vendor/pdf.worker.min.mjs"):
            # PDF.js (v4.4.168), served locally so its worker runs on the same origin
            self.send(open(os.path.join(HERE, path.lstrip("/")), "rb").read(), "text/javascript")
        elif path.startswith("/_editor"):
            self.send_error(404)
        else:
            super().do_GET()

    def do_POST(self):
        try:
            path = self.path.split("?")[0]
            if path == "/api/research/preview":
                page = build_page(self.body())
                base = f'<base href="http://{self.headers["Host"]}/" target="_blank">'
                self.send(page.replace("<head>", "<head>" + base, 1), "text/html")
            elif path == "/api/research/save":
                m = self.body()
                page = build_page(m)
                backup(RESEARCH_PAGE)
                open(RESEARCH_PAGE, "w", encoding="utf-8").write(page)
                with open(RESEARCH_DATA, "w", encoding="utf-8") as f:
                    json.dump(m, f, indent=2, ensure_ascii=False)
                self.send({"ok": True})
            elif path == "/api/qa/preview":
                page = build_qa_page(self.body(), preview=True)
                base = f'<base href="http://{self.headers["Host"]}/" target="_blank">'
                self.send(page.replace("<head>", "<head>" + base, 1), "text/html")
            elif path == "/api/qa/save":
                m = self.body()
                page = build_qa_page(m)
                backup(QA_PAGE)
                open(QA_PAGE, "w", encoding="utf-8").write(page)
                with open(QA_DATA, "w", encoding="utf-8") as f:
                    json.dump(m, f, indent=2, ensure_ascii=False)
                self.send({"ok": True})
            elif path == "/api/qa/parse":
                d = self.body()
                self.send(parse_reply(d.get("text", ""), d.get("eml", "")))
            elif path == "/api/upload":
                d = self.body()
                name = safe_filename(d["name"])
                with open(os.path.join(UPLOAD_DIR, name), "wb") as f:
                    f.write(base64.b64decode(d["data"].split(",", 1)[-1]))
                self.send({"src": f"images/research/{name}"})
            elif path == "/api/sync-publications":
                self.send(sync_publications(self.body()["orcid"]))
            elif path == "/api/save":
                d = self.body()
                blog_save(d.get("edits", {}), d.get("added", {}))
                self.send(blog_blocks())
            else:
                self.send_error(404)
        except Exception as e:
            self.send({"error": str(e)}, code=500)


if __name__ == "__main__":
    print(f"Website editor running: http://localhost:{PORT}/research , /blog and /qa  (Ctrl+C to stop)")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
