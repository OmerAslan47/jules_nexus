import re
from typing import Any, Dict, List, Optional, Tuple

# Pre-compile regex token extractors at module level to optimize tool selection speed
WORD_REGEX = re.compile(r"[a-zçğıöşü0-9]{3,}")
DESC_WORD_REGEX = re.compile(r"[a-zçğıöşü0-9]{4,}")


class SmartToolSelector:
    """
    87 aracın tamamını (~6.000 token) her soruda LLM'e gönderip sistemi yavaşlatmak yerine,
    kullanıcının Türkçe cümlesini milisaniyeler içinde analiz ederek:
    1. Doğrudan arayüz/mod komutlarını (Sessiz mod imleci aç/kapat, Ekrana yaz, Ekranı temizle) yakalar.
    2. Normal sohbet cümlelerinde 0 araç göndererek yanıt süresini 0.6 saniyeye indirir.
    3. İşlem gerektiren cümlelerde yalnızca en alakalı 4 aracı seçip LLM'e sunar.
    """

    # Kullanıcının yanıtı ekranda yazılı olarak da görmek istediğini belirten ifadeler
    SHOW_TEXT_PATTERNS = (
        "ekrana yaz",
        "ekranda göster",
        "ekrana yansıt",
        "ekrana dök",
        "yazılı göster",
        "yazılı olarak",
        "ekran çıktısı",
        "ekranda göreyim",
        "listeyi göster",
        "kodunu yaz",
        "kodu göster",
    )

    # Ekrandaki yazıyı temizleme ifadeleri
    CLEAR_SCREEN_PATTERNS = (
        "ekranı temizle",
        "yazıyı kapat",
        "yazıyı kaldır",
        "yazıları sil",
        "ekranı sıfırla",
    )

    # Sessiz mod + Yazı yazma imlecini açma ifadeleri
    ENABLE_SILENT_CURSOR_PATTERNS = (
        "sessiz modu aç",
        "sessiz moda geç",
        "kütüphane modunu aç",
        "kütüphane moduna geç",
        "imleci aç",
        "yazı yazacağım",
        "yazarak konuşalım",
        "klavyeyi aç",
        "sessize geç",
        "sessize al",
    )

    # Sesli moda dönme + İmleci kapatma ifadeleri
    ENABLE_VOICE_MODE_PATTERNS = (
        "sesli modu aç",
        "sesli moda geç",
        "benle sesli konuş",
        "benimle sesli konuş",
        "sesli konuş",
        "imleci kapat",
        "imleci gizle",
        "sesini aç",
    )

    # Uygulamayı kapatma ifadeleri
    EXIT_APP_PATTERNS = (
        "uygulamayı kapat",
        "kendini kapat",
        "sistemi kapat",
        "nexus kapan",
        "görüşürüz nexus",
    )

    # Sadece sesli komutla açılan UserProfile & Yetki Matrisi Ekranı ifadeleri
    OPEN_USER_PROFILE_PATTERNS = (
        "kullanıcı profilini aç",
        "kullanıcı profili aç",
        "kullanıcı profili",
        "user profile aç",
        "userprofile aç",
        "user profilini aç",
        "user profili aç",
        "user profili",
        "user profil",
        "profilleri aç",
        "profilimi aç",
        "kullanıcı ekranını aç",
        "yetki ekranını aç",
        "yetkileri aç",
        "kullanıcı ayarlarını aç",
    )

    CLOSE_USER_PROFILE_PATTERNS = (
        "kullanıcı profilini kapat",
        "user profile kapat",
        "userprofile kapat",
        "user profilini kapat",
        "yetki ekranını kapat",
        "profili kapat",
    )

    # Kibrit Kutusu - Mini Ekran İzleme Modu ifadeleri
    MINI_MODE_PATTERNS = (
        "ekranımı izle",
        "ekranı izle",
        "ekranımı takip et",
        "mini moda geç",
        "mini modu aç",
        "mini mod",
        "kibrit kutusu moduna geç",
        "kibrit kutusu modu",
        "kibrit kutusu",
        "mini ekran",
        "küçül",
        "pencereyi küçült",
    )

    EXIT_MINI_MODE_PATTERNS = (
        "normal moda geç",
        "normal moda dön",
        "tam ekrana dön",
        "tam ekran yap",
        "tam ekran moduna geç",
        "mini moddan çık",
        "mini modu kapat",
        "izlemeyi durdur",
        "izlemeyi bitir",
        "ekranı büyüt",
        "büyüt",
    )

    ENROLL_BIOMETRICS_PATTERNS = (
        "sesimi ve görüntümü kaydet",
        "görüntümü ve sesimi kaydet",
        "biyometrik kaydımı başlat",
        "biyometrik kayıt başlat",
        "yüzümü ve sesimi kaydet",
        "sesimi ve yüzümü kaydet",
        "beni veritabanına kaydet",
        "beni tanı",
    )

    SCAN_HAND_OBJECT_PATTERNS = (
        "elimdeki ne",
        "elimde ne var",
        "elimdeki eşya",
        "elimdeki nesne",
        "elimi görüyor musun",
        "kolumu görüyor musun",
        "kaç parmağım",
        "kameraya bak",
        "beni görüyor musun",
        "masada ne var",
        "elimdekini tanı",
        "görüntü tanıma",
    )

    ENABLE_AIRGAP_PATTERNS = (
        "kapalı kutu modunu aç",
        "kapalı kutu moduna geç",
        "sadece yerel çalış",
        "veriyi dışarı çıkarma",
        "çevrimdışı moda geç",
    )

    DISABLE_AIRGAP_PATTERNS = (
        "kapalı kutu modunu kapat",
        "hibrit moda geç",
        "hibrit modu aç",
        "bulut konseyini aç",
    )

    # Araç anahtar kelime haritası (Hızlı eşleştirme için)
    TOOL_KEYWORD_BOOST: Dict[str, List[str]] = {
        "sistem_durumu_getir": ["şarj", "pil", "batarya", "cpu", "ram", "bellek", "işlemci", "sistem durumu", "bilgisayarın durumu"],
        "ekrani_analiz_et": ["ekranımı analiz", "ekranda ne var", "ekranıma bak", "ekran görüntüsü analiz", "ekrandaki hata"],
        "ekran_goruntusu_al": ["ekran görüntüsü al", "screenshot", "ekranı çek", "ekran fotoğrafı"],
        "aktif_pencere_ve_pano_getir": ["aktif pencere", "hangi pencere", "panoda ne var", "kopyaladığım", "ctrl+c", "pano"],
        "panodaki_hatayi_coz": ["panodaki hata", "kopyaladığım hata", "hatayı çöz"],
        "masaustu_dosya_ara": ["dosya ara", "masaüstünde ara", "klasör ara", "nerede bu dosya", "dosyaları bul"],
        "hizli_not_olustur": ["not al", "not oluştur", "not kaydet", "kaydet bunu"],
        "uzun_gorev_baslat": ["uzun görev", "arka plan görevi", "10 saatlik", "görev başlat", "pomodoro başlat"],
        "gorev_durumu_sorgula": ["görevler ne durumda", "aktif görevler", "çalışan görevler"],
        "masaustunu_duzenle": ["masaüstünü düzenle", "dosyaları grupla", "dağınıklığı topla"],
        "uygulama_ac": ["uygulama aç", "programı başlat", "chrome aç", "not defteri aç", "hesap makinesi aç"],
        "uygulama_baslat": ["aç", "başlat", "programı aç", "uygulamayı aç", "çalıştır", "not defteri", "hesap makinesi", "chrome", "vscode", "spotify", "explorer"],
        "web_sitesi_veya_arama_ac": ["youtube", "youtube'u aç", "youtube aç", "google'da ara", "internette ara", "siteye git", "web sitesi"],
        "web_aramasi_ac": ["youtube", "google", "arama yap", "internette ara"],
        "masaustunde_dosya_olustur": ["masaüstüne dosya", "dosya oluştur", "dosya aç", "dosya yarat", "yeni dosya", "metin dosyası"],
        "hava_durumu_getir": ["hava nasıl", "hava durumu", "bugün hava", "sıcaklık kaç", "yağmur var mı", "derece kaç"],
        "ses_seviyesi_ayarla": ["sesi kıs", "sesi yükselt", "ses seviyesi"],
        "bilgi_grafigi_raporu_getir": ["bilgi grafiği", "knowledge graph", "hakkımda öğrendiğin bağlantılar"],
        "bilgi_grafigine_iliski_ekle": ["grafiğe ekle", "ilişki kaydet", "kalıcı bağlantı ekle"],
    }

    @classmethod
    def detect_ui_directive(cls, user_text: str) -> Dict[str, Any]:
        """
        Kullanıcı cümlesinde ekran/arayüz/mod direktifi olup olmadığını tespit eder.
        """
        t = user_text.strip().lower()

        wants_text_on_screen = any(p in t for p in cls.SHOW_TEXT_PATTERNS)
        wants_clear_screen = any(p in t for p in cls.CLEAR_SCREEN_PATTERNS)
        wants_silent_cursor = any(p in t for p in cls.ENABLE_SILENT_CURSOR_PATTERNS)
        wants_voice_mode = any(p in t for p in cls.ENABLE_VOICE_MODE_PATTERNS)
        wants_exit = any(p in t for p in cls.EXIT_APP_PATTERNS)
        wants_open_profile = any(p in t for p in cls.OPEN_USER_PROFILE_PATTERNS)
        wants_close_profile = any(p in t for p in cls.CLOSE_USER_PROFILE_PATTERNS)
        wants_mini_mode = any(p in t for p in cls.MINI_MODE_PATTERNS)
        wants_exit_mini = any(p in t for p in cls.EXIT_MINI_MODE_PATTERNS)
        wants_enroll_bio = any(p in t for p in cls.ENROLL_BIOMETRICS_PATTERNS)
        wants_scan_hand = any(p in t for p in cls.SCAN_HAND_OBJECT_PATTERNS)
        wants_enable_airgap = any(p in t for p in cls.ENABLE_AIRGAP_PATTERNS)
        wants_disable_airgap = any(p in t for p in cls.DISABLE_AIRGAP_PATTERNS)

        return {
            "show_text": wants_text_on_screen,
            "clear_screen": wants_clear_screen,
            "enable_silent_cursor": wants_silent_cursor,
            "enable_voice_mode": wants_voice_mode,
            "exit_app": wants_exit,
            "open_user_profile": wants_open_profile,
            "close_user_profile": wants_close_profile,
            "enter_mini_mode": wants_mini_mode,
            "exit_mini_mode": wants_exit_mini,
            "enroll_biometrics": wants_enroll_bio,
            "scan_hand_and_object": wants_scan_hand,
            "enable_airgap": wants_enable_airgap,
            "disable_airgap": wants_disable_airgap,
        }

    @classmethod
    def select_relevant_tools(
        cls,
        user_text: str,
        all_tools: List[Dict[str, Any]],
        max_tools: int = 4,
    ) -> List[Dict[str, Any]]:
        """
        Kullanıcının sorusuna göre 87 araç içinden sadece en alakalı olanları (0 ila max_tools) seçer.
        Eğer soru genel sohbet veya kişisel hafıza sorusuysa boş liste [] döndürür ki LLM anında yanıt versin.
        """
        t = user_text.strip().lower()
        words = set(WORD_REGEX.findall(t))

        # Saf sohbet / kişisel soru kalıpları -> Araç göndermeye gerek yok (Sıfır gecikme!)
        conversational_Checks = (
            "merhaba",
            "selam",
            "nasılsın",
            "kimsin",
            "adın ne",
            "benim hakkımda",
            "beni tanıyor musun",
            "ben kimim",
            "ne biliyorsun",
            "bana anlat",
            "nedir",
            "neden",
            "nasıl yapılır",
            "hikaye",
            "fikrin ne",
            "ne düşünüyorsun",
            "teşekkür",
            "sağ ol",
            "günaydın",
            "iyi geceler",
        )
        # Eğer cümle kısa bir sohbet cümlesiyse ve özel bir sistem eylemi içermiyorsa:
        has_boost_match = False
        for _, kw_list in cls.TOOL_KEYWORD_BOOST.items():
            if any(kw in t for kw in kw_list):
                has_boost_match = True
                break

        if not has_boost_match and any(c in t for c in conversational_Checks):
            return []

        scored: List[Tuple[float, Dict[str, Any]]] = []
        for tool in all_tools:
            score = 0.0
            t_name = tool.get("name", "").lower()
            t_desc = tool.get("description", "").lower()

            # 1. Özel anahtar kelime boost kontrolü
            for boost_kw in cls.TOOL_KEYWORD_BOOST.get(t_name, []):
                if boost_kw in t:
                    score += 15.0

            # 2. Araç adı kelimeleri
            name_parts = set(t_name.split("_"))
            overlap_name = words.intersection(name_parts)
            score += len(overlap_name) * 6.0

            # 3. Açıklama kelime örtüşmesi (kök/ön-ek benzerliği dahil)
            desc_words = set(DESC_WORD_REGEX.findall(t_desc))
            for uw in words:
                if uw in desc_words:
                    score += 3.0
                else:
                    prefix = uw[:4]
                    if len(prefix) == 4 and any(dw.startswith(prefix) for dw in desc_words):
                        score += 1.5

            if score >= 4.5:
                scored.append((score, tool))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:max_tools]]
