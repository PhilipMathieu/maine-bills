import logging
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .schema import FILENAME_PATTERN, BillRecord
from .text_extractor import TextExtractor


class BillScraper:
    """Scrapes Maine legislature bills and produces structured records."""

    BASE_URL = "http://lldc.mainelegislature.org/Open/LDs"
    TIMEOUT = 10

    def __init__(self, session: int, workers: int = 8, logger: logging.Logger | None = None):
        self.session = session
        self.workers = workers
        self.logger = logger or logging.getLogger(__name__)
        self.session_url = f"{self.BASE_URL}/{session}/"

    def _fetch_bill_list(self) -> list[str]:
        """Fetch list of bill filenames (without .pdf extension)."""
        self.logger.debug(f"Fetching bill list from {self.session_url}")
        res = requests.get(self.session_url, timeout=self.TIMEOUT)
        res.raise_for_status()

        soup = BeautifulSoup(res.content, features="html.parser")
        filenames = []
        for a in soup.find_all("a"):
            href = a.get("href", "")
            if href.endswith(".pdf"):
                filenames.append(href.split("/")[-1].removesuffix(".pdf"))

        self.logger.info(f"Found {len(filenames)} bills in session {self.session}")
        return filenames

    @retry(
        retry=retry_if_exception_type(requests.exceptions.Timeout),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _download_and_extract_bill(self, filename: str) -> BillRecord:
        """Download a bill PDF, extract text, and return a BillRecord.

        Retries up to 3 times on timeout with exponential backoff (2s, 4s).
        """
        pdf_url = f"{self.session_url}{filename}.pdf"

        response = requests.get(pdf_url, timeout=self.TIMEOUT)
        response.raise_for_status()

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(response.content)
            tmp_path = Path(tmp.name)

        try:
            bill_doc = TextExtractor.extract_bill_document(tmp_path)
            return BillRecord.from_filename_and_bill_document(
                filename=filename,
                bill_doc=bill_doc,
                base_url=self.session_url,
            )
        finally:
            tmp_path.unlink(missing_ok=True)

    def scrape_session(self) -> pd.DataFrame:
        """Scrape all bills in session and return a DataFrame of BillRecords."""
        self.logger.info(f"=== Scraping session {self.session} (workers={self.workers}) ===")

        filenames = self._fetch_bill_list()
        valid = [f for f in filenames if FILENAME_PATTERN.match(f)]
        skipped = len(filenames) - len(valid)
        if skipped:
            self.logger.warning(f"Skipping {skipped} unrecognized filenames")

        records = []
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures = {pool.submit(self._download_and_extract_bill, f): f for f in valid}
            for future in as_completed(futures):
                filename = futures[future]
                try:
                    record = future.result()
                    records.append(record.__dict__)
                except Exception:
                    self.logger.exception(f"Failed to process {filename!r}; skipping")

        self.logger.info(f"Successfully processed {len(records)} bills")
        return pd.DataFrame(records)
