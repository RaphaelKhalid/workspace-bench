"""One pinned-host SFTP connection for bounded, read-only export pulls; no pod lifecycle calls."""

import argparse
import json
import time
from pathlib import Path, PurePosixPath

from .export import SHA, receive_snapshot


class SFTPSource:
    def __init__(
        self,
        *,
        host,
        port,
        username,
        key_file,
        known_hosts,
        remote_root,
        deadline_epoch,
        monotonic=time.monotonic,
        wall=time.time,
    ):
        root = PurePosixPath(remote_root)
        if not root.is_absolute() or ".." in root.parts:
            raise ValueError("remote export root must be an absolute normalized path")
        if str(root) != remote_root or "\x00" in remote_root:
            raise ValueError("invalid remote export root")
        remaining = deadline_epoch - wall()
        if not 0 < remaining <= 24 * 3600:
            raise ValueError("transfer deadline must be within the next 24 hours")
        self.end = monotonic() + remaining
        self.monotonic, self.root = monotonic, root
        self.options = {
            "hostname": host,
            "port": port,
            "username": username,
            "key_filename": str(key_file),
            "allow_agent": False,
            "look_for_keys": False,
        }
        self.known_hosts = str(known_hosts)
        self.client = self.sftp = None

    def check(self):
        remaining = self.end - self.monotonic()
        if remaining <= 0:
            raise TimeoutError("export transfer deadline reached")
        if self.sftp is not None:
            self.sftp.get_channel().settimeout(min(5, remaining))

    def __enter__(self):
        import paramiko

        self.check()
        self.client = paramiko.SSHClient()
        try:
            self.client.load_host_keys(self.known_hosts)
            self.client.set_missing_host_key_policy(paramiko.RejectPolicy())
            timeout = min(5, (self.end - self.monotonic()) / 4)
            self.client.connect(
                **self.options,
                timeout=timeout,
                auth_timeout=timeout,
                banner_timeout=timeout,
                channel_timeout=timeout,
            )
            self.check()
            self.sftp = self.client.open_sftp()
            self.check()
            return self
        except BaseException:
            self.client.close()
            raise

    def __exit__(self, *_exc):
        try:
            if self.sftp is not None:
                self.sftp.close()
        finally:
            if self.client is not None:
                self.client.close()

    def open_object(self, sha):
        if not SHA.fullmatch(sha):
            raise ValueError("invalid object hash")
        self.check()
        return self.sftp.open(str(self.root / "objects" / sha), "rb")

    def snapshot(self, sha):
        if not SHA.fullmatch(sha):
            raise ValueError("invalid snapshot hash")
        self.check()
        with self.sftp.open(str(self.root / "snapshots" / f"{sha}.json"), "rb") as stream:
            pieces, remaining = [], 4 * 1024 * 1024
            while remaining:
                self.check()
                chunk = stream.read(min(65536, remaining))
                if not chunk:
                    break
                pieces.append(chunk)
                remaining -= len(chunk)
            if not remaining:
                raise ValueError("snapshot metadata exceeds transfer bound")
        data = json.loads(b"".join(pieces))
        if data.get("sha256") != sha:
            raise ValueError("requested snapshot hash differs")
        return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "host",
        "username",
        "key-file",
        "known-hosts",
        "remote-root",
        "snapshot",
        "run-id",
    ):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--deadline-epoch", type=float, required=True)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    context = json.loads(args.context.read_text(encoding="utf-8"))
    with SFTPSource(
        host=args.host,
        port=args.port,
        username=args.username,
        key_file=args.key_file,
        known_hosts=args.known_hosts,
        remote_root=args.remote_root,
        deadline_epoch=args.deadline_epoch,
    ) as source:
        snapshot = source.snapshot(args.snapshot)
        result = receive_snapshot(
            snapshot,
            args.destination,
            source.open_object,
            run_id=args.run_id,
            context=context,
            check=source.check,
        )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
