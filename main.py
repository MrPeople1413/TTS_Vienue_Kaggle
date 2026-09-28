"""
Vietnamese TTS Audiobook Reader  v2.1
======================================
Ứng dụng đọc truyện tiếng Việt:
  • Edge TTS     (online  – giọng HoaiMy Neural)
  • VieNeu TTS   (offline – nhiều giọng, clone giọng)
  • Kaggle Batch (offline pipeline – GPU T4 x2, không cần bore tunnel)
Portable: tất cả data lưu trong cùng thư mục với main.py.
"""

# ── Thư viện chuẩn ───────────────────────────────────────────────────────────
import sys, os, io, re, json, hashlib, queue, threading, time, ctypes
from datetime import datetime
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional, Tuple

# ── GUI ───────────────────────────────────────────────────────────────────────
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ── Audio playback ────────────────────────────────────────────────────────────
try:
    import pygame
    pygame.mixer.init(frequency=48000, size=-16, channels=1, buffer=2048)
    PYGAME_OK = True
except Exception:
    PYGAME_OK = False

# ── Kaggle Batch (import trước APP_DIR để available toàn app) ────────────────
try:
    from kaggle_batch import KaggleBatchManager, KaggleBatchConfig
    KAGGLE_BATCH_OK = True
except ImportError:
    KAGGLE_BATCH_OK = False

# ── Thư mục gốc (portable) ───────────────────────────────────────────────────
# Tất cả data lưu trong thư mục chứa main.py → dễ copy/xóa
APP_DIR     = Path(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR  = APP_DIR / "models"         # model VieNeu (~1.2 GB)
VOICES_DIR  = APP_DIR / "voices"         # WAV+TXT để clone giọng
CONFIG_DIR  = APP_DIR / "config"         # settings & vị trí đọc
EXPORTS_DIR = APP_DIR / "audio_exports"  # file audio xuất ra
CACHE_DIR   = APP_DIR / "cache"          # cache audio chunk

for _d in [MODELS_DIR, VOICES_DIR, CONFIG_DIR, EXPORTS_DIR, CACHE_DIR]:
    _d.mkdir(exist_ok=True)

# Đặt biến môi trường HuggingFace TRƯỚC KHI import bất kỳ thứ gì
# → buộc VieNeu tải model vào ./models/ thay vì ~/.cache
os.environ["HF_HOME"]                         = str(MODELS_DIR)
os.environ["HUGGINGFACE_HUB_CACHE"]          = str(MODELS_DIR)
os.environ["TRANSFORMERS_CACHE"]             = str(MODELS_DIR)
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

# ── In thông tin version khi khởi động ───────────────────────────────────────
try:
    import importlib.metadata as _meta
    _vieneu_ver = _meta.version("vieneu")
except Exception:
    try:
        import vieneu as _v
        _vieneu_ver = getattr(_v, "__version__", "unknown")
    except Exception:
        _vieneu_ver = "not installed"
print(f"[App] VieNeu version : {_vieneu_ver}")
print(f"[App] Model cache    : {MODELS_DIR}")
print(f"[App] HF_HOME        : {os.environ.get('HF_HOME', 'not set')}")


# ═══════════════════════════════════════════════════════════════════════════════
# SETTINGS & POSITION MANAGER
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class AppSettings:
    """Tất cả cài đặt người dùng — lưu vào config/settings.json."""
    engine:        str   = "edge_tts"    # "edge_tts" | "vieneu"
    edge_voice:    str   = "vi-VN-HoaiMyNeural"
    vieneu_voice:  str   = ""            # voice_id của VieNeu preset/custom
    vieneu_device: str   = "cpu"         # "cpu" | "gpu"
    speed:         float = 1.0           # 0.5 – 2.0
    volume:        float = 0.85
    chunk_size:     int   = 180                 # số ký tự mỗi chunk TTS
    export_workers: int   = 4                  # số chunk synth song song khi xuất (Edge TTS)
    vieneu_threads: int   = 0                  # số CPU threads cho VieNeu (0 = tự động = toàn bộ core)
    auto_next:      bool  = True               # tự chuyển file khi xong
    use_cache:      bool  = True               # cache audio chunk ra đĩa
    last_folder:    str   = ""
    export_dir:     str   = ""                 # thư mục xuất audio tùy chọn

    # ── Kaggle Batch Pipeline ─────────────────────────────────────────────────
    kaggle_username    : str  = ""               # Kaggle username
    kaggle_api_key     : str  = ""               # Kaggle API key
    kaggle_dataset_slug: str  = "viettt-tts-input"  # tên dataset
    kaggle_kernel_slug : str  = ""               # "username/kernel-name"
    kaggle_batch_voice : str  = ""               # voice_id gửi lên Kaggle
    kaggle_batch_size  : int  = 10               # số chap mỗi batch ZIP
    kaggle_poll_sec    : int  = 40               # giây giữa 2 lần poll


class SettingsManager:
    """Đọc/ghi settings và vị trí đọc từng file."""

    def __init__(self):
        self.sf = CONFIG_DIR / "settings.json"
        self.pf = CONFIG_DIR / "positions.json"
        self.settings  = AppSettings()
        self.positions: dict = {}
        self._load()

    def _load(self):
        try:
            if self.sf.exists():
                data  = json.loads(self.sf.read_text("utf-8"))
                valid = {f for f in AppSettings.__dataclass_fields__}
                # Bỏ qua field lạ (từ phiên bản cũ) để tránh crash
                self.settings = AppSettings(**{k: v for k, v in data.items() if k in valid})
        except Exception:
            pass
        try:
            if self.pf.exists():
                self.positions = json.loads(self.pf.read_text("utf-8"))
        except Exception:
            pass

        # ── Tự động đọc kaggle.json (cùng thư mục main.py) ──────────────────
        # Username + key KHÔNG lưu vào settings.json để tránh lộ thông tin.
        # kaggle.json được đọc mỗi lần khởi động → chỉnh sửa file đó là đủ.
        self._load_kaggle_json()

    def _load_kaggle_json(self):
        """Đọc credentials từ kaggle.json nếu tồn tại, ưu tiên hơn settings."""
        for candidate in [
            APP_DIR / "kaggle.json",          # cùng thư mục main.py
            Path.home() / ".kaggle" / "kaggle.json",  # vị trí mặc định của Kaggle CLI
        ]:
            if candidate.exists():
                try:
                    kj = json.loads(candidate.read_text("utf-8"))
                    u  = kj.get("username", "").strip()
                    k  = kj.get("key", "").strip()
                    if u and k:
                        self.settings.kaggle_username = u
                        self.settings.kaggle_api_key  = k
                        print(f"[Settings] Kaggle credentials loaded from: {candidate}")
                        return
                except Exception as e:
                    print(f"[Settings] Không đọc được {candidate}: {e}")

    def save(self):
        # Không lưu username/api_key vào settings.json (giữ trong kaggle.json)
        import dataclasses
        data = dataclasses.asdict(self.settings)
        data.pop("kaggle_username", None)
        data.pop("kaggle_api_key",  None)
        self.sf.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
        self.pf.write_text(json.dumps(self.positions, ensure_ascii=False, indent=2), "utf-8")

    def save_position(self, path: str, chunk_idx: int):
        """Lưu vị trí chunk đang đọc của một file."""
        self.positions[path] = {"chunk_index": chunk_idx, "ts": time.time()}
        self.save()

    def get_position(self, path: str) -> int:
        return self.positions.get(path, {}).get("chunk_index", 0)


# ═══════════════════════════════════════════════════════════════════════════════
# AUDIO CACHE
# ═══════════════════════════════════════════════════════════════════════════════

class AudioCache:
    """
    Cache audio chunk ra đĩa (./cache/).
    Key = MD5(text + engine + voice + speed) → tránh nhầm khi đổi giọng.
    Tự dọn LRU khi vượt MAX_SIZE_MB.
    Custom voice (giọng clone) KHÔNG được cache vì mỗi người khác nhau.
    """
    MAX_SIZE_MB = 500

    def __init__(self):
        self._lock = threading.Lock()

    def _key(self, text: str, engine: str, voice: str, speed: float) -> str:
        return hashlib.md5(f"{text}|{engine}|{voice}|{speed:.1f}".encode()).hexdigest()

    def get(self, text: str, engine: str, voice: str, speed: float, fmt: str) -> Optional[bytes]:
        path = CACHE_DIR / f"{self._key(text, engine, voice, speed)}.{fmt}"
        if path.exists():
            try:
                with self._lock:
                    data = path.read_bytes()
                path.touch()  # cập nhật atime cho LRU
                return data
            except Exception:
                return None
        return None

    def put(self, text: str, engine: str, voice: str, speed: float, fmt: str, data: bytes):
        path = CACHE_DIR / f"{self._key(text, engine, voice, speed)}.{fmt}"
        try:
            with self._lock:
                path.write_bytes(data)
            self._evict_if_needed()
        except Exception as e:
            print(f"[Cache] Loi ghi: {e}")

    def _evict_if_needed(self):
        """Xóa file cũ nhất (LRU) khi vượt giới hạn."""
        try:
            files = list(CACHE_DIR.glob("*.*"))
            total = sum(f.stat().st_size for f in files) / 1024 / 1024
            if total <= self.MAX_SIZE_MB:
                return
            files.sort(key=lambda f: f.stat().st_atime)
            for f in files:
                if total <= self.MAX_SIZE_MB * 0.8:
                    break
                total -= f.stat().st_size / 1024 / 1024
                f.unlink(missing_ok=True)
        except Exception:
            pass

    def clear(self):
        with self._lock:
            for f in CACHE_DIR.glob("*.*"):
                try: f.unlink()
                except: pass

    def size_mb(self) -> float:
        try:
            return sum(f.stat().st_size for f in CACHE_DIR.glob("*.*")) / 1024 / 1024
        except: return 0.0

    def count(self) -> int:
        try:  return len(list(CACHE_DIR.glob("*.*")))
        except: return 0


# ═══════════════════════════════════════════════════════════════════════════════
# TEXT PROCESSOR
# ═══════════════════════════════════════════════════════════════════════════════

class TextProcessor:
    """Làm sạch và tách văn bản tiếng Việt thành các chunk nhỏ để TTS."""

    # Xóa ký tự đặc biệt, giữ lại chữ cái + dấu câu thông thường
    _NOISE = re.compile(r'[^\w\s\.,!?;:\-\(\)\[\]\"\'\/\n\u00C0-\u024F\u1E00-\u1EFF]')

    @staticmethod
    def load(path: str) -> str:
        """Đọc file .txt, thử nhiều encoding phổ biến."""
        for enc in ("utf-8-sig", "utf-8", "cp1258", "latin-1"):
            try:
                return Path(path).read_text(enc)
            except (UnicodeDecodeError, LookupError):
                continue
        raise ValueError(f"Khong doc duoc: {path}")

    @staticmethod
    def clean(text: str) -> str:
        """Chuẩn hóa khoảng trắng và loại bỏ ký tự lỗi."""
        text = TextProcessor._NOISE.sub(" ", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def split_chunks(text: str, max_chars: int = 180) -> List[str]:
        """
        Tách văn bản thành các chunk <= max_chars ký tự.
        Ưu tiên tách theo câu (dấu . ! ?) rồi mới tách theo dòng/dấu phẩy.
        Tự động loại bỏ chunk trùng lặp liền kề.
        """
        # Tách theo dòng trước, mỗi dòng là đơn vị tối thiểu
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        sentences = []
        for line in lines:
            parts = re.split(r'(?<=[.!?…。])\s+', line)
            sentences.extend(p.strip() for p in parts if p.strip())

        chunks: List[str] = []
        cur = ""
        for s in sentences:
            if not cur:
                cur = s
            elif len(cur) + 1 + len(s) <= max_chars:
                cur = cur + " " + s
            else:
                chunks.append(cur)
                if len(s) > max_chars:
                    # Câu quá dài → tách thêm theo dấu phẩy
                    sub_parts = re.split(r',\s*', s)
                    cur = ""
                    for part in sub_parts:
                        part = part.strip()
                        if not part:
                            continue
                        if not cur:
                            cur = part
                        elif len(cur) + 2 + len(part) <= max_chars:
                            cur = cur + ", " + part
                        else:
                            chunks.append(cur)
                            cur = part
                else:
                    cur = s
        if cur:
            chunks.append(cur)

        # Loại bỏ chunk trùng lặp liền kề (phổ biến với truyện tải từ web)
        result = []
        for c in chunks:
            if not result or c != result[-1]:
                result.append(c)
        return result


# ═══════════════════════════════════════════════════════════════════════════════
# TTS ENGINES
# ═══════════════════════════════════════════════════════════════════════════════

class EdgeTTSEngine:
    """
    Microsoft Edge TTS – gọi API của trình duyệt Edge.
    Ưu điểm: giọng HoaiMy Neural rất tự nhiên, miễn phí.
    Nhược điểm: cần internet.
    """
    VOICES: List[Tuple[str, str]] = [
        ("🌸 HoaiMy – Nu mien Bac (Neural ⭐)", "vi-VN-HoaiMyNeural"),
        ("🔵 NamMinh – Nam mien Bac (Neural)",  "vi-VN-NamMinhNeural"),
    ]

    def get_voice_list(self) -> List[Tuple[str, str]]:
        return self.VOICES

    def synth(self, text: str, voice_id: str, speed: float) -> bytes:
        """Tổng hợp giọng nói, trả về MP3 bytes."""
        import asyncio, edge_tts
        rate = f"+{int((speed-1)*100)}%" if speed >= 1 else f"{int((speed-1)*100)}%"

        async def _run():
            buf = b""
            async for chunk in edge_tts.Communicate(text, voice_id, rate=rate).stream():
                if chunk["type"] == "audio":
                    buf += chunk["data"]
            return buf

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_run())
        finally:
            loop.close()


# ═══════════════════════════════════════════════════════════════════════════════
# VIENEU TTS ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class VieNeuTTSEngine:
    """
    VieNeu TTS – chạy hoàn toàn offline.
    Ưu điểm: nhiều giọng, hỗ trợ clone giọng từ file WAV.
    Nhược điểm: cần tải model ~1.2 GB, chậm hơn Edge TTS trên CPU.
    Model lưu trong ./models/ (không vào ~/.cache).
    """
    CUSTOM_PREFIX = "custom::"  # tiền tố phân biệt giọng clone với preset

    def __init__(self):
        self._tts             = None
        self._ready           = False
        self._current_device  = None
        self._current_threads = 0
        self._current_remote  = ""
        self._preset_cache: List[Tuple[str, str]] = []
        self._voice_cache:  dict = {}

    # ── Load model ────────────────────────────────────────────────────────────

    def _ensure_loaded(self, device: str = "cpu", n_threads: int = 0,
                       remote_url: str = ""):
        _threads = n_threads if n_threads > 0 else (os.cpu_count() or 4)
        _remote  = remote_url.rstrip("/")

        if (self._ready
                and self._current_device  == device
                and self._current_threads == _threads
                and self._current_remote  == _remote):
            return

        if self._tts is not None:
            self._tts = None
            self._ready = False
            self._voice_cache.clear()

        from vieneu import Vieneu

        if _remote:
            print(f"[VieNeu] Remote mode → {_remote}")
            api_base = _remote if _remote.endswith("/v1") else f"{_remote}/v1"
            self._tts = Vieneu(
                mode       = "remote",
                api_base   = api_base,
                model_name = "pnnbao-ump/VieNeu-TTS",
            )
            self._current_device  = "remote"
            self._current_threads = 0
            self._current_remote  = _remote
            self._ready = True
            print(f"[VieNeu] Ket noi remote OK: {api_base}")
            return

        ts = str(_threads)
        os.environ["OMP_NUM_THREADS"]        = ts
        os.environ["MKL_NUM_THREADS"]        = ts
        os.environ["OPENBLAS_NUM_THREADS"]   = ts
        os.environ["NUMEXPR_NUM_THREADS"]    = ts
        os.environ["VECLIB_MAXIMUM_THREADS"] = ts
        try:
            import torch
            torch.set_num_threads(_threads)
            torch.set_num_interop_threads(max(1, _threads // 2))
        except Exception:
            pass

        if device == "gpu":
            try:
                print("[VieNeu] Khoi dong GPU...")
                self._tts = Vieneu(backbone_kwargs={"n_gpu_layers": 99})
            except Exception as e:
                print(f"[VieNeu] GPU that bai ({e}) → fallback CPU")
                self._tts = Vieneu()
                device = "cpu"
        else:
            print(f"[VieNeu] Khoi dong CPU ({_threads} threads)...")
            print(f"[VieNeu] Model cache: {os.environ.get('HF_HOME', 'default')}")
            self._tts = Vieneu()

        self._current_device  = device
        self._current_threads = _threads
        self._current_remote  = ""
        self._ready = True
        print(f"[VieNeu] San sang ({device.upper()}, {_threads} threads)")

    # ── Giọng clone ───────────────────────────────────────────────────────────

    def scan_custom_voices(self) -> List[Tuple[str, str]]:
        result = []
        for wav in sorted(VOICES_DIR.glob("*.wav")):
            if not wav.with_suffix(".txt").exists():
                continue
            label_file = wav.with_suffix(".label")
            display = (label_file.read_text("utf-8").strip()
                       if label_file.exists() else wav.stem)
            result.append((f"🎤 {display}", f"{self.CUSTOM_PREFIX}{wav.stem}"))
        return result

    def get_custom_voice_info(self) -> List[dict]:
        result = []
        for wav in sorted(VOICES_DIR.glob("*.wav")):
            txt = wav.with_suffix(".txt")
            if not txt.exists():
                continue
            label_file = wav.with_suffix(".label")
            display = (label_file.read_text("utf-8").strip()
                       if label_file.exists() else wav.stem)
            result.append({
                "stem":    wav.stem,
                "display": display,
                "wav":     wav,
                "txt":     txt,
                "label":   label_file,
                "vid":     f"{self.CUSTOM_PREFIX}{wav.stem}",
            })
        return result

    def rename_custom_voice(self, stem: str, new_display: str):
        (VOICES_DIR / f"{stem}.label").write_text(new_display.strip(), "utf-8")
        self._voice_cache.pop(f"{self.CUSTOM_PREFIX}{stem}", None)
        self._preset_cache.clear()

    def delete_custom_voice(self, stem: str):
        for ext in (".wav", ".txt", ".label"):
            f = VOICES_DIR / f"{stem}{ext}"
            if f.exists():
                f.unlink()
        self._voice_cache.pop(f"{self.CUSTOM_PREFIX}{stem}", None)
        self._preset_cache.clear()

    # ── Danh sách giọng ───────────────────────────────────────────────────────

    def get_voice_list(self, device: str = "cpu") -> List[Tuple[str, str]]:
        if self._preset_cache:
            return self._preset_cache
        try:
            self._ensure_loaded(device)
            result = list(self.scan_custom_voices())
            for desc, name in self._tts.list_preset_voices():
                dl = desc.lower()
                icon   = "🌸" if any(k in dl for k in ["nữ","female","hoai","thu","hoa","my"]) else \
                         "🔹" if any(k in dl for k in ["nam","male","minh","hung"]) else "⚪"
                region = " [Bac]" if any(k in dl for k in ["bắc","bac","hanoi"]) else \
                         " [Nam]" if any(k in dl for k in ["nam","south","hcm"]) else ""
                result.append((f"{icon} {desc}{region}", name))
            self._preset_cache = result
            return result
        except ImportError:
            return [("Chua cai vieneu – chay install_vieneu.bat", "")]
        except Exception as e:
            return [(f"Loi: {str(e)[:50]}", "")]

    def reset_cache(self):
        self._preset_cache.clear()
        self._voice_cache.clear()

    def _get_voice_data(self, voice_id: str):
        cached = self._voice_cache.get(voice_id)
        if cached is not None:
            return cached
        if voice_id.startswith(self.CUSTOM_PREFIX):
            stem     = voice_id[len(self.CUSTOM_PREFIX):]
            wav_path = VOICES_DIR / f"{stem}.wav"
            if not wav_path.exists():
                return None
            try:
                data = self._tts.encode_reference(str(wav_path))
                self._voice_cache[voice_id] = data
                return data
            except Exception as e:
                print(f"[VieNeu] Loi encode {stem}: {e}")
                return None
        else:
            try:
                data = self._tts.get_preset_voice(voice_id)
                self._voice_cache[voice_id] = data
                return data
            except Exception as e:
                print(f"[VieNeu] Loi get preset {voice_id}: {e}")
                return None

    # ── Tổng hợp ──────────────────────────────────────────────────────────────

    def synth(self, text: str, voice_id: str, speed: float,
              device: str = "cpu", n_threads: int = 0,
              remote_url: str = "") -> bytes:
        import numpy as np, soundfile as sf
        self._ensure_loaded(device, n_threads, remote_url)
        kwargs = {}
        if voice_id:
            if voice_id.startswith(self.CUSTOM_PREFIX):
                stem     = voice_id[len(self.CUSTOM_PREFIX):]
                wav_path = VOICES_DIR / f"{stem}.wav"
                txt_path = VOICES_DIR / f"{stem}.txt"
                if wav_path.exists():
                    kwargs["ref_audio"] = str(wav_path)
                    if txt_path.exists():
                        kwargs["ref_text"] = txt_path.read_text("utf-8").strip()
            else:
                vdata = self._get_voice_data(voice_id)
                if vdata is not None:
                    kwargs["voice"] = vdata
        result = self._tts.infer(text=text, **kwargs)
        if isinstance(result, np.ndarray):
            audio, sr = result, 48000   # v3 mặc định 48kHz
        elif hasattr(result, "audio"):
            audio, sr = result.audio, getattr(result, "sample_rate", 48000)
        else:
            audio, sr = np.array(result), 48000
        buf = io.BytesIO()
        sf.write(buf, audio, samplerate=sr, format="WAV")
        return buf.getvalue()


# ═══════════════════════════════════════════════════════════════════════════════
# AUDIO PLAYER
# ═══════════════════════════════════════════════════════════════════════════════

class AudioPlayer:
    """Phát audio bytes qua pygame mixer."""

    def __init__(self):
        self._lock = threading.Lock()

    def play(self, data: bytes, fmt: str = "mp3"):
        if not PYGAME_OK or not data:
            return
        with self._lock:
            try:
                pygame.mixer.music.load(io.BytesIO(data), fmt)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    time.sleep(0.04)
            except Exception as e:
                print(f"[Audio] {e}")

    def stop(self):
        if PYGAME_OK:
            try: pygame.mixer.music.stop()
            except: pass

    def pause(self):
        if PYGAME_OK:
            try: pygame.mixer.music.pause()
            except: pass

    def resume(self):
        if PYGAME_OK:
            try: pygame.mixer.music.unpause()
            except: pass

    def set_volume(self, v: float):
        if PYGAME_OK:
            try: pygame.mixer.music.set_volume(max(0.0, min(1.0, v)))
            except: pass


# ═══════════════════════════════════════════════════════════════════════════════
# TTS WORKER  (pipeline 2 thread)
# ═══════════════════════════════════════════════════════════════════════════════
#
#  Thread SYNTH: tổng hợp chunk → đẩy vào _audio_q (buffer PREFETCH)
#  Thread PLAY : lấy từ _audio_q → phát liên tục, không chờ synth
#  → chunk tiếp theo đã sẵn sàng trước khi chunk hiện tại phát xong
#  → không còn khoảng im lặng giữa các câu
#
#  Cơ chế dừng: dùng _gen (generation counter) thay vì Event
#  → tránh race condition khi stop() và speak() gọi gần nhau

class TTSWorker:
    PREFETCH = 3  # số chunk synth trước trong buffer

    def __init__(self, player: AudioPlayer, cfg: AppSettings):
        self.player = player
        self.cfg    = cfg
        self.cache  = AudioCache()

        self._edge   = EdgeTTSEngine()
        self._vieneu = VieNeuTTSEngine()

        self.cur_idx = 0   # chunk đang phát
        self._gen    = 0   # tăng mỗi lần interrupt → thread cũ tự dừng

        # Callbacks gọi về UI thread (set từ VietTTSApp)
        self.on_chunk_start: Optional[callable] = None
        self.on_chunk_done:  Optional[callable] = None
        self.on_file_done:   Optional[callable] = None
        self.on_error:       Optional[callable] = None

        # Queue: task từ UI → synth thread
        self._task_q:  queue.Queue = queue.Queue()
        # Queue: audio từ synth thread → play thread
        # maxsize = PREFETCH + 1 để luôn có slot cho sentinel DONE
        self._audio_q: queue.Queue = queue.Queue(maxsize=self.PREFETCH + 1)

        self._pause = threading.Event()
        self._pause.set()

        threading.Thread(target=self._synth_loop, daemon=True, name="TTS-Synth").start()
        threading.Thread(target=self._play_loop,  daemon=True, name="TTS-Play").start()

    # ── Public API ────────────────────────────────────────────────────────────

    def speak(self, chunks: List[str], start: int = 0):
        """Dừng task cũ, bắt đầu đọc từ chunk `start`."""
        self._interrupt()
        self._task_q.put({"chunks": chunks, "start": start, "gen": self._gen})

    def pause(self):
        self._pause.clear()
        self.player.pause()

    def resume(self):
        self._pause.set()
        self.player.resume()

    def stop(self):
        self._interrupt()

    def get_voice_list(self) -> List[Tuple[str, str]]:
        device = getattr(self.cfg, "vieneu_device", "cpu")
        if self.cfg.engine == "vieneu":
            return self._vieneu.get_voice_list(device)
        return self._edge.get_voice_list()

    def reload_vieneu_voices(self) -> List[Tuple[str, str]]:
        self._vieneu.reset_cache()
        return self._vieneu.get_voice_list(getattr(self.cfg, "vieneu_device", "cpu"))

    # ── Internal ──────────────────────────────────────────────────────────────

    def _interrupt(self):
        """Tăng gen → tất cả thread đang chạy với gen cũ sẽ tự dừng."""
        self._gen += 1
        self._pause.set()     # tránh deadlock nếu đang pause
        self.player.stop()
        self._drain(self._audio_q)
        self._drain(self._task_q)

    @staticmethod
    def _drain(q: queue.Queue):
        while not q.empty():
            try: q.get_nowait()
            except queue.Empty: break

    def _synth_loop(self):
        """Thread tổng hợp: lấy task → synth từng chunk → đẩy vào _audio_q."""
        while True:
            try:
                task = self._task_q.get(timeout=0.1)
            except queue.Empty:
                continue

            chunks, start, my_gen = task["chunks"], task.get("start", 0), task.get("gen", 0)

            for i, chunk in enumerate(chunks[start:], start=start):
                if my_gen != self._gen: break
                self._pause.wait()
                if my_gen != self._gen: break

                data, fmt = self._synth_with_retry(chunk)

                # Đẩy vào buffer; block (backpressure) nếu play chưa kịp
                while True:
                    if my_gen != self._gen: break
                    try:
                        self._audio_q.put((i, data, fmt, my_gen), timeout=0.2)
                        break
                    except queue.Full:
                        continue

            # Sentinel báo hết file — retry cho đến khi queue có chỗ
            # (không dùng timeout cố định vì queue có thể đầy lâu hơn 1s)
            if my_gen == self._gen:
                while my_gen == self._gen:
                    try:
                        self._audio_q.put(("DONE", my_gen), timeout=0.1)
                        break
                    except queue.Full:
                        continue

    def _play_loop(self):
        """Thread phát: lấy audio từ _audio_q → phát liên tục."""
        while True:
            try:
                item = self._audio_q.get(timeout=0.1)
            except queue.Empty:
                continue

            # Sentinel hết file
            if isinstance(item, tuple) and len(item) == 2 and item[0] == "DONE":
                _, item_gen = item
                if item_gen == self._gen and self.on_file_done:
                    self.on_file_done()
                continue

            idx, data, fmt, item_gen = item
            if item_gen != self._gen:
                continue  # task cũ, bỏ qua

            self.cur_idx = idx
            if self.on_chunk_start:
                self.on_chunk_start(idx, "")

            if data:
                self._pause.wait()
                if item_gen == self._gen:
                    self.player.play(data, fmt)

            if item_gen == self._gen and self.on_chunk_done:
                self.on_chunk_done(idx)

    def _synth_with_retry(self, text: str, retries: int = 3) -> Tuple[Optional[bytes], str]:
        """Tổng hợp giọng với retry. Engine: edge_tts | vieneu"""
        engine  = self.cfg.engine
        fmt     = "mp3" if engine == "edge_tts" else "wav"

        # ── VieNeu / Edge ─────────────────────────────────────────────────────
        voice     = self.cfg.edge_voice if engine == "edge_tts" else self.cfg.vieneu_voice
        device    = getattr(self.cfg, "vieneu_device",  "cpu")
        threads   = getattr(self.cfg, "vieneu_threads", 0)
        is_custom = voice.startswith(VieNeuTTSEngine.CUSTOM_PREFIX)

        # Cache (chỉ cho preset voice)
        if self.cfg.use_cache and not is_custom:
            cached = self.cache.get(text, engine, voice, self.cfg.speed, fmt)
            if cached:
                return cached, fmt

        for attempt in range(retries):
            try:
                if engine == "edge_tts":
                    data = self._edge.synth(text, voice, self.cfg.speed)
                else:
                    data = self._vieneu.synth(text, voice, self.cfg.speed,
                                              device, threads)

                if self.cfg.use_cache and data and not is_custom:
                    self.cache.put(text, engine, voice, self.cfg.speed, fmt, data)
                return data, fmt

            except Exception as e:
                print(f"[TTS] lan {attempt+1}: {e}")
                if attempt < retries - 1:
                    time.sleep(1.0)
                else:
                    try:
                        if engine == "edge_tts":
                            data = self._edge.synth(text, self.cfg.edge_voice, self.cfg.speed)
                            return data, "mp3"
                        else:
                            data = self._vieneu.synth(text, self.cfg.vieneu_voice,
                                                      self.cfg.speed, device, threads)
                            return data, "wav"
                    except Exception as e2:
                        print(f"[TTS] Fallback loi: {e2}")
                        if self.on_error:
                            self.on_error(f"Bo qua doan ({str(e)[:40]})")
                        return None, fmt


# ═══════════════════════════════════════════════════════════════════════════════
# LOADING OVERLAY
# ═══════════════════════════════════════════════════════════════════════════════

class LoadingOverlay:
    """
    Overlay mờ che toàn bộ cửa sổ khi đang xử lý lâu.
    Hiển thị thông báo + animation chấm chấm.
    """

    def __init__(self, root: tk.Tk):
        self.root    = root
        self._frame  = None
        self._label  = None
        self._sub    = None
        self._dots   = 0
        self._job    = None
        self._active = False

    def show(self, message: str = "Dang xu ly..."):
        if self._active:
            self.update(message)
            return
        self._active = True
        self._frame  = tk.Frame(self.root, bg="#000000")
        self._frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._frame.lift()

        box = tk.Frame(self._frame, bg=C["card"],
                       highlightbackground=C["accent"], highlightthickness=2)
        box.place(relx=0.5, rely=0.45, anchor="center")

        tk.Label(box, text="⏳", font=("Segoe UI", 28),
                 bg=C["card"], fg=C["accent"]).pack(pady=(20, 4))
        self._label = tk.Label(box, text=message,
                               font=("Segoe UI", 11, "bold"),
                               bg=C["card"], fg=C["text"],
                               wraplength=300, justify="center")
        self._label.pack(padx=30, pady=(0, 8))
        self._sub = tk.Label(box, text="",
                             font=("Segoe UI", 9), bg=C["card"], fg=C["dim"])
        self._sub.pack(padx=30, pady=(0, 20))

        self._animate()
        self.root.update_idletasks()

    def update(self, message: str, sub: str = ""):
        if self._label: self._label.config(text=message)
        if self._sub and sub: self._sub.config(text=sub)
        self.root.update_idletasks()

    def hide(self):
        self._active = False
        if self._job:
            self.root.after_cancel(self._job)
            self._job = None
        if self._frame:
            self._frame.destroy()
            self._frame = self._label = self._sub = None

    def _animate(self):
        if not self._active or not self._sub:
            return
        self._sub.config(text="Vui long cho" + "." * (self._dots % 4))
        self._dots += 1
        self._job = self.root.after(400, self._animate)


# ═══════════════════════════════════════════════════════════════════════════════
# EXPORT RESUME MANAGER
# ═══════════════════════════════════════════════════════════════════════════════

class ExportResumeManager:
    """
    Theo dõi các export bị gián đoạn (mất điện, tắt app).
    Mỗi export lưu một file JSON trong config/export_progress/.
    Khi mở lại app, hiện dialog hỏi người dùng muốn làm gì.
    """

    def __init__(self):
        self.dir = CONFIG_DIR / "export_progress"
        self.dir.mkdir(exist_ok=True)

    def save(self, eid: str, info: dict):
        (self.dir / f"{eid}.json").write_text(
            json.dumps(info, ensure_ascii=False, indent=2), "utf-8")

    def load(self, eid: str) -> Optional[dict]:
        f = self.dir / f"{eid}.json"
        try:
            return json.loads(f.read_text("utf-8")) if f.exists() else None
        except Exception:
            return None

    def delete(self, eid: str):
        f = self.dir / f"{eid}.json"
        if f.exists(): f.unlink()

    def list_all(self) -> List[dict]:
        result = []
        for f in self.dir.glob("*.json"):
            try:
                info = json.loads(f.read_text("utf-8"))
                info["_id"] = f.stem
                result.append(info)
            except Exception:
                pass
        return result

    def cleanup_tmp(self, eid: str):
        """Xóa file tmp và JSON của export này."""
        info = self.load(eid)
        if info:
            tmp = Path(info.get("tmp_path", ""))
            if tmp.exists():
                import shutil
                shutil.rmtree(tmp, ignore_errors=True) if tmp.is_dir() else tmp.unlink(missing_ok=True)
        self.delete(eid)


class StoryExportProgress:
    """
    Theo dõi tiến độ xuất audio cho MỘT bộ truyện.
    File JSON lưu TRONG folder chứa file .txt:
        <story_folder>/export_progress.json

    Schema:
    {
      "chap1":  {"status": "done",    "output": "D:/audio/chap1.wav"},
      "chap2":  {"status": "done",    "output": "D:/audio/chap2.wav"},
      "chap41": {"status": "pending", "output": "D:/audio/chap41.wav"}
    }

    Quy tắc:
    - "pending"    → chưa xử lý
    - "processing" → bị dừng giữa chừng → xử lý lại
    - "done"       → hoàn thành → bỏ qua (trừ khi file output bị xóa)
    """

    STATUS_PENDING    = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_DONE       = "done"
    PROGRESS_FILE     = "export_progress.json"

    def __init__(self, story_folder: str):
        """story_folder: thư mục chứa các file .txt của truyện."""
        self.story_folder = Path(story_folder)
        self.path = self.story_folder / self.PROGRESS_FILE
        self.data: dict = {}
        self._load()

    # ── I/O ───────────────────────────────────────────────────────────────────

    def _load(self):
        try:
            if self.path.exists():
                self.data = json.loads(self.path.read_text("utf-8"))
        except Exception:
            self.data = {}

    def _save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(self.data, ensure_ascii=False, indent=2), "utf-8")
        except Exception as e:
            print(f"[StoryExportProgress] Loi ghi {self.path}: {e}")

    # ── Sync ─────────────────────────────────────────────────────────────────

    def scan_and_sync(self, output_dir: str):
        """
        Scan tất cả file .txt trong story_folder, đồng bộ với progress.
        Gọi hàm này mỗi lần mở dialog hoặc bắt đầu xuất để phát hiện chap mới.
        """
        def _nkey(p: Path):
            return [int(x) if x.isdigit() else x.lower()
                    for x in re.split(r'(\d+)', p.stem)]

        txt_files = sorted(self.story_folder.glob("*.txt"), key=_nkey)
        self._sync_files([str(f) for f in txt_files], output_dir)

    def _sync_files(self, txt_files: List[str], output_dir: str):
        """Đồng bộ danh sách file với progress (nội bộ)."""
        changed = False
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for fp in txt_files:
            stem = Path(fp).stem
            if stem == "export_progress":
                continue
            default_out = str(Path(output_dir) / f"{stem}.wav")

            if stem not in self.data:
                # Chương mới → thêm pending
                self.data[stem] = {
                    "status": self.STATUS_PENDING,
                    "output": default_out,
                    "added":  now,
                }
                changed = True
            else:
                entry = self.data[stem]

                # ── BUG FIX: KHÔNG bao giờ ghi đè "output" khi đã done ────
                # Khi user edit tay JSON đánh done, hay batch N→1 lưu path gộp,
                # scan_and_sync cũ luôn overwrite → check file không có → reset pending.
                if entry["status"] != self.STATUS_DONE:
                    if entry.get("output") != default_out:
                        entry["output"] = default_out
                        changed = True

                # Kiểm tra file audio bị xóa → reset pending
                # CHỈ reset nếu output là path tuyệt đối hợp lệ mà không tồn tại.
                # Nếu output rỗng / path tương đối → user edit tay → GIỮ NGUYÊN done.
                if entry["status"] == self.STATUS_DONE:
                    stored_str = entry.get("output", "")
                    stored     = Path(stored_str) if stored_str else None
                    if stored and stored.is_absolute():
                        audio_exists = stored.exists()
                        if not audio_exists:
                            # Thử đổi ext .wav ↔ .mp3
                            for ext in (".wav", ".mp3"):
                                alt = stored.with_suffix(ext)
                                if alt.exists():
                                    audio_exists = True
                                    entry["output"] = str(alt)
                                    changed = True
                                    break
                        if not audio_exists:
                            entry["status"]  = self.STATUS_PENDING
                            entry["updated"] = now
                            changed = True
                    # Nếu output rỗng hoặc không phải path tuyệt đối:
                    # → user tự edit tay → tin tưởng, GIỮ NGUYÊN done

        if changed:
            self._save()

    def sync_one(self, txt_file: str, output_dir: str):
        """Đồng bộ 1 file duy nhất (khi xuất single/all mode)."""
        self._sync_files([txt_file], output_dir)

    # ── Status ────────────────────────────────────────────────────────────────

    def get_status(self, stem: str) -> str:
        """Trả về trạng thái của chương, mặc định pending nếu chưa có."""
        return self.data.get(stem, {}).get("status", self.STATUS_PENDING)

    def set_status(self, stem: str, status: str, output: str = ""):
        """Cập nhật trạng thái và lưu ngay."""
        if stem not in self.data:
            self.data[stem] = {
                "status": status,
                "output": output,
                "added":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        else:
            self.data[stem]["status"] = status
            if output:
                self.data[stem]["output"] = output
        self.data[stem]["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._save()

    def get_pending(self) -> List[dict]:
        """List chương cần xử lý (pending + processing), sắp xếp tự nhiên."""
        def _nkey(item):
            return [int(x) if x.isdigit() else x.lower()
                    for x in re.split(r'(\d+)', item["stem"])]
        return sorted(
            [{"stem": s, **v} for s, v in self.data.items()
             if v["status"] in (self.STATUS_PENDING, self.STATUS_PROCESSING)],
            key=_nkey)

    def stats(self) -> dict:
        total = len(self.data)
        done  = sum(1 for v in self.data.values() if v["status"] == self.STATUS_DONE)
        proc  = sum(1 for v in self.data.values() if v["status"] == self.STATUS_PROCESSING)
        return {"total": total, "done": done,
                "pending": total - done - proc, "processing": proc}

    @property
    def is_complete(self) -> bool:
        return bool(self.data) and all(
            v["status"] == self.STATUS_DONE for v in self.data.values())


C = {
    "bg":       "#12121e",   # nền tối chính
    "panel":    "#1a1a2e",   # panel/sidebar
    "card":     "#0f3460",   # header, card
    "border":   "#2a2a4a",   # đường viền
    "accent":   "#e94560",   # đỏ hồng – màu chính
    "accent2":  "#533483",   # tím – phụ
    "green":    "#4ade80",   # trạng thái OK
    "yellow":   "#facc15",   # cảnh báo / pending
    "text":     "#e8e8f0",   # chữ chính
    "dim":      "#6060a0",   # chữ mờ
    "edge_clr": "#38bdf8",   # xanh dương – Edge TTS
    "vieu_clr": "#a78bfa",   # tím nhạt – VieNeu TTS
    "log_err":  "#ff6b6b",   # đỏ sáng – lỗi / cảnh báo xấu
}


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN APPLICATION
# ═══════════════════════════════════════════════════════════════════════════════

class VietTTSApp:
    """
    Giao diện chính của ứng dụng (Tkinter).
    Kết nối tất cả các module lại với nhau.
    """

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("📖  Doc Truyen TTS  v2.0")
        self.root.geometry("1060x780")
        self.root.minsize(860, 680)
        self.root.configure(bg=C["bg"])

        # ── Các thành phần chính ────────────────────────────────────────────
        self.mgr        = SettingsManager()
        self.cfg        = self.mgr.settings
        self.player     = AudioPlayer()
        self.worker     = TTSWorker(self.player, self.cfg)
        self.loading    = LoadingOverlay(root)
        self.export_mgr = ExportResumeManager()
        self._kaggle_batch_mgr = None   # KaggleBatchManager (lazy init)

        # Kết nối callback từ worker về UI
        self.worker.on_chunk_start = self._cb_chunk_start
        self.worker.on_file_done   = self._cb_file_done
        self.worker.on_error       = self._cb_error

        # ── Trạng thái ──────────────────────────────────────────────────────
        self.file_list:    List[str] = []
        self.cur_file_idx: int       = -1
        self.chunks:       List[str] = []
        self.is_playing:   bool      = False
        self.is_paused:    bool      = False
        self._chunk_line:  List[str] = []   # vị trí dòng của từng chunk trong Text widget

        self._pending_voice_id:      str  = ""     # giọng chờ Apply
        self._active_export_id:      str  = ""     # export đang chạy
        self._export_stop_flag:      bool = False  # cờ dừng export
        self._hide_loading_after_first: bool = False

        # ── Xây dựng UI ─────────────────────────────────────────────────────
        self._build_styles()
        self._build_ui()
        self.player.set_volume(self.cfg.volume)

        if self.cfg.last_folder and Path(self.cfg.last_folder).is_dir():
            self._load_folder(self.cfg.last_folder)

        self.root.after(1000, self._check_pending_exports)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ═══════════════════════════════════════════════════════════════════════
    # BUILD UI
    # ═══════════════════════════════════════════════════════════════════════

    def _build_styles(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure("Accent.Horizontal.TProgressbar",
                    background=C["accent"], troughcolor=C["border"], bordercolor=C["border"])
        s.configure("TCombobox", fieldbackground=C["panel"], background=C["card"],
                    foreground=C["text"], selectbackground=C["accent2"], arrowcolor=C["dim"])
        s.map("TCombobox",
              fieldbackground=[("readonly", C["panel"])],
              foreground=[("readonly", C["text"])])

    def _build_ui(self):
        self._build_header()
        body = tk.Frame(self.root, bg=C["bg"])
        body.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._build_left_panel(body)
        self._build_right_panel(body)

    # ── Header ───────────────────────────────────────────────────────────────

    def _build_header(self):
        h = tk.Frame(self.root, bg=C["card"], height=56)
        h.pack(fill="x")
        h.pack_propagate(False)
        tk.Label(h, text="📖  Doc Truyen TTS",
                 font=("Segoe UI", 17, "bold"),
                 bg=C["card"], fg=C["accent"]).pack(side="left", padx=18, pady=10)
        self._badge = tk.Label(h, text="", font=("Segoe UI", 9, "bold"), bg=C["card"])
        self._badge.pack(side="right", padx=18)
        self._refresh_badge()

    def _refresh_badge(self):
        """Cập nhật badge engine trên header."""
        if self.cfg.engine == "vieneu":
            self._badge.config(text="🖥️ VieNeu TTS  (offline)", fg=C["vieu_clr"])
        else:
            self._badge.config(text="🌐 Edge TTS  (online)", fg=C["edge_clr"])

    # ── Panel trái: danh sách file ────────────────────────────────────────────

    def _build_left_panel(self, parent):
        lf = tk.Frame(parent, bg=C["panel"], width=275)
        lf.pack(side="left", fill="y", padx=(0, 8), pady=6)
        lf.pack_propagate(False)

        tk.Label(lf, text="📚  Danh Sach Truyen",
                 font=("Segoe UI", 10, "bold"),
                 bg=C["card"], fg=C["text"], pady=7).pack(fill="x")

        bf = tk.Frame(lf, bg=C["panel"])
        bf.pack(fill="x", padx=6, pady=4)
        self._btn(bf, "📂 Folder", self._open_folder, C["accent2"]).pack(
            side="left", fill="x", expand=True, padx=(0, 3))
        self._btn(bf, "📄 File",   self._open_file,   C["card"]).pack(
            side="left", fill="x", expand=True)

        # Listbox file
        lbox_f = tk.Frame(lf, bg=C["panel"])
        lbox_f.pack(fill="both", expand=True, padx=6, pady=4)
        sb = tk.Scrollbar(lbox_f, bg=C["panel"], troughcolor=C["bg"], relief="flat", width=10)
        sb.pack(side="right", fill="y")
        self.listbox = tk.Listbox(
            lbox_f, bg=C["bg"], fg=C["text"],
            selectbackground=C["accent"], selectforeground="white",
            font=("Segoe UI", 10), borderwidth=0,
            highlightthickness=0, activestyle="none",
            yscrollcommand=sb.set)
        self.listbox.pack(fill="both", expand=True)
        sb.config(command=self.listbox.yview)
        self.listbox.bind("<Double-Button-1>", self._on_list_dbl)
        self.listbox.bind("<Return>", self._on_list_dbl)

        self.folder_lbl = tk.Label(lf, text="Chua chon folder",
                                   font=("Segoe UI", 8), bg=C["panel"],
                                   fg=C["dim"], wraplength=240, justify="left")
        self.folder_lbl.pack(padx=8, pady=(0, 6))

    # ── Panel phải: nội dung + điều khiển ────────────────────────────────────

    def _build_right_panel(self, parent):
        rf = tk.Frame(parent, bg=C["bg"])
        rf.pack(side="left", fill="both", expand=True, pady=6)
        self._build_content_area(rf)
        self._build_controls(rf)
        self._build_engine_voice_panel(rf)
        self._build_settings_bar(rf)

    def _build_content_area(self, parent):
        """Vùng hiển thị text đang đọc + progress bar."""
        cf = tk.Frame(parent, bg=C["panel"])
        cf.pack(fill="both", expand=True, pady=(0, 6))

        self.title_lbl = tk.Label(cf, text="Chon file de bat dau...",
                                  font=("Segoe UI", 13, "bold"),
                                  bg=C["panel"], fg=C["accent"])
        self.title_lbl.pack(pady=(10, 4))

        tf = tk.Frame(cf, bg=C["bg"])
        tf.pack(fill="both", expand=True, padx=10, pady=4)
        sb = tk.Scrollbar(tf)
        sb.pack(side="right", fill="y")
        self.txt = tk.Text(
            tf, bg=C["bg"], fg=C["text"],
            font=("Segoe UI", 12), wrap="word",
            borderwidth=0, highlightthickness=0,
            state="disabled", yscrollcommand=sb.set,
            padx=12, pady=8)
        self.txt.pack(fill="both", expand=True)
        sb.config(command=self.txt.yview)
        # Tag: chunk đang đọc (đỏ) và đã đọc (mờ)
        self.txt.tag_configure("cur",  background=C["accent"], foreground="white")
        self.txt.tag_configure("done", foreground=C["dim"])

        info = tk.Frame(cf, bg=C["panel"])
        info.pack(fill="x", padx=10, pady=4)
        self.prog_lbl = tk.Label(info, text="0 / 0 doan",
                                 font=("Segoe UI", 9), bg=C["panel"], fg=C["dim"])
        self.prog_lbl.pack(side="left")
        self.status_lbl = tk.Label(info, text="",
                                   font=("Segoe UI", 9), bg=C["panel"], fg=C["yellow"])
        self.status_lbl.pack(side="right")

        self.prog_var = tk.DoubleVar()
        ttk.Progressbar(cf, variable=self.prog_var,
                        style="Accent.Horizontal.TProgressbar",
                        maximum=100).pack(fill="x", padx=10, pady=(2, 10))

    def _build_controls(self, parent):
        """Hàng nút điều khiển phát: ⏮ ⏪ ▶ ⏩ ⏭ ⏹ ↩  +  💾 ⏹(xuất) bên phải"""
        cf = tk.Frame(parent, bg=C["card"])
        cf.pack(fill="x", pady=(0, 6))

        # Pack nút xuất bên PHẢI trước
        self._btn(cf, "💾 Xuat", self._export_audio,
                  C["accent2"]).pack(side="right", padx=(0, 10), pady=10)
        self._btn(cf, "📦 Xuat lo", self._show_batch_export_dialog,
                  C["accent2"]).pack(side="right", padx=(0, 4), pady=10)
        self._btn(cf, "☁ Kaggle Batch", self._open_kaggle_batch_dialog,
                  C["card"]).pack(side="right", padx=(0, 4), pady=10)
        self._stop_export_btn = tk.Button(cf, text="⏹ Dung xuat",
                                          command=self._stop_export,
                                          bg=C["border"], fg="white",
                                          activebackground=C["accent"],
                                          activeforeground="white",
                                          relief="flat", cursor="hand2",
                                          font=("Segoe UI", 9), padx=8, pady=4,
                                          state="disabled")
        self._stop_export_btn.pack(side="right", padx=(0, 4), pady=10)
        # Nút tiếp tục xuất (chỉ hiện khi đang có export bị tạm dừng)
        self._resume_export_btn = tk.Button(cf, text="▶ Tiep tuc xuat",
                                            command=self._resume_paused_export,
                                            bg=C["accent2"], fg="white",
                                            activebackground=C["card"],
                                            activeforeground="white",
                                            relief="flat", cursor="hand2",
                                            font=("Segoe UI", 9), padx=8, pady=4,
                                            state="disabled")
        self._resume_export_btn.pack(side="right", padx=(0, 4), pady=10)

        # Nút phát ở giữa
        row = tk.Frame(cf, bg=C["card"])
        row.pack(side="left", expand=True, pady=10)

        buttons = [
            ("⏮",  self._prev_file,       38, C["panel"]),
            ("⏪",  self._read_from_start,  38, C["panel"]),
            ("▶",  self._play_pause,      58, C["accent"]),
            ("⏩",  self._skip_fwd,       38, C["panel"]),
            ("⏭",  self._next_file,      38, C["panel"]),
            ("⏹",  self._stop,           38, C["panel"]),
            ("↩",  self._read_from_start, 38, C["accent2"]),
        ]
        self._play_btn = None
        for txt, cmd, w, bg in buttons:
            b = tk.Button(row, text=txt, command=cmd,
                          font=("Segoe UI", 14 if w > 40 else 11),
                          bg=bg, fg="white",
                          activebackground=C["accent2"], activeforeground="white",
                          relief="flat", cursor="hand2",
                          width=w // 10, pady=4)
            b.pack(side="left", padx=5)
            if txt == "▶": self._play_btn = b

    def _build_engine_voice_panel(self, parent):
        """Panel chọn Engine (Edge/VieNeu), Device (CPU/GPU) và Giọng đọc."""
        outer = tk.Frame(parent, bg=C["border"])
        outer.pack(fill="x", pady=(0, 6))
        inner = tk.Frame(outer, bg=C["panel"])
        inner.pack(fill="x", padx=1, pady=1)

        tk.Label(inner, text="🔊  Engine & Giong Doc",
                 font=("Segoe UI", 10, "bold"),
                 bg=C["panel"], fg=C["text"]).pack(anchor="w", padx=12, pady=(4, 2))

        # Row 1: Engine radio + Device radio
        r1 = tk.Frame(inner, bg=C["panel"])
        r1.pack(fill="x", padx=12, pady=(0, 4))

        tk.Label(r1, text="Engine:", font=("Segoe UI", 9),
                 bg=C["panel"], fg=C["dim"]).pack(side="left")

        self._engine_var = tk.StringVar(value=self.cfg.engine)
        for label, val, color in [
            ("🌐 Edge TTS  (online ⭐)", "edge_tts", C["edge_clr"]),
            ("🖥️ VieNeu TTS (offline)", "vieneu",   C["vieu_clr"]),
        ]:
            tk.Radiobutton(r1, text=label, variable=self._engine_var, value=val,
                           command=lambda v=val: self._on_engine_change(v),
                           font=("Segoe UI", 9), bg=C["panel"], fg=color,
                           selectcolor=C["bg"], activebackground=C["panel"],
                           activeforeground=color).pack(side="left", padx=(12, 0))

        # CPU/GPU selector (chỉ hiện khi chọn VieNeu)
        self._device_frame = tk.Frame(r1, bg=C["panel"])
        self._device_frame.pack(side="left", padx=(20, 0))
        tk.Label(self._device_frame, text="|  Chay bang:",
                 font=("Segoe UI", 9), bg=C["panel"], fg=C["dim"]).pack(side="left", padx=(0, 4))
        self._device_var = tk.StringVar(value=self.cfg.vieneu_device)
        for label, val, color in [("💻 CPU", "cpu", C["text"]), ("🚀 GPU (CUDA)", "gpu", C["green"])]:
            tk.Radiobutton(self._device_frame, text=label,
                           variable=self._device_var, value=val,
                           command=lambda v=val: self._on_device_change(v),
                           font=("Segoe UI", 9), bg=C["panel"], fg=color,
                           selectcolor=C["bg"], activebackground=C["panel"],
                           activeforeground=color).pack(side="left", padx=(0, 4))
        # GPU status label nằm ngay cạnh nút GPU
        self._gpu_lbl = tk.Label(self._device_frame, text="",
                                 font=("Segoe UI", 8), bg=C["panel"], fg=C["vieu_clr"])
        self._gpu_lbl.pack(side="left", padx=(2, 0))
        self._check_gpu_support()

        if self.cfg.engine != "vieneu":
            self._device_frame.pack_forget()


        # Row 2: Giọng đọc dropdown + Apply + Reload + Quản lý
        r2 = tk.Frame(inner, bg=C["panel"])
        r2.pack(fill="x", padx=12, pady=(0, 2))

        tk.Label(r2, text="Giong doc:", font=("Segoe UI", 9),
                 bg=C["panel"], fg=C["dim"]).pack(side="left")
        self._voice_ids:    List[str] = []
        self._voice_var = tk.StringVar()
        self._voice_combo = ttk.Combobox(r2, textvariable=self._voice_var,
                                         state="readonly", width=48, font=("Segoe UI", 9))
        self._voice_combo.pack(side="left", padx=(8, 8))
        # Combo chỉ ghi nhận lựa chọn, KHÔNG tự áp dụng ngay
        self._voice_combo.bind("<<ComboboxSelected>>", self._on_voice_select)

        self._apply_btn = tk.Button(r2, text="✅ Ap dung giong",
                                    command=self._apply_voice_now,
                                    bg=C["accent"], fg="white",
                                    activebackground=C["accent2"], activeforeground="white",
                                    relief="flat", cursor="hand2",
                                    font=("Segoe UI", 9), padx=10, pady=4)
        self._apply_btn.pack(side="left", padx=(0, 4))
        self._btn(r2, "🔄 Reload",        self._reload_voices,      C["card"]   ).pack(side="left", padx=(0, 4))
        self._btn(r2, "🎤 Quan ly giong", self._open_voice_manager, C["accent2"]).pack(side="left", padx=(0, 4))
        self._btn(r2, "📂 Mo voices/",    self._open_voices_folder, C["border"] ).pack(side="left")

        # Row 3: Gợi ý clone giọng (hint text)
        r3 = tk.Frame(inner, bg=C["panel"])
        r3.pack(fill="x", padx=12, pady=(0, 2))
        self._clone_hint = tk.Label(
            r3,
            text="🎤  Clone giong: bo file .wav + .txt vao ./voices/ roi bam Reload",
            font=("Segoe UI", 8), bg=C["panel"], fg=C["vieu_clr"], justify="left")
        self._clone_hint.pack(side="left")

        # Hint cài đặt VieNeu (ẩn/hiện theo engine)
        self._vieneu_hint = tk.Label(
            inner,
            text=("ℹ️  VieNeu TTS can cai them: chay install_vieneu.bat\n"
                  "    Model ~1.2 GB se tu download lan dau vao ./models/"),
            font=("Segoe UI", 8), bg=C["panel"], fg=C["yellow"], justify="left")

        self._refresh_voice_list()

    def _build_settings_bar(self, parent):
        """Thanh cài đặt: tốc độ, âm lượng, chunk, cache — 1 row gọn."""
        sf = tk.Frame(parent, bg=C["panel"])
        sf.pack(fill="x")

        row = tk.Frame(sf, bg=C["panel"])
        row.pack(fill="x", padx=10, pady=2)

        # Auto-next (bên phải)
        self._autonext_var = tk.BooleanVar(value=self.cfg.auto_next)
        tk.Checkbutton(row, text="Tu chuyen",
                       variable=self._autonext_var, bg=C["panel"], fg=C["text"],
                       selectcolor=C["bg"], activebackground=C["panel"],
                       font=("Segoe UI", 9),
                       command=lambda: setattr(self.cfg, "auto_next",
                                               self._autonext_var.get())
                       ).pack(side="right", padx=(0, 4))

        # Cache (bên phải)
        self._cache_var = tk.BooleanVar(value=self.cfg.use_cache)
        tk.Checkbutton(row, text="Cache",
                       variable=self._cache_var, bg=C["panel"], fg=C["green"],
                       selectcolor=C["bg"], activebackground=C["panel"],
                       font=("Segoe UI", 9), command=self._on_cache_toggle
                       ).pack(side="right", padx=(0, 2))
        self._cache_info = tk.Label(row, text="",
                                    font=("Segoe UI", 8), bg=C["panel"], fg=C["dim"])
        self._cache_info.pack(side="right", padx=(0, 2))
        self._btn(row, "🗑", self._clear_cache, C["border"]).pack(side="right", padx=(0, 6))

        # Chunk size
        tk.Label(row, text="📦", font=("Segoe UI", 9),
                 bg=C["panel"], fg=C["text"]).pack(side="left")
        self._chunk_var = tk.IntVar(value=self.cfg.chunk_size)
        tk.Spinbox(row, from_=80, to=400, increment=20,
                   textvariable=self._chunk_var, width=4,
                   font=("Segoe UI", 9), bg=C["bg"], fg=C["text"],
                   buttonbackground=C["card"], highlightthickness=0, relief="flat",
                   command=lambda: setattr(self.cfg, "chunk_size",
                                           self._chunk_var.get())
                   ).pack(side="left", padx=(2, 10))

        # Export workers (số luồng song song khi xuất - Edge TTS)
        tk.Label(row, text="🚀", font=("Segoe UI", 9),
                 bg=C["panel"], fg=C["text"]).pack(side="left")
        self._workers_var = tk.IntVar(value=self.cfg.export_workers)
        tk.Spinbox(row, from_=1, to=16, increment=1,
                   textvariable=self._workers_var, width=3,
                   font=("Segoe UI", 9), bg=C["bg"], fg=C["green"],
                   buttonbackground=C["card"], highlightthickness=0, relief="flat",
                   command=lambda: setattr(self.cfg, "export_workers",
                                           self._workers_var.get())
                   ).pack(side="left", padx=(2, 10))

        # VieNeu CPU threads
        tk.Label(row, text="🧵", font=("Segoe UI", 9),
                 bg=C["panel"], fg=C["text"]).pack(side="left")
        _auto_cores = os.cpu_count() or 4
        self._threads_var = tk.IntVar(
            value=self.cfg.vieneu_threads if self.cfg.vieneu_threads > 0
                  else _auto_cores)
        tk.Spinbox(row, from_=1, to=_auto_cores, increment=1,
                   textvariable=self._threads_var, width=3,
                   font=("Segoe UI", 9), bg=C["bg"], fg=C["yellow"],
                   buttonbackground=C["card"], highlightthickness=0, relief="flat",
                   command=lambda: (setattr(self.cfg, "vieneu_threads",
                                            self._threads_var.get()),
                                    self.worker._vieneu.reset_cache())
                   ).pack(side="left", padx=(2, 10))

        # Tốc độ
        tk.Label(row, text="🐢", font=("Segoe UI", 9),
                 bg=C["panel"], fg=C["text"]).pack(side="left")
        self._speed_var = tk.DoubleVar(value=self.cfg.speed)
        tk.Scale(row, variable=self._speed_var, from_=0.5, to=2.0,
                 resolution=0.1, orient="horizontal",
                 bg=C["panel"], fg=C["text"],
                 troughcolor=C["border"], highlightthickness=0,
                 length=90, showvalue=True, font=("Segoe UI", 8),
                 command=lambda v: setattr(self.cfg, "speed", float(v))
                 ).pack(side="left", padx=(2, 2))
        self._btn(row, "▶", self._apply_speed, C["card"]).pack(side="left", padx=(0, 10))

        # Âm lượng
        tk.Label(row, text="🔊", font=("Segoe UI", 9),
                 bg=C["panel"], fg=C["text"]).pack(side="left")
        self._vol_var = tk.DoubleVar(value=self.cfg.volume)
        tk.Scale(row, variable=self._vol_var, from_=0.0, to=1.0,
                 resolution=0.05, orient="horizontal",
                 bg=C["panel"], fg=C["text"],
                 troughcolor=C["border"], highlightthickness=0,
                 length=90, showvalue=True, font=("Segoe UI", 8),
                 command=lambda v: (setattr(self.cfg, "volume", float(v)),
                                    self.player.set_volume(float(v)))
                 ).pack(side="left", padx=(2, 0))

        self._update_cache_info()

    # ═══════════════════════════════════════════════════════════════════════
    # VOICE MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════════

    def _refresh_voice_list(self):
        """Đổ danh sách giọng vào combo theo engine hiện tại."""
        pairs = self.worker.get_voice_list()
        self._voice_labels = [p[0] for p in pairs]
        self._voice_ids    = [p[1] for p in pairs]
        self._voice_combo["values"] = self._voice_labels

        saved = (self.cfg.edge_voice  if self.cfg.engine == "edge_tts"
                 else self.cfg.vieneu_voice)
        idx = self._voice_ids.index(saved) if saved in self._voice_ids else 0
        if self._voice_labels:
            self._voice_combo.current(idx)
            self._voice_var.set(self._voice_labels[idx])
            if self._voice_ids:
                self._apply_voice(self._voice_ids[idx])

        # Hiện/ẩn hint theo engine
        if self.cfg.engine == "vieneu":
            self._vieneu_hint.pack(anchor="w", padx=12, pady=(0, 8))
            self._clone_hint.pack(side="left")
        else:
            self._vieneu_hint.pack_forget()
            self._clone_hint.pack_forget()

    def _reload_voices(self):
        """Reload danh sách giọng trong background thread."""
        def _bg():
            if self.cfg.engine == "vieneu":
                self.worker.reload_vieneu_voices()
            self.root.after(0, self._refresh_voice_list)
            self.root.after(0, self.loading.hide)
        threading.Thread(target=_bg, daemon=True).start()

    def _on_voice_select(self, _=None):
        """Người dùng chọn giọng → lưu pending, đổi màu nút Apply."""
        idx = self._voice_combo.current()
        if 0 <= idx < len(self._voice_ids):
            self._pending_voice_id = self._voice_ids[idx]
            self._apply_btn.config(bg=C["yellow"], fg=C["bg"])

    def _apply_voice_now(self):
        """Áp dụng giọng mới ngay: dừng → đổi giọng → tiếp tục đọc."""
        vid = self._pending_voice_id or (
            self._voice_ids[self._voice_combo.current()]
            if self._voice_combo.current() >= 0 else "")
        if not vid: return

        cur_chunk   = self.worker.cur_idx
        was_playing = self.is_playing and not self.is_paused

        self.worker.stop()
        self.is_playing = self.is_paused = False
        self._update_play_btn()
        self._apply_voice(vid)
        self._pending_voice_id = ""
        self._apply_btn.config(bg=C["accent"], fg="white")
        self.worker.cache.clear()
        self._update_cache_info()

        if was_playing and self.chunks:
            self.loading.show("Dang ap dung giong moi...")
            self._hide_loading_after_first = True
            self.root.after(200, lambda: self._start_reading(cur_chunk))

    def _apply_voice(self, vid: str):
        """Lưu voice_id vào cfg theo engine đang chọn."""
        if self.cfg.engine == "edge_tts":
            self.cfg.edge_voice = vid
        else:
            self.cfg.vieneu_voice = vid

    def _open_voices_folder(self):
        import subprocess
        subprocess.Popen(f'explorer "{VOICES_DIR}"')

    def _open_voice_manager(self):
        """Dialog quản lý giọng clone: đặt tên, xóa."""
        dlg = tk.Toplevel(self.root)
        dlg.title("Quan ly Giong Clone")
        dlg.geometry("520x400")
        dlg.resizable(False, True)
        dlg.configure(bg=C["panel"])
        dlg.grab_set()
        dlg.transient(self.root)
        x = self.root.winfo_x() + (self.root.winfo_width()  - 520) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 400) // 2
        dlg.geometry(f"+{x}+{y}")

        tk.Label(dlg, text="🎤  Quan Ly Giong Clone",
                 font=("Segoe UI", 13, "bold"),
                 bg=C["panel"], fg=C["vieu_clr"]).pack(pady=(14, 4))
        tk.Label(dlg, text="Dat ten hien thi de de phan biet khi dung nhieu giong.",
                 font=("Segoe UI", 8), bg=C["panel"], fg=C["dim"]).pack()

        # Header bảng
        hdr = tk.Frame(dlg, bg=C["card"])
        hdr.pack(fill="x", padx=14, pady=(8, 0))
        for txt, w in [("Ten file", 18), ("Ten hien thi", 22), ("", 8)]:
            tk.Label(hdr, text=txt, font=("Segoe UI", 8, "bold"),
                     bg=C["card"], fg=C["dim"], width=w, anchor="w"
                     ).pack(side="left", padx=4, pady=3)

        # Scrollable rows
        canvas   = tk.Canvas(dlg, bg=C["panel"], highlightthickness=0)
        sb       = tk.Scrollbar(dlg, orient="vertical", command=canvas.yview)
        rows_f   = tk.Frame(canvas, bg=C["panel"])
        rows_f.bind("<Configure>",
                    lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=rows_f, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True, padx=14)
        sb.pack(side="right", fill="y")

        engine     = self.worker._vieneu
        entry_vars: List[Tuple[str, tk.StringVar]] = []

        def _build_rows():
            for w in rows_f.winfo_children(): w.destroy()
            entry_vars.clear()
            vlist = engine.get_custom_voice_info()
            if not vlist:
                tk.Label(rows_f,
                         text="Chua co giong nao.\nBam 'Mo voices/' de them file WAV+TXT.",
                         font=("Segoe UI", 9), bg=C["panel"], fg=C["dim"],
                         justify="center").pack(pady=20)
                return
            for info in vlist:
                row = tk.Frame(rows_f, bg=C["bg"])
                row.pack(fill="x", pady=1)
                tk.Label(row, text=info["stem"], font=("Segoe UI", 9),
                         bg=C["bg"], fg=C["dim"], width=18, anchor="w"
                         ).pack(side="left", padx=(6, 2), pady=4)
                var = tk.StringVar(value=info["display"])
                entry_vars.append((info["stem"], var))
                tk.Entry(row, textvariable=var, font=("Segoe UI", 9),
                         bg=C["panel"], fg=C["text"], insertbackground=C["text"],
                         relief="flat", width=22).pack(side="left", padx=4)
                stem = info["stem"]
                tk.Button(row, text="🗑", font=("Segoe UI", 9),
                          bg=C["accent"], fg="white", relief="flat", cursor="hand2", padx=6,
                          command=lambda s=stem: _delete(s)).pack(side="left", padx=4)

        def _delete(stem: str):
            if messagebox.askyesno("Xoa giong",
                    f"Xoa giong '{stem}'?\nFile WAV, TXT va LABEL se bi xoa.", parent=dlg):
                engine.delete_custom_voice(stem)
                _build_rows()
                self._reload_voices()

        def _save_all():
            for stem, var in entry_vars:
                if var.get().strip():
                    engine.rename_custom_voice(stem, var.get().strip())
            self._reload_voices()
            messagebox.showinfo("Da luu", "Ten hien thi da cap nhat.", parent=dlg)

        _build_rows()

        btn_row = tk.Frame(dlg, bg=C["panel"])
        btn_row.pack(pady=10)
        self._btn(btn_row, "💾 Luu ten",     _save_all,                        C["accent"]).pack(side="left", padx=6)
        self._btn(btn_row, "📂 Mo voices/",  self._open_voices_folder,         C["card"]  ).pack(side="left", padx=6)
        self._btn(btn_row, "🔄 Lam moi",     lambda: (_build_rows(), self._reload_voices()), C["card"]).pack(side="left", padx=6)
        self._btn(btn_row, "Dong",           dlg.destroy,                      C["border"]).pack(side="left", padx=6)

    # ═══════════════════════════════════════════════════════════════════════
    # ENGINE / DEVICE / SPEED HANDLERS
    # ═══════════════════════════════════════════════════════════════════════

    def _on_engine_change(self, val: str):
        self.cfg.engine = val
        self._refresh_badge()

        # Ẩn device frame trước
        self._device_frame.pack_forget()

        if val == "vieneu":
            self._device_frame.pack(side="left", padx=(20, 0))
            self.loading.show("Dang load VieNeu TTS...")

        self._reload_voices()

    def _on_device_change(self, val: str):
        """Đổi CPU/GPU: reset model cũ, reload với device mới."""
        if self.cfg.vieneu_device == val: return
        self.cfg.vieneu_device = val
        self.worker._vieneu._ready = False
        self.worker._vieneu._voice_cache.clear()
        self.worker._vieneu._preset_cache.clear()

        if self.cfg.engine == "vieneu":
            device_name = "GPU (CUDA)" if val == "gpu" else "CPU"
            self.loading.show(f"Dang tai lai VieNeu tren {device_name}...")
            self.worker.stop()
            self.is_playing = self.is_paused = False
            self._update_play_btn()
            def _reload():
                self.worker._vieneu.get_voice_list(val)
                self.root.after(0, self._refresh_voice_list)
                self.root.after(0, self.loading.hide)
            threading.Thread(target=_reload, daemon=True).start()

    def _apply_speed(self):
        """Áp dụng tốc độ mới ngay: dừng → set speed → tiếp tục."""
        self.cfg.speed = self._speed_var.get()
        if not self.is_playing or not self.chunks: return
        cur, was = self.worker.cur_idx, not self.is_paused
        self.worker.stop()
        self.is_playing = self.is_paused = False
        if was:
            self.loading.show(f"Ap dung toc do {self.cfg.speed}x...")
            self.root.after(200, lambda: self._start_reading(cur))
            self.root.after(1000, self.loading.hide)

    def _check_gpu_support(self):
        """Kiểm tra CUDA ở background, hiện badge kết quả."""
        def _bg():
            try:
                import subprocess
                ok = subprocess.run(["nvidia-smi"], capture_output=True, timeout=3).returncode == 0
                txt = "🚀 CUDA san sang – VieNeu co the dung GPU" if ok else "⚠ Dang dung CPU"
                clr = C["green"] if ok else C["yellow"]
                self.root.after(0, lambda: self._gpu_lbl.config(text=txt, fg=clr))
            except Exception:
                pass
        threading.Thread(target=_bg, daemon=True).start()

    # ═══════════════════════════════════════════════════════════════════════
    # CACHE
    # ═══════════════════════════════════════════════════════════════════════

    def _on_cache_toggle(self):
        self.cfg.use_cache = self._cache_var.get()
        self._update_cache_info()

    def _update_cache_info(self):
        mb, cnt = self.worker.cache.size_mb(), self.worker.cache.count()
        self._cache_info.config(text=f"({cnt} file, {mb:.1f}MB)")

    def _clear_cache(self):
        if messagebox.askyesno("Xoa cache", "Xoa toan bo cache audio?\nLan sau phai tong hop lai."):
            self.worker.cache.clear()
            self._update_cache_info()

    # ═══════════════════════════════════════════════════════════════════════
    # FILE OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════

    def _open_folder(self):
        folder = filedialog.askdirectory(title="Chon folder truyen")
        if folder: self._load_folder(folder)

    def _open_file(self):
        fp = filedialog.askopenfilename(title="Chon file .txt",
                                        filetypes=[("Text", "*.txt"), ("All", "*.*")])
        if fp:
            self.file_list = [fp]
            self.listbox.delete(0, "end")
            self.listbox.insert(0, Path(fp).name)
            self._load_play_file(0)

    def _load_folder(self, folder: str):
        """Load danh sách file .txt theo natural sort (chap1 < chap2 < chap10)."""
        self.cfg.last_folder = folder

        def natural_key(p: Path):
            parts = re.split(r'(\d+)', p.stem.lower())
            return [int(x) if x.isdigit() else x for x in parts]

        files = sorted(Path(folder).glob("*.txt"), key=natural_key)
        self.file_list = [str(f) for f in files]
        self.listbox.delete(0, "end")
        for f in files:
            self.listbox.insert("end", f.name)
        short = folder if len(folder) < 48 else "…" + folder[-45:]
        self.folder_lbl.config(text=f"{short}\n{len(files)} file .txt")
        self.mgr.save()

    def _load_play_file(self, idx: int, start_chunk: int = None):
        """
        Load file vào bộ nhớ.
        - start_chunk=None : chọn thủ công → hiển thị, chờ Play
        - start_chunk=int  : auto-next/prev   → tự đọc ngay
        """
        if not self.file_list or idx >= len(self.file_list): return
        self.cur_file_idx = idx
        fp = self.file_list[idx]

        try:
            self.chunks = TextProcessor.split_chunks(
                TextProcessor.clean(TextProcessor.load(fp)), self.cfg.chunk_size)
        except Exception as e:
            messagebox.showerror("Loi doc file", str(e))
            return

        self.title_lbl.config(text=f"📖  {Path(fp).name}")
        self._chunk_line = []
        self._render_text(-1)
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(idx)
        self.listbox.see(idx)

        sc = start_chunk if start_chunk is not None else self.mgr.get_position(fp)

        if start_chunk is not None:
            self._start_reading(sc)
        else:
            # Chờ người dùng bấm Play
            self.worker.stop()
            self.is_playing = self.is_paused = False
            self.worker.cur_idx = sc
            self.prog_var.set(sc / len(self.chunks) * 100 if self.chunks else 0)
            if sc > 0:
                self._highlight_chunk(sc, scroll=True)
                self.prog_lbl.config(text=f"San sang – tiep tuc tu doan {sc+1}")
            else:
                self.prog_lbl.config(text="San sang – bam Play de bat dau")
            self._update_play_btn()

    def _start_reading(self, start: int = 0):
        if not self.chunks: return
        self.is_playing = True
        self.is_paused  = False
        self._update_play_btn()
        self.worker.speak(self.chunks, start)

    # ═══════════════════════════════════════════════════════════════════════
    # CONTROLS
    # ═══════════════════════════════════════════════════════════════════════

    def _play_pause(self):
        if not self.chunks:
            self._open_folder(); return
        if not self.is_playing:
            self._start_reading(self.worker.cur_idx)
        elif self.is_paused:
            self.is_paused = False
            self.worker.resume()
        else:
            self.is_paused = True
            self.worker.pause()
        self._update_play_btn()

    def _stop(self):
        self.is_playing = self.is_paused = False
        self.worker.stop()
        self._update_play_btn()
        self.prog_var.set(0)
        self.prog_lbl.config(text="Da dung")

    def _read_from_start(self):
        """Đọc lại từ đầu file (nút ⏪ và nút ↩)."""
        if not self.chunks: return
        self.is_playing = self.is_paused = False
        self.worker.stop()
        self._update_play_btn()
        self.prog_var.set(0)
        self.root.after(150, lambda: self._start_reading(0))

    def _next_file(self):
        next_idx = self.cur_file_idx + 1
        if next_idx < len(self.file_list):
            self.worker.stop()
            self.root.after(100, lambda i=next_idx: self._load_play_file(i, 0))

    def _prev_file(self):
        prev_idx = self.cur_file_idx - 1
        if prev_idx >= 0:
            self.worker.stop()
            self.root.after(100, lambda i=prev_idx: self._load_play_file(i, 0))

    def _skip_fwd(self):
        if self.chunks:
            new = min(self.worker.cur_idx + 5, len(self.chunks) - 1)
            self.worker.stop()
            self.root.after(150, lambda: self._start_reading(new))

    def _update_play_btn(self):
        if not self._play_btn: return
        if self.is_paused:
            self._play_btn.config(text="▶", bg=C["yellow"])
        elif self.is_playing:
            self._play_btn.config(text="⏸", bg=C["accent"])
        else:
            self._play_btn.config(text="▶", bg=C["accent"])

    # ═══════════════════════════════════════════════════════════════════════
    # WORKER CALLBACKS  (gọi từ background thread → dùng root.after)
    # ═══════════════════════════════════════════════════════════════════════

    def _cb_chunk_start(self, idx: int, _txt: str):
        self.root.after(0, self._update_progress, idx)
        if self.file_list and self.cur_file_idx >= 0:
            self.mgr.save_position(self.file_list[self.cur_file_idx], idx)
        # Ẩn loading sau chunk đầu tiên (sau khi đổi giọng/tốc độ)
        if self._hide_loading_after_first:
            self._hide_loading_after_first = False
            self.root.after(300, self.loading.hide)

    def _cb_file_done(self):
        """Worker callback: file đọc xong → cập nhật UI, tự chuyển file nếu bật."""
        def _ui():
            self.is_playing = False
            self.prog_var.set(100)
            self.prog_lbl.config(text="✅ Da doc xong")
            self._update_play_btn()
            if self.cfg.auto_next:
                next_idx = self.cur_file_idx + 1
                if next_idx < len(self.file_list):
                    # Capture next_idx ngay để tránh race condition
                    self.root.after(1000, lambda i=next_idx: self._load_play_file(i, 0))
        self.root.after(0, _ui)

    def _cb_error(self, msg: str):
        self.root.after(0, lambda: self.status_lbl.config(text=f"⚠ {msg[:60]}"))

    # ═══════════════════════════════════════════════════════════════════════
    # TEXT DISPLAY
    # ═══════════════════════════════════════════════════════════════════════

    def _render_text(self, cur: int = -1):
        """
        Render toàn bộ text vào widget (gọi 1 lần khi load file).
        Lưu vị trí dòng của từng chunk vào _chunk_line[] để scroll chính xác.
        """
        self.txt.config(state="normal")
        self.txt.delete("1.0", "end")
        if not self.chunks:
            self.txt.config(state="disabled")
            return

        self._chunk_line = []
        for i, c in enumerate(self.chunks):
            self._chunk_line.append(self.txt.index("end-1c linestart"))
            tag = "done" if i < cur else ""
            self.txt.insert("end", c + "\n\n", tag)
        self.txt.config(state="disabled")

        if cur >= 0:
            self._highlight_chunk(cur, scroll=False)

    def _highlight_chunk(self, idx: int, scroll: bool = True):
        """
        Chỉ cập nhật tag highlight — không rebuild text.
        Scroll chỉ khi chunk xuống quá 55% chiều cao màn hình.
        """
        if not self.chunks or idx < 0 or idx >= len(self.chunks): return
        self.txt.config(state="normal")
        self.txt.tag_remove("cur", "1.0", "end")

        if idx > 0 and idx < len(self._chunk_line):
            prev = self._chunk_line[idx - 1]
            self.txt.tag_add("done", prev, f"{prev} + {len(self.chunks[idx-1])}c")

        if idx < len(self._chunk_line):
            line = self._chunk_line[idx]
            self.txt.tag_add("cur", line, f"{line} + {len(self.chunks[idx])}c")
            if scroll:
                self.txt.see(line)
                self.txt.update_idletasks()
                try:
                    bbox = self.txt.bbox(line)
                    if bbox and bbox[1] > self.txt.winfo_height() * 0.55:
                        self.txt.see(line)
                except Exception:
                    pass
        self.txt.config(state="disabled")

    def _update_progress(self, idx: int):
        """Cập nhật progress bar + label + highlight chunk."""
        n = len(self.chunks)
        if n:
            self.prog_var.set(idx / n * 100)
            self.prog_lbl.config(text=f"{idx+1} / {n} doan  ({idx/n*100:.0f}%)")
        self._highlight_chunk(idx, scroll=True)

    # ═══════════════════════════════════════════════════════════════════════
    # EXPORT AUDIO
    # ═══════════════════════════════════════════════════════════════════════

    def _export_audio(self):
        if not self.file_list:
            messagebox.showwarning("Chua co noi dung", "Hay mo file truyen truoc.")
            return
        self._show_export_dialog()

    def _show_export_dialog(self):
        """Dialog chọn chế độ xuất: đơn / theo nhóm / toàn bộ."""
        dlg = tk.Toplevel(self.root)
        dlg.title("Xuat Audio")
        dlg.geometry("480x450")
        dlg.resizable(False, False)
        dlg.configure(bg=C["panel"])
        dlg.grab_set()
        dlg.transient(self.root)
        x = self.root.winfo_x() + (self.root.winfo_width()  - 480) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 450) // 2
        dlg.geometry(f"+{x}+{y}")

        # ── Tiêu đề ───────────────────────────────────────────────────────
        tk.Label(dlg, text="💾  Xuat Audio",
                 font=("Segoe UI", 13, "bold"),
                 bg=C["panel"], fg=C["accent"]).pack(pady=(14, 8))

        max_files = len(self.file_list)

        # ── Chế độ xuất ───────────────────────────────────────────────────
        mode_var = tk.StringVar(value="single")

        f_mode = tk.Frame(dlg, bg=C["panel"])
        f_mode.pack(fill="x", padx=20, pady=2)

        for txt, val in [
            ("Xuat file hien tai (1 file → 1 audio)",  "single"),
            ("Ghep theo nhom  (N file → 1 audio)",      "batch"),
            ("Xuat toan bo folder (moi file 1 audio)",  "all"),
        ]:
            tk.Radiobutton(
                f_mode, text=txt, variable=mode_var, value=val,
                font=("Segoe UI", 9), bg=C["panel"], fg=C["text"],
                selectcolor=C["bg"], activebackground=C["panel"],
                command=lambda: _update_mode()
            ).pack(anchor="w", pady=1)

        # ── Tuỳ chọn batch (hiện/ẩn theo mode) ───────────────────────────
        batch_frame = tk.Frame(dlg, bg=C["panel"])

        tk.Label(batch_frame, text="So file moi nhom:",
                 font=("Segoe UI", 9), bg=C["panel"], fg=C["dim"]
                 ).pack(side="left")

        # FIX: to phải >= from_ (tránh crash khi file_list rỗng)
        batch_to  = max(max_files, 2)
        batch_var = tk.IntVar(value=min(10, batch_to))
        tk.Spinbox(
            batch_frame, from_=2, to=batch_to, increment=1,
            textvariable=batch_var, width=5,
            font=("Segoe UI", 9), bg=C["bg"], fg=C["text"],
            buttonbackground=C["card"], highlightthickness=0, relief="flat"
        ).pack(side="left", padx=6)

        tk.Label(batch_frame,
                 text=f"file/nhom  (tong {max_files} file)",
                 font=("Segoe UI", 8), bg=C["panel"], fg=C["dim"]
                 ).pack(side="left")

        info_lbl = tk.Label(dlg, text="",
                            font=("Segoe UI", 8), bg=C["panel"],
                            fg=C["yellow"], justify="left", wraplength=420)

        def _update_mode(*_):
            m = mode_var.get()
            if m == "batch":
                batch_frame.pack(fill="x", padx=36, pady=2)
                # Tính preview nhóm
                n       = batch_var.get()
                total   = len(self.file_list)
                if total > 0 and n >= 2:
                    groups   = (total + n - 1) // n
                    previews = []
                    for i in range(0, total, n):
                        b    = self.file_list[i: i + n]
                        name = (f"{Path(b[0]).stem} → {Path(b[-1]).stem}"
                                if len(b) > 1 else Path(b[0]).stem)
                        previews.append(f"[{name}]")
                    preview = "  ".join(previews[:3])
                    if len(previews) > 3:
                        preview += f"  ... (+{len(previews)-3} nhom)"
                    info_lbl.config(text=f"Tong {total} file → {groups} nhom:\n{preview}")
                else:
                    info_lbl.config(text="(Chua co file → chon folder truoc)")
                info_lbl.pack(fill="x", padx=20, pady=2)
            else:
                batch_frame.pack_forget()
                info_lbl.pack_forget()

        batch_var.trace_add("write", _update_mode)

        # ── Delay ─────────────────────────────────────────────────────────
        delay_f = tk.Frame(dlg, bg=C["panel"])
        delay_f.pack(fill="x", padx=20, pady=4)
        tk.Label(delay_f, text="Delay giua file (giay):",
                 font=("Segoe UI", 9), bg=C["panel"], fg=C["dim"]
                 ).pack(side="left")
        delay_var = tk.DoubleVar(value=1.5)
        tk.Spinbox(
            delay_f, from_=0.0, to=10.0, increment=0.5,
            textvariable=delay_var, width=5,
            font=("Segoe UI", 9), bg=C["bg"], fg=C["text"],
            buttonbackground=C["card"], highlightthickness=0, relief="flat"
        ).pack(side="left", padx=6)

        # ── Định dạng ─────────────────────────────────────────────────────
        fmt_f = tk.Frame(dlg, bg=C["panel"])
        fmt_f.pack(fill="x", padx=20, pady=4)
        tk.Label(fmt_f, text="Dinh dang:",
                 font=("Segoe UI", 9), bg=C["panel"], fg=C["dim"]
                 ).pack(side="left")
        fmt_var = tk.StringVar(value="wav")
        for label, val in [("WAV (chinh xac)", "wav"), ("MP3 (nho hon)", "mp3")]:
            tk.Radiobutton(
                fmt_f, text=label, variable=fmt_var, value=val,
                font=("Segoe UI", 9), bg=C["panel"], fg=C["text"],
                selectcolor=C["bg"], activebackground=C["panel"]
            ).pack(side="left", padx=(8, 0))

        # ── Thư mục lưu ───────────────────────────────────────────────────
        out_f = tk.Frame(dlg, bg=C["panel"])
        out_f.pack(fill="x", padx=20, pady=4)
        tk.Label(out_f, text="Luu vao:",
                 font=("Segoe UI", 9), bg=C["panel"], fg=C["dim"]
                 ).pack(side="left")

        # Đọc export_dir an toàn (phòng trường hợp attribute chưa có)
        _export_dir = getattr(self.cfg, "export_dir", "") or str(EXPORTS_DIR)
        out_dir_var = tk.StringVar(value=_export_dir)

        tk.Entry(
            out_f, textvariable=out_dir_var,
            font=("Segoe UI", 9), bg=C["bg"], fg=C["text"],
            insertbackground=C["text"], relief="flat"
        ).pack(side="left", fill="x", expand=True, padx=(6, 4))

        def _choose_out():
            d = filedialog.askdirectory(
                title="Chon thu muc luu audio",
                initialdir=out_dir_var.get())
            if d:
                out_dir_var.set(d)
                # Lưu lại vào cfg nếu có thuộc tính
                if hasattr(self.cfg, "export_dir"):
                    self.cfg.export_dir = d
                    self.mgr.save()

        self._btn(out_f, "📂", _choose_out, C["card"]).pack(side="left")

        # ── Tắt máy sau khi xong ──────────────────────────────────────────
        shut_f = tk.Frame(dlg, bg=C["panel"])
        shut_f.pack(fill="x", padx=20, pady=4)
        shutdown_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            shut_f, text="🔌 Tat may sau khi xuat xong",
            variable=shutdown_var,
            font=("Segoe UI", 9), bg=C["panel"], fg=C["yellow"],
            selectcolor=C["bg"], activebackground=C["panel"]
        ).pack(side="left")

        # ── Nút hành động ─────────────────────────────────────────────────
        btn_f = tk.Frame(dlg, bg=C["panel"])
        btn_f.pack(pady=12)
        self._btn(btn_f, "✅ Bat dau xuat", lambda: _do(), C["accent"]
                  ).pack(side="left", padx=8)
        self._btn(btn_f, "Huy", dlg.destroy, C["border"]
                  ).pack(side="left", padx=8)

        # ── Logic xử lý khi bấm OK ────────────────────────────────────────
        def _do():
            mode     = mode_var.get()
            fmt      = fmt_var.get()
            delay    = delay_var.get()
            shutdown = shutdown_var.get()
            out_dir  = Path(out_dir_var.get())

            if not self.file_list:
                messagebox.showwarning("Chua co file",
                    "Vui long chon folder chua file .txt truoc.")
                return

            out_dir.mkdir(parents=True, exist_ok=True)
            jobs: list = []

            if mode == "single":
                if not self.chunks:
                    messagebox.showwarning("Chua chon file",
                        "Vui long chon file truyen truoc.")
                    return
                default = Path(self.file_list[self.cur_file_idx]).stem
                out = filedialog.asksaveasfilename(
                    title="Luu file audio",
                    initialdir=str(out_dir),
                    initialfile=default,
                    defaultextension=f".{fmt}",
                    filetypes=[(fmt.upper(), f"*.{fmt}")])
                if not out:
                    return
                jobs = [([self.file_list[self.cur_file_idx]], out)]

            elif mode == "batch":
                n = batch_var.get()
                for i in range(0, len(self.file_list), n):
                    batch = self.file_list[i: i + n]
                    name  = (f"{Path(batch[0]).stem}_den_{Path(batch[-1]).stem}"
                             if len(batch) > 1 else Path(batch[0]).stem)
                    jobs.append((batch, str(out_dir / f"{name}.{fmt}")))

            else:  # all
                for fp in self.file_list:
                    jobs.append(([fp], str(out_dir / f"{Path(fp).stem}.{fmt}")))

            # ── Preview + mark-done dialog ────────────────────────────────
            story_folder = Path(self.file_list[0]).parent
            prog = StoryExportProgress(str(story_folder))
            prog.scan_and_sync(str(out_dir))

            # Xây dựng danh sách job_states (mutable để refresh được)
            def _build_states():
                states = []
                for files, out_path_str in jobs:
                    out_p  = Path(out_path_str).with_suffix(f".{fmt}")
                    stems  = [Path(fp).stem for fp in files]
                    all_done = all(
                        prog.get_status(s) == StoryExportProgress.STATUS_DONE
                        for s in stems
                    )
                    state = "done" if (all_done and out_p.exists()) else "pending"
                    states.append({
                        "files":    files,
                        "out_str":  out_path_str,
                        "stems":    stems,
                        "out_p":    out_p,
                        "state":    state,
                    })
                return states

            job_states = _build_states()

            prev = tk.Toplevel(self.root)
            prev.title("Kiem tra tien do & Xac nhan xuat")
            prev.geometry("600x520")
            prev.resizable(True, True)
            prev.configure(bg=C["panel"])
            prev.grab_set()
            prev.transient(self.root)
            px = self.root.winfo_x() + (self.root.winfo_width()  - 600) // 2
            py = self.root.winfo_y() + (self.root.winfo_height() - 520) // 2
            prev.geometry(f"+{px}+{py}")

            tk.Label(prev, text="📋  Kiem tra tien do truoc khi xuat",
                     font=("Segoe UI", 12, "bold"),
                     bg=C["panel"], fg=C["accent"]).pack(pady=(14, 2))

            sum_lbl = tk.Label(prev, text="",
                               font=("Segoe UI", 9, "bold"),
                               bg=C["panel"], fg=C["yellow"])
            sum_lbl.pack(pady=(0, 4))

            frame_list = tk.Frame(prev, bg=C["panel"])
            frame_list.pack(fill="both", expand=True, padx=14, pady=(0, 2))

            sb = tk.Scrollbar(frame_list, bg=C["panel"], relief="flat", width=8)
            sb.pack(side="right", fill="y")
            lb = tk.Listbox(frame_list,
                            bg=C["bg"], fg=C["text"],
                            font=("Consolas", 9),
                            borderwidth=0, highlightthickness=0,
                            selectbackground=C["accent2"],
                            selectforeground="white",
                            selectmode="extended",
                            yscrollcommand=sb.set)
            lb.pack(fill="both", expand=True)
            sb.config(command=lb.yview)

            tk.Label(prev,
                     text=("✓ xanh = da xong (skip)   "
                           "⏳ trang = chua xuat   "
                           "Chon nhieu dong: Ctrl+Click / Shift+Click"),
                     font=("Segoe UI", 8), bg=C["panel"], fg=C["dim"]
                     ).pack(pady=(2, 2))

            # Nút hành động
            btn_row = tk.Frame(prev, bg=C["panel"])
            btn_row.pack(pady=6)

            mark_btn   = self._btn(btn_row, "✓ Danh dau Done (cac dong chon)",
                                   None, C["accent2"])
            mark_btn.pack(side="left", padx=5)

            unmark_btn = self._btn(btn_row, "↺ Reset ve Pending (cac dong chon)",
                                   None, C["border"])
            unmark_btn.pack(side="left", padx=5)

            start_btn  = self._btn(btn_row, "▶ Bat dau xuat", None, C["accent"])
            start_btn.pack(side="left", padx=5)

            self._btn(btn_row, "Huy", prev.destroy, C["border"]).pack(side="left", padx=5)

            _confirmed = [False]

            def _refresh_lb():
                lb.delete(0, "end")
                n_done = n_pend = 0
                for js in job_states:
                    out_name = js["out_p"].name
                    if len(js["files"]) > 1:
                        label = (f"{Path(js['files'][0]).stem}"
                                 f"..{Path(js['files'][-1]).stem} → {out_name}")
                    else:
                        label = out_name
                    if js["state"] == "done":
                        lb.insert("end", f"  ✓  {label}")
                        lb.itemconfig("end", fg=C["green"])
                        n_done += 1
                    else:
                        lb.insert("end", f"  ⏳  {label}")
                        lb.itemconfig("end", fg=C["text"])
                        n_pend += 1
                sum_lbl.config(
                    text=(f"Tong {len(job_states)} job:  "
                          f"✓ {n_done} da xong (skip)   "
                          f"⏳ {n_pend} chua xong (se xuat)"),
                    fg=C["green"] if n_pend == 0 else C["yellow"])
                start_btn.config(
                    text=(f"▶ Bat dau xuat ({n_pend} job)"
                          if n_pend > 0 else "✓ Tat ca da xong"),
                    bg=C["accent"] if n_pend > 0 else C["green"])

            def _mark_selected_done():
                sel = lb.curselection()
                if not sel:
                    return
                for i in sel:
                    js = job_states[i]
                    # Cập nhật StoryExportProgress: tất cả file trong job → done
                    for fp, stem in zip(js["files"], js["stems"]):
                        prog.set_status(stem, StoryExportProgress.STATUS_DONE,
                                        output=str(js["out_p"]))
                    js["state"] = "done"
                _refresh_lb()

            def _unmark_selected():
                sel = lb.curselection()
                if not sel:
                    return
                for i in sel:
                    js = job_states[i]
                    for stem in js["stems"]:
                        prog.set_status(stem, StoryExportProgress.STATUS_PENDING)
                    js["state"] = "pending"
                _refresh_lb()

            def _start():
                _confirmed[0] = True
                prev.destroy()

            mark_btn.config(command=_mark_selected_done)
            unmark_btn.config(command=_unmark_selected)
            start_btn.config(command=_start)

            _refresh_lb()
            prev.wait_window()

            if not _confirmed[0]:
                return

            dlg.destroy()
            threading.Thread(
                target=self._export_jobs_worker,
                args=(jobs, fmt, delay, shutdown),
                daemon=True
            ).start()

        # Gọi lần đầu để cập nhật hiển thị
        _update_mode()


    def _export_jobs_worker(self, jobs: List[tuple], fmt: str,
                            delay_sec: float, shutdown: bool):
        """
        Worker thread xuất audio — an toàn cho file dài đến 10+ tiếng.

        Hai lớp lưu tiến độ:
        A) StoryExportProgress  → <story_folder>/export_progress.json
           Lưu trạng thái từng CHƯƠNG (pending/processing/done + output path).
           Ổn định vĩnh viễn, KHÔNG bao giờ bị xóa tự động.
           Dùng để: biết chương nào đã xong, chương nào cần làm tiếp.

        B) ExportResumeManager  → config/export_progress/<id>.json
           Lưu tiến độ CHUNK bên trong một chương (khi ghép nhiều file).
           Chỉ tồn tại trong lúc đang xuất, tự xóa khi xong.
           Dùng để: resume khi tắt giữa chừng trong 1 chương dài.
        """
        import shutil
        from pathlib import Path as _P

        def _update_status(msg: str):
            self.root.after(0, lambda m=msg: self.status_lbl.config(text=m))

        self.root.after(0, lambda: self._set_export_running(True))
        total_jobs = len(jobs)

        for ji, (files, out_path) in enumerate(jobs):
            if self._export_stop_flag:
                break

            out_path = _P(out_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            chunk_ext = "mp3" if self.cfg.engine == "edge_tts" else "wav"

            # ── Lớp A: StoryExportProgress ───────────────────────────────
            # Luôn dùng cho MỌI mode: single / all / batch N→1
            story_folder = _P(files[0]).parent if files else out_path.parent
            story_prog   = StoryExportProgress(str(story_folder))
            story_prog.scan_and_sync(str(out_path.parent))

            # Skip nếu TẤT CẢ file trong job đã done VÀ file output tồn tại
            final_out_expected = out_path.with_suffix(f".{fmt}")
            if final_out_expected.exists():
                all_done = all(
                    story_prog.get_status(_P(fp).stem) == StoryExportProgress.STATUS_DONE
                    for fp in files
                )
                if all_done:
                    _update_status(
                        f"[SKIP] {final_out_expected.name} ({len(files)} file) da xong")
                    continue

            # Đánh dấu TẤT CẢ file trong job là đang xử lý
            for fp in files:
                story_prog.set_status(_P(fp).stem,
                                      StoryExportProgress.STATUS_PROCESSING)
            # ── Lớp B: ExportResumeManager (chunk-level resume) ──────────
            # Dùng MD5 để export_id ổn định qua mọi lần restart
            export_id = "exp_" + hashlib.md5(
                str(out_path).encode("utf-8")).hexdigest()[:16]
            self._active_export_id = export_id

            existing  = self.export_mgr.load(export_id)

            # BUG FIX: dùng lại đúng chunk_size đã tách lúc tạo export này.
            # Nếu người dùng đổi "chunk size" giữa lúc dừng và lúc resume,
            # tách lại theo size mới sẽ làm lệch số chunk / tên file tạm cũ.
            export_chunk_size = (existing.get("chunk_size", self.cfg.chunk_size)
                                 if existing else self.cfg.chunk_size)

            if existing and _P(existing.get("tmp_path", "")).exists():
                # RESUME chunk-level: dùng lại tmp_dir cũ
                tmp_dir      = _P(existing["tmp_path"])
                total_chunks = existing.get("total_chunks", 0)
                _update_status(
                    f"Resume {out_path.name}: "
                    f"{existing.get('done_chunks',0)}/{total_chunks} chunk")
            else:
                # NEW: tạo tmp_dir và tính tổng chunks
                tmp_dir = EXPORTS_DIR / f"tmp_{export_id}"
                tmp_dir.mkdir(exist_ok=True)

                all_file_chunks: list = []
                total_chunks = 0
                for fp in files:
                    try:
                        cks = TextProcessor.split_chunks(
                            TextProcessor.clean(TextProcessor.load(fp)),
                            export_chunk_size)
                        all_file_chunks.append((fp, cks))
                        total_chunks += len(cks)
                    except Exception as e:
                        print(f"[Export] Bo qua {fp}: {e}")
                        all_file_chunks.append((fp, []))

                self.export_mgr.save(export_id, {
                    "out_path":       str(out_path),
                    "tmp_path":       str(tmp_dir),
                    "files":          files,
                    "fmt":            fmt,
                    "delay_sec":      delay_sec,
                    "done_chunks":    0,
                    "total_chunks":   total_chunks,
                    "chunk_ext":      chunk_ext,
                    "chunk_size":     export_chunk_size,
                    "remaining_jobs": [(f, str(p)) for f, p in jobs[ji + 1:]],
                    "shutdown":       shutdown,
                })

            # Rebuild all_file_chunks khi resume (không có từ branch trên)
            # Dùng export_chunk_size (đã lưu lúc tạo) để khớp đúng file tạm cũ.
            if existing:
                all_file_chunks = []
                for fp in files:
                    try:
                        cks = TextProcessor.split_chunks(
                            TextProcessor.clean(TextProcessor.load(fp)),
                            export_chunk_size)
                        all_file_chunks.append((fp, cks))
                    except Exception:
                        all_file_chunks.append((fp, []))

            # ── Bước 1: Synth từng chunk → file tạm ──────────────────────
            chunk_counter = 0
            stopped = False

            # ── Flatten tất cả chunks thành danh sách phẳng có global_idx cố định ──
            # global_idx quyết định tên file c000001.xxx → đảm bảo thứ tự khi ghép
            flat_tasks: list = []
            for fi, (fp, chunks) in enumerate(all_file_chunks):
                for ci, chunk in enumerate(chunks):
                    flat_tasks.append((len(flat_tasks) + 1, fi, fp, ci,
                                       len(chunks), chunk))

            # ── Chọn số workers ──────────────────────────────────────────────────
            # edge   : I/O bound (chờ mạng) → parallel hiệu quả
            # vieneu : CPU bound, model không thread-safe → 1 worker
            engine = self.cfg.engine
            if engine == "edge_tts":
                max_w = max(1, self.cfg.export_workers)
            else:
                max_w = 1
            use_queue = False

            _counter_lock = threading.Lock()

            def _synth_one(task):
                """Synth 1 chunk (edge/vieneu), ghi file tạm."""
                gidx, fi, fp, ci, total_ci, chunk = task
                if self._export_stop_flag:
                    return gidx, False
                tmp_file = tmp_dir / f"c{gidx:06d}.{chunk_ext}"
                if tmp_file.exists() and tmp_file.stat().st_size > 0:
                    return gidx, True
                data, _ = self.worker._synth_with_retry(chunk)
                if data:
                    tmp_file.write_bytes(data)
                    return gidx, True
                return gidx, False

            from concurrent.futures import ThreadPoolExecutor, as_completed

            # ── Single-chunk mode (edge / vieneu) ────────────────────────
            with ThreadPoolExecutor(max_workers=max_w) as pool:
                    futures = {pool.submit(_synth_one, t): t for t in flat_tasks}
                    for fut in as_completed(futures):
                        if self._export_stop_flag:
                            stopped = True
                            break
                        gidx, ok = fut.result()
                        task     = futures[fut]
                        fname    = _P(task[2]).name

                        with _counter_lock:
                            chunk_counter += 1
                            cc = chunk_counter

                        skip_tag = "[Skip]" if not ok else ""
                        self.root.after(0,
                            lambda cc=cc, tc=total_chunks, f=fname,
                                   s=skip_tag, w=max_w:
                            self.status_lbl.config(
                                text=f"Job {ji+1}/{total_jobs} | {f} "
                                     f"({cc}/{tc}) ×{w}  {s}"))

                        _remaining = [(f, str(p)) for f, p in jobs[ji + 1:]]
                        with _counter_lock:
                            self.export_mgr.save(export_id, {
                                "out_path":       str(out_path),
                                "tmp_path":       str(tmp_dir),
                                "files":          files,
                                "fmt":            fmt,
                                "delay_sec":      delay_sec,
                                "done_chunks":    chunk_counter,
                                "total_chunks":   total_chunks,
                                "chunk_ext":      chunk_ext,
                                "chunk_size":     export_chunk_size,
                                "remaining_jobs": _remaining,
                                "shutdown":       shutdown,
                            })

            if stopped:
                for fp in files:
                    story_prog.set_status(_P(fp).stem,
                                          StoryExportProgress.STATUS_PENDING)
                _update_status(
                    f"Da dung ({chunk_counter}/{total_chunks} chunk). "
                    f"Bam '▶ Tiep tuc xuat' de tiep tuc.")
                break

            # ── Bước 2: Ghép bằng pydub (chuẩn hóa sample rate tự động) ──
            target_sr = 48000   # v3 xuất 48kHz
            _update_status(f"Dang ghep {chunk_counter} chunk bang pydub...")

            try:
                from pydub import AudioSegment
                silence  = AudioSegment.silent(
                    duration=int(delay_sec * 1000), frame_rate=target_sr)
                combined = AudioSegment.empty()

                global_idx = 0
                for fi, (fp, chunks) in enumerate(all_file_chunks):
                    for _ in chunks:
                        global_idx += 1
                        tf = tmp_dir / f"c{global_idx:06d}.{chunk_ext}"
                        if not tf.exists():
                            continue
                        _update_status(f"Dang ghep chunk {global_idx}/{chunk_counter}...")
                        seg = AudioSegment.from_file(str(tf), format=chunk_ext)
                        if seg.frame_rate != target_sr:
                            seg = seg.set_frame_rate(target_sr)
                        if seg.channels != 1:
                            seg = seg.set_channels(1)
                        combined += seg
                    if fi < len(all_file_chunks) - 1 and delay_sec > 0:
                        combined += silence

                _update_status(f"Dang luu {fmt.upper()}...")
                final_out = out_path.with_suffix(f".{fmt}")
                export_params: dict = {"format": fmt}
                if fmt == "mp3":
                    export_params["bitrate"] = "128k"
                combined.export(str(final_out), **export_params)

            except Exception as e:
                for fp in files:
                    story_prog.set_status(_P(fp).stem,
                                          StoryExportProgress.STATUS_PENDING)
                self._active_export_id = ""
                self.root.after(0, lambda e=e: messagebox.showerror(
                    "Loi xuat",
                    f"{e}\n\nFile tam con tai:\n{tmp_dir}\n"
                    "Ban co the thu lai bang nut 'Tiep tuc xuat'."))
                self.root.after(0, lambda: self._set_export_running(False))
                return

            # ── Bước 3: Dọn dẹp ──────────────────────────────────────────
            shutil.rmtree(tmp_dir, ignore_errors=True)
            self.export_mgr.delete(export_id)

            # Đánh dấu done — tất cả file trỏ về cùng output (batch N→1 share)
            for fp in files:
                story_prog.set_status(_P(fp).stem,
                                      StoryExportProgress.STATUS_DONE,
                                      output=str(final_out))
            done_jobs = ji + 1
            remain    = total_jobs - done_jobs
            msg = f"✓ Job {done_jobs}/{total_jobs} xong: {final_out.name}"
            if remain > 0:
                msg += f"  (con {remain} job)"
            _update_status(msg)

        # ── Kết thúc toàn bộ batch ────────────────────────────────────────
        self._active_export_id = ""
        self.root.after(0, lambda: self._set_export_running(False))

        if not self._export_stop_flag:
            out_dir = Path(jobs[-1][1]).parent if jobs else EXPORTS_DIR
            self.root.after(0, lambda: (
                messagebox.showinfo(
                    "Xuat Audio Hoan Thanh",
                    f"Da xuat xong {total_jobs} job!\nLuu tai: {out_dir}"),
                self.status_lbl.config(text="")))
            if shutdown:
                self.root.after(3000, self._shutdown_computer)


    # ── Chống sleep khi export ────────────────────────────────────────────────

    def _prevent_sleep(self):
        """Yêu cầu Windows KHÔNG sleep/hibernate trong lúc đang export."""
        try:
            ES_CONTINUOUS      = 0x80000000
            ES_SYSTEM_REQUIRED = 0x00000001   # giữ CPU không ngủ
            ctypes.windll.kernel32.SetThreadExecutionState(
                ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
        except Exception:
            pass   # Không phải Windows → bỏ qua

    def _allow_sleep(self):
        """Trả quyền sleep lại cho Windows sau khi export xong."""
        try:
            ES_CONTINUOUS = 0x80000000
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
        except Exception:
            pass

    def _set_export_running(self, running: bool):
        """Cập nhật trạng thái nút khi export bắt đầu/kết thúc."""
        if running:
            self._prevent_sleep()          # ← chặn Windows sleep
            self._export_stop_flag = False
            self._stop_export_btn.config(state="normal",   bg=C["accent"])
            self._resume_export_btn.config(state="disabled", bg=C["accent2"])
        else:
            self._allow_sleep()            # ← trả quyền sleep lại
            self._export_stop_flag = False
            self._stop_export_btn.config(state="disabled", bg=C["border"])
            # Hiện nút "Tiếp tục" nếu còn export bị dừng chưa xong
            pending = self.export_mgr.list_all()
            if pending:
                self._resume_export_btn.config(state="normal")
            else:
                self._resume_export_btn.config(state="disabled")

    def _stop_export(self):
        """Dừng export — giữ lại progress, cho phép tiếp tục sau."""
        self._export_stop_flag = True
        self.status_lbl.config(text="Dang dung xuat... chunk hien tai xong thi dung.")
        self._stop_export_btn.config(state="disabled", bg=C["border"])

    def _resume_paused_export(self):
        """Tiếp tục export bị tạm dừng trước đó."""
        pending = self.export_mgr.list_all()
        if not pending:
            self._resume_export_btn.config(state="disabled")
            return
        info  = pending[0]
        fname = Path(info.get("out_path", "")).name or "unknown"
        done  = info.get("done_chunks", 0)
        total = info.get("total_chunks", 1)
        pct   = f"{done/total*100:.0f}%"

        # Job đang bị dở + tất cả jobs còn lại chưa làm
        current_job    = (info.get("files", []), info.get("out_path", ""))
        remaining_jobs = [(f, p) for f, p in info.get("remaining_jobs", [])]
        all_jobs       = [current_job] + remaining_jobs

        n_remain = len(remaining_jobs)
        self.status_lbl.config(
            text=f"Tiep tuc xuat '{fname}' ({pct} da xong)"
                 + (f" + {n_remain} job tiep theo" if n_remain else "") + "...")
        self._resume_export_btn.config(state="disabled")
        threading.Thread(
            target=self._export_jobs_worker,
            args=(all_jobs,
                  info.get("fmt",       "wav"),
                  info.get("delay_sec", 1.5),
                  False),
            daemon=True
        ).start()

    # ═══════════════════════════════════════════════════════════════════════
    # BATCH EXPORT  –  Xuất nhiều truyện / tự động resume
    # ═══════════════════════════════════════════════════════════════════════

    def _show_batch_export_dialog(self):
        """
        Dialog xuất hàng loạt:
        - Chọn thư mục gốc chứa các folder truyện
        - Chọn output folder
        - Hiển thị danh sách truyện + tiến độ
        - Nút Bắt đầu / Dừng
        """
        dlg = tk.Toplevel(self.root)
        dlg.title("📦  Xuat Lo Nhieu Truyen")
        dlg.geometry("620x520")
        dlg.resizable(True, True)
        dlg.configure(bg=C["panel"])
        dlg.grab_set()
        dlg.transient(self.root)
        x = self.root.winfo_x() + (self.root.winfo_width()  - 620) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 520) // 2
        dlg.geometry(f"+{x}+{y}")

        tk.Label(dlg, text="📦  Xuat Lo – Tu dong Resume",
                 font=("Segoe UI", 13, "bold"),
                 bg=C["panel"], fg=C["accent"]).pack(pady=(14, 6))

        # Đường dẫn
        path_f = tk.Frame(dlg, bg=C["panel"])
        path_f.pack(fill="x", padx=16, pady=4)

        # Root folder (chứa các folder truyện)
        tk.Label(path_f, text="Thu muc goc (chua cac folder truyen):",
                 font=("Segoe UI", 9), bg=C["panel"], fg=C["dim"]).pack(anchor="w")
        root_row = tk.Frame(path_f, bg=C["panel"])
        root_row.pack(fill="x", pady=(2, 6))
        root_var = tk.StringVar(value=self.cfg.last_folder or str(APP_DIR))
        tk.Entry(root_row, textvariable=root_var,
                 font=("Segoe UI", 9), bg=C["bg"], fg=C["text"],
                 insertbackground=C["text"], relief="flat"
                 ).pack(side="left", fill="x", expand=True)
        def _choose_root():
            d = filedialog.askdirectory(initialdir=root_var.get())
            if d: root_var.set(d); _refresh_list()
        self._btn(root_row, "📂", _choose_root, C["card"]).pack(side="left", padx=(4, 0))

        # Output folder
        tk.Label(path_f, text="Thu muc luu audio (de trong = cung folder truyen):",
                 font=("Segoe UI", 9), bg=C["panel"], fg=C["dim"]).pack(anchor="w")
        out_row = tk.Frame(path_f, bg=C["panel"])
        out_row.pack(fill="x", pady=(2, 6))
        out_var = tk.StringVar(value=self.cfg.export_dir if self.cfg.export_dir else "")
        tk.Entry(out_row, textvariable=out_var,
                 font=("Segoe UI", 9), bg=C["bg"], fg=C["text"],
                 insertbackground=C["text"], relief="flat"
                 ).pack(side="left", fill="x", expand=True)
        def _choose_out():
            d = filedialog.askdirectory(initialdir=out_var.get() or root_var.get())
            if d: out_var.set(d)
        self._btn(out_row, "📂", _choose_out, C["card"]).pack(side="left", padx=(4, 0))

        # Format
        fmt_f = tk.Frame(dlg, bg=C["panel"])
        fmt_f.pack(fill="x", padx=16, pady=2)
        tk.Label(fmt_f, text="Dinh dang:",
                 font=("Segoe UI", 9), bg=C["panel"], fg=C["dim"]).pack(side="left")
        fmt_var = tk.StringVar(value="wav")
        for lbl, val in [("WAV", "wav"), ("MP3", "mp3")]:
            tk.Radiobutton(fmt_f, text=lbl, variable=fmt_var, value=val,
                           font=("Segoe UI", 9), bg=C["panel"], fg=C["text"],
                           selectcolor=C["bg"], activebackground=C["panel"]
                           ).pack(side="left", padx=(8, 0))

        # Danh sách truyện
        tk.Label(dlg, text="Danh sach truyen phat hien:",
                 font=("Segoe UI", 9, "bold"),
                 bg=C["panel"], fg=C["text"]).pack(anchor="w", padx=16, pady=(8, 2))

        list_f = tk.Frame(dlg, bg=C["panel"])
        list_f.pack(fill="both", expand=True, padx=16, pady=(0, 6))
        sb = tk.Scrollbar(list_f, bg=C["panel"], relief="flat", width=8)
        sb.pack(side="right", fill="y")
        story_list = tk.Listbox(list_f, bg=C["bg"], fg=C["text"],
                                 font=("Consolas", 9),
                                 borderwidth=0, highlightthickness=0,
                                 selectbackground=C["accent"],
                                 yscrollcommand=sb.set)
        story_list.pack(fill="both", expand=True)
        sb.config(command=story_list.yview)

        # Log nhỏ
        log_lbl = tk.Label(dlg, text="San sang.",
                           font=("Segoe UI", 9),
                           bg=C["panel"], fg=C["dim"],
                           anchor="w")
        log_lbl.pack(fill="x", padx=16)

        # Nút
        btn_f = tk.Frame(dlg, bg=C["panel"])
        btn_f.pack(pady=8)
        start_btn = self._btn(btn_f, "▶ Bat dau", None, C["accent"])
        start_btn.pack(side="left", padx=6)
        stop_btn  = self._btn(btn_f, "⏹ Dung", None, C["border"])
        stop_btn.pack(side="left", padx=6)
        stop_btn.config(state="disabled")
        self._btn(btn_f, "Huy", dlg.destroy, C["border"]).pack(side="left", padx=6)

        # Trạng thái
        _stop_ev = threading.Event()
        _stories: list = []  # [{"name", "folder", "output_dir"}]

        def _refresh_list():
            story_list.delete(0, "end")
            _stories.clear()
            root = Path(root_var.get())
            if not root.exists():
                return

            # Scan tất cả subfolder có file .txt
            for sub in sorted(root.iterdir()):
                if not sub.is_dir():
                    continue
                txts = sorted(sub.glob("*.txt"))
                if not txts:
                    continue

                out_d = Path(out_var.get()) / sub.name if out_var.get() else sub
                prog  = StoryExportProgress(str(sub))  # JSON luu trong folder truyen
                prog.scan_and_sync(str(out_d))
                stats = prog.stats()

                _stories.append({
                    "name":       sub.name,
                    "folder":     str(sub),
                    "output_dir": str(out_d),
                    "total":      stats["total"],
                    "done":       stats["done"],
                })

                pct = f"{stats['done']}/{stats['total']}"
                bar = "█" * int(stats['done'] / max(stats['total'], 1) * 10)
                bar = bar.ljust(10, "░")
                clr = C["green"] if stats["done"] == stats["total"] else C["text"]
                story_list.insert("end", f" {bar} {pct}  {sub.name}")
                story_list.itemconfig("end", fg=clr)

            log_lbl.config(text=f"Phat hien {len(_stories)} truyen", fg=C["dim"])

        root_var.trace_add("write", lambda *_: _refresh_list())
        _refresh_list()

        def _do_start():
            if not _stories:
                log_lbl.config(text="Khong co truyen nao!", fg=C["log_err"])
                return
            _stop_ev.clear()
            start_btn.config(state="disabled")
            stop_btn.config(state="normal", bg=C["accent"])
            dlg.protocol("WM_DELETE_WINDOW", lambda: None)  # chặn đóng khi chạy

            def _worker():
                fmt = fmt_var.get()
                for si, story in enumerate(_stories):
                    if _stop_ev.is_set():
                        break
                    name   = story["name"]
                    folder = story["folder"]
                    out_d  = Path(story["output_dir"])
                    out_d.mkdir(parents=True, exist_ok=True)

                    # Scan file .txt
                    txts = sorted(Path(folder).glob("*.txt"),
                                  key=lambda p: [int(x) if x.isdigit() else x.lower()
                                                 for x in re.split(r'(\d+)', p.stem)])
                    prog = StoryExportProgress(folder)  # JSON luu trong folder truyen
                    prog.scan_and_sync(str(out_d))

                    pending = prog.get_pending()
                    total_p = len(pending)

                    dlg.after(0, lambda n=name, d=prog.stats()["done"],
                                      t=len(txts):
                              log_lbl.config(
                                  text=f"[{si+1}/{len(_stories)}] {n}: {d}/{t} done, {total_p} con lai",
                                  fg=C["yellow"]))

                    for pi, item in enumerate(pending):
                        if _stop_ev.is_set():
                            break
                        stem       = item["stem"]
                        fp         = str(Path(folder) / f"{stem}.txt")
                        out_dir_ch = Path(out_d)
                        out_dir_ch.mkdir(parents=True, exist_ok=True)

                        dlg.after(0, lambda s=stem, pi=pi, t=total_p:
                                  log_lbl.config(
                                      text=f"  [{pi+1}/{t}] {s}.txt → TTS...",
                                      fg=C["text"]))

                        prog.set_status(stem, StoryExportProgress.STATUS_PROCESSING)

                        try:
                            chunks    = TextProcessor.split_chunks(
                                TextProcessor.clean(TextProcessor.load(fp)),
                                self.cfg.chunk_size)
                            chunk_ext = "mp3" if self.cfg.engine == "edge_tts" else "wav"

                            import shutil as _sh
                            tmp_dir = out_dir_ch / f"_tmp_{stem}"
                            tmp_dir.mkdir(exist_ok=True)

                            try:
                                for ci, chunk in enumerate(chunks):
                                    if _stop_ev.is_set():
                                        break
                                    data, _ = self.worker._synth_with_retry(chunk)
                                    if data:
                                        (tmp_dir / f"c{ci+1:06d}.{chunk_ext}"
                                         ).write_bytes(data)

                                if _stop_ev.is_set():
                                    prog.set_status(stem, StoryExportProgress.STATUS_PENDING)
                                    break

                                target_sr = 48000   # v3 xuất 48kHz
                                from pydub import AudioSegment
                                chunk_files = [
                                    tmp_dir / f"c{ci+1:06d}.{chunk_ext}"
                                    for ci in range(len(chunks))
                                    if (tmp_dir / f"c{ci+1:06d}.{chunk_ext}").exists()
                                ]
                                combined = AudioSegment.empty()
                                total_cf = len(chunk_files)
                                for idx_cf, tf in enumerate(chunk_files, 1):
                                    dlg.after(0, lambda i=idx_cf, t=total_cf:
                                              log_lbl.config(
                                                  text=f"  Ghep chunk {i}/{t}...",
                                                  fg=C["text"]))
                                    seg = AudioSegment.from_file(str(tf), format=chunk_ext)
                                    if seg.frame_rate != target_sr:
                                        seg = seg.set_frame_rate(target_sr)
                                    if seg.channels != 1:
                                        seg = seg.set_channels(1)
                                    combined += seg

                                out_final = out_dir_ch / f"{stem}.{fmt}"
                                dlg.after(0, lambda: log_lbl.config(
                                    text=f"  Dang luu {fmt.upper()}...", fg=C["text"]))
                                export_kw: dict = {"format": fmt}
                                if fmt == "mp3":
                                    export_kw["bitrate"] = "128k"
                                combined.export(str(out_final), **export_kw)

                            finally:
                                _sh.rmtree(tmp_dir, ignore_errors=True)

                            prog.set_status(stem, StoryExportProgress.STATUS_DONE,
                                            output=str(out_final))
                        except Exception as e:
                            prog.set_status(stem, StoryExportProgress.STATUS_PENDING)
                            dlg.after(0, lambda e=e, s=stem:
                                      log_lbl.config(
                                          text=f"  Loi {s}: {e}", fg=C["log_err"]))

                    # Refresh stats sau mỗi truyện
                    stats = prog.stats()
                    dlg.after(0, _refresh_list)

                # Xong
                dlg.after(0, lambda: (
                    start_btn.config(state="normal"),
                    stop_btn.config(state="disabled", bg=C["border"]),
                    dlg.protocol("WM_DELETE_WINDOW", dlg.destroy),
                    log_lbl.config(
                        text="Hoan thanh!" if not _stop_ev.is_set() else "Da dung.",
                        fg=C["green"] if not _stop_ev.is_set() else C["yellow"]),
                    _refresh_list(),
                ))

            threading.Thread(target=_worker, daemon=True).start()

        def _do_stop():
            _stop_ev.set()
            stop_btn.config(state="disabled")
            log_lbl.config(text="Dang dung an toan...", fg=C["yellow"])

        start_btn.config(command=_do_start)
        stop_btn.config(command=_do_stop)


    # ═══════════════════════════════════════════════════════════════════════
    # KAGGLE BATCH EXPORT
    # ═══════════════════════════════════════════════════════════════════════

    def _open_kaggle_batch_dialog(self):
        """Dialog điều phối Kaggle Batch Pipeline."""
        import threading
        from pathlib import Path as _P

        if not KAGGLE_BATCH_OK:
            messagebox.showerror(
                "Thiếu module",
                "Không tìm thấy kaggle_batch.py trong thư mục app.\n"
                "Hãy đặt file kaggle_batch.py cùng thư mục với main.py.")
            return

        story_folder = self.cfg.last_folder
        if not story_folder or not _P(story_folder).is_dir():
            messagebox.showwarning("Chưa chọn thư mục",
                                   "Hãy chọn thư mục truyện trước.")
            return

        # Nếu chưa điền credentials → mở thẳng settings dialog
        if not self.cfg.kaggle_username or not self.cfg.kaggle_api_key \
                or not self.cfg.kaggle_kernel_slug:
            self._open_kaggle_settings(on_saved=self._open_kaggle_batch_dialog)
            return

        story_p = _P(story_folder)
        out_dir = _P(self.cfg.export_dir or str(EXPORTS_DIR / story_p.name))
        out_dir.mkdir(parents=True, exist_ok=True)

        prog = StoryExportProgress(str(story_p))
        prog.scan_and_sync(str(out_dir))
        pending = prog.get_pending()
        if not pending:
            messagebox.showinfo("Xong rồi!", "Tất cả chap đã được xuất.")
            return

        pending_stems = [p["stem"] for p in pending]

        # ── Xây dialog ────────────────────────────────────────────────────
        dlg = tk.Toplevel(self.root)
        dlg.title("☁  Kaggle Batch TTS Export")
        dlg.geometry("680x520")
        dlg.resizable(True, True)
        dlg.configure(bg=C["panel"])
        dlg.transient(self.root)
        cx = self.root.winfo_x() + (self.root.winfo_width()  - 680) // 2
        cy = self.root.winfo_y() + (self.root.winfo_height() - 520) // 2
        dlg.geometry(f"+{cx}+{cy}")

        tk.Label(dlg, text="☁  Kaggle Batch TTS Export",
                 font=("Segoe UI", 13, "bold"),
                 bg=C["panel"], fg=C["accent"]).pack(pady=(14, 4))
        tk.Label(dlg,
                 text=(f"Truyện: {story_p.name}  |  "
                       f"{len(pending_stems)} chap chưa xuất  |  "
                       f"Batch: {self.cfg.kaggle_batch_size} chap/ZIP"),
                 font=("Segoe UI", 9),
                 bg=C["panel"], fg=C["dim"]).pack(pady=(0, 8))

        # Progress bar
        pbar_var = tk.DoubleVar(value=0)
        ttk.Progressbar(dlg, variable=pbar_var, maximum=100, length=640,
                        style="Accent.Horizontal.TProgressbar"
                        ).pack(padx=20, pady=(0, 2))
        pct_lbl = tk.Label(dlg, text="0%",
                           font=("Segoe UI", 9),
                           bg=C["panel"], fg=C["dim"])
        pct_lbl.pack()

        # Status
        status_lbl = tk.Label(dlg, text="Sẵn sàng.",
                              font=("Segoe UI", 10, "bold"),
                              bg=C["panel"], fg=C["yellow"],
                              wraplength=640)
        status_lbl.pack(pady=(4, 2))

        # Log box
        log_frame = tk.Frame(dlg, bg=C["bg"])
        log_frame.pack(fill="both", expand=True, padx=16, pady=4)
        log_sb = tk.Scrollbar(log_frame, bg=C["panel"])
        log_sb.pack(side="right", fill="y")
        log_box = tk.Text(log_frame, bg=C["bg"], fg=C["text"],
                          font=("Consolas", 9), relief="flat",
                          wrap="word", yscrollcommand=log_sb.set,
                          state="disabled", height=13)
        log_box.pack(fill="both", expand=True)
        log_sb.config(command=log_box.yview)

        # Buttons
        btn_row = tk.Frame(dlg, bg=C["panel"])
        btn_row.pack(pady=8)
        start_btn = self._btn(btn_row, "▶ Bắt đầu",  None, C["accent"])
        start_btn.pack(side="left", padx=6)
        stop_btn  = self._btn(btn_row, "⏹ Dừng",     None, C["border"])
        stop_btn.pack(side="left", padx=6)
        stop_btn.config(state="disabled")
        self._btn(btn_row, "✕ Đóng",
                  dlg.destroy, C["border"]).pack(side="left", padx=6)

        # ── Callbacks ─────────────────────────────────────────────────────
        def _append_log(msg: str):
            log_box.config(state="normal")
            log_box.insert("end", msg + "\n")
            log_box.see("end")
            log_box.config(state="disabled")

        def _on_log(msg):
            dlg.after(0, lambda m=msg: _append_log(m))

        def _on_progress(msg, pct):
            def _upd():
                status_lbl.config(text=msg)
                if 0 <= pct <= 1:
                    v = round(pct * 100, 1)
                    pbar_var.set(v)
                    pct_lbl.config(text=f"{v:.0f}%")
            dlg.after(0, _upd)

        def _on_batch_done(stems, wavs):
            s = stems[0] if stems else "?"
            e = stems[-1] if stems else "?"
            dlg.after(0, lambda: _append_log(
                f"✓ Batch xong: {len(stems)} chap ({s}…{e})"))

        def _on_finished(ok, msg):
            def _upd():
                start_btn.config(state="normal")
                stop_btn.config(state="disabled", bg=C["border"])
                status_lbl.config(
                    text=msg,
                    fg=C["green"] if ok else C["accent"])
                if ok:
                    pbar_var.set(100)
                    pct_lbl.config(text="100%")
                _append_log("=" * 48)
                _append_log(msg)
            dlg.after(0, _upd)

        # ── Start / Stop ───────────────────────────────────────────────────
        def _do_start():
            start_btn.config(state="disabled")
            stop_btn.config(state="normal", bg=C["accent"])
            status_lbl.config(text="Đang chạy...", fg=C["yellow"])
            pbar_var.set(0)
            pct_lbl.config(text="0%")

            cfg = KaggleBatchConfig(
                username     = self.cfg.kaggle_username,
                api_key      = self.cfg.kaggle_api_key,
                dataset_slug = self.cfg.kaggle_dataset_slug,
                kernel_slug  = self.cfg.kaggle_kernel_slug,
                batch_size   = self.cfg.kaggle_batch_size,
                poll_sec     = self.cfg.kaggle_poll_sec,
                voice_id     = self.cfg.kaggle_batch_voice,
                speed        = self.cfg.speed,
            )
            mgr = KaggleBatchManager(cfg, APP_DIR)
            self._kaggle_batch_mgr = mgr
            mgr.on_log        = _on_log
            mgr.on_progress   = _on_progress
            mgr.on_batch_done = _on_batch_done
            mgr.on_finished   = _on_finished

            threading.Thread(
                target=mgr.run_pipeline,
                args=(pending_stems, story_p, prog, out_dir),
                daemon=True).start()

        def _do_stop():
            if self._kaggle_batch_mgr:
                self._kaggle_batch_mgr.stop()
            stop_btn.config(state="disabled")
            status_lbl.config(text="Đang dừng...", fg=C["yellow"])

        start_btn.config(command=_do_start)
        stop_btn.config(command=_do_stop)
        dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)


    def _open_kaggle_settings(self, on_saved=None):
        """Dialog cài đặt Kaggle Batch API. on_saved: callback gọi sau khi lưu."""
        dlg = tk.Toplevel(self.root)
        dlg.title("⚙  Cài đặt Kaggle Batch")
        dlg.geometry("500x380")
        dlg.resizable(False, False)
        dlg.configure(bg=C["panel"])
        dlg.transient(self.root)
        dlg.grab_set()
        cx = self.root.winfo_x() + (self.root.winfo_width()  - 500) // 2
        cy = self.root.winfo_y() + (self.root.winfo_height() - 380) // 2
        dlg.geometry(f"+{cx}+{cy}")

        tk.Label(dlg, text="⚙  Cài đặt Kaggle Batch Pipeline",
                 font=("Segoe UI", 12, "bold"),
                 bg=C["panel"], fg=C["accent"]).pack(pady=(16, 6))

        # ── Trạng thái kaggle.json ─────────────────────────────────────────
        kj_path = APP_DIR / "kaggle.json"
        kj_home = Path.home() / ".kaggle" / "kaggle.json"
        if kj_path.exists():
            kj_status = f"✅  Đọc từ:  {kj_path.name}  (cùng thư mục app)"
            kj_color  = C["green"]
        elif kj_home.exists():
            kj_status = f"✅  Đọc từ:  {kj_home}"
            kj_color  = C["green"]
        else:
            kj_status = (f"⚠  Không tìm thấy kaggle.json\n"
                         f"Đặt file vào: {kj_path}")
            kj_color  = C["accent"]

        tk.Label(dlg, text=kj_status, font=("Consolas", 8),
                 bg=C["panel"], fg=kj_color,
                 wraplength=460, justify="left").pack(padx=24, pady=(0, 4), anchor="w")

        if self.cfg.kaggle_username:
            tk.Label(dlg,
                     text=f"   Username: {self.cfg.kaggle_username}",
                     font=("Segoe UI", 8), bg=C["panel"], fg=C["dim"]).pack(anchor="w", padx=24)

        def _field(label, var, show=None):
            f = tk.Frame(dlg, bg=C["panel"])
            f.pack(fill="x", padx=24, pady=3)
            tk.Label(f, text=label, width=20, anchor="w",
                     bg=C["panel"], fg=C["text"],
                     font=("Segoe UI", 9)).pack(side="left")
            kw = {"show": show} if show else {}
            e = tk.Entry(f, textvariable=var, width=30,
                         bg=C["bg"], fg=C["text"],
                         insertbackground=C["text"],
                         relief="flat", font=("Consolas", 9), **kw)
            e.pack(side="left", padx=4)
            return e

        v_ds     = tk.StringVar(value=self.cfg.kaggle_dataset_slug)
        v_kernel = tk.StringVar(value=self.cfg.kaggle_kernel_slug)
        v_voice  = tk.StringVar(value=self.cfg.kaggle_batch_voice)
        v_bsize  = tk.IntVar(value=self.cfg.kaggle_batch_size)
        v_poll   = tk.IntVar(value=self.cfg.kaggle_poll_sec)

        _field("Dataset Slug:", v_ds)
        _field("Kernel Slug:",  v_kernel)

        # ── Voice ID: dropdown ────────────────────────────────────────────
        vf = tk.Frame(dlg, bg=C["panel"])
        vf.pack(fill="x", padx=24, pady=3)
        tk.Label(vf, text="Voice ID:", width=20, anchor="w",
                 bg=C["panel"], fg=C["text"],
                 font=("Segoe UI", 9)).pack(side="left")

        # Lấy danh sách giọng từ VieNeu (nếu đã load)
        try:
            raw_voices = self.worker._vieneu._tts.list_preset_voices()                          if self.worker._vieneu._tts else []
        except Exception:
            raw_voices = []

        voice_display = []
        voice_values  = []
        for desc, name in raw_voices:
            voice_display.append(desc)
            voice_values.append(name)

        # Tìm index giọng hiện tại
        cur_val = self.cfg.kaggle_batch_voice or ""
        cur_idx = voice_values.index(cur_val) if cur_val in voice_values else 0

        voice_cb = ttk.Combobox(vf, textvariable=v_voice,
                                values=voice_display if voice_display
                                       else [cur_val or "(chưa tải)"],
                                width=28, state="readonly",
                                font=("Segoe UI", 9))
        voice_cb.pack(side="left", padx=4)
        if voice_display:
            voice_cb.current(cur_idx)

        def _on_voice_select(event):
            idx = voice_cb.current()
            if 0 <= idx < len(voice_values):
                v_voice.set(voice_values[idx])
        voice_cb.bind("<<ComboboxSelected>>", _on_voice_select)

        # Nút tải danh sách nếu model chưa load
        if not raw_voices:
            def _load_voices():
                try:
                    self.worker._vieneu._ensure_loaded(
                        getattr(self.cfg, "vieneu_device", "cpu"))
                    nv = self.worker._vieneu._tts.list_preset_voices()
                    nd = [d for d, _ in nv]
                    nk = [n for _, n in nv]
                    voice_values.clear(); voice_values.extend(nk)
                    voice_cb.config(values=nd, state="readonly")
                    voice_cb.current(0)
                    v_voice.set(nk[0])
                    load_btn.config(state="disabled", text="✓ Đã tải")
                except Exception as e:
                    load_btn.config(text=f"Lỗi!")
            load_btn = self._btn(vf, "↻ Tải ds", _load_voices, C["card"])
            load_btn.pack(side="left", padx=4)

        fi = tk.Frame(dlg, bg=C["panel"])
        fi.pack(fill="x", padx=24, pady=3)
        tk.Label(fi, text="Batch size:", width=12, anchor="w",
                 bg=C["panel"], fg=C["text"],
                 font=("Segoe UI", 9)).pack(side="left")
        tk.Spinbox(fi, from_=1, to=50, textvariable=v_bsize, width=5,
                   bg=C["bg"], fg=C["text"], buttonbackground=C["card"],
                   relief="flat", font=("Consolas", 9)).pack(side="left", padx=4)
        tk.Label(fi, text="  Poll (giây):", anchor="w",
                 bg=C["panel"], fg=C["text"],
                 font=("Segoe UI", 9)).pack(side="left")
        tk.Spinbox(fi, from_=20, to=300, textvariable=v_poll, width=5,
                   bg=C["bg"], fg=C["text"], buttonbackground=C["card"],
                   relief="flat", font=("Consolas", 9)).pack(side="left", padx=4)

        tk.Label(dlg,
                 text="Kernel Slug = tên_kaggle/tên_notebook  (xem URL notebook trên Kaggle)",
                 font=("Segoe UI", 8), bg=C["panel"], fg=C["dim"]).pack(pady=(4, 0))

        def _save():
            self.cfg.kaggle_dataset_slug = v_ds.get().strip()
            self.cfg.kaggle_kernel_slug  = v_kernel.get().strip()
            self.cfg.kaggle_batch_voice  = v_voice.get().strip()
            self.cfg.kaggle_batch_size   = v_bsize.get()
            self.cfg.kaggle_poll_sec     = v_poll.get()
            self.mgr.save()
            dlg.destroy()
            if on_saved:
                self.root.after(100, on_saved)
            else:
                messagebox.showinfo("Đã lưu", "Cài đặt Kaggle Batch đã được lưu!")

        btn_r = tk.Frame(dlg, bg=C["panel"])
        btn_r.pack(pady=14)
        self._btn(btn_r, "💾 Lưu",  _save,       C["accent"]).pack(side="left", padx=6)
        self._btn(btn_r, "Hủy", dlg.destroy, C["border"]).pack(side="left", padx=6)


    def _shutdown_computer(self):
        import subprocess
        try:
            subprocess.run(["shutdown", "/s", "/t", "30"], check=True)
            messagebox.showinfo("Tat may", "May se tat sau 30 giay.\nGo 'shutdown /a' de huy.")
        except Exception as e:
            messagebox.showerror("Loi", f"Khong the tat may: {e}")

    def _cleanup_old_tmp(self):
        """Xóa folder tmp của các export đã hoàn thành."""
        import shutil
        for tmp in EXPORTS_DIR.glob("tmp_export_*"):
            if tmp.is_dir():
                try: shutil.rmtree(tmp, ignore_errors=True)
                except: pass

    # ═══════════════════════════════════════════════════════════════════════
    # EXPORT RESUME
    # ═══════════════════════════════════════════════════════════════════════

    def _check_pending_exports(self):
        """Khi khởi động: kiểm tra export bị dở, hỏi người dùng."""
        pending = self.export_mgr.list_all()
        if not pending:
            return
        # Bật nút tiếp tục xuất ngay
        self._resume_export_btn.config(state="normal")

        # BUG FIX: lọc trước các export hợp lệ, rồi hiện dialog TUẦN TỰ
        # (mỗi lần 1 cái) thay vì mở chồng nhiều Toplevel cùng lúc.
        queue: List[dict] = []
        for info in pending:
            eid = info.get("_id", "")
            if not Path(info.get("tmp_path", "")).exists():
                self.export_mgr.delete(eid)
                continue
            queue.append(info)

        def _show_next():
            if not queue:
                return
            info  = queue.pop(0)
            eid   = info.get("_id", "")
            done  = info.get("done_chunks", 0)
            total = info.get("total_chunks", 1)
            fname = Path(info.get("out_path", "")).name or "unknown"
            self._show_resume_dialog(eid, fname, f"{done/total*100:.0f}%",
                                     done, total, info, on_done=_show_next)

        _show_next()

    def _show_resume_dialog(self, eid, fname, pct, done, total, info, on_done=None):
        """Dialog 3 lựa chọn: Tiếp tục / Để sau / Xóa bỏ."""
        dlg = tk.Toplevel(self.root)
        dlg.title("Export bi gian doan")
        dlg.geometry("480x250")
        dlg.resizable(False, False)
        dlg.configure(bg=C["panel"])
        dlg.grab_set()
        dlg.transient(self.root)
        x = self.root.winfo_x() + (self.root.winfo_width()  - 480) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 250) // 2
        dlg.geometry(f"+{x}+{y}")

        tk.Label(dlg, text="⚠️  Phat hien Export Bi Gian Doan",
                 font=("Segoe UI", 12, "bold"), bg=C["panel"], fg=C["yellow"]).pack(pady=(18, 6))
        tk.Label(dlg, text=f"File: {fname}\nTien do: {done}/{total} chunk  ({pct} hoan thanh)",
                 font=("Segoe UI", 10), bg=C["panel"], fg=C["text"], justify="center").pack(pady=4)
        tk.Label(dlg, text="Ban muon lam gi voi file nay?",
                 font=("Segoe UI", 9), bg=C["panel"], fg=C["dim"]).pack(pady=(4, 8))

        btn_row = tk.Frame(dlg, bg=C["panel"])
        btn_row.pack(pady=6)

        def _resume():
            dlg.destroy()
            # BUG FIX: phải đưa cả remaining_jobs vào, không chỉ job hiện tại,
            # nếu không các job còn lại trong lô (batch) sẽ bị bỏ sót vĩnh viễn.
            current_job    = (info.get("files", []), info.get("out_path", ""))
            remaining_jobs = [(f, p) for f, p in info.get("remaining_jobs", [])]
            all_jobs       = [current_job] + remaining_jobs
            threading.Thread(
                target=self._export_jobs_worker,
                args=(all_jobs,
                      info.get("fmt", "wav"), info.get("delay_sec", 1.5), False),
                daemon=True).start()
            if on_done: on_done()

        def _later():
            dlg.destroy()
            self._resume_export_btn.config(state="normal")
            self.status_lbl.config(
                text=f"Export '{fname}' tam hoan – bam '▶ Tiep tuc xuat' de tiep tuc.")
            if on_done: on_done()

        def _discard():
            dlg.destroy()
            self.export_mgr.cleanup_tmp(eid)
            self.status_lbl.config(text="Da xoa export bi do.")
            if on_done: on_done()

        self._btn(btn_row, "▶ Tiep tuc ngay", _resume,  C["accent"] ).pack(side="left", padx=6)
        self._btn(btn_row, "⏰ De sau",         _later,   C["card"]  ).pack(side="left", padx=6)
        self._btn(btn_row, "🗑 Xoa bo",         _discard, C["border"]).pack(side="left", padx=6)

    # ═══════════════════════════════════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════════════════════════════════

    def _btn(self, parent, text, cmd, bg, **kw):
        """Factory tạo nút với style nhất quán."""
        return tk.Button(parent, text=text, command=cmd,
                         bg=bg, fg="white",
                         activebackground=C["accent"], activeforeground="white",
                         relief="flat", cursor="hand2",
                         font=("Segoe UI", 9), padx=10, pady=4, **kw)

    def _on_list_dbl(self, _=None):
        sel = self.listbox.curselection()
        if sel:
            self._stop()
            self._load_play_file(sel[0])

    def _on_close(self):
        if self._active_export_id:
            if not messagebox.askyesno("Dang xuat audio",
                    "Dang xuat audio! Thoat se luu tien do lai.\n"
                    "Lan sau mo app co the tiep tuc.\n\nBan chac muon thoat?"):
                return
        self._stop()
        self.mgr.save()
        self.root.destroy()


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    root = tk.Tk()
    try: root.iconbitmap(str(APP_DIR / "icon.ico"))
    except: pass
    VietTTSApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
