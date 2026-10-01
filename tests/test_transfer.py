"""The transport pins host keys, reuses one SFTP session and enforces bounded reads."""

import io
import json
import sys
from pathlib import PurePosixPath
from types import SimpleNamespace

import pytest

from wsbench.produce.transfer import SFTPSource


def test_one_connection_pinned_host_and_deadline(monkeypatch):
    events = []
    clock = [0]

    class SFTP:
        def get_channel(self):
            return self

        def settimeout(self, timeout):
            assert 0 < timeout <= 5

        def open(self, path, mode):
            events.append(("open", path, mode))
            return io.BytesIO(b"payload")

        def close(self):
            events.append("sftp_close")

    class Client:
        def load_host_keys(self, path):
            events.append(("known_hosts", path))

        def set_missing_host_key_policy(self, policy):
            assert policy == "reject"

        def connect(self, **kwargs):
            assert kwargs["allow_agent"] is False and kwargs["look_for_keys"] is False
            for key in ["timeout", "auth_timeout", "banner_timeout", "channel_timeout"]:
                assert 0 < kwargs[key] <= 5
            events.append("connect")

        def open_sftp(self):
            return SFTP()

        def close(self):
            events.append("client_close")

    monkeypatch.setitem(
        sys.modules, "paramiko", SimpleNamespace(SSHClient=Client, RejectPolicy=lambda: "reject")
    )
    with SFTPSource(
        host="example",
        port=22,
        username="root",
        key_file="key",
        known_hosts="hosts",
        remote_root="/workspace/export",
        deadline_epoch=100,
        monotonic=lambda: clock[0],
        wall=lambda: 0,
    ) as source:
        for _ in range(2):
            with source.open_object("a" * 64) as stream:
                assert stream.read() == b"payload"
        clock[0] = 100
        with pytest.raises(TimeoutError, match="deadline"):
            source.open_object("b" * 64)
    assert events.count("connect") == 1
    assert events[-2:] == ["sftp_close", "client_close"]


def test_host_key_failure_closes_client_without_transfer(monkeypatch):
    events = []

    class Client:
        def load_host_keys(self, path):
            raise OSError("missing pinned hosts file")

        def close(self):
            events.append("closed")

    monkeypatch.setitem(sys.modules, "paramiko", SimpleNamespace(SSHClient=Client))
    with (
        pytest.raises(OSError),
        SFTPSource(
            host="example",
            port=22,
            username="root",
            key_file="key",
            known_hosts="hosts",
            remote_root="/workspace/export",
            deadline_epoch=100,
            wall=lambda: 0,
        ),
    ):
        pytest.fail("host verification was bypassed")
    assert events == ["closed"]


@pytest.mark.parametrize(
    "root,deadline",
    [("relative", 1), ("/a/../b", 1), ("/a", -1), ("/a", float("nan")), ("/a", 1000000)],
)
def test_invalid_transfer_configuration_fails_without_connection(root, deadline):
    with pytest.raises(ValueError):
        SFTPSource(
            host="example",
            port=22,
            username="root",
            key_file="key",
            known_hosts="hosts",
            remote_root=root,
            deadline_epoch=deadline,
            wall=lambda: 0,
        )


@pytest.mark.parametrize(
    "pointer",
    [
        {"sha256": "a" * 64, "run_id": "other"},
        {"sha256": "../escape", "run_id": "ours"},
        {"sha256": "a" * 64, "run_id": "ours", "extra": True},
        [],
    ],
)
def test_latest_pointer_requires_owner_and_bounded_object(pointer):
    source = object.__new__(SFTPSource)
    source.root = PurePosixPath("/exports")
    source.check = lambda: None
    source.sftp = SimpleNamespace(open=lambda *a: io.BytesIO(json.dumps(pointer).encode()))
    with pytest.raises(ValueError):
        source.latest("ours")


def test_latest_pointer_then_exact_snapshot():
    source = object.__new__(SFTPSource)
    source.root = PurePosixPath("/exports")
    source.check = lambda: None
    data = {
        "/exports/latest.json": {"run_id": "ours", "sha256": "a" * 64},
        f"/exports/snapshots/{'a' * 64}.json": {"sha256": "a" * 64},
    }
    source.sftp = SimpleNamespace(
        open=lambda path, mode: io.BytesIO(json.dumps(data[path]).encode())
    )
    assert source.snapshot(source.latest("ours")) == {"sha256": "a" * 64}
    source.sftp.open = lambda *a: io.BytesIO(b" " * 4096)
    with pytest.raises(ValueError, match="bound"):
        source.latest("ours")
