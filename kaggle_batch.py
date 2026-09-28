"""
kaggle_batch.py  –  KaggleBatchManager (CLI-based, không dùng Python API)
=========================================================================
Dùng kaggle CLI (subprocess) thay vì Python SDK để tránh xung đột
protobuf / import errors với các phiên bản kaggle package khác nhau.

Yêu cầu: pip install kaggle  (chỉ cần CLI, không cần import Python API)
"""

from __future__ import annotations

import json, os, shutil, subprocess, threading, time, zipfile
from pathlib import Path
from typing import Callable, List, Optional


# ── Kiểm tra kaggle CLI có sẵn không ─────────────────────────────────────────
def _kaggle_cli_ok() -> bool:
    try:
        r = subprocess.run(["kaggle", "--version"],
                           capture_output=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False

KAGGLE_BATCH_OK = True   # luôn True, kiểm tra thật lúc chạy


# ═════════════════════════════════════════════════════════════════════════════
# CONFIG
# ═════════════════════════════════════════════════════════════════════════════

class KaggleBatchConfig:
    def __init__(
        self,
        username      : str   = "",
        api_key       : str   = "",
        dataset_slug  : str   = "viettt-tts-input",
        kernel_slug   : str   = "",
        batch_size    : int   = 10,
        poll_sec      : int   = 40,
        voice_id      : str   = "",
        speed         : float = 1.0,
    ):
        self.username     = username
        self.api_key      = api_key
        self.dataset_slug = dataset_slug
        self.kernel_slug  = kernel_slug
        self.batch_size   = batch_size
        self.poll_sec     = poll_sec
        self.voice_id     = voice_id
        self.speed        = speed


# ═════════════════════════════════════════════════════════════════════════════
# MANAGER
# ═════════════════════════════════════════════════════════════════════════════

class KaggleBatchManager:
    _STAGING = "_kaggle_staging"

    def __init__(self, cfg: KaggleBatchConfig, work_dir: Path):
        self.cfg      = cfg
        self.work_dir = work_dir
        self._stop    = threading.Event()

        self.on_log:        Optional[Callable[[str], None]]                   = None
        self.on_progress:   Optional[Callable[[str, float], None]]            = None
        self.on_batch_done: Optional[Callable[[List[str], List[Path]], None]] = None
        self.on_finished:   Optional[Callable[[bool, str], None]]             = None

    # ── Public ───────────────────────────────────────────────────────────────

    def run_pipeline(
        self,
        pending_stems: List[str],
        txt_folder:    Path,
        export_progress,
        wav_out_dir:   Path,
    ):
        self._stop.clear()
        wav_out_dir.mkdir(parents=True, exist_ok=True)
        staging = self.work_dir / self._STAGING
        staging.mkdir(exist_ok=True)

        try:
            self._validate()
            if not pending_stems:
                raise RuntimeError("Không có chap nào cần xử lý.")

            # Ghi kaggle.json tạm để CLI dùng
            self._setup_kaggle_json()

            # 1. Pack input.zip
            input_zip = staging / "input.zip"
            self._pack_input_zip(pending_stems, txt_folder, input_zip, staging)
            if self._stop.is_set(): return

            # 2. Upload dataset
            self._upload_dataset(input_zip, staging)
            if self._stop.is_set(): return

            # 3. Trigger notebook
            self._trigger_notebook(staging)
            if self._stop.is_set(): return

            # 4. Chờ notebook spin-up
            self._log("Chờ notebook khởi động (~120 giây)...")
            self._progress("Đợi Kaggle khởi động...", 0.20)
            self._interruptible_sleep(120)
            if self._stop.is_set(): return

            # 5. Poll + Download
            self._poll_and_download(pending_stems, export_progress,
                                    wav_out_dir, staging)

        except Exception as exc:
            msg = f"Pipeline lỗi: {exc}"
            self._log(msg)
            if self.on_finished:
                self.on_finished(False, msg)

    def stop(self):
        self._stop.set()

    # ── Setup kaggle.json cho CLI ─────────────────────────────────────────────

    def _setup_kaggle_json(self):
        """
        Ghi credentials vào ~/.kaggle/kaggle.json để CLI dùng.
        Ưu tiên: nếu file đã tồn tại và có đủ thông tin thì giữ nguyên.
        """
        kj_dir  = Path.home() / ".kaggle"
        kj_path = kj_dir / "kaggle.json"
        kj_dir.mkdir(exist_ok=True)

        # Đọc credentials từ cfg (đã load từ kaggle.json cùng thư mục app)
        if self.cfg.username and self.cfg.api_key:
            data = {"username": self.cfg.username, "key": self.cfg.api_key}
            kj_path.write_text(json.dumps(data), "utf-8")
            try:
                kj_path.chmod(0o600)
            except Exception:
                pass
            self._log(f"  Đã ghi credentials vào {kj_path}")

    # ── Step 1: Pack input.zip ────────────────────────────────────────────────

    def _pack_input_zip(self, stems, txt_folder, out_zip, staging):
        self._log(f"Đóng gói {len(stems)} chap → input.zip ...")
        self._progress(f"Đóng gói {len(stems)} chap...", 0.03)

        metadata = {
            "voice_id"  : self.cfg.voice_id,
            "speed"     : self.cfg.speed,
            "batch_size": self.cfg.batch_size,
            "files"     : [f"{s}.txt" for s in stems],
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        missing = []
        with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            zf.writestr("metadata.json",
                        json.dumps(metadata, ensure_ascii=False, indent=2))
            for stem in stems:
                p = txt_folder / f"{stem}.txt"
                if p.exists():
                    zf.write(p, f"{stem}.txt")
                else:
                    missing.append(stem)
        if missing:
            self._log(f"  ⚠ Thiếu {len(missing)} file: {missing[:3]}")
        mb = out_zip.stat().st_size / 1024 / 1024
        self._log(f"  input.zip ({mb:.2f} MB) xong.")
        self._progress(f"input.zip ({mb:.1f} MB)", 0.08)

        # Copy vào upload/
        up = staging / "upload"
        up.mkdir(exist_ok=True)
        shutil.copy2(out_zip, up / "input.zip")

    # ── Step 2: Upload dataset ────────────────────────────────────────────────

    def _upload_dataset(self, input_zip: Path, staging: Path):
        self._log("Upload lên Kaggle Dataset ...")
        self._progress("Uploading...", 0.10)

        up_dir = staging / "upload"
        up_dir.mkdir(exist_ok=True)
        ds_id = f"{self.cfg.username}/{self.cfg.dataset_slug}"

        # Tạo dataset-metadata.json
        (up_dir / "dataset-metadata.json").write_text(
            json.dumps({
                "title"   : "VietTTS TTS Input",
                "id"      : ds_id,
                "licenses": [{"name": "CC0-1.0"}],
            }, indent=2), "utf-8")

        env = self._cli_env()

        # Thử create new trước
        r = subprocess.run(
            ["kaggle", "datasets", "create", "-p", str(up_dir),
             "--dir-mode", "zip"],
            capture_output=True, text=True, env=env, timeout=300)

        if r.returncode == 0:
            self._log("  Dataset mới đã tạo.")
        elif "already exists" in (r.stdout + r.stderr).lower() or \
             "403" in r.stderr or "409" in r.stderr:
            self._log("  Dataset đã tồn tại → tạo version mới...")
            r2 = subprocess.run(
                ["kaggle", "datasets", "version", "-p", str(up_dir),
                 "-m", f"batch_{time.strftime('%Y%m%d_%H%M%S')}",
                 "--dir-mode", "zip", "--delete-old-versions"],
                capture_output=True, text=True, env=env, timeout=300)
            if r2.returncode != 0:
                raise RuntimeError(f"Upload version lỗi: {r2.stderr[:200]}")
            self._log("  Version mới đã upload.")
        else:
            raise RuntimeError(f"Upload dataset lỗi:\n{r.stderr[:300]}")

        self._progress("Upload xong – chờ Kaggle xử lý...", 0.15)
        self._log("Chờ Kaggle xử lý dataset (~90 giây)...")
        self._interruptible_sleep(90)
        self._progress("Dataset sẵn sàng.", 0.18)

    # ── Step 3: Trigger Notebook ──────────────────────────────────────────────

    def _trigger_notebook(self, staging: Path):
        self._log(f"Kích hoạt notebook: {self.cfg.kernel_slug} ...")
        self._progress("Kích hoạt notebook...", 0.19)
        env  = self._cli_env()
        user, kname = self.cfg.kernel_slug.split("/", 1)

        pull_dir = staging / "_kernel_pull"
        if pull_dir.exists():
            shutil.rmtree(pull_dir)
        pull_dir.mkdir(parents=True)

        # ── Pull kernel metadata ──────────────────────────────────────────
        r_pull = subprocess.run(
            ["kaggle", "kernels", "pull", self.cfg.kernel_slug,
             "-p", str(pull_dir), "--metadata"],
            capture_output=True, text=True, env=env, timeout=60)

        self._log(f"  Pull: {(r_pull.stdout + r_pull.stderr).strip()[:200]}")

        meta_f = pull_dir / "kernel-metadata.json"

        if r_pull.returncode != 0 or not meta_f.exists():
            # Draft notebook chưa có committed version → tự tạo metadata
            self._log("  Pull thất bại → tự tạo metadata...")
            nb_files = list(pull_dir.glob("*.ipynb"))
            if not nb_files:
                raise RuntimeError(
                    f"Notebook chưa có committed version.\n\n"
                    f"Làm theo các bước:\n"
                    f"1. Mở notebook trên Kaggle\n"
                    f"2. Bấm 'Save & Run All' để tạo version đầu tiên\n"
                    f"3. Chờ chạy xong rồi bấm ▶ Bắt đầu lại")
            meta = {
                "id"              : self.cfg.kernel_slug,
                "title"           : f"{kname}_{time.strftime('%m%d_%H%M')}",
                "code_file"       : nb_files[0].name,
                "language"        : "python",
                "kernel_type"     : "notebook",
                "is_private"      : True,
                "enable_gpu"      : True,
                "enable_tpu"      : False,
                "enable_internet" : True,
                "dataset_sources" : [f"{self.cfg.username}/{self.cfg.dataset_slug}"],
                "competition_sources": [],
                "kernel_sources"  : [],
            }
            meta_f.write_text(json.dumps(meta, indent=2), "utf-8")
        else:
            meta = json.loads(meta_f.read_text("utf-8"))
            ds_ref  = f"{self.cfg.username}/{self.cfg.dataset_slug}"
            sources = meta.get("dataset_sources", [])
            if ds_ref not in sources:
                sources.append(ds_ref)
                meta["dataset_sources"] = sources
            meta["title"] = f"{kname}_{time.strftime('%m%d_%H%M')}"
            meta_f.write_text(json.dumps(meta, indent=2), "utf-8")

        # ── Push để trigger run ───────────────────────────────────────────
        r_push = subprocess.run(
            ["kaggle", "kernels", "push", "-p", str(pull_dir)],
            capture_output=True, text=True, env=env, timeout=60)

        out = (r_push.stdout + r_push.stderr).strip()
        self._log(f"  Push ({r_push.returncode}): {out[:300]}")

        if r_push.returncode != 0:
            raise RuntimeError(
                f"Push kernel lỗi:\n{out[:400]}")

        self._log("  Notebook đã được kích hoạt!")
        self._progress("Notebook đang chạy...", 0.20)
    # ── Step 4-9: Poll → Download → Cleanup ──────────────────────────────────

    def _poll_and_download(self, all_stems, export_progress,
                           wav_out_dir, staging):
        env         = self._cli_env()
        user, kname = self.cfg.kernel_slug.split("/", 1)
        total       = len(all_stems)
        dl_dir      = wav_out_dir / "_batch_zips"
        dl_dir.mkdir(exist_ok=True)
        downloaded_zips: List[str] = []
        done_stems: set = set()
        poll_n = 0
        last_status = ""

        self._log(f"Polling – {total} chap cần tải, interval={self.cfg.poll_sec}s")

        while not self._stop.is_set():
            poll_n += 1
            pct = 0.22 + 0.75 * len(done_stems) / max(total, 1)
            self._progress(f"[Poll #{poll_n}] {len(done_stems)}/{total} chap", pct)

            # Lấy kernel status
            cur_status = self._get_kernel_status(env)
            if cur_status and cur_status != last_status:
                self._log(f"  Kernel: {cur_status}")
                last_status = cur_status

            # Download output files
            try:
                r = subprocess.run(
                    ["kaggle", "kernels", "output",
                     self.cfg.kernel_slug,
                     "-p", str(dl_dir), "--quiet"],
                    capture_output=True, text=True,
                    env=env, timeout=600)

                # Tìm các file output_*.zip mới
                for zp in sorted(dl_dir.glob("output_*.zip")):
                    fname = zp.name
                    if fname in downloaded_zips:
                        continue
                    if not zp.exists() or zp.stat().st_size == 0:
                        continue

                    self._log(f"  ↓ Tải {fname} ({zp.stat().st_size//1024} KB)")
                    batch_stems = _extract_zip(zp, wav_out_dir)
                    downloaded_zips.append(fname)
                    done_stems.update(batch_stems)

                    # Mark done
                    if export_progress and batch_stems:
                        for stem in batch_stems:
                            wp = wav_out_dir / f"{stem}.wav"
                            if wp.exists():
                                export_progress.set_status(
                                    stem, "done", output=str(wp))

                    # Callback UI
                    if self.on_batch_done:
                        wavs = [wav_out_dir / f"{s}.wav"
                                for s in batch_stems
                                if (wav_out_dir / f"{s}.wav").exists()]
                        self.on_batch_done(batch_stems, wavs)

                    mb = zp.stat().st_size / 1024 / 1024
                    self._log(f"  ✓ {fname} – {len(batch_stems)} chap, {mb:.1f} MB")

                    # Gửi cleanup ack
                    self._upload_cleanup_ack(downloaded_zips, staging, env)

            except Exception as e:
                self._log(f"  Poll lỗi: {e}")

            # Kiểm tra xong chưa
            if done_stems >= set(all_stems):
                self._log(f"✅ {total} chap đã tải về!")
                self._progress("Hoàn thành!", 1.0)
                if self.on_finished:
                    self.on_finished(True, f"Hoàn thành {total} chap!")
                return

            if cur_status in ("complete", "error",
                              "cancelAcknowledged", "cancelled"):
                missing = set(all_stems) - done_stems
                msg = (f"Kernel kết thúc ({cur_status}), "
                       f"còn {len(missing)} chap chưa tải.")
                self._log(msg)
                if self.on_finished:
                    self.on_finished(len(missing) == 0, msg)
                return

            self._interruptible_sleep(self.cfg.poll_sec)

        self._log("Đã dừng.")
        if self.on_finished:
            self.on_finished(False,
                f"Đã dừng. Đã tải {len(done_stems)}/{total} chap.")

    # ── Cleanup ACK ───────────────────────────────────────────────────────────

    def _upload_cleanup_ack(self, downloaded_zips, staging, env):
        try:
            ack_dir = staging / "_cleanup"
            if ack_dir.exists():
                shutil.rmtree(ack_dir)
            ack_dir.mkdir()

            src = staging / "upload" / "input.zip"
            if src.exists():
                shutil.copy2(src, ack_dir / "input.zip")

            (ack_dir / "cleanup_ack.json").write_text(
                json.dumps({"downloaded_zips": downloaded_zips,
                            "ts": time.strftime("%Y-%m-%dT%H:%M:%S")},
                           ensure_ascii=False, indent=2), "utf-8")

            ds_id = f"{self.cfg.username}/{self.cfg.dataset_slug}"
            (ack_dir / "dataset-metadata.json").write_text(
                json.dumps({"title": "VietTTS TTS Input",
                            "id"   : ds_id,
                            "licenses": [{"name": "CC0-1.0"}]},
                           indent=2), "utf-8")

            subprocess.run(
                ["kaggle", "datasets", "version", "-p", str(ack_dir),
                 "-m", "cleanup_ack", "--dir-mode", "zip"],
                capture_output=True, text=True, env=env, timeout=120)
            self._log(f"  Cleanup ack đã gửi.")
        except Exception as e:
            self._log(f"  Cleanup ack lỗi: {e}")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_kernel_status(self, env) -> str:
        try:
            r = subprocess.run(
                ["kaggle", "kernels", "status", self.cfg.kernel_slug],
                capture_output=True, text=True, env=env, timeout=30)
            # Output: "username/kernel-name has status "running""
            import re
            m = re.search(r'status "(\w+)"', r.stdout)
            return m.group(1) if m else ""
        except Exception:
            return ""

    def _validate(self):
        if not _kaggle_cli_ok():
            raise RuntimeError(
                "Không tìm thấy lệnh 'kaggle' trong PATH.\n"
                "Chạy:  py -3.10 -m pip install kaggle\n"
                "Rồi khởi động lại app.")
        if not self.cfg.username:
            raise RuntimeError("Kaggle Username trống – kiểm tra kaggle.json.")
        if not self.cfg.api_key:
            raise RuntimeError("Kaggle API Key trống – kiểm tra kaggle.json.")
        if not self.cfg.kernel_slug or "/" not in self.cfg.kernel_slug:
            raise RuntimeError(
                "Kernel Slug không hợp lệ.\nVí dụ: myuser/vieneu-tts-batch")

    def _cli_env(self) -> dict:
        env = os.environ.copy()
        env["KAGGLE_USERNAME"] = self.cfg.username
        env["KAGGLE_KEY"]      = self.cfg.api_key
        return env

    def _log(self, msg: str):
        print(f"[KaggleBatch] {msg}", flush=True)
        if self.on_log:
            self.on_log(msg)

    def _progress(self, msg: str, pct: float):
        if self.on_progress:
            self.on_progress(msg, pct)

    def _interruptible_sleep(self, seconds: int):
        for _ in range(seconds):
            if self._stop.is_set():
                return
            time.sleep(1)


# ── Module helper ─────────────────────────────────────────────────────────────

def _extract_zip(zip_path: Path, wav_out_dir: Path) -> List[str]:
    stems = []
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for name in zf.namelist():
                if name.lower().endswith(".wav"):
                    stem   = Path(name).stem
                    target = wav_out_dir / f"{stem}.wav"
                    target.write_bytes(zf.read(name))
                    stems.append(stem)
    except Exception as e:
        print(f"[KaggleBatch] Extract lỗi: {e}")
    return stems


def ensure_kaggle_sdk() -> bool:
    return _kaggle_cli_ok()
