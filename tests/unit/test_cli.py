"""Tests for CLI argument parsing and dispatch."""

from pathlib import Path

from maine_bills.cli import build_parser


def test_default_sessions():
    parser = build_parser()
    args = parser.parse_args([])
    assert args.sessions == [132]


def test_single_session():
    parser = build_parser()
    args = parser.parse_args(["--sessions", "131"])
    assert args.sessions == [131]


def test_multiple_sessions():
    parser = build_parser()
    args = parser.parse_args(["--sessions", "130", "131", "132"])
    assert args.sessions == [130, 131, 132]


def test_default_repo_id():
    parser = build_parser()
    args = parser.parse_args([])
    assert args.repo_id == "pem207/maine-bills"


def test_custom_repo_id():
    parser = build_parser()
    args = parser.parse_args(["--repo-id", "other/repo"])
    assert args.repo_id == "other/repo"


def test_publish_flag_defaults_false():
    parser = build_parser()
    args = parser.parse_args([])
    assert args.publish is False


def test_publish_flag():
    parser = build_parser()
    args = parser.parse_args(["--publish"])
    assert args.publish is True


def test_default_local_dir():
    parser = build_parser()
    args = parser.parse_args([])
    assert args.local_dir == Path("./data")


def test_custom_local_dir():
    parser = build_parser()
    args = parser.parse_args(["--local-dir", "/tmp/bills"])
    assert args.local_dir == Path("/tmp/bills")


def test_workers_default():
    parser = build_parser()
    args = parser.parse_args([])
    assert args.workers >= 4


def test_workers_custom():
    parser = build_parser()
    args = parser.parse_args(["--workers", "16"])
    assert args.workers == 16


def test_enrich_flag_defaults_false():
    parser = build_parser()
    args = parser.parse_args([])
    assert args.enrich is False


def test_enrich_flag():
    parser = build_parser()
    args = parser.parse_args(["--enrich"])
    assert args.enrich is True


def test_enrich_noops_gracefully_when_matcher_unavailable(mocker, tmp_path):
    """--enrich without the sponsor_matching module warns and completes normally."""
    import pandas as pd

    from maine_bills.cli import main

    mock_scraper = mocker.patch("maine_bills.cli.BillScraper")
    mock_scraper.return_value.scrape_session.return_value = pd.DataFrame(
        [{"session": 132, "sponsors": ["Senator SMITH"], "text": "hello"}]
    )
    mocker.patch(
        "sys.argv",
        ["maine-bills", "--sessions", "132", "--enrich", "--local-dir", str(tmp_path)],
    )
    mock_load = mocker.patch("maine_bills.enrichment.load_matcher", return_value=None)
    mock_enrich = mocker.patch("maine_bills.enrichment.enrich_dataframe")

    assert main() == 0
    mock_load.assert_called_once()
    mock_enrich.assert_not_called()
    assert (tmp_path / "132" / "train-00000-of-00001.parquet").exists()


def test_enrich_applies_matcher_when_available(mocker, tmp_path):
    """--enrich runs enrich_dataframe on each session when a matcher loads."""
    import pandas as pd

    from maine_bills.cli import main

    df = pd.DataFrame([{"session": 132, "sponsors": ["Senator SMITH"], "text": "hello"}])
    mock_scraper = mocker.patch("maine_bills.cli.BillScraper")
    mock_scraper.return_value.scrape_session.return_value = df
    mocker.patch(
        "sys.argv",
        ["maine-bills", "--sessions", "132", "--enrich", "--local-dir", str(tmp_path)],
    )
    matcher_fn = lambda sponsors: [None] * len(sponsors)  # noqa: E731
    mocker.patch("maine_bills.enrichment.load_matcher", return_value=matcher_fn)
    mock_enrich = mocker.patch("maine_bills.enrichment.enrich_dataframe", return_value=df)

    assert main() == 0
    mock_enrich.assert_called_once()
    assert mock_enrich.call_args.args[1] is matcher_fn


def test_no_enrich_never_touches_enrichment(mocker, tmp_path):
    """Without --enrich, the enrichment module is never invoked."""
    import pandas as pd

    from maine_bills.cli import main

    mock_scraper = mocker.patch("maine_bills.cli.BillScraper")
    mock_scraper.return_value.scrape_session.return_value = pd.DataFrame(
        [{"session": 132, "text": "hello"}]
    )
    mocker.patch("sys.argv", ["maine-bills", "--sessions", "132", "--local-dir", str(tmp_path)])
    mock_load = mocker.patch("maine_bills.enrichment.load_matcher")

    assert main() == 0
    mock_load.assert_not_called()
