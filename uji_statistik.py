#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
uji_statistik.py
Analisis inferensial sebagai alat karakterisasi (bukan uji hipotesis):
  1. ANOVA faktorial pada log10(verdict latency) Tahap 1 -> Sum of Squares, df, F, dan ukuran efek eta^2.
  2. Uji Kruskal-Wallis antar strategi optimisasi Tahap 2 untuk verdict latency dan utilisasi inti tersibuk.
Masukan : direktori berisi CSV sender_*.csv dan monitor_*.csv (Tahap 1)
          serta sender_tahap2_*.csv dan monitor_tahap2_*.csv (Tahap 2).
Keluaran: tabel ANOVA dan hasil Kruskal-Wallis dicetak ke layar.
"""
import argparse, glob, os, collections
import numpy as np, pandas as pd
import statsmodels.formula.api as smf
from statsmodels.stats.anova import anova_lm
from scipy.stats import kruskal


def muat_tahap1(indir):
    """Membaca seluruh sender_*.csv Tahap 1 menjadi DataFrame per-request
    dengan kolom respons log10(latency) dan faktor TE, TEX, beban, profil."""
    baris = []
    for sf in glob.glob(os.path.join(indir, "sender_*.csv")):
        nama = os.path.basename(sf).split("sender_")[1].rsplit(".csv", 1)[0]
        if nama.startswith("tahap2"):
            continue
        atp, profil, beban, _rep = nama.split("__")
        d = pd.read_csv(sf)
        d["lat"] = pd.to_numeric(d["latency_ms"], errors="coerce")
        d["http"] = pd.to_numeric(d["http_code"], errors="coerce")
        ok = d[(d["status"] == "ok") & (d["http"] == 200)]["lat"].dropna().values
        te = 1 if atp in ("TE", "TE_TEX") else 0
        tex = 1 if atp in ("TEX", "TE_TEX") else 0
        for v in ok:
            baris.append((np.log10(v), te, tex, beban, profil))
    return pd.DataFrame(baris, columns=["loglat", "TE", "TEX", "beban", "profil"])


def anova_faktorial(df):
    """Menjalankan ANOVA faktorial dan menambahkan kolom ukuran efek eta^2."""
    model = smf.ols("loglat ~ C(TE)*C(TEX) + C(beban) + C(profil)", data=df).fit()
    aov = anova_lm(model, typ=2)
    sst = aov["sum_sq"].sum()
    aov["eta_sq_%"] = 100 * aov["sum_sq"] / sst
    return aov, sst


def muat_tahap2(indir):
    """Mengelompokkan verdict latency dan utilisasi inti tersibuk per strategi optimisasi."""
    lat = collections.defaultdict(list)
    core = collections.defaultdict(list)
    for sf in glob.glob(os.path.join(indir, "sender_tahap2_*.csv")):
        s = os.path.basename(sf).split("sender_tahap2_")[1].rsplit(".csv", 1)[0].rsplit("__r", 1)[0]
        d = pd.read_csv(sf)
        d["lat"] = pd.to_numeric(d["latency_ms"], errors="coerce")
        d["http"] = pd.to_numeric(d["http_code"], errors="coerce")
        lat[s] += list(d[(d["status"] == "ok") & (d["http"] == 200)]["lat"].dropna().values)
    for mf in glob.glob(os.path.join(indir, "monitor_tahap2_*.csv")):
        s = os.path.basename(mf).split("monitor_tahap2_")[1].rsplit(".csv", 1)[0].rsplit("__r", 1)[0]
        m = pd.read_csv(mf)
        core[s] += list(pd.to_numeric(m["cpu_max_core"], errors="coerce").dropna().values)
    return lat, core


def main():
    ap = argparse.ArgumentParser(description="ANOVA faktorial dan uji Kruskal-Wallis")
    ap.add_argument("--tahap1", required=True, help="direktori CSV Tahap 1")
    ap.add_argument("--tahap2", required=True, help="direktori CSV Tahap 2")
    args = ap.parse_args()

    # --- Tahap 1: ANOVA faktorial ---
    df = muat_tahap1(args.tahap1)
    print(f"[Tahap 1] N = {len(df)} request")
    aov, sst = anova_faktorial(df)
    print(aov[["sum_sq", "df", "F", "PR(>F)", "eta_sq_%"]].round(4).to_string())
    print(f"SS_total = {sst:.2f}\n")

    # --- Tahap 2: Kruskal-Wallis ---
    urut = ["S0_before", "A_ruleorder", "B_profilescope", "D_sizethreshold", "ABD_combined"]
    lat, core = muat_tahap2(args.tahap2)
    gl = [np.array(lat[s]) for s in urut if len(lat[s])]
    gc = [np.array(core[s]) for s in urut if len(core[s])]
    Hl, pl = kruskal(*gl)
    Hc, pc = kruskal(*gc)
    print("[Tahap 2] Kruskal-Wallis (df = jumlah strategi - 1)")
    print(f"  Verdict latency      : H = {Hl:.2f}  p = {pl:.3f}")
    print(f"  Utilisasi inti tersibuk: H = {Hc:.2f}  p = {pc:.3f}")


if __name__ == "__main__":
    main()
