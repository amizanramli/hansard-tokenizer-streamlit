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


def to_long_format(
    df: pd.DataFrame,
    token_column: str = "Speech Tokens",
    id_columns: list[str] | None = None,
) -> pd.DataFrame:
    """Explode a per-row token-list column into one row per token.

    By default every non-token column from `df` is carried along as
    metadata, which gets unwieldy fast on real Hansard data (Order, Page,
    Speaker (As Printed), Constituency, Jawatan, Kementerian, ...). Pass
    `id_columns` to keep only a specific subset (e.g. `["Matched Name"]`) so
    the resulting table stays readable — columns that don't exist in `df`
    are silently skipped.
    """
    if id_columns is None:
        id_cols = [c for c in df.columns if c != token_column]
    else:
        id_cols = [c for c in id_columns if c in df.columns and c != token_column]

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


def build_turn_overview(
    df: pd.DataFrame,
    text_column: str,
    id_columns: list[str],
    token_column: str = "Speech Tokens",
) -> pd.DataFrame:
    """One row per speech turn: id columns + original text + token count.

    Much easier to scan than a fully exploded token table when you just want
    to browse "which speech said what", with token-level detail available on
    demand (see `format_tokens_inline`).
    """
    id_cols = [c for c in id_columns if c in df.columns]
    cols = id_cols + [text_column, token_column]
    out = df[cols].copy()
    out["Token Count"] = out[token_column].apply(lambda toks: len(toks) if toks else 0)
    return out.drop(columns=[token_column])


def format_tokens_inline(tokens: list[dict]) -> str:
    """Render a token list as a compact 'text→lemma→root' string, space-separated."""
    if not tokens:
        return ""
    return " ".join(f"{t['text']}→{t['lemma']}→{t['root']}" for t in tokens)


# Excel's hard per-cell character limit. Long Hansard speeches can produce a
# JSON token blob well past this (some turns run 100k+ characters) — openpyxl
# would otherwise truncate mid-JSON and write an unparseable cell with no
# warning at all.
_EXCEL_CELL_CHAR_LIMIT = 32767


def tokens_to_json_column(df: pd.DataFrame, token_column: str = "Speech Tokens") -> pd.DataFrame:
    """JSON-encode the token list column so the dataframe can round-trip through xlsx/csv.

    Rows whose encoded JSON would exceed Excel's per-cell character limit get a
    clear placeholder instead of silently-truncated (and therefore invalid)
    JSON — the full token data for those rows is still available in the
    combined long-format CSV export, which has no such limit.
    """
    out = df.copy()

    def encode(toks):
        blob = json.dumps(toks, ensure_ascii=False)
        if len(blob) > _EXCEL_CELL_CHAR_LIMIT:
            return (
                f"[too long for one Excel cell — {len(toks)} tokens; "
                "see the combined token CSV/parquet export for full data]"
            )
        return blob

    out[token_column] = out[token_column].apply(encode)
    return out
