"""Unit tests for Neuron core logic.

Run with: python -m pytest tests/test_core.py -v
Uses mocks for fastembed and mcp to avoid heavy dependencies.
"""

from __future__ import annotations

import sys
import types
import tempfile
import os

# ── Mock heavy deps before any neuron import ────────────────────────────────

sys.modules["turso"] = None  # force sqlite3 fallback

_fe = types.ModuleType("fastembed")
class _FakeEmbed:
    def __init__(self, *a, **kw): pass
    def embed(self, texts):
        texts = list(texts) if not isinstance(texts, list) else texts
        for _ in texts:
            yield [0.1] * 384
_fe.TextEmbedding = _FakeEmbed
sys.modules["fastembed"] = _fe

def _make_mod(name):
    m = types.ModuleType(name)
    sys.modules[name] = m
    return m

mcp = _make_mod("mcp")
srv = _make_mod("mcp.server")
mdl = _make_mod("mcp.server.models")
std = _make_mod("mcp.server.stdio")
typ = _make_mod("mcp.types")

import contextlib

class _FakeSrv:
    def __init__(self, *a, **kw): pass
    def list_tools(self): return lambda f: f
    def call_tool(self):  return lambda f: f

@contextlib.asynccontextmanager
async def _fake_stdio(*a, **kw): yield None, None

srv.Server                    = _FakeSrv
mdl.InitializationOptions     = type("IO", (), {})
std.stdio_server              = _fake_stdio
typ.Tool                      = type("Tool", (), {"__init__": lambda s, **kw: None})
typ.TextContent               = type("TC", (), {"__init__": lambda s, **kw: s.__dict__.update(kw)})
typ.ServerCapabilities        = type("SC", (), {})
typ.ToolsCapability           = type("TsCap", (), {})

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# ── Imports under test ────────────────────────────────────────────────────────

from neuron.models import (
    Node, Link, Graph,
    WEIGHT_ORDER, TANGENTIAL_EXPIRY_TURNS, MAX_NODES,
    pack_vector, unpack_vector, VECTOR_DIM,
)
from neuron.server import (
    SemanticExtractor,
    CONTEXT_SWITCH_THRESHOLD, _domain_signal,
    flash_enabled,
    validate_turn_input,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Graph — node operations
# ═══════════════════════════════════════════════════════════════════════════════

class TestGraphNodes:
    def _graph(self):
        g = Graph()
        return g

    def test_add_node_basic(self):
        g = self._graph()
        g.add_node(Node(keyword="docker", turn=1, topic="infra", domain="architecture", sentiment="neutral"))
        assert g.get_node("docker") is not None
        assert len(g.nodes) == 1

    def test_get_node_missing(self):
        g = self._graph()
        assert g.get_node("nonexistent") is None

    def test_node_map_rebuilt_on_load(self):
        g = Graph()
        g.nodes = [Node(keyword="k1", turn=0, topic="t", domain="general", sentiment="neutral")]
        g._rebuild_node_map()
        assert g.get_node("k1") is not None

    def test_node_cap_evicts_lowest_salience(self):
        g = Graph()
        # fill to cap
        for i in range(MAX_NODES):
            g.add_node(Node(keyword=f"kw{i}", turn=i, topic="t", domain="general",
                            sentiment="neutral", salience=i))  # salience == index
        assert len(g.nodes) == MAX_NODES
        # add one more — lowest-salience (kw0, salience=0) should be evicted
        g.add_node(Node(keyword="new_kw", turn=MAX_NODES + 1, topic="t",
                        domain="general", sentiment="neutral", salience=999))
        assert len(g.nodes) <= MAX_NODES
        assert g.get_node("kw0") is None, "lowest-salience node should be evicted"
        assert g.get_node("new_kw") is not None


# ═══════════════════════════════════════════════════════════════════════════════
# Graph — link operations
# ═══════════════════════════════════════════════════════════════════════════════

class TestGraphLinks:
    def _graph_with_nodes(self):
        g = Graph()
        g.add_node(Node(keyword="A", turn=1, topic="t", domain="backend", sentiment="neutral", salience=3))
        g.add_node(Node(keyword="B", turn=2, topic="t", domain="backend", sentiment="neutral", salience=5))
        g.add_node(Node(keyword="C", turn=3, topic="t", domain="frontend", sentiment="neutral", salience=2))
        return g

    def test_add_link(self):
        g = self._graph_with_nodes()
        g.add_link(Link(source="A", target="B", link_type="deepening", weight="strong",
                        rationale="r", created_turn=1, last_active_turn=1))
        assert len(g.links) == 1

    def test_dedup_same_direction(self):
        g = self._graph_with_nodes()
        lk = Link(source="A", target="B", link_type="deepening", weight="medium",
                  rationale="r", created_turn=1, last_active_turn=1)
        g.add_link(lk)
        g.add_link(lk)  # duplicate
        assert len(g.links) == 1

    def test_dedup_reverse_direction(self):
        g = self._graph_with_nodes()
        g.add_link(Link(source="A", target="B", link_type="analogy", weight="medium",
                        rationale="r", created_turn=1, last_active_turn=1))
        g.add_link(Link(source="B", target="A", link_type="analogy", weight="medium",
                        rationale="r", created_turn=2, last_active_turn=2))
        assert len(g.links) == 1, "reverse duplicate should be ignored"

    def test_dedup_upgrades_weight(self):
        g = self._graph_with_nodes()
        g.add_link(Link(source="A", target="B", link_type="deepening", weight="tangential",
                        rationale="r", created_turn=1, last_active_turn=1))
        g.add_link(Link(source="A", target="B", link_type="deepening", weight="strong",
                        rationale="r", created_turn=2, last_active_turn=2))
        assert len(g.links) == 1
        assert g.links[0].weight == "strong", "weight should be upgraded to stronger"

    def test_weight_ranking(self):
        g = self._graph_with_nodes()
        g.add_link(Link(source="A", target="C", link_type="analogy",   weight="tangential",
                        rationale="r", created_turn=1, last_active_turn=1))
        g.add_link(Link(source="A", target="B", link_type="deepening", weight="strong",
                        rationale="r", created_turn=1, last_active_turn=3))
        sorted_links = sorted(g.links, key=lambda lk: (WEIGHT_ORDER.get(lk.weight, 0), lk.last_active_turn), reverse=True)
        assert sorted_links[0].weight == "strong"
        assert sorted_links[1].weight == "tangential"

    def test_get_active_links_excludes_tangential(self):
        g = self._graph_with_nodes()
        g.add_link(Link(source="A", target="B", link_type="deepening", weight="strong",
                        rationale="r", created_turn=1, last_active_turn=1))
        g.add_link(Link(source="A", target="C", link_type="analogy", weight="tangential",
                        rationale="r", created_turn=1, last_active_turn=1))
        active = g.get_active_links()
        assert all(lk.weight != "tangential" for lk in active)

    def test_prune_tangential_expired(self):
        g = self._graph_with_nodes()
        g.add_link(Link(source="A", target="B", link_type="deepening", weight="strong",
                        rationale="r", created_turn=1, last_active_turn=1))
        g.add_link(Link(source="A", target="C", link_type="analogy", weight="tangential",
                        rationale="r", created_turn=1, last_active_turn=1,
                        inactive_turns=TANGENTIAL_EXPIRY_TURNS + 1))
        removed = g.prune_tangential()
        assert removed == 1
        assert len(g.links) == 1
        assert g.links[0].weight == "strong"


# ═══════════════════════════════════════════════════════════════════════════════
# Graph — node composite scoring (get_context logic)
# ═══════════════════════════════════════════════════════════════════════════════

class TestNodeScoring:
    def test_composite_score_favours_high_salience_recent(self):
        g = Graph()
        g.add_node(Node(keyword="A", turn=4, topic="t", domain="backend", sentiment="neutral", salience=5))
        g.add_node(Node(keyword="B", turn=1, topic="t", domain="backend", sentiment="neutral", salience=2))
        g.add_link(Link(source="A", target="B", link_type="deepening", weight="strong",
                        rationale="r", created_turn=1, last_active_turn=4))
        g.turn_count = 5

        scores = {}
        for nd_kw in ["A", "B"]:
            nd = g.get_node(nd_kw)
            base     = float(nd.salience)
            recency  = 2.0 if (g.turn_count - nd.turn) <= 5 else 0.0
            link_sc  = sum(WEIGHT_ORDER.get(lk.weight, 0) for lk in g.links
                           if lk.source == nd_kw or lk.target == nd_kw)
            scores[nd_kw] = base + recency + link_sc * 0.5
        top = sorted(scores.items(), key=lambda x: -x[1])
        assert top[0][0] == "A", f"A should rank first (high salience + recent), got {top}"


# ═══════════════════════════════════════════════════════════════════════════════
# Graph — SQLite persistence
# ═══════════════════════════════════════════════════════════════════════════════

class TestGraphPersistence:
    def test_save_and_load_roundtrip(self):
        g = Graph()
        g.turn_count = 5
        g.last_topic = "test topic"
        g.add_node(Node(keyword="spring", turn=1, topic="java", domain="backend",
                        sentiment="neutral", salience=3))
        g.add_link(Link(source="spring", target="jpa", link_type="deepening", weight="strong",
                        rationale="ORM", created_turn=1, last_active_turn=1))
        assert g._dirty

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db = f.name
        try:
            g.save_sqlite(db)
            assert not g._dirty, "dirty flag should be cleared after save"

            g2 = Graph()
            g2.load_sqlite(db)
            assert g2.turn_count == 5
            assert g2.last_topic  == "test topic"
            assert g2.get_node("spring") is not None
            assert g2.get_node("spring").salience == 3
            assert len(g2.links) == 1
            assert g2.links[0].weight == "strong"
        finally:
            os.unlink(db)

    def test_save_skips_clean_graph(self):
        g = Graph()
        g.add_node(Node(keyword="k", turn=1, topic="t", domain="general", sentiment="neutral"))
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db = f.name
        try:
            g.save_sqlite(db)
            mtime1 = os.path.getmtime(db)
            import time; time.sleep(0.05)
            g.save_sqlite(db)          # should skip — not dirty
            mtime2 = os.path.getmtime(db)
            assert mtime1 == mtime2, "second save should be a no-op (not dirty)"
        finally:
            os.unlink(db)

    def test_domain_filter_on_load(self):
        g = Graph()
        g.add_node(Node(keyword="react",   turn=1, topic="ui",      domain="frontend", sentiment="neutral"))
        g.add_node(Node(keyword="spring",  turn=2, topic="java",    domain="backend",  sentiment="neutral"))
        g.add_node(Node(keyword="general", turn=3, topic="general", domain="general",  sentiment="neutral"))
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db = f.name
        try:
            g.save_sqlite(db)
            g2 = Graph()
            g2.load_sqlite(db, domain_filter="backend")
            kws = {nd.keyword for nd in g2.nodes}
            assert "spring" in kws
            assert "react"   not in kws
        finally:
            os.unlink(db)


# ═══════════════════════════════════════════════════════════════════════════════
# Vector helpers
# ═══════════════════════════════════════════════════════════════════════════════

class TestVectorHelpers:
    def test_pack_unpack_roundtrip(self):
        vec = [0.1 * i for i in range(VECTOR_DIM)]
        packed   = pack_vector(vec)
        unpacked = unpack_vector(packed)
        assert len(unpacked) == VECTOR_DIM
        for a, b in zip(vec, unpacked):
            assert abs(a - b) < 1e-5


# ═══════════════════════════════════════════════════════════════════════════════
# SemanticExtractor
# ═══════════════════════════════════════════════════════════════════════════════

class TestSemanticExtractor:
    def test_extracts_keywords(self):
        result = SemanticExtractor.extract("How do I use Spring Boot with JPA repositories?")
        assert len(result.keywords) > 0
        kws_lower = [k.lower() for k in result.keywords]
        assert any("spring" in k or "jpa" in k or "boot" in k or "repositories" in k for k in kws_lower)

    def test_domain_backend(self):
        result = SemanticExtractor.extract("Configure Hibernate entity mapping with JPA annotations")
        assert result.domain == "backend", f"got {result.domain}"

    def test_domain_frontend(self):
        result = SemanticExtractor.extract("Angular component lifecycle hooks with TypeScript")
        assert result.domain == "frontend", f"got {result.domain}"

    def test_domain_general_neutral(self):
        result = SemanticExtractor.extract("What do you think about this approach?")
        assert result.domain == "general", f"got {result.domain}"

    def test_intent_question(self):
        result = SemanticExtractor.extract("How does dependency injection work?")
        assert result.intent == "question"

    def test_sentiment_urgent(self):
        result = SemanticExtractor.extract("URGENT: production is down, critical bug!")
        assert result.sentiment == "urgent"

    def test_empty_text_fallback(self):
        result = SemanticExtractor.extract("")
        assert len(result.keywords) >= 1  # should not crash


# ═══════════════════════════════════════════════════════════════════════════════
# Hysteresis context switch
# ═══════════════════════════════════════════════════════════════════════════════

class TestHysteresis:
    def setup_method(self):
        _domain_signal["domain"] = None
        _domain_signal["count"]  = 0

    def _signal(self, domain: str) -> bool:
        if _domain_signal["domain"] == domain:
            _domain_signal["count"] += 1
        else:
            _domain_signal["domain"] = domain
            _domain_signal["count"]  = 1
        return _domain_signal["count"] >= CONTEXT_SWITCH_THRESHOLD

    def test_single_signal_no_switch(self):
        assert self._signal("backend") is False

    def test_consecutive_signals_trigger_switch(self):
        self._signal("backend")
        assert self._signal("backend") is True

    def test_different_domain_resets_counter(self):
        self._signal("backend")
        self._signal("frontend")   # resets counter
        assert self._signal("frontend") is True   # now consecutive → switch

    def test_threshold_value(self):
        assert CONTEXT_SWITCH_THRESHOLD == 2


# ═══════════════════════════════════════════════════════════════════════════════
# Validation
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidation:
    def test_valid_input(self):
        assert validate_turn_input(["docker", "kubernetes"], "infra topic", []) is None

    def test_too_many_keywords(self):
        kws = [f"kw{i}" for i in range(9)]
        assert validate_turn_input(kws, "topic", []) is not None

    def test_keyword_invalid_chars(self):
        assert validate_turn_input(["bad(keyword)"], "topic", []) is not None

    def test_topic_too_long(self):
        assert validate_turn_input(["kw"], "x" * 101, []) is not None

    def test_empty_keywords(self):
        assert validate_turn_input([], "topic", []) is not None


# ═══════════════════════════════════════════════════════════════════════════════
# flash_enabled default
# ═══════════════════════════════════════════════════════════════════════════════

def test_flash_enabled_by_default():
    assert flash_enabled is True
