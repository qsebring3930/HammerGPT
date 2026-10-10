"""Copy one explicitly named VPK entry to a new workspace file, checking CRC."""
import argparse
from pathlib import Path
import struct
import zlib


def read_entry(archive,entry):
    with archive.open('rb') as file:
        header=file.read(12)
        if len(header)!=12: raise ValueError('Truncated VPK header')
        magic,version,size=struct.unpack('<III',header)
        if magic!=0x55AA1234 or version not in (1,2): raise ValueError('Unsupported VPK')
        header_size=28 if version==2 else 12
        if header_size+size>archive.stat().st_size: raise ValueError('Truncated VPK tree')
        if version==2: file.read(16)
        tree=file.read(size)
    cursor=0; matches=[]
    def string():
        nonlocal cursor
        end=tree.find(b'\0',cursor)
        if end<0: raise ValueError('Unterminated VPK string')
        result=tree[cursor:end].decode('utf-8'); cursor=end+1
        return result
    while True:
        extension=string()
        if not extension: break
        while True:
            folder=string()
            if not folder: break
            while True:
                name=string()
                if not name: break
                if cursor+18>len(tree): raise ValueError('Truncated VPK entry')
                crc,preload,index,offset,length,terminator=struct.unpack_from('<IHHIIH',tree,cursor)
                cursor+=18
                if terminator!=0xffff or cursor+preload>len(tree): raise ValueError('Invalid VPK entry')
                prefix=tree[cursor:cursor+preload]; cursor+=preload
                path=(folder+'/' if folder!=' ' else '')+name+'.'+extension
                if path.lower()==entry.replace('\\','/').lower(): matches.append((crc,prefix,index,offset,length))
    if len(matches)!=1: raise ValueError('Expected one matching entry, found '+str(len(matches)))
    crc,prefix,index,offset,length=matches[0]
    if index==0x7fff:
        data_file=archive; offset+=header_size+size
    else:
        if not archive.stem.endswith('_dir'): raise ValueError('Split VPK requires a _dir archive')
        data_file=archive.with_name(archive.stem[:-4]+f'_{index:03d}.vpk')
    if offset+length>data_file.stat().st_size: raise ValueError('Truncated VPK payload')
    with data_file.open('rb') as file:
        file.seek(offset); data=prefix+file.read(length)
    if zlib.crc32(data)&0xffffffff!=crc: raise ValueError('VPK entry CRC mismatch')
    return data


def extract(archive,entry,output):
    if output.exists(): raise ValueError('Output already exists')
    data=read_entry(archive,entry)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb') as file: file.write(data)
    return len(data)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',type=Path,required=True); parser.add_argument('--entry',required=True); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); print('Copied',extract(args.archive,args.entry,args.output),'bytes to',args.output)
