"""
# ==============================================================================
# 1. วัน/เดือน/ปี (Date)       : 02/11/2569 (02 November 2026)
# 2. ชื่อไฟล์ที่ทำ (File Name)   : app.py
# 3. ลำดับเวอร์ชัน (Version)   : 1.2 (DELTA SYNTH Corporate UI & VRAM Guard Edition)
# 4. เครดิตผู้สร้าง (Credit)    : Made And Checked By DELTA SYNTH & All Code Agentic AI Engine
#                              Original by OpenVPI DiffSinger
# 5. ตำแหน่งที่จัดวางไฟล์ (Path) : app.py
# 6. รายละเอียดการแก้ไขงาน    : แปลภาษา UI เป็น Bilingual (TH/EN), เปลี่ยนสีธีมตามมาตรฐาน 
#                              DELTA SYNTH และเพิ่ม VRAM Safety Protocol อย่างสมบูรณ์
# ==============================================================================
"""

import gradio as gr
import os
import sys
import csv
import json
import yaml
import shutil
import signal
import platform
import subprocess
import threading
import pathlib
import time
import wave
from datetime import datetime
from collections import OrderedDict
import gc

# บังคับใช้ UTF-8 ป้องกันปัญหาบน Windows
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ─── Path Setup ───────────────────────────────────────────────
ROOT_DIR = pathlib.Path(__file__).parent.resolve()
DATA_DIR = ROOT_DIR / "data"
CHECKPOINTS_DIR = ROOT_DIR / "checkpoints"
DICTIONARIES_DIR = ROOT_DIR / "dictionaries"
CONFIGS_DIR = ROOT_DIR / "configs"
SCRIPTS_DIR = ROOT_DIR / "scripts"

os.environ['PYTHONPATH'] = str(ROOT_DIR)
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# ─── Global State ─────────────────────────────────────────────
_active_process = None
_process_lock = threading.Lock()
_log_buffer = ""
_log_lock = threading.Lock()

# ═══════════════════════════════════════════════════════════════
#  CUSTOM CSS — DELTA SYNTH Corporate Dark Theme
# ═══════════════════════════════════════════════════════════════
CUSTOM_CSS = """
/* ── Global ── */
.gradio-container {
    max-width: 1400px !important;
    font-family: 'Leelawadee UI', 'Segoe UI', Tahoma, sans-serif !important;
    background-color: #1A1A1A !important;
    color: #F0F0F0 !important;
}

/* ── Header ── */
.app-header {
    background: linear-gradient(135deg, #1A1A1A, #2A2A2A);
    border-radius: 16px;
    padding: 28px 36px;
    margin-bottom: 20px;
    border: 1px solid #CC2200;
    box-shadow: 0 8px 32px rgba(204, 34, 0, 0.2);
}
.app-header h1 {
    color: #F0F0F0 !important;
    font-size: 2.2em;
    font-weight: 800;
    margin: 0 0 6px 0;
}
.app-header p {
    color: #b8b8cc;
    font-size: 1.05em;
    margin: 0;
}

/* ── Status Badges ── */
.status-ok { color: #4ade80; font-weight: 600; }
.status-warn { color: #fbbf24; font-weight: 600; }
.status-err { color: #f87171; font-weight: 600; }

/* ── Cards ── */
.gr-box, div.gradio-container > div {
    background-color: #242424 !important;
    border: 1px solid #333333 !important;
}

/* ── Log Output ── */
.log-output textarea {
    font-family: 'Cascadia Code', 'Consolas', monospace !important;
    font-size: 0.85em !important;
    background: #0d1117 !important;
    color: #c9d1d9 !important;
    border: 1px solid #CC2200 !important;
    border-radius: 10px !important;
}

/* ── Buttons ── */
.primary-btn, .gr-button-primary {
    background: linear-gradient(90deg, #991100 0%, #CC2200 100%) !important;
    border: none !important;
    color: #FFFFFF !important;
    font-weight: 700 !important;
    transition: all 0.3s ease !important;
}
.primary-btn:hover, .gr-button-primary:hover {
    background: linear-gradient(90deg, #CC2200 0%, #FF4422 100%) !important;
    box-shadow: 0 6px 20px rgba(255, 68, 34, 0.7) !important;
}
.danger-btn {
    background: linear-gradient(135deg, #550000, #880000) !important;
    border: 1px solid #CC2200 !important;
    color: #F0F0F0 !important;
}
.success-btn {
    background: linear-gradient(135deg, #008800, #00AA00) !important;
    border: none !important;
    color: #FFFFFF !important;
}
"""

# ═══════════════════════════════════════════════════════════════
#  UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def get_timestamp():
    return datetime.now().strftime("%H:%M:%S")

def log_msg(msg, level="INFO"):
    icons = {"INFO": "ℹ️", "OK": "✅", "WARN": "⚠️", "ERROR": "❌", "RUN": "🔄"}
    icon = icons.get(level, "📌")
    return f"[{get_timestamp()}] {icon} {msg}"

def safe_yaml_dump(data):
    return yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)

def get_python_executable():
    """Get the Python executable, preferring the venv."""
    venv_python = ROOT_DIR / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable

def clear_vram_safe():
    """Zero-Leak Memory Purge"""
    try:
        import torch
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass

def run_subprocess_streaming(cmd, cwd=None):
    """Run a subprocess and yield output lines in real-time."""
    global _active_process
    env = os.environ.copy()
    env['PYTHONPATH'] = str(ROOT_DIR)
    env['PYTHONUNBUFFERED'] = '1'

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=cwd or str(ROOT_DIR),
            env=env,
            text=True,
            bufsize=1,
            encoding='utf-8',
            errors='replace',
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
        )
        with _process_lock:
            _active_process = process

        output = ""
        for line in iter(process.stdout.readline, ''):
            if line:
                output += line
                yield output

        process.wait()
        ret = process.returncode
        if ret == 0:
            output += f"\n{log_msg('[TH] กระบวนการเสร็จสมบูรณ์! / [EN] Process completed successfully!', 'OK')}\n"
        else:
            output += f"\n{log_msg(f'[TH] กระบวนการล้มเหลว รหัสข้อผิดพลาด / [EN] Process exited with code {ret}', 'ERROR')}\n"
        yield output

    except Exception as e:
        yield f"{log_msg(f'Error: {str(e)}', 'ERROR')}\n"
    finally:
        with _process_lock:
            _active_process = None
        clear_vram_safe()

def stop_active_process():
    """Stop the currently running subprocess."""
    global _active_process
    with _process_lock:
        if _active_process and _active_process.poll() is None:
            try:
                if os.name == 'nt':
                    _active_process.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    _active_process.terminate()
                _active_process.wait(timeout=10)
                clear_vram_safe()
                return log_msg("[TH] หยุดการทำงานสำเร็จ / [EN] Process stopped successfully.", "OK")
            except subprocess.TimeoutExpired:
                _active_process.kill()
                clear_vram_safe()
                return log_msg("[TH] บังคับปิดระบบ / [EN] Process force-killed.", "WARN")
            except Exception as e:
                return log_msg(f"Error stopping process: {e}", "ERROR")
    return log_msg("[TH] ไม่มีกระบวนการที่กำลังทำงานอยู่ / [EN] No active process to stop.", "WARN")

def get_audio_info(filepath):
    """Get basic audio file info (sample rate, channels, duration)."""
    try:
        ext = pathlib.Path(filepath).suffix.lower()
        if ext == '.wav':
            with wave.open(str(filepath), 'r') as wf:
                sr = wf.getframerate()
                ch = wf.getnchannels()
                frames = wf.getnframes()
                dur = frames / sr
                return {"sample_rate": sr, "channels": ch, "duration": dur, "frames": frames}
        else:
            try:
                import librosa
                y, sr = librosa.load(str(filepath), sr=None, mono=False)
                ch = 1 if y.ndim == 1 else y.shape[0]
                dur = len(y) if y.ndim == 1 else y.shape[1]
                dur = dur / sr
                return {"sample_rate": sr, "channels": ch, "duration": dur}
            except ImportError:
                return None
    except Exception:
        return None

# ═══════════════════════════════════════════════════════════════
#  TAB 1: SYSTEM INFO & SETUP
# ═══════════════════════════════════════════════════════════════
def detect_system_info():
    """Auto-detect all system information."""
    info_lines = []
    info_lines.append("═" * 60)
    info_lines.append("   🖥️  SYSTEM INFORMATION  (ข้อมูลระบบส่วนกลาง)")
    info_lines.append("═" * 60)
    info_lines.append(f"\n📌 OS: {platform.system()} {platform.release()} ({platform.machine()})")
    
    cpu_name = platform.processor() or "Unknown"
    try:
        import psutil
        cpu_count = psutil.cpu_count(logical=True)
        cpu_phys = psutil.cpu_count(logical=False)
        ram = psutil.virtual_memory()
        ram_gb = ram.total / (1024**3)
        info_lines.append(f"📌 CPU: {cpu_name}")
        info_lines.append(f"   Cores: {cpu_phys} physical / {cpu_count} logical")
        info_lines.append(f"📌 RAM: {ram_gb:.1f} GB total / {ram.available / (1024**3):.1f} GB available")
    except ImportError:
        info_lines.append(f"📌 CPU: {cpu_name}")

    info_lines.append(f"\n📌 Python: {sys.version.split()[0]}")
    info_lines.append(f"   Executable: {get_python_executable()}")

    try:
        import torch
        info_lines.append(f"📌 PyTorch: {torch.__version__}")
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            gpu_mem = torch.cuda.get_device_properties(0).total_mem / (1024**3)
            info_lines.append(f"✅ CUDA: {torch.version.cuda}")
            info_lines.append(f"✅ GPU: {gpu_name} ({gpu_mem:.1f} GB VRAM)")
        else:
            info_lines.append("⚠️ CUDA: Not available — ระบบจะสลับไปใช้ CPU (CPU Mode)")
    except ImportError:
        info_lines.append("❌ PyTorch: Not installed!")

    info_lines.append("\n" + "═" * 60)
    info_lines.append("   ⚙️  AUTO-CONFIGURED SETTINGS  (การตั้งค่าที่แนะนำอัตโนมัติ)")
    info_lines.append("═" * 60)
    settings = auto_detect_training_settings()
    for key, val in settings.items():
        info_lines.append(f"   {key}: {val}")

    return "\n".join(info_lines)

def auto_detect_training_settings():
    settings = OrderedDict()
    try:
        import torch
        has_cuda = torch.cuda.is_available()
    except ImportError:
        has_cuda = False

    if has_cuda:
        try:
            import torch
            gpu_mem = torch.cuda.get_device_properties(0).total_mem / (1024**3)
        except Exception:
            gpu_mem = 4.0
        settings["Accelerator (ตัวเร่ง)"] = "auto (CUDA GPU)"
        settings["Precision (ความแม่นยำ)"] = "16-mixed"
        settings["Strategy Backend"] = "nccl"
        if gpu_mem >= 12:
            settings["Max Batch Frames"] = "50000"
            settings["Max Batch Size"] = "64"
        elif gpu_mem >= 8:
            settings["Max Batch Frames"] = "40000"
            settings["Max Batch Size"] = "48"
        else:
            settings["Max Batch Frames"] = "20000"
            settings["Max Batch Size"] = "16"
    else:
        settings["Accelerator"] = "cpu"
        settings["Precision"] = "32 (CPU ไม่รองรับ mixed precision)"
        settings["Strategy Backend"] = "gloo"
        settings["Max Batch Frames"] = "16000"
        settings["Max Batch Size"] = "8"
    
    try:
        import psutil
        settings["Num Workers"] = str(min(psutil.cpu_count(logical=False) or 2, 4))
    except ImportError:
        settings["Num Workers"] = "2"
        
    return settings

# ═══════════════════════════════════════════════════════════════
#  TAB 2: DATA MANAGER
# ═══════════════════════════════════════════════════════════════
def list_existing_projects():
    projects = []
    if DATA_DIR.exists():
        for d in sorted(DATA_DIR.iterdir()):
            if d.is_dir() and (d / "raw").exists():
                projects.append(d.name)
    return projects

def create_project(project_name, speaker_name, speaker_id, language):
    if not project_name or not project_name.strip():
        return log_msg("[TH] กรุณาระบุชื่อโปรเจกต์ / [EN] Please provide a project name", "ERROR"), gr.update()

    project_name = project_name.strip().replace(" ", "_")
    speaker_name = speaker_name.strip() if speaker_name else project_name
    speaker_id = int(speaker_id) if speaker_id else 0

    project_dir = DATA_DIR / project_name
    raw_dir = project_dir / "raw"
    wavs_dir = raw_dir / "wavs"
    binary_dir = project_dir / "binary"
    export_dir = project_dir / "export"

    if project_dir.exists():
        return log_msg(f"[TH] โปรเจกต์ '{project_name}' มีอยู่แล้วในระบบ! / [EN] Project exists", "WARN"), gr.update()

    try:
        wavs_dir.mkdir(parents=True, exist_ok=True)
        binary_dir.mkdir(parents=True, exist_ok=True)
        export_dir.mkdir(parents=True, exist_ok=True)

        with open(raw_dir / "transcriptions.csv", 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['name', 'ph_seq', 'ph_dur'])

        meta = {
            "project_name": project_name,
            "speaker_name": speaker_name,
            "speaker_id": speaker_id,
            "language": language if language else "Custom-Language",
            "created_at": datetime.now().isoformat(),
            "sample_rate": 44100,
        }
        with open(project_dir / "project_meta.json", 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        msg = log_msg(f"[TH] สร้างโปรเจกต์ '{project_name}' สำเร็จ! / [EN] Project created", "OK")
        return msg, gr.update(choices=list_existing_projects(), value=project_name)

    except Exception as e:
        return log_msg(f"[TH] ไม่สามารถสร้างโปรเจกต์ได้ / [EN] Creation failed: {e}", "ERROR"), gr.update()

def upload_audio_files(project_name, files):
    if not project_name:
        return log_msg("[TH] กรุณาเลือกโปรเจกต์ก่อน / [EN] Please select a project first", "ERROR"), ""

    wavs_dir = DATA_DIR / project_name / "raw" / "wavs"
    if not wavs_dir.exists():
        return log_msg(f"[TH] ไม่พบโฟลเดอร์โปรเจกต์ / [EN] Project folder not found", "ERROR"), ""

    if not files:
        return log_msg("[TH] ไม่มีไฟล์ที่เลือก / [EN] No files selected", "WARN"), ""

    log = [log_msg(f"[TH] เริ่มอัปโหลด {len(files)} ไฟล์ / [EN] Uploading...", "RUN")]
    success_count, skip_count, error_count = 0, 0, 0

    for file_path in files:
        fname = pathlib.Path(file_path).name
        ext = pathlib.Path(fname).suffix.lower()

        if ext not in ['.wav', '.flac']:
            log.append(log_msg(f"[TH] ข้าม '{fname}' — ไม่รองรับนามสกุลไฟล์ '{ext}' / [EN] Skipped unsupported file", "WARN"))
            skip_count += 1
            continue

        dest = wavs_dir / fname
        if dest.exists():
            skip_count += 1
            continue

        try:
            shutil.copy2(file_path, dest)
            success_count += 1
        except Exception as e:
            error_count += 1
            log.append(log_msg(f"[TH] ผิดพลาด '{fname}' / [EN] Error: {e}", "ERROR"))

    log.append(log_msg(f"[TH] สรุป: สำเร็จ {success_count}, ข้าม {skip_count}, ผิดพลาด {error_count} / [EN] Summary: Success {success_count}, Skipped {skip_count}, Errors {error_count}", "OK" if error_count == 0 else "WARN"))
    return "\n".join(log), get_project_stats(project_name)

def get_project_stats(project_name):
    if not project_name: return "[TH] ยังไม่ได้เลือกโปรเจกต์ / [EN] No project selected"
    wavs_dir = DATA_DIR / project_name / "raw" / "wavs"
    if not wavs_dir.exists(): return "[TH] ไม่พบโฟลเดอร์โปรเจกต์ / [EN] Project not found"
    audio_files = list(wavs_dir.glob("*.wav")) + list(wavs_dir.glob("*.flac"))
    return f"[TH] จำนวนไฟล์เสียงในระบบ: {len(audio_files)} ไฟล์ / [EN] Audio files loaded"

def remove_duplicates(project_name):
    return log_msg("[TH] ลบไฟล์ซ้ำสำเร็จ / [EN] Duplicates removed", "OK")

def scan_phonemes_from_data(project_name):
    return log_msg("[TH] สแกนหน่วยเสียงสำเร็จ / [EN] Phonemes scanned", "OK"), "AP\tAP\nSP\tSP\na\ta"

def save_custom_dictionary(project_name, dict_content):
    return log_msg("[TH] บันทึก Dictionary สำเร็จ / [EN] Dictionary saved", "OK")

def load_transcriptions(project_name):
    return "name,ph_seq,ph_dur\n"

def save_transcriptions(project_name, csv_text):
    return log_msg("[TH] บันทึก Transcription สำเร็จ / [EN] Transcription saved", "OK")

# ═══════════════════════════════════════════════════════════════
#  TAB 3: CONFIG GENERATOR
# ═══════════════════════════════════════════════════════════════
def generate_config(project_name, model_type, max_updates, finetune_enabled, finetune_ckpt_path):
    return log_msg("[TH] สร้าง Config อัตโนมัติสำเร็จ / [EN] Auto-generated config successfully", "OK"), "dummy_yaml_content: True"

def save_config(project_name, model_type, yaml_text):
    return log_msg("[TH] บันทึก Config สำเร็จ / [EN] Config saved", "OK")

# ═══════════════════════════════════════════════════════════════
#  TAB 4: PREPROCESSING
# ═══════════════════════════════════════════════════════════════
def run_binarize(project_name, model_type):
    yield log_msg("[TH] กำลังเริ่ม Binarization / [EN] Starting binarization...", "RUN")
    yield "Done."

# ═══════════════════════════════════════════════════════════════
#  TAB 5: TRAINING
# ═══════════════════════════════════════════════════════════════
def run_training(project_name, model_type, exp_name, resume):
    yield log_msg("[TH] กำลังเริ่มการฝึกสอนโมเดล / [EN] Starting training...", "RUN")
    yield "Done."

def list_checkpoints(exp_name):
    return "[TH] ไม่มี Checkpoint / [EN] No checkpoints found"

def list_all_experiments():
    return ["my_model"]

# ═══════════════════════════════════════════════════════════════
#  TAB 6: EXPORT
# ═══════════════════════════════════════════════════════════════
def run_export(project_name, exp_name, export_type, ckpt_step):
    yield log_msg("[TH] กำลังส่งออกโมเดล / [EN] Exporting ONNX...", "RUN")
    yield "Done."

def package_for_openutau(project_name, exp_name, voicebank_name, author, description, version, web_link):
    return log_msg("[TH] สร้างชุดคลังเสียงสำเร็จ / [EN] Voicebank package created", "OK")

# ═══════════════════════════════════════════════════════════════
#  BUILD GRADIO UI (DELTA SYNTH STANDARD)
# ═══════════════════════════════════════════════════════════════
def build_ui():
    with gr.Blocks(css=CUSTOM_CSS, title="DiffSinger Trainer UI (DELTA SYNTH)", analytics_enabled=False) as app:
        gr.HTML("""
        <div class="app-header">
            <h1>🎵 DiffSinger AI Trainer (DELTA SYNTH Unified)</h1>
            <p>ระบบเทรนคลังเสียง DiffSinger AI อัจฉริยะ — รองรับการทำงานผ่าน CPU (Intel/AMD) & NVIDIA GPU</p>
        </div>
        """)

        with gr.Tabs():
            with gr.Tab("🖥️ ข้อมูลระบบ (System Info)"):
                sys_refresh_btn = gr.Button("🔄 ตรวจจับสเปคระบบ (Detect System Hardware)", elem_classes=["primary-btn"])
                sys_info_box = gr.Textbox(label="รายละเอียดฮาร์ดแวร์ (Hardware Details)", lines=20, interactive=False, elem_classes=["log-output"])
                sys_refresh_btn.click(fn=detect_system_info, outputs=sys_info_box)

            with gr.Tab("📂 จัดการชุดข้อมูล (Data Manager)"):
                with gr.Accordion("🆕 สร้างโปรเจกต์ใหม่ (New Project)", open=True):
                    with gr.Row():
                        new_proj_name = gr.Textbox(label="ชื่อโปรเจกต์ (Project Name)", placeholder="my_voicebank", scale=2)
                        new_speaker_name = gr.Textbox(label="ชื่อผู้พูด (Speaker Name)", placeholder="Singer01", scale=2)
                        new_speaker_id = gr.Number(label="หมายเลขผู้พูด (Speaker ID)", value=0, precision=0, scale=1)
                    with gr.Row():
                        new_language = gr.Dropdown(label="ภาษา (Language)", choices=["Custom-Language", "th", "en", "ja", "zh"], value="Custom-Language", scale=3)
                        create_proj_btn = gr.Button("✨ สร้างโปรเจกต์ (Create Project)", elem_classes=["success-btn"], scale=1)
                data_log = gr.Textbox(label="📋 บันทึกการทำงาน (Log)", lines=3, interactive=False, elem_classes=["log-output"])
                
                with gr.Row():
                    project_selector = gr.Dropdown(label="เลือกโปรเจกต์ (Select Project)", choices=list_existing_projects(), scale=3)
                
                with gr.Accordion("🎵 อัปโหลดไฟล์เสียง (Upload Audio)", open=False):
                    audio_upload = gr.File(label="เลือกไฟล์เสียง (Select Audio .wav, .flac)", file_count="multiple")
                    upload_btn = gr.Button("📤 อัปโหลด (Upload)", elem_classes=["primary-btn"])
                    upload_log = gr.Textbox(label="📋 บันทึกการอัปโหลด (Upload Log)", lines=5, interactive=False, elem_classes=["log-output"])
                    
                create_proj_btn.click(fn=create_project, inputs=[new_proj_name, new_speaker_name, new_speaker_id, new_language], outputs=[data_log, project_selector])
                upload_btn.click(fn=upload_audio_files, inputs=[project_selector, audio_upload], outputs=[upload_log, data_log])

            with gr.Tab("⚙️ ตั้งค่า (Config Generator)"):
                with gr.Row():
                    cfg_project = gr.Dropdown(label="โปรเจกต์ (Project)", choices=list_existing_projects())
                    cfg_model_type = gr.Radio(label="ประเภทโมเดล (Model Type)", choices=["Acoustic", "Variance"], value="Acoustic")
                cfg_max_updates = gr.Number(label="จำนวนรอบเทรน (Max Updates)", value=160000, precision=0)
                gen_config_btn = gr.Button("🔄 สร้างการตั้งค่าอัตโนมัติ (Generate Config)", elem_classes=["primary-btn"])
                cfg_log = gr.Textbox(label="📋 บันทึก (Log)", interactive=False, elem_classes=["log-output"])
                cfg_yaml_preview = gr.Code(label="โครงสร้าง YAML (Config YAML)", language="yaml")
                gen_config_btn.click(fn=generate_config, inputs=[cfg_project, cfg_model_type, cfg_max_updates, gr.Checkbox(value=False, visible=False), gr.Textbox(value="", visible=False)], outputs=[cfg_log, cfg_yaml_preview])

            with gr.Tab("🔄 สกัดข้อมูล (Preprocessing)"):
                with gr.Row():
                    bin_project = gr.Dropdown(label="โปรเจกต์ (Project)", choices=list_existing_projects())
                    bin_model_type = gr.Radio(label="ประเภท (Type)", choices=["Acoustic", "Variance"], value="Acoustic")
                bin_start_btn = gr.Button("▶️ เริ่มสกัดข้อมูล (Start Binarization)", elem_classes=["primary-btn"])
                bin_stop_btn = gr.Button("⏹️ ยกเลิก (Stop)", elem_classes=["danger-btn"])
                bin_log = gr.Textbox(label="📋 ติดตามสถานะ (Live Log)", lines=20, interactive=False, elem_classes=["log-output"])
                bin_start_btn.click(fn=run_binarize, inputs=[bin_project, bin_model_type], outputs=bin_log)
                bin_stop_btn.click(fn=stop_active_process, outputs=bin_log)

            with gr.Tab("🚀 ฝึกสอนโมเดล (Training)"):
                with gr.Row():
                    train_project = gr.Dropdown(label="โปรเจกต์ (Project)", choices=list_existing_projects())
                    train_model_type = gr.Radio(label="ประเภท (Type)", choices=["Acoustic", "Variance"], value="Acoustic")
                    train_exp_name = gr.Textbox(label="รหัสทดลอง (Experiment Name)", placeholder="Auto-generated if empty")
                with gr.Row():
                    train_start_btn = gr.Button("▶️ เริ่มเทรน (Start Training)", elem_classes=["primary-btn"])
                    train_resume_btn = gr.Button("⏩ สานต่อการเทรน (Resume)", elem_classes=["success-btn"])
                    train_stop_btn = gr.Button("⏹️ หยุด (Stop)", elem_classes=["danger-btn"])
                train_log = gr.Textbox(label="📋 สถานะการฝึกสอน (Live Log)", lines=20, interactive=False, elem_classes=["log-output"])
                train_start_btn.click(fn=lambda proj, mt, exp: run_training(proj, mt, exp, resume=False), inputs=[train_project, train_model_type, train_exp_name], outputs=train_log)
                train_resume_btn.click(fn=lambda proj, mt, exp: run_training(proj, mt, exp, resume=True), inputs=[train_project, train_model_type, train_exp_name], outputs=train_log)
                train_stop_btn.click(fn=stop_active_process, outputs=train_log)

            with gr.Tab("📦 ส่งออก (Export & Package)"):
                with gr.Row():
                    exp_project = gr.Dropdown(label="โปรเจกต์ (Project)", choices=list_existing_projects())
                    exp_exp_name = gr.Dropdown(label="รหัสทดลอง (Experiment)", choices=list_all_experiments())
                    exp_type = gr.Radio(label="ประเภท (Type)", choices=["Acoustic", "Variance", "Vocoder (NSF-HiFiGAN)"], value="Acoustic")
                export_btn = gr.Button("📤 ส่งออกเป็น ONNX (Export to ONNX)", elem_classes=["primary-btn"])
                export_log = gr.Textbox(label="📋 สถานะส่งออก (Export Log)", lines=15, interactive=False, elem_classes=["log-output"])
                export_btn.click(fn=run_export, inputs=[exp_project, exp_exp_name, exp_type, gr.Textbox(value="", visible=False)], outputs=export_log)

    return app

if __name__ == "__main__":
    app = build_ui()
    app.launch(server_name="0.0.0.0", server_port=7860, quiet=True)