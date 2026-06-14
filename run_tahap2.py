#!/usr/bin/env python3
r"""
run_tahap2.py -- Tahap 2: pengukuran sebelum/sesudah strategi optimisasi pada kondisi worst case.

Kondisi worst case (TETAP untuk semua strategi):
  - Profil   : file_heavy  (C:\corpus\file_heavy)
  - Beban    : concurrency 40 (setara "tinggi")
  - ATP      : Threat Emulation + Threat Extraction (profil TP_TE_TEX), KECUALI bila
               strategi mengubah cakupan (lihat B dan D di Langkah_Tahap2.md)

Strategi (jalankan satu per satu, sebagai argumen):
  S0_before        -> kondisi worst case TANPA optimisasi (referensi "sebelum")
  A_ruleorder      -> rule base ordering
  B_profilescope   -> pembatasan cakupan Threat Prevention profile (tipe berkas berisiko)
  D_sizethreshold  -> pengaturan ambang ukuran berkas
  ABD_combined     -> kombinasi A + B + D

Sifat aman (sama seperti run_block.py):
  - TIDAK pernah menghapus data.
  - Hanya menjalankan strategi yang disebut; tidak auto-lanjut.
  - Run yang sudah selesai dilewati (restart-safe via _progress_tahap2.json).

Cara pakai (dari folder berisi run_tahap2.py + file_sender.py + monitor_dut.py):
    python run_tahap2.py S0_before
    python run_tahap2.py A_ruleorder
    python run_tahap2.py B_profilescope
    python run_tahap2.py D_sizethreshold
    python run_tahap2.py ABD_combined
"""
import json, os, subprocess, sys, time

# ---------------- KONFIG ----------------
PY = sys.executable
SERVER = "http://10.0.10.105:8080/upload"
CORPUS_FILEHEAVY = r"C:\corpus\file_heavy"
DUT_HOST = "10.0.7.103"; DUT_USER = "admin"; DUT_PASS = "CHANGE_ME"
OUTDIR = r"C:\hasil_tahap2"
WARMUP = 60; SUSTAIN = 300; COOLDOWN = 60
CONCURRENCY = 40            # worst case = beban tinggi
REPS = 3
STRATEGIES = ["S0_before", "A_ruleorder", "B_profilescope", "D_sizethreshold", "ABD_combined"]
# ----------------------------------------

os.makedirs(OUTDIR, exist_ok=True)
progress_path = os.path.join(OUTDIR, "_progress_tahap2.json")
done = set(json.load(open(progress_path))) if os.path.exists(progress_path) else set()
def save(): json.dump(sorted(done), open(progress_path, "w"), indent=2)

def run_one(strat, rep):
    tag = f"{strat}__r{rep}"
    if tag in done:
        print("SKIP (sudah selesai):", tag); return
    print("\n" + "=" * 60); print("RUN:", tag)
    sender_out = os.path.join(OUTDIR, f"sender_tahap2_{tag}.csv")
    monitor_out = os.path.join(OUTDIR, f"monitor_tahap2_{tag}.csv")
    monitor_raw = os.path.join(OUTDIR, f"monitorraw_tahap2_{tag}.txt")
    print(f"  Warm-up {WARMUP}s...")
    subprocess.Popen([PY,"file_sender.py","--server",SERVER,"--corpus",CORPUS_FILEHEAVY,
                      "--concurrency",str(max(2,CONCURRENCY//3)),"--duration",str(WARMUP),
                      "--out",os.path.join(OUTDIR,f"_warmup_tahap2_{tag}.csv")]).wait()
    print(f"  Sustain {SUSTAIN}s (concurrency {CONCURRENCY})...")
    mon = subprocess.Popen([PY,"monitor_dut.py","--host",DUT_HOST,"--user",DUT_USER,"--password",DUT_PASS,
                            "--interval","3","--duration",str(SUSTAIN),"--out",monitor_out,"--rawlog",monitor_raw])
    snd = subprocess.Popen([PY,"file_sender.py","--server",SERVER,"--corpus",CORPUS_FILEHEAVY,
                            "--concurrency",str(CONCURRENCY),"--duration",str(SUSTAIN),"--out",sender_out])
    snd.wait(); mon.wait()
    print(f"  Cooldown {COOLDOWN}s..."); time.sleep(COOLDOWN)
    done.add(tag); save(); print("  selesai:", tag)

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in STRATEGIES:
        print("Gunakan: python run_tahap2.py <" + " | ".join(STRATEGIES) + ">"); sys.exit(1)
    strat = sys.argv[1]
    todo = [r for r in range(1, REPS+1) if f"{strat}__r{r}" not in done]
    print("=" * 60)
    print(f"STRATEGI = {strat} | kondisi: file_heavy, concurrency {CONCURRENCY}")
    print(f"REPS total {REPS} | sudah selesai {REPS-len(todo)} | akan dijalankan {len(todo)}")
    print("Script TIDAK menghapus data apa pun.")
    if not todo:
        print("Semua ulangan strategi ini sudah selesai."); return
    print(f"\nPASTIKAN konfigurasi SmartConsole untuk strategi '{strat}' sudah diterapkan dan policy ter-install.")
    print("Lihat Langkah_Tahap2.md untuk detail konfigurasi tiap strategi.")
    input(f"Tekan ENTER setelah konfigurasi '{strat}' aktif (atau Ctrl+C untuk batal)...")
    for r in todo: run_one(strat, r)
    print(f"\nSTRATEGI {strat} SELESAI.")

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt:
        print("\n\nDihentikan (Ctrl+C). Progres yang selesai TERSIMPAN; jalankan lagi perintah yang sama untuk melanjutkan.")
