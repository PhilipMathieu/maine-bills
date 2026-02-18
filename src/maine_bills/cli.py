import argparse
import logging
import sys
from pathlib import Path

from .scraper import BillScraper


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scrape Maine legislature bills")
    parser.add_argument(
        "--sessions",
        nargs="+",
        type=int,
        default=[132],
        metavar="SESSION",
        help="Legislative session number(s) to scrape (default: 132)",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Upload parquet files to HuggingFace Hub after scraping",
    )
    parser.add_argument(
        "--repo-id",
        default="pem207/maine-bills",
        help="HuggingFace dataset repo ID (default: pem207/maine-bills)",
    )
    parser.add_argument(
        "--local-dir",
        type=Path,
        default=Path("./data"),
        help="Local directory for parquet output (default: ./data)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Number of parallel download workers (default: 8)",
    )
    return parser


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s:%(levelname)s:%(message)s",
        stream=sys.stdout,
    )
    logger = logging.getLogger("maine_bills")

    args = build_parser().parse_args()

    try:
        for session in args.sessions:
            scraper = BillScraper(session, workers=args.workers, logger=logger)
            df = scraper.scrape_session()
            logger.info(f"Session {session}: {len(df)} records")

            if args.publish:
                from .publish import publish_session, sync_dataset_card
                publish_session(df, session, args.repo_id, args.local_dir)
            else:
                out_dir = args.local_dir / str(session)
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path = out_dir / "train-00000-of-00001.parquet"
                df.to_parquet(out_path, index=False)
                logger.info(f"Saved {out_path}")

        if args.publish:
            from .publish import sync_dataset_card
            sync_dataset_card(args.repo_id)

        return 0

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
