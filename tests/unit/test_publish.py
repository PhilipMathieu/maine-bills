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


def _sync_card_and_get_readme(mocker):
    """Run sync_dataset_card against a mocked HfApi and return the README text."""
    from maine_bills.publish import sync_dataset_card

    mock_api_instance = MagicMock()
    mocker.patch("maine_bills.publish.HfApi", return_value=mock_api_instance)

    item = MagicMock(spec=["path"])
    item.path = "data/132"
    mock_api_instance.list_repo_tree.return_value = [item]

    sync_dataset_card("pem207/maine-bills")

    readme_bytes = mock_api_instance.upload_file.call_args.kwargs["path_or_fileobj"]
    return readme_bytes.decode("utf-8")


def test_sync_dataset_card_documents_v2_enrichment_columns(mocker):
    """Dataset card schema table includes all four v2 enrichment columns."""
    readme = _sync_card_and_get_readme(mocker)

    assert "`sponsor_ids`" in readme
    assert "`sponsor_parties`" in readme
    assert "`sponsor_districts`" in readme
    assert "`sponsor_match_confidence`" in readme
    # Original sponsors column stays documented as provenance
    assert "`sponsors`" in readme
    assert "provenance" in readme


def test_sync_dataset_card_includes_methodology_section(mocker):
    """Dataset card documents the two-pass matching methodology."""
    readme = _sync_card_and_get_readme(mocker)

    assert "## Sponsor enrichment methodology" in readme
    assert "OpenStates" in readme
    assert "rapidfuzz" in readme
    assert "threshold" in readme
    # Unmatched sponsors are left null
    assert "null" in readme


def test_sync_dataset_card_includes_version_note(mocker):
    """Dataset card carries a v2 version note."""
    readme = _sync_card_and_get_readme(mocker)
    assert "v2" in readme


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


# --- the actions config ---
#
# The hazard these are about is not upload mechanics. It is the default config
# quietly acquiring a second schema: `all` globs data/**/*.parquet, so an
# actions parquet placed anywhere beneath data/ would load as bill rows for
# every consumer who never names a config.


def actions_dir(tmp_path, sessions=(131, 132)):
    for s in sessions:
        d = tmp_path / str(s)
        d.mkdir(parents=True)
        pd.DataFrame([{"session": s, "ld_number": "0001", "action_count": 0}]).to_parquet(
            d / "train-00000-of-00001.parquet"
        )
    (tmp_path / "build-summary.json").write_text("{}")
    return tmp_path


def test_actions_are_published_outside_the_bills_glob(tmp_path, mocker):
    """data/**/*.parquet must never match an actions file."""
    from maine_bills.publish import publish_actions_config

    api = MagicMock()
    mocker.patch("maine_bills.publish.HfApi", return_value=api)

    publish_actions_config(actions_dir(tmp_path), "pem207/maine-bills")

    paths = [c.kwargs["path_in_repo"] for c in api.upload_file.call_args_list]
    assert paths == [
        "actions/131/train-00000-of-00001.parquet",
        "actions/132/train-00000-of-00001.parquet",
    ]
    assert not any(p.startswith("data/") for p in paths)


def test_the_default_config_glob_cannot_reach_the_actions_path():
    """Asserted on the template itself, so a later edit that moves actions under
    data/ fails here rather than in someone's load_dataset call."""
    import fnmatch

    from maine_bills.publish import ACTIONS_ROOT, DATASET_CARD_TEMPLATE

    assert 'path: "data/**/*.parquet"' in DATASET_CARD_TEMPLATE
    assert not fnmatch.fnmatch(
        f"{ACTIONS_ROOT}/132/train-00000-of-00001.parquet", "data/**/*.parquet"
    )


def test_the_build_summary_is_not_uploaded(tmp_path, mocker):
    """It describes the build, not the data, and would land in the repo root."""
    from maine_bills.publish import publish_actions_config

    api = MagicMock()
    mocker.patch("maine_bills.publish.HfApi", return_value=api)
    publish_actions_config(actions_dir(tmp_path), "pem207/maine-bills")

    assert not any("summary" in c.kwargs["path_in_repo"] for c in api.upload_file.call_args_list)


def test_an_empty_directory_is_refused_not_reported_as_success(tmp_path, mocker):
    """ "Nothing to upload" and "uploaded nothing" look identical in a log."""
    import pytest

    from maine_bills.publish import publish_actions_config

    mocker.patch("maine_bills.publish.HfApi")
    (tmp_path / "empty").mkdir()
    with pytest.raises(ValueError, match="No session directories"):
        publish_actions_config(tmp_path / "empty", "pem207/maine-bills")


def test_a_session_directory_with_no_parquet_is_refused(tmp_path, mocker):
    """A half-finished build leaves the directory but not the file."""
    import pytest

    from maine_bills.publish import publish_actions_config

    mocker.patch("maine_bills.publish.HfApi")
    (tmp_path / "132").mkdir(parents=True)
    with pytest.raises(FileNotFoundError, match="did not finish"):
        publish_actions_config(tmp_path, "pem207/maine-bills")


# --- the card ---


def tree(paths):
    return [MagicMock(path=p) for p in paths]


def test_the_card_gains_a_config_per_actions_session(mocker):
    from maine_bills.publish import sync_dataset_card

    api = MagicMock()
    api.list_repo_tree.side_effect = lambda repo_id, repo_type, path_in_repo: (
        tree(["data/131", "data/132"]) if path_in_repo == "data" else tree(["actions/131"])
    )
    mocker.patch("maine_bills.publish.HfApi", return_value=api)

    sync_dataset_card("pem207/maine-bills")

    readme = api.upload_file.call_args.kwargs["path_or_fileobj"].decode()
    assert 'config_name: "actions-131"' in readme
    assert 'path: "actions/131/*.parquet"' in readme
    assert 'config_name: "132"' in readme
    assert 'config_name: "actions-132"' not in readme, "only published sessions get a config"


def test_the_card_is_still_correct_before_actions_is_ever_published(mocker):
    """A repo with no actions/ directory must still get a valid card, not a
    traceback and not a template with an unfilled placeholder."""
    from maine_bills.publish import sync_dataset_card

    api = MagicMock()

    def tree_or_raise(repo_id, repo_type, path_in_repo):
        if path_in_repo == "actions":
            raise FileNotFoundError("actions not found")
        return tree(["data/132"])

    api.list_repo_tree.side_effect = tree_or_raise
    mocker.patch("maine_bills.publish.HfApi", return_value=api)

    sync_dataset_card("pem207/maine-bills")

    readme = api.upload_file.call_args.kwargs["path_or_fileobj"].decode()
    front_matter = readme.split("---")[1]
    assert 'config_name: "132"' in front_matter
    # Scoped to the front matter: the prose below documents `actions-<session>`
    # as a naming convention whether or not any are published yet.
    assert "actions-" not in front_matter
    assert "{" not in front_matter, "no unfilled template placeholder"
    # The repo-wide `actions` config stays declared; it globs an empty
    # directory harmlessly and means publishing later needs no card change.
    assert 'config_name: "actions"' in front_matter


def test_a_real_hub_failure_is_not_read_as_a_missing_directory(mocker):
    """Catching Exception here swallowed auth failures, 5xx and network errors
    as "directory missing", so a transient outage would publish a card with the
    actions configs quietly absent — and the job would still go green. A wrong
    card is worse than a failed job, because nothing downstream re-checks it."""
    import pytest

    from maine_bills.publish import sync_dataset_card

    api = MagicMock()

    def tree_or_fail(repo_id, repo_type, path_in_repo):
        if path_in_repo == "actions":
            raise ConnectionError("503 from the hub")
        return tree(["data/132"])

    api.list_repo_tree.side_effect = tree_or_fail
    mocker.patch("maine_bills.publish.HfApi", return_value=api)

    with pytest.raises(ConnectionError):
        sync_dataset_card("pem207/maine-bills")
    api.upload_file.assert_not_called()
