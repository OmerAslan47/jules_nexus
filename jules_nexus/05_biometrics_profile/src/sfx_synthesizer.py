from core.paths import NEXUS_ROOT
import logging
import math
import os
import threading
import wave
from typing import Dict, Optional
import numpy as np


SFX_DIR = (NEXUS_ROOT + "/ui/assets/sfx")
LOG_DIR = (NEXUS_ROOT + "/logs")
os.makedirs(SFX_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger("NEXUS.SFXEngine")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler(os.path.join(LOG_DIR, "sfx_engine.log"), encoding="utf-8")
    fh.setFormatter(
        logging.Formatter(
            "[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
    )
    logger.addHandler(fh)


class SciFiSFXSynthesizer:
    """
    NEXUS v4.0 - Sinematik Bilim-Kurgu Animasyon Ses Efektleri Motoru (DSP FM Synthesizer):
    - 3B Dünya'nın durum geçişlerinde (Uyanış, Dinleme, Hızlı Düşünme, Derin Konsey Kilitlenmesi,
      Görsel El/Nesne Tarama, Biyometrik Onay ve Güvenlik Uyarısı) çalan 7 farklı fütüristik ses efektini
      matematiksel FM/Harmonik sentez ile 24kHz WAV olarak üretir.
    - 'pygame.mixer.Sound' üzerinden ayrı ses kanalında çaldığı için NEXUS'un konuşma sesini
      (pygame.mixer.music) asla kesmez; arka planda sinematik ambiyans sağlar.
    """

    SAMPLE_RATE = 24000

    SFX_FILES = {
        "awakening": "sfx_startup_awakening.wav",
        "listening": "sfx_listening_ping.wav",
        "thinking": "sfx_thinking_synapse.wav",
        "deep_thinking": "sfx_deep_council_lock.wav",
        "scanning": "sfx_scan_biometric.wav",
        "confirmed": "sfx_confirmed_chime.wav",
        "security_alert": "sfx_alert_security.wav",
        "jarvis_compute": "sfx_jarvis_telemetry_compute.wav",
        "airgap_lock": "sfx_airgap_vault_lock.wav",
        "profile_open": "sfx_profile_hud_open.wav",
        "hand_locked": "sfx_hand_target_lock.wav",
        "memory_encoded": "sfx_memory_node_encoded.wav",
    }

    def __init__(self, enabled: bool = True, volume: float = 0.32):
        self.enabled = enabled
        self.volume = max(0.0, min(volume, 1.0))
        self._sounds_cache: Dict[str, object] = {}
        self._lock = threading.Lock()
        self.ensure_all_sfx_generated()

    @classmethod
    def _save_wav(cls, filepath: str, signal: np.ndarray):
        peak = float(np.max(np.abs(signal)))
        if peak > 1e-5:
            signal = (signal / peak) * 0.82
        pcm = np.clip(signal * 32767.0, -32768, 32767).astype(np.int16)
        with wave.open(filepath, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(cls.SAMPLE_RATE)
            wf.writeframes(pcm.tobytes())

    @classmethod
    def ensure_all_sfx_generated(cls):
        sr = cls.SAMPLE_RATE

        # 1. AWAKENING: Derin Kuantum Çekirdek Uyanışı (Sub-bass sweep + kristal harmonik akor)
        p_awake = os.path.join(SFX_DIR, cls.SFX_FILES["awakening"])
        if not os.path.exists(p_awake):
            dur = 1.45
            t = np.linspace(0, dur, int(sr * dur), endpoint=False)
            env = np.sin(np.pi * (t / dur)) ** 0.7
            f_sweep = np.linspace(55.0, 165.0, len(t))
            phase = 2.0 * np.pi * np.cumsum(f_sweep) / sr
            sub = 0.55 * np.sin(phase)
            chord = (
                0.22 * np.sin(2.0 * np.pi * 220.0 * t)
                + 0.18 * np.sin(2.0 * np.pi * 330.0 * t)
                + 0.14 * np.sin(2.0 * np.pi * 440.0 * t * (1.0 + 0.005 * np.sin(18 * t)))
            )
            shimmer = 0.08 * np.sin(2.0 * np.pi * 880.0 * t) * np.exp(-2.2 * t)
            cls._save_wav(p_awake, (sub + chord + shimmer) * env)

        # 2. LISTENING: Dinleme Modu Kristal Sonar Darbesi (Kısa, temiz çift ton)
        p_listen = os.path.join(SFX_DIR, cls.SFX_FILES["listening"])
        if not os.path.exists(p_listen):
            dur = 0.24
            t = np.linspace(0, dur, int(sr * dur), endpoint=False)
            env = np.exp(-12.0 * t) * (1.0 - np.exp(-90.0 * t))
            f1 = 528.0
            f2 = 792.0
            sig = 0.6 * np.sin(2.0 * np.pi * f1 * t) + 0.4 * np.sin(
                2.0 * np.pi * f2 * np.maximum(0, t - 0.05)
            )
            cls._save_wav(p_listen, sig * env)

        # 3. THINKING: Sinaptik Hesaplama Veri Akışı (Yumuşak nöral darbe dizisi)
        p_think = os.path.join(SFX_DIR, cls.SFX_FILES["thinking"])
        if not os.path.exists(p_think):
            dur = 0.36
            t = np.linspace(0, dur, int(sr * dur), endpoint=False)
            env = np.exp(-7.5 * t) * (0.6 + 0.4 * np.sin(2.0 * np.pi * 22.0 * t))
            carrier = np.sin(2.0 * np.pi * 360.0 * t + 1.8 * np.sin(2.0 * np.pi * 90.0 * t))
            cls._save_wav(p_think, carrier * env * 0.65)

        # 4. DEEP_THINKING: 3-Katmanlı Konsey & Jiroskopik Kuantum Çekirdek Kilitlenmesi
        p_deep = os.path.join(SFX_DIR, cls.SFX_FILES["deep_thinking"])
        if not os.path.exists(p_deep):
            dur = 0.92
            t = np.linspace(0, dur, int(sr * dur), endpoint=False)
            env = np.sin(np.pi * (t / dur)) ** 0.5 * np.exp(-1.8 * t)
            f_drop = np.linspace(180.0, 68.0, len(t))
            ph = 2.0 * np.pi * np.cumsum(f_drop) / sr
            bass_lock = 0.65 * np.sin(ph)
            gyro_pulse = (
                0.35
                * np.sin(2.0 * np.pi * 480.0 * t)
                * (0.5 + 0.5 * np.sign(np.sin(2.0 * np.pi * 14.0 * t)))
                * np.exp(-3.5 * t)
            )
            cls._save_wav(p_deep, (bass_lock + gyro_pulse) * env)

        # 5. SCANNING: Kamera El/Kol/Eşya ve Biyometri Lazer Tarama Sesi
        p_scan = os.path.join(SFX_DIR, cls.SFX_FILES["scanning"])
        if not os.path.exists(p_scan):
            dur = 0.65
            t = np.linspace(0, dur, int(sr * dur), endpoint=False)
            env = np.sin(np.pi * (t / dur))
            f_laser = 320.0 + 240.0 * np.sin(2.0 * np.pi * 4.5 * t)
            ph = 2.0 * np.pi * np.cumsum(f_laser) / sr
            sig = 0.5 * np.sin(ph) + 0.25 * np.sin(2.0 * ph)
            cls._save_wav(p_scan, sig * env * 0.7)

        # 6. CONFIRMED: Biyometrik / Hesaplama Onay Akoru
        p_conf = os.path.join(SFX_DIR, cls.SFX_FILES["confirmed"])
        if not os.path.exists(p_conf):
            dur = 0.42
            t = np.linspace(0, dur, int(sr * dur), endpoint=False)
            env = np.exp(-6.5 * t)
            sig = (
                0.5 * np.sin(2.0 * np.pi * 440.0 * t)
                + 0.45 * np.sin(2.0 * np.pi * 554.37 * np.maximum(0, t - 0.07))
                + 0.45 * np.sin(2.0 * np.pi * 659.25 * np.maximum(0, t - 0.14))
            )
            cls._save_wav(p_conf, sig * env)

        # 7. SECURITY_ALERT: Misafir / Yetkisiz Erişim Uyarı Darbesi
        p_alert = os.path.join(SFX_DIR, cls.SFX_FILES["security_alert"])
        if not os.path.exists(p_alert):
            dur = 0.55
            t = np.linspace(0, dur, int(sr * dur), endpoint=False)
            gate = np.where(np.sin(2.0 * np.pi * 5.0 * t) > 0, 1.0, 0.15)
            sig = (
                0.6 * np.sin(2.0 * np.pi * 290.0 * t)
                + 0.35 * np.sin(2.0 * np.pi * 580.0 * t)
            ) * gate * np.exp(-2.0 * t)
            cls._save_wav(p_alert, sig)

        # 8. JARVIS_COMPUTE: Hızlı Mühendislik & Matematik Telemetri Hesaplama Sesi
        p_calc = os.path.join(SFX_DIR, cls.SFX_FILES["jarvis_compute"])
        if not os.path.exists(p_calc):
            dur = 0.28
            t = np.linspace(0, dur, int(sr * dur), endpoint=False)
            env = np.exp(-9.0 * t)
            step_freqs = np.where(t < 0.09, 660.0, np.where(t < 0.18, 880.0, 1320.0))
            ph = 2.0 * np.pi * np.cumsum(step_freqs) / sr
            sig = 0.55 * np.sin(ph) + 0.25 * np.sin(2.0 * ph)
            cls._save_wav(p_calc, sig * env * 0.65)

        # 9. AIRGAP_LOCK: Kapalı Kutu Elektromanyetik Zırh Kilitlenme Sesi
        p_air = os.path.join(SFX_DIR, cls.SFX_FILES["airgap_lock"])
        if not os.path.exists(p_air):
            dur = 0.72
            t = np.linspace(0, dur, int(sr * dur), endpoint=False)
            env = np.exp(-3.8 * t)
            f_lock = np.linspace(240.0, 75.0, len(t))
            ph = 2.0 * np.pi * np.cumsum(f_lock) / sr
            metallic = 0.3 * np.sin(2.0 * np.pi * 620.0 * t) * np.exp(-14.0 * t)
            cls._save_wav(p_air, (0.7 * np.sin(ph) + metallic) * env)

        # 10. PROFILE_OPEN: UserProfile Holografik Yetki Matrisi Açılış Sesi
        p_prof = os.path.join(SFX_DIR, cls.SFX_FILES["profile_open"])
        if not os.path.exists(p_prof):
            dur = 0.48
            t = np.linspace(0, dur, int(sr * dur), endpoint=False)
            env = np.sin(np.pi * (t / dur)) ** 0.6
            f_up = np.linspace(330.0, 660.0, len(t))
            ph = 2.0 * np.pi * np.cumsum(f_up) / sr
            sig = 0.5 * np.sin(ph) + 0.3 * np.sin(2.0 * np.pi * 990.0 * t) * np.exp(-5.0 * t)
            cls._save_wav(p_prof, sig * env * 0.7)

        # 11. HAND_LOCKED: Kamera El/Kol/Eşya Hedef Kilitlenme Sesi
        p_hand = os.path.join(SFX_DIR, cls.SFX_FILES["hand_locked"])
        if not os.path.exists(p_hand):
            dur = 0.32
            t = np.linspace(0, dur, int(sr * dur), endpoint=False)
            pulse = np.where((t < 0.12) | (t > 0.17), 1.0, 0.0)
            sig = 0.6 * np.sin(2.0 * np.pi * 740.0 * t) * pulse * np.exp(-5.5 * t)
            cls._save_wav(p_hand, sig)

        # 12. MEMORY_ENCODED: Bilgi Grafiği Kristal Hafıza Kayıt Sesi
        p_mem = os.path.join(SFX_DIR, cls.SFX_FILES["memory_encoded"])
        if not os.path.exists(p_mem):
            dur = 0.35
            t = np.linspace(0, dur, int(sr * dur), endpoint=False)
            env = np.exp(-8.0 * t)
            sig = 0.45 * np.sin(2.0 * np.pi * 587.33 * t) + 0.35 * np.sin(2.0 * np.pi * 880.0 * t)
            cls._save_wav(p_mem, sig * env * 0.55)

    def play_sfx(self, event_name: str):
        if not self.enabled:
            return
        fname = self.SFX_FILES.get(event_name)
        if not fname:
            return
        fpath = os.path.join(SFX_DIR, fname)
        if not os.path.exists(fpath):
            return

        def _play_worker():
            try:
                import pygame

                with self._lock:
                    if not pygame.mixer.get_init():
                        # VoiceEngine ile AYNI mikser ayarı: biri diğerinin mikserini kapatmasın
                        pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=2048)
                    snd = self._sounds_cache.get(event_name)
                    if snd is None:
                        snd = pygame.mixer.Sound(fpath)
                        self._sounds_cache[event_name] = snd
                    snd.set_volume(self.volume)
                    snd.play()
            except Exception as e:
                logger.debug(f"SFX çalma uyarısı ({event_name}): {e}")

        threading.Thread(target=_play_worker, daemon=True).start()
