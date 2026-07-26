"""Diagnose why a session extracts far fewer sponsor mentions than its peers.

Issue #13 item 4: session 132 reports 2,770 sponsor mentions across 3,375
documents (0.8/doc) against ~2.8/doc for session 131. That makes 132's headline
98.2% match rate rest on a suspiciously small denominator.

Three hypotheses, and this script separates them:

1. **Composition.** Amendments carry no "Presented by" block, so a session
   that is mostly amendments should have a low mentions/doc by construction and
   nothing is wrong. Reported as the original-vs-amendment split.
2. **Extraction regression.** The sponsor block is present in `text` but the
   patterns missed it. Detected by re-running the current extractor over the
   published `text` of documents that have no stored sponsors: any mentions it
   finds now are ones v1 lost.
3. **Missing source.** The block never made it into `text` at all (layout
   change, preamble stripped). Detected by looking for a "Presented by" /
   "Cosponsored by" marker in documents where re-extraction also finds nothing.

Run it over the suspect session *and* a healthy one; the comparison is the
finding, not either number alone.

Usage:
    uv run python scripts/diagnose_sponsor_extraction.py \\
        --sessions 132 131 \\
        --parquet-source hf://datasets/pem207/maine-bills \\
        --output report
"""

import argparse
import importlib.util
import json
import logging
import re
import sys
from pathlib import Path

import pandas as pd

from maine_bills.text_extractor import TextExtractor

logger = logging.getLogger("diagnose_sponsor_extraction")

# Reuse the report script's parquet loader rather than duplicating it.
_REPORT = Path(__file__).with_name("run_matching_report.py")
_spec = importlib.util.spec_from_file_location("_matching_report", _REPORT)
if _spec is None or _spec.loader is None:  # pragma: no cover - path/packaging error
    raise ImportError(f"Cannot load the matching report helpers from {_REPORT}")
_report = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_report)

# Deliberately looser than the extractor's patterns: this asks "is there a
# sponsor block here at all", not "can we parse it".
SPONSOR_MARKER = re.compile(r"presented\s+by|cosponsored\s+by|sponsored\s+by", re.IGNORECASE)

SAMPLE_CHARS = 900
DEFAULT_SAMPLES = 15


def sponsor_count(value) -> int:
    """Length of a stored sponsors cell, tolerating None/NaN/ndarray."""
    if value is None or isinstance(value, float):
        return 0
    return len(value)


def summarize_group(df: pd.DataFrame) -> dict:
    """Document/mention counts for one slice of a session."""
    counts = df["sponsors"].map(sponsor_count)
    docs = len(df)
    mentions = int(counts.sum())
    return {
        "documents": docs,
        "mentions": mentions,
        "mentions_per_doc": round(mentions / docs, 2) if docs else 0.0,
        "zero_sponsor_docs": int((counts == 0).sum()),
        "zero_sponsor_share": round(float((counts == 0).mean()), 4) if docs else 0.0,
    }


def analyze_zero_sponsor_docs(df: pd.DataFrame) -> dict:
    """Split documents with no stored sponsors by what their text actually holds.

    ``recoverable`` means the current extractor finds mentions in the published
    text that the stored record does not have — an extraction gap, fixable
    without re-downloading PDFs. ``marker_only`` means a sponsor block appears
    to be present but nothing parses out of it: the interesting failures.
    ``no_marker`` means the text genuinely has no sponsor block.
    """
    recoverable, marker_only, no_marker = [], [], []

    for _, row in df.iterrows():
        if sponsor_count(row.get("sponsors")) > 0:
            continue
        text = row.get("text")
        name = row.get("source_filename", "")
        if not isinstance(text, str) or not text:
            no_marker.append(name)
            continue
        if TextExtractor._extract_sponsor_mentions(text):
            recoverable.append(name)
        elif SPONSOR_MARKER.search(text):
            marker_only.append(name)
        else:
            no_marker.append(name)

    return {
        "recoverable": recoverable,
        "marker_only": marker_only,
        "no_marker": no_marker,
    }


def diagnose_session(df: pd.DataFrame, session: int, samples: int) -> tuple[dict, list[dict]]:
    """Full breakdown for one session, plus text samples worth eyeballing."""
    is_amendment = df["amendment_code"].notna()
    originals = df[~is_amendment]

    result = {
        "session": session,
        "all": summarize_group(df),
        "originals": summarize_group(originals),
        "amendments": summarize_group(df[is_amendment]),
    }

    # Only originals are expected to carry a sponsor block, so the zero-sponsor
    # breakdown over amendments would just be noise.
    buckets = analyze_zero_sponsor_docs(originals)
    result["zero_sponsor_originals"] = {
        name: {"count": len(names), "examples": names[:10]} for name, names in buckets.items()
    }

    # Sample the two buckets that indicate a real problem, in that order.
    interesting = buckets["marker_only"] + buckets["recoverable"]
    by_filename = originals.set_index("source_filename", drop=False)
    text_samples = []
    for name in interesting[:samples]:
        row = by_filename.loc[name]
        if isinstance(row, pd.DataFrame):  # duplicate filenames, if any
            row = row.iloc[0]
        text = row.get("text") or ""
        text_samples.append(
            {
                "session": session,
                "source_filename": name,
                "bucket": "marker_only" if name in buckets["marker_only"] else "recoverable",
                "reextracted": TextExtractor._extract_sponsor_mentions(text)[:10],
                "text_head": text[:SAMPLE_CHARS],
            }
        )

    return result, text_samples


def format_markdown(results: list[dict]) -> str:
    """A table that makes the composition-vs-regression question answerable."""
    lines = [
        "# Sponsor extraction diagnosis",
        "",
        "Mentions per document, split by whether the document is an amendment.",
        "Amendments carry no sponsor block, so only the `originals` column is",
        "comparable across sessions.",
        "",
        "| session | docs | amendments | originals | mentions/doc (all) "
        "| mentions/doc (originals) | originals w/o sponsors |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['session']} | {r['all']['documents']} | {r['amendments']['documents']} "
            f"| {r['originals']['documents']} | {r['all']['mentions_per_doc']} "
            f"| {r['originals']['mentions_per_doc']} "
            f"| {r['originals']['zero_sponsor_share']:.1%} |"
        )

    lines += [
        "",
        "## Original bills with no stored sponsors",
        "",
        "- **recoverable** — the current extractor finds mentions in the published",
        "  text that the record lacks: an extraction gap, no re-scrape needed.",
        "- **marker_only** — a 'Presented by' block is present but nothing parses.",
        "- **no_marker** — no sponsor block in the text at all.",
        "",
        "| session | recoverable | marker_only | no_marker |",
        "|---|---|---|---|",
    ]
    for r in results:
        z = r["zero_sponsor_originals"]
        lines.append(
            f"| {r['session']} | {z['recoverable']['count']} "
            f"| {z['marker_only']['count']} | {z['no_marker']['count']} |"
        )
    return "\n".join(lines) + "\n"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sessions", type=int, nargs="+", required=True)
    parser.add_argument("--parquet-source", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--samples",
        type=int,
        default=DEFAULT_SAMPLES,
        help="Text samples to dump per session from the problem buckets",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s:%(levelname)s:%(message)s")
    args = parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)

    results, samples = [], []
    for session in args.sessions:
        logger.info(f"=== Session {session} ===")
        df = _report.load_session_bills(args.parquet_source, session)
        result, session_samples = diagnose_session(df, session, args.samples)
        results.append(result)
        samples.extend(session_samples)
        logger.info(
            f"Session {session}: {result['originals']['mentions_per_doc']} mentions/doc "
            f"over {result['originals']['documents']} original bills"
        )

    (args.output / "sponsor-extraction-diagnosis.json").write_text(json.dumps(results, indent=2))
    (args.output / "sponsor-extraction-samples.json").write_text(json.dumps(samples, indent=2))
    markdown = format_markdown(results)
    (args.output / "sponsor-extraction-diagnosis.md").write_text(markdown)
    print(markdown)
    return 0


if __name__ == "__main__":
    sys.exit(main())
