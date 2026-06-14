#!/usr/bin/env python3
"""
run_block.py  -- menjalankan SATU blok ATP saja, aman untuk diulang.

PERBEDAAN PENTING dari orchestrator sebelumnya:
  - TIDAK PERNAH menghapus data apa pun.
  - Hanya menjalankan blok ATP yang kamu sebut di argumen. Tidak auto-lompat
    ke blok lain, sehingga Ctrl+C lalu jalankan lagi tetap aman.
  - Run yang sudah selesai (tercatat di _progress.json) otomatis DILEWATI.
    Jadi bila terputus, cukup jalankan perintah yang sama: ia melanjutkan.
  - Run yang terputus di tengah (belum selesai) akan diulang dan berkasnya
    ditimpa otomatis.

Cara pakai (jalankan dari folder berisi run_block.py + file_sender.py + monitor_dut.py):
    python run_block.py TEX
    python run_block.py TE
    python run_block.py TE_TEX
    python run_block.py Baseline

Sebelum menjalankan satu blok, set profil TP_<blok> di SmartConsole + Install Policy.
"""
import itertools
import json
import os
import subprocess
import sys
import time

# ---------------- KONFIG (samakan dengan setup) ----------------
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
PROFILES = ["mixed_office", "file_heavy"]
LOADS = ["rendah", "sedang", "tinggi"]
VALID_ATP = ["Baseline", "TEX", "TE", "TE_TEX"]
# ----------------------------------------------------------------

os.makedirs(OUTDIR, exist_ok=True)
progress_path = os.path.join(OUTDIR, "_progress.json")
done = set(json.load(open(progress_path))) if os.path.exists(progress_path) else set()


def save_progress():
    json.dump(sorted(done), open(progress_path, "w"), indent=2)


def run_one(atp, profil, load, rep):
    tag = f"{atp}__{profil}__{load}__r{rep}"
    if tag in done:
        print("SKIP (sudah selesai):", tag)
        return
    print("\n" + "=" * 60)
    print("RUN:", tag)
    conc = LOAD_CONC[load]
    sender_out = os.path.join(OUTDIR, f"sender_{tag}.csv")
    monitor_out = os.path.join(OUTDIR, f"monitor_{tag}.csv")
    monitor_raw = os.path.join(OUTDIR, f"monitorraw_{tag}.txt")

    print(f"  Warm-up {WARMUP}s...")
    subprocess.Popen([PY, "file_sender.py", "--server", SERVER,
                      "--corpus", CORPUS[profil], "--concurrency", str(max(2, conc // 3)),
                      "--duration", str(WARMUP),
                      "--out", os.path.join(OUTDIR, f"_warmup_{tag}.csv")]).wait()

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
    if len(sys.argv) < 2 or sys.argv[1] not in VALID_ATP:
        print("Gunakan: python run_block.py <Baseline|TEX|TE|TE_TEX>")
        sys.exit(1)
    atp = sys.argv[1]

    all_runs = [(p, l, r) for p, l in itertools.product(PROFILES, LOADS) for r in range(1, REPS + 1)]
    todo = [(p, l, r) for (p, l, r) in all_runs if f"{atp}__{p}__{l}__r{r}" not in done]

    print("=" * 60)
    print(f"BLOK ATP = {atp}")
    print(f"Total run blok ini: {len(all_runs)} | sudah selesai: {len(all_runs)-len(todo)} | "
          f"akan dijalankan: {len(todo)}")
    print("Script ini TIDAK menghapus data apa pun. Run selesai akan dilewati.")
    if not todo:
        print("\nSemua run pada blok ini sudah selesai. Tidak ada yang dijalankan.")
        return
    print("\nDaftar run yang akan dijalankan:")
    for (p, l, r) in todo:
        print(f"  - {atp}__{p}__{l}__r{r}")
    print(f"\nPASTIKAN profil TP_{atp} sudah aktif dan policy ter-install di SmartConsole.")
    input(f"Tekan ENTER setelah profil TP_{atp} benar-benar aktif (atau Ctrl+C untuk batal)...")

    for (p, l, r) in todo:
        run_one(atp, p, l, r)
    print(f"\nBLOK {atp} SELESAI. Jalankan 'python cek_status.py' untuk verifikasi.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nDihentikan oleh pengguna (Ctrl+C). Progres yang sudah selesai TERSIMPAN.")
        print("Untuk melanjutkan, jalankan lagi perintah yang sama; run yang sudah selesai akan dilewati.")
