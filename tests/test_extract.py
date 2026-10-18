from seoguard.extract import extract_signals

PAGE = """<!doctype html>
<html><head>
  <title>  Blue Running Shoes | Shop </title>
  <meta name="description" content="Lightweight shoes.">
  <meta name="ROBOTS" content="noindex, follow">
  <link rel="canonical" href="/shoes/blue">
  <link rel="alternate" hreflang="de" href="https://example.com/de/shoes/blue">
  <script>var x = "lots of words that should not count";</script>
</head><body>
  <h1>Blue Shoes</h1><h1></h1>
  <p>Great shoes for running fast.</p>
  <a href="/shoes/red">Red</a>
  <a href="https://www.example.com/about">About</a>
  <a href="https://other.com/">Other</a>
  <a href="#top">Top</a><a href="mailto:a@b.c">Mail</a>
</body></html>"""


def test_extracts_core_signals():
    s = extract_signals(PAGE, "https://example.com/shoes/blue?ref=1")
    assert s.title == "Blue Running Shoes | Shop"
    assert s.meta_description == "Lightweight shoes."
    assert s.canonical == "https://example.com/shoes/blue"
    assert s.noindex
    assert s.hreflang == [("de", "https://example.com/de/shoes/blue")]
    assert s.h1 == ["Blue Shoes"]


def test_link_counts_treat_www_as_same_site():
    s = extract_signals(PAGE, "https://example.com/shoes/blue")
    assert s.internal_links == 2
    assert s.external_links == 1


def test_word_count_ignores_scripts():
    s = extract_signals(PAGE, "https://example.com/")
    # h1 (2) + sentence (5) + link texts (5); the <script> words are excluded
    assert s.word_count == 12


def test_empty_page():
    s = extract_signals("", "https://example.com/")
    assert s.title is None and s.h1 == [] and s.word_count == 0
