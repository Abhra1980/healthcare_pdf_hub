
# High-Level Design (HLD): Healthcare PDF Hub (Modular)

## 1. Purpose & Goals
**Purpose:** A Streamlit application that lets users upload, browse, and retrieve knowledge from healthcare PDFs (Medical Documents, Medicine Details, Hospital Details). It adds lightweight RAG (retrieve-and-generate) using FAISS + sentence‑transformer embeddings and an LLM (Euri AI wrapper) to answer questions grounded in the uploaded content.

**Goals**
- Organize PDFs by domain with quick preview/download.
- Read PDFs from local “resource folders” (Windows paths with relative fallbacks).
- Build in-memory search over uploaded PDFs (chunk → embed → FAISS).
- Ask questions and get answers that **cite retrieved text**.
- Modular, easy-to-extend codebase.

**Out of scope (v1)**
- Multi-user tenancy or DB persistence.
- Server-side persistence of uploads (session-only).
- OCR for scanned PDFs.
- Enterprise auth/SSO.

---

## 2. Users & Use Cases
- **Clinician/Pharmacist**: search guidance leaflets, dosage notes, hospital brochures.
- **Patient/Advocate**: organize reports; ask clarifying questions.
- **Ops/Admin**: maintain curated “resource folders” and export bundles (ZIP).

**Key flows**
1) Upload PDFs → Add to Library → Preview/Download.  
2) Build FAISS index from uploaded files → Query → Answer with citations.  
3) Browse local resource folders and **Download ALL (ZIP)** per folder.

---

## 3. System Context & Architecture

```
+------------------+        +-------------------+         +---------------------------+
|   User Browser   | <----> |   Streamlit App   |  -----> |  Euri AI Chat Model API   |
| (single-session) |        |  (Python runtime) |         | (euriai.langchain wrapper)|
+------------------+        +----+---------+----+         +---------------------------+
                                   |         \
                                   |          \
                                   |           \ Embeddings (CPU)
                                   |            \
                                   v             v
                         +----------------+   +------------------+
                         |     pypdf      |   | sentence-        |
                         |  text extract  |   | transformers     |
                         +--------+-------+   +---------+--------+
                                  |                       |
                                  v                       v
                        Chunking (LangChain)          +--------+
                          (Recursive splitter)  --->  | FAISS  |
                                                      | index  |
                                                      +--------+
```

**External libs**
- `streamlit`, `pypdf`
- `langchain`, `langchain-community`, `langchain-text-splitters`
- `sentence-transformers`, `faiss-cpu`, `torch`
- `euriai.langchain` (LLM wrapper), `python-dotenv`

---

## 4. Module View

```
Healthcare-PDF-Hub-Modular/
├─ app.py
├─ requirements.txt
├─ README.md
└─ src/
   └─ healthcare_pdf_hub/
      ├─ __init__.py
      ├─ catalogs.py          # catalog/brands, hospitals list
      ├─ config.py            # resolves resource folders
      ├─ ui/
      │  └─ components.py     # reusable UI widgets
      └─ utils/
         ├─ pdf_utils.py      # extract/preview/list/zip helpers
         ├─ chat_model.py     # Euri AI wrapper
         └─ faiss_utils.py    # FAISS index + retrieval
```

**Key components**
- **app.py**: tabs, flows, session state, chat model init (`@st.cache_resource`).
- **pdf_utils.py**: `extract_text_from_pdf`, `get_page_count`, `pdf_preview_html`, `list_pdfs_from_folder`, `make_zip_from_items`.
- **faiss_utils.py**: `create_faiss_index(texts)`, `retrive_relevant_docs(vectorstore, query, k)`.
- **chat_model.py**: `get_chat_model(api_key)`, `ask_chat_model(chat_model, question)`.
- **catalogs.py**: `MEDICINE_CATALOG`, `MEDICINE_BRANDS`, `HOSPITALS_2025`.
- **config.py**: env → absolute → relative folder resolution.
- **ui/components.py**: `process_uploads`, `render_bucket_table`.

---

## 5. Data Design

### Session state
```python
{
  "uploads": {
     "medical":  [ {name, size, pages, uploaded_at, data}, ... ],
     "medicine": [ ... ],
     "hospital": [ ... ]
  },
  "medical_last_batch":   [ {name, data}, ... ],
  "medicine_last_batch":  [ {name, data}, ... ],
  "hospital_last_batch":  [ {name, data}, ... ],

  "medical_vectorstore":  <FAISS>,
  "medicine_vectorstore": <FAISS>,
  "hospital_vectorstore": <FAISS>,
}
```

### Retrieval index
- Chunk size: 1000 chars; overlap: 200 (configurable).
- Embeddings: `sentence-transformers/all-MiniLM-L6-v2` (default).
- Vector store: FAISS (in-memory).

---

## 6. Core Flows

### Upload & Library
1. User selects PDFs → **Add to Library** → saved to `session_state.uploads[tab]`.
2. Save the batch bytes in `*_last_batch` for downstream indexing.

### Build Index & Ask
1. Prompt (disabled until docs added) or selection-driven prompt (Medicine/Hospital).
2. Extract (pypdf) → Chunk (LangChain) → Embed (MiniLM) → **FAISS**.
3. Retrieve K docs → compose prompt with context → **ask_chat_model** → render answer.

### Resource Folders
- Read via `list_pdfs_from_folder(Path)` and show:
  - Per-file downloads
  - **Download ALL (ZIP)** via `make_zip_from_items(items)`

---

## 7. Functional Requirements
- Upload & manage PDFs per domain.
- Preview and download PDFs.
- Read curated folders & ZIP-all.
- RAG: index uploaded PDFs and answer questions using retrieved context.
- Disable prompts until Library has docs.

---

## 8. Non-Functional Requirements
- **Performance:** CPU-friendly embeddings; chunking bounded by doc size.
- **Scalability:** Single-session, in-memory; future persistence optional.
- **Reliability:** Handle empty/invalid PDFs gracefully.
- **Security/Privacy:** `.env` for `EURI_API_KEY`; session-only data; avoid logging PHI.
- **Compliance:** Informational; not a medical device; conservative guidance.
- **Observability:** UI alerts + Streamlit logs.

---

## 9. Configuration
- `.env`: `EURI_API_KEY` (required).  
- Optional: `HPDFHUB_MEDICAL_DIR`, `HPDFHUB_MEDICINE_DIR`, `HPDFHUB_HOSPITAL_DIR`.
- `requirements.txt` pins compatible versions for Torch/Transformers/SBERT/FAISS.

---

## 10. Error Handling & Edge Cases
- Scanned PDFs → extraction empty → warn; roadmap: OCR.
- Model init failures → clear UI error (missing key / package).
- Large uploads → Streamlit size limits; consider pagination or caps.
- Package mismatch → documented version sets.

---

## 11. Security Considerations
- Keep `.env` out of VCS.
- Limit LLM context to retrieved text; avoid sending entire PDFs.
- No background telemetry of content.
- Display disclaimers; avoid prescriptive dosing unless cited.

---

## 12. Extensibility Roadmap
- Persist FAISS indexes to disk (save/load local).
- OCR fallback (`pdf2image` + `pytesseract`).
- Rich citations with file + page metadata per chunk.
- Hybrid retrieval (BM25 + dense) & multi-query strategies.
- Multi-user mode + role-based access.
- Feedback loops & analytics (query logs, thumbs).

---

## 13. Deployment
- **Local/dev:** `pip install -r requirements.txt` → `streamlit run app.py`.
- **Server:** Reverse proxy to Streamlit; secure env vars; optional volume mounts for folders and persistence.

---

## 14. Testing
- **Unit:** `extract_text_from_pdf`, `make_zip_from_items`, `create_faiss_index`.
- **Integration:** End-to-end RAG on sample PDFs per tab; verify top-k quality.
- **UX:** Prompt disabled until docs exist; ZIP contains expected files.

---

## 15. Risks & Assumptions
- Initial model downloads (network/time).
- Memory growth with many/large PDFs.
- Legal/clinical risk mitigated via disclaimers and conservative answers.
