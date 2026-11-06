# ==============================================================================
# Date: 05/11/2026 (พ.ศ. 2569)
# File Name: binarize.py
# Version: 1.5
# Location: scripts/binarize.py
# Credit: Made And Checked By DELTA SYNTH & All Code Agentic AI Engine
#         [ Original by DiffSinger Project ]
# Description: Intercept --reset flag to clear binary_data_dir automatically, 
#              integrated robust memory safety, and bilingual logging.
# ==============================================================================
import importlib
import os
import sys
import traceback
import gc
import shutil
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
os.environ['PYTHONPATH'] = str(root_dir)
sys.path.insert(0, str(root_dir))

from utils.hparams import set_hparams, hparams

def log_bilingual(th, en):
    """แสดงผลข้อความ 2 ภาษาตามกฎของ DELTA SYNTH"""
    print(f"[TH] {th}\n[EN] {en}", flush=True)

def binarize():
    # ดักจับคำสั่ง --reset เพื่อล้างข้อมูลเก่า
    is_reset = False
    if '--reset' in sys.argv:
        is_reset = True
        # นำออกเพื่อใช้สำหรับการจัดการโฟลเดอร์โดยเฉพาะ ป้องกันการทำงานซ้อนทับกับพารามิเตอร์อื่น
        sys.argv.remove('--reset')

    # โหลดการตั้งค่าหลักจาก config
    set_hparams()
    
    try:
        # จัดการล้างโฟลเดอร์เป้าหมายเมื่อผู้ใช้งานต้องการรีเซ็ตข้อมูล (Zero-Defect Logic)
        if is_reset:
            binary_dir = hparams.get("binary_data_dir")
            if binary_dir:
                bin_path = Path(binary_dir).resolve()
                if bin_path.exists():
                    log_bilingual(f"ระบบกำลังล้างข้อมูลเก่าในโฟลเดอร์: {bin_path}", 
                                  f"System is clearing old data in: {bin_path}")
                    shutil.rmtree(bin_path)
                bin_path.mkdir(parents=True, exist_ok=True)
                log_bilingual("ล้างโฟลเดอร์และเตรียมพื้นที่สำหรับ Binarize เสร็จสิ้น", 
                              "Folder cleared and space prepared successfully")

        binarizer_cls_path = hparams.get("binarizer_cls")
        if not binarizer_cls_path:
            raise ValueError("binarizer_cls is not defined in hparams (กรุณาตรวจสอบไฟล์ config)")
            
        pkg = ".".join(binarizer_cls_path.split(".")[:-1])
        cls_name = binarizer_cls_path.split(".")[-1]
        
        module = importlib.import_module(pkg)
        binarizer_cls = getattr(module, cls_name)
        
        log_bilingual(f"เริ่มกระบวนการเตรียมข้อมูล: {binarizer_cls.__name__}", 
                      f"Starting Binarizer: {binarizer_cls.__name__}")
        
        # ประมวลผลข้อมูล Binarize
        binarizer_cls().process()
        
        log_bilingual("กระบวนการ Binarize เสร็จสิ้นอย่างสมบูรณ์", 
                      "Binarize process completed successfully.")
        
    except Exception as e:
        log_bilingual(f"ข้อผิดพลาดร้ายแรงระหว่างกระบวนการ Binarize: {e}", 
                      f"Fatal error during Binarization: {e}")
        traceback.print_exc()
        sys.exit(1)
    finally:
        # คืนพื้นที่หน่วยความจำอย่างเคร่งครัดตามมาตรฐาน
        gc.collect()

if __name__ == '__main__':
    binarize()