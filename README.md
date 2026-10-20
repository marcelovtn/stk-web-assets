# SuperTuxKart web assets

Tracks, karts, items, icons, music and sound effects from
[SuperTuxKart](https://supertuxkart.net), repacked so a browser game can load
them from a CDN. They feed an unofficial web port of SuperTuxKart that runs as
a Hubs app.

This is not an official SuperTuxKart project. All the art, models, music and
sounds belong to the SuperTuxKart artists. They are licensed under
CC-BY-SA, GPL and other free licenses. Each folder has a `LICENSES.txt` copied
from the upstream asset that names the authors and the license of every file.
Anything you make from these files keeps those licenses and needs the same
credit.

## Where to load them from

Everything lives under `v2/` and is served by GitHub Pages at
`https://marcelovtn.github.io/stk-web-assets/v2/` (CORS open, real content types).
The older `v1` set stays reachable through the `v1` tag
(`https://cdn.jsdelivr.net/gh/marcelovtn/stk-web-assets@v1/`).

## What is here

| Folder | Contents |
| --- | --- |
| `v2/tracks/<id>/` | 21 race tracks, 9 battle arenas, 6 soccer fields: `pack.png` (meshes, instanced props, collision, driveline or navmesh, start spots, cannons, goals), the textures, a screenshot |
| `v2/karts/<id>/` | all 18 karts: `pack.png` (body and wheels), textures, icon and shadow |
| `v2/items/` | `pack.png` with gift box, banana, nitro, bowling ball, cake, gum, plunger, swatter, parachute and rubber ball |
| `v2/icons/` | HUD and powerup icons from `stk-code/data/gui/icons` |
| `v2/music/`, `v2/sfx/` | Ogg Vorbis files, unchanged |

Source: the `stk-assets-lq.zip` of the SuperTuxKart 1.5 asset release
(`supertuxkart/stk-assets-mobile`) and `stk-code` 1.5 for the icons.

## Pack format

A sandboxed page may load images from https but cannot make requests, so the
binary data travels inside a lossless RGB PNG (no alpha, 1024 px wide). Read
the pixels row by row, R G B per pixel:

```
'STKW' | u32 payload length | u32 json length | json (utf-8) | pad to 4 | blob
```

All offsets in the JSON are relative to the blob. Meshes are baked per material
in "game space", which is STK/Irrlicht coordinates with z negated (right-handed,
y up; karts face -z). Each batch has positions as f32x3, normals as i8x4
normalized, uv as f16x2, optional vertex colour as u8x4, and indices as u32.

`tools/` holds the converter (`build.py`, with `spm.py` reading STK's `.spm`
format). Run it with
`python3 build.py <stk assets dir> <stk-code ref dir> <out dir>`.
