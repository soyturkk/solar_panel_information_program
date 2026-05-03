import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np

# --- 1. SAYFA AYARLARI ---
st.set_page_config(page_title="Güneş Termal Analiz", layout="wide")

# --- 2. KULLANICI GİRİŞLERİ (SIDEBAR) ---
st.sidebar.header("🏠 Sistem Parametreleri")

sehir_coords = {
    "Adana": {"lat": 37.00, "lon": 35.32},
    "Trabzon": {"lat": 41.00, "lon": 39.72},
    "İstanbul": {"lat": 41.01, "lon": 28.97},
    "Ankara": {"lat": 39.93, "lon": 32.85}
}

sehir = st.sidebar.selectbox("Şehir Seçiniz", list(sehir_coords.keys()))
panel_sayisi = st.sidebar.slider("Panel Sayısı", 1, 6, 2)
depo_hacmi = st.sidebar.number_input("Depo Hacmi (Litre)", value=200)
yalitim_cm = st.sidebar.slider("Yalıtım Kalınlığı (cm)", 1, 15, 5)

st.sidebar.markdown("---")
st.sidebar.header("🚿 Kullanım Alışkanlığı")
kisi_sayisi = st.sidebar.number_input("Akşam duş alacak kişi sayısı", value=2, min_value=0)
dus_saati = st.sidebar.slider("Duş saati (Akşam)", 18, 23, 20)

# --- ANA EKRAN BAŞLIĞI ---
st.title("☀️ Güneş Enerjisi ve Termal Depolama Simülasyonu")

# --- 3. DIŞ VERİ ÇEKME ---
@st.cache_data
def hava_durumu_getir(lat, lon):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,shortwave_radiation&forecast_days=1"
    response = requests.get(url).json()
    return response['hourly']

data = hava_durumu_getir(sehir_coords[sehir]['lat'], sehir_coords[sehir]['lon'])
saatlik_radyasyon = data['shortwave_radiation']
saatlik_dis_sicaklik = data['temperature_2m']

# --- 4. HESAPLAMA MOTORU ---
sistem_verimi = 0.45 
aci_duzeltme = 0.85
h_dis = 10 
k_yalitkan = 0.04 
panel_birim_alan = 1.9 

r_toplam = (1 / h_dis) + (yalitim_cm / 100 / k_yalitkan)
u_degeri = 1 / r_toplam
yuzey_alani = 1.5 + (depo_hacmi / 500)
su_sicakligi = 18.0 
sicaklik_gecmisi = []

# Sankey ve Metrikler için Sayaçlar
toplam_kazanc_joule = 0
toplam_kayip_joule = 0

for i in range(24):
    # Giriş Isısı (Güneş)
    q_in = (panel_sayisi * panel_birim_alan) * saatlik_radyasyon[i] * sistem_verimi * aci_duzeltme * 3600
    toplam_kazanc_joule += q_in
    
    # Çıkış Isısı (Yalıtım Kaybı)
    q_out = u_degeri * yuzey_alani * (su_sicakligi - saatlik_dis_sicaklik[i]) * 3600
    toplam_kayip_joule += max(0, q_out) # Sadece dışarı giden ısıyı kayıp sayıyoruz
    
    # Duş Kullanımı
    if i == dus_saati:
        harcanan_su = kisi_sayisi * 50
        if harcanan_su > 0:
            if harcanan_su > depo_hacmi: harcanan_su = depo_hacmi
            su_sicakligi = ((depo_hacmi - harcanan_su) * su_sicakligi + (harcanan_su * 18)) / depo_hacmi

    # Net Enerji Dengesi
    net_q = q_in - q_out
    delta_t = net_q / (depo_hacmi * 4186)
    su_sicakligi += delta_t
    
    # Sınırlandırmalar
    if su_sicakligi > 99.0: su_sicakligi = 99.0
    if su_sicakligi < 18.0: su_sicakligi = 18.0
    sicaklik_gecmisi.append(round(su_sicakligi, 2))

# --- 5. GÖRSELLEŞTİRME (Çizgi Grafik) ---
df = pd.DataFrame({
    "Saat": [f"{h:02d}:00" for h in range(24)],
    "Su Sıcaklığı (°C)": sicaklik_gecmisi,
    "Dış Hava Sıcaklığı (°C)": saatlik_dis_sicaklik
})

fig = px.line(df, x="Saat", y=["Su Sıcaklığı (°C)", "Dış Hava Sıcaklığı (°C)"],
              title=f"{sehir} - Günlük Sıcaklık Değişim Analizi",
              color_discrete_map={"Su Sıcaklığı (°C)": "red", "Dış Hava Sıcaklığı (°C)": "blue"})
st.plotly_chart(fig, use_container_width=True)

# Özet Metrikler
st.subheader("📊 Özet Analiz")
c1, c2, c3 = st.columns(3)
c1.metric("Max Su Sıcaklığı", f"{max(sicaklik_gecmisi)} °C")
c2.metric("Günlük Toplam Kazanç", f"{toplam_kazanc_joule/3600000:.2f} kWh")
c3.metric("Ekonomik Kazanç (TL)", f"{(toplam_kazanc_joule/3600000)*2.6:.2f} TL")

# --- 6. YENİ BÖLÜM: ENERJİ AKIŞI (SANKEY DIAGRAM) ---
st.markdown("---")
st.subheader("📊 Günlük Toplam Enerji Akışı (Sankey Analizi)")
st.write("Güneşten gelen enerjinin ne kadarının depoda kaldığını ve ne kadarının çevreye 'eriyerek' gittiğini görün.")

q_in_kwh = toplam_kazanc_joule / 3600000
q_out_kwh = toplam_kayip_joule / 3600000
q_net_kwh = max(0, q_in_kwh - q_out_kwh)

fig_sankey = go.Figure(data=[go.Sankey(
    node = dict(
      pad = 20,
      thickness = 30,
      line = dict(color = "black", width = 0.5),
      label = [
          f"Güneş Girişi ({q_in_kwh:.1f} kWh)", 
          f"Isı Kaybı ({q_out_kwh:.1f} kWh)", 
          f"Faydalı Isı ({q_net_kwh:.1f} kWh)"
      ],
      color = ["#FFD700", "#FF4B4B", "#00CC96"] # Altın, Kırmızı, Yeşil
    ),
    link = dict(
      source = [0, 0], # Girişten çıkışlara
      target = [1, 2], # 1: Kayıp, 2: Depo
      value = [q_out_kwh, q_net_kwh]
  ))])

fig_sankey.update_layout(height=400)
st.plotly_chart(fig_sankey, use_container_width=True)

# --- 7. ISI HARİTASI (CONTOUR PLOT) ---
st.markdown("---")
st.subheader("🗺️ Sistem Tasarım ve Optimizasyon Haritası")

p_ekseni = np.linspace(1, 6, 20) 
y_ekseni = np.linspace(1, 15, 20)
P, Y = np.meshgrid(p_ekseni, y_ekseni)

# Harita için gerçekçi etkin radyasyon hesabı
gunesli_saatler = [r for r in saatlik_radyasyon if r > 0]
etkin_rad = sum(gunesli_saatler) / len(gunesli_saatler) if gunesli_saatler else 0

def simule_max_temp(p, y):
    u_lokal = 1 / ((1/10) + (y/100/0.04))
    # Ortalama güneşli saat süresince (yaklaşık 10 saat) biriken ısı
    isi_kazanc = (p * 1.9) * etkin_rad * sistem_verimi * aci_duzeltme
    isi_kayip = u_lokal * 1.8 * (40 - 20)
    t_artis = (isi_kazanc - isi_kayip) * 8 * 3600 / (depo_hacmi * 4186)
    return min(max(18 + t_artis, 18), 99)

Z = np.vectorize(simule_max_temp)(P, Y)

fig_contour = go.Figure(data=go.Contour(
    z=Z, x=p_ekseni, y=y_ekseni, 
    colorscale='Hot',
    contours=dict(showlabels=True, labelfont=dict(size=12, color='white')),
    colorbar=dict(title="Max T (°C)")
))

fig_contour.update_layout(xaxis_title="Panel Sayısı (Adet)", yaxis_title="Yalıtım Kalınlığı (cm)", height=600)
st.plotly_chart(fig_contour, use_container_width=True)

st.info("💡 Mühendislik Notu: Sankey diyagramı 24 saatlik toplam enerji dengesini gösterirken; Isı Haritası farklı donanım kombinasyonlarının performans limitlerini analiz etmenizi sağlar.")