"""Helpers for tokenizing Hansard transcript workbooks.

A Hansard workbook (as produced by the Hansard Extractor project) has a
`Transcript` sheet with one row per speaker turn and a `Speech Text` column
holding the speech itself. These helpers add a `Speech Tokens` column and can
explode the result into a long, one-row-per-token table for analysis.
"""
from __future__ import annotations

import json

import pandas as pd

from .tokenizer import tokenize_many

DEFAULT_SHEET_NAME = "Transcript"
DEFAULT_TEXT_COLUMN = "Speech Text"


def tokenize_dataframe(
    df: pd.DataFrame,
    text_column: str = DEFAULT_TEXT_COLUMN,
    split_clitics: bool = True,
    source_label: str | None = None,
) -> pd.DataFrame:
    """Return a copy of df with a 'Speech Tokens' column (list[dict] per row)."""
    if text_column not in df.columns:
        raise KeyError(
            f"Column '{text_column}' not found. Available columns: {list(df.columns)}"
        )

    texts = df[text_column].fillna("").astype(str).tolist()
    token_lists = tokenize_many(texts, split_clitics=split_clitics)

    out = df.copy()
    out["Speech Tokens"] = token_lists
    if source_label:
        out["Source File"] = source_label
    return out


def tokenize_workbook(
    file_obj,
    sheet_name: str = DEFAULT_SHEET_NAME,
    text_column: str = DEFAULT_TEXT_COLUMN,
    split_clitics: bool = True,
    source_label: str | None = None,
) -> pd.DataFrame:
    """Read `sheet_name` from an xlsx file-like object/path and tokenize it."""
    df = pd.read_excel(file_obj, sheet_name=sheet_name)
    return tokenize_dataframe(
        df, text_column=text_column, split_clitics=split_clitics, source_label=source_label
    )


def to_long_format(df: pd.DataFrame, token_column: str = "Speech Tokens") -> pd.DataFrame:
    """Explode a per-row token-list column into one row per token."""
    id_cols = [c for c in df.columns if c != token_column]
    records = []
    for _, row in df.iterrows():
        tokens = row[token_column] or []
        for i, tok in enumerate(tokens):
            rec = {col: row[col] for col in id_cols}
            rec["Token Index"] = i
            rec["Token Text"] = tok["text"]
            rec["Token Lemma"] = tok["lemma"]
            rec["Token Root"] = tok["root"]
            records.append(rec)
    return pd.DataFrame.from_records(records)


def tokens_to_json_column(df: pd.DataFrame, token_column: str = "Speech Tokens") -> pd.DataFrame:
    """JSON-encode the token list column so the dataframe can round-trip through xlsx/csv."""
    out = df.copy()
    out[token_column] = out[token_column].apply(lambda toks: json.dumps(toks, ensure_ascii=False))
    return out
