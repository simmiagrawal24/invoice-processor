"""PDF text extraction: pypdf -> pdfplumber -> OCR (pypdfium2 + tesseract, optional)."""


def _ocr_fallback(pdf_path: str) -> str:
    """Render pages to images and OCR. Returns '' if deps/OS binaries missing."""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return ""
    try:
        import pytesseract
    except ImportError:
        return ""
    try:
        doc = pdfium.PdfDocument(pdf_path)
        out = []
        for i in range(min(len(doc), 3)):  # first 3 pages enough for invoices
            bitmap = doc[i].render(scale=2).to_pil()
            out.append(pytesseract.image_to_string(bitmap))
        return "\n".join(out).strip()
    except Exception:
        return ""  # tesseract binary missing, corrupt PDF, etc.


def extract_text(pdf_path: str) -> tuple[str, str]:
    """Returns (text, method_used): 'pypdf' | 'pdfplumber' | 'ocr' | 'partial' | 'failed'."""
    text = ""
    try:
        from pypdf import PdfReader

        reader = PdfReader(pdf_path)
        parts = [(p.extract_text() or "") for p in reader.pages]
        text = "\n".join(parts).strip()
        if len(text) > 50:
            return text, "pypdf"
    except Exception:
        pass
    try:
        import pdfplumber

        with pdfplumber.open(pdf_path) as pdf:
            parts = [(p.extract_text() or "") for p in pdf.pages]
        text2 = "\n".join(parts).strip()
        if len(text2) > len(text):
            text = text2
        if len(text) > 50:
            return text, "pdfplumber"
    except Exception:
        pass
    if len(text) <= 50:
        ocr = _ocr_fallback(pdf_path)
        if len(ocr) > len(text):
            return ocr, "ocr"
    if text:
        return text, "partial"
    return "", "failed"
