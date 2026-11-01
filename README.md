# Panduan Proyek Platform Web Geofisika: ResIPy & GPS Integration
Inisiator: Kang Rangga Adi
Lokasi Repositori: `/home/localai/projects/resipy-web-platform`

---

## Pembagian Tim & Modul Kerja

### 1. Tim GUI Website (Frontend)
- **Target:** Dashboard Web Interaktif (React / Next.js + Tailwind CSS)
- **Fokus Fitur:**
  - Panel upload data mentah resistivitas (.dat, .csv, format instrumen Syscal/ARES/Geometrics).
  - Form parameterisasi akuisisi (Wenner, Schlumberger, Dipole-Dipole, electrode spacing).
  - Monitoring log proses inversi (progress bar RMS error real-time).
  - Integrasi tab penampil 2D, viewport 3D, dan peta interaktif.

### 2. Tim Kodingan ResIPy 2D (Inversion Engine)
- **Target:** Backend Worker & API ResIPy (FastAPI + Python ResIPy/R2)
- **Fokus Fitur:**
  - Parsing dan QC data (filtering reciprocal errors, resistivitas semu negatif).
  - Otomasi pembuatan mesh (triangular/trapezoidal) dengan koreksi topografi.
  - Eksekusi solver forward & inverse modeling 2D headless.
  - Ekstraksi output penampang resistivitas (PNG/SVG, GeoTIFF, dan CSV matrix).

### 3. Tim Desain & Inversi 3D
- **Target:** Engine Rendering & Pemodelan Volumetrik (Three.js / VTK.js / PyVista)
- **Fokus Fitur:**
  - Interpolasi spasial data multi-line 2D menjadi blok/volume 3D.
  - Rendering interaktif di browser (Iso-surface, fence diagram, depth-slices).
  - Kontrol colorbar dinamis (skala logaritmik ohm-m untuk akuifer, lempung, batuan dasar).

### 4. Tim Peta & Komponen GPS
- **Target:** Modul GIS Lapangan Terintegrasi (Leaflet.js / MapLibre GL)
- **Fokus Fitur:**
  - Plotting otomatis baseline lintasan dan posisi elektroda di peta satelit/topografi (WGS84 / UTM).
  - Pembacaan sinyal GPS secara real-time via Web Serial API (NMEA / GNSS receiver lapangan).
  - Integrasi DEM (DEMNAS/SRTM) untuk penyusunan data ketinggian elektroda secara otomatis.

### 5. Tim 5: Deployment, Cloudflare & GitHub CI/CD (Phiseis)
- **Target:** Infrastruktur Global, Edge Delivery, Otomasi Pipeline & Security Gateway
- **Fokus Fitur:**
  - **CI/CD Pipeline GitHub Actions:** Otomasi build, testing, linting, dan trigger deployment otomatis saat ada commit ke main branch.
  - **Hosting Edge Cloudflare:** Deployment Web Frontend ke Cloudflare Pages/Workers dengan latensi ultra rendah dan proteksi DDoS/WAF.
  - **Cloudflare Tunnel / Zero Trust API Gateway:** Routing aman dari publik (domain Web) ke microservice komputasi internal klaster (Cikkaaa Ubuntu untuk Inversi 2D ResIPy & Windah Windows untuk Pemodelan 3D 24 Jam) tanpa membuka port publik rentan.
  - **Manajemen Domain & SSL:** Integrasi sertifikat TLS otomatis, custom caching rules untuk aset 3D (glTF/binary mesh), dan edge workers untuk kompresi data transfer.

---

## 🚀 Cloud Accelerator (Google Colab)
Untuk inversi data geolistrik skala besar atau pemodelan 3D berdensitas tinggi menggunakan GPU/High-RAM cloud gratis Google Colab:
- **Notebook:** [`notebooks/ResIPy_PeatFR_3D_Colab_Accelerator.ipynb`](notebooks/ResIPy_PeatFR_3D_Colab_Accelerator.ipynb)
- **Direct Run in Colab:** [Buka di Google Colab](https://colab.research.google.com/github/Rangga-26/resipy-web-platform/blob/main/notebooks/ResIPy_PeatFR_3D_Colab_Accelerator.ipynb)

