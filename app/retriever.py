"""Document chunking and BM25 retrieval using SQLite FTS5."""

import re
from . import db

CHUNK_SIZE = 800       # chars per chunk
CHUNK_OVERLAP = 100    # overlap between consecutive chunks
TOP_K = 5              # default number of chunks to retrieve
MAX_CONTEXT_CHARS = 5000  # max total chars injected into prompt

# Common technical synonyms/expansions for better recall
TERM_EXPANSIONS = {
    "sram": ["sram", "memory", "ram", "embedded"],
    "gpio": ["gpio", "pin", "port", "input", "output"],
    "timer": ["timer", "counter", "prescaler", "period"],
    "adc": ["adc", "analog", "digital", "converter", "channel"],
    "dma": ["dma", "transfer", "memory", "direct"],
    "interrupt": ["interrupt", "irq", "nvic", "handler", "isr", "vector"],
    "uart": ["uart", "usart", "serial", "baud", "tx", "rx"],
    "spi": ["spi", "mosi", "miso", "sck", "slave", "master"],
    "i2c": ["i2c", "scl", "sda", "address", "slave"],
    "can": ["can", "bus", "message", "filter", "fifo"],
    "clock": ["clock", "rcc", "pll", "hse", "hsi", "sysclk", "prescaler"],
    "flash": ["flash", "memory", "program", "erase", "sector"],
    "register": ["register", "bit", "field", "offset"],
    "address": ["address", "memory", "map", "boundary", "offset"],
    "boot": ["boot", "bootloader", "startup", "reset", "vector"],
    "rtos": ["rtos", "freertos", "task", "scheduler", "semaphore"],
    "pwm": ["pwm", "duty", "cycle", "timer", "output", "compare"],
}

# Stopwords to strip from queries
STOP_WORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'by', 'is', 'was', 'are', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'may', 'might', 'can', 'this', 'that', 'these', 'those',
    'it', 'its', 'not', 'no', 'from', 'as', 'if', 'then', 'than',
    'what', 'where', 'when', 'how', 'which', 'who', 'whom',
    'me', 'my', 'i', 'you', 'your', 'we', 'our', 'they', 'their',
    'tell', 'explain', 'show', 'describe', 'about', 'please',
}


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks, preferring paragraph/sentence boundaries."""
    text = re.sub(r'\n{3,}', '\n\n', text.strip())
    if not text:
        return []

    paragraphs = re.split(r'\n\n+', text)
    chunks = []
    current = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if len(current) + len(para) + 2 <= chunk_size:
            current = f"{current}\n\n{para}".strip()
        else:
            if current:
                chunks.append(current)
            # Handle oversized paragraphs
            while len(para) > chunk_size:
                split_at = para.rfind('. ', 0, chunk_size)
                if split_at == -1:
                    split_at = para.rfind(' ', 0, chunk_size)
                if split_at == -1:
                    split_at = chunk_size
                chunks.append(para[:split_at + 1].strip())
                para = para[split_at + 1:].strip()
            current = para

    if current:
        chunks.append(current)

    return [c for c in chunks if len(c.strip()) > 30]


def index_file(file_id: str, mentor: str, filename: str, text: str):
    """Chunk a file's text and insert into FTS5 index."""
    db.delete_file_chunks(file_id)
    chunks = chunk_text(text)
    for idx, content in enumerate(chunks):
        db.add_file_chunk(file_id, mentor, filename, idx, content)
    return len(chunks)


def remove_file(file_id: str):
    """Remove all chunks for a file from the index."""
    db.delete_file_chunks(file_id)


def expand_query(query: str) -> str:
    """Analyse user query: extract key terms, strip fluff, expand with synonyms."""
    raw_terms = re.findall(r'[a-zA-Z0-9_]+', query.lower())
    # Keep hex addresses as-is (e.g. 0x20000000)
    hex_addrs = re.findall(r'0x[0-9a-fA-F]+', query)

    # Filter stopwords, keep meaningful terms
    key_terms = [t for t in raw_terms if t not in STOP_WORDS and len(t) > 1]

    # Expand known technical terms with synonyms
    expanded = set(key_terms)
    for term in key_terms:
        if term in TERM_EXPANSIONS:
            expanded.update(TERM_EXPANSIONS[term])

    # Add back hex addresses
    expanded.update(hex_addrs)

    return " OR ".join(expanded) if expanded else ""


def search(query: str, mentor: str, top_k: int = TOP_K) -> list[dict]:
    """Search file chunks relevant to a query using BM25 ranking."""
    fts_query = expand_query(query)
    if not fts_query:
        return []

    return db.search_chunks_fts(fts_query, mentor, top_k)


def build_context(query: str, mentor: str, top_k: int = TOP_K) -> str:
    """Search and format relevant chunks into a context string for the LLM."""
    results = search(query, mentor, top_k)
    if not results:
        return ""

    context = "\n\n--- RELEVANT SECTIONS (from uploaded files) ---\n"
    total_chars = 0
    for r in results:
        snippet = r["content"]
        if total_chars + len(snippet) > MAX_CONTEXT_CHARS:
            snippet = snippet[:MAX_CONTEXT_CHARS - total_chars]
            context += f"\n### {r['filename']} (chunk {r['chunk_idx']}) [truncated]\n{snippet}\n"
            break
        context += f"\n### {r['filename']} (chunk {r['chunk_idx']})\n{snippet}\n"
        total_chars += len(snippet)

    return context
