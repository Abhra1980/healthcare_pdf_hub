import base64
import io, zipfile
from pathlib import Path
from datetime import datetime


try:
    from pypdf import PdfReader
    HAS_PYPDF = True
except Exception:
    HAS_PYPDF = False   

def human_size(n_bytes: int) -> str:
    if n_bytes is None:
        return "-"
    for unit in ["B", "KB", "MB", "GB"]:
        if n_bytes < 1024.0:
            return f"{n_bytes:0.2f} {unit}"
        n_bytes /= 1024.0
    return f"{n_bytes:0.2f} TB"

def get_page_count(pdf_bytes: bytes) -> str:
    if not HAS_PYPDF:
        return "—"
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        return str(len(reader.pages))
    except Exception:
        return "?"

def pdf_preview_html(pdf_bytes: bytes, height: int = 600) -> str:
    """Embed a PDF in an <object> tag using base64 (works in Streamlit via components.html)."""
    b64 = base64.b64encode(pdf_bytes).decode("utf-8")
    return f"""
    <object data="data:application/pdf;base64,{b64}" type="application/pdf" width="100%" height="{height}">
        <p>PDF preview not available in your browser. Use the download button below.</p>
    </object>
    """

def list_pdfs_from_folder(folder_path: Path):
    """
    Return a list of dicts for every *.pdf in folder_path.
    Each dict matches the in-memory 'entry' shape used by the app.
    """
    items = []
    if not folder_path.exists():
        return items

    for p in sorted(folder_path.glob("*.pdf")):
        try:
            pdf_bytes = p.read_bytes()
            items.append({
                "name": p.name,
                "size": len(pdf_bytes),
                "pages": get_page_count(pdf_bytes),
                "uploaded_at": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "data": pdf_bytes,
                "path": str(p),
            })
        except Exception:
            continue
    return items

def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract all text from a PDF file and return as string."""
    if not HAS_PYPDF:
        return ""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        parts = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
        return "\n".join(parts).strip()
    except Exception:
        return ""

def make_zip_from_items(items) -> bytes:
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for item in items:
            name = item.get("name", "document.pdf")
            data = item.get("data", b"")
            if data:
                zf.writestr(name, data)
    mem.seek(0)
    return mem.getvalue()
