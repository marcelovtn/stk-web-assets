"""Build the web asset set for the Hubs SuperTuxKart port.

usage: python3 -I build.py <stk assets dir> <stk-code ref dir> <out dir>

Everything is converted to "game space": STK/Irrlicht coordinates with z negated
(right-handed, y up). Karts face -z. Meshes are baked per material into packs
(see pack.py); textures and sounds are copied as they are.
"""
import math
import os
import re
import shutil
import struct
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pack  # noqa: E402
import spm  # noqa: E402

SRC, REF, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
TRACKS = ['snowtuxpeak', 'sandtrack', 'hacienda']
KARTS = ['tux', 'gnu', 'nolok', 'suzanne', 'kiki', 'adiumy', 'xue', 'pidgin', 'puffy', 'wilber',
         'emule', 'gavroche', 'amanda', 'hexley']
ITEMS = {
    'gift': 'gift-box.spm', 'banana': 'banana.spm', 'nitro_small': 'nitrotank-small.spm',
    'nitro_big': 'nitrotank-big.spm', 'bowling': 'bowling.spm', 'cake': 'cake.spm',
    'bubblegum': 'bubblegum.spm', 'plunger': 'plunger.spm', 'swatter': 'swatter.spm',
    'parachute': 'parachute.spm', 'rubber_ball': 'rubber_ball.spm', 'shield': 'bubblegum_shield.spm',
}
MUSIC = {'snowmountain.music', 'egypt.music', 'hacienda.music', 'race_summary.music', 'main_theme.music'}
SFX = ['start_race', 'pre_start_race', 'engine_small', 'engine_large', 'skid', 'nitro', 'crash',
       'crash2', 'grab_collectable', 'shoot', 'bowling_shoot', 'bowling_roll', 'explosion', 'goo',
       'plunger', 'swatter', 'wee', 'race_finish', 'race_finish_victory', 'last_lap_fanfare', 'boing',
       'jump', 'ugh', 'horn', 'ball_bounce', 'bzzt', 'strike', 'energy_bar_full', 'swap', 'parachute']
ICONS = ['bowling-icon', 'bubblegum-icon', 'cake-icon', 'plunger-icon', 'swatter-icon',
         'zipper_collect', 'rubber_ball-icon', 'parachute-icon', 'anchor-icon', 'swap-icon',
         'nitro', 'gift', 'lap_flag', 'gauge_empty', 'gauge_full', 'gauge_full_bright', 'banana',
         'logo', 'robot', 'speed', 'speedback', 'speedfore', 'red_flag', 'crown']

GLOBAL_TEX_DIRS = [os.path.join(SRC, 'textures'), os.path.join(SRC, 'textures', 'skybox'),
                   os.path.join(SRC, 'textures', 'deprecated'), os.path.join(SRC, 'models')]


# ---------------------------------------------------------------- math (Irrlicht)

def mat_identity():
    return [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]


def mat_mul(a, b):
    # Irrlicht column-major multiply: result = a * b (b applied first)
    m = [0.0] * 16
    for r in range(4):
        for c in range(4):
            m[c * 4 + r] = sum(a[k * 4 + r] * b[c * 4 + k] for k in range(4))
    return m


def mat_trs(xyz, hpr, scale):
    x, y, z = [math.radians(v) for v in hpr]
    cr, sr, cp, sp, cy, sy = math.cos(x), math.sin(x), math.cos(y), math.sin(y), math.cos(z), math.sin(z)
    m = [0.0] * 16
    m[0] = cp * cy
    m[1] = cp * sy
    m[2] = -sp
    srsp, crsp = sr * sp, cr * sp
    m[4] = srsp * cy - cr * sy
    m[5] = srsp * sy + cr * cy
    m[6] = sr * cp
    m[8] = crsp * cy + sr * sy
    m[9] = crsp * sy - sr * cy
    m[10] = cr * cp
    m[15] = 1
    sx, sy_, sz = scale
    for i in range(3):
        m[i] *= sx
        m[4 + i] *= sy_
        m[8 + i] *= sz
    m[12], m[13], m[14] = xyz
    return m


def xform(m, p):
    x, y, z = p
    return (x * m[0] + y * m[4] + z * m[8] + m[12],
            x * m[1] + y * m[5] + z * m[9] + m[13],
            x * m[2] + y * m[6] + z * m[10] + m[14])


def xform_dir(m, n):
    x, y, z = n
    v = (x * m[0] + y * m[4] + z * m[8], x * m[1] + y * m[5] + z * m[9], x * m[2] + y * m[6] + z * m[10])
    length = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2) or 1
    return (v[0] / length, v[1] / length, v[2] / length)


def det3(m):
    return (m[0] * (m[5] * m[10] - m[9] * m[6]) - m[4] * (m[1] * m[10] - m[9] * m[2])
            + m[8] * (m[1] * m[6] - m[5] * m[2]))


def vec(s, default=(0.0, 0.0, 0.0)):
    if not s:
        return default
    return tuple(float(v) for v in s.split())


def game(p):
    return (p[0], p[1], -p[2])


def unpack_normal(packed):
    out = []
    for shift in (0, 10, 20):
        part = (packed >> shift) & 1023
        out.append((1024 - part) * (-1.0 / 512.0) if part & 512 else part * (1.0 / 511.0))
    length = math.sqrt(sum(v * v for v in out)) or 1
    return tuple(v / length for v in out)


# ---------------------------------------------------------------- materials

def read_materials(path, into):
    if not os.path.exists(path):
        return
    for e in ET.parse(path).getroot().iter('material'):
        name = e.get('name')
        if not name:
            continue
        rec = {}
        shader = e.get('shader')
        if shader:
            rec['shader'] = shader
        for key, attr in (('maxSpeed', 'max-speed'), ('slowdown', 'slowdown-time')):
            if e.get(attr):
                rec[key] = float(e.get(attr))
        for key, attr in (('reset', 'reset'), ('ignore', 'ignore'), ('noCull', 'backface-culling'),
                          ('noZ', 'disable-z-write')):
            v = e.get(attr)
            if v is not None:
                yes = v.upper() in ('Y', 'YES', 'TRUE', '1')
                rec[key] = (not yes) if key == 'noCull' else yes
        if e.get('collision-reaction') == 'reset':
            rec['reset'] = True
        z = e.find('zipper')
        if z is not None:
            rec['zipper'] = {k: float(z.get(a)) for k, a in (
                ('duration', 'duration'), ('gain', 'speed-gain'), ('maxInc', 'max-speed-increase'),
                ('fade', 'fade-out-time')) if z.get(a)}
        if shader == 'splatting':
            rec['splat'] = [e.get('uv-two-tex')] + [e.get('tex-layer-%d' % i) for i in range(2, 6)]
        into[name] = rec


def global_materials():
    mats = {}
    read_materials(os.path.join(SRC, 'textures', 'materials.xml'), mats)
    read_materials(os.path.join(SRC, 'models', 'materials.xml'), mats)
    return mats


# ---------------------------------------------------------------- mesh baking

class Batcher:
    """Collects triangles per material key, already in game space."""

    def __init__(self):
        self.batches = {}

    def add_mesh(self, info, matrix, tex_of, collide=True, render=True, coll=None):
        flip = det3(matrix) < 0
        for b in info['buffers']:
            t1, t2 = info['textures'][b['mat']]
            key = (t1, t2)
            pos = [game(xform(matrix, p)) for p in b['pos']]
            if b['nor']:
                nor = [game(xform_dir(matrix, unpack_normal(n))) for n in b['nor']]
            else:
                nor = [(0.0, 1.0, 0.0)] * len(pos)
            idx = b['idx']
            tris = []
            for i in range(0, len(idx) - 2, 3):
                a, c, d = idx[i], idx[i + 1], idx[i + 2]
                # game space mirrors z, so winding flips; a mirrored matrix flips it back
                tris.append((a, c, d) if flip else (a, d, c))
            if render:
                batch = self.batches.setdefault(key, {'pos': [], 'nor': [], 'uv': [], 'uv2': [], 'col': [],
                                                      'idx': [], 'has_col': False, 'has_uv2': False})
                base = len(batch['pos'])
                batch['pos'] += pos
                batch['nor'] += nor
                uv = b['uv'] or [(0.0, 0.0)] * len(pos)
                batch['uv'] += uv
                batch['uv2'] += b.get('uv2') or uv
                if b.get('uv2'):
                    batch['has_uv2'] = True
                if b['col']:
                    batch['has_col'] = True
                    batch['col'] += b['col']
                else:
                    batch['col'] += [(255, 255, 255)] * len(pos)
                for t in tris:
                    batch['idx'].append((t[0] + base, t[1] + base, t[2] + base))
            if collide and coll is not None:
                coll.add(pos, tris, t1)


class Collision:
    def __init__(self):
        self.pos = []
        self.tris = []
        self.mats = []
        self.mat_ids = {}

    def add(self, pos, tris, tex):
        base = len(self.pos)
        self.pos += pos
        mid = self.mat_ids.setdefault(tex or '', len(self.mat_ids))
        for t in tris:
            self.tris.append((t[0] + base, t[1] + base, t[2] + base))
            self.mats.append(mid)


def half(v):
    return struct.unpack('<H', struct.pack('<e', max(-65000.0, min(65000.0, v))))[0]


def write_batches(batches, blob, materials, tex_dirs, tex_out, skip_shaders=('displace',)):
    out = []
    for (t1, t2), b in batches.items():
        mat = materials.get(t1, {})
        if mat.get('shader') in skip_shaders:
            continue
        if not b['idx']:
            continue
        n = len(b['pos'])
        rec = {'tex': copy_tex(t1, tex_dirs, tex_out) if t1 else None, 'n': n, 'm': len(b['idx']) * 3}
        rec['pos'] = blob.add(struct.pack('<%df' % (n * 3), *[c for p in b['pos'] for c in p]))
        rec['nor'] = blob.add(bytes(
            (int(round(max(-1, min(1, c)) * 127)) & 0xFF) for p in b['nor'] for c in (p[0], p[1], p[2], 0)))
        rec['uv'] = blob.add(struct.pack('<%dH' % (n * 2), *[half(c) for p in b['uv'] for c in p]))
        if b['has_uv2']:
            rec['uv2'] = blob.add(struct.pack('<%dH' % (n * 2), *[half(c) for p in b['uv2'] for c in p]))
        if b['has_col']:
            rec['col'] = blob.add(bytes(c for p in b['col'] for c in (p[0], p[1], p[2], 255)))
        rec['idx'] = blob.add(struct.pack('<%dI' % rec['m'], *[i for t in b['idx'] for i in t]))
        if mat:
            rec['mat'] = t1
        if mat.get('splat'):
            rec['splat'] = [copy_tex(t, tex_dirs, tex_out) if t else None for t in mat['splat']]
        out.append(rec)
    return out


_copied = {}


def copy_tex(name, dirs, out_dir):
    name = os.path.basename(name)
    for d in dirs:
        p = os.path.join(d, name)
        if os.path.exists(p):
            os.makedirs(out_dir, exist_ok=True)
            dst = os.path.join(out_dir, name)
            if not os.path.exists(dst):
                shutil.copyfile(p, dst)
            return name
    _copied.setdefault('missing', set()).add(name)
    return None


def read_spm(path):
    info = spm.read_mesh(open(path, 'rb').read())
    return info


# ---------------------------------------------------------------- tracks

def build_track(tid):
    tdir = os.path.join(SRC, 'tracks', tid)
    out_dir = os.path.join(OUT, 'tracks', tid)
    os.makedirs(out_dir, exist_ok=True)
    mats = global_materials()
    lib_dirs = []
    batcher = Batcher()
    coll = Collision()
    stats = {'objects': 0}

    def place(model_path, matrix, interaction):
        if not os.path.exists(model_path):
            return
        info = read_spm(model_path)
        render = interaction != 'physics-only'
        collide = interaction not in ('ghost', 'none')
        batcher.add_mesh(info, matrix, None, collide=collide, render=render, coll=coll)
        stats['objects'] += 1

    def walk(path, base_dir, parent, lods):
        root = ET.parse(path).getroot()
        local_lods = dict(lods)
        for g in root.iter('group'):
            best = None
            for so in g.findall('static-object'):
                d = float(so.get('lod_distance', '9999'))
                if best is None or d < best[0]:
                    best = (d, so.get('model'))
            if best:
                local_lods[g.get('name')] = os.path.join(base_dir, best[1])
        read_materials(os.path.join(base_dir, 'materials.xml'), mats)

        def visit(e, matrix):
            for c in e:
                tag = c.tag
                if tag in ('lod',):
                    continue
                m = mat_mul(matrix, mat_trs(vec(c.get('xyz')), vec(c.get('hpr')),
                                            vec(c.get('scale'), (1.0, 1.0, 1.0))))
                if tag == 'track':
                    place(os.path.join(base_dir, c.get('model')), matrix, 'static')
                    visit(c, matrix)
                elif tag in ('static-object', 'object'):
                    if c.get('type') in ('sfx-emitter', 'particle-emitter', 'billboard', 'cutscene_camera',
                                         'action-trigger'):
                        continue
                    if c.get('lod_instance') == 'true':
                        mp = local_lods.get(c.get('lod_group'))
                        if mp:
                            place(mp, m, c.get('interaction', 'static'))
                    elif c.get('model'):
                        place(os.path.join(base_dir, c.get('model')), m, c.get('interaction', 'static'))
                    visit(c, m)
                elif tag == 'library':
                    ld = os.path.join(SRC, 'library', c.get('name'))
                    if ld not in lib_dirs:
                        lib_dirs.append(ld)
                    node = os.path.join(ld, 'node.xml')
                    if os.path.exists(node):
                        walk(node, ld, m, local_lods)
        visit(root, parent)

    walk(os.path.join(tdir, 'scene.xml'), tdir, mat_identity(), {})
    # Track-local materials win over library and global ones.
    read_materials(os.path.join(tdir, 'materials.xml'), mats)

    tex_dirs = [tdir] + lib_dirs + GLOBAL_TEX_DIRS
    blob = pack.Blob()
    meta = {'id': tid}
    meta['batches'] = write_batches(batcher.batches, blob, mats, tex_dirs, out_dir)

    # collision: drop non-solid materials
    keep_tris, keep_mats = [], []
    names = {v: k for k, v in coll.mat_ids.items()}
    for t, mid in zip(coll.tris, coll.mats):
        m = mats.get(names[mid], {})
        if m.get('ignore') or m.get('shader') in ('alphablend', 'additive', 'displace', 'grass'):
            if not m.get('reset'):
                continue
        keep_tris.append(t)
        keep_mats.append(mid)
    used = sorted(set(keep_mats))
    remap = {old: new for new, old in enumerate(used)}
    meta['collision'] = {
        'n': len(coll.pos), 't': len(keep_tris),
        'pos': blob.add(struct.pack('<%df' % (len(coll.pos) * 3), *[c for p in coll.pos for c in p])),
        'idx': blob.add(struct.pack('<%dI' % (len(keep_tris) * 3), *[i for t in keep_tris for i in t])),
        'mat': blob.add(struct.pack('<%dH' % len(keep_mats), *[remap[m] for m in keep_mats])),
        'mats': [names[o] for o in used],
    }
    surf = {}
    for name in meta['collision']['mats']:
        m = mats.get(name, {})
        rec = {k: m[k] for k in ('maxSpeed', 'slowdown', 'reset', 'zipper') if k in m}
        if rec:
            surf[name] = rec
    meta['surfaces'] = surf
    meta['materials'] = {b['mat']: {k: v for k, v in mats[b['mat']].items() if k in ('shader', 'noCull', 'noZ')}
                         for b in meta['batches'] if b.get('mat')}

    # scene extras
    scene = ET.parse(os.path.join(tdir, 'scene.xml')).getroot()
    scroll = {}
    for at in scene.iter('animated-texture'):
        scroll[at.get('name')] = [float(at.get('dx', 0)), float(at.get('dy', 0))]
    meta['scroll'] = scroll
    sun = scene.find('sun')
    if sun is not None:
        meta['sun'] = {
            'dir': list(game(vec(sun.get('xyz'), (0, 100, 0)))),
            'diffuse': [int(v) / 255 for v in (sun.get('sun-diffuse') or '255 255 255').split()],
            'ambient': [int(v) / 255 for v in (sun.get('ambient') or '120 120 120').split()],
        }
        if (sun.get('fog') or '').lower() == 'true':
            meta['fog'] = {'color': [int(v) / 255 for v in sun.get('fog-color', '128 128 128').split()],
                           'start': float(sun.get('fog-start', 50)), 'end': float(sun.get('fog-end', 300)),
                           'max': float(sun.get('fog-max', 1))}
    sky = scene.find('sky-box')
    if sky is not None:
        names_ = sky.get('texture').split()
        meta['skybox'] = [copy_tex(n, tex_dirs, out_dir) for n in names_]
    sc = scene.find('sky-color')
    if sc is not None:
        meta['skyColor'] = [min(255, int(v)) / 255 for v in sc.get('rgb').split()]
    items = []
    for tag, kind in (('item', 'gift'), ('small-nitro', 'nitro_small'), ('big-nitro', 'nitro_big'),
                      ('banana', 'banana'), ('easter-egg', None)):
        for e in scene.iter(tag):
            if kind:
                items.append([kind] + [round(v, 2) for v in game((float(e.get('x')), float(e.get('y')),
                                                                     float(e.get('z'))))])
    meta['items'] = items

    # driveline
    quads = []
    q_root = ET.parse(os.path.join(tdir, 'quads.xml')).getroot()
    for q in q_root.iter('quad'):
        pts = []
        for k in ('p0', 'p1', 'p2', 'p3'):
            v = q.get(k)
            if ':' in v:
                qi, pi = v.split(':')
                pts.append(quads[int(qi)][int(pi)])
            else:
                pts.append(game(vec(v)))
        quads.append(pts)
    meta['quads'] = [[[round(c, 3) for c in p] for p in q] for q in quads]
    succ = {}
    g_root = ET.parse(os.path.join(tdir, 'graph.xml')).getroot()
    for e in g_root:
        if e.tag in ('edge-loop', 'edge-line'):
            a, b = int(e.get('from')), int(e.get('to'))
            for i in range(a, b):
                succ.setdefault(i, []).append(i + 1)
            if e.tag == 'edge-loop':
                succ.setdefault(b, []).append(a)
        elif e.tag == 'edge':
            succ.setdefault(int(e.get('from')), []).append(int(e.get('to')))
    meta['succ'] = [succ.get(i, []) for i in range(len(quads))]

    tx = ET.parse(os.path.join(tdir, 'track.xml')).getroot()
    meta['name'] = tx.get('name')
    meta['laps'] = int(tx.get('default-number-of-laps') or 3)
    music = tx.get('music', '').split()[0] if tx.get('music') else None
    meta['music'] = music_file(music) if music else None
    ds = scene.find('default-start')
    meta['start'] = {'perRow': int(ds.get('karts-per-row', 2)) if ds is not None else 2,
                     'fwd': float(ds.get('forwards-distance', 1.5)) if ds is not None else 1.5,
                     'side': float(ds.get('sidewards-distance', 3)) if ds is not None else 3.0}
    shot = tx.get('screenshot') or 'screenshot.jpg'
    if os.path.exists(os.path.join(tdir, shot)):
        shutil.copyfile(os.path.join(tdir, shot), os.path.join(out_dir, 'screenshot.jpg'))
    lic = os.path.join(tdir, 'licenses.txt')
    lic_text = open(lic, encoding='utf-8', errors='replace').read() if os.path.exists(lic) else ''
    for ld in lib_dirs:
        lp = os.path.join(ld, 'licenses.txt')
        if os.path.exists(lp):
            lic_text += '\n\n# library/%s\n' % os.path.basename(ld) + open(lp, encoding='utf-8', errors='replace').read()
    open(os.path.join(out_dir, 'LICENSES.txt'), 'w').write(lic_text)
    size = pack.write_pack(os.path.join(out_dir, 'pack.png'), meta, blob)
    tris = sum(b['m'] for b in meta['batches']) // 3
    print('track', tid, 'objects', stats['objects'], 'batches', len(meta['batches']), 'tris', tris,
          'coll tris', len(keep_tris), 'pack KB', size // 1024, 'blob KB', blob.size // 1024)


def music_file(music_name):
    p = os.path.join(SRC, 'music', music_name)
    if not os.path.exists(p):
        return None
    x = ET.parse(p).getroot()
    f = x.get('file')
    if not f:
        return None
    os.makedirs(os.path.join(OUT, 'music'), exist_ok=True)
    shutil.copyfile(os.path.join(SRC, 'music', f), os.path.join(OUT, 'music', f))
    return f


# ---------------------------------------------------------------- karts

def build_kart(kid):
    kdir = os.path.join(SRC, 'karts', kid)
    out_dir = os.path.join(OUT, 'karts', kid)
    os.makedirs(out_dir, exist_ok=True)
    kx = ET.parse(os.path.join(kdir, 'kart.xml')).getroot()
    mats = global_materials()
    read_materials(os.path.join(kdir, 'materials.xml'), mats)
    tex_dirs = [kdir] + GLOBAL_TEX_DIRS
    blob = pack.Blob()
    meta = {'id': kid, 'name': kx.get('name'), 'type': kx.get('type', 'medium'),
            'rgb': [float(v) for v in (kx.get('rgb') or '1 1 1').split()]}
    body = Batcher()
    info = read_spm(os.path.join(kdir, kx.get('model-file')))
    body.add_mesh(info, mat_identity(), None)
    meta['body'] = write_batches(body.batches, blob, mats, tex_dirs, out_dir)
    bb = info['bbox']
    meta['bbox'] = [list(game(bb[0:3])), list(game(bb[3:6]))]
    wheels = []
    w_el = kx.find('wheels')
    for name in ('front-left', 'front-right', 'rear-left', 'rear-right'):
        e = w_el.find(name) if w_el is not None else None
        if e is None:
            continue
        wb = Batcher()
        winfo = read_spm(os.path.join(kdir, e.get('model')))
        wb.add_mesh(winfo, mat_identity(), None)
        wheels.append({'pos': list(game(vec(e.get('position')))),
                       'mesh': write_batches(wb.batches, blob, mats, tex_dirs, out_dir)})
    meta['wheels'] = wheels
    ne = kx.find('nitro-emitter')
    if ne is not None:
        meta['nitro'] = [list(game(vec(c.get('position')))) for c in ne]
    for key, attr in (('icon', 'icon-file'), ('shadow', 'shadow-file')):
        if kx.get(attr):
            meta[key] = copy_tex(kx.get(attr), tex_dirs, out_dir)
    for e in kx.iter():
        if e.tag in ('icon-file',) or e.get('icon-file'):
            copy_tex(e.get('icon-file'), tex_dirs, out_dir)
    shutil.copyfile(os.path.join(kdir, 'licenses.txt'), os.path.join(out_dir, 'LICENSES.txt'))
    size = pack.write_pack(os.path.join(out_dir, 'pack.png'), meta, blob)
    print('kart', kid, meta['name'], meta['type'], 'pack KB', size // 1024)
    return {'id': kid, 'name': meta['name'], 'type': meta['type'], 'icon': meta.get('icon'),
            'rgb': meta['rgb']}


# ---------------------------------------------------------------- items, icons, sounds

def build_items():
    out_dir = os.path.join(OUT, 'items')
    os.makedirs(out_dir, exist_ok=True)
    mats = global_materials()
    blob = pack.Blob()
    meta = {'items': {}}
    for key, f in ITEMS.items():
        b = Batcher()
        info = read_spm(os.path.join(SRC, 'models', f))
        b.add_mesh(info, mat_identity(), None)
        meta['items'][key] = {'mesh': write_batches(b.batches, blob, mats, GLOBAL_TEX_DIRS, out_dir),
                              'bbox': [list(game(info['bbox'][0:3])), list(game(info['bbox'][3:6]))]}
    meta['materials'] = {}
    for rec in meta['items'].values():
        for bt in rec['mesh']:
            if bt.get('mat'):
                meta['materials'][bt['mat']] = {k: v for k, v in mats[bt['mat']].items()
                                                if k in ('shader', 'noCull', 'noZ')}
    shutil.copyfile(os.path.join(SRC, 'models', 'licenses.txt'), os.path.join(out_dir, 'LICENSES.txt'))
    size = pack.write_pack(os.path.join(out_dir, 'pack.png'), meta, blob)
    print('items pack KB', size // 1024)


def build_icons():
    src = os.path.join(REF, 'icons')
    out_dir = os.path.join(OUT, 'icons')
    os.makedirs(out_dir, exist_ok=True)
    for n in ICONS:
        p = os.path.join(src, n + '.png')
        if os.path.exists(p):
            shutil.copyfile(p, os.path.join(out_dir, n + '.png'))
    if os.path.exists(os.path.join(src, 'licenses.txt')):
        shutil.copyfile(os.path.join(src, 'licenses.txt'), os.path.join(out_dir, 'LICENSES.txt'))


def build_sounds():
    out_dir = os.path.join(OUT, 'sfx')
    os.makedirs(out_dir, exist_ok=True)
    for n in SFX:
        p = os.path.join(SRC, 'sfx', n + '.ogg')
        if os.path.exists(p):
            shutil.copyfile(p, os.path.join(out_dir, n + '.ogg'))
    shutil.copyfile(os.path.join(SRC, 'sfx', 'licenses.txt'), os.path.join(out_dir, 'LICENSES.txt'))
    for m in MUSIC:
        music_file(m)
    shutil.copyfile(os.path.join(SRC, 'music', 'licenses.txt'), os.path.join(OUT, 'music', 'LICENSES.txt'))


if __name__ == '__main__':
    only = sys.argv[4] if len(sys.argv) > 4 else 'all'
    if only in ('all', 'tracks'):
        for t in TRACKS:
            build_track(t)
    karts = []
    if only in ('all', 'karts'):
        for k in KARTS:
            karts.append(build_kart(k))
    if only in ('all', 'items'):
        build_items()
    if only == 'all':
        build_icons()
        build_sounds()
    if _copied.get('missing'):
        print('missing textures:', sorted(_copied['missing'])[:30])
