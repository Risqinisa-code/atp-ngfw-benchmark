# ATP NGFW Benchmark — Check Point Quantum Force 9700 (RFC 9411)

Kode dan skrip pengujian untuk penelitian tesis:
**"Evaluasi Empiris dan Optimisasi Dampak Advanced Threat Prevention (Threat Emulation dan Threat Extraction) terhadap Verdict Latency dan Utilisasi CPU pada Next-Generation Firewall Berbasis Metodologi RFC 9411: Studi Eksperimental pada Check Point Quantum Force 9700"**

> Repositori ini berisi seluruh skrip Python yang dipakai untuk membangkitkan beban, memantau perangkat, menjalankan eksperimen, serta menganalisis hasil. Tujuannya agar pengukuran dapat ditelusuri dan direplikasi.

*English summary:* Python testbed for empirically benchmarking the performance impact (verdict latency and CPU utilization) of Advanced Threat Prevention features (Threat Emulation and Threat Extraction) on a Check Point Quantum Force 9700, adapting the RFC 9411 methodology to file-level granularity.

---

## Daftar Isi
- [Ikhtisar](#ikhtisar)
- [Struktur Skrip](#struktur-skrip)
- [Prasyarat](#prasyarat)
- [Instalasi](#instalasi)
- [Cara Menjalankan](#cara-menjalankan)
- [Format Berkas Keluaran](#format-berkas-keluaran)
- [Reproduksibilitas](#reproduksibilitas)
- [Sitasi](#sitasi)
- [Lisensi](#lisensi)

---

## Ikhtisar

Eksperimen terdiri atas dua tahap yang mengadaptasi struktur fase RFC 9411 (ramp-up / sustain / ramp-down) pada granularitas berkas:

- **Tahap 1 (faktorial penuh, 72 run):** 4 status fitur ATP (Baseline, TEX, TE, TE+TEX) x 2 profil lalu lintas (mixed_office, file_heavy) x 3 tingkat beban (concurrency 12/24/40) x 3 ulangan.
- **Tahap 2 (before-after, 15 run):** pada kondisi worst case (TE+TEX, file_heavy, concurrency 40), mengevaluasi 5 kondisi optimisasi (S0, A rule ordering, B scope tipe, D ambang ukuran, A+B+D) dengan 3 ulangan.

Metrik utama: **verdict latency** (p50/p95/p99) dan **utilisasi CPU** (rata-rata agregat dan inti tersibuk). Metrik pelengkap: throughput level berkas. Emulasi Threat Emulation berjalan pada **ThreatCloud** dengan mode **Hold**.

## Struktur Skrip

| Skrip | Lokasi jalan | Peran |
|---|---|---|
| `server_receiver.py` | Server (Host B) | Penerima unggahan HTTP pada port 8080; mengukur lalu membuang berkas (drain), tidak menyimpan. |
| `file_sender.py` | Klien (Host A) | Pembangkit beban; mengirim berkas via HTTP POST pada concurrency tertentu; mencatat verdict latency per request. |
| `monitor_dut.py` | Klien -> DUT (SSH) | Membaca `/proc/stat` dan `/proc/loadavg` DUT secara berkala; mencatat CPU agregat dan inti tersibuk. |
| `corpus_sorter.py` | Klien | Menyiapkan korpus uji (mixed_office, file_heavy, korpus berbahaya). |
| `calibrate_rate.py` | Klien | Menyapu beberapa tingkat concurrency untuk menemukan titik jenuh. |
| `run_block.py` | Klien | Runner satu blok ATP: menjalankan 2 profil x 3 beban x 3 ulangan (sender + monitor paralel, fase warm-up/sustain/cooldown). |
| `orchestrator.py` | Klien | Orkestrasi Tahap 1 secara menyeluruh. |
| `run_tahap2.py` | Klien | Runner Tahap 2 per strategi optimisasi. |
| `uji_deteksi.py` | Klien | Uji deteksi keamanan (berkas berbahaya + EICAR) sebelum/sesudah optimisasi. |
| `cek_status.py` | Klien | Memeriksa kelengkapan kombinasi/berkas hasil. |
| `analyze.py` | Klien | Statistik deskriptif (persentil, CPU) dan grafik (boxplot, bar, scatter, before/after). |
| `uji_statistik.py` | Klien | ANOVA faktorial (Sum of Squares, df, F, ukuran efek eta^2) dan uji Kruskal-Wallis. |
| `orchestrator_lanjut.py` | Klien | Versi lama orkestrator (tidak dipakai / deprecated). |

## Prasyarat

- Python 3.9 atau lebih baru.
- Akses jaringan klien -> DUT -> server sesuai topologi penelitian.
- Akses SSH ke DUT (untuk `monitor_dut.py`).
- Pustaka pada `requirements.txt`.

## Instalasi

```bash
git clone https://github.com/<username>/atp-ngfw-benchmark-cp9700.git
cd atp-ngfw-benchmark-cp9700
pip install -r requirements.txt
```

## Cara Menjalankan

Ringkasan urutan (detail lengkap beserta konfigurasi DUT ada pada berkas panduan replikasi):

```bash
# 1) Di server (Host B)
python server_receiver.py --port 8080 --bind 0.0.0.0

# 2) Siapkan korpus (Host A)
python corpus_sorter.py --raw C:\raw --malware C:\raw_malware --out C:\corpus

# 3) Kalibrasi beban
python calibrate_rate.py --server http://10.0.10.105:8080/upload \
  --corpus C:\corpus\file_heavy --dut 10.0.7.103 --dut-pass <password> --out kalibrasi.csv

# 4) Tahap 1 (ganti profil di SmartConsole + Install Policy tiap blok)
python run_block.py Baseline
python run_block.py TEX
python run_block.py TE
python run_block.py TE_TEX

# 5) Tahap 2 (terapkan strategi + Install Policy tiap kali)
python run_tahap2.py S0_before
python run_tahap2.py A_ruleorder
python run_tahap2.py B_profilescope
python run_tahap2.py D_sizethreshold
python run_tahap2.py ABD_combined

# 6) Uji deteksi
python uji_deteksi.py S0_before
python uji_deteksi.py ABD_combined

# 7) Cek kelengkapan dan analisis
python cek_status.py
python analyze.py --indir . --outdir hasil_analisis
python uji_statistik.py --tahap1 . --tahap2 .
```

> Konstanta seperti alamat server, host DUT, dan kredensial diatur di bagian atas `run_block.py`, `run_tahap2.py`, dan `orchestrator.py`. Sesuaikan dengan lingkungan Anda. **Jangan** menaruh kredensial asli di repositori publik.

## Format Berkas Keluaran

- Tahap 1: `sender_{ATP}__{profil}__{beban}__r{rep}.csv` dan `monitor_{ATP}__{profil}__{beban}__r{rep}.csv`
- Tahap 2: `sender_tahap2_{strategi}__r{rep}.csv` dan `monitor_tahap2_{strategi}__r{rep}.csv`
- Uji deteksi: `deteksi_{label}.csv`

Berkas `sender_*` memuat verdict latency dan status per request; `monitor_*` memuat sampel utilisasi CPU.

## Reproduksibilitas

- Emulasi berjalan di **ThreatCloud**, sehingga nilai **absolut** verdict latency dapat berbeda antar waktu dan kondisi jaringan. Pola dan kesimpulan kualitatif (lonjakan latensi, saturasi inti tersibuk, non-aditivitas dampak, trade-off optimisasi) tetap dapat direplikasi.
- Jaga variabel kendali konstan: mode Hold, blade IPS/AV/Anti-Bot nonaktif, durasi fase (warm-up 60 s / sustain 300 s / cooldown 60 s), korpus identik.
- Hanya fase sustain yang direkam untuk analisis.
- Catat versi perangkat (Gaia R82 take 91), tanggal pengujian, dan status lisensi fitur.

## Sitasi

Jika menggunakan kode ini, mohon sitasi tesis terkait:

```
Nisa, R. K. (2026). Evaluasi Empiris dan Optimisasi Dampak Advanced Threat Prevention
(Threat Emulation dan Threat Extraction) terhadap Verdict Latency dan Utilisasi CPU
pada Next-Generation Firewall Berbasis Metodologi RFC 9411: Studi Eksperimental pada
Check Point Quantum Force 9700 (Tesis Magister, Universitas Indonesia).
```

## Lisensi

Disarankan MIT License untuk kode (lihat berkas `LICENSE`). Sesuaikan dengan kebijakan institusi Anda.

---

Kontak: Risqi Khoirun Nisa — Program Studi Teknik Elektro, Universitas Indonesia.
