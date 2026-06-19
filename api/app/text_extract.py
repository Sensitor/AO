"""Extraction de texte (PDF / texte brut) puis découpage en chunks."""
import io

from pypdf import PdfReader


def extract_text(data: bytes, content_type: str | None, filename: str) -> str:
    """Retourne le texte brut d'un document PDF ou texte."""
    name = (filename or "").lower()
    ctype = (content_type or "").lower()

    if name.endswith(".pdf") or "pdf" in ctype:
        reader = PdfReader(io.BytesIO(data))
        parts = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(parts).strip()

    if name.endswith((".txt", ".md", ".markdown")) or ctype.startswith("text/"):
        for enc in ("utf-8", "latin-1"):
            try:
                return data.decode(enc).strip()
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="ignore").strip()

    raise ValueError(f"Type de fichier non supporté: {content_type or filename}")


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """Découpe en fenêtres d'environ `size` caractères, avec un recouvrement.

    Découpage sur les frontières de mots (jamais en plein milieu d'un mot), y
    compris au début des chunks de recouvrement. Un mot plus long que `size` est
    pris seul. La progression d'au moins un mot par itération est garantie.
    """
    text = " ".join(text.split())  # normalise les espaces / sauts de ligne
    if not text:
        return []
    if size <= 0:
        return [text]
    overlap = max(0, min(overlap, size - 1))

    words = text.split(" ")
    n = len(words)
    chunks: list[str] = []
    i = 0
    while i < n:
        # Empile des mots jusqu'à approcher `size` (au moins un mot, même trop long).
        j, cur_len = i, 0
        while j < n:
            add = len(words[j]) + (1 if j > i else 0)
            if j > i and cur_len + add > size:
                break
            cur_len += add
            j += 1
        chunks.append(" ".join(words[i:j]))
        if j >= n:
            break
        # Recule d'environ `overlap` caractères (en mots) pour le chunk suivant.
        back_len, k = 0, j
        while k > i + 1 and back_len < overlap:
            back_len += len(words[k - 1]) + 1
            k -= 1
        i = k  # k >= i + 1 => progression garantie
    return chunks
