"""Drift Detection Pipeline — Vietnamese News Headlines.

Simulates real VnExpress RSS data with a reference period (Jan 2025, pre-Tết)
and a current period (Mar 2025, post-Tết). Extracts text features, computes
PSI/KL/KS, emits Prometheus metrics via Pushgateway, and writes a drift report.

Designed to work with real VnExpress RSS data by replacing synth_vn_headlines()
with an actual RSS fetch (see fetch_vnexpress_rss() stub below).
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Optional

import numpy as np
from scipy import stats

HERE = Path(__file__).resolve().parent.parent
DATA_DIR = HERE / "data"
REPORTS_DIR = HERE / "reports"
DATA_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)

# Prometheus Pushgateway — set via env, default to local docker
PUSHGATEWAY = os.getenv("PUSHGATEWAY_URL", "http://localhost:9091")
JOB_NAME = "vn-drift-detection"

# ── Vietnamese vocabulary pools for realistic simulation ─────────
VN_WORDS_PRE_TET = [
    "Tết", "xuân", "lì xì", "bánh chưng", "bánh tét", "hoa đào", "hoa mai",
    "mứt", "dưa hấu", "thịt kho", "cây nêu", "ông Công ông Táo", "gói bánh",
    "chợ Tết", "áo dài", "lễ hội", "đường hoa", "chúc Tết", "mừng tuổi",
    "sum họp", "về quê", "tất niên", "giao thừa", "pháo", "du xuân",
    "vé tàu", "tắc đường", "siêu thị", "giảm giá", "quà Tết",
]
VN_WORDS_POST_TET = [
    "du lịch", "nghỉ dưỡng", "khởi nghiệp", "AI", "ChatGPT", "blockchain",
    "startup", "WTT", "chuyển đổi số", "công nghệ", "điện toán đám mây",
    "thương mại điện tử", "livestream", "TikTok", "influencer", "podcast",
    "năng lượng xanh", "ESG", "tín chỉ carbon", "xe điện", "VinFast",
    "chứng khoán", "lãi suất", "bất động sản", "sáp nhập", "thanh lý",
    "tuyển dụng", "remote", "hybrid", "wellness",
]
VN_COMMON_WORDS = [
    "Việt Nam", "Hà Nội", "TP HCM", "chính phủ", "quốc hội", "người dân",
    "doanh nghiệp", "thị trường", "tăng trưởng", "phát triển", "đầu tư",
    "dự án", "triển khai", "công bố", "chính thức", "đề xuất", "kiến nghị",
    "cảnh báo", "khuyến cáo", "xử lý", "điều tra", "khởi tố", "xét xử",
]
VN_TEMPLATES = [
    "{subject} {verb} {object}",
    "{subject}: {object} {adj}",
    "{subject} {verb} {object} trong {context}",
    "Vì sao {subject} {verb} {object}?",
    "{num} {subject} {verb} tại {location}",
    "{subject} {verb}: '{quote}'",
    "Nóng: {subject} {verb} {object}",
    "{subject} {verb} {object}, {object2} {verb2}",
]

# ── Feature extraction ──────────────────────────────────────────

def tokenize_vn(text: str) -> list[str]:
    """Simple Vietnamese word tokenization by splitting on spaces/punctuation."""
    import re
    return [t.lower() for t in re.findall(r'[a-zA-ZÀ-ỹđĐ]+', text)]


def count_tone_marks(text: str) -> float:
    """Fraction of characters with Vietnamese tone marks (sắc, huyền, hỏi, ngã, nặng)."""
    tone_chars = set("áàảãạắằẳẵặấầẩẫậéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ")
    alpha_chars = [c for c in text if c.isalpha() or c in tone_chars or 'a' <= c.lower() <= 'z']
    if not alpha_chars:
        return 0.0
    tone_count = sum(1 for c in alpha_chars if c in tone_chars)
    return tone_count / len(alpha_chars)


def count_english_ratio(text: str) -> float:
    """Fraction of words that are purely ASCII (likely English/loanwords)."""
    import re
    words = re.findall(r'[a-zA-ZÀ-ỹđĐ]+', text)
    if not words:
        return 0.0
    ascii_count = sum(1 for w in words if all(ord(c) < 128 for c in w))
    return ascii_count / len(words)


def extract_features(headlines: list[str]) -> dict[str, np.ndarray]:
    """Extract numerical features from Vietnamese headlines."""
    lengths = np.array([len(h.split()) for h in headlines], dtype=float)
    tone_ratios = np.array([count_tone_marks(h) for h in headlines], dtype=float)
    eng_ratios = np.array([count_english_ratio(h) for h in headlines], dtype=float)

    # Top unigram frequencies
    all_tokens: list[str] = []
    for h in headlines:
        all_tokens.extend(tokenize_vn(h))
    unigram_counts = Counter(all_tokens)

    return {
        "text_length": lengths,
        "tone_mark_ratio": tone_ratios,
        "english_word_ratio": eng_ratios,
    }


# ── Synthetic data generation ────────────────────────────────────

def synth_vn_headlines(
    n: int,
    seasonal_words: list[str],
    common_words: list[str],
    rng: np.random.Generator,
    english_ratio: float = 0.03,
) -> list[str]:
    """Generate realistic Vietnamese news headlines with controllable drift."""
    headlines = []
    for _ in range(n):
        template = rng.choice(VN_TEMPLATES)
        # Decide subject: sometimes seasonal, sometimes common
        if rng.random() < 0.35:
            subject = rng.choice(seasonal_words)
        else:
            subject = rng.choice(common_words)

        verb = rng.choice(["tăng", "giảm", "đạt", "vượt", "triển khai", "công bố", "ra mắt",
                           "cảnh báo", "đề xuất", "kiến nghị", "khởi động", "hoàn thành"])
        obj_pool = seasonal_words if rng.random() < 0.4 else common_words
        obj = rng.choice(obj_pool)

        headline = template.format(
            subject=subject, verb=verb, object=obj,
            adj=rng.choice(["mạnh mẽ", "ấn tượng", "kỷ lục", "bất ngờ", "đáng chú ý"]),
            context=("bối cảnh " + rng.choice(["kinh tế khó khăn", "chuyển đổi số", "hội nhập quốc tế", "sau đại dịch"])),
            num=str(rng.integers(1, 1000)),
            location=rng.choice(["Hà Nội", "TP HCM", "Đà Nẵng", "Cần Thơ", "miền Trung"]),
            quote=rng.choice(["'Đây là bước ngoặt'", "'Cần có giải pháp đồng bộ'", "'Thị trường đang phục hồi'"]),
            object2=rng.choice(common_words),
            verb2=rng.choice(["được đẩy mạnh", "cần được quan tâm", "đang trên đà phục hồi"]),
        )

        # Inject English words with given probability
        if rng.random() < english_ratio:
            eng_word = rng.choice(["AI", "chatbot", "blockchain", "startup", "livestream",
                                    "TikTok", "influencer", "trending", "viral", "esports",
                                    "metaverse", "green", "smart", "digital", "fintech"])
            headline = headline + " " + eng_word

        headlines.append(headline)
    return headlines


# ── Drift metrics ────────────────────────────────────────────────

def population_stability_index(reference: np.ndarray, current: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(min(reference.min(), current.min()), max(reference.max(), current.max()), bins + 1)
    ref_hist, _ = np.histogram(reference, bins=edges)
    cur_hist, _ = np.histogram(current, bins=edges)
    ref_p = (ref_hist + 1) / (ref_hist.sum() + bins)
    cur_p = (cur_hist + 1) / (cur_hist.sum() + bins)
    return float(np.sum((cur_p - ref_p) * np.log(cur_p / ref_p)))


def kl_divergence(reference: np.ndarray, current: np.ndarray, bins: int = 20) -> float:
    edges = np.linspace(min(reference.min(), current.min()), max(reference.max(), current.max()), bins + 1)
    ref_hist, _ = np.histogram(reference, bins=edges, density=True)
    cur_hist, _ = np.histogram(current, bins=edges, density=True)
    ref_p = (ref_hist + 1e-9) / (ref_hist.sum() + 1e-9 * bins)
    cur_p = (cur_hist + 1e-9) / (cur_hist.sum() + 1e-9 * bins)
    return float(np.sum(ref_p * np.log(ref_p / cur_p)))


def drift_level(psi: float) -> str:
    if psi > 0.25:
        return "significant"
    elif psi > 0.1:
        return "moderate"
    return "stable"


# ── Prometheus pushgateway ───────────────────────────────────────

def push_metrics(summary: dict[str, dict[str, float]]) -> None:
    """Push drift metrics to Prometheus Pushgateway."""
    import urllib.request

    lines = []
    for feature, metrics in summary.items():
        safe_name = feature.replace("_", "")
        lines.append(f"vn_drift_psi{{feature=\"{feature}\"}} {metrics['psi']}")
        lines.append(f"vn_drift_kl{{feature=\"{feature}\"}} {metrics['kl']}")
        lines.append(f"vn_drift_ks_stat{{feature=\"{feature}\"}} {metrics['ks_stat']}")
        lines.append(f"vn_drift_ks_pvalue{{feature=\"{feature}\"}} {metrics['ks_pvalue']}")
        # Drift flag: 1=significant, 0.5=moderate, 0=stable
        flag = 1.0 if metrics["psi"] > 0.25 else (0.5 if metrics["psi"] > 0.1 else 0.0)
        lines.append(f"vn_drift_significant{{feature=\"{feature}\"}} {flag}")

    body = "\n".join(lines) + "\n"

    try:
        req = urllib.request.Request(
            f"{PUSHGATEWAY}/metrics/job/{JOB_NAME}",
            data=body.encode(),
            headers={"Content-Type": "text/plain"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
        print(f"[pushgateway] Pushed {len(lines)} metric lines to {PUSHGATEWAY}")
    except Exception as e:
        print(f"[pushgateway] Push failed (non-fatal): {e}", file=sys.stderr)


# ── Main ─────────────────────────────────────────────────────────

def main() -> int:
    rng = np.random.default_rng(seed=2025)

    # Generate reference (Jan 2025 — pre-Tết) and current (Mar 2025 — post-Tết)
    print("Generating synthetic Vietnamese news headlines...")
    ref_headlines = synth_vn_headlines(1000, VN_WORDS_PRE_TET, VN_COMMON_WORDS, rng, english_ratio=0.03)
    cur_headlines = synth_vn_headlines(1000, VN_WORDS_POST_TET, VN_COMMON_WORDS, rng, english_ratio=0.12)

    # Save sample
    (DATA_DIR / "reference_headlines.txt").write_text("\n".join(ref_headlines[:50]))
    (DATA_DIR / "current_headlines.txt").write_text("\n".join(cur_headlines[:50]))

    # Extract features
    ref_features = extract_features(ref_headlines)
    cur_features = extract_features(cur_headlines)

    # Compute drift per feature
    summary: dict[str, dict[str, float]] = {}
    for feat_name in ref_features:
        ref = ref_features[feat_name]
        cur = cur_features[feat_name]
        psi = population_stability_index(ref, cur)
        kl = kl_divergence(ref, cur)
        ks_stat, ks_p = stats.ks_2samp(ref, cur)
        summary[feat_name] = {
            "psi": round(psi, 4),
            "kl": round(kl, 4),
            "ks_stat": round(float(ks_stat), 4),
            "ks_pvalue": round(float(ks_p), 6),
            "drift": drift_level(psi),
        }

    # Write report
    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "reference_period": "2025-01 (pre-Tết)",
        "current_period": "2025-03 (post-Tết)",
        "n_reference": len(ref_headlines),
        "n_current": len(cur_headlines),
        "features": summary,
        "overall_drift": "significant" if any(
            m["drift"] == "significant" for m in summary.values()
        ) else ("moderate" if any(m["drift"] == "moderate" for m in summary.values()) else "stable"),
    }
    report_path = REPORTS_DIR / "vn-drift-report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"Wrote: {report_path}")

    # Print summary
    print("\n=== Drift Detection Summary ===")
    print(f"  Reference: {report['reference_period']} ({report['n_reference']} headlines)")
    print(f"  Current:   {report['current_period']} ({report['n_current']} headlines)")
    print(f"  Overall:   {report['overall_drift'].upper()}")
    print()
    for feat, m in summary.items():
        print(f"  {feat:<25} PSI={m['psi']:.3f}  KL={m['kl']:.3f}  KS={m['ks_stat']:.3f} (p={m['ks_pvalue']:.4f})  → {m['drift']}")

    # Push to Prometheus
    push_metrics(summary)

    # Top tokens comparison (interpretable drift signal)
    ref_tokens = Counter()
    cur_tokens = Counter()
    for h in ref_headlines:
        ref_tokens.update(tokenize_vn(h))
    for h in cur_headlines:
        cur_tokens.update(tokenize_vn(h))

    ref_top = set(w for w, _ in ref_tokens.most_common(30))
    cur_top = set(w for w, _ in cur_tokens.most_common(30))
    new_tokens = cur_top - ref_top
    gone_tokens = ref_top - cur_top

    print(f"\n  Top tokens new in current: {sorted(new_tokens)[:15]}")
    print(f"  Top tokens gone from ref:  {sorted(gone_tokens)[:15]}")

    return 0


# ── VnExpress RSS fetch stub (real implementation for production) ─

def fetch_vnexpress_rss(category: str = "tin-moi-nhat") -> list[str]:
    """Fetch real VnExpress RSS headlines. Requires network access.

    URL: https://vnexpress.net/rss/{category}.rss
    Returns list of title strings.
    """
    import urllib.request
    import xml.etree.ElementTree as ET

    url = f"https://vnexpress.net/rss/{category}.rss"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Day23-Drift-Detection/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            xml_data = resp.read().decode("utf-8")
        root = ET.fromstring(xml_data)
        titles = [item.find("title").text for item in root.iter("item") if item.find("title") is not None]
        return titles
    except Exception as e:
        print(f"[rss] Failed to fetch {url}: {e}", file=sys.stderr)
        return []


if __name__ == "__main__":
    raise SystemExit(main())
