"""
sff_reader.py - Standalone MUGEN SFF sprite reader.
SFF v1 subfile header = 32 bytes exactly.
SFF v2 sprite entry   = 28 bytes exactly.
"""
import struct
import logging
from io import BytesIO

logger = logging.getLogger("sff_reader")

# Verified struct formats
_SFF1_HDR  = '<IIHHHHHBxxxxxxxxxxxxx'  # 32 bytes: next(4)+len(4)+ax(2)+ay(2)+grp(2)+img(2)+idx(2)+pal(1)+pad(13)
_SFF2_SPR  = '<HHHHHHHBBII' + 'HH'     # 28 bytes
_SFF2_PAL  = '<HHHHII'                 # 16 bytes

import struct as _s
assert _s.calcsize(_SFF1_HDR) == 32
assert _s.calcsize(_SFF2_SPR) == 28
assert _s.calcsize(_SFF2_PAL) == 16


# ── RLE decoders ─────────────────────────────────────────────────────────────

def _decode_rle8(data, width, height):
    out = bytearray()
    total = width * height
    i = 0
    while i < len(data) and len(out) < total:
        b = data[i]; i += 1
        if b == 0x00:
            if i >= len(data): break
            ctrl = data[i]; i += 1
            run  = ctrl & 0x3F
            flag = ctrl & 0xC0
            if flag == 0x40:
                if i >= len(data): break
                col = data[i]; i += 1
                out.extend([col] * run)
            elif flag == 0x80:
                for _ in range(run):
                    if i >= len(data): break
                    out.append(data[i]); i += 1
            else:
                out.extend([0] * run)
        else:
            out.append(b)
    return bytes(out[:total])


def _decode_rle5(data, width, height):
    out = bytearray()
    total = width * height
    i = 0
    while i < len(data) and len(out) < total:
        b = data[i]; i += 1
        if b & 0xC0 == 0x40:
            run = (b & 0x3F) + 2
            if i >= len(data): break
            col = data[i]; i += 1
            out.extend([col] * run)
        elif b & 0xC0 == 0x80:
            run = b & 0x3F
            for _ in range(run):
                if i >= len(data): break
                out.append(data[i]); i += 1
        else:
            out.append(b)
    return bytes(out[:total])


def _decode_lz5(data, width, height):
    out = bytearray()
    total = width * height
    i = 0
    while i < len(data) and len(out) < total:
        b = data[i]; i += 1
        if b & 0xC0 == 0x00:
            run = (b & 0x3F) + 2
            if i >= len(data): break
            col = data[i]; i += 1
            out.extend([col] * run)
        elif b & 0xC0 == 0x40:
            run  = b & 0x3F
            if i >= len(data): break
            back = data[i] + 1; i += 1
            src  = max(0, len(out) - back)
            for j in range(run):
                out.append(out[src + j] if src + j < len(out) else 0)
        elif b & 0xC0 == 0x80:
            run = b & 0x3F
            for _ in range(run):
                if i >= len(data): break
                out.append(data[i]); i += 1
        else:
            out.append(b)
    return bytes(out[:total])


# ── PCX (SFF v1) ─────────────────────────────────────────────────────────────

def _pcx_palette(pcx):
    if len(pcx) < 769 or pcx[-769] != 0x0C:
        return None
    base = len(pcx) - 768
    pal = []
    for i in range(256):
        pal.extend([pcx[base+i*3], pcx[base+i*3+1], pcx[base+i*3+2]])
    return pal


def _pcx_to_image(pcx, shared_pal=None):
    try:
        from PIL import Image
        if len(pcx) < 128:
            return None
        xmin, ymin, xmax, ymax = struct.unpack('<HHHH', pcx[4:12])
        bpl = struct.unpack('<H', pcx[66:68])[0]
        w = xmax - xmin + 1
        h = ymax - ymin + 1
        if not (0 < w <= 4096 and 0 < h <= 4096):
            return None
        # decode PCX RLE
        raw = bytearray()
        i = 128
        need = bpl * h
        while i < len(pcx) and len(raw) < need:
            b = pcx[i]; i += 1
            if (b & 0xC0) == 0xC0:
                cnt = b & 0x3F
                if i >= len(pcx): break
                val = pcx[i]; i += 1
                raw.extend([val] * cnt)
            else:
                raw.append(b)
        pal = shared_pal or _pcx_palette(pcx) or (list(pcx[16:64]) + [0]*(768-48))
        pixels = bytearray()
        for row in range(h):
            pixels.extend(raw[row*bpl : row*bpl + w])
        pixels = bytes(pixels[:w*h])
        img = Image.frombytes('P', (w, h), pixels)
        img.putpalette(pal)
        rgba = img.convert('RGBA')
        pdata = rgba.load()
        for y in range(h):
            for x in range(w):
                if pixels[y*w + x] == 0:
                    r,g,b,_ = pdata[x,y]
                    pdata[x,y] = (r,g,b,0)
        return rgba
    except Exception as e:
        logger.info(f"PCX decode error: {e}")
        return None


# ── SFF v1 ────────────────────────────────────────────────────────────────────

def _read_sffv1(f):
    f.seek(16)  # past signature(12) + version(4)
    group_total, image_total, next_subfile, hdr_len = struct.unpack('<IIII', f.read(16))

    shared_pal = None
    offset = next_subfile
    HDR = 32

    for _ in range(image_total):
        if offset == 0:
            break
        f.seek(offset)
        hdr = f.read(HDR)
        if len(hdr) < HDR:
            break

        (next_off, length, axisx, axisy,
         groupno, imageno, index, pal_flag) = struct.unpack(_SFF1_HDR, hdr)

        pcx_len = length - HDR
        if pcx_len <= 0:
            offset = next_off
            continue

        if groupno == 9000 and imageno == 1:
            pcx = f.read(pcx_len)
            img = _pcx_to_image(pcx, shared_pal)
            if img:
                logger.info(f"SFFv1: decoded 9000,1 → {img.size}")
            else:
                logger.info("SFFv1: 9000,1 PCX decode failed")
            return {(9000,1): img} if img else {}

        # Collect shared palette from first sprite that owns one
        if shared_pal is None and pal_flag == 1:
            pcx = f.read(pcx_len)
            shared_pal = _pcx_palette(pcx)

        offset = next_off

    logger.info("SFFv1: 9000,1 not found")
    return {}


# ── SFF v2 ────────────────────────────────────────────────────────────────────

def _read_sffv2(f):
    f.seek(36)  # skip sig(12)+ver(4)+res(8)+compat(4)+res(8) = 36
    (spr_off, spr_total,
     pal_off, pal_total,
     ldata_off, ldata_len,
     tdata_off, tdata_len) = struct.unpack('<IIIIIIII', f.read(32))

    logger.info(f"SFFv2: sprites={spr_total}@{spr_off} pals={pal_total}@{pal_off} "
                f"ldata@{ldata_off} tdata@{tdata_off}")

    # Scan sprite table
    f.seek(spr_off)
    target = None
    for i in range(spr_total):
        raw = f.read(28)
        if len(raw) < 28: break
        (grp, itm, w, h, ax, ay, idx, fmt, depth,
         doff, dlen, pal_idx, flags) = struct.unpack(_SFF2_SPR, raw)
        if grp == 9000 and itm == 1:
            target = dict(w=w, h=h, fmt=fmt, doff=doff, dlen=dlen,
                          pal_idx=pal_idx, flags=flags,
                          ldata_off=ldata_off, tdata_off=tdata_off)
            logger.info(f"SFFv2: 9000,1 at entry#{i}: {w}x{h} fmt={fmt} "
                        f"doff={doff} dlen={dlen} pal={pal_idx} flags={flags}")
            break

    if target is None:
        logger.info("SFFv2: 9000,1 not found")
        return {}

    pals = _read_sffv2_palettes(f, pal_off, pal_total, ldata_off)
    img  = _decode_sffv2_sprite(f, target, pals)
    if img:
        logger.info(f"SFFv2: success → {img.size} {img.mode}")
        return {(9000,1): img}
    return {}


def _read_sffv2_palettes(f, pal_off, pal_total, ldata_off):
    pals = []
    f.seek(pal_off)
    hdrs = []
    for _ in range(pal_total):
        raw = f.read(16)
        if len(raw) < 16: break
        grp, itm, ncols, idx, doff, dlen = struct.unpack(_SFF2_PAL, raw)
        hdrs.append((ncols, doff, dlen))
    for ncols, doff, dlen in hdrs:
        f.seek(ldata_off + doff)
        raw = f.read(dlen)
        pal = []
        for i in range(min(ncols, 256)):
            if i*4+3 >= len(raw): break
            pal.extend([raw[i*4], raw[i*4+1], raw[i*4+2]])
        while len(pal) < 768: pal.append(0)
        pals.append(pal)
    return pals


def _decode_sffv2_sprite(f, s, pals):
    try:
        from PIL import Image
        w, h = s['w'], s['h']
        if w == 0 or h == 0: return None

        base = s['tdata_off'] if (s['flags'] & 1) else s['ldata_off']
        f.seek(base + s['doff'])
        raw = f.read(s['dlen'])
        if not raw:
            logger.info("SFFv2: empty raw data")
            return None

        fmt = s['fmt']
        logger.info(f"SFFv2: fmt={fmt} raw={len(raw)} bytes, first={raw[:8].hex()}")

        if fmt == 10:
            # PNG bytes embedded directly
            try:
                return Image.open(BytesIO(raw)).convert('RGBA')
            except Exception as e:
                logger.info(f"SFFv2 PNG error: {e}")
                return None

        if   fmt == 0: pixels = raw[:w*h]
        elif fmt == 2: pixels = _decode_rle8(raw[4:], w, h)
        elif fmt == 3: pixels = _decode_rle5(raw[4:], w, h)
        elif fmt == 4: pixels = _decode_lz5(raw[4:], w, h)
        else:
            logger.info(f"SFFv2: unknown fmt {fmt}")
            return None

        if len(pixels) < w*h:
            pixels = pixels + b'\x00'*(w*h - len(pixels))
        pixels = bytes(pixels[:w*h])

        pal_i = s['pal_idx']
        pal = pals[pal_i] if pals and pal_i < len(pals) else (pals[0] if pals else list(range(256))*3)

        img = Image.frombytes('P', (w,h), pixels)
        img.putpalette(pal)
        rgba = img.convert('RGBA')
        pdata = rgba.load()
        for y in range(h):
            for x in range(w):
                if pixels[y*w + x] == 0:
                    r,g,b,_ = pdata[x,y]
                    pdata[x,y] = (r,g,b,0)
        return rgba

    except Exception as e:
        logger.info(f"SFFv2 decode error: {e}")
        import traceback; logger.info(traceback.format_exc())
        return None


# ── Public API ────────────────────────────────────────────────────────────────

def get_portrait(sff_path):
    try:
        from PIL import Image
        with open(sff_path, 'rb') as f:
            sig = f.read(12)
            if sig != b'ElecbyteSpr\x00':
                logger.info(f"Not a valid SFF: {sff_path}")
                return None
            ver = struct.unpack('4B', f.read(4))
            is_v2 = (ver[3] == 2)
            logger.info(f"SFF ver={ver} {'v2' if is_v2 else 'v1'}: {sff_path}")
            f.seek(0)
            sprites = _read_sffv2(f) if is_v2 else _read_sffv1(f)
        return sprites.get((9000,1)) if sprites else None
    except Exception as e:
        logger.info(f"get_portrait error: {e}")
        return None


def find_sff_path(char_def_path):
    import os
    from libmugen.parse import MugenParser
    try:
        with open(char_def_path, encoding='ascii', errors='surrogateescape') as f:
            data = f.read()
        cfg = MugenParser()
        cfg.read_string(data)
        if not cfg.has_section('files'):
            return None
        srel = cfg['files'].get('sprite')
        if not srel:
            return None
        srel = srel.strip('" \'').replace('/', os.sep).replace('\\', os.sep)
        char_dir = os.path.dirname(char_def_path)
        spath = os.path.normpath(os.path.join(char_dir, srel))
        if os.path.exists(spath):
            return spath
        # case-insensitive fallback
        sname = os.path.basename(spath).lower()
        sdir  = os.path.dirname(spath)
        if os.path.isdir(sdir):
            for e in os.listdir(sdir):
                if e.lower() == sname:
                    return os.path.join(sdir, e)
        logger.info(f"SFF not found: {spath}")
        return None
    except Exception as e:
        logger.info(f"find_sff_path error: {e}")
        return None
