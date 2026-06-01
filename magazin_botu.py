import os
import time
import requests
from bs4 import BeautifulSoup
import re

# =====================================================================
# CONFIGURATION / AYARLAR
# =====================================================================
# GitHub Secrets'tan gelen anahtarlar
XF_API_KEY = os.environ.get("XF_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
# Super User anahtar kullandığın için konuyu açacak adminin ID'si (Varsayılan: 1)
XF_API_USER_ID = os.environ.get("XF_API_USER_ID", "1") 

XF_API_URL = "https://www.magazin.biz.tr/api/threads"
NODE_ID = 26  
HAFIZA_DOSYASI = "used_titles.txt"
# =====================================================================

def hafiza_oku():
    """Daha önce açılmış konuların başlıklarını hafıza dosyasından çeker."""
    if not os.path.exists(HAFIZA_DOSYASI):
        return set()
    with open(HAFIZA_DOSYASI, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

def hafiza_yaz(baslik):
    """Yeni açılan konunun başlığını hafızaya kaydeder."""
    with open(HAFIZA_DOSYASI, "a", encoding="utf-8") as f:
        f.write(baslik.strip() + "\n")

def onedio_rss_cek():
    """Onedio RSS servisinden güncel haberleri çeker ve magazin olanları filtreler."""
    url = "https://onedio.com/support/rss.xml"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    haberler = []
    
    magazin_kelimeleri = ["magazin", "ünlü", "unlu", "oyuncu", "dizi", "fenomen", "şarkıcı", "sarkici", "dedikodu", "televizyon", "sosyal medya"]
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            print(f"Onedio RSS bağlantı hatası! Durum Kodu: {response.status_code}")
            return haberler
            
        soup = BeautifulSoup(response.text, "xml")
        items = soup.find_all("item")
        
        for item in items:
            category_tags = item.find_all("category")
            title_tag = item.find("title")
            desc_tag = item.find("description")
            
            kategoriler_metni = " ".join([cat.get_text().lower() for cat in category_tags])
            baslik_metni = title_tag.get_text().lower() if title_tag else ""
            
            # Kategoride veya başlıkta magazin kelimeleri geçiyor mu kontrolü
            is_magazin = any(kelime in kategoriler_metni or kelime in baslik_metni for kelime in magazin_kelimeleri)
            
            if is_magazin:
                link_tag = item.find("link")
                if title_tag and link_tag:
                    baslik = title_tag.get_text().strip()
                    link = link_tag.get_text().strip()
                    
                    desc = desc_tag.get_text().strip() if desc_tag else ""
                    if desc:
                        # Olası hatalara karşı güvenli HTML temizliği
                        desc = BeautifulSoup(desc, "html.parser").get_text().strip()
                    
                    if baslik not in [h['baslik'] for h in haberler]:
                        haberler.append({
                            "baslik": baslik,
                            "link": link,
                            "detay": desc
                        })
    except Exception as e:
        print(f"RSS Çekme Hatası: {e}")
    
    return haberler

def gorsel_bul(haber_url):
    """Haberin orijinal sayfasından og:image (kapak görseli) linkini bulur."""
    gorsel = None
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        sayfa_icerigi = requests.get(haber_url, headers=headers, timeout=10).text
        
        # Meta etiketlerindeki görsel linkini yakalamak için esnek regex yapısı
        bulunan_gorseller = re.findall(r'<meta[^>]*?property=["\']og:image["\'][^>]*?content=["\']([^"\']+)["\']', sayfa_icerigi)
        if not bulunan_gorseller:
            bulunan_gorseller = re.findall(r'<meta[^>]*?content=["\']([^"\']+)["\'][^>]*?property=["\']og:image["\']', sayfa_icerigi)
            
        if bulunan_gorseller:
            gorsel = bulunan_gorseller[0]
    except:
        pass
    return gorsel

def gemini_magazin_yaz(baslik, kaynak_detay):
    """Gemini 2.5-Flash API'sini kullanarak haberi özgün forum konusuna dönüştürür."""
    if not GEMINI_API_KEY:
        print("Hata: GEMINI_API_KEY bulunamadı!")
        return None
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    
    prompt
