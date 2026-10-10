import struct
import tempfile
import unittest
from pathlib import Path
import zlib

from extract_vpk_entry import read_entry,extract


class VpkExtractionTests(unittest.TestCase):
    def archive(self,root,version=2,split=False,corrupt=False):
        data=b'NAV test payload'; preload=data[:3]; rest=data[3:]
        crc=zlib.crc32(data)+(1 if corrupt else 0)
        tree=b'nav\0maps\0example\0'+struct.pack('<IHHIIH',crc,len(preload),0 if split else 0x7fff,0,len(rest),0xffff)+preload+b'\0\0\0'
        header=struct.pack('<III',0x55AA1234,version,len(tree))+(b'\0'*16 if version==2 else b'')
        path=root/'map_dir.vpk'; path.write_bytes(header+tree+(b'' if split else rest))
        if split: (root/'map_000.vpk').write_bytes(rest)
        return path,data

    def test_embedded_versions_and_preload(self):
        with tempfile.TemporaryDirectory() as directory:
            for version in (1,2):
                path,data=self.archive(Path(directory),version)
                self.assertEqual(read_entry(path,'maps/example.nav'),data)

    def test_split_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            path,data=self.archive(Path(directory),split=True)
            self.assertEqual(read_entry(path,'maps/example.nav'),data)

    def test_crc_and_missing_entry_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path,_=self.archive(Path(directory),corrupt=True)
            with self.assertRaisesRegex(ValueError,'CRC'): read_entry(path,'maps/example.nav')
            with self.assertRaisesRegex(ValueError,'matching entry'): read_entry(path,'maps/missing.nav')

    def test_output_never_overwrites_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); path,data=self.archive(root); output=root/'explicit.nav'
            extract(path,'maps/example.nav',output)
            with self.assertRaisesRegex(ValueError,'already exists'): extract(path,'maps/example.nav',output)
            self.assertEqual(output.read_bytes(),data)


if __name__=='__main__': unittest.main()
