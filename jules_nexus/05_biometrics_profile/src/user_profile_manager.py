from core.paths import NEXUS_ROOT
import base64
import json
import logging
import os
import sqlite3
import threading
import time
import wave
from typing import Any, Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np


LOG_DIR = (NEXUS_ROOT + "/logs")
DATA_DIR = (NEXUS_ROOT + "/data")
BIOMETRICS_DIR = (NEXUS_ROOT + "/data/biometrics")

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(BIOMETRICS_DIR, exist_ok=True)

logger = logging.getLogger("NEXUS.UserProfile")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler(
        os.path.join(LOG_DIR, "user_profile.log"), encoding="utf-8"
    )
    fh.setFormatter(
        logging.Formatter(
            "[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
    )
    logger.addHandler(fh)


# ============================================================================
# YETKİ MATRİSİ TANIMLARI (KARE SEÇİM KUTUCUKLARI İÇİN)
# ============================================================================
PERMISSION_DEFINITIONS: List[Dict[str, str]] = [
    {
        "key": "perm_system_control",
        "label": "Sistem ve Donanım Kontrolü",
        "desc": "Uygulama açma/kapatma, ses seviyesi, ekran parlaklığı ve güç işlemleri",
    },
    {
        "key": "perm_file_access",
        "label": "Dosya ve Klasör Erişimi",
        "desc": "Bilgisayardaki dosyaları okuma, oluşturma, düzenleme ve arama yetkisi",
    },
    {
        "key": "perm_personal_memory",
        "label": "Kişisel Hafıza ve Bilgi Grafiği",
        "desc": "Sahibin özel notlarına, geçmiş konuşmalarına ve bilgi grafiğine erişim",
    },
    {
        "key": "perm_code_terminal",
        "label": "Kod ve Terminal Çalıştırma",
        "desc": "Python betikleri, kabuk komutları ve geliştirici araçlarını çalıştırma",
    },
    {
        "key": "perm_vision_screen",
        "label": "Kamera ve Ekran Analizi",
        "desc": "Ekran görüntüsü analizi, OCR ve kamera tabanlı görsel işlemler",
    },
    {
        "key": "perm_profile_admin",
        "label": "UserProfile ve Güvenlik Yönetimi",
        "desc": "Kullanıcı profili ekranını açma, yeni kişi ekleme ve yetki değiştirme",
    },
]


class UserProfileManager:
    """
    NEXUS Merkezi Kullanıcı Profili, Biyometrik Kimlik (Ses + Yüz) ve Yetki Matrisi Motoru:
    - Veritabanında kesin olarak 'sahip' (Sahip) ve 'misafir' (Misafir) profillerini barındırır.
    - Sistemin 'Sahip' veya kayıtlı yetkili kullanıcı olarak doğrulamadığı herkes otomatik olarak
      'Misafir' profilinde değerlendirilir ve sadece Misafir yetki kutucuklarına göre işlem yapılır.
    - Ekstra yetkili kullanıcılar eklenebilir ve her birinin yetkileri kare kutucuklarla (checkbox) seçilir.
    - AI destekli ses ve görüntü kaydı ile gerçek biyometrik vektörler (Voiceprint + Face Embedding)
      çıkarılır, etiketlenir ve gerçek zamanlı karşılaştırma yapılır.
    """

    def __init__(
        self,
        db_path: str = (NEXUS_ROOT + "/data/user_profiles.db"),
    ):
        self.db_path = db_path
        self._lock = threading.Lock()
        self.active_user_id: str = "sahip"
        self.active_match_confidence: float = 0.0
        self.last_auth_method: str = "henuz_dogrulanmadi"
        self.is_enrolling: bool = False

        self._init_db()
        self._ensure_default_profiles()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_profiles (
                        user_id TEXT PRIMARY KEY,
                        display_name TEXT NOT NULL,
                        role_type TEXT NOT NULL,
                        is_builtin INTEGER DEFAULT 0,
                        permissions_json TEXT NOT NULL,
                        voice_enrolled INTEGER DEFAULT 0,
                        face_enrolled INTEGER DEFAULT 0,
                        voice_vec_path TEXT DEFAULT '',
                        face_vec_path TEXT DEFAULT '',
                        face_img_path TEXT DEFAULT '',
                        biometric_labels_json TEXT DEFAULT '{}',
                        created_at REAL,
                        updated_at REAL
                    )
                    """
                )
                conn.commit()
            finally:
                conn.close()

    def _ensure_default_profiles(self):
        """
        Veritabanında 'sahip' (Sahip) ve 'misafir' (Misafir) profillerinin
        kesin olarak var olmasını sağlar.
        """
        now = time.time()
        owner_perms = {p["key"]: True for p in PERMISSION_DEFINITIONS}
        guest_perms = {
            "perm_system_control": False,
            "perm_file_access": False,
            "perm_personal_memory": False,
            "perm_code_terminal": False,
            "perm_vision_screen": False,
            "perm_profile_admin": False,
        }

        with self._lock:
            conn = self._get_conn()
            try:
                cur = conn.execute(
                    "SELECT user_id FROM user_profiles WHERE user_id = 'sahip'"
                )
                if not cur.fetchone():
                    conn.execute(
                        """
                        INSERT INTO user_profiles (
                            user_id, display_name, role_type, is_builtin,
                            permissions_json, voice_enrolled, face_enrolled,
                            biometric_labels_json, created_at, updated_at
                        ) VALUES (?, ?, ?, 1, ?, 0, 0, ?, ?, ?)
                        """,
                        (
                            "sahip",
                            "Sahip (Ana Kullanıcı)",
                            "owner",
                            json.dumps(owner_perms),
                            json.dumps(
                                {
                                    "status": "Biyometrik kayıt bekleniyor",
                                    "voice_tag": "Kayıtsız",
                                    "face_tag": "Kayıtsız",
                                },
                                ensure_ascii=False,
                            ),
                            now,
                            now,
                        ),
                    )

                cur_g = conn.execute(
                    "SELECT user_id FROM user_profiles WHERE user_id = 'misafir'"
                )
                if not cur_g.fetchone():
                    conn.execute(
                        """
                        INSERT INTO user_profiles (
                            user_id, display_name, role_type, is_builtin,
                            permissions_json, voice_enrolled, face_enrolled,
                            biometric_labels_json, created_at, updated_at
                        ) VALUES (?, ?, ?, 1, ?, 0, 0, ?, ?, ?)
                        """,
                        (
                            "misafir",
                            "Misafir (Tanınmayan Kişiler)",
                            "guest",
                            json.dumps(guest_perms),
                            json.dumps(
                                {
                                    "status": "Sahip/Yetkili olarak doğrulanmayan herkes için varsayılan profil",
                                    "voice_tag": "Genel Misafir Filtresi",
                                    "face_tag": "Genel Misafir Filtresi",
                                },
                                ensure_ascii=False,
                            ),
                            now,
                            now,
                        ),
                    )
                conn.commit()
            finally:
                conn.close()

    # ========================================================================
    # PROFİL SORGULAMA, EKLEME VE YETKİ KUTUCUĞU GÜNCELLEME
    # ========================================================================
    def get_all_profiles(self) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM user_profiles ORDER BY is_builtin DESC, created_at ASC"
                ).fetchall()
                result = []
                for r in rows:
                    d = dict(r)
                    d["permissions"] = json.loads(d.get("permissions_json") or "{}")
                    d["biometric_labels"] = json.loads(
                        d.get("biometric_labels_json") or "{}"
                    )
                    # Yüz fotoğrafı varsa küçük Base64 önizlemesini ekle
                    face_img = d.get("face_img_path", "")
                    if face_img and os.path.exists(face_img):
                        try:
                            with open(face_img, "rb") as f:
                                b64 = base64.b64encode(f.read()).decode("ascii")
                                d["face_preview_b64"] = f"data:image/jpeg;base64,{b64}"
                        except Exception:
                            d["face_preview_b64"] = ""
                    else:
                        d["face_preview_b64"] = ""
                    result.append(d)
                return result
            finally:
                conn.close()

    def get_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        for p in self.get_all_profiles():
            if p["user_id"] == user_id:
                return p
        return None

    def is_owner_biometrics_enrolled(self) -> bool:
        owner = self.get_profile("sahip")
        if not owner:
            return False
        return bool(owner.get("voice_enrolled") or owner.get("face_enrolled"))

    def create_authorized_user(
        self, display_name: str, permissions: Optional[Dict[str, bool]] = None
    ) -> Dict[str, Any]:
        clean_name = display_name.strip()
        if not clean_name:
            raise ValueError("Kullanıcı adı boş olamaz.")

        slug = "".join(
            c for c in clean_name.lower().replace(" ", "_") if c.isalnum() or c == "_"
        )
        user_id = f"user_{slug}_{int(time.time()) % 10000}"

        default_perms = {
            "perm_system_control": True,
            "perm_file_access": True,
            "perm_personal_memory": False,
            "perm_code_terminal": False,
            "perm_vision_screen": True,
            "perm_profile_admin": False,
        }
        if permissions:
            default_perms.update({k: bool(v) for k, v in permissions.items()})

        now = time.time()
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO user_profiles (
                        user_id, display_name, role_type, is_builtin,
                        permissions_json, voice_enrolled, face_enrolled,
                        biometric_labels_json, created_at, updated_at
                    ) VALUES (?, ?, 'authorized', 0, ?, 0, 0, ?, ?, ?)
                    """,
                    (
                        user_id,
                        clean_name,
                        json.dumps(default_perms),
                        json.dumps(
                            {
                                "status": "Biyometrik kayıt bekleniyor",
                                "voice_tag": "Kayıtsız",
                                "face_tag": "Kayıtsız",
                            },
                            ensure_ascii=False,
                        ),
                        now,
                        now,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

        logger.info(f"Yeni yetkili kullanıcı profili oluşturuldu: {clean_name} ({user_id})")
        return self.get_profile(user_id) or {}

    def update_user_permissions(
        self, user_id: str, permissions: Dict[str, bool]
    ) -> bool:
        # Sahip profilinin admin yetkisi kilitlenmesin
        if user_id == "sahip":
            permissions["perm_profile_admin"] = True

        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "UPDATE user_profiles SET permissions_json = ?, updated_at = ? WHERE user_id = ?",
                    (json.dumps(permissions), time.time(), user_id),
                )
                conn.commit()
                return True
            finally:
                conn.close()

    def delete_user_profile(self, user_id: str) -> bool:
        if user_id in ("sahip", "misafir"):
            return False
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("DELETE FROM user_profiles WHERE user_id = ?", (user_id,))
                conn.commit()
                if self.active_user_id == user_id:
                    self.active_user_id = "sahip"
                return True
            finally:
                conn.close()

    # ========================================================================
    # SES VE GÖRÜNTÜ BİYOMETRİK ÖZNİTELİK ÇIKARIMI VE ETİKETLEME
    # ========================================================================
    @staticmethod
    def extract_voice_biometric_vector(
        wav_path: str,
    ) -> Tuple[Optional[np.ndarray], Dict[str, Any]]:
        """
        WAV ses kaydından 64-boyutlu normalize Spektral + Pitch (F0) + Enerji
        ses biyometrisi vektörü ve insan tarafından okunabilir ses etiketi çıkarır.
        """
        try:
            with wave.open(wav_path, "rb") as wf:
                sr = wf.getframerate() or 16000
                raw = wf.readframes(wf.getnframes())
                audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

            # Sessiz kısımları kırp
            frame_len = int(sr * 0.03)
            active_chunks = []
            for i in range(0, len(audio) - frame_len, frame_len):
                ch = audio[i : i + frame_len]
                if np.sqrt(np.mean(ch**2)) > 0.015:
                    active_chunks.append(ch)

            if len(active_chunks) < 4:
                active_audio = audio
            else:
                active_audio = np.concatenate(active_chunks)

            if len(active_audio) < 1600:
                return None, {}

            # FFT Spektral Zarf (48 log-frekans bandı)
            n_fft = 512
            hop = 256
            spec_frames = []
            pitches = []
            for i in range(0, len(active_audio) - n_fft, hop):
                seg = active_audio[i : i + n_fft] * np.hanning(n_fft)
                mag = np.abs(np.fft.rfft(seg))[:240]
                # 48 banda indirge
                bands = np.mean(mag.reshape(48, 5), axis=1)
                spec_frames.append(np.log1p(bands))

                # Otokorelasyon ile temel frekans (Pitch F0) tahmini
                corr = np.correlate(seg, seg, mode="full")[n_fft - 1 :]
                min_lag = int(sr / 320)  # max 320 Hz
                max_lag = int(sr / 75)   # min 75 Hz
                if max_lag < len(corr):
                    peak_lag = min_lag + int(np.argmax(corr[min_lag:max_lag]))
                    if corr[peak_lag] > 0.15 * corr[0]:
                        pitches.append(float(sr / peak_lag))

            if not spec_frames:
                return None, {}

            spec_mat = np.array(spec_frames, dtype=np.float32)
            mean_spec = np.mean(spec_mat, axis=0)  # 48-dim
            std_spec = np.std(spec_mat, axis=0)[:16]  # 16-dim

            combined = np.concatenate([mean_spec, std_spec]).astype(np.float32)
            combined -= np.mean(combined)
            norm = float(np.linalg.norm(combined))
            vec = combined / (norm + 1e-8)

            avg_pitch = round(float(np.median(pitches)), 1) if pitches else 135.0
            if avg_pitch < 145:
                timbre = f"Derin/Bariton Tını ({avg_pitch} Hz)"
            elif avg_pitch < 190:
                timbre = f"Orta/Tenor Tını ({avg_pitch} Hz)"
            else:
                timbre = f"Tiz/Parlak Tını ({avg_pitch} Hz)"

            meta = {
                "voice_tag": timbre,
                "fundamental_freq_hz": avg_pitch,
                "duration_sec": round(len(active_audio) / sr, 2),
                "enrolled_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            return vec, meta
        except Exception as e:
            logger.error(f"Ses biyometrisi çıkarma hatası: {e}")
            return None, {}

    @staticmethod
    def extract_face_biometric_vector(
        bgr_frame: np.ndarray,
    ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], Dict[str, Any]]:
        """
        Kamera karesinden yüzü tespit eder, 512-boyutlu aydınlatma-bağımsız yüz vektörü,
        kırpılmış yüz görüntüsü ve görsel etiket meta verisi çıkarır.
        """
        try:
            gray = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2GRAY)
            cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            )
            faces = cascade.detectMultiScale(
                gray, scaleFactor=1.15, minNeighbors=5, minSize=(50, 50)
            )
            if len(faces) > 0:
                faces = sorted(faces, key=lambda r: r[2] * r[3], reverse=True)
                x, y, w, h = [int(v) for v in faces[0]]
                face_gray = gray[y : y + h, x : x + w]
                pad = int(0.15 * w)
                y0, y1 = max(0, y - pad), min(bgr_frame.shape[0], y + h + pad)
                x0, x1 = max(0, x - pad), min(bgr_frame.shape[1], x + w + pad)
                face_color = bgr_frame[y0:y1, x0:x1]
                face_detected = True
            else:
                h, w = gray.shape[:2]
                face_gray = gray[h // 5 : 4 * h // 5, w // 4 : 3 * w // 4]
                face_color = bgr_frame[h // 5 : 4 * h // 5, w // 4 : 3 * w // 4]
                face_detected = False

            resized = cv2.resize(face_gray, (64, 64))
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            norm_img = clahe.apply(resized).astype(np.float32)

            spatial = cv2.resize(norm_img, (16, 16)).flatten()
            gx = np.diff(norm_img, axis=1, append=norm_img[:, -1:])
            gy = np.diff(norm_img, axis=0, append=norm_img[-1:, :])
            grad_mag = np.sqrt(gx**2 + gy**2)
            grad_feat = cv2.resize(grad_mag, (16, 16)).flatten()

            vec = np.concatenate([spatial, grad_feat]).astype(np.float32)
            vec -= np.mean(vec)
            vec = vec / (float(np.linalg.norm(vec)) + 1e-8)

            lum = round(float(np.mean(face_gray)), 1)
            meta = {
                "face_tag": f"{'Net Yüz Tespit Edildi' if face_detected else 'Merkez Portre'} (Işık: {lum})",
                "face_detected": face_detected,
                "enrolled_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            preview_bgr = cv2.resize(face_color, (160, 160))
            return vec, preview_bgr, meta
        except Exception as e:
            logger.error(f"Yüz biyometrisi çıkarma hatası: {e}")
            return None, None, {}

    def enroll_user_biometrics_interactive(
        self,
        user_id: str,
        voice_engine,
        ui_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """
        AI tarafından yönetilen etkileşimli Ses + Görüntü Biyometrik Kayıt Akışı:
        1. Kullanıcıdan kameraya bakmasını ister ve 3 kare çekip ortalama yüz vektörünü etiketler.
        2. Kullanıcıdan birkaç saniye konuşmasını ister, mikrofondan kaydedip ses vektörünü etiketler.
        3. Veritabanını günceller ve sonucu bildirir.
        """
        import sounddevice as sd
        from scipy.io.wavfile import write

        profile = self.get_profile(user_id)
        if not profile:
            return {"ok": False, "message": "Kullanıcı profili bulunamadı."}

        self.is_enrolling = True
        disp_name = profile["display_name"].split("(")[0].strip()

        try:
            # ADIM 1: KAMERADAN YÜZ GÖRÜNTÜSÜ TOPLAMA VE ETİKETLEME
            msg_cam = f"{disp_name} profili için biyometrik kayıt başlatıldı. Lütfen şimdi kameraya doğru bak, yüz görüntünü alıp işliyorum."
            if ui_callback:
                ui_callback({"action": "biometric_status", "text": "📷 Kamera açılıyor: Yüz biyometrisi taranıyor..."})
            voice_engine.speak(msg_cam)
            while voice_engine.is_speaking:
                time.sleep(0.1)

            cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            if not cap.isOpened():
                cap = cv2.VideoCapture(0)

            face_vecs = []
            best_preview = None
            face_meta = {}
            if cap.isOpened():
                for _ in range(5):
                    ret, frm = cap.read()
                    if ret and frm is not None:
                        v, prev, m = self.extract_face_biometric_vector(frm)
                        if v is not None:
                            face_vecs.append(v)
                            best_preview = prev
                            face_meta = m
                    time.sleep(0.15)
                cap.release()

            face_vec_path = ""
            face_img_path = ""
            face_ok = False
            if face_vecs:
                avg_face_vec = np.mean(np.stack(face_vecs, axis=0), axis=0)
                avg_face_vec = avg_face_vec / (float(np.linalg.norm(avg_face_vec)) + 1e-8)
                face_vec_path = os.path.join(BIOMETRICS_DIR, f"{user_id}_face.npy")
                face_img_path = os.path.join(BIOMETRICS_DIR, f"{user_id}_face.jpg")
                np.save(face_vec_path, avg_face_vec)
                if best_preview is not None:
                    cv2.imwrite(face_img_path, best_preview)
                # Eğer 'sahip' ise ana owner_face dosyalarını da senkronize et
                if user_id == "sahip":
                    np.save((NEXUS_ROOT + "/owner_face_vec.npy"), avg_face_vec)
                    if best_preview is not None:
                        cv2.imwrite((NEXUS_ROOT + "/owner_face.jpg"), best_preview)
                face_ok = True

            # ADIM 2: MİKROFONDAN SES BİYOMETRİSİ TOPLAMA VE ETİKETLEME
            msg_mic = "Yüz görüntün etiketlendi. Şimdi ses biyometrini çıkarabilmem için sinyalden sonra 3 saniye boyunca doğal sesinle konuş."
            if ui_callback:
                ui_callback({"action": "biometric_status", "text": "🎙️ Mikrofon dinleniyor: Lütfen 3.5 saniye boyunca konuşun..."})
            voice_engine.speak(msg_mic)
            while voice_engine.is_speaking:
                time.sleep(0.1)
            time.sleep(0.2)

            sr = 16000
            rec_sec = 3.6
            rec_frames = sd.rec(int(sr * rec_sec), samplerate=sr, channels=1, dtype="int16")
            sd.wait()

            wav_out = os.path.join(BIOMETRICS_DIR, f"{user_id}_voice_sample.wav")
            write(wav_out, sr, rec_frames)

            voice_vec, voice_meta = self.extract_voice_biometric_vector(wav_out)
            voice_vec_path = ""
            voice_ok = False
            if voice_vec is not None:
                voice_vec_path = os.path.join(BIOMETRICS_DIR, f"{user_id}_voice.npy")
                np.save(voice_vec_path, voice_vec)
                voice_ok = True

            # ADIM 3: VERİTABANINA ETİKETLERİ VE VEKTÖR YOLLARINI KAYDET
            labels = profile.get("biometric_labels", {})
            labels["status"] = "Aktif & Doğrulanmış Biyometrik Profil"
            labels["face_tag"] = face_meta.get("face_tag", "Kayıtlı Yüz Vektörü") if face_ok else "Kamera Bulunamadı"
            labels["voice_tag"] = voice_meta.get("voice_tag", "Kayıtlı Ses İzi") if voice_ok else "Ses Algılanamadı"
            labels["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

            with self._lock:
                conn = self._get_conn()
                try:
                    conn.execute(
                        """
                        UPDATE user_profiles
                        SET voice_enrolled = ?, face_enrolled = ?,
                            voice_vec_path = ?, face_vec_path = ?, face_img_path = ?,
                            biometric_labels_json = ?, updated_at = ?
                        WHERE user_id = ?
                        """,
                        (
                            1 if voice_ok else 0,
                            1 if face_ok else 0,
                            voice_vec_path,
                            face_vec_path,
                            face_img_path,
                            json.dumps(labels, ensure_ascii=False),
                            time.time(),
                            user_id,
                        ),
                    )
                    conn.commit()
                finally:
                    conn.close()

            done_msg = (
                f"{disp_name} profili için yüz ve ses biyometrisi başarıyla işlendi, etiketlendi ve veritabanına kaydedildi. "
                "Artık kullanıcı ayrımını bu biyometrik verilerle yapacağım."
            )
            if ui_callback:
                ui_callback({"action": "refresh_user_profiles", "status_text": "✅ Biyometrik kayıt ve etiketleme tamamlandı!"})
            voice_engine.speak(done_msg)
            return {"ok": True, "message": done_msg, "profile": self.get_profile(user_id)}
        except Exception as e:
            logger.error(f"Etkileşimli biyometrik kayıt hatası: {e}")
            return {"ok": False, "message": f"Biyometrik kayıt hatası: {e}"}
        finally:
            self.is_enrolling = False

    # ========================================================================
    # GERÇEK ZAMANLI SES VE YÜZ KARŞILAŞTIRMA (KULLANICI AYRIMI MOTORU)
    # ========================================================================
    def identify_speaker_from_wav(
        self, wav_path: str, threshold: float = 0.76
    ) -> Tuple[str, float, Dict[str, Any]]:
        """
        Konuşan kişinin ses kaydını veritabanındaki kayıtlı kullanıcıların ('sahip' ve eklenen profiller)
        ses vektörleriyle karşılaştırır:
        - Eğer veritabanında henüz hiçbir biyometrik kayıt yoksa: 'sahip' döndürür (ancak durumu 'kayıtsız' olarak işaretler).
        - Eğer kayıt varsa ve eşleşme >= threshold ise: Eşleşen kullanıcı profilini ('sahip' veya 'user_xxx') döndürür.
        - Eşleşme < threshold ise: Kişiyi otomatik olarak 'misafir' (Misafir) profiline geçirir!
        """
        profiles = self.get_all_profiles()
        enrolled_profiles = [
            p
            for p in profiles
            if p["user_id"] != "misafir"
            and p.get("voice_enrolled")
            and p.get("voice_vec_path")
            and os.path.exists(p["voice_vec_path"])
        ]

        if not enrolled_profiles:
            # Henüz biyometrik kayıt yapılmamış
            self.active_user_id = "sahip"
            self.active_match_confidence = 0.0
            self.last_auth_method = "veritabaninda_kayit_yok"
            return "sahip", 0.0, self.get_profile("sahip") or {}

        cur_vec, _ = self.extract_voice_biometric_vector(wav_path)
        if cur_vec is None:
            return self.active_user_id, self.active_match_confidence, self.get_profile(self.active_user_id) or {}

        best_uid = "misafir"
        best_score = 0.0

        for p in enrolled_profiles:
            try:
                ref_vec = np.load(p["voice_vec_path"])
                if ref_vec.shape == cur_vec.shape:
                    sim = float(np.dot(ref_vec, cur_vec))
                    if sim > best_score:
                        best_score = sim
                        if sim >= threshold:
                            best_uid = p["user_id"]
            except Exception:
                continue

        self.active_user_id = best_uid
        self.active_match_confidence = round(best_score, 3)
        self.last_auth_method = f"ses_biyometrisi (skor: {self.active_match_confidence})"
        matched_prof = self.get_profile(best_uid) or self.get_profile("misafir") or {}
        logger.info(
            f"Ses Kimlik Tespiti -> Aktif Profil: {best_uid} | Benzerlik: {self.active_match_confidence}"
        )
        return best_uid, self.active_match_confidence, matched_prof

    def check_permission(self, permission_key: str, user_id: Optional[str] = None) -> bool:
        uid = user_id or self.active_user_id
        prof = self.get_profile(uid)
        if not prof:
            prof = self.get_profile("misafir")
        if not prof:
            return False
        perms = prof.get("permissions", {})
        return bool(perms.get(permission_key, False))
