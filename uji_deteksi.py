#!/usr/bin/env python3
r"""
uji_deteksi.py -- Uji deteksi/sanitisasi singkat untuk Tahap 2.

Mengirim setiap berkas sampel (EICAR dan sampel uji) di folder corpus_raw_malware
SATU PER SATU melewati firewall ke server, lalu mencatat hasil yang teramati dari
sisi klien (terkirim / terblokir / error) beserta verdict latency tiap berkas.

PENTING -- batas kemampuan pengukuran ini (baca sebelum menafsirkan hasil):
  1. server_receiver.py hanya membuang data dan membalas ok, TIDAK menyimpan berkas.
     Maka SANITISASI Threat Extraction (berkas dibersihkan namun tetap dikirim)
     TIDAK terlihat dari sisi klien. Skrip ini hanya bisa melihat apakah pengiriman
     BERHASIL atau DIBLOKIR, bukan apakah konten dibersihkan.
  2. Bukti deteksi/sanitisasi yang SAHIH ada di SmartConsole:
       Logs & Monitor -> Logs -> filter Blade: Threat Emulation / Threat Extraction,
       Source: 10.0.7.105, pada rentang waktu uji.
     Ekspor log tersebut ke CSV untuk memperoleh verdict per berkas
     (Malicious/Benign) dan action (Prevent/Detect/Clean). Itulah angka detection
     rate yang dilaporkan di Bab 4.
  3. EICAR adalah berkas uji berbasis SIGNATURE Anti-Virus, BUKAN malware perilaku.
     Threat Emulation (sandbox perilaku) dapat mengembalikan verdict BENIGN untuk
     EICAR karena tidak ada perilaku berbahaya saat dieksekusi, dan blade Anti-Virus
     dinonaktifkan pada eksperimen ini. Jadi EICAR yang lolos pada kondisi TE/TEX
     adalah WAJAR dan bukan berarti fitur gagal. Untuk menguji Threat Emulation,
     gunakan sampel malware perilaku. Untuk menguji Threat Extraction, gunakan
     dokumen dengan konten aktif (makro/JavaScript) lalu periksa log TEX.

Cara pakai (dari folder berisi uji_deteksi.py; butuh paket requests seperti file_sender):
    python uji_deteksi.py <label>
contoh:
    python uji_deteksi.py S0_before
    python uji_deteksi.py B_profilescope
Jalankan SETELAH konfigurasi kondisi tersebut aktif di SmartConsole + Install Policy,
agar label hasil cocok dengan kondisi yang diuji.
"""
import csv, os, sys, time, io
import requests

# ---------------- KONFIG ----------------
SERVER = "http://10.0.10.105:8080/upload"
SAMPLE_DIR = r"C:\corpus_raw_malware"
OUTDIR = r"C:\hasil_tahap2"
TIMEOUT = 180          # detik; longgar agar verdict Hold sempat kembali
DELAY_BETWEEN = 0.5    # jeda antar berkas (detik), agar log mudah dipetakan
# ----------------------------------------

def list_samples(root):
    out = []
    for dirpath, _, files in os.walk(root):
        for fn in files:
            out.append(os.path.join(dirpath, fn))
    return sorted(out)

def classify(http_code, status):
    # heuristik sisi-klien (lihat catatan di docstring)
    if status.startswith("err"):
        return "blocked_or_error"     # reset/timeout: sering = diblokir saat Hold+Prevent
    if http_code == 200:
        return "delivered"            # terkirim (untuk TEX, bisa jadi sudah dibersihkan)
    if http_code in (403, 451) or 400 <= http_code < 600:
        return "blocked"
    return "unknown"

def main():
    if len(sys.argv) < 2:
        print("Gunakan: python uji_deteksi.py <label>   (mis. S0_before, B_profilescope)")
        sys.exit(1)
    label = sys.argv[1]
    os.makedirs(OUTDIR, exist_ok=True)
    if not os.path.isdir(SAMPLE_DIR):
        print(f"Folder sampel tidak ditemukan: {SAMPLE_DIR}")
        sys.exit(1)
    samples = list_samples(SAMPLE_DIR)
    if not samples:
        print(f"Tidak ada berkas di {SAMPLE_DIR}")
        sys.exit(1)
    out_csv = os.path.join(OUTDIR, f"deteksi_{label}.csv")
    print("=" * 64)
    print(f"UJI DETEKSI | label = {label}")
    print(f"Sumber sampel: {SAMPLE_DIR}  ({len(samples)} berkas)")
    print(f"Hasil ditulis ke: {out_csv}")
    print("Pastikan konfigurasi kondisi ini sudah aktif di SmartConsole + Install Policy.")
    print("=" * 64)

    rows = []
    counts = {}
    for i, path in enumerate(samples, 1):
        fname = os.path.basename(path)
        try:
            payload = open(path, "rb").read()
            size = len(payload)
        except OSError as e:
            print(f"  [{i}/{len(samples)}] LEWAT (tak terbaca): {fname} ({e})")
            continue
        submit = time.time(); code, status = -1, "ok"
        try:
            r = requests.post(SERVER, files={"file": (fname, io.BytesIO(payload))}, timeout=TIMEOUT)
            code = r.status_code
        except Exception as e:
            status = f"err:{type(e).__name__}"
        lat = (time.time() - submit) * 1000.0
        outcome = classify(code, status)
        counts[outcome] = counts.get(outcome, 0) + 1
        rows.append(dict(file=fname, size_bytes=size, http_code=code, status=status,
                         latency_ms=round(lat, 1), outcome=outcome))
        print(f"  [{i}/{len(samples)}] {fname:<40} {code:>5} {outcome:<18} {lat:8.0f} ms")
        time.sleep(DELAY_BETWEEN)

    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["file", "size_bytes", "http_code", "status", "latency_ms", "outcome"])
        w.writeheader(); w.writerows(rows)

    print("\n--- Ringkasan (sisi klien) ---")
    for k, v in sorted(counts.items()):
        print(f"  {k:<18}: {v}")
    delivered = counts.get("delivered", 0)
    total = len(rows)
    print(f"  total terkirim/diuji: {total}")
    print(f"  terkirim (lolos pengiriman): {delivered}  | tidak terkirim: {total - delivered}")
    print("\nLANGKAH WAJIB BERIKUTNYA untuk angka deteksi yang sahih:")
    print("  Ekspor SmartConsole -> Logs (Threat Emulation & Threat Extraction,")
    print("  Source 10.0.7.105) pada rentang waktu uji ini ke CSV, lalu unggah.")
    print("  Verdict (Malicious/Benign) dan action (Prevent/Detect/Clean) di log itulah")
    print("  yang menjadi detection rate / sanitization rate pada Bab 4.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nDihentikan oleh pengguna.")
