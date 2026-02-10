import argparse
import logging
import sys
from pathlib import Path
from .scraper import BillScraper


def setup_logging(log_file: Path, level: int = logging.INFO) -> logging.Logger:
    """Set up logging to both file and console."""
    logger = logging.getLogger("maine_bills")
    logger.setLevel(level)

    # File handler
    log_file.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(level)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)

    # Formatter
    formatter = logging.Formatter(
        "%(asctime)s:%(levelname)s:%(message)s"
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def main() -> int:
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="Scrape Maine legislature bills"
    )
    parser.add_argument(
        "-s", "--session",
        default="131",
        type=str,
        help="Legislative session number (default: 131)"
    )
    parser.add_argument(
        "-o", "--output-dir",
        default="./",
        type=str,
        help="Output directory for bill data (default: ./)"
    )

    args = parser.parse_args()
    output_dir = Path(args.output_dir) / args.session
    log_file = output_dir / "scraper.log"

    logger = setup_logging(log_file)

    try:
        scraper = BillScraper(args.session, output_dir, logger)
        new_count = scraper.scrape_session()
        logger.info(f"Scraping complete: {new_count} new bills added")
        return 0

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
