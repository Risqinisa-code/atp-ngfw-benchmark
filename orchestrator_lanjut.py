#!/usr/bin/env python3
"""
orchestrator_lanjut.py  -- versi LANJUTAN dari orchestrator.py

Gunakan bila eksperimen Tahap 1 perlu dilanjutkan dari blok ATP tertentu
(misalnya blok Baseline sudah selesai dan valid, tetapi blok TEX terlanjur
berjalan dengan profil yang salah sehingga harus diulang).

Perilaku:
  - START_FROM menentukan blok ATP awal; blok sebelum itu tidak dijalankan.
  - PURGE_BLOCKS: blok yang datanya dianggap rusak akan DIBERSIHKAN
    (hapus CSV sender_/monitor_/warmup + hapus dari _progress.json) sebelum
    dijalankan ulang, sehingga run-nya benar-benar diulang dengan profil benar.
  - Blok lain tetap menghormati _progress.json (run yang sudah valid dilewati).

EDIT bagian KONFIG sesuai kebutuhan, lalu jalankan dari folder yang berisi
orchestrator_lanjut.py + file_sender.py + monitor_dut.py:
    python orchestrator_lanjut.py
"""
import itertools
import json
import os
import subprocess
import sys
import time

# ---------------- KONFIG ----------------
PY = sys.executable
SERVER = "http://10.0.10.105:8080/upload"
CORPUS = {
    "mixed_office": r"C:\corpus\mixed_office",
    "file_heavy":   r"C:\corpus\file_heavy",
}
DUT_HOST = "10.0.7.103"
DUT_USER = "admin"
DUT_PASS = "CHANGE_ME"
OUTDIR = r"C:\hasil"
WARMUP = 60
SUSTAIN = 300
COOLDOWN = 60
REPS = 3
LOAD_CONC = {"rendah": 12, "sedang": 24, "tinggi": 40}

ALL_ATP = ["Baseline", "TEX", "TE", "TE_TEX"]
PROFILES = ["mixed_office", "file_heavy"]
LOADS = ["rendah", "sedang", "tinggi"]

# ---- pengaturan lanjutan ----
START_FROM = "TEX"            # blok awal yang dijalankan (Baseline dilewati)
PURGE_BLOCKS = ["TEX"]        # blok yang datanya dibersihkan & diulang total
# ----------------------------------------

os.makedirs(OUTDIR, exist_ok=True)
progress_path = os.path.join(OUTDIR, "_progress.json")
done = set(json.load(open(progress_path))) if os.path.exists(progress_path) else set()


def save_progress():
    json.dump(sorted(done), open(progress_path, "w"), indent=2)


def purge_block(atp):
    """Hapus CSV dan entri progress untuk seluruh run pada blok ATP tertentu."""
    removed_files = 0
    removed_tags = 0
    for profil, load in itertools.product(PROFILES, LOADS):
        for rep in range(1, REPS + 1):
            tag = f"{atp}__{profil}__{load}__r{rep}"
            for prefix in ("sender_", "monitor_", "monitorraw_", "_warmup_"):
                ext = ".txt" if prefix == "monitorraw_" else ".csv"
                fp = os.path.join(OUTDIR, f"{prefix}{tag}{ext}")
                if os.path.exists(fp):
                    try:
                        os.remove(fp)
                        removed_files += 1
                    except OSError:
                        pass
            if tag in done:
                done.discard(tag)
                removed_tags += 1
    save_progress()
    print(f"  Dibersihkan blok {atp}: {removed_files} berkas, {removed_tags} entri progress dihapus.")


def run_one(atp, profil, load, rep):
    tag = f"{atp}__{profil}__{load}__r{rep}"
    if tag in done:
        print("SKIP (sudah ada):", tag)
        return
    print("\n" + "=" * 60)
    print("RUN:", tag)
    conc = LOAD_CONC[load]
    sender_out = os.path.join(OUTDIR, f"sender_{tag}.csv")
    monitor_out = os.path.join(OUTDIR, f"monitor_{tag}.csv")
    monitor_raw = os.path.join(OUTDIR, f"monitorraw_{tag}.txt")

    print(f"  Warm-up {WARMUP}s...")
    wu = subprocess.Popen([PY, "file_sender.py", "--server", SERVER,
                           "--corpus", CORPUS[profil], "--concurrency", str(max(2, conc // 3)),
                           "--duration", str(WARMUP),
                           "--out", os.path.join(OUTDIR, f"_warmup_{tag}.csv")])
    wu.wait()

    print(f"  Sustain {SUSTAIN}s (concurrency {conc})...")
    mon = subprocess.Popen([PY, "monitor_dut.py", "--host", DUT_HOST,
                            "--user", DUT_USER, "--password", DUT_PASS,
                            "--interval", "3", "--duration", str(SUSTAIN),
                            "--out", monitor_out, "--rawlog", monitor_raw])
    snd = subprocess.Popen([PY, "file_sender.py", "--server", SERVER,
                            "--corpus", CORPUS[profil], "--concurrency", str(conc),
                            "--duration", str(SUSTAIN), "--out", sender_out])
    snd.wait()
    mon.wait()

    print(f"  Cooldown {COOLDOWN}s...")
    time.sleep(COOLDOWN)
    done.add(tag)
    save_progress()
    print("  selesai:", tag)


def main():
    start_idx = ALL_ATP.index(START_FROM)
    blocks = ALL_ATP[start_idx:]
    print("Blok yang akan dijalankan:", blocks)
    print("Blok yang dilewati (dianggap selesai & valid):", ALL_ATP[:start_idx])

    # Bersihkan blok yang rusak lebih dulu, agar benar-benar diulang.
    for atp in PURGE_BLOCKS:
        if atp in blocks:
            print(f"\nMembersihkan blok {atp} (data lama dianggap rusak)...")
            purge_block(atp)

    for atp in blocks:
        print("\n" + "#" * 60)
        print(f"# BLOK ATP = {atp}")
        print(f"# 1) Di SmartConsole, set Action rule Threat Prevention ke profil: TP_{atp}")
        print(f"# 2) Install Policy (Threat Prevention).")
        print(f"# 3) PASTIKAN profil benar-benar TP_{atp} sebelum lanjut.")
        input(f"# Tekan ENTER HANYA setelah profil TP_{atp} aktif dan policy ter-install...")
        for profil, load in itertools.product(PROFILES, LOADS):
            for rep in range(1, REPS + 1):
                run_one(atp, profil, load, rep)

    print("\nSELESAI. Verifikasi jumlah berkas di OUTDIR sebelum analisis.")


if __name__ == "__main__":
    main()
