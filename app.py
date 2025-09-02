import os
import base64
import pandas as pd
from datetime import datetime
from pathlib import Path
import streamlit as st
#from dotenv import load_dotenv
import sys
#sys.path.append(str(Path(__file__).resolve().parent / "src"))


from src.healthcare_pdf_hub.utils.chat_model import get_chat_model, ask_chat_model
from src.healthcare_pdf_hub.utils.faiss_utils import create_faiss_index, retrive_relevant_docs
from src.healthcare_pdf_hub.config import choose_resource_dirs
from src.healthcare_pdf_hub.catalogs import MEDICINE_CATALOG, MEDICINE_BRANDS, HOSPITALS_2025
from src.healthcare_pdf_hub.utils.pdf_utils import (
    human_size, get_page_count, pdf_preview_html, list_pdfs_from_folder
)
from src.healthcare_pdf_hub.ui.components import process_uploads, render_bucket_table
from langchain.text_splitter import RecursiveCharacterTextSplitter
from src.healthcare_pdf_hub.utils.pdf_utils import extract_text_from_pdf, pdf_preview_html 
from src.healthcare_pdf_hub.utils.pdf_utils import make_zip_from_items  
# Code to create/store the index for FAISS and retreive the relevant documents

# langchain vectorstores documentation: https://python.langchain.com/docs/modules/data_connection/vectorstores/integrations/faiss
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from typing import List
# Load .env explicitly from project root
load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

EURI_API_KEY = os.getenv("EURI_API_KEY", "")
#EURI_API_KEY="euri-484faba612354addf4b29e160cccfac93e09d7ff55cc32f58fca5b4dce3e837c"


st.set_page_config(page_title="Healthcare PDF Hub", page_icon="📄", layout="wide")



# Initialize once and cache (prevents re-creating on every rerun)
@st.cache_resource(show_spinner=False)
def _init_chat_model():
    if not EURI_API_KEY:
        raise RuntimeError("EURI_API_KEY is missing. Set it in your .env.")
    return get_chat_model(EURI_API_KEY)

try:
    chat_model = _init_chat_model()
except Exception as e:
    st.error(f"Chat model init failed: {e}")
    chat_model = None

# Resolve default resource folders (env -> absolute -> relative fallback)
DEFAULT_DIRS = choose_resource_dirs()


# ---------- UI ----------
st.title("📄 Healthcare PDF Hub")
st.caption("Upload and manage PDFs across Medical Documents, Medicine Details, and Hospital Details.")

tabs = st.tabs([
    "ℹ️ Introduction",
    "🧾 Medical Documents",
    "💊 Medicine Details",
    "🏥 Hospital Details",
    "📘 User Guide"
])



# ---------- Introduction Tab ----------
with tabs[0]:
    st.subheader("📄 Healthcare PDF Hub – Overview")
    st.markdown(
        """
        ### 🏥 Welcome to **Healthcare PDF Hub**
        
        This app helps you organize and access healthcare resources more easily:

        - **🧾 Medical Documents** → Upload and manage lab reports, prescriptions, discharge summaries, and clinical notes.  
        - **💊 Medicine Details** → Upload leaflets, dosage guides, and OTC information sheets, plus browse a catalog of common medicines.  
        - **🏥 Hospital Details** → Upload brochures or admission forms, and explore the **Top 10 Hospitals in India (Newsweek 2025 Rankings)** with quick search and notes.  

        ⚙️ *Powered by AI & LangChain • Designed for doctors, patients, and healthcare professionals.*  
        """
    )
    st.info("Use the tabs above to navigate between different sections of the app.")
    st.divider()
    
    
# ---------- Medical Documents Tab ----------
with tabs[1]:
    st.subheader("Upload Medical Document PDFs")
    files = st.file_uploader(
        "Choose one or more PDF files",
        type=["pdf"],
        accept_multiple_files=True,
        key="up_medical",
        help="Upload lab reports, prescriptions, discharge summaries, etc.",
    )

    # Cache this upload batch so Submit can use the same PDFs
    if files:
        last_batch_snapshot = [{"name": f.name, "data": f.getvalue()} for f in files]
        if st.button("Add to Library", type="primary", key="btn_medical"):
            process_uploads(files, "medical")
            st.session_state["medical_last_batch"] = last_batch_snapshot
            st.success("Added to Medical Documents.")

    st.divider()

    # --- Prompt + Submit (always visible; disabled until docs exist) ---
    med_bucket = st.session_state.get("uploads", {}).get("medical", [])
    med_has_docs = len(med_bucket) > 0

    note_val = st.text_input(
        "Enter your prompt",
        key="med_doc_note",
        disabled=not med_has_docs,
        placeholder="e.g., summarize lab report, abnormal values, discharge instructions…"
    )
    submit_med = st.button("Submit Prompt", key="btn_medical_note", disabled=not med_has_docs)

    if not med_has_docs:
        st.caption("⬆️ Upload PDFs and click **Add to Library** to enable search & answer.")

    if submit_med:
        # Prefer the most recent batch; fallback to everything already in the Library
        batch = st.session_state.get("medical_last_batch", [])
        if not batch:
            batch = [{"name": it["name"], "data": it["data"]} for it in med_bucket]

        if not batch:
            st.warning("No PDFs available. Please upload and click Add to Library.")
        else:
            # 1) Extract text from each PDF
            all_content = []
            for item in batch:
                text = extract_text_from_pdf(item["data"])
                if text:
                    all_content.append(text)

            if not all_content:
                st.warning("No extractable text found (PDFs may be scanned images).")
            else:
                # 2) Split texts into chunks
                splitter = RecursiveCharacterTextSplitter(
                    chunk_size=1000,
                    chunk_overlap=200,
                    length_function=len,
                )
                chunks = []
                for t in all_content:
                    chunks.extend(splitter.split_text(t))

                if not chunks:
                    st.warning("Could not create chunks from the uploaded PDFs.")
                else:
                    # 3) Build FAISS index from chunks
                    vectorstore = create_faiss_index(chunks)
                    st.session_state["medical_vectorstore"] = vectorstore
                    # st.success(f"Built FAISS index with {len(chunks)} chunks.")

                    # 4) Retrieval + LLM
                    prompt = (note_val or "").strip()
                    if not prompt:
                        st.info("Type a prompt above to run retrieval.")
                    else:
                        relevant_docs = retrive_relevant_docs(vectorstore, prompt)
                        context = "\n\n".join([doc.page_content for doc in relevant_docs])

                        system_prompt = f"""You are MediChat Pro — an intelligent medical document assistant.

Based on the following medical documents, provide accurate and helpful answers.
If information is not in the documents, say so clearly. Cite sources when used.

# Documents
{context}

# User Question
{prompt}

# Answer"""
                        if not chat_model:
                            st.error("Chat model is not initialized. Check EURI_API_KEY.")
                        else:
                            with st.spinner("Generating answer…"):
                                response = ask_chat_model(chat_model, system_prompt)
                            st.markdown("### 🧠 MediChat Pro — Answer")
                            st.write(response)

    st.divider()
    st.subheader("Library")
    bucket = st.session_state.get("uploads", {}).get("medical", [])
    render_bucket_table(bucket)


# ---------- Medicine Details Tab ----------
with tabs[2]:
    st.subheader("Upload Medicine Detail PDFs")
    files = st.file_uploader(
        "Choose one or more PDF files",
        type=["pdf"],
        accept_multiple_files=True,
        key="up_medicine",
        help="Upload medicine leaflets, OTC info sheets, dosage guides, etc.",
    )

    # Cache this upload batch so search can use the same PDFs
    if files:
        last_batch_snapshot = [{"name": f.name, "data": f.getvalue()} for f in files]

        if st.button("Add to Library", type="primary", key="btn_medicine"):
            process_uploads(files, "medicine")
            st.session_state["medicine_last_batch"] = last_batch_snapshot
            st.success("Added to Medicine Details.")

    st.divider()

    # ---------- Browse Common Medicines ----------
    st.subheader("Browse Common Medicines")

    col1, col2 = st.columns([1, 1])
    with col1:
        category = st.selectbox(
            "Select Category",
            options=list(MEDICINE_CATALOG.keys()),
            index=0,
            key="med_cat"
        )
    with col2:
        med_options = MEDICINE_CATALOG.get(category, [])
        medicine = st.selectbox(
            "Select Medicine",
            options=med_options if med_options else ["—"],
            key="med_name"
        )

    if med_options:
        st.success(
            f"**Selected:** {medicine}\n\n"
            f"**Category:** {category}"
            + (
                f"\n\n**Common brand/examples:** {MEDICINE_BRANDS.get(medicine, '—')}"
                if MEDICINE_BRANDS.get(medicine) else ""
            )
        )

    with st.expander("Safety notes", expanded=False):
        st.markdown(
            """
- This dropdown is informational and **not** a prescription.
- **NSAIDs** (e.g., ibuprofen, aspirin, diclofenac) should be avoided in **suspected dengue** or certain conditions without medical advice.
- For injections/emergency/anticonvulsants/antidotes listed here (marked **clinical use**), seek professional care.
- Always check labels, allergy history, and interactions. When in doubt, consult a clinician/pharmacist.
            """
        )

    # (Removed: Manual search / notes + Save note)

    st.divider()

    # ---------- Medicine Table → drives search ----------
    rows = []
    for cat, meds in MEDICINE_CATALOG.items():
        for med in meds:
            rows.append({
                "Medicine": med,
                "Category": cat,
                "Brand examples": MEDICINE_BRANDS.get(med, "—"),
            })
    med_df = pd.DataFrame(rows)

    st.subheader("Medicine Table")
    st.dataframe(med_df, use_container_width=True, hide_index=True)

    med_pick = st.selectbox(
        "Pick a medicine to search in your PDFs",
        options=sorted(med_df["Medicine"].unique()),
        key="med_table_pick"
    )

    # Enable search only when docs are in Library
    med_bucket = st.session_state.get("uploads", {}).get("medicine", [])
    med_has_docs = len(med_bucket) > 0

    do_search = st.button(
        "🔍 Search Selected Medicine",
        key="btn_med_table_search",
        disabled=not med_has_docs
    )
    if not med_has_docs:
        st.caption("⬆️ Upload PDFs and click **Add to Library** to enable search & answer.")

    if do_search:
        # Prefer the most recent batch; fallback to everything already in the Library
        med_batch = st.session_state.get("medicine_last_batch", [])
        if not med_batch:
            med_batch = [{"name": it["name"], "data": it["data"]} for it in med_bucket]

        if not med_batch:
            st.warning("No PDFs available. Please upload and click Add to Library.")
        else:
            # 1) Extract text
            all_content = []
            for item in med_batch:
                txt = extract_text_from_pdf(item["data"])
                if txt:
                    all_content.append(txt)

            if not all_content:
                st.warning("No extractable text found (PDFs may be scanned images).")
            else:
                # 2) Chunk
                splitter = RecursiveCharacterTextSplitter(
                    chunk_size=1000,
                    chunk_overlap=200,
                    length_function=len,
                )
                chunks = []
                for t in all_content:
                    chunks.extend(splitter.split_text(t))

                # 3) Index
                vectorstore = create_faiss_index(chunks)
                st.session_state["medicine_vectorstore"] = vectorstore
                st.success(f"Built FAISS index with {len(chunks)} chunks.")

                # 4) Query from table selection (+ brand aliases)
                brand_hint = MEDICINE_BRANDS.get(med_pick, "")
                prompt = f"{med_pick} {brand_hint}".strip()

                relevant_docs = retrive_relevant_docs(vectorstore, prompt)
                context = "\n\n".join([doc.page_content for doc in relevant_docs])

                # 5) Ask the chat model
                system_prompt = f"""You are MediChat Pro — an intelligent medical document assistant for India (IN).

# Mission
- Answer user questions **based on the provided medical documents first**.
- Be accurate, cautious, and helpful.

# Citations
- Cite document sources used, e.g., [Document Title — page/section].

# Uploaded Medicine PDFs (context)
{context}

# User Question
{prompt}

# Answer"""
                if not chat_model:
                    st.error("Chat model is not initialized. Check EURI_API_KEY.")
                else:
                    with st.spinner("Generating answer…"):
                        response = ask_chat_model(chat_model, system_prompt)

                    st.markdown("### 🧠 MediChat Pro — Answer")
                    st.write(response)

    # ---------- Library (bottom) ----------
    st.divider()
    st.subheader("Library")
    bucket = st.session_state.get("uploads", {}).get("medicine", [])
    render_bucket_table(bucket)
    
    
    
# ---------- Hospital Details Tab ----------
with tabs[3]:
    st.subheader("Upload Hospital Detail PDFs")
    files = st.file_uploader(
        "Choose one or more PDF files",
        type=["pdf"],
        accept_multiple_files=True,
        key="up_hospital",
        help="Upload hospital brochures, department lists, admission forms, etc.",
    )
    if files:
        last_batch_snapshot = [{"name": f.name, "data": f.getvalue()} for f in files]
        if st.button("Add to Library", type="primary", key="btn_hospital"):
            process_uploads(files, "hospital")
            st.session_state["hospital_last_batch"] = last_batch_snapshot
            st.success("Added to Hospital Details.")

    st.divider()

    # ---------- Browse Top Hospitals (Newsweek 2025) ----------
    st.subheader("Browse Top Hospitals (Newsweek 2025)")

    from src.healthcare_pdf_hub.catalogs import HOSPITALS_2025
    # Removed Quick search. Use full list directly.
    options = [f'{h["name"]} — {h["city"]}' for h in HOSPITALS_2025] if HOSPITALS_2025 else []
    selected_label = st.selectbox(
        "Select Hospital",
        options=options if options else ["— No hospitals available —"],
        key="hospital_select"
    )

    # ---------- Selected Hospital ----------
    if options:
        idx = options.index(selected_label)
        chosen = HOSPITALS_2025[idx]
        st.success(f"**Selected:** {chosen['name']}  \n**City:** {chosen['city']}")

        # ---------- PROMPT + ANSWER (right after selection) ----------
        hosp_bucket = st.session_state.get("uploads", {}).get("hospital", [])
        hosp_has_docs = len(hosp_bucket) > 0

        prompt_val = st.text_input(
            "Enter your prompt",
            key="hosp_prompt",
            disabled=not hosp_has_docs,
            placeholder=f"Ask about {chosen['name']} (departments, admission, insurance, OPD timings…)"
        )
        submit_hosp = st.button("Submit Prompt", key="btn_hospital_note", disabled=not hosp_has_docs)

        if not hosp_has_docs:
            st.caption("⬆️ Upload PDFs and click **Add to Library** to enable search & answer.")

        if submit_hosp:
            # Prefer the most recent batch; fallback to everything in the Library
            hosp_batch = st.session_state.get("hospital_last_batch", [])
            if not hosp_batch:
                hosp_batch = [{"name": it["name"], "data": it["data"]} for it in hosp_bucket]

            if not hosp_batch:
                st.warning("No PDFs available. Please upload and click Add to Library.")
            else:
                # 1) Extract text
                all_content = []
                for item in hosp_batch:
                    txt = extract_text_from_pdf(item["data"])
                    if txt:
                        all_content.append(txt)

                if not all_content:
                    st.warning("No extractable text found (PDFs may be scanned images).")
                else:
                    # 2) Chunk
                    splitter = RecursiveCharacterTextSplitter(
                        chunk_size=1000,
                        chunk_overlap=200,
                        length_function=len,
                    )
                    chunks = []
                    for t in all_content:
                        chunks.extend(splitter.split_text(t))

                    # 3) Index
                    vectorstore = create_faiss_index(chunks)
                    st.session_state["hospital_vectorstore"] = vectorstore
                    #st.success(f"Built FAISS index with {len(chunks)} chunks.")

                    # 4) Retrieval using selected hospital + user prompt
                    prompt_query = " ".join(
                        [p for p in [chosen["name"], chosen["city"], (prompt_val or "").strip()] if p]
                    )
                    relevant_docs = retrive_relevant_docs(vectorstore, prompt_query)
                    context = "\n\n".join([doc.page_content for doc in relevant_docs])

                    # 5) Ask the model
                    system_prompt = f"""You are MediChat Pro — an intelligent medical document assistant for India (IN).

# Mission
- Answer questions **based on the uploaded hospital PDFs first** (brochures, department lists, admission/insurance info).
- Be accurate and cautious; if info isn’t in the documents, say so clearly.

# Citations
- Cite document sources used, e.g., [Document Title — page/section].

# Uploaded Hospital PDFs (context)
{context}

# User Question
{prompt_query}

# Answer"""
                    if not chat_model:
                        st.error("Chat model is not initialized. Check EURI_API_KEY.")
                    else:
                        with st.spinner("Generating answer…"):
                            response = ask_chat_model(chat_model, system_prompt)
                        st.markdown("### 🧠 MediChat Pro — Answer")
                        st.write(response)

        # ---------- Matching PDFs (by filename) ----------
        st.markdown("**Matching PDFs (by filename):**")
        hosp_hits = [
            item for item in hosp_bucket
            if chosen["name"].split("(")[0].strip().lower() in item["name"].lower()
               or chosen["city"].lower() in item["name"].lower()
               or any(k in item["name"].lower() for k in
                      ["apollo", "aiims", "yashoda", "gleneagles", "medanta", "hiranandani", "pgimer", "cmc"])
        ]
        if hosp_hits:
            for i, item in enumerate(hosp_hits, start=1):
                st.write(f"- {i}. **{item['name']}** · {item['pages']} pages · {item['uploaded_at']}")
        else:
            st.caption("No matching hospital PDFs yet — upload brochures or department lists above.")

    # ---------- Library (bottom) ----------
    st.divider()
    st.subheader("Library")
    bucket = st.session_state.get("uploads", {}).get("hospital", [])
    render_bucket_table(bucket)

# ---------- User Guide Tab ----------
with tabs[4]:
    st.subheader("📘 User Guide & Resources")

    # YouTube video embed
    st.markdown("### 🎥 Watch the App Walkthrough")
    st.video("https://www.youtube.com/watch?v=dQw4w9WgXcQ")  # replace link with your real video

    st.divider()

    # Folder organization with expanders (reads from disk, not from uploads)
    st.markdown("### 📂 Resource Folders")

    # Helper to render one folder block with "Download ALL" button
    def render_folder_expander(title: str, folder: Path,
                               zip_prefix: str, zip_key_prefix: str, dl_key_prefix: str):
        with st.expander(title):
            if not folder.exists():
                st.warning(f"Folder not found: {folder}")
                return

            st.caption(f"Showing PDFs from: `{folder}`")
            items = list_pdfs_from_folder(folder)
            if not items:
                st.info("No PDFs found in this folder.")
                return

            # ⬇️ One-click ZIP of all PDFs
            all_zip_bytes = make_zip_from_items(items)
            st.download_button(
                label=f"⬇️ Download ALL ({len(items)} PDFs) as ZIP",
                data=all_zip_bytes,
                file_name=f"{zip_prefix}_all.zip",
                mime="application/zip",
                key=f"{zip_key_prefix}_all",
                use_container_width=True
            )
            st.divider()

            # Per-file list + download
            for i, item in enumerate(items, start=1):
                st.write(f"{i}. {item['name']}  ({item['pages']} pages • {human_size(item['size'])})")
                st.download_button(
                    label=f"Download {item['name']}",
                    data=item["data"],
                    file_name=item["name"],
                    mime="application/pdf",
                    key=f"{dl_key_prefix}_{i}"
                )

    # ---- Medical Reports (from folder) ----
    render_folder_expander(
        "📁 Medical Reports",
        DEFAULT_DIRS["medical"],
        zip_prefix="medical_reports",
        zip_key_prefix="zip_userguide_med",
        dl_key_prefix="dl_userguide_med_folder",
    )

    # ---- Medicine (from folder) ----
    render_folder_expander(
        "📁 Medicine",
        DEFAULT_DIRS["medicine"],
        zip_prefix="medicine",
        zip_key_prefix="zip_userguide_medi",
        dl_key_prefix="dl_userguide_medi_folder",
    )

    # ---- Hospital (from folder) ----
    render_folder_expander(
        "📁 Hospital",
        DEFAULT_DIRS["hospital"],
        zip_prefix="hospital",
        zip_key_prefix="zip_userguide_hosp",
        dl_key_prefix="dl_userguide_hosp_folder",
    )

    st.divider()

 
# Footer note
st.caption(
    "Tip: Install `pypdf` to see page counts. All files remain in memory for this session; "
    "modify code to persist to disk or cloud storage if needed."
)

# -------- Custom Footer --------
st.markdown(
    """
    <div style='text-align: center; margin-top: 50px; font-size: 15px;'>
        <span style='font-size:18px;'>⚙️ Powered by <b style="color:#4B8BBE;">Euri AI</b> & 
        <b style="color:#FF4B4B;">LangChain</b> | 🧾 Medical Document Intelligence</span>
        <br><br>
        <span style='font-size:16px;'>👨‍💻 Developed by <b style="color:#1E90FF;">Abhrajit Pal</b> 
        | 📧 <a href="mailto:virabhra@yahoo.com" style="text-decoration:none; color:#FF8C00;">
        virabhra@yahoo.com</a> | © 2025 All rights reserved</span>
    </div>
    """,
    unsafe_allow_html=True
)
