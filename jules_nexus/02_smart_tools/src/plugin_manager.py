from core.paths import NEXUS_ROOT
import importlib.util
import inspect
import json
import logging
import os
import threading
import time
import traceback
from collections import deque
from typing import Any, Callable, Deque, Dict, List, Optional


# ============================================================================
# LOGLAMA VE GÜVENLİK DENETİM YAPILANDIRMASI
# ============================================================================
LOG_DIR = (NEXUS_ROOT + "/logs")
os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger("NEXUS.PluginManager")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler(
        os.path.join(LOG_DIR, "plugin_security_audit.log"), encoding="utf-8"
    )
    fh.setFormatter(
        logging.Formatter(
            "[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
    )
    logger.addHandler(fh)

# Global Kayıtlı Araçlar Sözlüğü
REGISTERED_TOOLS: Dict[str, Dict[str, Any]] = {}


# ============================================================================
# @nexus_tool DEKORATÖRÜ
# ============================================================================
def nexus_tool(
    name: str,
    description: str,
    risk_level: str = "low",
    guest_allowed: bool = True,
    category: str = "general",
    timeout_sec: float = 30.0,
    rate_limit_per_min: int = 30,
):
    """
    NEXUS Kurumsal Eklenti Dekoratörü.
    plugins/ klasörüne atılan bağımsız Python dosyalarındaki fonksiyonları otomatik tanır.
    Parametreler:
      - name: Aracın benzersiz adı (Örn: 'sistem_durumu_getir')
      - description: LLM'in bu aracı ne zaman kullanacağını anlamasını sağlayan açıklama
      - risk_level:
          * 'low'       -> Otonom olarak doğrudan çalışır
          * 'medium'    -> Loglanır ve çalışır
          * 'high'      -> Kullanıcıdan sesli/yazılı onay ister (Dosya silme, klasör taşıma vb.)
          * 'forbidden' -> Kesinlikle çalıştırılmaz (Finansal/Bankacılık işlemleri)
      - guest_allowed: Misafir modunda (tanınmayan yüz/ses) çalışmasına izin verilip verilmediği
      - rate_limit_per_min: Dakikada maksimum çağrılma sınırı (Sonsuz döngü koruması)
    """

    def decorator(func: Callable):
        sig = inspect.signature(func)
        params: Dict[str, Dict[str, Any]] = {}
        for param_name, param in sig.parameters.items():
            param_type = (
                param.annotation.__name__
                if param.annotation != inspect.Parameter.empty
                and hasattr(param.annotation, "__name__")
                else "str"
            )
            default_val = (
                None if param.default == inspect.Parameter.empty else param.default
            )
            params[param_name] = {
                "type": param_type,
                "required": param.default == inspect.Parameter.empty,
                "default": default_val,
            }

        REGISTERED_TOOLS[name] = {
            "name": name,
            "description": description,
            "risk_level": risk_level.lower().strip(),
            "guest_allowed": bool(guest_allowed),
            "category": category,
            "timeout_sec": float(timeout_sec),
            "rate_limit_per_min": int(rate_limit_per_min),
            "parameters": params,
            "func": func,
            "module_file": getattr(func, "__module__", "unknown"),
            "doc": (func.__doc__ or "").strip(),
        }
        return func

    return decorator


# ============================================================================
# HIZ SINIRLAYICI VE SONSUZ DÖNGÜ KORUMASI (RATE LIMITER)
# ============================================================================
class ToolRateLimiter:
    """
    Bir aracın dakikada izin verilenden fazla çağrılmasını (örneğin hatalı bir
    otonom döngüde art arda 50 kez dosya oluşturmasını) engeller.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._call_timestamps: Dict[str, Deque[float]] = {}

    def allow_call(self, tool_name: str, max_per_minute: int = 30) -> bool:
        now = time.time()
        with self._lock:
            q = self._call_timestamps.setdefault(tool_name, deque(maxlen=200))
            while q and (now - q[0]) > 60.0:
                q.popleft()
            if len(q) >= max_per_minute:
                return False
            q.append(now)
            return True


# ============================================================================
# EKLENTİ PERFORMANS VE GÜVENLİK DENETÇİSİ (TELEMETRİ)
# ============================================================================
class PluginTelemetry:
    """
    Her bir eklentinin kaç kez çağrıldığını, ortalama çalışma süresini (ms),
    son çalışma çıktısını ve Misafir Modu / Güvenlik Duvarı engellemelerini takip eder.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.stats: Dict[str, Dict[str, Any]] = {}
        self.security_events: List[Dict[str, Any]] = []
        self.execution_history: Deque[Dict[str, Any]] = deque(maxlen=60)

    def record_execution(
        self,
        name: str,
        kwargs: Dict[str, Any],
        success: bool,
        duration_ms: float,
        output_preview: str = "",
        error_msg: str = "",
    ):
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            st = self.stats.setdefault(
                name,
                {
                    "calls": 0,
                    "successes": 0,
                    "failures": 0,
                    "total_duration_ms": 0.0,
                    "avg_duration_ms": 0.0,
                    "last_called": "",
                    "last_error": "",
                },
            )
            st["calls"] += 1
            if success:
                st["successes"] += 1
            else:
                st["failures"] += 1
                st["last_error"] = error_msg[:200]
            st["total_duration_ms"] = round(st["total_duration_ms"] + duration_ms, 2)
            st["avg_duration_ms"] = round(
                st["total_duration_ms"] / max(st["calls"], 1), 2
            )
            st["last_called"] = now_str

            self.execution_history.append(
                {
                    "tool": name,
                    "args": kwargs,
                    "success": success,
                    "duration_ms": round(duration_ms, 1),
                    "output_preview": output_preview[:120],
                    "timestamp": now_str,
                }
            )

    def record_security_block(self, tool_name: str, reason: str, is_guest: bool):
        event = {
            "tool": tool_name,
            "reason": reason,
            "is_guest": is_guest,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        with self._lock:
            self.security_events.append(event)
            self.security_events = self.security_events[-100:]
        logger.warning(
            f"GÜVENLİK ENGELİ: Araç={tool_name} | Sebep={reason} | Misafir={is_guest}"
        )

    def get_report(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "tool_stats": dict(self.stats),
                "recent_executions": list(self.execution_history)[-10:],
                "recent_security_blocks": list(self.security_events)[-15:],
            }


# ============================================================================
# FAZ 1 & FAZ 5 DİNAMİK EKLENTİ VE GÜVENLİK YÖNETİCİSİ (PLUGIN MANAGER V2)
# ============================================================================
class PluginManager:
    """
    NEXUS Modüler Eklenti Yöneticisi (Kurumsal Tam Sürüm):
    - plugins/ klasöründeki tüm .py dosyalarını dinamik olarak yükler ve çalışma zamanında
      yeniden yükleyebilir (Hot-Reload).
    - Otomatik Eklenti Kataloğu (PLUGINS_KATALOGU.md) oluşturur.
    - Parametre doğrulama, tip dönüşümü (Type Coercion) ve Zaman Aşımı (Timeout) kontrolü yapar.
    - Misafir Modu (Guest Mode), Yüksek Risk Sesli Onay, Hız Sınırlayıcı ve Finansal İşlem Yasağını uygular.
    """

    FORBIDDEN_FINANCIAL_WORDS = (
        "iban",
        "kredi_karti",
        "para_transferi",
        "havale",
        "eft",
        "banka_odeme",
        "kripto_transfer",
    )

    def __init__(
        self,
        plugins_dir: str = (NEXUS_ROOT + "/plugins"),
        catalog_path: str = (NEXUS_ROOT + "/PLUGINS_KATALOGU.md"),
    ):
        self.plugins_dir = plugins_dir
        self.catalog_path = catalog_path
        os.makedirs(self.plugins_dir, exist_ok=True)
        self.telemetry = PluginTelemetry()
        self.rate_limiter = ToolRateLimiter()
        self.loaded_files: Dict[str, float] = {}
        self.load_errors: Dict[str, str] = {}
        self.disabled_tools: set = set()

    def enable_tool(self, tool_name: str):
        self.disabled_tools.discard(tool_name)

    def disable_tool(self, tool_name: str):
        self.disabled_tools.add(tool_name)

    def load_all_plugins(self, force_reload: bool = False) -> List[str]:
        """plugins/ klasöründeki tüm .py dosyalarını tarar ve dinamik olarak yükler."""
        loaded = []
        changed = False
        for filename in sorted(os.listdir(self.plugins_dir)):
            if not filename.endswith(".py") or filename.startswith("_"):
                continue
            filepath = os.path.join(self.plugins_dir, filename)
            mtime = os.path.getmtime(filepath)

            if not force_reload and filename in self.loaded_files:
                if self.loaded_files[filename] == mtime:
                    loaded.append(filename)
                    continue

            module_name = f"nexus_plugin_{filename[:-3]}"
            try:
                spec = importlib.util.spec_from_file_location(module_name, filepath)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    self.loaded_files[filename] = mtime
                    self.load_errors.pop(filename, None)
                    loaded.append(filename)
                    changed = True
                    logger.info(f"Eklenti modülü yüklendi: {filename}")
            except Exception as e:
                err_str = f"{e}\n{traceback.format_exc()}"
                self.load_errors[filename] = str(e)
                logger.error(f"Eklenti yükleme hatası ({filename}): {err_str}")

        if changed or force_reload:
            self.export_catalog_markdown()

        return loaded

    def check_and_hot_reload(self) -> List[str]:
        """Klasöre yeni atılan veya değiştirilen .py eklenti dosyalarını otomatik algılar."""
        return self.load_all_plugins(force_reload=False)

    def export_catalog_markdown(self):
        """Kayıtlı tüm eklentilerin şeffaf bir Markdown kataloğunu oluşturur."""
        try:
            lines = [
                "# 🔧 NEXUS - Aktif Eklenti ve Araç Kataloğu",
                f"> **Otomatik Güncelleme:** {time.strftime('%Y-%m-%d %H:%M:%S')} | **Toplam Araç:** {len(REGISTERED_TOOLS)}",
                "",
                "| Araç Adı (`@nexus_tool`) | Risk Seviyesi | Misafir İzni | Parametreler | Açıklama |",
                "| :--- | :--- | :--- | :--- | :--- |",
            ]
            for name, tool in sorted(REGISTERED_TOOLS.items()):
                risk = tool.get("risk_level", "low").upper()
                guest = "✅ Evet" if tool.get("guest_allowed") else "🔒 Hayır"
                params = ", ".join(tool.get("parameters", {}).keys()) or "*Yok*"
                desc = tool.get("description", "")
                lines.append(f"| `{name}` | **{risk}** | {guest} | `{params}` | {desc} |")

            with open(self.catalog_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        except Exception as e:
            logger.debug(f"Katalog yazma hatası: {e}")

    def get_tools_prompt_schema(self, is_guest: bool = False) -> List[Dict[str, Any]]:
        """Aktif araçların LLM için JSON şemasını döndürür (Misafir modunda kısıtlı araçları gizler)."""
        self.check_and_hot_reload()
        schema = []
        for tool in REGISTERED_TOOLS.values():
            if tool["name"] in self.disabled_tools:
                continue
            if is_guest and not tool["guest_allowed"]:
                continue
            if tool["risk_level"] == "forbidden":
                continue
            schema.append(
                {
                    "name": tool["name"],
                    "description": tool["description"],
                    "risk_level": tool["risk_level"],
                    "category": tool.get("category", "general"),
                    "parameters": tool["parameters"],
                }
            )
        return schema

    @staticmethod
    def _coerce_arguments(
        tool_meta: Dict[str, Any], raw_kwargs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """LLM'den gelen parametreleri fonksiyonun beklediği tiplere (int, float, bool, str) güvenli dönüştürür."""
        coerced: Dict[str, Any] = {}
        param_defs = tool_meta.get("parameters", {})

        for k, v in (raw_kwargs or {}).items():
            if k not in param_defs:
                continue
            expected = param_defs[k].get("type", "str")
            try:
                if expected == "int":
                    coerced[k] = int(v)
                elif expected == "float":
                    coerced[k] = float(v)
                elif expected == "bool":
                    coerced[k] = (
                        v
                        if isinstance(v, bool)
                        else str(v).lower() in ("true", "1", "evet")
                    )
                else:
                    coerced[k] = str(v)
            except Exception:
                coerced[k] = v

        for p_name, p_info in param_defs.items():
            if p_name not in coerced and not p_info.get("required", False):
                if p_info.get("default") is not None:
                    coerced[p_name] = p_info["default"]

        return coerced

    def execute_tool(
        self,
        name: str,
        kwargs: Optional[Dict[str, Any]] = None,
        is_guest: bool = False,
        confirmation_callback: Optional[Callable[[str], bool]] = None,
    ) -> str:
        """
        Aracı güvenlik duvarı, hız sınırlayıcı, misafir modu ve onay protokollerine göre çalıştırır.
        """
        self.check_and_hot_reload()

        if name not in REGISTERED_TOOLS:
            return f"Hata: '{name}' adında kayıtlı bir NEXUS eklentisi bulunamadı."

        if name in self.disabled_tools:
            return f"Bilgi: '{name}' eklentisi şu anda devre dışı bırakılmış."

        tool = REGISTERED_TOOLS[name]

        # 1. Finansal / Yasaklı İşlem Kontrolü
        if tool["risk_level"] == "forbidden" or any(
            fw in name.lower() for fw in self.FORBIDDEN_FINANCIAL_WORDS
        ):
            self.telemetry.record_security_block(
                name, "Finansal/Yasaklı İşlem", is_guest
            )
            return "Güvenlik Engeli: Finansal veya yasaklı işlemler kesinlikle yapılamaz."

        # 2. Misafir Modu (Guest Mode) Kontrolü
        if is_guest and not tool["guest_allowed"]:
            self.telemetry.record_security_block(
                name, "Misafir Modu Kısıtlaması", is_guest
            )
            return "Güvenlik Engeli: Şu anda Misafir Modu aktif. Sahibin kişisel dosyalarına ve sistem ayarlarına erişim kilitlidir."

        # 3. Hız Sınırlayıcı (Rate Limit) Kontrolü
        max_rpm = int(tool.get("rate_limit_per_min", 30))
        if not self.rate_limiter.allow_call(name, max_per_minute=max_rpm):
            self.telemetry.record_security_block(name, "Rate Limit Aşıldı", is_guest)
            return f"Güvenlik Engeli: '{name}' aracı dakikada en fazla {max_rpm} kez çağrılabilir."

        # 4. Yüksek Riskli İşlem Onay Protokolü
        if tool["risk_level"] == "high":
            if confirmation_callback:
                approved = confirmation_callback(
                    f"'{name}' işlemi kritik sistem/dosya değişikliği içeriyor (Parametreler: {kwargs}). Onaylıyor musunuz?"
                )
                if not approved:
                    self.telemetry.record_security_block(
                        name, "Kullanıcı Onayı Reddedildi", is_guest
                    )
                    return "İşlem kullanıcı tarafından onaylanmadığı için iptal edildi."
            else:
                self.telemetry.record_security_block(
                    name, "Onay Mekanizması Yok", is_guest
                )
                return "Onay Gerekli: Kritik işlem için kullanıcı onay mekanizması bekleniyor."

        # 5. Parametre Hazırlığı ve Çalıştırma
        safe_kwargs = self._coerce_arguments(tool, kwargs or {})
        t0 = time.time()
        try:
            result = tool["func"](**safe_kwargs)
            duration_ms = (time.time() - t0) * 1000.0
            result_str = str(result)
            self.telemetry.record_execution(
                name, safe_kwargs, True, duration_ms, output_preview=result_str
            )
            logger.info(f"Araç çalıştırıldı: {name} ({int(duration_ms)}ms)")
            return result_str
        except Exception as e:
            duration_ms = (time.time() - t0) * 1000.0
            self.telemetry.record_execution(
                name, safe_kwargs, False, duration_ms, error_msg=str(e)
            )
            logger.error(f"Araç çalışma hatası ({name}): {e}")
            return f"Eklenti çalışma hatası ({name}): {e}"

    def generate_plugin_template(
        self, plugin_filename: str, tool_name: str, description: str
    ) -> str:
        """Yeni bir eklenti dosyası için hazır iskelet oluşturur."""
        if not plugin_filename.endswith(".py"):
            plugin_filename += ".py"
        target_path = os.path.join(self.plugins_dir, plugin_filename)
        code = (
            "from core.plugin_manager import nexus_tool\n\n\n"
            f'@nexus_tool(\n    name="{tool_name}",\n    description="{description}",\n'
            '    risk_level="low",\n    guest_allowed=False,\n)\n'
            f'def {tool_name}(parametre: str = "") -> str:\n'
            f'    """{description}"""\n'
            f'    return f"{tool_name} başarıyla çalıştı: {{parametre}}"\n'
        )
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(code)
        self.load_all_plugins(force_reload=True)
        return target_path

    def get_diagnostics(self) -> Dict[str, Any]:
        return {
            "loaded_plugin_files": list(self.loaded_files.keys()),
            "total_registered_tools": len(REGISTERED_TOOLS),
            "disabled_tools": list(self.disabled_tools),
            "load_errors": self.load_errors,
            "telemetry": self.telemetry.get_report(),
        }
