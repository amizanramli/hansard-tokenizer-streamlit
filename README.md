# Hansard Tokenizer — Streamlit Interface

A Streamlit front-end for [`warisan_nlp`](./wheels/warisan_nlp-0.1.0-py3-none-any.whl), a
lightweight, rule-based Bahasa Melayu tokenizer/lemmatizer built on spaCy. It provides:

- **Quick text demo** — paste any Bahasa Melayu text and see `text` / `lemma` / `root`
  for every token, live.
- **Upload & tokenize Hansard files** — upload one or more Hansard transcript `.xlsx`
  workbooks (as produced by the Hansard Extractor pipeline: a `Transcript` sheet with a
  `Speech Text` column) and get back:
  - an enriched copy of each workbook with a `Speech Tokens` column, and
  - one combined, long-format token table (one row per token) as a downloadable CSV.

Row-level pipeline errors (the bundled hyphen-merger occasionally hits messy real-world
text) are caught per row and fall back to a plain split rather than aborting the whole file
— see `src/tokenizer.py`.

## Project layout

```
.
├── app.py                  # Streamlit entrypoint
├── src/
│   ├── tokenizer.py         # wraps warisan_tokenizer.bm_spacy_pipeline, cached + fault-tolerant
│   └── xlsx_processing.py   # Hansard workbook tokenizing + long-format explode helpers
├── wheels/
│   └── warisan_nlp-0.1.0-py3-none-any.whl   # bundled so installs work with no external index
├── sample_data/             # drop your own Hansard .xlsx here to try locally (gitignored)
├── .streamlit/config.toml   # theme + upload size limit
└── requirements.txt
```

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

The app opens at `http://localhost:8501`.

## Deploy on Streamlit Community Cloud

1. Push this repo to GitHub (see below).
2. Go to [share.streamlit.io](https://share.streamlit.io), sign in, and pick **New app**.
3. Point it at this repo, branch `main`, main file `app.py`.
4. Deploy — `requirements.txt` installs the bundled wheel automatically (no extra
   configuration needed since the `.whl` ships inside the repo).

## Pushing this repo to GitHub

This folder is already a git repository with an initial commit. To publish it:

```bash
# 1. Create an empty repo on GitHub first (github.com/new), don't initialize it with
#    a README/license/gitignore — this repo already has those.

# 2. From this folder:
git remote add origin https://github.com/<your-username>/<repo-name>.git
git branch -M main
git push -u origin main
```

If you use the `gh` CLI instead:

```bash
gh repo create <repo-name> --public --source=. --remote=origin --push
```

## Notes on the Hansard workbook format

The sidebar lets you override the sheet name and text column if your files differ from
the default `Transcript` / `Speech Text` layout used by the Hansard Extractor project.

## License

MIT — see [LICENSE](./LICENSE).
