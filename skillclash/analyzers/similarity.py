from __future__ import annotations

import hashlib
import math
import re
import unicodedata

from skillclash.parse.tokenize import tokenize


def normalize_text_for_similarity(text: str) -> str:
    """Normalize text: NFKC, lowercase, remove frontmatter versions, collapse whitespace."""
    norm = unicodedata.normalize("NFKC", text).lower()
    # Remove version indicators like "version: 1.0.0" or "v1.2.3"
    norm = re.sub(r"\bversion\s*[:=]\s*[\d.]+\b", "", norm)
    norm = re.sub(r"\bv\d+(\.\d+)+\b", "", norm)
    norm = re.sub(r"\s+", " ", norm)
    return norm.strip()


def extract_shingles(text: str, k: int = 5) -> set[str]:
    """Generate k-gram shingles. For Latin uses words, for CJK uses characters."""
    norm = normalize_text_for_similarity(text)
    tokens = tokenize(norm)
    if not tokens:
        return set()

    if len(tokens) < k:
        return {" ".join(tokens)}

    shingles: set[str] = set()
    for i in range(len(tokens) - k + 1):
        shingles.add(" ".join(tokens[i : i + k]))
    return shingles


def jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """Calculate exact Jaccard similarity between two sets."""
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


# MinHash & LSH using blake2b
NUM_HASHES = 128
LSH_BANDS = 32
LSH_ROWS = 4  # 32 * 4 = 128
_MERSENNE_PRIME = (1 << 61) - 1
_HASH_A = [((i * 10007 + 3) & 0xFFFFFFFFFFFFF) for i in range(NUM_HASHES)]
_HASH_B = [((i * 20011 + 7) & 0xFFFFFFFFFFFFF) for i in range(NUM_HASHES)]


def compute_minhash(shingles: set[str], num_hashes: int = NUM_HASHES) -> list[int]:
    """Compute MinHash signature of length num_hashes using blake2b."""
    if not shingles:
        return [0] * num_hashes

    signatures = [0xFFFFFFFFFFFFFFFF] * num_hashes
    for s in shingles:
        s_bytes = s.encode("utf-8")
        base_h = int.from_bytes(hashlib.blake2b(s_bytes, digest_size=8).digest(), "little")
        for i in range(num_hashes):
            val = (_HASH_A[i] * base_h + _HASH_B[i]) % _MERSENNE_PRIME
            if val < signatures[i]:
                signatures[i] = val
    return signatures


def minhash_similarity(sig_a: list[int], sig_b: list[int]) -> float:
    """Estimate Jaccard similarity from MinHash signatures."""
    if not sig_a or not sig_b:
        return 0.0
    matches = sum(1 for a, b in zip(sig_a, sig_b) if a == b)
    return matches / len(sig_a)


class MinHashLSH:
    """LSH index for MinHash signatures using 32 bands of 4 rows."""

    def __init__(self, bands: int = LSH_BANDS, rows: int = LSH_ROWS):
        self.bands = bands
        self.rows = rows
        self.buckets: list[dict[int, list[str]]] = [{} for _ in range(bands)]

    def insert(self, item_id: str, signature: list[int]) -> None:
        for b in range(self.bands):
            start = b * self.rows
            band_tuple = tuple(signature[start : start + self.rows])
            band_hash = hash(band_tuple)
            bucket = self.buckets[b]
            if band_hash not in bucket:
                bucket[band_hash] = []
            bucket[band_hash].append(item_id)

    def query_candidates(self, signature: list[int]) -> set[str]:
        candidates: set[str] = set()
        for b in range(self.bands):
            start = b * self.rows
            band_tuple = tuple(signature[start : start + self.rows])
            band_hash = hash(band_tuple)
            bucket = self.buckets[b]
            if band_hash in bucket:
                candidates.update(bucket[band_hash])
        return candidates


# TF-IDF & Cosine Similarity for Section 8.3
def build_tfidf_model(documents: list[list[str]]) -> tuple[dict[str, float], float]:
    """Calculate IDF for all terms across documents.

    idf = ln((1 + N) / (1 + df)) + 1
    Returns:
        (idf_dict, median_idf)
    """
    n = len(documents)
    df: dict[str, int] = {}
    for doc in documents:
        seen = set(doc)
        for term in seen:
            df[term] = df.get(term, 0) + 1

    idf_dict: dict[str, float] = {}
    for term, freq in df.items():
        idf_dict[term] = math.log((1.0 + n) / (1.0 + freq)) + 1.0

    all_idfs = sorted(idf_dict.values())
    median_idf = all_idfs[len(all_idfs) // 2] if all_idfs else 1.0
    return idf_dict, median_idf


def compute_tfidf_vector(
    tokens: list[str],
    idf_dict: dict[str, float],
) -> dict[str, float]:
    """Compute L2-normalized TF-IDF vector for a document.

    tf = 1 + ln(count)
    weight = tf * idf
    """
    counts: dict[str, int] = {}
    for t in tokens:
        counts[t] = counts.get(t, 0) + 1

    vec: dict[str, float] = {}
    sq_sum = 0.0
    for term, count in counts.items():
        tf = 1.0 + math.log(count)
        idf = idf_dict.get(term, 1.0)
        w = tf * idf
        vec[term] = w
        sq_sum += w * w

    norm = math.sqrt(sq_sum)
    if norm > 0:
        for term in vec:
            vec[term] /= norm

    return vec


def cosine_similarity(
    vec_a: dict[str, float],
    vec_b: dict[str, float],
) -> tuple[float, list[tuple[str, float]]]:
    """Compute cosine similarity between two normalized sparse vectors and top shared terms."""
    common_terms = set(vec_a.keys()) & set(vec_b.keys())
    if not common_terms:
        return 0.0, []

    score = 0.0
    term_contributions: list[tuple[str, float]] = []
    for term in common_terms:
        contrib = vec_a[term] * vec_b[term]
        score += contrib
        term_contributions.append((term, contrib))

    term_contributions.sort(key=lambda x: x[1], reverse=True)
    return score, term_contributions
