"""
kaggle_notebook_tts.py  –  chạy TRÊN KAGGLE (T4 x2)
=====================================================
Kiến trúc: 2 subprocess độc lập (không dùng multiprocessing module)
  → tránh hoàn toàn lỗi CUDA fork/spawn trong Jupyter kernel.

GPU0 subprocess → render nửa đầu → ghi WAV vào _wavs/
GPU1 subprocess → render nửa sau → ghi WAV vào _wavs/
Main process    → poll _wavs/ → pack ZIP theo batch_size

INPUT:  /kaggle/working/input.zip  hoặc  /kaggle/input/<slug>/input.zip
OUTPUT: /kaggle/working/output_<first>_<last>.zip
"""

import io, json, os, sys, subprocess, time, zipfile
from pathlib import Path
from threading import Thread, Event
from typing import Dict, List, Optional

# ═════════════════════════════════════════════════════════════════════════════
# PATHS
# ═════════════════════════════════════════════════════════════════════════════
WORKING    = Path("/kaggle/working")
INPUT_ROOT = Path("/kaggle/input")
MODELS_DIR = WORKING / "models"
STAGING    = WORKING / "_staging"
WAVS_DIR   = WORKING / "_wavs"       # workers ghi WAV vào đây

for d in (WORKING, MODELS_DIR, STAGING, WAVS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ═════════════════════════════════════════════════════════════════════════════
# TÌM input.zip
# ═════════════════════════════════════════════════════════════════════════════
_candidates = (sorted(INPUT_ROOT.rglob("input.zip")) +
               sorted(WORKING.glob("input.zip")))
if not _candidates:
    raise FileNotFoundError("Không tìm thấy input.zip!")

INPUT_ZIP = _candidates[0]
print(f"[NB] Input: {INPUT_ZIP}", flush=True)

with zipfile.ZipFile(INPUT_ZIP, "r") as zf:
    zf.extractall(STAGING)

META       = json.loads((STAGING / "metadata.json").read_text("utf-8"))
VOICE_ID   = META.get("voice_id", "")
SPEED      = float(META.get("speed", 1.0))
FILE_NAMES = META.get("files", [])
BATCH_SIZE = int(META.get("batch_size", 10))

print(f"[NB] {len(FILE_NAMES)} chap | voice={VOICE_ID!r} | "
      f"speed={SPEED} | batch_size={BATCH_SIZE}", flush=True)

STEMS: List[str] = []
TEXTS: Dict[str, str] = {}
for fname in FILE_NAMES:
    stem = Path(fname).stem
    STEMS.append(stem)
    p = STAGING / fname
    TEXTS[stem] = p.read_text("utf-8", errors="replace").strip() if p.exists() else ""
    if not p.exists():
        print(f"[NB] ⚠ Không tìm thấy: {fname}", flush=True)

# ═════════════════════════════════════════════════════════════════════════════
# CÀI THƯ VIỆN
# ═════════════════════════════════════════════════════════════════════════════
def _pip(*pkgs):
    subprocess.check_call([sys.executable, "-m", "pip", "install",
                           "--quiet", "--no-warn-script-location", *pkgs])

try:
    from vieneu import Vieneu
    print("[NB] VieNeu đã cài sẵn.", flush=True)
except ImportError:
    print("[NB] Đang cài VieNeu...", flush=True)
    _pip("vieneu")

try:
    import soundfile
except ImportError:
    _pip("soundfile")

# ═════════════════════════════════════════════════════════════════════════════
# DETECT GPU
# ═════════════════════════════════════════════════════════════════════════════
try:
    import torch
    N_GPU = torch.cuda.device_count()
    print(f"[NB] {N_GPU} GPU(s) detected.", flush=True)
    for i in range(N_GPU):
        print(f"  GPU {i}: {torch.cuda.get_device_name(i)}", flush=True)
    del torch   # giải phóng, worker sẽ tự init
except Exception:
    N_GPU = 0
    print("[NB] Không có GPU – chạy CPU.", flush=True)

# ═════════════════════════════════════════════════════════════════════════════
# VIẾT WORKER SCRIPT RA FILE
# Đây là cách duy nhất để spawn subprocess hoạt động trong Jupyter
# ═════════════════════════════════════════════════════════════════════════════
WORKER_SCRIPT = WORKING / "_tts_worker.py"
WORKER_SCRIPT.write_text(r'''"""
_tts_worker.py  –  subprocess TTS worker
Chạy bởi main script, KHÔNG chạy trực tiếp.
Args: --gpu <id>  --stems <s1,s2,...>  --staging <dir>  --out <dir>
      --voice <id>  --speed <float>  --models <dir>  --n_gpu <int>
"""
import argparse, io, json, os, sys, time
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--gpu",     type=int,   required=True)
ap.add_argument("--stems",   type=str,   required=True)
ap.add_argument("--staging", type=str,   required=True)
ap.add_argument("--out",     type=str,   required=True)
ap.add_argument("--voice",   type=str,   default="")
ap.add_argument("--speed",   type=float, default=1.0)
ap.add_argument("--models",  type=str,   default="")
ap.add_argument("--n_gpu",   type=int,   default=0)
args = ap.parse_args()

GPU_ID   = args.gpu
STEMS    = [s for s in args.stems.split(",") if s]
STAGING  = Path(args.staging)
OUT_DIR  = Path(args.out)
VOICE_ID = args.voice
SPEED    = args.speed
N_GPU    = args.n_gpu
LABEL    = f"GPU{GPU_ID}" if GPU_ID >= 0 else "CPU"

# Set CUDA trước khi import torch/vieneu
if GPU_ID >= 0:
    os.environ["CUDA_VISIBLE_DEVICES"] = str(GPU_ID)
else:
    os.environ["CUDA_VISIBLE_DEVICES"] = ""

if args.models:
    os.environ["HF_HOME"]               = args.models
    os.environ["HUGGINGFACE_HUB_CACHE"] = args.models
    os.environ["TRANSFORMERS_CACHE"]    = args.models

def _pip(*pkgs):
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install",
                           "--quiet", "--no-warn-script-location", *pkgs])

try:
    from vieneu import Vieneu
except ImportError:
    _pip("vieneu"); from vieneu import Vieneu

try:
    import soundfile as sf
except ImportError:
    _pip("soundfile"); import soundfile as sf

import numpy as np

print(f"[{LABEL}] Khởi động VieNeu...", flush=True)
if GPU_ID >= 0 and N_GPU > 0:
    tts = Vieneu(backbone_kwargs={"n_gpu_layers": 99})
else:
    from multiprocessing import cpu_count
    tts = Vieneu(backbone_kwargs={"n_threads": max(2, cpu_count() // 2)})
print(f"[{LABEL}] VieNeu sẵn sàng. {len(STEMS)} chap.", flush=True)

voice_data = None
if VOICE_ID:
    try:
        voice_data = tts.get_preset_voice(VOICE_ID)
        print(f"[{LABEL}] Voice '{VOICE_ID}' đã load.", flush=True)
    except Exception as ve:
        print(f"[{LABEL}] Voice lỗi: {ve} → dùng mặc định.", flush=True)

for stem in STEMS:
    out_wav = OUT_DIR / f"{stem}.wav"
    if out_wav.exists() and out_wav.stat().st_size > 0:
        print(f"[{LABEL}] ↷ {stem} đã có, bỏ qua.", flush=True)
        continue

    txt_file = STAGING / f"{stem}.txt"
    text = txt_file.read_text("utf-8", errors="replace").strip() if txt_file.exists() else ""
    if not text:
        print(f"[{LABEL}] ⚠ {stem}: text rỗng.", flush=True)
        continue

    try:
        kwargs = {}
        if voice_data is not None:
            kwargs["voice"] = voice_data

        result = tts.infer(text=text, speed=SPEED, **kwargs)

        if isinstance(result, np.ndarray):
            audio, sr = result, 24000
        elif hasattr(result, "audio"):
            audio = result.audio
            sr    = getattr(result, "sample_rate", 24000)
        else:
            audio, sr = np.array(result), 24000

        buf = io.BytesIO()
        sf.write(buf, audio, samplerate=sr, format="WAV", subtype="PCM_16")
        out_wav.write_bytes(buf.getvalue())
        print(f"[{LABEL}] ✓ {stem}  ({out_wav.stat().st_size//1024} KB)", flush=True)

    except Exception as e:
        print(f"[{LABEL}] ✗ {stem}: {e}", flush=True)

print(f"[{LABEL}] Xong.", flush=True)
''', encoding="utf-8")

print(f"[NB] Worker script: {WORKER_SCRIPT}", flush=True)

# ═════════════════════════════════════════════════════════════════════════════
# CHIA STEMS CHO TỪNG GPU
# ═════════════════════════════════════════════════════════════════════════════
N_WORKERS = min(max(N_GPU, 1), 2)

if N_WORKERS == 2:
    # GPU0: index chẵn, GPU1: index lẻ → phân bố đều
    splits = [
        [s for i, s in enumerate(STEMS) if i % 2 == 0],  # GPU0
        [s for i, s in enumerate(STEMS) if i % 2 == 1],  # GPU1
    ]
else:
    splits = [STEMS]

print(f"[NB] Phân chia: {[len(s) for s in splits]} chap cho {N_WORKERS} worker(s).",
      flush=True)

# ═════════════════════════════════════════════════════════════════════════════
# KHỞI ĐỘNG SUBPROCESS
# ═════════════════════════════════════════════════════════════════════════════
def _stream_output(proc, label):
    """Stream stdout của subprocess ra Jupyter cell output."""
    for line in proc.stdout:
        print(line, end="", flush=True)

procs = []
threads = []
for gid, stems_for_gpu in enumerate(splits):
    if not stems_for_gpu:
        continue
    actual_gpu = gid if N_GPU > 0 else -1
    cmd = [
        sys.executable, str(WORKER_SCRIPT),
        "--gpu",     str(actual_gpu),
        "--stems",   ",".join(stems_for_gpu),
        "--staging", str(STAGING),
        "--out",     str(WAVS_DIR),
        "--voice",   VOICE_ID,
        "--speed",   str(SPEED),
        "--models",  str(MODELS_DIR),
        "--n_gpu",   str(N_GPU),
    ]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT,
                         text=True, bufsize=1)
    t = Thread(target=_stream_output, args=(p, f"GPU{actual_gpu}"), daemon=True)
    t.start()
    procs.append(p)
    threads.append(t)
    print(f"[NB] Worker GPU{actual_gpu} PID={p.pid} đã khởi động.", flush=True)

# ═════════════════════════════════════════════════════════════════════════════
# CLEANUP THREAD
# ═════════════════════════════════════════════════════════════════════════════
_cleanup_stop = Event()

def _cleanup_loop():
    known: set = set()
    while not _cleanup_stop.is_set():
        time.sleep(60)
        for ack_f in sorted(INPUT_ROOT.rglob("cleanup_ack.json"),
                            key=lambda p: p.stat().st_mtime, reverse=True)[:1]:
            try:
                ack = json.loads(ack_f.read_text("utf-8"))
                for zname in ack.get("downloaded_zips", []):
                    if zname in known:
                        continue
                    t = WORKING / zname
                    if t.exists():
                        t.unlink()
                        known.add(zname)
                        print(f"[NB][Cleanup] Xóa {zname}", flush=True)
            except Exception as e:
                print(f"[NB][Cleanup] Lỗi: {e}", flush=True)

Thread(target=_cleanup_loop, daemon=True).start()

# ═════════════════════════════════════════════════════════════════════════════
# MAIN: POLL WAVs → PACK ZIPs
# ═════════════════════════════════════════════════════════════════════════════
output_batches = [STEMS[i:i+BATCH_SIZE]
                  for i in range(0, len(STEMS), BATCH_SIZE)]
packed_batches: set = set()
t0 = time.time()

def _pack_batch(batch):
    zip_name = f"output_{batch[0]}_{batch[-1]}.zip"
    zip_path = WORKING / zip_name
    n_ok = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
        for stem in batch:
            wav = WAVS_DIR / f"{stem}.wav"
            if wav.exists() and wav.stat().st_size > 0:
                zf.write(wav, f"{stem}.wav")
                n_ok += 1
            else:
                print(f"[NB] ⚠ {stem}: không có WAV.", flush=True)
    mb = zip_path.stat().st_size / 1024 / 1024
    print(f"[NB] ✅ {zip_name}  ({n_ok}/{len(batch)} chap, {mb:.1f} MB)",
          flush=True)

def _all_done(batch):
    return all((WAVS_DIR / f"{s}.wav").exists() and
               (WAVS_DIR / f"{s}.wav").stat().st_size > 0
               for s in batch)

print(f"[NB] Đang render {len(STEMS)} chap...", flush=True)

while True:
    # Pack các batch đã xong
    for batch in output_batches:
        key = f"{batch[0]}_{batch[-1]}"
        if key not in packed_batches and _all_done(batch):
            _pack_batch(batch)
            packed_batches.add(key)

    # Kiểm tra tất cả xong chưa
    done_count = sum(1 for s in STEMS
                     if (WAVS_DIR / f"{s}.wav").exists() and
                        (WAVS_DIR / f"{s}.wav").stat().st_size > 0)

    all_procs_done = all(p.poll() is not None for p in procs)

    elapsed = time.time() - t0
    print(f"[NB] Tiến độ: {done_count}/{len(STEMS)} chap | "
          f"{elapsed/60:.1f} phút", flush=True)

    if done_count >= len(STEMS) or (all_procs_done and done_count == done_count):
        if all_procs_done:
            break

    time.sleep(20)

# Pack batch cuối còn sót
for batch in output_batches:
    key = f"{batch[0]}_{batch[-1]}"
    if key not in packed_batches and _all_done(batch):
        _pack_batch(batch)
        packed_batches.add(key)

# Dọn dẹp
for t in threads:
    t.join(timeout=5)
_cleanup_stop.set()
WORKER_SCRIPT.unlink(missing_ok=True)

# Tổng kết
out_zips = sorted(WORKING.glob("output_*.zip"))
elapsed  = time.time() - t0
print(f"\n[NB] {'═'*46}", flush=True)
print(f"[NB] ✅ HOÀN THÀNH! {len(STEMS)} chap | {elapsed/60:.1f} phút", flush=True)
for z in out_zips:
    print(f"  {z.name}  ({z.stat().st_size/1024/1024:.1f} MB)", flush=True)
print(f"[NB] {'═'*46}", flush=True)
