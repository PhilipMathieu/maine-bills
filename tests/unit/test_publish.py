"""Tests for HuggingFace publish logic."""

from unittest.mock import MagicMock

import pandas as pd

# --- publish_session ---

def test_publish_session_writes_parquet_locally(tmp_path, mocker):
    from maine_bills.publish import publish_session

    mocker.patch("maine_bills.publish.HfApi")

    df = pd.DataFrame([{"session": 131, "ld_number": "0001", "text": "hello"}])
    publish_session(df, 131, "pem207/maine-bills", tmp_path)

    expected = tmp_path / "131" / "train-00000-of-00001.parquet"
    assert expected.exists()
    written = pd.read_parquet(expected)
    assert len(written) == 1
    assert written.iloc[0]["ld_number"] == "0001"


def test_publish_session_uploads_to_hf(tmp_path, mocker):
    from maine_bills.publish import publish_session

    mock_api_instance = MagicMock()
    mocker.patch("maine_bills.publish.HfApi", return_value=mock_api_instance)

    df = pd.DataFrame([{"session": 131, "text": "hello"}])
    publish_session(df, 131, "pem207/maine-bills", tmp_path)

    mock_api_instance.upload_file.assert_called_once()
    call_kwargs = mock_api_instance.upload_file.call_args.kwargs
    assert call_kwargs["path_in_repo"] == "data/131/train-00000-of-00001.parquet"
    assert call_kwargs["repo_id"] == "pem207/maine-bills"
    assert call_kwargs["repo_type"] == "dataset"


def test_publish_session_commit_message_includes_record_count(tmp_path, mocker):
    from maine_bills.publish import publish_session

    mock_api_instance = MagicMock()
    mocker.patch("maine_bills.publish.HfApi", return_value=mock_api_instance)

    df = pd.DataFrame([{"session": 131}, {"session": 131}, {"session": 131}])
    publish_session(df, 131, "pem207/maine-bills", tmp_path)

    commit_msg = mock_api_instance.upload_file.call_args.kwargs["commit_message"]
    assert "131" in commit_msg
    assert "3" in commit_msg


# --- sync_dataset_card ---

def test_sync_dataset_card_uploads_readme(mocker):
    from maine_bills.publish import sync_dataset_card

    mock_api_instance = MagicMock()
    mocker.patch("maine_bills.publish.HfApi", return_value=mock_api_instance)

    # Simulate two session directories in the HF repo (RepoFolder objects)
    item_131 = MagicMock(spec=["path"])
    item_131.path = "data/131"
    item_132 = MagicMock(spec=["path"])
    item_132.path = "data/132"
    mock_api_instance.list_repo_tree.return_value = [item_131, item_132]

    sync_dataset_card("pem207/maine-bills")

    mock_api_instance.upload_file.assert_called_once()
    call_kwargs = mock_api_instance.upload_file.call_args.kwargs
    assert call_kwargs["path_in_repo"] == "README.md"
    assert call_kwargs["repo_id"] == "pem207/maine-bills"


def test_sync_dataset_card_readme_contains_session_configs(mocker):
    from maine_bills.publish import sync_dataset_card

    mock_api_instance = MagicMock()
    mocker.patch("maine_bills.publish.HfApi", return_value=mock_api_instance)

    item = MagicMock(spec=["path"])
    item.path = "data/131"
    mock_api_instance.list_repo_tree.return_value = [item]

    sync_dataset_card("pem207/maine-bills")

    readme_bytes = mock_api_instance.upload_file.call_args.kwargs["path_or_fileobj"]
    readme = readme_bytes.decode("utf-8")
    assert 'config_name: "131"' in readme
    assert 'config_name: "all"' in readme
    assert "data/131/*.parquet" in readme


def test_sync_dataset_card_skips_non_session_entries(mocker):
    from maine_bills.publish import sync_dataset_card

    mock_api_instance = MagicMock()
    mocker.patch("maine_bills.publish.HfApi", return_value=mock_api_instance)

    session_dir = MagicMock(spec=["path"])
    session_dir.path = "data/131"
    readme_file = MagicMock(spec=["path"])
    readme_file.path = "README.md"
    mock_api_instance.list_repo_tree.return_value = [session_dir, readme_file]

    sync_dataset_card("pem207/maine-bills")

    readme_bytes = mock_api_instance.upload_file.call_args.kwargs["path_or_fileobj"]
    readme = readme_bytes.decode("utf-8")
    # "README.md" should not appear as a config_name entry
    assert 'config_name: "README.md"' not in readme
    assert 'config_name: "131"' in readme
