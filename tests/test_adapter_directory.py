"""Adapter repositories, subfolders and revision pins must reach the downloader intact."""

from pathlib import Path

import pytest

from wsbench.produce.methods import OLens, adapter_directory


@pytest.mark.parametrize("repo_type", ["model", "dataset"])
def test_subfolder_does_not_imply_dataset(repo_type):
    seen = []

    def download(repo, **kwargs):
        seen.append((repo, kwargs))
        return "cache"

    path = adapter_directory("owner/repo:adapter", download, repo_type=repo_type, revision="abc")
    assert path == str(Path("cache") / "adapter")
    assert seen == [
        ("owner/repo", {"repo_type": repo_type, "revision": "abc", "allow_patterns": ["adapter/*"]})
    ]


def test_default_oracle_uses_public_model_repo():
    lens = OLens()
    assert lens.lora == "agu18dec/olens_and_ar:olens_s3d_rl600"
    assert lens.repo_type == "model"


@pytest.mark.parametrize("reference", ["owner/repo:../bad", "owner/repo:/bad", ":bad"])
def test_unsafe_subfolder_rejected_without_download(reference):
    def never(*args, **kwargs):
        pytest.fail("invalid reference reached downloader")

    with pytest.raises(ValueError):
        adapter_directory(reference, never)
