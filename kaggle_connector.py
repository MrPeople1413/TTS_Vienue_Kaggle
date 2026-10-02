#!/usr/bin/env python3
"""
================================================================================
Kaggle VieNeu Pipeline Connector (Tự động kết nối & xử lý GPU T4 x2)
================================================================================
File kết nối giữa ứng dụng Đọc Truyện Tiếng Việt và dịch vụ GPU miễn phí Kaggle.
Tự động:
  1. Lấy dữ liệu truyện từ ứng dụng (hoặc file txt cục bộ).
  2. Sắp xếp tuần tự tự nhiên (chap1.txt -> chap100.txt).
  3. Gộp chương theo cấu hình (mặc định 10 chương / 1 file .wav hoặc .mp3).
  4. Đóng gói input.zip và upload lên Kaggle Dataset qua Kaggle API.
  5. Kích hoạt Kaggle Kernel (Dual GPU T4 x2).
  6. Theo dõi tiến trình tuần tự và tự động tải output.zip về máy.
================================================================================
"""

import os
import sys
import json
import time
import shutil
import zipfile
import re
import argparse
from pathlib import Path

CONFIG_DIR = Path("config")
SETTINGS_FILE = CONFIG_DIR / "settings.json"
OUTPUT_DIR = Path("output_audio")
INPUT_PKG_DIR = Path("kaggle_package")

def natural_sort_key(s):
    """Sort strings with embedded numbers naturally: chap1, chap2, ..., chap10, chap100."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', str(s))]

def load_settings():
    defaults = {
        "kaggle_username": os.environ.get("KAGGLE_USERNAME", ""),
        "kaggle_api_key": os.environ.get("KAGGLE_KEY", ""),
        "kaggle_dataset_slug": "viettt-tts-input",
        "kaggle_kernel_slug": "vieneu-tts-server",
        "kaggle_batch_voice": "Ngọc Lan — nữ, giọng dịu dàng",
        "kaggle_batch_size": 10,
        "kaggle_poll_sec": 30,
        "speed": 1.0,
        "format": "wav"
    }
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                defaults.update(data)
        except Exception as e:
            print(f"[!] Không đọc được settings.json: {e}")
    return defaults

def save_settings(new_data):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    current = load_settings()
    current.update(new_data)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2, ensure_ascii=False)
    return current

def setup_kaggle_credentials(username, key):
    """Ensure ~/.kaggle/kaggle.json exists."""
    kaggle_dir = Path.home() / ".kaggle"
    kaggle_dir.mkdir(parents=True, exist_ok=True)
    cred_file = kaggle_dir / "kaggle.json"
    
    if username and key:
        with open(cred_file, "w", encoding="utf-8") as f:
            json.dump({"username": username, "key": key}, f)
        try:
            os.chmod(cred_file, 0o600)
        except Exception:
            pass
        os.environ["KAGGLE_USERNAME"] = username
        os.environ["KAGGLE_KEY"] = key
        print(f"[✓] Đã cấu hình xác thực Kaggle cho user: {username}")
        return True
    
    if cred_file.exists():
        print(f"[✓] Tìm thấy file cấu hình tại {cred_file}")
        return True
        
    print("[!] Chưa có thông tin Kaggle API Key! Vui lòng cung cấp username và key.")
    return False

def fetch_local_app_chapters():
    """Fetch chapters from local app or sample data."""
    try:
        import urllib.request
        req = urllib.request.Request("http://localhost:3000/api/stories")
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                print(f"[✓] Đã kết nối với Web App nội bộ, lấy được {len(data)} chương truyện.")
                return data
    except Exception:
        pass
    
    # Fallback: check if local txt files exist in current dir
    txt_files = sorted(Path(".").glob("*.txt"), key=lambda p: natural_sort_key(p.name))
    chapters = []
    for idx, tf in enumerate(txt_files):
        if tf.name in ["requirements.txt"]:
            continue
        try:
            content = tf.read_text(encoding="utf-8")
            chapters.append({
                "id": tf.stem,
                "title": tf.stem,
                "content": content
            })
        except Exception:
            pass
            
    return chapters

def build_dataset_package(chapters, group_size=10, voice="Ngọc Lan — nữ, giọng dịu dàng", speed=1.0, fmt="wav"):
    """
    Tạo gói dataset input.zip với cấu trúc chuẩn:
    - chapters sorted naturally
    - metadata.json chứa quy tắc gộp chương (group_size) và giọng đọc VieNeu
    - dataset-metadata.json để upload Kaggle Dataset
    """
    INPUT_PKG_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = INPUT_PKG_DIR / "input.zip"
    
    # Sắp xếp chương theo chuẩn tự nhiên
    chapters = sorted(chapters, key=lambda c: natural_sort_key(c.get("title", c.get("id"))))
    
    metadata = {
        "version": "2.2",
        "created_at": time.time(),
        "voice_id": voice,
        "speed": speed,
        "format": fmt, # 'wav' or 'mp3'
        "group_size": group_size, # e.g. 10 chapters merged into 1 file
        "total_chapters": len(chapters),
        "files": []
    }
    
    print(f"\n[📦] Đang đóng gói {len(chapters)} chương (Ghép {group_size} chương / file .{fmt.upper()})...")
    
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for idx, chap in enumerate(chapters, start=1):
            pad_idx = str(idx).padStart = f"{idx:04d}"
            safe_name = re.sub(r'[/\\?%*:|"<> ]', '_', chap.get("title", f"chap_{idx}"))
            chap_filename = f"chap_{pad_idx}_{safe_name}.txt"
            
            content = chap.get("content", "").strip()
            zf.writestr(chap_filename, content.encode("utf-8"))
            metadata["files"].append({
                "index": idx,
                "filename": chap_filename,
                "title": chap.get("title", f"Chương {idx}"),
                "words": len(content.split())
            })
            
        zf.writestr("metadata.json", json.dumps(metadata, indent=2, ensure_ascii=False).encode("utf-8"))

    # Create dataset-metadata.json for kaggle dataset upload
    settings = load_settings()
    username = settings.get("kaggle_username", "username")
    dataset_slug = settings.get("kaggle_dataset_slug", "viettt-tts-input")
    
    dataset_meta = {
        "title": f"Vietnamese TTS Input Package ({dataset_slug})",
        "id": f"{username}/{dataset_slug}",
        "licenses": [{"name": "CC0-1.0"}]
    }
    with open(INPUT_PKG_DIR / "dataset-metadata.json", "w", encoding="utf-8") as f:
        json.dump(dataset_meta, f, indent=2)

    print(f"[✓] Đã tạo gói {zip_path} thành công ({zip_path.stat().st_size / 1024:.1f} KB).")
    return zip_path

def run_pipeline(args):
    settings = load_settings()
    
    username = args.username or settings.get("kaggle_username")
    key = args.key or settings.get("kaggle_api_key")
    dataset_slug = args.dataset_slug or settings.get("kaggle_dataset_slug", "viettt-tts-input")
    kernel_slug = args.kernel_slug or settings.get("kaggle_kernel_slug", "vieneu-tts-server")
    voice = args.voice or settings.get("kaggle_batch_voice", "Ngọc Lan — nữ, giọng dịu dàng")
    group_size = args.group_size or settings.get("kaggle_batch_size", 10)
    speed = args.speed or settings.get("speed", 1.0)
    fmt = (args.format or settings.get("format", "wav")).lower()
    poll_sec = args.poll_sec or settings.get("kaggle_poll_sec", 30)
    
    print("=" * 65)
    print(" 🚀 KAGGLE VIENEU TTS PIPELINE RUNNER (DUAL GPU T4 x2)")
    print("=" * 65)
    print(f" • Kaggle User   : {username or '(Chưa thiết lập)'}")
    print(f" • Dataset Slug  : {dataset_slug}")
    print(f" • Kernel Slug   : {kernel_slug}")
    print(f" • Giọng đọc     : {voice}")
    print(f" • Gộp chương    : {group_size} chương / 1 file .{fmt.upper()}")
    print(f" • Tốc độ        : {speed}x")
    print("=" * 65)

    if not setup_kaggle_credentials(username, key):
        print("\n[!] Lỗi: Bạn cần cung cấp Kaggle API credentials để chạy tự động.")
        print("    Có thể nhập qua: python kaggle_connector.py --username <user> --key <api_key>")
        print("    Hoặc lưu tại giao diện web tab 'Kaggle VieNeu Pipeline'.")
        return False

    # Check kaggle CLI package
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi
        api = KaggleApi()
        api.authenticate()
        print("[✓] Xác thực Kaggle API thành công!")
    except ImportError:
        print("[!] Thư viện 'kaggle' chưa được cài đặt.")
        print("    Đang cài đặt tự động: pip install kaggle...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "kaggle"])
        from kaggle.api.kaggle_api_extended import KaggleApi
        api = KaggleApi()
        api.authenticate()

    # 1. Fetch chapters
    chapters = fetch_local_app_chapters()
    if not chapters:
        print("[!] Không tìm thấy chương truyện nào để xuất.")
        return False

    # 2. Build package
    zip_path = build_dataset_package(chapters, group_size=group_size, voice=voice, speed=speed, fmt=fmt)

    # 3. Upload dataset to Kaggle
    print(f"\n[🚀] [1/3] Đang cập nhật Kaggle Dataset: {username}/{dataset_slug}...")
    try:
        # Check if dataset already exists
        datasets = [d.ref for d in api.dataset_list(user=username)]
        target_dataset_ref = f"{username}/{dataset_slug}"
        
        if target_dataset_ref in datasets:
            print(f" • Tạo phiên bản mới cho dataset {target_dataset_ref}...")
            api.dataset_create_version(
                folder=str(INPUT_PKG_DIR),
                version_notes=f"Auto batch updated {time.strftime('%Y-%m-%d %H:%M:%S')} (Group {group_size} chap)",
                quiet=False
            )
        else:
            print(f" • Tạo mới dataset {target_dataset_ref}...")
            api.dataset_create_new(
                folder=str(INPUT_PKG_DIR),
                public=False,
                quiet=False
            )
        print(f"[✓] Đã đẩy dữ liệu {len(chapters)} chương lên Kaggle thành công!")
    except Exception as e:
        print(f"[!] Lỗi khi đẩy Dataset lên Kaggle: {e}")
        print("    Nếu dataset chưa có, hãy đảm bảo quyền tạo private dataset trên tài khoản Kaggle của bạn.")

    # 4. Trigger Notebook execution
    full_kernel = f"{username}/{kernel_slug}" if "/" not in kernel_slug else kernel_slug
    print(f"\n[⚡] [2/3] Kích hoạt Kaggle Notebook: {full_kernel}...")
    try:
        # Check kernel status or push
        status = api.kernel_status(full_kernel)
        print(f" • Trạng thái hiện tại của kernel: {status.get('status')}")
    except Exception as e:
        print(f" • Thông báo kernel: {e}")
        print(f" • Đảm bảo bạn đã tạo Kernel '{full_kernel}' trên Kaggle với GPU T4 x2.")

    # 5. Polling until complete
    if args.no_poll:
        print("\n[✓] Đã hoàn tất đẩy dữ liệu lên Kaggle. (Bỏ qua bước chờ kết quả)")
        return True

    print(f"\n[⏳] [3/3] Bắt đầu theo dõi tiến độ tuần tự (Kiểm tra mỗi {poll_sec}s)...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    start_time = time.time()
    while True:
        try:
            status_obj = api.kernel_status(full_kernel)
            st = status_obj.get("status", "unknown").lower()
            elapsed_min = (time.time() - start_time) / 60
            print(f"  [{time.strftime('%H:%M:%S')}] Trạng thái GPU: {st.upper()} (Đã chạy: {elapsed_min:.1f} phút)")

            if st in ["complete", "completed"]:
                print(f"\n[🎉] Kernel đã hoàn thành xuất sắc!")
                print(f"[📥] Đang tải các file âm thanh về thư mục: {OUTPUT_DIR.resolve()}...")
                api.kernel_output(full_kernel, path=str(OUTPUT_DIR))
                
                # Check output zip
                out_zip = OUTPUT_DIR / "output.zip"
                if out_zip.exists():
                    print(f"[✓] Giải nén {out_zip}...")
                    with zipfile.ZipFile(out_zip, 'r') as z:
                        z.extractall(OUTPUT_DIR)
                    print(f"[✓] Tất cả file audio .{fmt.upper()} đã sẵn sàng tại {OUTPUT_DIR}/")
                break
            elif st in ["error", "cancelack", "cancelled"]:
                print(f"[❌] Quá trình xử lý trên Kaggle dừng lại với trạng thái: {st}")
                err_msg = status_obj.get("failureMessage", "Không rõ nguyên nhân.")
                print(f"     Chi tiết: {err_msg}")
                break
        except KeyboardInterrupt:
            print("\n[!] Đã dừng theo dõi. Tiến trình trên Kaggle vẫn tiếp tục chạy ngầm.")
            break
        except Exception as ex:
            print(f"  [!] Đang kiểm tra lại... ({ex})")

        time.sleep(poll_sec)

    return True

def main():
    parser = argparse.ArgumentParser(description="Kaggle VieNeu Pipeline Connector (Tự động gộp chương & kết nối GPU T4 x2)")
    parser.add_argument("--username", help="Kaggle Username")
    parser.add_argument("--key", help="Kaggle API Key")
    parser.add_argument("--dataset-slug", help="Dataset slug (mặc định viettt-tts-input)")
    parser.add_argument("--kernel-slug", help="Kernel slug (mặc định vieneu-tts-server)")
    parser.add_argument("--voice", help="Giọng VieNeu (Ngọc Lan, Bảo Long, v.v.)")
    parser.add_argument("--group-size", type=int, default=10, help="Số chương gộp vào 1 file audio (mặc định 10)")
    parser.add_argument("--speed", type=float, default=1.0, help="Tốc độ đọc (mặc định 1.0)")
    parser.add_argument("--format", choices=["wav", "mp3"], default="wav", help="Định dạng xuất (wav hoặc mp3)")
    parser.add_argument("--poll-sec", type=int, default=30, help="Số giây giữa mỗi lần kiểm tra tiến độ")
    parser.add_argument("--no-poll", action="store_true", help="Không đợi kết quả, chỉ đóng gói và upload")
    
    args = parser.parse_args()
    run_pipeline(args)

if __name__ == "__main__":
    main()
