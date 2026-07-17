"""Tests for ingestion text cleaning — especially the HTML-strip regex."""

from quizzer.ingestion.cleaner import clean_text


# --- HTML tags must still be stripped (characterization of existing behavior) ---

def test_strips_simple_tags():
    assert clean_text("<p>Hello</p> world") == "Hello world"


def test_strips_tags_with_attributes():
    assert clean_text('Before <div class="note" id="x">inside</div> after') == "Before inside after"


def test_strips_self_closing_tags():
    assert clean_text("line one<br/>line two") == "line oneline two"


def test_strips_html_comments():
    assert clean_text("keep <!-- secret editor note --> this") == "keep  this"


# --- Prose with < and > must survive (bug: regex ate everything between them) ---

def test_preserves_inequalities_in_prose():
    s = "If latency < 100ms the SLA holds, but p99 > 250ms breaks it."
    assert clean_text(s) == s


def test_preserves_inequalities_across_lines():
    s = "Throughput was x < y that day.\nLater z > w caused backpressure."
    assert clean_text(s) == s


def test_preserves_generic_type_parameters():
    s = "A Map<String, User> cache keyed by id, with a generic Node<T> wrapper."
    assert clean_text(s) == s


def test_preserves_arrows_and_comparisons():
    s = "Requests flow client -> LB -> app; shard if n > 10_000 keys."
    assert clean_text(s) == s
