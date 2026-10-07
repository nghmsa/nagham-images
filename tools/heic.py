import struct, sys, subprocess, os, tempfile
from PIL import Image

def boxes(d, s, e):
    while s + 8 <= e:
        sz, t = struct.unpack('>I4s', d[s:s+8]); h = 8
        if sz == 1: sz = struct.unpack('>Q', d[s+8:s+16])[0]; h = 16
        elif sz == 0: sz = e - s
        yield t.decode('latin1'), s + h, s + sz
        s += sz

def parse(d):
    info = {'items': {}, 'loc': {}, 'props': [], 'assoc': {}, 'dimg': {}, 'pitm': None}
    for t, s, e in boxes(d, 0, len(d)):
        if t != 'meta': continue
        s += 4
        for t, s2, e2 in boxes(d, s, e):
            if t == 'pitm':
                v = d[s2]; info['pitm'] = struct.unpack('>H' if v == 0 else '>I', d[s2+4:s2+(6 if v == 0 else 8)])[0]
            elif t == 'iinf':
                v = d[s2]; p = s2 + 4 + (2 if v == 0 else 4)
                for tt, a, b in boxes(d, p, e2):
                    vv = d[a]
                    if vv >= 2:
                        iid = struct.unpack('>H', d[a+4:a+6])[0] if vv == 2 else struct.unpack('>I', d[a+4:a+8])[0]
                        o = a + 4 + (2 if vv == 2 else 4) + 2
                        info['items'][iid] = d[o:o+4].decode('latin1')
            elif t == 'iloc':
                v = d[s2]; b1 = d[s2+4]; b2 = d[s2+5]
                osz, lsz = b1 >> 4, b1 & 15; bo, ib = b2 >> 4, b2 & 15
                p = s2 + 6
                if v < 2: cnt = struct.unpack('>H', d[p:p+2])[0]; p += 2
                else: cnt = struct.unpack('>I', d[p:p+4])[0]; p += 4
                rd = lambda n, p: int.from_bytes(d[p:p+n], 'big')
                for _ in range(cnt):
                    if v < 2: iid = rd(2, p); p += 2
                    else: iid = rd(4, p); p += 4
                    cm = 0
                    if v in (1, 2): cm = rd(2, p) & 15; p += 2
                    p += 2
                    p += bo
                    ec = rd(2, p); p += 2
                    ext = []
                    for _ in range(ec):
                        if v in (1, 2) and ib: p += ib
                        o = rd(osz, p); p += osz
                        l = rd(lsz, p); p += lsz
                        ext.append((o, l))
                    info['loc'][iid] = ext; info.setdefault('cm', {})[iid] = cm
            elif t == 'idat':
                info['idat'] = (s2, e2)
            elif t == 'iprp':
                for tt, a, b in boxes(d, s2, e2):
                    if tt == 'ipco':
                        for t3, c, f in boxes(d, a, b):
                            info['props'].append((t3, d[c:f]))
                    elif tt == 'ipma':
                        v = d[a]; fl = int.from_bytes(d[a+1:a+4], 'big')
                        n = struct.unpack('>I', d[a+4:a+8])[0]; p = a + 8
                        for _ in range(n):
                            if v < 1: iid = struct.unpack('>H', d[p:p+2])[0]; p += 2
                            else: iid = struct.unpack('>I', d[p:p+4])[0]; p += 4
                            k = d[p]; p += 1; lst = []
                            for _ in range(k):
                                if fl & 1: x = struct.unpack('>H', d[p:p+2])[0]; p += 2; idx = x & 0x7fff
                                else: idx = d[p] & 0x7f; p += 1
                                lst.append(idx)
                            info['assoc'][iid] = lst
            elif t == 'iref':
                v = d[s2]
                for tt, a, b in boxes(d, s2 + 4, e2):
                    if tt == 'dimg':
                        if v == 0:
                            fr = struct.unpack('>H', d[a:a+2])[0]; n = struct.unpack('>H', d[a+2:a+4])[0]
                            to = list(struct.unpack('>%dH' % n, d[a+4:a+4+2*n]))
                        else:
                            fr = struct.unpack('>I', d[a:a+4])[0]; n = struct.unpack('>H', d[a+4:a+6])[0]
                            to = list(struct.unpack('>%dI' % n, d[a+6:a+6+4*n]))
                        info['dimg'][fr] = to
    return info

def hvc_params(b):
    nl = (b[21] & 3) + 1
    n = b[22]; p = 23; out = b''
    for _ in range(n):
        p += 1; cnt = struct.unpack('>H', b[p:p+2])[0]; p += 2
        for _ in range(cnt):
            l = struct.unpack('>H', b[p:p+2])[0]; p += 2
            out += b'\0\0\0\1' + b[p:p+l]; p += l
    return nl, out

def decode_tile(d, info, iid, tmp):
    ps = [info['props'][i-1] for i in info['assoc'][iid]]
    hv = [x for t, x in ps if t == 'hvcC'][0]
    nl, params = hvc_params(hv)
    ext = info['loc'][iid]
    data = b''.join(d[o:o+l] for o, l in ext)
    out = params; p = 0
    while p < len(data):
        l = int.from_bytes(data[p:p+nl], 'big'); p += nl
        out += b'\0\0\0\1' + data[p:p+l]; p += l
    f = os.path.join(tmp, 'x%d.hevc' % iid); open(f, 'wb').write(out)
    png = os.path.join(tmp, 'x%d.png' % iid)
    r = subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', f, '-frames:v', '1', png], capture_output=True)
    if not os.path.exists(png): raise RuntimeError(r.stderr.decode()[:300])
    return Image.open(png).convert('RGB')

def convert(path, outp, maxdim=2000):
    d = open(path, 'rb').read(); info = parse(d)
    pid = info['pitm']; tmp = tempfile.mkdtemp()
    if info['items'][pid] == 'grid':
        ext = info['loc'][pid]; base = info['idat'][0] if info['cm'][pid] == 1 else 0; g = b''.join(d[base+o:base+o+l] for o, l in ext)
        rows, cols = g[2] + 1, g[3] + 1
        if g[1] & 1: W, H = struct.unpack('>II', g[4:12])
        else: W, H = struct.unpack('>HH', g[4:8])
        tiles = info['dimg'][pid]
        imgs = [decode_tile(d, info, t, tmp) for t in tiles]
        tw, th = imgs[0].size
        canvas = Image.new('RGB', (tw*cols, th*rows))
        for i, im in enumerate(imgs): canvas.paste(im, ((i % cols)*tw, (i//cols)*th))
        img = canvas.crop((0, 0, W, H))
    else:
        img = decode_tile(d, info, pid, tmp)
    # rotation
    for i in info['assoc'].get(pid, []):
        t, x = info['props'][i-1]
        if t == 'irot':
            a = x[0] & 3
            if a: img = img.rotate(90*a, expand=True)
    img.thumbnail((maxdim, maxdim)); img.save(outp, quality=88)

if __name__ == '__main__':
    convert(sys.argv[1], sys.argv[2])
