# 측정용 코드입니다. 투자 판단의 근거로 쓰는 것은 직접 확인하신 뒤, 자신의 책임하에 진행하셔야 합니다.
# 김쿤 9편 측정 코드 공개판 — 원본에서 바꾼 곳은 README.md '원본과 다른 점'.
"""뉴스 제목 특징 만들기 — 원본 scripts/news_prepost_rules.py 에서 4단계 기준선(낱말 규칙)에 쓰는 부분만 옮겼다.

옮긴 것: load_names(파일 위치만 바꿈 · 선택 파일은 없으면 건너뜀) · Masker · show · 특징 정규식 · bucket_edges · build_features · ftype · to_X.
build_features 는 형태소 분석에 kiwipiepy 를 쓰고, 기사 줄마다 붙은 종목 코드 목록을 data/news/lines/<날짜>.csv(srno, codes) 에서 읽는다
(원본 위치는 증권사 뉴스 API 로 받은 하루치 파일 폴더 — 이름만 바꿈). 가격 값은 특징에 쓰지 않는다.
"""
from __future__ import annotations

import csv
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict

import numpy as np
import pandas as pd
import scipy.sparse as sp

from ep09_paths import DATA

NEWS = DATA / "news" / "lines"
SPLIT = re.compile(r"[|,;\s]+")
KEEP_TAGS = {"NNG", "NNP", "VV", "VA", "XR", "SL", "SH", "MAG"}   # 형태소 특징에 쓰는 품사(내가 정함)


def load_names():
    """종목 코드 → 이름 집합(가리기용). 원본은 세 파일을 모두 읽었다. 공개판은 없는 파일을 건너뛴다(셋 다 있으면 원본과 같다).
    data/daily/_universe_20261104.csv(code,name — 필수) · data/dart/corpCode.zip(OpenDART 고유번호 파일, 선택) · data/dart/listed_corps.json(선택, {"by_name": {이름: 코드}})"""
    code2 = defaultdict(set)
    u = pd.read_csv(DATA / "daily" / "_universe_20261104.csv", dtype=str)
    for c, n in zip(u.code, u.name):
        if isinstance(n, str) and n.strip():
            code2[c].add(n.strip())
    cz = DATA / "dart" / "corpCode.zip"
    if cz.exists():
        with zipfile.ZipFile(cz) as z:
            root = ET.fromstring(z.read("CORPCODE.xml"))
        for e in root.iter("list"):
            sc = (e.findtext("stock_code") or "").strip()
            nm = (e.findtext("corp_name") or "").strip()
            if len(sc) == 6 and nm:
                code2[sc].add(nm)
    lj = DATA / "dart" / "listed_corps.json"
    if lj.exists():
        d = json.loads(lj.read_text(encoding="utf-8"))
        for nm, c in d.get("by_name", {}).items():
            if nm.strip():
                code2[c].add(nm.strip())
    return code2


class Masker:
    """제목 → (종목 가림 판, 종목·숫자 가림 판). 가림 글자: \\x01 = <종목>, \\x02 = <수>."""

    def __init__(self, code2):
        self.code2 = code2
        self.codes = set(code2)
        names = {n for s in code2.values() for n in s if len(n) >= 3}   # 기사 줄 밖 종목 이름은 3글자 이상만(내가 정함)
        self.pre = defaultdict(list)
        for n in names:
            self.pre[n[:2]].append(n)
        for k in self.pre:
            self.pre[k].sort(key=lambda s: (-len(s), s))

    @staticmethod
    def _ascii_ok(s, i, n):
        if n[0].isascii() and n[0].isalnum() and i > 0 and s[i - 1].isascii() and s[i - 1].isalnum():
            return False
        j = i + len(n)
        if n[-1].isascii() and n[-1].isalnum() and j < len(s) and s[j].isascii() and s[j].isalnum():
            return False
        return True

    def mask(self, title, line_codes):
        s = title
        # ① 그 기사 줄에 붙은 종목 이름(길이 무관, 긴 것부터)
        lnames = sorted({n for c in line_codes for n in self.code2.get(c, ()) if len(n) >= 2}, key=lambda x: (-len(x), x))
        for n in lnames:
            if n in s:
                s = s.replace(n, "\x01")
        # ② 6자리 종목 코드(괄호 안 또는 그 줄의 코드)
        s = re.sub(r"\(\s*(\d{6})\s*\)", lambda m: "(\x01)" if m.group(1) in self.codes else m.group(0), s)
        for c in line_codes:
            if c.isdigit():
                s = re.sub(rf"(?<!\d){c}(?!\d)", "\x01", s)
        # ③ 그 밖의 종목 이름(3글자 이상, 긴 것부터)
        out, i, L = [], 0, len(s)
        while i < L:
            hit = None
            for n in self.pre.get(s[i:i + 2], ()):
                if s.startswith(n, i) and self._ascii_ok(s, i, n):
                    hit = n
                    break
            if hit:
                out.append("\x01")
                i += len(hit)
            else:
                out.append(s[i])
                i += 1
        s = "".join(out)
        s = re.sub(r"\x01\s*\(\s*\x01\s*\)", "\x01", s)
        s = re.sub(r"\x01+", "\x01", s)
        full = re.sub(r"\d+(?:[.,]\d+)*", "\x02", s)
        return s, full


def show(s):
    return s.replace("\x01", "<종목>").replace("\x02", "<수>")


# ======================================================================
# 2. 특징 만들기(가격 값 쓰지 않음)
# ======================================================================
TOK = re.compile(r"[\x01\x02A-Za-z0-9가-힣ㄱ-ㅣ一-鿿]+")
OPEN_B, CLOSE_B = "[【〔<〈《(", "]】〕>〉》)"
FRONT = re.compile(r"^\s*([\[【〔<〈《(])\s*([^\[\]【】〔〕<>〈〉《》()]{1,25}?)\s*([\]】〕>〉》)])")
BACK = re.compile(r"([\[【〔<〈《(])\s*([^\[\]【】〔〕<>〈〉《》()]{1,25}?)\s*([\]】〕>〉》)])\s*$")
FLAGS = [
    ("숫자 있음", re.compile(r"\d")), ("% 있음", re.compile(r"[%％]")), ("오름 화살표(↑▲△)", re.compile(r"[↑▲△⬆]")),
    ("내림 화살표(↓▼▽)", re.compile(r"[↓▼▽⬇]")), ("다른 화살표(→←⇒)", re.compile(r"[→←⇒➡]")),
    ("물음표", re.compile(r"[?？]")), ("느낌표", re.compile(r"[!！]")), ("큰따옴표", re.compile(r"[\"“”]")),
    ("작은따옴표", re.compile(r"['‘’]")), ("말줄임(…)", re.compile(r"…|\.\.\.|‥")), ("가운뎃점(·)", re.compile(r"[·ㆍ]")),
    ("+숫자", re.compile(r"\+\s?\d")), ("−숫자", re.compile(r"(?:^|[\s(\[])[-−–]\s?\d")),
    ("한자 있음", re.compile(r"[一-鿿]")), ("영문 있음", re.compile(r"[A-Za-z]")),
]


def bucket_edges(x, q=(0.2, 0.4, 0.6, 0.8)):
    return list(np.nanquantile(x, q))


def build_features(ev, code2, front_mask):
    """줄마다 특징 문자열 목록. 경계는 앞 절반(front_mask) 분포로만 정한다."""
    from kiwipiepy import Kiwi
    print("[특징] 줄별 종목 코드 목록 읽기", flush=True)
    line_codes = {}
    for d in sorted(ev.day.unique()):
        p = NEWS / f"{d}.csv"
        with p.open(encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                cs = [c for c in SPLIT.split((r.get("codes") or "").strip()) if c]
                k = (d, r["srno"])
                if k in line_codes:
                    line_codes[k] = sorted(set(line_codes[k]) | set(cs))
                else:
                    line_codes[k] = cs
    mk = Masker(code2)
    print("[특징] 제목 가리기", flush=True)
    sm, fm, ncodes = [], [], []
    cache = {}
    for d, s, c, t in zip(ev.day, ev.srno, ev.code, ev.title):
        lc = line_codes.get((d, s), [])
        lcs = tuple(sorted(set(lc) | {c}))
        key = (t, lcs)
        if key not in cache:
            cache[key] = mk.mask(t, lcs)
        a, b = cache[key]
        sm.append(a)
        fm.append(b)
        ncodes.append(len(lcs))
    ev["t_stock"] = sm
    ev["t_full"] = fm
    ev["n_codes"] = ncodes
    print("[특징] 형태소(kiwipiepy)", flush=True)
    kiwi = Kiwi(num_workers=8)
    uniq = sorted(set(fm))
    texts = [u.replace("\x01", " ").replace("\x02", " 0 ") for u in uniq]
    morph = {}
    for u, toks in zip(uniq, kiwi.tokenize(texts)):
        morph[u] = sorted({f"{(x.form.lower() if x.tag == 'SL' else x.form)}/{x.tag}" for x in toks if x.tag in KEEP_TAGS})
    # 경계(앞 절반)
    tlen = ev.title.str.len().values
    le = [int(round(v)) for v in bucket_edges(tlen[front_mask])]
    tv = ev.tv20.values.astype(float)
    te = [float(round(v / 1e8, 2)) for v in bucket_edges(tv[front_mask])]   # 억 원, 소수 둘째 자리로 고정(내가 정함)
    print(f"[특징] 제목 길이 경계(앞 절반) {le} · 거래대금 경계(억, 앞 절반) {te}", flush=True)

    def len_lab(x):
        edges = le
        if x < edges[0]:
            return f"제목 길이:{edges[0] - 1}자 이하"
        for a, b in zip(edges[:-1], edges[1:]):
            if a <= x < b:
                return f"제목 길이:{a}~{b - 1}자"
        return f"제목 길이:{edges[-1]}자 이상"

    def tv_lab(x):
        if not np.isfinite(x):
            return "거래대금:없음(일봉 없음)"
        e = [v * 1e8 for v in te]
        if x < e[0]:
            return f"거래대금:{te[0]:.2f}억 미만"
        for a, b, la, lb in zip(e[:-1], e[1:], te[:-1], te[1:]):
            if a <= x < b:
                return f"거래대금:{la:.2f}억 이상 {lb:.2f}억 미만"
        return f"거래대금:{te[-1]:.2f}억 이상"

    def nc_lab(n):
        return "종목 수:" + ("1" if n == 1 else "2" if n == 2 else "3~5" if n <= 5 else "6~20" if n <= 20 else "21 이상")

    def pr_lab(n):
        return "그날 앞선 기사:" + ("0(그날 첫 기사)" if n == 0 else "1" if n == 1 else "2" if n == 2 else "3~5" if n <= 5 else "6 이상")

    def band(m):
        h = m // 60
        return "시간대:" + ("09:06~09:59" if h == 9 else f"{h:02d}시대" if h < 14 else "14:00~15:00")

    print("[특징] 줄별 특징 목록", flush=True)
    feats = []
    for t, s_, f_, nc, dorg, kind, typ, bd, m, tvv in zip(ev.title, ev.t_stock, ev.t_full, ev.n_codes, ev.dorg, ev.kind, ev.type,
                                                         ev.before_day, ev.m, tv):
        fs = set()
        toks = [show(x).lower() for x in TOK.findall(f_)]
        fs.update("낱말:" + x for x in toks)
        fs.update(f"두 낱말:{a} {b}" for a, b in zip(toks[:-1], toks[1:]))
        fs.update("형태소:" + x for x in morph[f_])
        mm = FRONT.match(f_)
        if mm:
            inner = re.sub(r"\s+", " ", show(mm.group(2)).strip())
            fs.add(f"앞 꼬리표:{mm.group(1)}{inner}{mm.group(3)}")
            fs.add("앞 꼬리표:있음(괄호로 시작)")
        else:
            fs.add("앞 꼬리표:없음")
        mb = BACK.search(f_)
        if mb and not (mm and mm.start() == mb.start()):
            inner = re.sub(r"\s+", " ", show(mb.group(2)).strip())
            fs.add(f"끝 꼬리표:{mb.group(1)}{inner}{mb.group(3)}")
            fs.add("끝 꼬리표:있음(괄호로 끝남)")
        for nm, rx in FLAGS:
            fs.add(f"표시:{nm}" if rx.search(s_) else f"표시:{nm} 없음")
        fs.add(len_lab(len(t)))
        fs.add(nc_lab(nc))
        k = s_.count("\x01")
        fs.add("제목 속 종목 이름 수:" + ("0" if k == 0 else "1" if k == 1 else "2 이상"))
        fs.add(f"공급사:{dorg}")
        fs.add(band(int(m)))
        fs.add(f"갈래 분류:{kind}")
        fs.add(f"제목 유형:{typ}")
        fs.add(pr_lab(int(bd)))
        fs.add(tv_lab(tvv))
        feats.append(fs)
    return feats, {"len_edges": le, "tv_edges_eok": te}


def ftype(f):
    return f.split(":", 1)[0]


def to_X(feats_rows, vocab):
    """줄별 특징 집합 → 특징 × 줄 희소 행렬(csr, 0/1)."""
    ix = {f: i for i, f in enumerate(vocab)}
    r, c = [], []
    for j, fs in enumerate(feats_rows):
        for f in fs:
            i = ix.get(f)
            if i is not None:
                r.append(i)
                c.append(j)
    return sp.csr_matrix((np.ones(len(r)), (r, c)), shape=(len(vocab), len(feats_rows)))
