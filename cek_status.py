#!/usr/bin/env python3
"""
cek_status.py  -- menampilkan kondisi sebenarnya data eksperimen di OUTDIR.

Untuk tiap blok ATP, menampilkan:
  - jumlah run yang tercatat selesai di _progress.json
  - jumlah berkas sender_/monitor_ yang benar-benar ada dan berisi data
  - peringatan bila ada ketidakcocokan (tercatat selesai tapi berkas hilang,
    atau berkas ada tapi tidak tercatat).

Jalankan: python cek_status.py
Tidak mengubah atau menghapus apa pun (hanya membaca).
"""
import csv
import itertools
import json
import os

OUTDIR = r"C:\hasil"
REPS = 3
PROFILES = ["mixed_office", "file_heavy"]
LOADS = ["rendah", "sedang", "tinggi"]
ATP_LIST = ["Baseline", "TEX", "TE", "TE_TEX"]


def rows_in_csv(path):
    try:
        with open(path, newline="") as f:
            return max(0, sum(1 for _ in csv.reader(f)) - 1)  # tanpa header
    except OSError:
        return -1  # tidak ada


def main():
    progress_path = os.path.join(OUTDIR, "_progress.json")
    done = set(json.load(open(progress_path))) if os.path.exists(progress_path) else set()

    print("=" * 70)
    print(f"STATUS EKSPERIMEN  |  OUTDIR = {OUTDIR}")
    print(f"_progress.json: {len(done)} run tercatat selesai")
    print("=" * 70)

    grand_ok = 0
    for atp in ATP_LIST:
        done_cnt = 0
        file_ok = 0
        warns = []
        for p, l in itertools.product(PROFILES, LOADS):
            for r in range(1, REPS + 1):
                tag = f"{atp}__{p}__{l}__r{r}"
                in_prog = tag in done
                s_rows = rows_in_csv(os.path.join(OUTDIR, f"sender_{tag}.csv"))
                m_rows = rows_in_csv(os.path.join(OUTDIR, f"monitor_{tag}.csv"))
                if in_prog:
                    done_cnt += 1
                has_data = s_rows > 0 and m_rows > 0
                if has_data:
                    file_ok += 1
                if in_prog and not has_data:
                    warns.append(f"  ! {tag}: tercatat selesai TAPI berkas hilang/kosong "
                                 f"(sender_rows={s_rows}, monitor_rows={m_rows})")
                if has_data and not in_prog:
                    warns.append(f"  ! {tag}: berkas ADA TAPI tidak tercatat di progress")
        total = len(PROFILES) * len(LOADS) * REPS
        status = "LENGKAP" if (done_cnt == total and file_ok == total) else "belum lengkap"
        print(f"\nBlok {atp:<8} : selesai(progress)={done_cnt}/{total}  "
              f"berkas-berisi-data={file_ok}/{total}  -> {status}")
        for w in warns:
            print(w)
        grand_ok += file_ok

    print("\n" + "=" * 70)
    print(f"TOTAL berkas valid berisi data: {grand_ok}/{len(ATP_LIST)*len(PROFILES)*len(LOADS)*REPS}")
    print("Catatan: angka 'berkas-berisi-data' adalah ukuran paling tepercaya.")
    print("=" * 70)


if __name__ == "__main__":
    main()
