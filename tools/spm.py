"""Minimal reader for SuperTuxKart .spm meshes (format version 1).

Mirrors stk-code src/graphics/sp_mesh_loader.cpp: header, texture table, then
mesh buffers. Only what the web port needs: positions, normals, colors, uv1,
indices, and the texture pair per buffer. Skinned meshes (SPMA) are read in
their bind pose; the animation block after the buffers is ignored.
"""
import struct


def half_to_float(h):
    return struct.unpack('<e', struct.pack('<H', h & 0xFFFF))[0]


class Reader:
    def __init__(self, data):
        self.d = data
        self.o = 0

    def read(self, n):
        b = self.d[self.o:self.o + n]
        if len(b) != n:
            raise EOFError('spm truncated')
        self.o += n
        return b

    def u8(self):
        return self.read(1)[0]

    def u16(self):
        return struct.unpack('<H', self.read(2))[0]

    def u32(self):
        return struct.unpack('<I', self.read(4))[0]


def read_header(data):
    r = Reader(data)
    if r.read(2) != b'SP':
        raise ValueError('not an spm')
    b = r.u8()
    version = b >> 3
    if version != 1:
        raise ValueError('spm version %d' % version)
    kind = b & ~0x08
    kind = {0: 'SPMS', 1: 'SPMA'}.get(kind, 'SPMN')
    flags = r.u8()
    info = {
        'kind': kind,
        'normal': bool(flags & 1),
        'vcolor': bool(flags >> 1 & 1),
        'tangent': bool(flags >> 2 & 1),
        'bbox': struct.unpack('<6f', r.read(24)),
    }
    textures = []
    n = r.u16()
    for _ in range(n):
        names = []
        for _ in range(2):
            s = r.u8()
            names.append(r.read(s).decode('utf-8', 'replace') if s else '')
        textures.append(tuple(names))
    info['textures'] = textures
    return info, r


def read_mesh(data):
    info, r = read_header(data)
    buffers = []
    n = r.u16()
    for _ in range(n):
        mat_count = r.u16()
        for _ in range(mat_count):
            vc = r.u32()
            ic = r.u32()
            mat = r.u16()
            uv1 = bool(info['textures'][mat][0])
            uv2 = bool(info['textures'][mat][1])
            pos, nor, col, uv, uv_two = [], [], [], [], []
            for _ in range(vc):
                pos.append(struct.unpack('<3f', r.read(12)))
                if info['normal']:
                    nor.append(r.u32())
                if info['vcolor']:
                    ci = r.u8()
                    col.append((255, 255, 255) if ci == 128 else tuple(r.read(3)))
                if uv1:
                    a, b = struct.unpack('<2H', r.read(4))
                    uv.append((half_to_float(a), half_to_float(b)))
                    if uv2:
                        a, b = struct.unpack('<2H', r.read(4))
                        uv_two.append((half_to_float(a), half_to_float(b)))
                    if info['tangent']:
                        r.read(4)
                if info['kind'] == 'SPMA':
                    r.read(16)
            if vc > 255:
                idx = list(struct.unpack('<%dH' % ic, r.read(ic * 2)))
            else:
                idx = list(r.read(ic))
            buffers.append({'mat': mat, 'pos': pos, 'nor': nor, 'col': col, 'uv': uv, 'uv2': uv_two,
                            'idx': idx})
    info['buffers'] = buffers
    return info
