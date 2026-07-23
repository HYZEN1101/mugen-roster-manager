"""
sff_reader.py
MUGEN SFF v1 and v2 portrait reader.
Drop this into mugen-roster-manager/core/ replacing the existing file.

Verified struct sizes:
  SFF v1 subfile header : 32 bytes
  SFF v2 sprite entry   : 28 bytes
  SFF v2 palette header : 16 bytes
"""
import struct
import logging
from io import BytesIO

logger = logging.getLogger("sff_reader")

# ── Struct formats ────────────────────────────────────────────────────────────
# SFF v1 subfile header layout (32 bytes):
#   next_subfile(4) length(4) axisx(2) axisy(2)
#   groupno(2) imageno(2) index(2) palette_flag(1) padding(13)
_SFF1_HDR = '<IIHHHHHBxxxxxxxxxxxxx'

# SFF v2 sprite entry layout (28 bytes):
#   groupno(2) itemno(2) width(2) height(2) axisx(2) axisy(2) index(2)
#   format(1) colordepth(1) data_offset(4) data_length(4)
#   palette_index(2) flags(2)
_SFF2_SPR = '<HHHHHHHBBII' + 'HH'

# SFF v2 palette header layout (16 bytes):
#   groupno(2) itemno(2) numcols(2) index(2) data_offset(4) data_length(4)
_SFF2_PAL = '<HHHHII'

# Sanity check at import time
assert struct.calcsize(_SFF1_HDR) == 32, f"SFF1 struct wrong size: {struct.calcsize(_SFF1_HDR)}"
assert struct.calcsize(_SFF2_SPR) == 28, f"SFF2 sprite struct wrong size: {struct.calcsize(_SFF2_SPR)}"
assert struct.calcsize(_SFF2_PAL) == 16, f"SFF2 palette struct wrong size: {struct.calcsize(_SFF2_PAL)}"


# ── RLE / compression decoders ────────────────────────────────────────────────

def _decode_rle8(data, width, height):
    """MUGEN RLE8: 0x00 is escape byte."""
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
            if flag == 0x40:          # colour run
                if i >= len(data): break
                col = data[i]; i += 1
                out.extend([col] * run)
            elif flag == 0x80:        # literal run
                for _ in range(run):
                    if i >= len(data): break
                    out.append(data[i]); i += 1
            else:                     # transparent run (index 0)
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


# ── PCX helpers (SFF v1 uses PCX internally) ──────────────────────────────────

def _pcx_palette(pcx):
    """Extract 256-colour palette from end of PCX data. Returns flat list of 768 ints."""
    if len(pcx) < 769 or pcx[-769] != 0x0C:
        return None
    base = len(pcx) - 768
    pal = []
    for i in range(256):
        pal.extend([pcx[base + i*3],
                    pcx[base + i*3 + 1],
                    pcx[base + i*3 + 2]])
    return pal


def _pcx_to_image(pcx, shared_pal=None):
    """Decode raw PCX bytes into a PIL RGBA Image. Returns None on any error."""
    try:
        from PIL import Image
        if len(pcx) < 128:
            return None

        xmin, ymin, xmax, ymax = struct.unpack('<HHHH', pcx[4:12])
        bytes_per_line = struct.unpack('<H', pcx[66:68])[0]
        w = xmax - xmin + 1
        h = ymax - ymin + 1

        if not (0 < w <= 4096 and 0 < h <= 4096):
            return None

        # Decode PCX RLE scan lines
        raw = bytearray()
        i = 128                         # PCX header is 128 bytes
        need = bytes_per_line * h
        while i < len(pcx) and len(raw) < need:
            b = pcx[i]; i += 1
            if (b & 0xC0) == 0xC0:
                cnt = b & 0x3F
                if i >= len(pcx): break
                val = pcx[i]; i += 1
                raw.extend([val] * cnt)
            else:
                raw.append(b)

        # Palette: shared > embedded in this PCX > header fallback
        pal = shared_pal or _pcx_palette(pcx)
        if pal is None:
            # 16-colour header palette at bytes 16..63
            pal = list(pcx[16:64]) + [0] * (768 - 48)

        # Extract pixel rows (bytes_per_line >= w due to alignment)
        pixels = bytearray()
        for row in range(h):
            pixels.extend(raw[row * bytes_per_line: row * bytes_per_line + w])
        pixels = bytes(pixels[:w * h])

        img = Image.frombytes('P', (w, h), pixels)
        img.putpalette(pal)
        rgba = img.convert('RGBA')

        # Index 0 → transparent
        pdata = rgba.load()
        for y in range(h):
            for x in range(w):
                if pixels[y * w + x] == 0:
                    r, g, b, _ = pdata[x, y]
                    pdata[x, y] = (r, g, b, 0)
        return rgba

    except Exception as e:
        logger.info(f"PCX decode error: {e}")
        return None


# ── SFF v1 ────────────────────────────────────────────────────────────────────

def _read_sffv1(f):
    """
    Walk SFF v1 linked-list subfile chain and decode portrait 9000,1.

    SFF v1 PALETTE SYSTEM (from spec):
      Every subfile header has:
        pal_flag  (1 byte): 1 = this PCX has its OWN palette appended
                            0 = this PCX references another sprite's palette
        index     (2 bytes): when pal_flag=0, this is the subfile NUMBER
                             (0-based position in the chain) of the sprite
                             whose palette to use.

    So to get the correct palette for sprite 9000,1:
      1. Read its header to get index (the palette source sprite number)
      2. Walk the chain to find sprite at that position
      3. Extract the PCX palette from that sprite's data

    The "first pal_flag=1 sprite" approach gives the WRONG palette because
    different sprites in different groups use different palettes.
    """
    f.seek(16)
    group_total, image_total, next_subfile, hdr_len = struct.unpack('<IIII', f.read(16))
    logger.info(f"SFFv1: image_total={image_total} first_offset={next_subfile}")

    HDR = 32

    # Pass 1: build a map of subfile_number → (offset, pcx_len, pal_flag, index)
    # We need this to follow palette links correctly.
    subfiles = []   # list of (offset, pcx_len, groupno, imageno, index, pal_flag)
    portrait_subfile_num = None
    offset = next_subfile

    for n in range(image_total):
        if offset == 0:
            break
        f.seek(offset)
        hdr = f.read(HDR)
        if len(hdr) < HDR:
            break

        (next_off, length, axisx, axisy,
         groupno, imageno, index,
         pal_flag) = struct.unpack(_SFF1_HDR, hdr)

        pcx_len = length - HDR
        subfiles.append((offset, pcx_len, groupno, imageno, index, pal_flag))

        if groupno == 9000 and imageno == 1:
            portrait_subfile_num = n
            logger.info(f"SFFv1: found 9000,1 at subfile#{n} offset={offset} "
                        f"pcx_len={pcx_len} pal_flag={pal_flag} index={index}")

        offset = next_off

    if portrait_subfile_num is None:
        logger.info("SFFv1: 9000,1 not found")
        return {}

    port_offset, pcx_len, _, _, port_index, port_pal_flag = subfiles[portrait_subfile_num]

    if pcx_len <= 0:
        logger.info("SFFv1: portrait pcx_len <= 0")
        return {}

    # Determine which palette to use
    palette = None

    if port_pal_flag == 1:
        # Portrait has its own palette — use it directly
        f.seek(port_offset + HDR)
        pcx = f.read(pcx_len)
        palette = _pcx_palette(pcx)
        logger.info(f"SFFv1: using portrait's own palette")
    else:
        # Follow the index link to the palette source sprite
        pal_source_num = port_index
        if 0 <= pal_source_num < len(subfiles):
            pal_offset, pal_pcx_len, pg, pi, _, pal_flag2 = subfiles[pal_source_num]
            logger.info(f"SFFv1: palette link → subfile#{pal_source_num} "
                        f"({pg},{pi}) pal_flag={pal_flag2}")
            if pal_pcx_len > 0:
                f.seek(pal_offset + HDR)
                pal_pcx = f.read(pal_pcx_len)
                palette = _pcx_palette(pal_pcx)
                if palette:
                    logger.info(f"SFFv1: palette extracted from subfile#{pal_source_num}")

        if palette is None:
            # Fallback: find any pal_flag=1 sprite
            logger.info("SFFv1: palette link failed, searching for any pal_flag=1 sprite")
            for i, (soff, spcx_len, sg, si, sidx, spal) in enumerate(subfiles):
                if spal == 1 and spcx_len > 0:
                    f.seek(soff + HDR)
                    pal_pcx = f.read(spcx_len)
                    palette = _pcx_palette(pal_pcx)
                    if palette:
                        logger.info(f"SFFv1: fallback palette from subfile#{i} ({sg},{si})")
                        break

    # Read portrait PCX (re-read since we may have seeked elsewhere)
    f.seek(port_offset + HDR)
    pcx = f.read(pcx_len)

    img = _pcx_to_image(pcx, palette)
    if img:
        logger.info(f"SFFv1: decoded portrait → {img.size}")
    else:
        logger.info("SFFv1: PCX decode returned None")
    return {(9000, 1): img} if img else {}


# ── SFF v2 ────────────────────────────────────────────────────────────────────

def _read_sffv2(f):
    """Read SFF v2 header, find 9000,1 in sprite table, decode and return it."""
    # SFF v2 file header layout:
    #   signature(12) version(4) reserved(8) compat_ver(4) reserved(8)
    #   sprite_offset(4) sprite_total(4) palette_offset(4) palette_total(4)
    #   ldata_offset(4) ldata_length(4) tdata_offset(4) tdata_length(4)
    f.seek(36)      # skip sig(12)+ver(4)+reserved(8)+compat(4)+reserved(8) = 36
    (spr_off, spr_total,
     pal_off, pal_total,
     ldata_off, ldata_len,
     tdata_off, tdata_len) = struct.unpack('<IIIIIIII', f.read(32))

    logger.info(f"SFFv2: sprites={spr_total}@{spr_off} palettes={pal_total}@{pal_off} "
                f"ldata@{ldata_off}({ldata_len}) tdata@{tdata_off}({tdata_len})")

    # Scan sprite table for 9000,1
    f.seek(spr_off)
    target = None
    for i in range(spr_total):
        raw = f.read(28)
        if len(raw) < 28:
            break
        (grp, itm, w, h, ax, ay, idx,
         fmt, depth,
         doff, dlen,
         pal_idx, flags) = struct.unpack(_SFF2_SPR, raw)

        if grp == 9000 and itm == 1:
            target = dict(w=w, h=h, fmt=fmt,
                          doff=doff, dlen=dlen,
                          pal_idx=pal_idx, flags=flags,
                          ldata_off=ldata_off,
                          tdata_off=tdata_off)
            logger.info(f"SFFv2: found 9000,1 at entry#{i}: "
                        f"{w}x{h} fmt={fmt} doff={doff} dlen={dlen} "
                        f"pal={pal_idx} flags={flags}")
            break

    if target is None:
        logger.info("SFFv2: 9000,1 not found in sprite table")
        return {}

    # Read palettes (needed for indexed formats 0/2/3/4)
    pals = _read_sffv2_palettes(f, pal_off, pal_total, ldata_off)

    img = _decode_sffv2_sprite(f, target, pals)
    if img:
        logger.info(f"SFFv2: portrait decoded → {img.size} {img.mode}")
        return {(9000, 1): img}
    logger.info("SFFv2: decode returned None")
    return {}


def _read_sffv2_palettes(f, pal_off, pal_total, ldata_off):
    """Return list of 256-colour palettes as flat 768-int lists."""
    pals = []
    f.seek(pal_off)
    hdrs = []
    for _ in range(pal_total):
        raw = f.read(16)
        if len(raw) < 16:
            break
        grp, itm, ncols, idx, doff, dlen = struct.unpack(_SFF2_PAL, raw)
        hdrs.append((ncols, doff, dlen))

    for ncols, doff, dlen in hdrs:
        f.seek(ldata_off + doff)
        raw = f.read(dlen)
        pal = []
        n = min(ncols, 256)
        for i in range(n):
            if i * 4 + 3 >= len(raw):
                break
            pal.extend([raw[i*4], raw[i*4+1], raw[i*4+2]])
        while len(pal) < 768:
            pal.append(0)
        pals.append(pal)

    return pals


def _decode_sffv2_sprite(f, s, pals):
    """Decode one SFF v2 sprite into PIL RGBA Image."""
    try:
        from PIL import Image

        w, h = s['w'], s['h']
        if w == 0 or h == 0:
            return None

        # flags bit 0: 0 = data in ldata section, 1 = data in tdata section
        base = s['tdata_off'] if (s['flags'] & 1) else s['ldata_off']
        seek_pos = base + s['doff']
        f.seek(seek_pos)
        raw = f.read(s['dlen'])

        if not raw:
            logger.info(f"SFFv2: empty raw data at seek={seek_pos}")
            return None

        fmt = s['fmt']
        logger.info(f"SFFv2: decoding fmt={fmt} size={w}x{h} "
                    f"raw={len(raw)} bytes first8={raw[:8].hex()}")

        # ── Format 10: embedded PNG ───────────────────────────────────────
        # The raw data has a variable-length prefix before the PNG magic bytes.
        # Observed prefixes: 4 bytes (uint32 uncompressed size).
        # We scan the first 16 bytes for the PNG magic \x89PNG and skip to it.
        if fmt == 10:
            PNG_MAGIC = b'\x89PNG\r\n\x1a\n'
            png_offset = 0
            # Search for PNG magic in first 16 bytes
            for search_off in range(min(16, len(raw) - 4)):
                if raw[search_off:search_off+4] == b'\x89PNG':
                    png_offset = search_off
                    break
            try:
                png_data = raw[png_offset:]
                logger.info(f"SFFv2 fmt10: PNG magic at offset={png_offset} "
                            f"first8={raw[:8].hex()}")
                img = Image.open(BytesIO(png_data)).convert('RGBA')
                logger.info(f"SFFv2 fmt10: decoded → {img.size}")
                return img
            except Exception as e:
                logger.info(f"SFFv2 fmt10 PNG error: {e} — first16={raw[:16].hex()}")
                return None

        # ── Indexed pixel formats ─────────────────────────────────────────
        if fmt == 0:
            pixels = raw[:w * h]
        elif fmt == 2:
            pixels = _decode_rle8(raw[4:], w, h)
        elif fmt == 3:
            pixels = _decode_rle5(raw[4:], w, h)
        elif fmt == 4:
            pixels = _decode_lz5(raw[4:], w, h)
        else:
            logger.info(f"SFFv2: unknown format {fmt}")
            return None

        # Pad or trim to exact size
        need = w * h
        if len(pixels) < need:
            pixels = pixels + b'\x00' * (need - len(pixels))
        pixels = bytes(pixels[:need])

        # Select palette
        pal_i = s['pal_idx']
        if pals and pal_i < len(pals):
            pal = pals[pal_i]
        elif pals:
            pal = pals[0]
        else:
            pal = list(range(256)) * 3     # greyscale fallback

        img = Image.frombytes('P', (w, h), pixels)
        img.putpalette(pal)
        rgba = img.convert('RGBA')

        # Index 0 → transparent
        pdata = rgba.load()
        for y in range(h):
            for x in range(w):
                if pixels[y * w + x] == 0:
                    r, g, b, _ = pdata[x, y]
                    pdata[x, y] = (r, g, b, 0)
        return rgba

    except Exception as e:
        import traceback
        logger.info(f"SFFv2 decode error: {e}\n{traceback.format_exc()}")
        return None


# ── Public API ────────────────────────────────────────────────────────────────

def get_portrait(sff_path):
    """
    Extract portrait sprite (group=9000, index=1) from a MUGEN SFF file.
    Returns PIL RGBA Image or None.
    Supports SFF v1 (PCX-based) and SFF v2 (MUGEN 1.1).
    """
    try:
        from PIL import Image  # noqa — ensure Pillow is available
        with open(sff_path, 'rb') as f:
            sig = f.read(12)
            if sig != b'ElecbyteSpr\x00':
                logger.info(f"Not a valid SFF file: {sff_path}")
                return None
            ver = struct.unpack('4B', f.read(4))
            # ver = (verlo3, verlo2, verlo1, verhi)
            # verhi == 1 → SFF v1,  verhi == 2 → SFF v2
            is_v2 = (ver[3] == 2)
            logger.info(f"SFF ver={ver} → {'v2' if is_v2 else 'v1'}")
            f.seek(0)
            sprites = _read_sffv2(f) if is_v2 else _read_sffv1(f)
        return sprites.get((9000, 1))
    except Exception as e:
        import traceback
        logger.info(f"get_portrait error [{sff_path}]: {e}\n{traceback.format_exc()}")
        return None


def find_sff_path(char_def_path):
    """
    Given a character .def path, read [Files] sprite= and return
    the absolute path to the .sff file. Returns None if not found.
    """
    import os
    from libmugen.parse import MugenParser
    try:
        with open(char_def_path, encoding='ascii', errors='surrogateescape') as f:
            data = f.read()
        cfg = MugenParser()
        cfg.read_string(data)

        if not cfg.has_section('files'):
            logger.info(f"No [Files] section: {char_def_path}")
            return None

        srel = cfg['files'].get('sprite')
        if not srel:
            logger.info(f"No sprite= key: {char_def_path}")
            return None

        # Strip quotes, normalise separators
        srel = srel.strip('" \'').replace('/', os.sep).replace('\\', os.sep)
        char_dir = os.path.dirname(char_def_path)
        spath = os.path.normpath(os.path.join(char_dir, srel))

        if os.path.exists(spath):
            return spath

        # Case-insensitive fallback (Windows paths can differ in case)
        sname = os.path.basename(spath).lower()
        sdir  = os.path.dirname(spath)
        if os.path.isdir(sdir):
            for entry in os.listdir(sdir):
                if entry.lower() == sname:
                    found = os.path.join(sdir, entry)
                    logger.info(f"SFF found via case-insensitive match: {found}")
                    return found

        logger.info(f"SFF not found at: {spath}")
        return None

    except Exception as e:
        logger.info(f"find_sff_path error [{char_def_path}]: {e}")
        return None