# Mytier Auotomation


> ⚠️ Gunakan secara bertanggung jawab dan patuhi ToS situs terkait. Kredensial & sesi milikmu = tanggung jawabmu.

---

## ✨ Fitur

- ✅ **Auto Login + Session Refresh**  

- ✅ **Check-in Harian**  

- ✅ **Auto Mining**  

- ✅ **Multi Akun via `akun.txt`**  


---

## 🧰 Prasyarat

- **Python 3.9+**  

## INSTAL
```bash
git clone https://github.com/<username>/<repo-kamu>.git
cd <mytier>
```

# Install module
 ```bash
  pip install aiohttp rich fake-useragent
```

# Cara Pakai
1. Siapkan `akun.txt` (dibuat otomatis jika belum ada)

Format:
```bash
nickname1|password1 # perline
nickname2|password2
```

2. Jalankan bot:
```bash
python mine.py
```


##  Contoh Output (CLI)

```text
Mytier Automation — By ADMFIDN Team
┌───────────────┬───────────────────┬──────────────────────────────┬──────────────────────────────┐
│ Nickname      │ Check-in          │ Mining                       │ Next Try (UTC)              │
├───────────────┼───────────────────┼──────────────────────────────┼──────────────────────────────┤
│ akunA         │ CLAIMED           │ OK mined=375 total=14000     │ 2025-10-04T06:54:12+00:00    │
│ akunB         │ ALREADY TODAY     │ ALREADY MINING               │ 2025-10-04T06:46:26+00:00    │
└───────────────┴───────────────────┴──────────────────────────────┴──────────────────────────────┘

