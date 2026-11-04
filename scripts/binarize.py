# ==============================================================================
# Date: 2026-10-31
# File Name: binarize.py
# Version: 1.3
# Location: Root Directory / scripts
# Credit: Made And Checked By DELTA SYNTH & Staff
#         Original by DiffSinger Project
# Description: Refactored with robust error handling, bilingual logs, and memory safety.
# ==============================================================================
import importlib
import os
import sys
import traceback
import gc
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
os.environ['PYTHONPATH'] = str(root_dir)
sys.path.insert(0, str(root_dir))

from utils.hparams import set_hparams, hparams

def log_bilingual(th, en):
    """แสดงผลข้อความ 2 ภาษาตามกฎของ DELTA SYNTH"""
    print(f"[TH] {th}\n[EN] {en}", flush=True)

def binarize():
    set_hparams()
    try:
        binarizer_cls_path = hparams.get("binarizer_cls")
        if not binarizer_cls_path:
            raise ValueError("binarizer_cls is not defined in hparams")
            
        pkg = ".".join(binarizer_cls_path.split(".")[:-1])
        cls_name = binarizer_cls_path.split(".")[-1]
        
        module = importlib.import_module(pkg)
        binarizer_cls = getattr(module, cls_name)
        
        log_bilingual(f"เริ่มกระบวนการเตรียมข้อมูล: {binarizer_cls}", f"Starting Binarizer: {binarizer_cls}")
        binarizer_cls().process()
        log_bilingual("กระบวนการ Binarize เสร็จสิ้นอย่างสมบูรณ์", "Binarize process completed successfully.")
        
    except Exception as e:
        log_bilingual(f"ข้อผิดพลาดร้ายแรงระหว่างกระบวนการ Binarize: {e}", f"Fatal error during Binarization: {e}")
        traceback.print_exc()
        sys.exit(1)
    finally:
        gc.collect()

if __name__ == '__main__':
    binarize()