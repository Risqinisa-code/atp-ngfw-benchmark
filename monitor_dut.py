#!/usr/bin/env python3
"""
monitor_dut.py  -- jalankan di Host A / workstation manajemen, Python 3.9+
pip install paramiko

Polling utilisasi CPU dan kedalaman antrian (queue) pada DUT via SSH selama
fase sustain, lalu menulis CSV: epoch, cpu_user, cpu_sys, cpu_idle, cpu_busy, queue.
Menyimpan juga keluaran mentah (--rawlog) untuk audit/penyesuaian parser.

VERIFIKASI perintah di perangkatmu (Gaia R82 take 91) dan sesuaikan regex bila perlu:
  - CPU  : cpstat os -f cpu   (alternatif: cpstat os -f multi_cpu, top -bn1)
  - QUEUE: tecli show emulator queue   (alternatif: tecli show emulator status)

Contoh:
  python monitor_dut.py --host 192.168.1.1 --user admin --password CHANGE_ME ^
    --interval 3 --duration 300 --out monitor_TE_TEX__file_heavy__tinggi__r1.csv --rawlog raw.txt
"""
import argparse
import csv
import re
import time

import paramiko


def run_cmd(ssh, cmd, timeout=15):
    try:
        _, out, _ = ssh.exec_command(cmd, timeout=timeout)
        return out.read().decode(errors="replace")
    except Exception as e:
        return f"__ERR__ {e}"


def parse_proc_stat(text):
    """Baca /proc/stat (env-free). Kembalikan dict label -> (total, idle_all)."""
    res = {}
    for line in text.splitlines():
        p = line.split()
        if not p:
            continue
        if p[0] == "cpu" or (p[0].startswith("cpu") and p[0][3:].isdigit()):
            nums = [int(x) for x in p[1:] if x.isdigit()]
            if len(nums) < 4:
                continue
            idle = nums[3] + (nums[4] if len(nums) > 4 else 0)  # idle + iowait
            res[p[0]] = (sum(nums), idle)
    return res


def cpu_from_delta(prev, cur):
    """Hitung %busy agregat dan core tersibuk dari dua snapshot /proc/stat."""
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
            busy = 100.0 * (dt - di) / dt
            maxcore = max(maxcore, busy)
    return agg, round(maxcore, 1)


def parse_loadavg(text):
    try:
        return float(text.split()[0])
    except Exception:
        return None


def parse_queue(text):
    """'tecli show emulator queue' berupa tabel; queue depth = jumlah baris data
    setelah baris pemisah (garis '---'). Kosong -> 0."""
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="192.168.1.1")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", required=True)
    ap.add_argument("--interval", type=float, default=3.0)
    ap.add_argument("--duration", type=int, default=300)
    ap.add_argument("--queue-cmd", default="tecli show emulator queue")
    ap.add_argument("--out", required=True)
    ap.add_argument("--rawlog", default=None)
    args = ap.parse_args()

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(args.host, username=args.user, password=args.password, timeout=20)

    raw = open(args.rawlog, "w") if args.rawlog else None
    rows = []
    end = time.time() + args.duration
    prev = None
    print(f"Monitoring {args.host} tiap {args.interval}s selama {args.duration}s...")
    while time.time() < end:
        ts = time.time()
        stat_txt = run_cmd(ssh, "cat /proc/stat")
        load_txt = run_cmd(ssh, "cat /proc/loadavg")
        # queue lewat clish agar environment Check Point ter-load (kosong = 0 di ThreatCloud)
        q_txt = run_cmd(ssh, 'clish -c "%s"' % args.queue_cmd)
        cur = parse_proc_stat(stat_txt)
        cpu_busy, cpu_max = (None, None)
        if prev is not None:
            cpu_busy, cpu_max = cpu_from_delta(prev, cur)
        prev = cur
        load1 = parse_loadavg(load_txt)
        q = parse_queue(q_txt)
        rows.append({"epoch": round(ts, 3), "cpu_busy": cpu_busy,
                     "cpu_max_core": cpu_max, "load1": load1, "queue": q})
        if raw:
            raw.write(f"==== {ts} ====\n[STAT]\n{stat_txt}\n[LOAD]\n{load_txt}\n[QUEUE]\n{q_txt}\n")
            raw.flush()
        slp = args.interval - (time.time() - ts)
        if slp > 0:
            time.sleep(slp)
    ssh.close()
    if raw:
        raw.close()

    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["epoch", "cpu_busy", "cpu_max_core", "load1", "queue"])
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} sampel ditulis ke {args.out}")


if __name__ == "__main__":
    main()
