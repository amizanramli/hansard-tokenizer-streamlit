"""Streamlit interface for warisan_nlp / warisan_tokenizer.

Two things you can do:
1. Paste Bahasa Melayu text and see it tokenized live (text / lemma / root).
2. Upload one or more Hansard transcript .xlsx files and get back an enriched
   workbook (extra 'Speech Tokens' column) plus a combined long-format token
   table you can download as CSV.

Run locally:
    streamlit run app.py
"""
from __future__ import annotations

import io
import zipfile

import pandas as pd
import streamlit as st

from src.tokenizer import load_nlp, tokenize_text
from src.xlsx_processing import (
    DEFAULT_SHEET_NAME,
    DEFAULT_TEXT_COLUMN,
    to_long_format,
    tokenize_workbook,
    tokens_to_json_column,
)

st.set_page_config(
    page_title="Warisan NLP — Hansard Tokenizer",
    page_icon="🧬",
    layout="wide",
)


@st.cache_resource(show_spinner="Loading Bahasa Melayu pipeline...")
def get_nlp(split_clitics: bool):
    return load_nlp(split_clitics=split_clitics)


def df_to_xlsx_bytes(df: pd.DataFrame, sheet_name: str) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)
    return buf.getvalue()


st.title("🧬 Warisan NLP — Hansard Tokenizer")
st.caption(
    "A Streamlit interface for the `warisan_nlp` toolkit "
    "(rule-based Bahasa Melayu tokenizer, lemmatizer, and root annotator)."
)

with st.sidebar:
    st.header("Settings")
    split_clitics = st.toggle(
        "Split clitics",
        value=True,
        help="Split clitic suffixes like '-ku', '-mu', '-nya' into separate tokens "
        "(e.g. 'rumahku' → 'rumah' + 'ku').",
    )
    st.divider()
    st.subheader("Hansard workbook layout")
    sheet_name = st.text_input("Sheet name", value=DEFAULT_SHEET_NAME)
    text_column = st.text_input("Speech text column", value=DEFAULT_TEXT_COLUMN)
    st.caption(
        "Defaults match the Hansard Extractor output format "
        "(a 'Transcript' sheet with a 'Speech Text' column)."
    )
    st.divider()
    st.caption("Pipeline warms up on first use — subsequent runs are cached.")

# Warm the pipeline once per split_clitics setting so both tabs share it.
nlp = get_nlp(split_clitics)

tab_demo, tab_upload = st.tabs(["✍️ Quick text demo", "📄 Upload & tokenize Hansard files"])

with tab_demo:
    st.subheader("Tokenize free text")
    default_text = "Dia membaca buku-buku di rumahku."
    text_input = st.text_area("Bahasa Melayu text", value=default_text, height=120)

    if st.button("Tokenize", type="primary", key="tokenize_demo"):
        if not text_input.strip():
            st.warning("Enter some text first.")
        else:
            tokens = tokenize_text(text_input, split_clitics=split_clitics)
            result_df = pd.DataFrame(tokens)
            st.dataframe(result_df, use_container_width=True, hide_index=True)
            st.download_button(
                "Download as CSV",
                result_df.to_csv(index=False).encode("utf-8-sig"),
                file_name="tokens.csv",
                mime="text/csv",
            )

with tab_upload:
    st.subheader("Upload Hansard transcript workbook(s)")
    st.caption(
        f"Expects a **{sheet_name}** sheet with a **{text_column}** column "
        "(one row per speaker turn) — adjust these in the sidebar if your files differ."
    )

    uploaded_files = st.file_uploader(
        "Hansard .xlsx files",
        type=["xlsx"],
        accept_multiple_files=True,
    )

    row_limit = st.number_input(
        "Row limit per file (0 = no limit, useful for a quick preview)",
        min_value=0,
        value=0,
        step=10,
    )

    if uploaded_files and st.button("Tokenize uploaded file(s)", type="primary"):
        enriched_frames: dict[str, pd.DataFrame] = {}
        long_frames: list[pd.DataFrame] = []
        errors: list[str] = []

        progress = st.progress(0.0, text="Starting...")
        for i, uf in enumerate(uploaded_files):
            progress.progress(i / len(uploaded_files), text=f"Tokenizing {uf.name}...")
            try:
                df = tokenize_workbook(
                    uf,
                    sheet_name=sheet_name,
                    text_column=text_column,
                    split_clitics=split_clitics,
                    source_label=uf.name,
                )
                if row_limit:
                    df = df.head(int(row_limit))
                enriched_frames[uf.name] = df
                long_frames.append(to_long_format(df))
            except Exception as exc:  # noqa: BLE001 - surfaced to the user, not swallowed
                errors.append(f"{uf.name}: {exc}")
        progress.progress(1.0, text="Done")

        if errors:
            st.error("Some files failed to process:\n\n" + "\n".join(f"- {e}" for e in errors))

        if enriched_frames:
            all_long = pd.concat(long_frames, ignore_index=True) if long_frames else pd.DataFrame()

            st.success(f"Tokenized {len(enriched_frames)} file(s), {len(all_long)} tokens total.")

            st.markdown("#### Preview (long format, first 200 tokens)")
            st.dataframe(all_long.head(200), use_container_width=True, hide_index=True)

            st.markdown("#### Downloads")
            col1, col2 = st.columns(2)

            with col1:
                st.download_button(
                    "Download combined token table (CSV)",
                    all_long.to_csv(index=False).encode("utf-8-sig"),
                    file_name="all_tokens.csv",
                    mime="text/csv",
                )

            with col2:
                zip_buf = io.BytesIO()
                with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    for name, df in enriched_frames.items():
                        out_df = tokens_to_json_column(df)
                        xlsx_bytes = df_to_xlsx_bytes(out_df, sheet_name=sheet_name)
                        zf.writestr(name, xlsx_bytes)
                st.download_button(
                    "Download enriched workbook(s) (.zip)",
                    zip_buf.getvalue(),
                    file_name="tokenized_workbooks.zip",
                    mime="application/zip",
                )

            with st.expander("Per-file previews"):
                for name, df in enriched_frames.items():
                    st.markdown(f"**{name}** — {len(df)} rows")
                    st.dataframe(df.head(20), use_container_width=True, hide_index=True)
    elif uploaded_files:
        st.info("Files are loaded — click **Tokenize uploaded file(s)** to process them.")
