"""Thin wrapper around the warisan_tokenizer bm_spacy_pipeline.

Kept separate from app.py so the pipeline can be unit-tested and cached
independently of any Streamlit session state.
"""
from __future__ import annotations

from functools import lru_cache

from spacy.language import Language
from spacy.tokens import Doc


@lru_cache(maxsize=4)
def load_nlp(split_clitics: bool = True) -> Language:
    """Build (and cache) a Bahasa Melayu spaCy pipeline from warisan_tokenizer.

    Cached per `split_clitics` value so toggling the setting in the UI doesn't
    require re-importing spaCy, but does rebuild the pipeline (it's cheap -
    this is a rule-based, model-free pipeline, not a trained model load).
    """
    from warisan_tokenizer.bm_spacy_pipeline import create_bm_nlp

    return create_bm_nlp(split_clitics=split_clitics)


def tokenize_text(text: str, split_clitics: bool = True) -> list[dict]:
    """Tokenize a single string, returning a list of token dicts."""
    nlp = load_nlp(split_clitics=split_clitics)
    doc: Doc = nlp(text or "")
    return [
        {"text": tok.text, "lemma": tok.lemma_, "root": tok._.root}
        for tok in doc
        if not tok.is_space
    ]


def tokenize_many(
    texts: list[str], split_clitics: bool = True, on_error: str = "fallback"
) -> list[list[dict]]:
    """Tokenize many strings, one at a time, tolerating per-row pipeline errors.

    The bundled hyphen-merger occasionally hits overlapping spans on messy
    real-world transcript text (ValueError: E102) — rather than aborting the
    whole batch, each row is tokenized independently. A row that errors falls
    back to a plain whitespace split (`on_error="fallback"`) so processing a
    large Hansard file never dies partway through; pass `on_error="raise"` to
    surface the original exception instead.
    """
    nlp = load_nlp(split_clitics=split_clitics)
    results: list[list[dict]] = []
    for text in texts:
        text = text or ""
        try:
            doc = nlp(text)
            results.append([
                {"text": tok.text, "lemma": tok.lemma_, "root": tok._.root}
                for tok in doc
                if not tok.is_space
            ])
        except Exception:
            if on_error == "raise":
                raise
            results.append([
                {"text": word, "lemma": word, "root": word}
                for word in text.split()
            ])
    return results
