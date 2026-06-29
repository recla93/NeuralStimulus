"""Neuron v3.1 — Summary query for neuron-summary.ps1."""
import sqlite3
import sys

db = sys.argv[1]
c = sqlite3.connect(db)
meta = dict(c.execute("SELECT key, value FROM meta").fetchall())
turn = int(meta.get("turn_count", "0"))
nodes = c.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
links = c.execute("SELECT COUNT(*) FROM links").fetchone()[0]

strong = c.execute("SELECT COUNT(*) FROM links WHERE weight='forte'").fetchone()[0]
medium = c.execute("SELECT COUNT(*) FROM links WHERE weight='medio'").fetchone()[0]
tangential = c.execute("SELECT COUNT(*) FROM links WHERE weight='tangenziale'").fetchone()[0]
link_types = c.execute("SELECT COUNT(DISTINCT link_type) FROM links").fetchone()[0]
pruned = int(meta.get("pruned_count", "0"))

print(f"Turns: {turn}  |  Nodes: {nodes}  |  Links: {links}")
print(f"Strong: {strong}  |  Medium: {medium}  |  Tangential: {tangential}")
print(f"Link types: {link_types}  |  Pruned: {pruned}")
print()

rows = c.execute("""
    SELECT keyword, SUM(salience) as tot, COUNT(*) as occ
    FROM nodes GROUP BY keyword
    ORDER BY tot DESC LIMIT 12
""").fetchall()
if rows:
    print("Keyword piu rilevanti (salience):")
    for r in rows:
        print(f"  {r[0]:20s}  salience={r[1]:3d}  occorrenze={r[2]}")
    print()

rows = c.execute("""
    SELECT source, target, link_type, weight, created_turn
    FROM links ORDER BY created_turn DESC LIMIT 8
""").fetchall()
if rows:
    print("Ultimi link:")
    for r in rows:
        print(f"  {r[0]:15s} ->({r[2]:16s})-> {r[1]:15s}  [{r[3]:12s}]  turno {r[4]}")

c.close()
