# -*- coding: utf-8 -*-
# ==============================================================================
# 1. วัน/เดือน/ปี (Date)       : 02/11/2569 (02 November 2026)
# 2. ชื่อไฟล์ที่ทำ (File Name)   : auto_pipeline.py
# 3. ลำดับเวอร์ชัน (Version)   : 1.2 (Bilingual Safe Exec Pipeline Edition)
# 4. เครดิตผู้สร้าง (Credit)    : Made And Checked By DELTA SYNTH & All Code Agentic AI Engine
#                              Original by OpenVPI DiffSinger
# 5. ตำแหน่งที่จัดวางไฟล์ (Path) : auto_pipeline.py
# 6. รายละเอียดการแก้ไขงาน    : ยกระดับมาตรฐานการแจ้งเตือนสองภาษา (Bilingual Logging) 
#                              และรับประกันเสถียรภาพเมื่อพบข้อผิดพลาดขณะทำงาน (OOM/Crash)
# ==============================================================================

import argparse
import os
import yaml
import subprocess
import sys

# บังคับใช้ UTF-8 ป้องกันปัญหาบน Windows
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def print_banner(msg):
    print("=" * 65)
    print(f" {msg} ")
    print("=" * 65)

def validate_config(config_path):
    print_banner("1. CONFIG VALIDATION (ตรวจสอบการตั้งค่า)")
    if not os.path.exists(config_path):
        print(f"[TH] ❌ [ERROR] ไม่พบไฟล์ Config ที่ระบุ: {config_path}")
        print(f"[EN] ❌ [ERROR] Config file not found: {config_path}")
        return False
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print(f"[TH] ❌ [ERROR] ไม่สามารถอ่านไฟล์ Config ({config_path}) ได้: {e}")
        print(f"[EN] ❌ [ERROR] Unable to parse Config file ({config_path}): {e}")
        return False
        
    binary_data_dir = config.get('binary_data_dir', '')
    if binary_data_dir and not os.path.exists(binary_data_dir):
        print(f"[TH] ❌ [ERROR] ไม่พบโฟลเดอร์ binary_data_dir ที่ระบุใน config: {binary_data_dir}")
        print("          (โปรดตรวจสอบว่ารันขั้นตอน Binarize หรือยัง หรือระบุพาธผิด)")
        print(f"[EN] ❌ [ERROR] binary_data_dir not found: {binary_data_dir}")
        return False
        
    max_batch_size = config.get('max_batch_size', 0)
    if max_batch_size > 24:
        print(f"[TH] ⚠️ [WARNING] max_batch_size ใน config มีค่า {max_batch_size} ซึ่งอาจทำให้เกิด GPU OOM ได้")
        print("          (แนะนำให้ปรับลดลงเหลือประมาณ 12-16 หาก VRAM ไม่พอ)")
        print(f"[EN] ⚠️ [WARNING] High max_batch_size ({max_batch_size}) may cause GPU OOM.")
        
    print("[TH] ✅ [OK] ตรวจสอบไฟล์ Config เบื้องต้นผ่านแล้ว!")
    print("[EN] ✅ [OK] Config file validation passed!")
    return True

def run_training(config_path, exp_name):
    print_banner("2. TRAINING (กำลังฝึกสอนโมเดล)")
    cmd = [sys.executable, "scripts/train.py", "--config", config_path, "--exp_name", exp_name]
    print(f"[TH] 🔄 กำลังรันคำสั่ง (Executing): {' '.join(cmd)}")
    
    try:
        subprocess.run(cmd, check=True)
        print("[TH] ✅ [SUCCESS] การเทรนเสร็จสมบูรณ์!")
        print("[EN] ✅ [SUCCESS] Training process completed!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n[TH] ❌ [ERROR] เกิดข้อผิดพลาดขณะเทรน (Exit Code: {e.returncode})")
        print("[TH] สรุปปัญหาที่อาจเป็นไปได้ (Possible Causes):")
        print("1. GPU Out of Memory (OOM) - แนะนำให้ลด max_batch_size ลง")
        print("2. ข้อมูลสูญหายหรือพาธไม่ถูกต้อง - ตรวจสอบ binary_data_dir อีกครั้ง")
        print("3. โค้ดหรือ Python Environment มีปัญหา (Environment/Library issues)")
        return False

def run_export(exp_name, out_dir):
    print_banner("3. ONNX EXPORT (ส่งออกไฟล์โมเดล ONNX)")
    cmd = [sys.executable, "scripts/export.py", "--exp_name", exp_name]
    if out_dir:
        cmd.extend(["--out", out_dir])
        
    print(f"[TH] 🔄 กำลังรันคำสั่ง (Executing): {' '.join(cmd)}")
    
    try:
        subprocess.run(cmd, check=True)
        print("[TH] ✅ [SUCCESS] การ Export เป็น ONNX เสร็จสมบูรณ์!")
        
        # Determine final output dir
        if not out_dir:
            out_dir = os.path.join("checkpoints", exp_name)
            
        print_banner("SUMMARY & OUTPUT (สรุปผลการทำงาน)")
        print(f"[TH] 🎉 สำเร็จ! ไฟล์ ONNX และโมเดลสำหรับ OpenUtau ถูกจัดเก็บไว้ที่:")
        print(f"[EN] 🎉 Success! ONNX and OpenUtau artifacts are saved at:")
        print(f"   >> {os.path.abspath(out_dir)} <<")
        print("[TH] สามารถนำโฟลเดอร์นี้ไปแพ็คใช้งานใน OpenUtau ได้ทันทีครับ")
        
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n[TH] ❌ [ERROR] เกิดข้อผิดพลาดขณะส่งออกโมเดล (Export ONNX Failed) (Exit Code: {e.returncode})")
        print("[TH] สรุปปัญหาที่อาจเป็นไปได้ (Possible Causes):")
        print("1. ไม่พบ Checkpoint (โมเดลอาจจะเทรนไม่เสร็จ หรือระบุ exp_name ผิด)")
        print("2. ไลบรารีสำหรับ ONNX ไม่ครบ (รัน pip install -r requirements-onnx.txt)")
        return False

def main():
    parser = argparse.ArgumentParser(description="DiffSinger 1-Click Pipeline (Train + Export) by DELTA SYNTH")
    parser.add_argument("--config", type=str, default="configs/variance.yaml", help="Path to config file")
    parser.add_argument("--exp_name", type=str, required=True, help="Experiment name (e.g., my_model)")
    parser.add_argument("--out", type=str, default="", help="Output directory for ONNX (optional)")
    
    args = parser.parse_args()
    
    if not validate_config(args.config):
        sys.exit(1)
        
    if not run_training(args.config, args.exp_name):
        sys.exit(1)
        
    if not run_export(args.exp_name, args.out):
        sys.exit(1)

if __name__ == "__main__":
    main()