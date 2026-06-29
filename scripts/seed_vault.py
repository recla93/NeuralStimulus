"""Seed knowledge base from Obsidian vault using existing Graphify output.

Loads BackEndNotes/graphify-out/graph.json (2553 nodes, 7582 edges),
scans BEGUIDES/ raw .md for remaining content,
merges into knowledge/base_knowledge.db.

Supported vault roots (tried in order):
  1. C:\\Users\\recla\\OneDrive\\Documenti   (OneDrive — primary)
  2. D:\\Desktop\\NEURON\\New Obs             (legacy local path)
Set NEURON_VAULT env var to override, e.g.:
  NEURON_VAULT=C:\\MyVault python scripts/seed_vault.py
"""

import os, re, json, sqlite3
from pathlib import Path

# ---------------------------------------------------------------------------
# Vault discovery
# ---------------------------------------------------------------------------

_CANDIDATE_VAULTS = [
    Path(os.environ["NEURON_VAULT"]) if "NEURON_VAULT" in os.environ else None,
    Path(r"C:\Users\recla\OneDrive\Documenti"),
    Path(r"D:\Desktop\NEURON\New Obs"),
]

def _find_vault() -> Path | None:
    for p in _CANDIDATE_VAULTS:
        if p is not None and p.exists():
            return p
    return None

VAULT = _find_vault()
if VAULT is None:
    raise SystemExit(
        "Vault not found. Set NEURON_VAULT env var to your Obsidian vault root, "
        "or place notes at C:\\Users\\recla\\OneDrive\\Documenti."
    )

SKIP_DIRS = {"RAG-Nexus", "RAG-Nexus - Backup", ".obsidian", "Pics", "graphify-out", ".git"}
OUT_DIR = Path(__file__).resolve().parent.parent / "knowledge"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Keyword quality filter
# ---------------------------------------------------------------------------

_KW_PATTERN = re.compile(r"^[a-zA-Z0-9\s\-_.:+/]+$")

def is_valid_keyword(kw: str) -> bool:
    """Return True only for clean, usable keywords.

    Rejects:
    - function call syntax: contains ( ) { }
    - Obsidian/JS config noise: starts with _ or .
    - Empty or very short/long
    - Fails character pattern
    - Looks like a path (contains \\ or multiple /)
    """
    if not kw:
        return False
    if len(kw) < 3 or len(kw) > 40:
        return False
    if any(c in kw for c in "(){}[]<>\\"):
        return False
    if kw.startswith(("_", ".", "#")):
        return False
    if kw.count("/") > 1:  # allow "java/spring" but not deep paths
        return False
    if not _KW_PATTERN.match(kw):
        return False
    # Reject obvious JS/config artifacts: camelCase-looking long tokens with no spaces
    if len(kw) > 20 and " " not in kw and kw[0].islower():
        return False
    return True

# ---------------------------------------------------------------------------
# Domain inference
# ---------------------------------------------------------------------------

DOMAIN_KEYWORDS: list[tuple[str, list[str]]] = [
    ("backend", ["java", "spring", "hibernate", "jpa", "sql", "database",
                 "python", "django", "fastapi", "csharp", ".net", "c#",
                 "php", "laravel", "symfony", "node", "express", "nestjs",
                 "mapstruct", "mongodb", "redis", "kafka", "rabbitmq",
                 "rest", "api", "graphql", "microservice", "backend",
                 "jdbc", "orm", "query", "endpoint", "dto", "entity",
                 "repository", "service", "controller"]),
    ("architecture", ["docker", "kubernetes", "infrastructure", "architettura",
                      "design pattern", "solid", "clean", "hexagonal",
                      "ddd", "domain driven", "event sourcing", "cqrs",
                      "monolith", "deployment", "ci/cd", "devops"]),
    ("AI", ["machine learning", "deep learning", "neural", "llm", "rag",
            "embedding", "vector", "nlp", "transformer", "dataset",
            "training", "inference", "classification", "ai"]),
    ("frontend", ["angular", "react", "vue", "svelte", "typescript",
                  "css", "html", "javascript", "dom", "ui", "ux",
                  "frontend", "browser", "responsive"]),
    ("gaming", ["unity", "unreal", "godot", "game", "shader", "sprite"]),
]
DEFAULT_DOMAIN = "general"


def infer_domain(source_file: str, content: str = "") -> str:
    """Infer domain from file path and optionally file content keywords."""
    lower_path = source_file.lower().replace("\\", "/")
    lower_content = content.lower()[:2000]  # first 2000 chars only

    scores: dict[str, int] = {}
    for domain, kws in DOMAIN_KEYWORDS:
        score = sum(1 for kw in kws if kw in lower_path)
        score += sum(1 for kw in kws if kw in lower_content) // 3  # content counts less
        if score:
            scores[domain] = scores.get(domain, 0) + score

    if not scores:
        return DEFAULT_DOMAIN
    return max(scores, key=scores.get)


# ---------------------------------------------------------------------------
# Load Graphify output
# ---------------------------------------------------------------------------

def load_graphify(path: Path) -> tuple[list[dict], list[dict]]:
    if not path.exists():
        return [], []
    data = json.loads(path.read_text(encoding="utf-8"))
    nodes: dict[str, dict] = {}
    links: list[dict] = []
    seen_links: set[tuple[str, str]] = set()

    for gn in data.get("nodes", []):
        sf = gn.get("source_file", "")
        if not sf or sf.startswith("."):
            continue
        kw = gn.get("label", gn["id"])
        if not is_valid_keyword(kw):
            continue
        domain = infer_domain(sf)
        tags = [p for p in Path(sf).parts[:-1] if p not in SKIP_DIRS]
        nodes[gn["id"]] = {
            "keyword": kw,
            "turn": 0,
            "topic": kw[:80],
            "domain": domain,
            "sentiment": "neutral",
            "salience": 1,
            "entities": "[]",
            "tags": json.dumps(tags[:10]),
            "refs": json.dumps([{"type": "file", "path": sf, "description": kw[:80]}]),
        }

    for gl in data.get("links", []):
        s, t = gl.get("source"), gl.get("target")
        if not s or not t or s not in nodes or t not in nodes:
            continue
        edge = (s, t)
        rev = (t, s)
        if edge not in seen_links and rev not in seen_links:
            seen_links.add(edge)
            links.append({
                "source": s,
                "target": t,
                "link_type": "deepening",
                "weight": "medium",
                "rationale": gl.get("relation", "connected"),
                "created_turn": 0,
                "last_active_turn": 0,
                "inactive_turns": 0,
            })

    return list(nodes.values()), links


# ---------------------------------------------------------------------------
# Scan raw .md files (for vaults without graphify-out)
# ---------------------------------------------------------------------------

def scan_md_files(root: Path) -> tuple[list[dict], list[dict]]:
    files: list[dict] = []
    for dirpath, dirs, names in os.walk(str(root)):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in names:
            if not name.endswith(".md"):
                continue
            fpath = Path(dirpath) / name
            rel = str(fpath.relative_to(root))
            files.append({
                "path": str(fpath),
                "relative": rel,
                "filename": name[:-3],
            })

    nodes: dict[str, dict] = {}
    links: list[dict] = []
    seen_links: set[tuple[str, str]] = set()
    collisions: dict[str, list[dict]] = {}

    for f in files:
        collisions.setdefault(f["filename"], []).append(f)

    for f in files:
        kw = f["filename"]
        collided = len(collisions.get(kw, [])) > 1
        content = Path(f["path"]).read_text(encoding="utf-8", errors="replace")
        title = kw
        m = re.search(r"^#\s+(.+)", content, re.MULTILINE)
        if m:
            title = m.group(1).strip()[:80]

        if collided:
            parts = [p for p in Path(f["relative"]).parts[:-1] if p not in SKIP_DIRS]
            kw = f"{parts[-1]}/{kw}" if parts else kw

        if not is_valid_keyword(kw):
            continue

        domain = infer_domain(f["path"], content)
        tags = [p for p in Path(f["relative"]).parts[:-1] if p not in SKIP_DIRS]
        wikilinks = re.findall(r"\[\[([^\]]+?)(?:\|[^\]]+?)?\]\]", content)

        if kw in nodes:
            existing = nodes[kw]
            et = json.loads(existing["tags"])
            er = json.loads(existing["refs"])
            ee = json.loads(existing["entities"])
            for t in tags:
                if t not in et: et.append(t)
            if {"type": "file", "path": f["relative"], "description": title} not in er:
                er.append({"type": "file", "path": f["relative"], "description": title})
            for e in wikilinks:
                if e not in ee: ee.append(e)
            existing["salience"] += 1
            existing["tags"] = json.dumps(et[:10])
            existing["refs"] = json.dumps(er[:5])
            existing["entities"] = json.dumps(ee[:30])
            kw_nodes = existing
        else:
            nodes[kw] = {
                "keyword": kw,
                "turn": 0,
                "topic": title,
                "domain": domain,
                "sentiment": "neutral",
                "salience": 1,
                "entities": json.dumps(wikilinks[:30]),
                "tags": json.dumps(tags[:10]),
                "refs": json.dumps([{"type": "file", "path": f["relative"], "description": title}]),
            }

        for target in wikilinks[:30]:
            if target == kw:
                continue
            edge = (kw, target)
            rev = (target, kw)
            if edge not in seen_links and rev not in seen_links:
                seen_links.add(edge)
                links.append({
                    "source": kw,
                    "target": target,
                    "link_type": "deepening",
                    "weight": "medium",
                    "rationale": "wikilink",
                    "created_turn": 0,
                    "last_active_turn": 0,
                    "inactive_turns": 0,
                })

    return list(nodes.values()), links


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------

def merge(nodes_a: list[dict], links_a: list[dict],
           nodes_b: list[dict], links_b: list[dict]) -> tuple[list[dict], list[dict]]:
    merged_nodes: dict[str, dict] = {}
    for n in nodes_a + nodes_b:
        kw = n["keyword"]
        if kw in merged_nodes:
            en = merged_nodes[kw]
            en["salience"] += n.get("salience", 1)
            for attr in ("tags", "entities"):
                a = set(json.loads(en.get(attr, "[]")))
                b = set(json.loads(n.get(attr, "[]")))
                merged = list(a | b)
                en[attr] = json.dumps(merged[:30])
            # refs are list of dicts — dedup by json string
            ra = json.loads(en.get("refs", "[]"))
            rb = json.loads(n.get("refs", "[]"))
            seen_r = {json.dumps(r, sort_keys=True) for r in ra}
            for r in rb:
                key = json.dumps(r, sort_keys=True)
                if key not in seen_r:
                    seen_r.add(key)
                    ra.append(r)
            en["refs"] = json.dumps(ra[:10])
        else:
            merged_nodes[kw] = dict(n)

    seen_links: set[tuple[str, str]] = set()
    merged_links: list[dict] = []
    for lk in links_a + links_b:
        edge = (lk["source"], lk["target"])
        rev = (lk["target"], lk["source"])
        if edge not in seen_links and rev not in seen_links:
            seen_links.add(edge)
            merged_links.append(lk)

    return list(merged_nodes.values()), merged_links


# ---------------------------------------------------------------------------
# Save to SQLite
# ---------------------------------------------------------------------------

def save_db(nodes: list[dict], links: list[dict], db_path: str):
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT, turn INTEGER, topic TEXT,
                domain TEXT, sentiment TEXT, salience INTEGER,
                entities TEXT DEFAULT '[]',
                tags TEXT DEFAULT '[]',
                refs TEXT DEFAULT '[]');
            CREATE INDEX IF NOT EXISTS idx_nodes_keyword ON nodes(keyword);
            CREATE TABLE IF NOT EXISTS node_vectors (
                keyword TEXT PRIMARY KEY,
                embedding BLOB NOT NULL,
                dim INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT, target TEXT, link_type TEXT, weight TEXT,
                rationale TEXT, created_turn INTEGER,
                last_active_turn INTEGER, inactive_turns INTEGER);
            CREATE INDEX IF NOT EXISTS idx_links_source ON links(source);
            CREATE INDEX IF NOT EXISTS idx_links_target ON links(target);
        """)

        conn.execute("DELETE FROM meta")
        for k, v in [("session_id", "seed"), ("turn_count", "0"),
                      ("last_sentiment", "neutral"), ("last_topic", "seed knowledge")]:
            conn.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (k, v))

        conn.execute("DELETE FROM nodes")
        conn.execute("DELETE FROM node_vectors")
        conn.executemany(
            "INSERT INTO nodes (keyword, turn, topic, domain, sentiment, salience, entities, tags, refs) "
            "VALUES (:keyword, :turn, :topic, :domain, :sentiment, :salience, :entities, :tags, :refs)",
            nodes,
        )

        conn.execute("DELETE FROM links")
        conn.executemany(
            "INSERT INTO links (source, target, link_type, weight, rationale, created_turn, last_active_turn, inactive_turns) "
            "VALUES (:source, :target, :link_type, :weight, :rationale, :created_turn, :last_active_turn, :inactive_turns)",
            links,
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"Vault root: {VAULT}")
    print("Loading Graphify output from BackEndNotes...")
    gnodes, glinks = load_graphify(VAULT / "BackEndNotes" / "graphify-out" / "graph.json")
    print(f"  Graphify: {len(gnodes)} nodes, {len(glinks)} links")

    print("Scanning BEGUIDES raw .md files...")
    bnodes, blinks = scan_md_files(VAULT / "BEGUIDES")
    print(f"  BEGUIDES: {len(bnodes)} nodes, {len(blinks)} links")

    print("Merging...")
    nodes, links = merge(gnodes, glinks, bnodes, blinks)
    print(f"  Merged: {len(nodes)} nodes, {len(links)} links")

    db_path = str(OUT_DIR / "base_knowledge.db")
    print(f"Saving to {db_path}...")
    save_db(nodes, links, db_path)

    domains: dict[str, int] = {}
    for n in nodes:
        domains[n["domain"]] = domains.get(n["domain"], 0) + 1
    print("\nDomain distribution:")
    for d, c in sorted(domains.items(), key=lambda x: -x[1]):
        print(f"  {d}: {c}")


if __name__ == "__main__":
    main()
