#!/usr/bin/env python3
"""
analyze.py  -- pengolah data deskriptif (metrik: verdict latency, queue, CPU)
Python 3.9+   |   pip install pandas matplotlib numpy openpyxl

Membaca seluruh CSV hasil eksperimen, menghitung statistik deskriptif per sel,
dan menghasilkan grafik untuk Bab 4:
  - Gambar 4.2 : boxplot verdict latency per status ATP
  - Gambar 4.3 : bar utilisasi CPU rata-rata per status ATP
  - Gambar 4.4 : scatter ukuran file vs latency (kondisi TE/TE+TEX aktif)
  - Gambar 4.5 : grafik sebelum/sesudah optimisasi (Tahap 2, dari CSV manual)
Plus ekspor ringkasan ke Excel (per_run & per_sel).

Penamaan file yang diharapkan (dihasilkan orchestrator.py):
  sender_{ATP}__{profil}__{load}__r{rep}.csv
  monitor_{ATP}__{profil}__{load}__r{rep}.csv
  ATP in {Baseline, TEX, TE, TE_TEX}

Pemakaian:
  python analyze.py --indir C:\\hasil --outdir C:\\hasil_analisis --beforeafter C:\\tahap2.csv
"""
import argparse
import glob
import os
import re

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ATP_ORDER = ["Baseline", "TEX", "TE", "TE_TEX"]


def parse_tag(path):
    """Parse sender_/monitor_{ATP}__{profil}__{load}__r{rep}.csv via split('__').
    Robust terhadap underscore di dalam nama (TE_TEX, mixed_office, file_heavy)."""
    base = os.path.basename(path)
    if not base.endswith(".csv"):
        return None
    if not (base.startswith("sender_") or base.startswith("monitor_")):
        return None
    stem = base[:-4]
    kind, rest = stem.split("_", 1)          # kind=sender; rest=TE_TEX__file_heavy__tinggi__r3
    parts = rest.split("__")
    if len(parts) != 4:
        return None
    atp, profil, load, reppart = parts
    if not reppart.startswith("r"):
        return None
    try:
        rep = int(reppart[1:])
    except ValueError:
        return None
    return {"kind": kind, "atp": atp, "profil": profil, "load": load, "rep": rep}


def load_sender(indir):
    rows = []
    for f in glob.glob(os.path.join(indir, "sender_*.csv")):
        t = parse_tag(f)
        if not t:
            continue
        try:
            df = pd.read_csv(f)
        except Exception:
            continue
        if "latency_ms" not in df.columns:
            continue
        if "http_code" in df.columns:
            ok = df[df["http_code"] == 200]
        else:
            ok = df
        lat = ok["latency_ms"].dropna()
        if lat.empty:
            continue
        rows.append({
            "atp": t["atp"], "profil": t["profil"], "load": t["load"], "rep": t["rep"],
            "n_files": int(len(ok)),
            "lat_p50": float(np.percentile(lat, 50)),
            "lat_p95": float(np.percentile(lat, 95)),
            "lat_p99": float(np.percentile(lat, 99)),
            "lat_mean": float(lat.mean()),
            "size_mean": float(ok["size_bytes"].mean()) if "size_bytes" in ok else np.nan,
        })
    return pd.DataFrame(rows)


def load_monitor(indir):
    rows = []
    for f in glob.glob(os.path.join(indir, "monitor_*.csv")):
        t = parse_tag(f)
        if not t:
            continue
        try:
            df = pd.read_csv(f)
        except Exception:
            continue
        cpu = df["cpu_busy"].dropna() if "cpu_busy" in df else pd.Series(dtype=float)
        q = df["queue"].dropna() if "queue" in df else pd.Series(dtype=float)
        rows.append({
            "atp": t["atp"], "profil": t["profil"], "load": t["load"], "rep": t["rep"],
            "cpu_avg": float(cpu.mean()) if not cpu.empty else np.nan,
            "cpu_peak": float(cpu.max()) if not cpu.empty else np.nan,
            "q_avg": float(q.mean()) if not q.empty else np.nan,
            "q_max": float(q.max()) if not q.empty else np.nan,
        })
    return pd.DataFrame(rows)


def merge_data(sender, monitor):
    if sender.empty and monitor.empty:
        return pd.DataFrame()
    if sender.empty:
        return monitor
    if monitor.empty:
        return sender
    return sender.merge(monitor, on=["atp", "profil", "load", "rep"], how="outer")


def order_atp(df):
    df = df.copy()
    df["atp"] = pd.Categorical(df["atp"], categories=ATP_ORDER, ordered=True)
    return df.sort_values(["atp", "profil", "load", "rep"])


def present_atps(df, col):
    sub = df.dropna(subset=[col])
    return sub, [a for a in ATP_ORDER if a in set(sub["atp"].dropna().unique())]


def fig_box_latency(df, outdir):
    sub, labels = present_atps(df, "lat_p50")
    if not labels:
        print("  (lewati boxplot latency: data kosong)")
        return
    groups = [sub[sub["atp"] == a]["lat_p50"].values for a in labels]
    plt.figure(figsize=(7, 4.5))
    bp = plt.boxplot(groups)
    plt.xticks(range(1, len(labels) + 1), labels)
    plt.ylabel("Verdict latency p50 (ms)")
    plt.xlabel("Status ATP")
    plt.title("Distribusi verdict latency per status ATP")
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, "gambar_4_2_boxplot_latency.png"), dpi=300)
    plt.close()


def fig_bar_cpu(df, outdir):
    sub, labels = present_atps(df, "cpu_avg")
    if not labels:
        print("  (lewati bar CPU: data kosong)")
        return
    means = [sub[sub["atp"] == a]["cpu_avg"].mean() for a in labels]
    plt.figure(figsize=(7, 4.5))
    plt.bar(labels, means)
    plt.ylabel("CPU busy rata-rata (%)")
    plt.xlabel("Status ATP")
    plt.title("Utilisasi CPU rata-rata per status ATP")
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, "gambar_4_3_bar_cpu.png"), dpi=300)
    plt.close()


def fig_scatter_size_latency(indir, outdir):
    xs, ys = [], []
    for f in glob.glob(os.path.join(indir, "sender_TE*.csv")):
        try:
            df = pd.read_csv(f)
        except Exception:
            continue
        if "size_bytes" in df and "latency_ms" in df:
            ok = df[df["http_code"] == 200] if "http_code" in df else df
            xs.extend(ok["size_bytes"].values / 1024 / 1024)  # MB
            ys.extend(ok["latency_ms"].values)
    if not xs:
        print("  (lewati scatter: tidak ada file sender_TE*)")
        return
    plt.figure(figsize=(7, 4.5))
    plt.scatter(xs, ys, s=6, alpha=0.3)
    plt.xlabel("Ukuran file (MB)")
    plt.ylabel("Latency (ms)")
    plt.title("Ukuran file vs latency (TE/TE+TEX aktif)")
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, "gambar_4_4_scatter_size_latency.png"), dpi=300)
    plt.close()


def fig_before_after(beforeafter_csv, outdir):
    """CSV manual Tahap 2; kolom: strategi,kondisi,lat_p50,cpu_avg ; kondisi=before/after."""
    if not beforeafter_csv or not os.path.exists(beforeafter_csv):
        print("  (lewati before/after: CSV Tahap 2 tidak diberikan)")
        return
    df = pd.read_csv(beforeafter_csv)
    strategies = list(df["strategi"].unique())
    x = np.arange(len(strategies))
    w = 0.35
    bef = [df[(df["strategi"] == s) & (df["kondisi"] == "before")]["lat_p50"].mean() for s in strategies]
    aft = [df[(df["strategi"] == s) & (df["kondisi"] == "after")]["lat_p50"].mean() for s in strategies]
    plt.figure(figsize=(8, 4.5))
    plt.bar(x - w / 2, bef, w, label="Sebelum")
    plt.bar(x + w / 2, aft, w, label="Sesudah")
    plt.xticks(x, strategies)
    plt.ylabel("Verdict latency p50 (ms)")
    plt.title("Verdict latency sebelum vs sesudah optimisasi (Tahap 2)")
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, "gambar_4_5_before_after.png"), dpi=300)
    plt.close()


def main():
    ap = argparse.ArgumentParser(description="Pengolah data deskriptif eksperimen ATP")
    ap.add_argument("--indir", required=True, help="folder berisi sender_*.csv & monitor_*.csv")
    ap.add_argument("--outdir", default="hasil_analisis")
    ap.add_argument("--beforeafter", default=None, help="CSV Tahap 2 before/after (opsional)")
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)

    sender = load_sender(args.indir)
    monitor = load_monitor(args.indir)
    df = merge_data(sender, monitor)
    if df.empty:
        print("Tidak ada data terbaca. Periksa penamaan file di", args.indir)
        return
    df = order_atp(df)

    agg = df.groupby(["atp", "profil", "load"], observed=True).agg(
        lat_p50=("lat_p50", "mean"),
        lat_p95=("lat_p95", "mean"),
        lat_p99=("lat_p99", "mean"),
        cpu_avg=("cpu_avg", "mean"),
        cpu_peak=("cpu_peak", "mean"),
        q_avg=("q_avg", "mean"),
        q_max=("q_max", "mean"),
        n_files=("n_files", "mean"),
    ).reset_index()

    xlsx = os.path.join(args.outdir, "ringkasan_deskriptif.xlsx")
    try:
        with pd.ExcelWriter(xlsx) as w:
            df.to_excel(w, sheet_name="per_run", index=False)
            agg.to_excel(w, sheet_name="per_sel", index=False)
        print("Ringkasan Excel:", xlsx)
    except Exception as e:
        print("Gagal menulis Excel (cek openpyxl):", e)
    agg.to_csv(os.path.join(args.outdir, "ringkasan_per_sel.csv"), index=False)

    fig_box_latency(df, args.outdir)
    fig_bar_cpu(df, args.outdir)
    fig_scatter_size_latency(args.indir, args.outdir)
    fig_before_after(args.beforeafter, args.outdir)
    print("Selesai. Grafik & ringkasan di:", args.outdir)


if __name__ == "__main__":
    main()
