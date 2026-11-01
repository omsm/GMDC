"""Unit tests for idle FTP image uploader."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from ftplib import error_perm

from gmdc_common.services.ftp_image_upload import (
    FtpUploadConfig,
    iter_image_files,
    upload_images,
)


class FtpImageUploadTests(unittest.TestCase):
    def test_iter_image_files_recursive(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "a.jpg").write_bytes(b"jpg")
            sub = root / "traffic_in"
            sub.mkdir()
            (sub / "b.PNG").write_bytes(b"png")
            (sub / "notes.txt").write_text("skip", encoding="utf-8")
            (root / ".hidden.jpg").write_bytes(b"x")
            found = [p.relative_to(root).as_posix() for p in iter_image_files(root)]
            self.assertEqual(found, ["a.jpg", "traffic_in/b.PNG"])

    def test_upload_images_stores_and_deletes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            lane = root / "mines_entry"
            lane.mkdir()
            photo = lane / "truck_FRONT.jpg"
            photo.write_bytes(b"photo-bytes")

            ftp = MagicMock()
            created: set[str] = set()

            def smart_cwd(name):
                if name == "/":
                    return
                if name in created:
                    return
                raise error_perm("550")

            def smart_mkd(name):
                created.add(name)

            ftp.cwd.side_effect = smart_cwd
            ftp.mkd.side_effect = smart_mkd

            cfg = FtpUploadConfig(
                host="10.80.118.100",
                username="ftpclient",
                password="secret",
                remote_dir="/Mines-Checkpoint",
                delete_after_upload=True,
            )
            with patch(
                "gmdc_common.services.ftp_image_upload.FTP",
                return_value=ftp,
            ):
                ok, failed = upload_images(root, cfg)

            self.assertEqual(ok, 1)
            self.assertEqual(failed, 0)
            ftp.connect.assert_called_once()
            ftp.login.assert_called_once_with("ftpclient", "secret")
            self.assertTrue(
                any(
                    call.args and str(call.args[0]).startswith("STOR ")
                    for call in ftp.storbinary.call_args_list
                )
            )
            self.assertFalse(photo.exists())

    def test_disabled_skips(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "x.jpg").write_bytes(b"x")
            cfg = FtpUploadConfig(
                host="10.80.118.100",
                username="ftpclient",
                password="x",
                enabled=False,
            )
            with patch("gmdc_common.services.ftp_image_upload.FTP") as ftp_cls:
                ok, failed = upload_images(root, cfg)
            self.assertEqual((ok, failed), (0, 0))
            ftp_cls.assert_not_called()
            self.assertTrue((root / "x.jpg").exists())


if __name__ == "__main__":
    unittest.main()
