import re
from app.config import settings


def split_text(text: str, chunk_size: int = None, chunk_overlap: int = None) -> list[dict]:
    chunk_size = chunk_size or settings.chunk_size
    chunk_overlap = chunk_overlap or settings.chunk_overlap

    paragraphs = re.split(r'\n\s*\n', text.strip())
    chunks = []
    current_chunk = ""
    current_len = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        para_len = len(para)

        if current_len + para_len <= chunk_size:
            if current_chunk:
                current_chunk += "\n\n"
            current_chunk += para
            current_len += para_len
        else:
            if current_chunk:
                chunks.append(current_chunk)
            overlap_text = current_chunk[-chunk_overlap:] if current_chunk and chunk_overlap > 0 else ""
            current_chunk = overlap_text + ("\n\n" + para if overlap_text else para)
            current_len = len(current_chunk)

    if current_chunk:
        chunks.append(current_chunk)

    return [{"text": c, "index": i} for i, c in enumerate(chunks) if c.strip()]


def split_text_with_images(text: str, image_positions: list[dict], chunk_size: int = None, chunk_overlap: int = None) -> list[dict]:
    chunks = split_text(text, chunk_size, chunk_overlap)
    char_offset = 0
    chunk_ranges = []
    for c in chunks:
        start = text.find(c["text"], char_offset)
        if start == -1:
            start = char_offset
        end = start + len(c["text"])
        chunk_ranges.append((start, end))
        char_offset = end

    for img in image_positions:
        img_pos = img["char_position"]
        best_idx = 0
        best_dist = float("inf")
        for i, (cs, ce) in enumerate(chunk_ranges):
            if cs <= img_pos <= ce:
                best_idx = i
                break
            dist = min(abs(img_pos - cs), abs(img_pos - ce))
            if dist < best_dist:
                best_dist = dist
                best_idx = i
        if "images" not in chunks[best_idx]:
            chunks[best_idx]["images"] = []
        if img["path"] not in chunks[best_idx]["images"]:
            chunks[best_idx]["images"].append(img["path"])

    for c in chunks:
        c.setdefault("images", [])
    return chunks
