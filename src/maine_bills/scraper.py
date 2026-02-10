import logging
from pathlib import Path
from typing import List, Optional
import requests
from bs4 import BeautifulSoup
from .text_extractor import TextExtractor


class BillScraper:
    """Scrapes Maine legislature bills from the official website."""

    BASE_URL = "http://lldc.mainelegislature.org/Open/LDs"
    TIMEOUT = 10

    def __init__(self, session: str, output_dir: Path, logger: Optional[logging.Logger] = None):
        """
        Initialize the bill scraper.

        Args:
            session: Legislative session number (e.g., "131")
            output_dir: Base directory for storing bills
            logger: Optional logger instance
        """
        self.session = session
        self.output_dir = Path(output_dir)
        self.logger = logger or logging.getLogger(__name__)
        self.session_url = f"{self.BASE_URL}/{session}/"
        self.pdf_dir = self.output_dir / "pdf"
        self.txt_dir = self.output_dir / "txt"

    def _ensure_directories(self) -> None:
        """Create necessary directories if they don't exist."""
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        self.txt_dir.mkdir(parents=True, exist_ok=True)

    def _bill_already_processed(self, bill_id: str) -> bool:
        """
        Check if a bill has already been processed.

        Args:
            bill_id: Legislative document number

        Returns:
            True if text file exists, False otherwise
        """
        return (self.txt_dir / f"{bill_id}.txt").exists()

    def _fetch_bill_list(self) -> List[str]:
        """
        Fetch list of bill IDs from the legislature website.

        Returns:
            List of bill IDs (e.g., ["131-LD-0001", "131-LD-0002", ...])

        Raises:
            requests.RequestException: If fetching fails
        """
        self.logger.debug(f"Fetching bill list from {self.session_url}")
        res = requests.get(self.session_url, timeout=self.TIMEOUT)
        res.raise_for_status()

        soup = BeautifulSoup(res.content, features="html.parser")
        hrefs = [a.attrs["href"] for a in soup.find_all("a")[1:]]
        bill_ids = [href.split('/')[-1][:-4] for href in hrefs]

        self.logger.info(f"Found {len(bill_ids)} bills in session {self.session}")
        return bill_ids

    def _download_bill_pdf(self, bill_id: str) -> bool:
        """
        Download a single bill PDF.

        Args:
            bill_id: Legislative document number

        Returns:
            True if successful, False otherwise
        """
        pdf_url = f"{self.session_url}{bill_id}.pdf"
        pdf_path = self.pdf_dir / f"{bill_id}.pdf"

        try:
            self.logger.debug(f"Downloading PDF for {bill_id}")
            res = requests.get(pdf_url, timeout=self.TIMEOUT)
            res.raise_for_status()

            with open(pdf_path, 'wb') as f:
                f.write(res.content)

            self.logger.debug(f"Successfully downloaded {bill_id}")
            return True

        except requests.exceptions.RequestException as e:
            self.logger.warning(f"Download error for {bill_id}: {e}")
            return False
        except IOError as e:
            self.logger.warning(f"Could not write PDF for {bill_id}: {e}")
            return False

    def _process_bill(self, bill_id: str) -> bool:
        """
        Process a single bill: download PDF, extract text, clean up.

        Args:
            bill_id: Legislative document number

        Returns:
            True if successful, False otherwise
        """
        if self._bill_already_processed(bill_id):
            self.logger.debug(f"{bill_id} already in corpus")
            return False

        self.logger.info(f"Processing {bill_id}")

        if not self._download_bill_pdf(bill_id):
            return False

        try:
            pdf_path = self.pdf_dir / f"{bill_id}.pdf"
            text = TextExtractor.extract_from_pdf(pdf_path)
            txt_path = self.txt_dir / f"{bill_id}.txt"
            TextExtractor.save_text(txt_path, text)

            pdf_path.unlink()  # Remove PDF after extraction
            self.logger.debug(f"Extracted and cleaned up {bill_id}")
            return True

        except Exception as e:
            self.logger.error(f"Error processing {bill_id}: {e}")
            return False

    def scrape_session(self) -> int:
        """
        Scrape all bills in the configured session.

        Returns:
            Number of newly processed bills

        Raises:
            requests.RequestException: If fetching bill list fails
        """
        self._ensure_directories()
        self.logger.info(f"######### NEW RUN: Session {self.session} #########")

        bill_ids = self._fetch_bill_list()
        new_count = 0

        for bill_id in bill_ids:
            if self._process_bill(bill_id):
                new_count += 1

        self.logger.info(f"Added {new_count} new bills to corpus")
        return new_count
