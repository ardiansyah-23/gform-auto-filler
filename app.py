import time
import pandas as pd
import streamlit as st
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

st.set_page_config(page_title="Bot Kuesioner Auto-Fill", page_icon="🚀")

st.title("🚀 Bot Auto-Fill Google Form")
st.write("Aplikasi ini akan membaca file Excel dan mengisi Google Form secara otomatis.")

# ==========================================
# 1. INPUT LINK & SUMBER DATA (STREAMLIT UI)
# ==========================================
import clickhouse_connect # Tambahkan import ini di bagian atas file

url_form = st.text_input("🔗 Masukkan/Tempel Link Google Form target:", placeholder="https://docs.google.com/forms/...")
st.write("---")

# Pilihan Sumber Data
sumber_data = st.radio("Pilih sumber data responden:", ["Upload File Excel", "Tarik dari ClickHouse"])

df = None # Siapkan variabel df kosong

if sumber_data == "Upload File Excel":
    uploaded_file = st.file_uploader("📂 Upload file Excel (.xlsx / .xls)", type=["xlsx", "xls"])
    if uploaded_file is not None:
        df = pd.read_excel(uploaded_file)

elif sumber_data == "Tarik dari ClickHouse":
    st.info("Masukkan detail koneksi database ClickHouse kamu:")
    col1, col2 = st.columns(2)
    ch_host = col1.text_input("Host", placeholder="localhost atau IP server")
    ch_port = col2.number_input("Port", value=8123)
    ch_user = col1.text_input("Username", value="default")
    ch_pass = col2.text_input("Password", type="password")
    ch_table = st.text_input("Nama Tabel", placeholder="contoh: data_responden")
    
    if st.button("Ambil Data dari Database"):
        try:
            client = clickhouse_connect.get_client(host=ch_host, port=ch_port, username=ch_user, password=ch_pass)
            # Menarik data dari ClickHouse dan langsung mengubahnya menjadi Pandas DataFrame
            df = client.query_df(f"SELECT * FROM {ch_table}")
            st.success(f"Berhasil menarik {len(df)} baris data dari database!")
            st.dataframe(df.head()) # Tampilkan preview data
        except Exception as e:
            st.error(f"Gagal terhubung ke database: {e}")

st.write("---")

# ==========================================
# TOMBOL MULAI EKSEKUSI
# ==========================================
if st.button("Mulai Isi Form"):
    if not url_form or not url_form.startswith("http"):
        st.error("❌ Link Google Form tidak valid! Pastikan diawali dengan https://")
    elif uploaded_file is None:
        st.warning("⚠️ Silakan upload file Excel terlebih dahulu!")
    else:
        try:
            # Membaca file Excel langsung dari memory Streamlit
            df = pd.read_excel(uploaded_file)

            if "Nama" in df.columns:
                daftar_nama = df["Nama"].dropna().astype(str).tolist()
            else:
                daftar_nama = df.iloc[:, 1].dropna().astype(str).tolist()

            jumlah_pengiriman = len(daftar_nama)
            st.success(f"📊 Total responden yang akan diisi: {jumlah_pengiriman} orang.")

            if jumlah_pengiriman == 0:
                st.error("❌ Kolom nama kosong! Pastikan file Excel diisi dengan benar.")
                st.stop()

          # ==========================================
            # 2. KONFIGURASI BROWSER SELENIUM UNTUK CLOUD
            # ==========================================
            st.info("🔧 Menyiapkan bot dan membuka browser di background...")
            
            import os # Pastikan library os di-import
            
            chrome_options = Options()
            chrome_options.add_argument("--headless=new") 
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--lang=id")

            # MENGATASI ERROR VERSI CHROMEDRIVER
            # Jika file chromedriver ada di sistem linux (Streamlit Cloud), gunakan file tersebut
            if os.path.exists("/usr/bin/chromedriver"):
                service = Service("/usr/bin/chromedriver")
            # Jika dijalankan di komputer lokalmu, tetap gunakan webdriver_manager
            else:
                service = Service(ChromeDriverManager().install())

            driver = webdriver.Chrome(service=service, options=chrome_options)
            # Progress bar untuk memantau proses
            progress_bar = st.progress(0)
            status_text = st.empty()

            # ==========================================
            # 3. PROSES PENGISIAN OTOMATIS
            # ==========================================
            for i in range(1, jumlah_pengiriman + 1):
                nama_saat_ini = daftar_nama[i - 1]
                status_text.text(f"⏳ Memproses responden ke-{i}/{jumlah_pengiriman}: {nama_saat_ini}...")

                kolom_jawaban_idx = 2
                driver.get(url_form + "?hl=id")
                time.sleep(3)

                try:
                    halaman_aktif = 1
                    while True:
                        semua_pertanyaan = driver.find_elements(By.XPATH, '//div[@role="listitem"]')

                        for pertanyaan in semua_pertanyaan:
                            try:
                                teks_pertanyaan = pertanyaan.text.lower()
                                kolom_teks = pertanyaan.find_elements(By.XPATH, './/input[@type="text"]')
                                opsi_opsi = pertanyaan.find_elements(By.XPATH, './/div[@role="radio"]')

                                if kolom_teks:
                                    if "nama" in teks_pertanyaan:
                                        kolom_teks[0].clear()
                                        kolom_teks[0].send_keys(nama_saat_ini)
                                        time.sleep(0.2)
                                    else:
                                        if kolom_jawaban_idx < df.shape[1]:
                                            nilai_jawaban = df.iloc[i - 1, kolom_jawaban_idx]
                                            if pd.notna(nilai_jawaban) and str(nilai_jawaban).strip() != "-":
                                                kolom_teks[0].clear()
                                                kolom_teks[0].send_keys(str(nilai_jawaban).strip())
                                                time.sleep(0.2)
                                            kolom_jawaban_idx += 1

                                elif opsi_opsi:
                                    if kolom_jawaban_idx < df.shape[1]:
                                        nilai_jawaban = df.iloc[i - 1, kolom_jawaban_idx]
                                        if pd.notna(nilai_jawaban) and str(nilai_jawaban).strip() not in ["-", "nan", "None", ""]:
                                            nilai_str = str(nilai_jawaban).strip().lower()
                                            ditemukan = False

                                            for opsi in opsi_opsi:
                                                teks_opsi = ""
                                                aria_lbl = opsi.get_attribute("aria-label")
                                                if aria_lbl:
                                                    teks_opsi = aria_lbl.strip().lower()
                                                else:
                                                    try:
                                                        parent = opsi.find_element(By.XPATH, "./..")
                                                        teks_opsi = parent.text.strip().lower()
                                                    except:
                                                        teks_opsi = opsi.text.strip().lower()

                                                match = False
                                                if nilai_str == teks_opsi:
                                                    match = True
                                                elif nilai_str.isdigit() and (
                                                    teks_opsi == nilai_str or teks_opsi.startswith(nilai_str + ".") or teks_opsi.startswith(nilai_str + " -") or teks_opsi.startswith(nilai_str + " ")
                                                ):
                                                    match = True
                                                elif len(nilai_str) > 2 and nilai_str in teks_opsi and not ("tidak" in teks_opsi and "tidak" not in nilai_str) and not ("sangat" in teks_opsi and "sangat" not in nilai_str):
                                                    match = True

                                                if match:
                                                    driver.execute_script("arguments[0].click();", opsi)
                                                    ditemukan = True
                                                    break

                                            if not ditemukan and opsi_opsi:
                                                driver.execute_script("arguments[0].click();", opsi_opsi[0])

                                        kolom_jawaban_idx += 1
                                        time.sleep(0.2)

                            except Exception:
                                pass

                        tombol_berikutnya = driver.find_elements(By.XPATH, '//span[contains(text(), "Berikutnya") or contains(text(), "Next")]')
                        tombol_kirim = driver.find_elements(By.XPATH, '//span[contains(text(), "Kirim") or contains(text(), "Submit")]')

                        if tombol_berikutnya:
                            driver.execute_script("arguments[0].click();", tombol_berikutnya[0])
                            time.sleep(2.0)
                            halaman_aktif += 1
                        elif tombol_kirim:
                            driver.execute_script("arguments[0].click();", tombol_kirim[0])
                            break
                        else:
                            break

                except Exception as e:
                    st.error(f"❌ Gagal pada responden {nama_saat_ini}. Lanjut ke data berikutnya.")
                
                # Update progress bar
                progress_bar.progress(i / jumlah_pengiriman)
                time.sleep(2)

            driver.quit()
            status_text.text("✅ Proses Selesai!")
            st.balloons()
            st.success(f"🎉 Semua {jumlah_pengiriman} proses pengisian formulir selesai!")

        except Exception as e:
            st.error(f"Terjadi kesalahan sistem: {e}")
