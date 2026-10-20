"""Binary pack written into an RGB PNG so a sandboxed page can read it from an <img>.

Layout of the bytes carried by the pixels (row-major, R,G,B per pixel):
  'STKW' | u32 payload length | u32 json length | json (utf-8) | pad to 4 | blob
JSON offsets are relative to the blob start. RGB only (no alpha), so a canvas
read never sees premultiplied values.
"""
import json
import struct
import zlib

WIDTH = 1024


class Blob:
    def __init__(self):
        self.parts = []
        self.size = 0

    def add(self, data):
        off = self.size
        self.parts.append(data)
        self.size += len(data)
        pad = (-self.size) % 4
        if pad:
            self.parts.append(b'\0' * pad)
            self.size += pad
        return off

    def bytes(self):
        return b''.join(self.parts)


def write_png(path, payload):
    row_bytes = WIDTH * 3
    height = max(1, -(-len(payload) // row_bytes))
    payload = payload + b'\0' * (row_bytes * height - len(payload))
    raw = b''.join(b'\0' + payload[y * row_bytes:(y + 1) * row_bytes] for y in range(height))

    def chunk(tag, data):
        c = struct.pack('>I', len(data)) + tag + data
        return c + struct.pack('>I', zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', struct.pack('>IIBBBBB', WIDTH, height, 8, 2, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(raw, 9))
    png += chunk(b'IEND', b'')
    with open(path, 'wb') as f:
        f.write(png)
    return len(png)


def write_pack(path, meta, blob):
    js = json.dumps(meta, separators=(',', ':')).encode('utf-8')
    head = js + b'\0' * ((-len(js)) % 4)
    body = struct.pack('<I', len(js)) + head + blob.bytes()
    payload = b'STKW' + struct.pack('<I', len(body)) + body
    return write_png(path, payload)
