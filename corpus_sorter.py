#!/usr/bin/env python3
"""
corpus_sorter.py  -- jalankan di Host A (Windows 10), Python 3.9+

Menyusun corpus pengujian dari folder mentah (GovDocs1 + dokumen besar tambahan)
menjadi dua profil lalu lintas, ditambah folder malware. Ambang ukuran dapat
diatur dari command line agar terkalibrasi dengan distribusi nyata corpus.

Tipe yang relevan dengan Threat Emulation/Extraction: PDF, Office, ZIP, EXE.
File tipe lain diabaikan (tidak diemulasi).

DUA MODE:
  1) Mode statistik (lihat sebaran ukuran dulu, tidak menyalin apa pun):
       python corpus_sorter.py --raw C:\\corpus_raw --stats
  2) Mode susun corpus:
       python corpus_sorter.py --raw C:\\corpus_raw --malware C:\\corpus_raw_malware --out C:\\corpus
       (opsional ambang) --small-max-kb 100 --large-min-mb 5

Ambang ukuran:
  small  : < small-max-kb (default 100 KB)
  medium : antara small-max-kb dan large-min-mb
  large  : >= large-min-mb (default 5 MB)
"""
import argparse
import os
import random
import shutil
from collections import defaultdict

random.seed(42)  # reprodusibel

TYPE_MAP = {
    "pdf":    {"pdf"},
    "office": {"doc", "docx", "xls", "xlsx", "ppt", "pptx", "rtf", "csv"},
    "zip":    {"zip", "rar", "7z", "gz", "tar"},
    "exe":    {"exe", "dll", "msi"},
}

# Target distribusi per profil. EXE diset 0 secara default karena GovDocs1
# umumnya tidak memuat executable; ZIP menutup porsi tersebut. Sesuaikan bila
# tersedia sumber EXE benign.
PROFILES = {
    "mixed_office": {
        "type_ratio": {"pdf": 0.45, "office": 0.35, "zip": 0.20, "exe": 0.0},
        "size_ratio": {"small": 0.70, "medium": 0.25, "large": 0.05},
        "total": 500,
    },
    "file_heavy": {
        "type_ratio": {"pdf": 0.45, "office": 0.35, "zip": 0.20, "exe": 0.0},
        "size_ratio": {"small": 0.20, "medium": 0.50, "large": 0.30},
        "total": 500,
    },
}


def file_type(path):
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    for t, exts in TYPE_MAP.items():
        if ext in exts:
            return t
    return "other"


def size_class(path, small_max, large_min):
    try:
        sz = os.path.getsize(path)
    except OSError:
        return None
    if sz < small_max:
        return "small"
    if sz < large_min:
        return "medium"
    return "large"


def index_raw(raw_dir, small_max, large_min):
    buckets = defaultdict(list)
    for root, _, names in os.walk(raw_dir):
        for n in names:
            p = os.path.join(root, n)
            t = file_type(p)
            if t == "other":
                continue
            try:
                if os.path.getsize(p) == 0:
                    continue
            except OSError:
                continue
            s = size_class(p, small_max, large_min)
            if s is None:
                continue
            buckets[(t, s)].append(p)
    for k in buckets:
        random.shuffle(buckets[k])
    return buckets


def print_stats(raw_dir):
    """Histogram ukuran terperinci untuk membantu memilih ambang."""
    bins = [
        ("<100KB", 0, 100 * 1024),
        ("100KB-500KB", 100 * 1024, 500 * 1024),
        ("500KB-1MB", 500 * 1024, 1024 * 1024),
        ("1-3MB", 1024 * 1024, 3 * 1024 * 1024),
        ("3-5MB", 3 * 1024 * 1024, 5 * 1024 * 1024),
        ("5-10MB", 5 * 1024 * 1024, 10 * 1024 * 1024),
        (">10MB", 10 * 1024 * 1024, float("inf")),
    ]
    counts = defaultdict(int)
    by_type = defaultdict(lambda: defaultdict(int))
    total = 0
    for root, _, names in os.walk(raw_dir):
        for n in names:
            p = os.path.join(root, n)
            t = file_type(p)
            if t == "other":
                continue
            try:
                sz = os.path.getsize(p)
            except OSError:
                continue
            if sz == 0:
                continue
            total += 1
            for label, lo, hi in bins:
                if lo <= sz < hi:
                    counts[label] += 1
                    by_type[t][label] += 1
                    break
    print(f"\nTotal file tipe relevan: {total}\n")
    print(f"{'Rentang ukuran':<14} {'Jumlah':>8}   (pdf / office / zip / exe)")
    print("-" * 60)
    cum_from_top = 0
    for label, _, _ in reversed(bins):
        cum_from_top += counts[label]
    running = 0
    for label, _, _ in bins:
        running += counts[label]
        bt = by_type
        detail = f"{bt['pdf'][label]} / {bt['office'][label]} / {bt['zip'][label]} / {bt['exe'][label]}"
        print(f"{label:<14} {counts[label]:>8}   {detail}")
    print("-" * 60)
    # Kumulatif "file besar" untuk berbagai ambang
    print("\nJumlah file pada/di atas ambang (calon 'large'):")
    for thr_label, thr in [(">=1MB", 1), (">=3MB", 3), (">=5MB", 5), (">=10MB", 10)]:
        c = 0
        for root, _, names in os.walk(raw_dir):
            for n in names:
                p = os.path.join(root, n)
                if file_type(p) == "other":
                    continue
                try:
                    if os.path.getsize(p) >= thr * 1024 * 1024:
                        c += 1
                except OSError:
                    pass
        print(f"  {thr_label:<8}: {c} file")
    print("\nPanduan: pilih --large-min-mb sehingga jumlah 'large' >= ~150 "
          "agar file_heavy (target 30% large dari 500) terpenuhi tanpa fallback.")


def pick(buckets, used, t, s, n):
    out = []
    for p in buckets.get((t, s), []):
        if len(out) >= n:
            break
        if p in used:
            continue
        out.append(p)
        used.add(p)
    return out


def build_profile(name, cfg, buckets, used, out_root):
    target = cfg["total"]
    dst = os.path.join(out_root, name)
    os.makedirs(dst, exist_ok=True)
    chosen = []
    for t, tr in cfg["type_ratio"].items():
        if tr <= 0:
            continue
        for s, sr in cfg["size_ratio"].items():
            n = round(target * tr * sr)
            chosen.extend(pick(buckets, used, t, s, n))
    if len(chosen) < target:
        for (t, s), pool in buckets.items():
            for p in pool:
                if len(chosen) >= target:
                    break
                if p in used:
                    continue
                chosen.append(p)
                used.add(p)
    counts = defaultdict(int)
    for i, src in enumerate(chosen):
        ext = os.path.splitext(src)[1].lower()
        fn = f"{name}_{i:04d}{ext}"
        try:
            shutil.copy2(src, os.path.join(dst, fn))
            t = file_type(src)
            counts[t] += 1
        except OSError as e:
            print(f"  gagal menyalin {src}: {e}")
    return len(chosen), counts


def copy_malware(mal_dir, out_root):
    dst = os.path.join(out_root, "malware")
    os.makedirs(dst, exist_ok=True)
    n = 0
    if mal_dir and os.path.isdir(mal_dir):
        for root, _, names in os.walk(mal_dir):
            for nm in names:
                try:
                    shutil.copy2(os.path.join(root, nm), os.path.join(dst, nm))
                    n += 1
                except OSError as e:
                    print(f"  gagal menyalin malware {nm}: {e}")
    return n


def main():
    ap = argparse.ArgumentParser(description="Penyusun corpus pengujian ATP")
    ap.add_argument("--raw", required=True, help="folder file benign mentah")
    ap.add_argument("--malware", default=None, help="folder malware/EICAR (opsional)")
    ap.add_argument("--out", default=None, help="folder output corpus")
    ap.add_argument("--small-max-kb", type=float, default=100, help="ambang small (KB), default 100")
    ap.add_argument("--large-min-mb", type=float, default=5, help="ambang large (MB), default 5")
    ap.add_argument("--stats", action="store_true", help="hanya tampilkan histogram ukuran lalu keluar")
    args = ap.parse_args()

    if args.stats:
        print("Memindai untuk statistik ukuran:", args.raw)
        print_stats(args.raw)
        return

    if not args.out:
        print("ERROR: --out wajib pada mode susun corpus (atau gunakan --stats).")
        return

    small_max = int(args.small_max_kb * 1024)
    large_min = int(args.large_min_mb * 1024 * 1024)
    print(f"Ambang: small < {args.small_max_kb} KB, "
          f"medium < {args.large_min_mb} MB, large >= {args.large_min_mb} MB")
    print("Mengindeks corpus mentah:", args.raw)
    buckets = index_raw(args.raw, small_max, large_min)
    if not buckets:
        print("Tidak ada file tipe relevan ditemukan. Periksa folder --raw.")
        return
    print("Komposisi tersedia (tipe, ukuran) -> jumlah:")
    for k in sorted(buckets):
        print(f"  {k}: {len(buckets[k])}")

    for name, cfg in PROFILES.items():
        used = set()  # tiap profil menyusun dari pool penuh
        total, counts = build_profile(name, cfg, buckets, used, args.out)
        print(f"\n[{name}] tersusun {total} file (per tipe): {dict(counts)}")

    nm = copy_malware(args.malware, args.out)
    print(f"\n[malware] {nm} file disalin")
    print("\nCorpus READY di:", args.out)


if __name__ == "__main__":
    main()
