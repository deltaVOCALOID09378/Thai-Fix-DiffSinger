# ==============================================================================
# Date: 05/11/2026 (พ.ศ. 2569)
# File Name: train.py
# Version: 1.4
# Location: scripts/train.py
# Credit: Made And Checked By DELTA SYNTH & All Code Agentic AI Engine
#         [ Original by DiffSinger Project ]
# Description: Added fallback parameter injection for 'max_val_batch_frames' to ensure zero-defect task initialization.
# ==============================================================================
import importlib
import os
import sys
import traceback
from pathlib import Path

root_dir = Path(__file__).parent.parent.resolve()
os.environ['PYTHONPATH'] = str(root_dir)
sys.path.insert(0, str(root_dir))

os.environ['TORCH_CUDNN_V8_API_ENABLED'] = '1'  # Prevent unacceptable slowdowns when using 16 precision

from utils.hparams import set_hparams, hparams

def log_bilingual(th, en):
    """แสดงผลข้อความ 2 ภาษาตามกฎของ DELTA SYNTH"""
    print(f"[TH] {th}\n[EN] {en}", flush=True)

# 1. โหลดการตั้งค่าทั้งหมด
set_hparams()

# 2. [DELTA SYNTH] ระบบ Guard & Fallback เพื่อป้องกัน KeyError ใน base_task.py
if 'max_val_batch_frames' not in hparams:
    fallback_val = hparams.get('max_batch_frames', 80000)
    hparams['max_val_batch_frames'] = fallback_val
    log_bilingual(
        f"คำเตือน: ไม่พบ 'max_val_batch_frames' ใน config ระบบปรับใช้ค่าอ้างอิงเป็น: {fallback_val}",
        f"Warning: 'max_val_batch_frames' not found in config. Auto-fallback applied with value: {fallback_val}"
    )

if not hparams.get('nccl_p2p', True):
    log_bilingual("กำลังปิดใช้งาน NCCL P2P", "Disabling NCCL P2P")
    os.environ['NCCL_P2P_DISABLE'] = '1'

def run_task():
    try:
        assert hparams.get('task_cls', '') != '', "| [ERROR] 'task_cls' is not specified."
        pkg = ".".join(hparams["task_cls"].split(".")[:-1])
        cls_name = hparams["task_cls"].split(".")[-1]
        task_cls = getattr(importlib.import_module(pkg), cls_name)

        log_bilingual(f"เริ่มต้นกระบวนการฝึกสอนโมเดล (Training): {cls_name}", 
                      f"Starting training task: {cls_name}")
        
        # 3. สั่งรันการเทรน
        task_cls.start()
        
    except Exception as e:
        log_bilingual(f"ข้อผิดพลาดร้ายแรงระหว่างกระบวนการฝึกสอน: {e}", 
                      f"Fatal error during training task: {e}")
        traceback.print_exc()
        sys.exit(-1)

if __name__ == '__main__':
    run_task()