"""
debug_portrait.py - Diagnose portrait loading.
Usage: python debug_portrait.py "path/to/chars/folder"
"""
import sys, os, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Correct struct constants (verified sizes) ─────────────────────────────────
# SFF v1 subfile header = 32 bytes
# next(4) len(4) ax(2) ay(2) grp(2) img(2) idx(2) pal(1) pad(13)
_SFF1_HDR = '<IIHHHHHBxxxxxxxxxxxxx'
# SFF v2 sprite entry = 28 bytes
_SFF2_SPR = '<HHHHHHHBBII' + 'HH'

assert struct.calcsize(_SFF1_HDR) == 32, f"SFF1 struct wrong: {struct.calcsize(_SFF1_HDR)}"
assert struct.calcsize(_SFF2_SPR) == 28, f"SFF2 struct wrong: {struct.calcsize(_SFF2_SPR)}"
print(f"Struct sizes OK: SFF1={struct.calcsize(_SFF1_HDR)} SFF2={struct.calcsize(_SFF2_SPR)}")


def test_char(char_def_path):
    print(f"\n{'='*60}")
    print(f"DEF: {char_def_path}")

    # Step 1: parse def
    try:
        from libmugen.parse import MugenParser
        with open(char_def_path, encoding='ascii', errors='surrogateescape') as f:
            data = f.read()
        config = MugenParser()
        config.read_string(data)
        name   = config['info'].get('name', '?')   if config.has_section('info')  else '?'
        author = config['info'].get('author', '?') if config.has_section('info')  else '?'
        print(f"  Name: {name}  Author: {author}")
        has_files = config.has_section('files')
        print(f"  Has [Files] section: {has_files}")
        if has_files:
            sprite_val = config['files'].get('sprite')
            print(f"  sprite = {repr(sprite_val)}")
    except Exception as e:
        print(f"  DEF PARSE FAILED: {e}")
        return

    # Step 2: find SFF
    from core.sff_reader import find_sff_path
    sff_path = find_sff_path(char_def_path)
    if not sff_path:
        print("  SFF NOT FOUND — checking char dir manually...")
        char_dir = os.path.dirname(char_def_path)
        sffs = [f for f in os.listdir(char_dir) if f.lower().endswith('.sff')]
        print(f"  SFF files in char dir: {sffs}")
        return
    print(f"  SFF: {sff_path}  ({os.path.getsize(sff_path):,} bytes)")

    # Step 3: header
    with open(sff_path, 'rb') as f:
        sig      = f.read(12)
        ver      = struct.unpack('4B', f.read(4))
        is_v2    = (ver[3] == 2)
        print(f"  Signature: {sig}  ver={ver}  → {'SFFv2' if is_v2 else 'SFFv1'}")

    # Step 4: sprite scan
    with open(sff_path, 'rb') as f:
        if is_v2:
            _scan_v2(f)
        else:
            _scan_v1(f)

    # Step 5: full get_portrait test
    from core.sff_reader import get_portrait
    try:
        img = get_portrait(sff_path)
        if img is None:
            print("  get_portrait() returned None  ← check roster_manager.log for details")
        else:
            print(f"  SUCCESS: portrait={img.size} mode={img.mode}")
            out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'portrait_test.png')
            img.save(out)
            print(f"  Saved: {out}")
    except Exception as e:
        import traceback
        print(f"  get_portrait() EXCEPTION: {e}")
        traceback.print_exc()


def _scan_v1(f):
    f.seek(16)
    group_total, image_total, next_subfile, hdr_len = struct.unpack('<IIII', f.read(16))
    print(f"  SFFv1: images={image_total} first_offset={next_subfile}")

    HDR = 32
    offset = next_subfile
    samples = []
    found = False

    for _ in range(min(image_total, 5000)):
        if offset == 0: break
        f.seek(offset)
        hdr = f.read(HDR)
        if len(hdr) < HDR:
            print(f"  Short read at offset {offset}")
            break

        (next_off, length, axisx, axisy,
         groupno, imageno, index, pal_flag) = struct.unpack(_SFF1_HDR, hdr)

        if len(samples) < 10 or groupno == 9000:
            samples.append((groupno, imageno, length, pal_flag))

        if groupno == 9000 and imageno == 1:
            print(f"  FOUND 9000,1: length={length} pal_flag={pal_flag} at offset={offset}")
            found = True
            break

        offset = next_off

    if not found:
        print(f"  9000,1 NOT FOUND in sprite table")
        print(f"  First sprites: {samples[:10]}")
        nines = [(g,i,l,p) for g,i,l,p in samples if g == 9000]
        print(f"  Group 9000 entries: {nines}")


def _scan_v2(f):
    f.seek(36)
    (spr_off, spr_total,
     pal_off, pal_total,
     ldata_off, ldata_len,
     tdata_off, tdata_len) = struct.unpack('<IIIIIIII', f.read(32))
    print(f"  SFFv2: sprites={spr_total}@{spr_off}  ldata@{ldata_off}  tdata@{tdata_off}")

    f.seek(spr_off)
    found = False
    samples = []
    for i in range(min(spr_total, 5000)):
        raw = f.read(28)
        if len(raw) < 28: break
        (grp, itm, w, h, ax, ay, idx, fmt, depth,
         doff, dlen, pal_idx, flags) = struct.unpack(_SFF2_SPR, raw)
        if i < 10 or grp == 9000:
            samples.append((grp, itm, w, h, fmt, dlen))
        if grp == 9000 and itm == 1:
            base = tdata_off if (flags & 1) else ldata_off
            print(f"  FOUND 9000,1: {w}x{h} fmt={fmt} doff={doff} dlen={dlen} "
                  f"pal={pal_idx} flags={flags} base={base} → seek={base+doff}")
            found = True
            # Try reading the raw bytes for fmt10 (PNG)
            if fmt == 10:
                f.seek(base + doff)
                png_bytes = f.read(dlen)
                print(f"  PNG first 8 bytes: {png_bytes[:8].hex()}")
                print(f"  Valid PNG header: {png_bytes[:8] == b'\\x89PNG\\r\\n\\x1a\\n'}")
            break

    if not found:
        print(f"  9000,1 NOT FOUND")
        print(f"  First 10: {samples[:10]}")
        nines = [(g,i,w,h,fmt,dl) for g,i,w,h,fmt,dl in samples if g == 9000]
        print(f"  Group 9000: {nines}")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python debug_portrait.py <chars_folder>")
        sys.exit(1)

    chars_dir = sys.argv[1]
    if not os.path.exists(chars_dir):
        print(f"Not found: {chars_dir}")
        sys.exit(1)

    from libmugen.parse import MugenParser
    from libmugen.config import guess_kind

    tested = 0
    for root, dirs, files in os.walk(chars_dir):
        for fname in files:
            if not fname.lower().endswith('.def'):
                continue
            path = os.path.join(root, fname)
            try:
                with open(path, encoding='ascii', errors='surrogateescape') as fh:
                    d = fh.read()
                cfg = MugenParser(); cfg.read_string(d)
                if guess_kind(cfg) != 'character':
                    continue
            except:
                continue
            test_char(path)
            tested += 1
            if tested >= 5:
                break
        if tested >= 5:
            break

    print(f"\n{'='*60}")
    print(f"Tested {tested} characters.")
