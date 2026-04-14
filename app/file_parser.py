"""Parse uploaded files into text content for LLM context."""


TEXT_EXTENSIONS = {
    "txt", "md", "py", "c", "h", "cpp", "hpp", "cc", "cxx",
    "js", "ts", "jsx", "tsx", "java", "rs", "go", "sh", "bash",
    "yaml", "yml", "json", "xml", "html", "css", "scss",
    "sql", "r", "m", "asm", "s", "ld", "cfg", "ini", "toml",
    "makefile", "cmake", "dockerfile", "csv", "log", "env",
    "gitignore", "editorconfig", "properties",
}


def parse_file(filename: str, content_bytes: bytes) -> str:
    """Extract text content from a file for LLM context."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    basename = filename.lower()

    # Plain text / source code
    if ext in TEXT_EXTENSIONS or basename in ("makefile", "dockerfile", "readme"):
        try:
            return content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return content_bytes.decode("latin-1", errors="replace")

    # PDF
    if ext == "pdf":
        try:
            import PyPDF2
            import io
            reader = PyPDF2.PdfReader(io.BytesIO(content_bytes))
            pages = []
            for i, page in enumerate(reader.pages):
                text = page.extract_text()
                if text:
                    pages.append(f"[Page {i+1}]\n{text}")
            return "\n\n".join(pages) if pages else "[PDF: no extractable text]"
        except Exception as e:
            return f"[Could not parse PDF: {e}]"

    # DOCX
    if ext == "docx":
        try:
            import docx
            import io
            doc = docx.Document(io.BytesIO(content_bytes))
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except Exception as e:
            return f"[Could not parse DOCX: {e}]"

    # Fallback: try as text
    try:
        text = content_bytes.decode("utf-8")
        # If it decoded fine and has printable chars, it's probably text
        if sum(c.isprintable() or c.isspace() for c in text[:500]) / max(len(text[:500]), 1) > 0.9:
            return text
    except UnicodeDecodeError:
        pass

    return f"[Binary file: {filename}, {len(content_bytes)} bytes — cannot parse]"
