from datetime import datetime
import streamlit as st
from src.healthcare_pdf_hub.utils.pdf_utils import human_size, pdf_preview_html

def process_uploads(files, bucket_key: str):
    """Persist uploaded files in session_state under the given bucket (tab)."""
    if "uploads" not in st.session_state:
        st.session_state.uploads = {"medical": [], "medicine": [], "hospital": []}
    bucket = st.session_state.uploads[bucket_key]

    for f in files:
        pdf_bytes = f.read()
        entry = {
            "name": f.name,
            "size": len(pdf_bytes),
            "pages": "—",  # page count will be computed in preview
            "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data": pdf_bytes,
        }
        bucket.append(entry)

def render_bucket_table(bucket):
    if not bucket:
        st.info("No PDFs uploaded yet.")
        return

    rows = [
        {"File name": item["name"], "Size": human_size(item["size"]),
         "Pages": item.get("pages", "—"), "Uploaded": item["uploaded_at"]}
        for item in bucket
    ]
    st.dataframe(rows, use_container_width=True)

    with st.expander("Preview & download", expanded=False):
        for i, item in enumerate(bucket, start=1):
            st.subheader(f"{i}. {item['name']}")
            st.caption(f"Size: {human_size(item['size'])} • Pages: {item.get('pages','—')} • Uploaded: {item['uploaded_at']}")
            st.components.v1.html(pdf_preview_html(item["data"]), height=620, scrolling=True)
            st.download_button(
                label="Download PDF",
                data=item["data"],
                file_name=item["name"],
                mime="application/pdf",
                key=f"dl_{item['name']}_{item['uploaded_at']}",
            )
            st.divider()

