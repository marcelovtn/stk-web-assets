"""Turn old->new file changes into page.code.edit patches (unique old_string, minimal context)."""
import difflib, json, sys
old_path, new_path = sys.argv[1], sys.argv[2]
a = open(old_path).read().split('\n')
b = open(new_path).read().split('\n')
src = '\n'.join(a)
edits = []
for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
    if tag == 'equal':
        continue
    ctx = 0
    while True:
        lo, hi = max(0, i1 - ctx), min(len(a), i2 + ctx)
        old = '\n'.join(a[lo:hi])
        if old and src.count(old) == 1:
            break
        ctx += 1
    new = '\n'.join(a[lo:i1] + b[j1:j2] + a[i2:hi])
    edits.append({'old_string': old, 'new_string': new})
# merge overlapping contexts by applying sequentially is fine as long as olds stay unique after earlier edits
cur = src
for e in edits:
    assert cur.count(e['old_string']) == 1, e['old_string'][:80]
    cur = cur.replace(e['old_string'], e['new_string'])
assert cur == '\n'.join(b)
print(json.dumps(edits, ensure_ascii=False))
