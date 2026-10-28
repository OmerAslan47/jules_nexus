import os
import psutil
from core.plugin_manager import nexus_tool
from core.context_engine import ContextEngine, SmartMemory

_context = ContextEngine()
_memory = SmartMemory()


@nexus_tool(
    name="sistem_durumu_getir",
    description="Bilgisayarın CPU, RAM ve batarya/şarj yüzdesini kontrol eder.",
    risk_level="low",
    guest_allowed=True,
)
def sistem_durumu_getir() -> str:
    cpu = psutil.cpu_percent(interval=0.3)
    ram = psutil.virtual_memory().percent
    battery = psutil.sensors_battery()
    bat_str = (
        f"%{battery.percent} ({'Şarj oluyor' if battery.power_plugged else 'Pilde'})"
        if battery
        else "Bilinmiyor"
    )
    return f"CPU Kullanımı: %{cpu}, RAM Kullanımı: %{ram}, Batarya: {bat_str}"


@nexus_tool(
    name="aktif_pencere_ve_pano_oku",
    description="Kullanıcının o an açık olan penceresini ve panoya (Ctrl+C) kopyaladığı son metni okur.",
    risk_level="low",
    guest_allowed=False,
)
def aktif_pencere_ve_pano_oku() -> str:
    snap = _context.build_context_snapshot(include_clipboard=True)
    return f"Aktif Pencere: {snap['active_window']} | Pano İçeriği: {snap.get('clipboard', 'Boş')}"


@nexus_tool(
    name="hafizaya_kaydet",
    description="Önemli bir bilgiyi veya kullanıcı tercihini NEXUS akıllı hafızasına (memory.json) kaydeder.",
    risk_level="low",
    guest_allowed=False,
)
def hafizaya_kaydet(anahtar: str, deger: str) -> str:
    _memory.upsert_fact(anahtar, deger)
    return f"Hafızaya kaydedildi: {anahtar} = {deger}"


@nexus_tool(
    name="dosya_sil",
    description="Belirtilen yoldaki dosyayı siler (Kritik işlem - onay gerektirir).",
    risk_level="high",
    guest_allowed=False,
)
def dosya_sil(dosya_yolu: str) -> str:
    if os.path.exists(dosya_yolu):
        os.remove(dosya_yolu)
        return f"{dosya_yolu} başarıyla silindi."
    return f"Dosya bulunamadı: {dosya_yolu}"
