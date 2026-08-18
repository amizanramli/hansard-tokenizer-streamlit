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
    build_turn_overview,
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

    # Tokenizing writes its results into session_state instead of a local variable.
    # Streamlit reruns this whole script top-to-bottom on *every* widget interaction
    # (including just picking a row in the "inspect one speech turn" dropdown below),
    # and st.button() only evaluates True on the exact run it was clicked. Keeping the
    # results local to `if st.button(...):` meant selecting a speech turn triggered a
    # rerun where the button was no longer "clicked" - so the whole results section,
    # selection included, disappeared. Session state survives reruns, so it doesn't.
    if uploaded_files and st.button("Tokenize uploaded file(s)", type="primary"):
        enriched_frames: dict[str, pd.DataFrame] = {}
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
            except Exception as exc:  # noqa: BLE001 - surfaced to the user, not swallowed
                errors.append(f"{uf.name}: {exc}")
        progress.progress(1.0, text="Done")

        st.session_state["tokenize_result"] = {
            "enriched_frames": enriched_frames,
            "errors": errors,
            "text_column": text_column,
            "sheet_name": sheet_name,
        }

    result = st.session_state.get("tokenize_result")

    if result is None and uploaded_files:
        st.info("Files are loaded — click **Tokenize uploaded file(s)** to process them.")

    if result is not None:
        enriched_frames = result["enriched_frames"]
        errors = result["errors"]
        # Use the column names the results were actually tokenized with, not whatever
        # is currently in the sidebar text inputs (those may have changed since).
        text_column = result["text_column"]
        sheet_name = result["sheet_name"]

        if errors:
            st.error("Some files failed to process:\n\n" + "\n".join(f"- {e}" for e in errors))

        if enriched_frames:
            combined_turns = pd.concat(enriched_frames.values(), ignore_index=True)
            n_files = len(enriched_frames)

            # Which non-token columns to actually show/export. Keeping every original
            # column (Order, Page, Speaker (As Printed), Constituency, Jawatan,
            # Kementerian, ...) makes the preview unreadable, so default to just
            # 'Matched Name' (falls back to the first column if that's not present).
            available_meta_cols = [
                c for c in combined_turns.columns if c not in (text_column, "Speech Tokens")
            ]
            default_meta = ["Matched Name"] if "Matched Name" in available_meta_cols else (
                available_meta_cols[:1]
            )
            if n_files > 1 and "Source File" in available_meta_cols and "Source File" not in default_meta:
                default_meta = default_meta + ["Source File"]

            id_columns = st.multiselect(
                "Metadata columns to show/export alongside each speech",
                options=available_meta_cols,
                default=default_meta,
                help="Everything else from the original workbook (Order, Page, Constituency, "
                "Jawatan, Kementerian, ...) is left out to keep the table readable.",
                key="id_columns",
            )

            all_long = pd.concat(
                [to_long_format(df, id_columns=id_columns) for df in enriched_frames.values()],
                ignore_index=True,
            )

            st.success(f"Tokenized {n_files} file(s), {len(all_long)} tokens total.")

            st.markdown("#### Speech turns")
            st.caption(
                "One row per speech turn. Pick a row below to see its full text and "
                "token-by-token breakdown."
            )
            overview = build_turn_overview(combined_turns, text_column, id_columns)
            st.dataframe(
                overview,
                use_container_width=True,
                hide_index=True,
                height=350,
                column_config={
                    text_column: st.column_config.TextColumn(text_column, width="large"),
                },
            )

            st.markdown("#### Inspect one speech turn")
            turn_labels = [
                f"{i}. " + " | ".join(str(combined_turns.iloc[i][c]) for c in id_columns)
                if id_columns
                else f"Row {i}"
                for i in range(len(combined_turns))
            ]
            if turn_labels:
                selected = st.selectbox(
                    "Speech turn",
                    options=range(len(turn_labels)),
                    format_func=lambda i: turn_labels[i],
                    key="selected_turn",
                )
                row = combined_turns.iloc[selected]
                st.text_area("Original text", value=str(row[text_column]), height=180, disabled=True)
                token_df = pd.DataFrame(row["Speech Tokens"])
                st.dataframe(token_df, use_container_width=True, hide_index=True)

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
                st.caption("Workbooks keep every original column — only the preview/CSV above is filtered.")
