#!/usr/bin/env python3
"""
calibrate_rate.py  -- jalankan di Host A (Windows 10), Python 3.9+
pip install requests paramiko

Tujuan:
  Mencari laju kedatangan file (file/detik) yang tepat untuk menetapkan tiga
  level beban eksperimen (rendah / sedang / tinggi). Caranya: menaikkan laju
  kirim secara bertahap (sweep) sambil memantau kedalaman antrian (queue) dan
  utilisasi CPU pada DUT. Titik di mana queue MULAI tumbuh konsisten menandai
  ambang saturasi engine sandbox.

Logika penetapan level (heuristik, bisa kamu sesuaikan):
  - tinggi  = laju pada/di atas titik queue mulai tumbuh (mendekati saturasi)
  - sedang  = sekitar 75% dari laju 'tinggi'
  - rendah  = sekitar 50% dari laju 'tinggi'

Pakai pada kondisi yang paling berat agar saturasi cepat terlihat:
  profil file_heavy, status ATP TE+TEX (mode Hold), corpus sudah siap.

Contoh:
  python calibrate_rate.py ^
    --server http://10.0.10.105:8080/upload ^
    --corpus C:\\corpus\\file_heavy ^
    --dut 192.168.1.1 --dut-user admin --dut-pass CHANGE_ME ^
    --concurrencies 10,20,40,60,80,100 --step-duration 60 --out kalibrasi.csv

Penting:
  - Pastikan profil TP_TE_TEX aktif & policy ter-install sebelum menjalankan.
  - Verifikasi perintah queue pada DUT-mu (lihat --queue-cmd). Default:
    'tecli show emulator queue'. Sesuaikan bila build R82 take 91 berbeda.
"""
import argparse
import io
import os
import random
import re
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

try:
    import paramiko
except ImportError:
    paramiko = None


# ---------- pengiriman file (sama prinsip dengan file_sender) ----------
def unique_payload(path):
    with open(path, "rb") as f:
        data = f.read()
    return data + random.randbytes(16)


def collect_files(corpus_dir):
    files = []
    for root, _, names in os.walk(corpus_dir):
        for n in names:
            files.append(os.path.join(root, n))
    return files


def send_one(server, path, lat_list, lock, timeout):
    payload = unique_payload(path)
    fname = os.path.basename(path)
    t0 = time.time()
    code = -1
    try:
        r = requests.post(server, files={"file": (fname, io.BytesIO(payload))}, timeout=timeout)
        code = r.status_code
    except Exception:
        pass
    dt = (time.time() - t0) * 1000.0
    if code == 200:
        with lock:
            lat_list.append(dt)


# ---------- monitoring DUT ----------
def ssh_connect(host, user, pw):
    if paramiko is None:
        raise RuntimeError("paramiko belum terinstal: pip install paramiko")
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cli.connect(host, username=user, password=pw, timeout=20)
    return cli


def run_cmd(cli, cmd, timeout=15):
    try:
        _, out, _ = cli.exec_command(cmd, timeout=timeout)
        return out.read().decode(errors="replace")
    except Exception as e:
        return f"__ERR__ {e}"


def parse_proc_stat(text):
    res = {}
    for line in text.splitlines():
        p = line.split()
        if not p:
            continue
        if p[0] == "cpu" or (p[0].startswith("cpu") and p[0][3:].isdigit()):
            nums = [int(x) for x in p[1:] if x.isdigit()]
            if len(nums) < 4:
                continue
            idle = nums[3] + (nums[4] if len(nums) > 4 else 0)
            res[p[0]] = (sum(nums), idle)
    return res


def cpu_from_delta(prev, cur):
    agg = None
    maxcore = 0.0
    if "cpu" in prev and "cpu" in cur:
        t0, i0 = prev["cpu"]; t1, i1 = cur["cpu"]
        dt, di = t1 - t0, i1 - i0
        if dt > 0:
            agg = round(100.0 * (dt - di) / dt, 1)
    for k in cur:
        if k == "cpu" or k not in prev:
            continue
        t0, i0 = prev[k]; t1, i1 = cur[k]
        dt, di = t1 - t0, i1 - i0
        if dt > 0:
            maxcore = max(maxcore, 100.0 * (dt - di) / dt)
    return agg, round(maxcore, 1)


def parse_queue(text):
    """Queue depth = jumlah baris data setelah baris pemisah; kosong -> 0."""
    lines = text.splitlines()
    sep_idx = None
    for i, ln in enumerate(lines):
        s = ln.strip()
        if len(s) > 10 and set(s) <= set("- "):
            sep_idx = i
            break
    if sep_idx is None:
        return None
    return sum(1 for ln in lines[sep_idx + 1:] if ln.strip())


# ---------- satu langkah sweep pada satu level concurrency ----------
def run_step(server, files, conc, duration, timeout, cli, queue_cmd):
    lat = []
    lock = threading.Lock()
    cpu_samples, cpumax_samples, q_samples = [], [], []
    stop = threading.Event()

    def monitor():
        prev = None
        while not stop.is_set():
            if cli is not None:
                cur = parse_proc_stat(run_cmd(cli, "cat /proc/stat"))
                if prev is not None:
                    agg, mx = cpu_from_delta(prev, cur)
                    if agg is not None:
                        cpu_samples.append(agg)
                        cpumax_samples.append(mx)
                prev = cur
                q = parse_queue(run_cmd(cli, 'clish -c "%s"' % queue_cmd))
                if q is not None:
                    q_samples.append(q)
            time.sleep(3)

    mon_t = threading.Thread(target=monitor, daemon=True)
    mon_t.start()

    # MODE CONCURRENCY: 'conc' thread pekerja, masing-masing mengirim berkas
    # berurutan sampai deadline -> menjaga ~conc emulasi in-flight.
    deadline = time.time() + duration
    counter = {"i": 0}

    def worker():
        while time.time() < deadline:
            with lock:
                path = files[counter["i"] % len(files)]
                counter["i"] += 1
            send_one(server, path, lat, lock, timeout)

    threads = [threading.Thread(target=worker) for _ in range(conc)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    stop.set()
    mon_t.join(timeout=5)

    def safe(fn, seq, default=0):
        return fn(seq) if seq else default

    return {
        "concurrency": conc,
        "sent": counter["i"],
        "ok": len(lat),
        "lat_p50": round(safe(statistics.median, lat), 1),
        "lat_p95": round(safe(lambda x: statistics.quantiles(x, n=20)[18] if len(x) >= 20 else max(x), lat), 1),
        "cpu_avg": round(safe(statistics.mean, cpu_samples), 1),
        "cpu_busiest_core_avg": round(safe(statistics.mean, cpumax_samples), 1),
        "cpu_busiest_core_peak": safe(max, cpumax_samples),
        "q_avg": round(safe(statistics.mean, q_samples), 1),
        "q_max": safe(max, q_samples),
    }


def main():
    ap = argparse.ArgumentParser(description="Kalibrasi laju kedatangan file (rate)")
    ap.add_argument("--server", required=True)
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--dut", default=None, help="IP manajemen DUT untuk monitoring (opsional)")
    ap.add_argument("--dut-user", default="admin")
    ap.add_argument("--dut-pass", default=None)
    ap.add_argument("--queue-cmd", default="tecli show emulator queue",
                    help="perintah CLI untuk membaca kedalaman antrian")
    ap.add_argument("--concurrencies", default="10,20,40,60,80,100",
                    help="daftar level concurrency yang diuji, dipisah koma")
    ap.add_argument("--step-duration", type=int, default=60, help="durasi tiap langkah (detik)")
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--out", default="kalibrasi.csv")
    args = ap.parse_args()

    files = collect_files(args.corpus)
    if not files:
        print("Corpus kosong:", args.corpus)
        return
    levels = [int(float(x)) for x in args.concurrencies.split(",") if x.strip()]

    cli = None
    if args.dut and args.dut_pass:
        try:
            cli = ssh_connect(args.dut, args.dut_user, args.dut_pass)
            print("Terhubung ke DUT untuk monitoring queue & CPU.")
        except Exception as e:
            print("Gagal SSH ke DUT, lanjut tanpa monitoring:", e)
    else:
        print("PERINGATAN: --dut tidak diisi, monitoring CPU/queue DILEWATI (akan 0).")

    print(f"{len(files)} file di corpus. Sweep concurrency: {levels}")
    results = []
    for conc in levels:
        print(f"\n>> Menguji concurrency {conc} selama {args.step_duration}s ...")
        res = run_step(args.server, files, conc, args.step_duration,
                       args.timeout, cli, args.queue_cmd)
        results.append(res)
        print(f"   sent={res['sent']} ok={res['ok']} "
              f"lat_p50={res['lat_p50']}ms lat_p95={res['lat_p95']}ms "
              f"cpu_avg={res['cpu_avg']}% busiest_core_avg={res['cpu_busiest_core_avg']}% "
              f"busiest_core_peak={res['cpu_busiest_core_peak']}% "
              f"q_avg={res['q_avg']} q_max={res['q_max']}")
        time.sleep(15)  # jeda antar langkah agar antrian sempat drain

    if cli is not None:
        cli.close()

    import csv
    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        w.writeheader()
        w.writerows(results)
    print("\nHasil kalibrasi ditulis ke", args.out)

    # Heuristik penetapan beban. Karena emulasi cloud (ThreatCloud), CPU agregat
    # dan queue lokal rendah; lonjakan VERDICT LATENCY adalah sinyal saturasi utama.
    sat = None
    base = results[0]["lat_p50"] if results else 0
    for res in results:
        # saturasi bila p50 melonjak jauh (>=3x baseline) atau queue/core jenuh
        if (base > 0 and res["lat_p50"] >= 3 * base) or res["q_avg"] > 1.0 \
                or res["cpu_busiest_core_peak"] >= 90:
            sat = res["concurrency"]
            break
    print("\n--- Rekomendasi level beban (concurrency) ---")
    if sat is None:
        top = results[-1]["concurrency"]
        print(f"Belum terlihat titik saturasi jelas hingga concurrency tertinggi ({top}).")
        print(f"Saran: gunakan tinggi={top}, sedang={int(top*0.6)}, rendah={int(top*0.3)}.")
    else:
        print(f"Titik saturasi (lonjakan latency / queue / core jenuh) pada concurrency ~{sat}.")
        print(f"Saran level:  tinggi = {sat},  sedang = {int(sat*0.6)},  rendah = {int(sat*0.3)}")
    print("Masukkan angka ini ke dict LOAD_CONC pada orchestrator.py.")


if __name__ == "__main__":
    main()
