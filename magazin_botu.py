import os
import time
import requests
from bs4 import BeautifulSoup
import re

# =====================================================================
# CONFIGURATION / AYARLAR
# =====================================================================
# GitHub Secrets'tan güvenli şekilde çekiyoruz:
XF_API_KEY = os.environ.get("XF_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Hedef Forum Ayarları
XF_API_URL = "https://www.magazin.biz.tr/api/threads"
NODE_ID = 26  # magazin-haberleri.26 kategorisi için ID
HAFIZA_DOSYASI = "used_titles.txt"
# =====================================================================

def hafiza_oku():
    if not os.path.exists(HAFIZA_DOSYASI):
        return set()
    with open(HAFIZA_DOSYASI, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

def hafiza_yaz(baslik):
    with open(HAFIZA_DOSYASI, "a", encoding="utf-8") as f:
        f.write(baslik + "\n")

def onedio_magazin_cek():
    url = "https://onedio.com/magazin"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    haberler = []
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            return haberler
            
        soup = BeautifulSoup(response.text, "html.parser")
        
        for article in soup.find_all("article"):
            link_tag = article.find("a", href=True)
            title_tag = article.find(["h2", "h3", "span"], class_=re.compile(r"title|headline", re.I))
            
            if link_tag and (title_tag or link_tag.get_text()):
                baslik = title_tag.get_text().strip() if title_tag else link_tag.get_text().strip()
                href = link_tag["href"]
                
                full_url = href if href.startswith("http") else f"https://onedio.com{href}"
                
                if baslik and full_url not in [h['link'] for h in haberler]:
                    haberler.append({"baslik": baslik, "link": full_url})
    except Exception as e:
        print(f"Onedio çekme hatası: {e}")
    
    return haberler

def haber_detayini_ve_resmini_bul(haber_url):
    gorsel = None
    detay_metni = ""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        # Sunucuyu yormamak için detay sayfasına gitmeden önce kısa mola
        time.sleep(5)
        sayfa_icerigi = requests.get(haber_url, headers=headers, timeout=10).text
        
        bulunan_gorseller = re.findall(r'<meta[^>]*property=["\']og:image["\'][^>]*content=["\']([^"\']+)["\']', sayfa_icerigi)
        if bulunan_gorseller:
            gorsel = bulunan_gorseller[0]
            
        bulunan_ozet = re.findall(r'<meta[^>]*property=["\']og:description["\'][^>]*content=["\']([^"\']+)["\']', sayfa_icerigi)
        if bulunan_ozet:
            detay_metni = bulunan_ozet[0].strip()
            
    except Exception as e:
        print(f"Siteden detay veri çekme hatası: {e}")
    return gorsel, detay_metni

def gemini_magazin_yaz(baslik, kaynak_detay):
    if not GEMINI_API_KEY:
        return f"{baslik} hakkındaki magazin gelişmeleri yakından takip ediliyor."
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    
    haber_kaynagi = f"Haber Başlığı: {baslik}\nHaber Detayı/Özeti: {kaynak_detay}" if kaynak_detay else f"Haber Başlığı: {baslik}"
    
    prompt = f"""
    Sen popüler bir magazin sitesinin baş editörüsün. Sana verilen magazin haberini okuyarak; ilgi çekici, akıcı, merak uyandıran ve tamamen özgün (copy-paste olmayan) bir Türkçe magazin forumu konusu yaz.
    
    KAYNAK BİLGİLER:
    {haber_kaynagi}
    
    KURALLAR:
    1. İçeriği zenginleştirerek en az 2-3 paragraf uzunluğunda okuması keyifli bir metin hazırla.
    2. Forum diline uygun, okuyucuya hitap eden ama seviyeli bir üslup kullan.
    3. Metnin sonuna "Siz bu konuda ne düşünüyorsunuz? Yorumlarda buluşalım!" gibi forumda etkileşim artıracak bir cümle ekle.
    4. Asla markdown kod bloku (```) veya HTML tagları ekleme. Resmi BBCode formatını bozma.
    """
    
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=20)
        if response.status_code == 200:
            res_json = response.json()
            return res_json['candidates'][0]['content']['parts'][0]['text'].strip()
    except Exception as e:
        print(f"Gemini bağlantı hatası: {e}")
        
    return f"{baslik} dünyasından en sıcak ve en yeni dedikodular geldikçe paylaşmaya devam edeceğiz. Takipte kalın!"

def konu_ac(baslik, icerik, node_id):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json",
        "XF-Api-Key": XF_API_KEY
    }
    data = {
        "node_id": node_id,
        "title": baslik,
        "message": icerik
    }
    try:
        response = requests.post(XF_API_URL, headers=headers, data=data, timeout=25)
        if response.status_code == 200:
            print(f"Başarılı şekilde eklendi: {baslik}")
            return True
        else:
            print(f"XenForo API Hatası ({response.status_code}) - {response.text}")
            return False
    except Exception as e:
        print(f"XenForo baglanti hatasi: {e}")
        return False

def ana_fonksiyon():
    print("Onedio Magazin haberleri taranıyor...")
    magazin_haberleri = onedio_magazin_cek()
    
    if not magazin_haberleri:
        print("Yeni haber bulunamadı veya siteye erişilemedi.")
        return

    hafiza = hafiza_oku()
    
    for haber in magazin_haberleri:
        baslik = haber["baslik"]
        haber_linki = haber["link"]
        
        if baslik in hafiza:
            continue
            
        print(f"Yeni magazin haberi işleniyor: {baslik}")
        
        # Sunucu güvenliği (Firewall) koruması için 15 saniyelik derin mola
        print("Sunucu güvenliği koruması için bekletiliyor...")
        time.sleep(15)
        
        canli_gorsel_url, haber_detay_metni = haber_detayini_ve_resmini_bul(haber_linki)
        
        print("Gemini içerik üretiyor...")
        yapay_zeka_icerigi = gemini_magazin_yaz(baslik, haber_detay_metni)
        
        if canli_gorsel_url:
            yapay_zeka_icerigi = f"[IMG]{canli_gorsel_url}[/IMG]\n\n{yapay_zeka_icerigi}"
        
        # Konuyu açmadan önce son bir kez daha insansı bekleme süresi
        time.sleep(10)
        
        if konu_ac(baslik, yapay_zeka_icerigi, NODE_ID):
            hafiza_yaz(baslik)
            print("Sunucu sağlığı için bu turluk işlem tamamlandı, bot kapatılıyor.")
            break # Tek seferde sadece 1 konu açıp çıkacak, sunucu asla yorulmayacak.

if __name__ == "__main__":
    ana_fonksiyon()
