"""Checksummed, chunked archives of complete studies and exact checkpoint bytes."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path

CHUNK_BYTES = 48 * 1024 * 1024


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda:source.read(4<<20),b''):h.update(block)
    return h.hexdigest()


def pack(studies, output, provenance=()):
    output=Path(output)
    assert not output.exists(), 'Archive output must be new'
    sources=[]
    names=set()
    for label,directory,require_complete in [
            *[(label,directory,True) for label,directory in studies],
            *[(label,directory,False) for label,directory in provenance]]:
        assert label not in names and '/' not in label and label not in ('','.','..')
        names.add(label)
        directory=Path(directory).resolve()
        assert directory.is_dir(), f'Missing directory: {directory}'
        if require_complete:
            assert (directory/'complete.json').is_file(), f'Incomplete study: {directory}'
        for path in sorted(directory.rglob('*')):
            # Preserve profiles, frozen sources and interrupted partial files too.
            # A suffix filter can silently drop paid work from the final archive.
            if path.is_file():
                assert not path.is_symlink()
                sources.append((f'{label}/{path.relative_to(directory).as_posix()}',path))
    assert sources
    output.mkdir(parents=True)
    manifest=dict(schema='training-strategy-artifact-archive-v1',chunk_bytes=CHUNK_BYTES,files=[],
        provenance_labels=[label for label,_ in provenance])
    for name,path in sources:
        expected=sha(path)
        chunks=[]
        total=0
        with path.open('rb') as source:
            for index,block in enumerate(iter(lambda:source.read(CHUNK_BYTES),b'')):
                destination=output/'chunks'/name/f'{index:04d}.gz'
                destination.parent.mkdir(parents=True,exist_ok=True)
                with destination.open('wb') as raw:
                    with gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0,compresslevel=6) as gz:
                        gz.write(block)
                chunks.append(dict(path=destination.relative_to(output).as_posix(),
                    compressed_sha256=sha(destination),uncompressed_sha256=hashlib.sha256(block).hexdigest(),bytes=len(block)))
                total+=len(block)
        assert total==path.stat().st_size and sha(path)==expected, f'Source changed during archive: {path}'
        entry=dict(path=name,sha256=expected,bytes=total,chunks=chunks)
        manifest['files'].append(entry)
        print(json.dumps(dict(archived=name,bytes=total,sha256=expected)),flush=True)
    target=output/'manifest.json'
    target.write_text(json.dumps(manifest,indent=2)+'\n')
    (output/'SHA256SUMS').write_text(f'{sha(target)}  manifest.json\n')
    return manifest


def safe_path(root, relative):
    relative=Path(relative)
    assert not relative.is_absolute() and '..' not in relative.parts
    target=Path(root)/relative
    assert target.resolve().is_relative_to(Path(root).resolve())
    return target


def restore(archive, output, expected_manifest):
    archive,output=Path(archive),Path(output)
    assert sha(archive/'manifest.json')==expected_manifest, 'Archive manifest identity differs'
    assert not output.exists(), 'Restore output must be new'
    manifest=json.loads((archive/'manifest.json').read_text())
    assert manifest['schema']=='training-strategy-artifact-archive-v1'
    assert len({f['path'] for f in manifest['files']})==len(manifest['files'])
    output.mkdir(parents=True)
    for entry in manifest['files']:
        target=safe_path(output,entry['path'])
        target.parent.mkdir(parents=True,exist_ok=True)
        partial=target.with_name(target.name+'.partial')
        h=hashlib.sha256();total=0
        with partial.open('xb') as destination:
            for chunk in entry['chunks']:
                source=safe_path(archive,chunk['path'])
                assert sha(source)==chunk['compressed_sha256'], f'Corrupt archive: {source}'
                # Stream decompression; enforce the manifest's byte bound.
                local=hashlib.sha256();count=0
                with gzip.open(source,'rb') as compressed:
                    for block in iter(lambda:compressed.read(4<<20),b''):
                        count+=len(block)
                        assert count<=chunk['bytes']
                        local.update(block);h.update(block);destination.write(block)
                assert count==chunk['bytes'] and local.hexdigest()==chunk['uncompressed_sha256']
                total+=count
            destination.flush();os.fsync(destination.fileno())
        assert total==entry['bytes'] and h.hexdigest()==entry['sha256']
        partial.rename(target)
    # Keep original absolute-path receipts intact in provenance. Re-create only
    # these location-dependent receipts through data.prepare on the new host.
    moved=[]
    for entry in manifest['files']:
        path=output/entry['path']
        if path.name=='data.json':
            receipt=json.loads(path.read_text())
            if receipt.get('schema')=='canonical-rich-root-v1':
                original=path.with_name('data.original.json')
                assert not original.exists()
                path.rename(original);moved.append(str(original.relative_to(output)))
    (output/'restore.json').write_text(json.dumps(dict(manifest_sha256=expected_manifest,
        verified_files=len(manifest['files']),relocated_receipts=moved,
        note='Model and row bytes are unchanged. Original absolute-path data receipts are preserved; run data.py to make local receipts.'),indent=2)+'\n')
    return manifest


def main():
    ap=argparse.ArgumentParser()
    commands=ap.add_subparsers(dest='command',required=True)
    pack_args=commands.add_parser('pack')
    pack_args.add_argument('--study',action='append',required=True,help='label:completed-directory')
    pack_args.add_argument('--provenance',action='append',default=[],
        help='label:evidence-directory; retains logs/sources without asserting study completion')
    pack_args.add_argument('--output',type=Path,required=True)
    restore_args=commands.add_parser('restore')
    restore_args.add_argument('--archive',type=Path,required=True)
    restore_args.add_argument('--output',type=Path,required=True)
    restore_args.add_argument('--manifest-sha256',required=True)
    args=ap.parse_args()
    if args.command=='pack':
        result=pack([p.split(':',1) for p in args.study],args.output,
            [p.split(':',1) for p in args.provenance])
    else:
        result=restore(args.archive,args.output,args.manifest_sha256)
    print(json.dumps(dict(files=len(result['files']),output=str(args.output))))


if __name__=='__main__':main()
