# VITTy — VIT Chennai Campus AI Assistant

VITTy is a Streamlit-based RAG and tool-calling assistant for VIT Chennai
students. It answers campus and hostel questions from the local knowledge base
and can file hostel maintenance tickets after collecting the required details.

## Features

- **Grounded campus answers:** Retrieves relevant passages from
  `data/vit_info.txt` using ChromaDB.
- **Gemini embeddings:** Uses `gemini-embedding-001` for both document and
  query embeddings.
- **Maintenance agent:** Exposes `file_maintenance_ticket` to Gemini. The
  assistant collects the block, room number, and issue description before
  writing a ticket to `data/maintenance_tickets.json`.
- **Streamlit interface:** Provides chat history and a browser-based interface
  in `gui_app.py`.
- **CLI interface:** The same RAG and maintenance workflow is available through
  `app.py`.

## Technology

- Python 3.10+
- Google GenAI API
  - Chat model: `gemini-3.8-flash`
  - Embedding model: `gemini-embedding-001`
- ChromaDB persistent vector store
- Streamlit
- `python-dotenv`

## Setup

1. Create and activate a virtual environment:

   ```bat
   python -m venv venv
   venv\Scripts\activate
   ```

2. Install dependencies:

   ```bat
   python -m pip install -r requirements.txt
   ```

3. Create a `.env` file in the project root:

   ```text
   GEMINI_API_KEY=your_api_key_here
   ```

   You can start from [.env.example](./.env.example). Never commit `.env` or
   expose the API key in source code.

4. Start the web application:

   ```bat
   streamlit run gui_app.py
   ```

   Open the local URL printed by Streamlit, normally
   `http://localhost:8501`.

To use the CLI instead:

```bat
python app.py
```

## Project files

| Path | Purpose |
|---|---|
| `gui_app.py` | Streamlit web application |
| `app.py` | CLI RAG and maintenance agent |
| `data/vit_info.txt` | Source knowledge used for retrieval |
| `data/maintenance_tickets.json` | Local ticket file; ignored by Git |
| `chroma_db/` | Local ChromaDB collection; ignored by Git |
| `eval_sheet.md` | Evaluation cases and reported results |

The ChromaDB collection is refreshed when the SHA-256 hash of
`data/vit_info.txt` changes. The first run therefore requires API access to
create document embeddings.

## Evaluation

The evaluation cases in [eval_sheet.md](./eval_sheet.md) cover:

1. Domain guardrails and persona behavior.
2. RAG retrieval and unsupported-answer fallback.
3. Maintenance tool invocation, slot filling, and JSON persistence.
4. Adversarial prompts, ambiguity, malformed data, duplicate tickets, and UI
   recovery.

The evaluation contains 50 cases:

- 30 original smoke cases with project-reported results of 30/30.
- 20 additional challenge cases that must be executed before publishing a
  final benchmark score.

The original `100% (30/30)` is therefore a historical smoke-test result, not
the final accuracy of the assistant. The scoring rule is:

```text
score = PASS / (PASS + FAIL) * 100
```

Cases marked `NOT RUN` are excluded until they are actually tested. The
current defensible verdict is **provisionally acceptable for the original
smoke cases, but not yet benchmark-verified**. A final score of at least 90%
requires at least 45 passes out of 50 after all challenge cases have been
executed. Results should be rerun after changing the model, prompt, knowledge
file, embedding model, or tool schema.

## Limitations

- Ticket persistence is a local JSON simulation, not a production help-desk
  integration.
- The assistant depends on a valid Gemini API key and network access.
- Answers are grounded in the contents of `data/vit_info.txt`; information
  outside that file may be unavailable or require official confirmation.
- The application does not yet provide authentication, authorization, or
  concurrent ticket-write protection for production deployment.
- The current evaluation score is not a statistically representative measure
  of real-world accuracy.

## GitHub publishing checklist

Before pushing:

1. Rotate any API key that has ever been exposed or shared.
2. Confirm `.env`, `venv/`, `chroma_db/`, and
   `data/maintenance_tickets.json` are ignored.
3. Review the staged file list for secrets and personal data:

   ```bat
   git status --short
   git diff --cached --name-only
   ```

4. Create the repository, then push the clean source files:

   ```bat
   git init
   git add app.py gui_app.py data/vit_info.txt eval_sheet.md README.md requirements.txt .gitignore .env.example
   git commit -m "Initial VITTy campus assistant"
   git branch -M main
   git remote add origin https://github.com/<username>/<repository>.git
   git push -u origin main
   ```

Do not use `git add .` until you have confirmed that the ignore rules and
staged file list are correct.
