#!/usr/bin/env python3
"""
file_sender.py  -- jalankan di Host A (10.0.7.105), Python 3.9+
pip install requests

Mengirim berkas dari folder corpus ke Host B via HTTP POST, dengan:
  - HASH UNIK: tiap berkas ditambah 16 byte acak sebelum dikirim agar
    Threat Emulation benar mengemulasi (tidak mengambil verdict dari cache).
  - LAJU TERKENDALI: --rate file per detik.
  - PENGUKURAN LATENCY: waktu submit -> balasan 200 (mode Hold = proxy verdict latency).
Menulis CSV: submit_epoch, verdict_epoch, latency_ms, file, size_bytes, http_code, status.

Contoh:
  python file_sender.py --server http://10.0.10.105:8080/upload ^
    --corpus C:\\corpus\\file_heavy --rate 30 --duration 300 --out sender_TE_TEX__file_heavy__tinggi__r1.csv
"""
import argparse
import csv
import io
import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests


def collect_files(corpus_dir):
    files = []
    for root, _, names in os.walk(corpus_dir):
        for n in names:
            files.append(os.path.join(root, n))
    return files


def unique_payload(path):
    with open(path, "rb") as f:
        data = f.read()
    return data + random.randbytes(16)


def send_one(server, path, results, lock, timeout):
    fname = os.path.basename(path)
    try:
        size = os.path.getsize(path)
        payload = unique_payload(path)
    except OSError:
        return
    t0 = time.time()
    code, status = -1, "ok"
    try:
        r = requests.post(server, files={"file": (fname, io.BytesIO(payload))}, timeout=timeout)
        code = r.status_code
    except Exception as e:
        status = f"err:{type(e).__name__}"
    t1 = time.time()
    with lock:
        results.append({
            "submit_epoch": round(t0, 4),
            "verdict_epoch": round(t1, 4),
            "latency_ms": round((t1 - t0) * 1000.0, 2),
            "file": fname,
            "size_bytes": size,
            "http_code": code,
            "status": status,
        })


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://10.0.10.105:8080/upload")
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--rate", type=float, default=None, help="mode laju: kirim file per detik")
    ap.add_argument("--concurrency", type=int, default=None,
                    help="mode beban: jumlah upload paralel yang dijaga tetap (lever beban utama)")
    ap.add_argument("--duration", type=int, default=300, help="durasi fase sustain (detik)")
    ap.add_argument("--workers", type=int, default=128, help="batas pool thread (mode rate)")
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    files = collect_files(args.corpus)
    if not files:
        print("Corpus kosong:", args.corpus)
        return

    results = []
    lock = threading.Lock()
    deadline = time.time() + args.duration

    if args.concurrency:
        # MODE CONCURRENCY: N thread pekerja, masing-masing mengirim berkas secara
        # berurutan sampai deadline -> menjaga ~N emulasi in-flight (lever beban).
        print(f"{len(files)} file | concurrency {args.concurrency} | durasi {args.duration}s")
        counter = {"i": 0}

        def worker():
            while time.time() < deadline:
                with lock:
                    path = files[counter["i"] % len(files)]
                    counter["i"] += 1
                send_one(args.server, path, results, lock, args.timeout)

        threads = [threading.Thread(target=worker) for _ in range(args.concurrency)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    else:
        rate = args.rate if args.rate else 10.0
        print(f"{len(files)} file | rate {rate}/s | durasi {args.duration}s")
        interval = 1.0 / rate
        idx = 0
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            next_t = time.time()
            while time.time() < deadline:
                pool.submit(send_one, args.server, files[idx % len(files)], results, lock, args.timeout)
                idx += 1
                next_t += interval
                slp = next_t - time.time()
                if slp > 0:
                    time.sleep(slp)
            print("Sustain selesai, menunggu upload tersisa...")

    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["submit_epoch", "verdict_epoch", "latency_ms",
                                          "file", "size_bytes", "http_code", "status"])
        w.writeheader()
        w.writerows(results)
    ok = sum(1 for r in results if r["http_code"] == 200)
    print(f"Terkirim {len(results)} | sukses {ok} | ditulis ke {args.out}")


if __name__ == "__main__":
    main()
