"""
debug_portrait.py
Drop into mugen-roster-manager/ and run:
  python debug_portrait.py "C:\path\to\chars"
"""
import sys, os, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_SFF1_HDR = '<IIHHHHHBxxxxxxxxxxxxx'   # 32 bytes
_SFF2_SPR = '<HHHHHHHBBII' + 'HH'      # 28 bytes

assert struct.calcsize(_SFF1_HDR) == 32, f"SFF1={struct.calcsize(_SFF1_HDR)}"
assert struct.calcsize(_SFF2_SPR) == 28, f"SFF2={struct.calcsize(_SFF2_SPR)}"
print(f"Struct sizes OK — SFF1={struct.calcsize(_SFF1_HDR)}  SFF2={struct.calcsize(_SFF2_SPR)}")


def test_char(path):
    print(f"\n{'='*60}\nDEF: {path}")
    try:
        from libmugen.parse import MugenParser
        with open(path, encoding='ascii', errors='surrogateescape') as f:
            d = f.read()
        cfg = MugenParser(); cfg.read_string(d)
        name   = cfg['info'].get('name', '?')   if cfg.has_section('info')  else '?'
        author = cfg['info'].get('author', '?') if cfg.has_section('info')  else '?'
        print(f"  Name: {name}   Author: {author}")
        srel = cfg['files'].get('sprite') if cfg.has_section('files') else None
        print(f"  sprite = {repr(srel)}")
    except Exception as e:
        print(f"  DEF parse failed: {e}"); return

    from core.sff_reader import find_sff_path, get_portrait
    sff = find_sff_path(path)
    if not sff:
        print("  SFF NOT FOUND"); return
    print(f"  SFF: {sff}  ({os.path.getsize(sff):,} bytes)")

    with open(sff, 'rb') as f:
        sig = f.read(12)
        ver = struct.unpack('4B', f.read(4))
        is_v2 = ver[3] == 2
        print(f"  Signature: {sig}   ver={ver}  → {'SFFv2' if is_v2 else 'SFFv1'}")

    # Sprite scan
    with open(sff, 'rb') as f:
        if is_v2:
            _scan_v2(f)
        else:
            _scan_v1(f)

    # Full decode test
    print("  Running get_portrait()...")
    img = get_portrait(sff)
    if img is None:
        print("  RESULT: None — check roster_manager.log for details")
    else:
        print(f"  RESULT: SUCCESS {img.size} {img.mode}")
        out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'portrait_test.png')
        img.save(out)
        print(f"  Saved: {out}")


def _scan_v1(f):
    f.seek(16)
    _, image_total, next_subfile, _ = struct.unpack('<IIII', f.read(16))
    print(f"  SFFv1: images={image_total}  first_offset={next_subfile}")
    offset = next_subfile
    samples = []
    for _ in range(min(image_total, 5000)):
        if offset == 0: break
        f.seek(offset)
        hdr = f.read(32)
        if len(hdr) < 32:
            print(f"  Short read at offset {offset}"); break
        (next_off, length, _, _, groupno, imageno, _, pal) = struct.unpack(_SFF1_HDR, hdr)
        samples.append((groupno, imageno, length, pal))
        if groupno == 9000 and imageno == 1:
            print(f"  FOUND 9000,1: length={length} pal_flag={pal} offset={offset}")
            return
        offset = next_off
    print(f"  9000,1 NOT FOUND")
    print(f"  First 10 sprites: {samples[:10]}")
    print(f"  Group 9000 sprites: {[s for s in samples if s[0]==9000]}")


def _scan_v2(f):
    f.seek(36)
    spr_off, spr_total, _, _, ldata_off, _, tdata_off, _ = struct.unpack('<IIIIIIII', f.read(32))
    print(f"  SFFv2: sprites={spr_total}@{spr_off}  ldata@{ldata_off}  tdata@{tdata_off}")
    f.seek(spr_off)
    samples = []
    for i in range(min(spr_total, 5000)):
        raw = f.read(28)
        if len(raw) < 28: break
        grp, itm, w, h, _, _, _, fmt, _, doff, dlen, pal, flags = struct.unpack(_SFF2_SPR, raw)
        samples.append((grp, itm, w, h, fmt, dlen))
        if grp == 9000 and itm == 1:
            base = tdata_off if (flags & 1) else ldata_off
            print(f"  FOUND 9000,1 at entry#{i}: {w}x{h} fmt={fmt} doff={doff} dlen={dlen} flags={flags}")
            print(f"  Data location: {'tdata' if (flags&1) else 'ldata'} base={base} → seek={base+doff}")
            if fmt == 10:
                f.seek(base + doff)
                png = f.read(min(dlen, 16))
                valid = png[:8] == b'\x89PNG\r\n\x1a\n'
                print(f"  PNG header check: {png[:8].hex()}  valid={valid}")
            return
    print(f"  9000,1 NOT FOUND")
    print(f"  First 10: {samples[:10]}")
    print(f"  Group 9000: {[s for s in samples if s[0]==9000]}")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python debug_portrait.py <chars_folder>"); sys.exit(1)
    chars_dir = sys.argv[1]
    from libmugen.parse import MugenParser
    from libmugen.config import guess_kind
    tested = 0
    for root, dirs, files in os.walk(chars_dir):
        for fname in files:
            if not fname.lower().endswith('.def'): continue
            p = os.path.join(root, fname)
            try:
                with open(p, encoding='ascii', errors='surrogateescape') as fh: d = fh.read()
                cfg = MugenParser(); cfg.read_string(d)
                if guess_kind(cfg) != 'character': continue
            except: continue
            test_char(p)
            tested += 1
            if tested >= 5: break
        if tested >= 5: break
    print(f"\n{'='*60}\nTested {tested} characters.")
