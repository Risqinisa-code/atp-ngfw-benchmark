#!/usr/bin/env python3
"""
orchestrator.py  -- jalankan di Host A, Python 3.9+

Menjalankan matriks Tahap 1 (72 run) secara berurutan, dikelompokkan per BLOK
status ATP agar profil di SmartConsole cukup ditukar + Install Policy 4 kali.
Untuk tiap run: warm-up, lalu monitor_dut.py + file_sender.py paralel selama
sustain, lalu cooldown. CSV per run dinamai:
    sender_{ATP}__{profil}__{load}__r{rep}.csv
    monitor_{ATP}__{profil}__{load}__r{rep}.csv
Progress disimpan ke _progress.json sehingga bisa dilanjutkan bila terputus.

EDIT bagian KONFIG sebelum menjalankan (terutama DUT_PASS, OUTDIR, dan RATE
hasil calibrate_rate.py). Pastikan server_receiver.py jalan di Host B.
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
DUT_HOST = "10.0.7.103"              # SSH management reachable dari Host A (eth6)
DUT_USER = "admin"
DUT_PASS = "CHANGE_ME"                # password DUT (sesuai kalibrasi)
OUTDIR = r"C:\hasil"
WARMUP = 60                          # detik
SUSTAIN = 300                        # detik
COOLDOWN = 60                        # detik
REPS = 3
# Beban dikontrol via CONCURRENCY (jumlah upload/emulasi paralel yang dijaga).
# Hasil calibrate_rate.py: knee/saturasi pada concurrency ~40.
LOAD_CONC = {"rendah": 12, "sedang": 24, "tinggi": 40}

ATP = ["Baseline", "TEX", "TE", "TE_TEX"]       # urut; ganti profil tiap blok
PROFILES = ["mixed_office", "file_heavy"]
LOADS = ["rendah", "sedang", "tinggi"]
# ----------------------------------------

os.makedirs(OUTDIR, exist_ok=True)
progress_path = os.path.join(OUTDIR, "_progress.json")
done = set(json.load(open(progress_path))) if os.path.exists(progress_path) else set()


def save_progress():
    json.dump(sorted(done), open(progress_path, "w"), indent=2)


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
    for atp in ATP:
        print("\n" + "#" * 60)
        print(f"# BLOK ATP = {atp}")
        print(f"# 1) Di SmartConsole, set Action rule Threat Prevention ke profil: TP_{atp}")
        print(f"# 2) Install Policy (Threat Prevention).")
        input("# Tekan ENTER bila profil sudah aktif dan policy ter-install...")
        for profil, load in itertools.product(PROFILES, LOADS):
            for rep in range(1, REPS + 1):
                run_one(atp, profil, load, rep)
    print("\nSEMUA RUN TAHAP 1 SELESAI (72 run). Lanjutkan analisis lalu Tahap 2.")


if __name__ == "__main__":
    main()
