"""Check that final archives retain evidence and reject corrupt bytes."""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from archive_results import pack, restore, sha


class ArchiveTests(unittest.TestCase):
    def test_preserve_profiles_sources_and_interrupted_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / 'study'
            study.mkdir()
            files = {
                'complete.json': b'{"complete":true}\n',
                'service-sample.txt': b'CPU dispatch profile\n',
                'source.py': b'print("frozen source")\n',
                'rows.bin.partial': b'\x00\xff\x01',
                'unknown-extension.evidence': b'unknown outcome\n',
            }
            for name, content in files.items():
                (study / name).write_bytes(content)
            archive = root / 'archive'
            with contextlib.redirect_stdout(io.StringIO()):
                manifest = pack([('study', study)], archive)
                restore(archive, root / 'restored', sha(archive / 'manifest.json'))
            self.assertEqual(len(manifest['files']), len(files))
            for name, content in files.items():
                self.assertEqual((root / 'restored' / 'study' / name).read_bytes(), content)

    def test_incomplete_study_is_not_archived(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(AssertionError, 'Incomplete study'):
                pack([('study', root)], root / 'archive')

    def test_provenance_does_not_claim_study_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study, evidence = root / 'study', root / 'evidence'
            study.mkdir()
            evidence.mkdir()
            (study / 'complete.json').write_text('{}\n')
            (evidence / 'launch.log').write_text('Interrupted process; exit unknown\n')
            archive = root / 'archive'
            with contextlib.redirect_stdout(io.StringIO()):
                manifest = pack([('study', study)], archive, [('provenance', evidence)])
                restore(archive, root / 'restored', sha(archive / 'manifest.json'))
            self.assertEqual(manifest['provenance_labels'], ['provenance'])
            self.assertFalse((root / 'restored/provenance/complete.json').exists())
            self.assertEqual((root / 'restored/provenance/launch.log').read_bytes(),
                             (evidence / 'launch.log').read_bytes())

    def test_corrupt_chunk_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / 'study'
            study.mkdir()
            (study / 'complete.json').write_text('{}\n')
            archive = root / 'archive'
            with contextlib.redirect_stdout(io.StringIO()):
                manifest = pack([('study', study)], archive)
            chunk = archive / manifest['files'][0]['chunks'][0]['path']
            chunk.write_bytes(b'corrupt')
            with self.assertRaisesRegex(AssertionError, 'Corrupt archive'):
                restore(archive, root / 'restored', sha(archive / 'manifest.json'))


if __name__ == '__main__':
    unittest.main()
