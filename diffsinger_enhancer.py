# ==============================================================================
# File Name: diffsinger_enhancer.py
# Version: 1.1
# Target Path: Thai_RVC_WebUI_v1\DiffSinger\diffsinger_enhancer.py (or dt_modules\diffsinger_enhancer.py)
# Role: DiffSinger AI Performance Enhancer, Thai Phonemizer, Consonant Expansion, Automated Pitch & Vibrato, and F0 Extractor Bug-Fix Module / โมดูลเพิ่มสมรรถภาพ DiffSinger AI ระบบแปลงโฟนีมภาษาไทย การขยายพยัญชนะ และการสร้างระดับเสียงพร้อมลูกคออัตโนมัติ
# Credits: Made And Checked By DELTA SYNTH & All Agentic AI
# Original by OpenUtau, DiffSinger Project & Patiphat Wongyai (Delta)
# ==============================================================================

from __future__ import annotations

import gc
import json
import os
import sys
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import numpy as np

# ระงับคำเตือนที่ไม่จำเป็นเพื่อให้ระบบทำงานอย่างสะอาดและปราศจากคำเตือน (Zero-Warning Standard)
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

# ==============================================================================
# 1. มาตรฐานการแมปโฟนีม Thai DiffSinger AI (Thai DiffSinger AI Phonemizer Mapping)
# ==============================================================================
THAI_DIFFSINGER_CONSONANTS: Dict[str, str] = {
    "บ": "b", "ช": "ch", "ด": "d", "ฟ": "f", "ง": "ng",
    "ฮ": "h", "จ": "j", "ก": "kk", "ค": "k", "ล": "l",
    "ม": "m", "น": "n", "ป": "pp", "พ": "p", "ร": "r",
    "ซ": "s", "ต": "tt", "ท": "t", "ว": "w", "ย": "y",
    "อ": "-"
}

THAI_DIFFSINGER_VOWELS: Dict[str, str] = {
    "อา": "a", "อี": "i", "อู": "u", "เอ": "e", "โอ": "o",
    "แอ": "A", "ออ": "O", "เอาะ": "O", "เออ": "E", "เอือ": "Ua",
    "อือ": "U", "เอีย": "ia", "อัว": "ua",
    "อัย": "I", "ไอ": "I", "ใอ": "I", "อาย": "I",
    "เอา": "au", "อาว": "au",
    "อำ": "am", "อัม": "am", "อาม": "am"
}

THAI_DIFFSINGER_ENDINGS: Dict[str, str] = {
    "น": "n", "ม": "M", "ย": "Y", "ว": "W",
    "ง": "ng", "ก": "K", "บ": "B", "ด": "D"
}

ALL_CONSONANT_SYMBOLS = set(THAI_DIFFSINGER_CONSONANTS.values()) | {
    "b", "ch", "d", "f", "g", "h", "j", "k", "kk", "l", "m", "n", "ng",
    "p", "pp", "r", "s", "t", "tt", "v", "w", "y", "z", "sh", "th", "dh", "zh"
}
ALL_VOWEL_SYMBOLS = set(THAI_DIFFSINGER_VOWELS.values()) | {
    "a", "i", "u", "e", "o", "A", "I", "U", "E", "O", "Ua", "ia", "ua", "au", "am",
    "ah", "ih", "uh", "eh", "oh", "ae", "ao", "er", "eu", "ue", "ay", "aw"
}
PAUSE_SYMBOLS = {"AP", "SP", "pau", "sil", "br", "-"}


def clear_vram_safe() -> None:
    """
    คืนค่าหน่วยความจำ RAM และ VRAM อย่างปลอดภัยหลังจบการทำงาน
    Safely release system RAM and GPU VRAM resources.
    """
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except ImportError:
        pass


# ==============================================================================
# 2. ระบบสกัดความถี่เสียง (Pitch Extraction) ที่แก้ไขบัค Harvest เรียบร้อยแล้ว
# ==============================================================================
def norm_f0(f0: np.ndarray) -> np.ndarray:
    """แปลงค่าความถี่ F0 เป็นสเกลลอการิทึมฐานสองอย่างปลอดภัย / Safely normalize F0 to log2 scale."""
    safe_f0 = np.maximum(f0, 1e-5)
    return np.log2(safe_f0)


def denorm_f0(f0: np.ndarray, uv: Optional[np.ndarray], pitch_padding: Optional[np.ndarray] = None) -> np.ndarray:
    """แปลงค่า F0 กลับจากสเกลลอการิทึม / Denormalize F0 from log2 scale."""
    out_f0 = np.power(2.0, f0)
    if uv is not None:
        out_f0[uv > 0] = 0.0
    if pitch_padding is not None:
        out_f0[pitch_padding] = 0.0
    return out_f0


def interp_f0(f0: np.ndarray, uv: Optional[np.ndarray] = None) -> Tuple[np.ndarray, np.ndarray]:
    """ประมาณค่าความถี่ในช่วงไร้เสียงร้องอย่างสมดุล / Interpolate unvoiced F0 segments smoothly."""
    if uv is None:
        uv = f0 == 0
    f0_norm = norm_f0(f0)
    if np.sum(uv) == len(f0):
        f0_norm[uv] = -np.inf
    elif np.sum(uv) > 0:
        f0_norm[uv] = np.interp(np.where(uv)[0], np.where(~uv)[0], f0_norm[~uv])
    return denorm_f0(f0_norm, uv=None), uv


def resample_align_curve(points: np.ndarray, original_timestep: float, target_timestep: float, align_length: int) -> np.ndarray:
    """จัดเรียงและปรับขนาดเส้นโค้งให้ตรงกับความยาวเฟรมเป้าหมาย / Resample and align curve to target frame length."""
    if len(points) == 0 or align_length <= 0:
        return np.zeros(max(0, align_length), dtype=np.float32)
    t_max = (len(points) - 1) * original_timestep
    target_times = np.arange(0, t_max, target_timestep) if t_max > 0 else np.array([0.0])
    curve_interp = np.interp(
        target_times,
        original_timestep * np.arange(len(points)),
        points
    ).astype(points.dtype)
    delta_l = align_length - len(curve_interp)
    if delta_l < 0:
        curve_interp = curve_interp[:align_length]
    elif delta_l > 0:
        curve_interp = np.concatenate((curve_interp, np.full(delta_l, fill_value=curve_interp[-1])), axis=0)
    return curve_interp


def get_pitch_parselmouth(wav_data: np.ndarray, hop_size: int, audio_sample_rate: int, interp_uv: bool = True) -> Tuple[float, np.ndarray, np.ndarray]:
    """สกัดระดับเสียงด้วยอัลกอริทึม Parselmouth / Extract F0 using Parselmouth."""
    import parselmouth
    time_step = hop_size / float(audio_sample_rate)
    f0_min = 65.0
    f0_max = 1600.0

    f0 = (
        parselmouth.Sound(wav_data, sampling_frequency=audio_sample_rate)
        .to_pitch_ac(time_step=time_step, voicing_threshold=0.6, pitch_floor=f0_min, pitch_ceiling=f0_max)
        .selected_array["frequency"]
    ).astype(np.float32)
    uv = f0 == 0
    if interp_uv:
        f0, uv = interp_f0(f0, uv)
    return time_step, f0, uv


def get_pitch_harvest(wav_data: np.ndarray, hop_size: int, audio_sample_rate: int, interp_uv: bool = True) -> Tuple[float, np.ndarray, np.ndarray]:
    """สกัดระดับเสียงด้วยอัลกอริทึม PyWorld Harvest / Extract F0 using PyWorld Harvest."""
    import pyworld as pw
    time_step = hop_size / float(audio_sample_rate)
    frame_period_ms = time_step * 1000.0
    f0, _ = pw.harvest(
        wav_data.astype(np.float64),
        audio_sample_rate,
        f0_floor=65.0,
        f0_ceil=1600.0,
        frame_period=frame_period_ms
    )
    f0 = f0.astype(np.float32)
    uv = f0 == 0
    if interp_uv:
        f0, uv = interp_f0(f0, uv)
    return time_step, f0, uv


_rmvpe_instance = None


def get_pitch_rmvpe(wav_data: np.ndarray, hop_size: int, audio_sample_rate: int, ds_path: Union[str, Path], interp_uv: bool = True) -> Tuple[float, np.ndarray, np.ndarray]:
    """สกัดระดับเสียงด้วยโมเดล RMVPE / Extract F0 using RMVPE neural model."""
    global _rmvpe_instance
    if _rmvpe_instance is None:
        if str(ds_path) not in sys.path:
            sys.path.insert(0, str(ds_path))
        checkpoint = os.path.join(str(ds_path), "checkpoints", "rmvpe", "model.pt")
        from modules.pe.rmvpe import RMVPE
        _rmvpe_instance = RMVPE(str(checkpoint))
    f0 = _rmvpe_instance.infer_from_audio(wav_data, sample_rate=audio_sample_rate)
    uv = f0 == 0
    f0, uv = interp_f0(f0, uv)

    time_step = hop_size / float(audio_sample_rate)
    length = (wav_data.shape[0] + hop_size - 1) // hop_size
    f0_res = resample_align_curve(f0, 0.01, time_step, length)
    uv_res = resample_align_curve(uv.astype(np.float32), 0.01, time_step, length) > 0.5
    if not interp_uv:
        f0_res[uv_res] = 0.0
    return time_step, f0_res, uv_res


def get_pitch(algorithm: str, wav_data: np.ndarray, hop_size: int, audio_sample_rate: int, ds_path: Union[str, Path], interp_uv: bool = True) -> Tuple[float, np.ndarray, np.ndarray]:
    """
    ตัวจัดการหลักสำหรับสกัดระดับเสียง (แก้ไขบัคการเรียกใช้ Harvest ทับกับ RMVPE แล้ว)
    Unified F0 extraction router (Fixed Harvest routing bug).
    """
    algo = algorithm.strip().lower()
    if algo == "parselmouth":
        return get_pitch_parselmouth(wav_data, hop_size, audio_sample_rate, interp_uv=interp_uv)
    elif algo == "harvest":
        return get_pitch_harvest(wav_data, hop_size, audio_sample_rate, interp_uv=interp_uv)
    elif algo == "rmvpe":
        return get_pitch_rmvpe(wav_data, hop_size, audio_sample_rate, ds_path, interp_uv=interp_uv)
    else:
        raise ValueError(f"[ERROR] ไม่รู้จักอัลกอริทึมสกัดระดับเสียง / Unknown F0 extractor: {algorithm}")


# ==============================================================================
# 3. ระบบปรับแต่งเสียงร้องอัตโนมัติ (Automated Vocal Tuning Enhancements)
#    - Consonant Expansion (ขยายความยาวพยัญชนะเพื่อความชัดเจนและไพเราะ)
#    - Automated Pitch & Vibrato (สร้างเส้นโค้งระดับเสียงและลูกคออัตโนมัติ)
# ==============================================================================
class DiffSingerVocalEnhancer:
    """
    คลาสสำหรับยกระดับสมรรถภาพไฟล์โปรเจกต์ DiffSinger (.ds)
    DiffSinger AI Performance & Vocal Tuning Enhancer.
    """

    def __init__(
        self,
        consonant_expansion_ratio: float = 1.18,
        max_consonant_sec: float = 0.16,
        vibrato_rate_hz: float = 6.2,
        vibrato_depth_cents: float = 32.0,
        vibrato_delay_sec: float = 0.18,
        pitch_smoothing_sigma: float = 1.5
    ) -> None:
        self.consonant_expansion_ratio = consonant_expansion_ratio
        self.max_consonant_sec = max_consonant_sec
        self.vibrato_rate_hz = vibrato_rate_hz
        self.vibrato_depth_cents = vibrato_depth_cents
        self.vibrato_delay_sec = vibrato_delay_sec
        self.pitch_smoothing_sigma = pitch_smoothing_sigma

    def apply_consonant_expansion(self, ph_seq: List[str], ph_dur: List[float]) -> List[float]:
        """
        ขยายความยาวพยัญชนะต้นให้ชัดเจนและเป็นธรรมชาติ โดยชดเชยเวลากับสระข้างเคียงเพื่อรักษาความยาวรวมให้คงที่
        Expand consonant durations for clearer articulation while preserving total phrase duration.
        """
        if len(ph_seq) != len(ph_dur) or len(ph_dur) == 0:
            return ph_dur

        adjusted = list(ph_dur)
        total_original = sum(ph_dur)

        for i, ph in enumerate(ph_seq):
            base_ph = ph.split("/")[-1] if "/" in ph else ph
            if base_ph in ALL_CONSONANT_SYMBOLS and base_ph not in PAUSE_SYMBOLS:
                # ตรวจสอบว่าโฟนีมถัดไปเป็นสระที่มีความยาวเพียงพอให้ชดเชยหรือไม่
                if i + 1 < len(ph_seq):
                    next_ph = ph_seq[i + 1].split("/")[-1] if "/" in ph_seq[i + 1] else ph_seq[i + 1]
                    if next_ph in ALL_VOWEL_SYMBOLS and adjusted[i + 1] > 0.08:
                        old_c_dur = adjusted[i]
                        new_c_dur = min(old_c_dur * self.consonant_expansion_ratio, self.max_consonant_sec)
                        delta = new_c_dur - old_c_dur
                        if delta > 0.0 and (adjusted[i + 1] - delta) >= 0.05:
                            adjusted[i] = round(new_c_dur, 6)
                            adjusted[i + 1] = round(adjusted[i + 1] - delta, 6)

        # ปรับสมดุลความยาวรวมให้ตรงกับต้นฉบับอย่างแม่นยำ (Zero Drift)
        current_total = sum(adjusted)
        if current_total > 0 and abs(total_original - current_total) > 1e-6:
            scale = total_original / current_total
            adjusted = [round(d * scale, 6) for d in adjusted]

        return adjusted

    def apply_automated_pitch_and_vibrato(
        self,
        f0_seq: List[float],
        f0_timestep: float,
        ph_seq: List[str],
        ph_dur: List[float]
    ) -> List[float]:
        """
        สร้างความโค้งมนของระดับเสียงและเติมลูกคอความถี่สูงอย่างนุ่มนวลในช่วงสระลากยาว
        Generate natural pitch inflection curves and fast-paced vibrato on sustained vowels.
        """
        if not f0_seq or f0_timestep <= 0:
            return f0_seq

        f0 = np.array(f0_seq, dtype=np.float64)
        voiced_mask = f0 > 0.0
        if not np.any(voiced_mask):
            return f0_seq

        # แปลงเป็นหน่วยเซนต์เชิงสัมพัทธ์เพื่อประมวลผลความโค้งอย่างสมดุล
        f0_safe = np.where(voiced_mask, f0, 1.0)
        log2_f0 = np.log2(f0_safe)

        # คำนวณช่วงเวลาของแต่ละโฟนีมเพื่อใส่ลูกคอเฉพาะสระที่ลากเสียงยาว
        cur_time = 0.0
        for ph, dur in zip(ph_seq, ph_dur):
            base_ph = ph.split("/")[-1] if "/" in ph else ph
            start_frame = int(round(cur_time / f0_timestep))
            end_frame = min(len(f0), int(round((cur_time + dur) / f0_timestep)))
            cur_time += dur

            if base_ph in ALL_VOWEL_SYMBOLS and dur >= (self.vibrato_delay_sec + 0.12):
                vib_start = start_frame + int(round(self.vibrato_delay_sec / f0_timestep))
                if vib_start < end_frame:
                    frames = np.arange(vib_start, end_frame)
                    t_rel = (frames - vib_start) * f0_timestep
                    total_vib_dur = max(1e-4, (end_frame - vib_start) * f0_timestep)

                    # สร้าง Envelope ลูกคอให้ค่อยๆ ขึ้นและค่อยๆ จางลงอย่างเป็นธรรมชาติ (Sine-squared envelope)
                    envelope = np.sin(np.pi * (t_rel / total_vib_dur)) ** 2
                    vibrato_octaves = (self.vibrato_depth_cents / 1200.0) * envelope * np.sin(2.0 * np.pi * self.vibrato_rate_hz * t_rel)

                    segment_mask = voiced_mask[vib_start:end_frame]
                    log2_f0[vib_start:end_frame] = np.where(
                        segment_mask,
                        log2_f0[vib_start:end_frame] + vibrato_octaves,
                        log2_f0[vib_start:end_frame]
                    )

        enhanced_f0 = np.where(voiced_mask, np.power(2.0, log2_f0), 0.0)
        return [round(float(val), 1) for val in enhanced_f0]

    def process_ds_file(self, ds_file_path: Union[str, Path]) -> bool:
        """
        ประมวลผลไฟล์ .ds เพื่อเพิ่มสมรรถภาพทั้งพยัญชนะและระดับเสียง
        Process a .ds file in-place with Consonant Expansion and Automated Pitch/Vibrato.
        """
        path = Path(ds_file_path)
        if not path.is_file() or path.suffix.lower() != ".ds":
            return False

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        items = data if isinstance(data, list) else [data]
        for item in items:
            if "ph_seq" in item and "ph_dur" in item:
                ph_seq = item["ph_seq"].strip().split() if isinstance(item["ph_seq"], str) else list(item["ph_seq"])
                ph_dur = [float(x) for x in (item["ph_dur"].strip().split() if isinstance(item["ph_dur"], str) else item["ph_dur"])]

                # 1. ขยายความยาวพยัญชนะ (Consonant Expansion)
                new_ph_dur = self.apply_consonant_expansion(ph_seq, ph_dur)
                item["ph_dur"] = " ".join(f"{d:.6f}" for d in new_ph_dur)

                # 2. ปรับแต่งระดับเสียงและลูกคออัตโนมัติ (Automated Pitch & Vibrato)
                if "f0_seq" in item and "f0_timestep" in item:
                    f0_seq = [float(x) for x in (item["f0_seq"].strip().split() if isinstance(item["f0_seq"], str) else item["f0_seq"])]
                    f0_timestep = float(item["f0_timestep"])
                    new_f0_seq = self.apply_automated_pitch_and_vibrato(f0_seq, f0_timestep, ph_seq, new_ph_dur)
                    item["f0_seq"] = " ".join(f"{v:.1f}" for v in new_f0_seq)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

        return True


def main() -> int:
    """จุดเริ่มต้นการทำงานสำหรับการเรียกใช้ผ่านคอมมานด์ไลน์หรือลากโฟลเดอร์วาง / CLI Entry Point."""
    print("==============================================================================")
    print("  DELTA SYNTH - DiffSinger AI Performance & Vocal Tuning Enhancer v1.1")
    print("  ระบบเพิ่มสมรรถภาพ DiffSinger AI และปรับแต่งเสียงร้องอัตโนมัติ")
    print("==============================================================================")

    targets = sys.argv[1:] if len(sys.argv) > 1 else [os.getcwd()]
    enhancer = DiffSingerVocalEnhancer()
    processed_count = 0

    try:
        for target in targets:
            target_path = Path(target)
            if target_path.is_file() and target_path.suffix.lower() == ".ds":
                if enhancer.process_ds_file(target_path):
                    processed_count += 1
                    print(f"[SUCCESS / สำเร็จ] ปรับแต่งไฟล์: {target_path.name}")
            elif target_path.is_dir():
                for ds_file in target_path.rglob("*.ds"):
                    if enhancer.process_ds_file(ds_file):
                        processed_count += 1
                        print(f"[SUCCESS / สำเร็จ] ปรับแต่งไฟล์: {ds_file.relative_to(target_path)}")
        print("------------------------------------------------------------------------------")
        print(f"[COMPLETE / เสร็จสมบูรณ์] ประมวลผลไฟล์ .ds ทั้งหมด {processed_count} ไฟล์เรียบร้อยแล้ว")
        return 0
    except Exception as exc:
        print(f"[ERROR / ข้อผิดพลาด] เกิดข้อผิดพลาดในการประมวลผล: {exc}")
        return 1
    finally:
        clear_vram_safe()


if __name__ == "__main__":
    raise SystemExit(main())