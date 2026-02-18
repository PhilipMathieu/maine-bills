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
