import os
import time
import requests
from bs4 import BeautifulSoup
import re

# =====================================================================
# CONFIGURATION / AYARLAR
# =====================================================================
XF_API_KEY = os.environ.get("XF_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Doğrudan magazin kullanıcısının ID'si (6746) sabit
XF_API_USER_ID = "6746" 

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

def onedio_magazin_sayfasi_cek():
    """Doğrudan onedio.com/magazin sayfasını kazıyarak en güncel magazin haberlerini toplar."""
    url = "https://onedio.com/magazin"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    haberler = []
    
    try:
        response = requests.get(url, headers=headers, timeout=12)
        if response.status_code != 200:
            print(f"Onedio Magazin sayfasına erişilemedi! Durum Kodu: {response.status_code}")
            return haberler
            
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Onedio'nun modern arayüzündeki haber linklerini ve başlıklarını yakalıyoruz
        # Sitedeki tüm makale linklerini süzer
        links = soup.find_all("a", href=re.compile(r"/-haberleri/|-\d+$"))
        
        for link in links:
            href = link.get("href", "")
            # Tam URL haline getiriyoruz
            if href.startswith("/"):
                tam_url = "https://onedio.com" + href
            elif href.startswith("http"):
                tam_url = href
            else:
                continue
                
            # Linkin içindeki metni veya img alt etiketini başlık olarak alıyoruz
            baslik_metni = link.get_text().strip()
            if not baslik_metni and link.find("img"):
                baslik_metni = link.find("img").get("alt", "").strip()
                
            # Kısa manşetleri veya boş olanları eliyoruz
            if len(baslik_metni) < 15:
                continue
                
            # Mükerrer eklemeyi önle
            if tam_url not in [h['link'] for h in haberler] and baslik_metni not in [h['baslik'] for h in haberler]:
                # Detay metni sayfa kazımada ilk etapta boş kalabilir, Gemini başlığa göre de harika üretebiliyor
                haberler.append({
                    "baslik": baslik_metni,
                    "link": tam_url,
                    "detay": baslik_metni  
                })
                
    except Exception as e:
        print(f"Sayfa Kazıma Hatası: {e}")
        
    return haberler

def gorsel_bul(haber_url):
    """Haberin orijinal sayfasından og:image (kapak görseli) linkini bulur."""
    gorsel = None
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        sayfa_icerigi = requests.get(haber_url, headers=headers, timeout=10).text
        
        bulunan_gorseller = re.findall(r'<meta[^>]*?property=["\']og:image["\'][^>]*?content=["\']([^"\']+)["\']', sayfa_icerigi)
        if not bulunan_gorseller:
            bulunan_gorseller = re.findall(r'<meta[^>]*?content=["\']([^"\']+)["\'][^>]*?property=["\']og:image["\']', sayfa_icerigi)
            
        if bulunan_gorseller:
            gorsel = bulunan_gorseller[0]
    except:
        pass
    return gorsel

def gemini_magazin_yaz(baslik, kaynak_detay):
    """Gemini API'sini kullanır. 429 (Kota) hatası alırsa otomatik olarak bekleyip tekrar dener."""
    if not GEMINI_API_KEY:
        print("Hata: GEMINI_API_KEY bulunamadı!")
        return None
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    
    prompt = f"""
    Sen popüler bir magazin sitesinin baş editörüsün. Sana verilen güncel magazin olayını okuyarak; ilgi çekici, akıcı, merak uyandıran, dedikodu dozajı yerinde ve tamamen özgün bir Türkçe magazin forumu konusu yaz.
    
    Haber Başlığı / Detayı: {baslik}
    
    KURALLAR:
    1. İçeriği zenginleştirerek en az 2-3 paragraf uzunluğunda okuması keyifli bir metin hazırla.
    2. Forum diline uygun, okuyucuya hitap eden ama seviyeli bir üslup kullan.
    3. Metnin sonuna "Siz bu konuda ne düşünüyorsunuz? Yorumlarda buluşalım!" gibi forumda etkileşim artıracak bir cümle ekle.
    4. Asla markdown kod bloku (```) veya HTML tagları ekleme. Resmi BBCode formatını bozma.
    """
    
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    
    for deneme in range(1, 4):
        try:
            response = requests.post(url, headers=headers, json=data, timeout=20)
            if response.status_code == 200:
                res_json = response.json()
                return res_json['candidates'][0]['content']['parts'][0]['text'].strip()
            elif response.status_code == 429:
                bekleme_suresi = deneme * 20  
                print(f"Gemini Kotası Dolmuş (429). {bekleme_suresi} saniye sonra otomatik tekrar denenecek (Deneme {deneme}/3)...")
                time.sleep(bekleme_suresi)
            else:
                print(f"Gemini API Hatası! Kod: {response.status_code}")
                return None
        except Exception as e:
            print(f"Gemini bağlantı hatası: {e}")
            time.sleep(5)
            
    return None

def konu_ac(baslik, icerik, node_id):
    """XenForo REST API'sine standart form verisi formatında güvenli istek atar."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "XF-Api-Key": str(XF_API_KEY).strip(),
        "XF-Api-User": str(XF_API_USER_ID).strip()
    }
    
    payload = {
        "node_id": int(node_id),
        "title": str(baslik).strip(),
        "message": str(icerik).strip()
    }
    
    try:
        response = requests.post(XF_API_URL, headers=headers, data=payload, timeout=25)
        if response.status_code == 200:
            print(f"Başarılı şekilde eklendi: {baslik}")
            return True
        else:
            print(f"XenForo API Hatası ({response.status_code})")
            print(f"Sunucu Yanıtı: {response.text}")
            return False
    except Exception as e:
        print(f"XenForo bağlantı hatası: {e}")
        return False

def ana_fonksiyon():
    print("Onedio MAGAZİN sayfası canlı olarak taranıyor...")
    magazin_haberleri = onedio_magazin_sayfasi_cek()
    
    if not magazin_haberleri:
        print("Magazin sayfasından haber çekilemedi.")
        return

    hafiza = hafiza_oku()
    
    for haber in magazin_haberleri:
        baslik = haber["baslik"].strip()
        haber_linki = haber["link"]
        detay_metni = haber["detay"]
        
        if baslik in hafiza:
            continue
            
        print(f"Yeni saf magazin haberi işleniyor: {baslik}")
        
        print("Gemini içerik üretiyor...")
        yapay_zeka_icerigi = gemini_magazin_yaz(baslik, detay_metni)
        
        if not yapay_zeka_icerigi:
            print("Gemini içerik üretemedi. Süreç pas geçiliyor...")
            return  
        
        canli_gorsel_url = gorsel_bul(haber_linki)
        if canli_gorsel_url:
            yapay_zeka_icerigi = f"[IMG]{canli_gorsel_url}[/IMG]\n\n{yapay_zeka_icerigi}"
        
        time.sleep(3)
        
        if not konu_ac(baslik, yapay_zeka_icerigi, NODE_ID):
            print("Konu açılamadı, süreç durduruldu.")
            return  
            
        hafiza_yaz(baslik)
        break 

if __name__ == "__main__":
    ana_fonksiyon()
