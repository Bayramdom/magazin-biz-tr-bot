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
    
    prompt = f"""
    Sen popüler bir magazin sitesinin baş editörüsün. Sana verilen magazin haberini okuyarak; ilgi çekici, akıcı, merak uyandıran ve tamamen özgün (copy-paste olmayan) bir Türkçe magazin forumu konusu yaz.
    
    KAYNAK BİLGİLER:
    Haber Başlığı: {baslik}
    Haber Özeti: {kaynak_detay}
    
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
        else:
            print(f"Gemini API Hatası! Kod: {response.status_code}, Cevap: {response.text}")
            return None
    except Exception as e:
        print(f"Gemini bağlantı hatası: {e}")
        return None

def konu_ac(baslik, icerik, node_id):
    """XenForo REST API'sini kullanarak forumda JSON formatında konuyu açar."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "XF-Api-Key": XF_API_KEY,
        "XF-Api-User": XF_API_USER_ID,
        "Content-Type": "application/json",  # JSON kabul etmesi için zorunlu başlık
        "Accept": "application/json"
    }
    
    # Sunucu kaprislerini engellemek için string ve int tiplerini kesinleştiriyoruz
    data = {
        "node_id": int(node_id),
        "title": str(baslik).strip(),
        "message": str(icerik).strip()
    }
    try:
        # json=data kullanarak içeriği ham form verisi yerine JSON paketi olarak atıyoruz
        response = requests.post(XF_API_URL, headers=headers, json=data, timeout=25)
        
        if response.status_code == 200:
            print(f"Başarılı şekilde eklendi: {baslik}")
            return True
        else:
            print(f"XenForo API Hatası ({response.status_code}) - Mesaj Formatı veya Yetki Sorunu!")
            print(f"Sunucu Yanıtı: {response.text}")
            return False
    except Exception as e:
        print(f"XenForo bağlantı hatası: {e}")
        return False

def ana_fonksiyon():
    print("Onedio Resmi RSS kanalı taranıyor...")
    magazin_haberleri = onedio_rss_cek()
    
    if not magazin_haberleri:
        print("Güncel magazin haberi bulunamadı veya RSS'e erişilemedi.")
        return

    hafiza = hafiza_oku()
    
    for haber in magazin_haberleri:
        baslik = haber["baslik"].strip()
        haber_linki = haber["link"]
        detay_metni = haber["detay"]
        
        # Mükerrer konu açmamak için hafıza kontrolü
        if baslik in hafiza:
            continue
            
        print(f"Yeni magazin haberi işleniyor: {baslik}")
        
        print("Gemini içerik üretiyor...")
        yapay_zeka_icerigi = gemini_magazin_yaz(baslik, detay_metni)
        
        # KONTROL: Gemini o anlık yoğunluktan (503) dolayı boş döndüyse işlemi iptal et
        if not yapay_zeka_icerigi:
            print("Gemini içerik üretemedi (API Yoğun veya Hatalı). Forumda boş konu açılmaması için bu tur pas geçiliyor...")
            return  
        
        # Orijinal görseli bulup BBCode formatında metnin en üstüne ekleme
        canli_gorsel_url = gorsel_bul(haber_linki)
        if canli_gorsel_url:
            yapay_zeka_icerigi = f"[IMG]{canli_gorsel_url}[/IMG]\n\n{yapay_zeka_icerigi}"
        
        time.sleep(3)
        
        # XenForo'da konuyu açmayı dene. JSON uyumlu yeni sisteme göre çalışır.
        if not konu_ac(baslik, yapay_zeka_icerigi, NODE_ID):
            print("Konu açılamadı, süreç durduruldu.")
            return  
            
        # İşlem başarılıysa hafızaya yaz ve bu çalıştırma için döngüden çık (Her çalıştırmada 1 konu)
        hafiza_yaz(baslik)
        break 

if __name__ == "__main__":
    ana_fonksiyon()
