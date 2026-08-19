from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from drilling_knowledge.loader import LASAdapter


class LASAdapterTests(unittest.TestCase):
    def test_scans_las_and_extracts_mnemonics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            las = Path(temp_dir) / "sample.las"
            las.write_text(
                "~Version\nVERS. 2.0\n~Well\nWELL. : Demo\nSRVC. : Pason\n~Curve\nDEPT.M : Depth\nSPP.PSI : Standpipe Pressure\nHKLD.KLBF : Hook Load\n~A\n",
                encoding="utf-8",
            )
            adapter = LASAdapter()

            records = adapter.scan(temp_dir)

            self.assertEqual(len(records), 1)
            record, observations = records[0]
            self.assertEqual(record.well_name, "Demo")
            self.assertEqual({item.mnemonic for item in observations}, {"DEPT", "SPP", "HKLD"})