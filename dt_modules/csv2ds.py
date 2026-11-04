# ==============================================================================
# File Name: csv2ds.py
# Version: 1.1
# Target Path: DiffTrainer-main\dt_modules\csv2ds.py
# Role: Transcription CSV to DiffSinger .ds Converter integrated with Consonant Expansion and Automated Pitch & Vibrato for Thai / โมดูลแปลงไฟล์ CSV เป็น .ds พร้อมระบบขยายพยัญชนะและใส่ลูกคออัตโนมัติ
# Credits: Made And Checked By DELTA SYNTH & All Agentic AI
# Original by agentasteriski (DiffTrainer) & Patiphat Wongyai (Delta)
# ==============================================================================

import csv
import json
import os
import pathlib
from decimal import Decimal
from math import isclose
from typing import List, Tuple
import librosa
import numpy as np
from tqdm import tqdm

from dt_modules.get_pitch import get_pitch

# ชุดพยัญชนะและสระสำหรับตรวจสอบเพื่อทำ Consonant Expansion และ Automated Vibrato
ALL_CONSONANT_SYMBOLS = {
    "b", "ch", "d", "f", "g", "h", "j", "k", "kk", "l", "m", "n", "ng",
    "p", "pp", "r", "s", "t", "tt", "v", "w", "y", "z", "sh", "th", "dh", "zh", "kh", "ph"
}
ALL_VOWEL_SYMBOLS = {
    "a", "i", "u", "e", "o", "A", "I", "U", "E", "O", "Ua", "ia", "ua", "au", "am",
    "ah", "ih", "uh", "eh", "oh", "ae", "ao", "er", "eu", "ue", "ay", "aw", "aa", "ey", "iy", "ow", "oy", "uw",
    "@", "Q", "3", "6", "1"
}
PAUSE_SYMBOLS = {"AP", "SP", "pau", "sil", "br", "-"}


def apply_consonant_expansion(ph_seq: List[str], ph_dur: List[float], expansion_ratio: float = 1.18, max_consonant_sec: float = 0.16) -> List[float]:
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
            if i + 1 < len(ph_seq):
                next_ph = ph_seq[i + 1].split("/")[-1] if "/" in ph_seq[i + 1] else ph_seq[i + 1]
                if next_ph in ALL_VOWEL_SYMBOLS and adjusted[i + 1] > 0.08:
                    old_c_dur = adjusted[i]
                    new_c_dur = min(old_c_dur * expansion_ratio, max_consonant_sec)
                    delta = new_c_dur - old_c_dur
                    if delta > 0.0 and (adjusted[i + 1] - delta) >= 0.05:
                        adjusted[i] = round(new_c_dur, 6)
                        adjusted[i + 1] = round(adjusted[i + 1] - delta, 6)

    current_total = sum(adjusted)
    if current_total > 0 and abs(total_original - current_total) > 1e-6:
        scale = total_original / current_total
        adjusted = [round(d * scale, 6) for d in adjusted]

    return adjusted


def apply_automated_pitch_and_vibrato(
    f0_seq: List[float],
    f0_timestep: float,
    ph_seq: List[str],
    ph_dur: List[float],
    vibrato_rate_hz: float = 6.2,
    vibrato_depth_cents: float = 32.0,
    vibrato_delay_sec: float = 0.18
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

    f0_safe = np.where(voiced_mask, f0, 1.0)
    log2_f0 = np.log2(f0_safe)

    cur_time = 0.0
    for ph, dur in zip(ph_seq, ph_dur):
        base_ph = ph.split("/")[-1] if "/" in ph else ph
        start_frame = int(round(cur_time / f0_timestep))
        end_frame = min(len(f0), int(round((cur_time + dur) / f0_timestep)))
        cur_time += dur

        if base_ph in ALL_VOWEL_SYMBOLS and dur >= (vibrato_delay_sec + 0.12):
            vib_start = start_frame + int(round(vibrato_delay_sec / f0_timestep))
            if vib_start < end_frame:
                frames = np.arange(vib_start, end_frame)
                t_rel = (frames - vib_start) * f0_timestep
                total_vib_dur = max(1e-4, (end_frame - vib_start) * f0_timestep)

                envelope = np.sin(np.pi * (t_rel / total_vib_dur)) ** 2
                vibrato_octaves = (vibrato_depth_cents / 1200.0) * envelope * np.sin(2.0 * np.pi * vibrato_rate_hz * t_rel)

                segment_mask = voiced_mask[vib_start:end_frame]
                log2_f0[vib_start:end_frame] = np.where(
                    segment_mask,
                    log2_f0[vib_start:end_frame] + vibrato_octaves,
                    log2_f0[vib_start:end_frame]
                )

    enhanced_f0 = np.where(voiced_mask, np.power(2.0, log2_f0), 0.0)
    return [round(float(val), 1) for val in enhanced_f0]


def csv2ds(transcription_file, wavs_folder, tolerance, hop_size, sample_rate, pe, ds_path, enable_enhancements=True):
    """Convert a transcription file to DS file with integrated Consonant Expansion and Automated Pitch & Vibrato."""
    wavs_folder = pathlib.Path(wavs_folder)
    assert wavs_folder.is_dir(), "wavs folder not found."
    out_ds = {}
    out_exists = []
    
    with open(transcription_file, "r", encoding="utf-8") as f:
        for trans_line in tqdm(csv.DictReader(f)):
            item_name = trans_line["name"]
            wav_fn = wavs_folder / f"{item_name}.wav"
            ds_fn = wavs_folder / f"{item_name}.ds"
            ph_dur = list(map(float, trans_line["ph_dur"].strip().split()))
            ph_num = list(map(int, trans_line["ph_num"].strip().split()))
            note_seq = trans_line["note_seq"].strip().split()
            note_dur = list(map(float, trans_line["note_dur"].strip().split()))
            note_glide = trans_line["note_glide"].strip().split() if "note_glide" in trans_line else None

            assert wav_fn.is_file(), f"{item_name}.wav not found."
            assert len(ph_dur) == sum(ph_num), "ph_dur and ph_num mismatch."
            assert len(note_seq) == len(note_dur), "note_seq and note_dur should have the same length."
            if note_glide:
                assert len(note_glide) == len(note_seq), "note_glide and note_seq should have the same length."
            assert isclose(
                sum(ph_dur), sum(note_dur), abs_tol=tolerance
            ), f"[{item_name}] ERROR: mismatch total duration: {sum(ph_dur) - sum(note_dur)}"

            # 1. ใช้ระบบ Consonant Expansion หากเปิดใช้งาน
            ph_seq_list = trans_line["ph_seq"].strip().split()
            if enable_enhancements:
                ph_dur = apply_consonant_expansion(ph_seq_list, ph_dur)

            # Resolve note_slur
            if "note_slur" in trans_line and trans_line["note_slur"]:
                note_slur = list(map(int, trans_line["note_slur"].strip().split()))
            else:
                note_seq, note_dur, note_slur = align_notes_to_words(
                    ph_dur, ph_num, note_seq, note_dur, tol=tolerance
                )

            # Extract f0_seq
            wav, _ = librosa.load(wav_fn, sr=sample_rate, mono=True)
            f0_timestep, f0, _ = get_pitch(pe, wav, hop_size, sample_rate, ds_path)

            # 2. ใช้ระบบ Automated Pitch & Vibrato หากเปิดใช้งาน
            f0_list = f0.tolist() if isinstance(f0, np.ndarray) else list(f0)
            if enable_enhancements:
                f0_list = apply_automated_pitch_and_vibrato(f0_list, f0_timestep, ph_seq_list, ph_dur)

            ds_content = [
                {
                    "offset": 0.0,
                    "text": trans_line["ph_seq"],
                    "ph_seq": trans_line["ph_seq"],
                    "ph_dur": " ".join(str(round(d, 6)) for d in ph_dur),
                    "ph_num": trans_line["ph_num"],
                    "note_seq": " ".join(note_seq),
                    "note_dur": " ".join(str(round(d, 6)) for d in note_dur),
                    "note_slur": " ".join(map(str, note_slur)),
                    "f0_seq": " ".join("{:.1f}".format(v) for v in f0_list),
                    "f0_timestep": str(f0_timestep),
                }
            ]
            if note_glide:
                ds_content[0]["note_glide"] = " ".join(note_glide)
            out_ds[ds_fn] = ds_content
            if ds_fn.exists():
                out_exists.append(ds_fn)

    for ds_fn, ds_content in out_ds.items():
        with open(ds_fn, "w", encoding="utf-8") as f:
            json.dump(ds_content, f, ensure_ascii=False, indent=4)


def align_notes_to_words(
    ph_dur: List[float], ph_num: List[int], note_seq: List[str], note_dur: List[float], tol: float = 0.01
) -> Tuple[List[str], List[float], List[int]]:
    idx = 0
    word_dur = []
    for num in ph_num:
        word_dur.append(sum(ph_dur[idx:idx + num]))
        idx += num
    word_start = np.cumsum([0.0] + word_dur[:-1])
    word_end = np.cumsum(word_dur)
    note_start = np.cumsum([0.0] + note_dur[:-1])
    note_end = np.cumsum(note_dur)
    new_note_seq = []
    new_note_dur = []
    note_slur = []
    
    for word_idx in range(len(word_dur)):
        note_start_idx = np.argmin(np.abs(note_start - word_start[word_idx]))
        if word_start[word_idx] < note_start[note_start_idx] - tol:
            note_start_idx = max(0, note_start_idx - 1)
        note_end_idx = np.argmin(np.abs(note_end[note_start_idx:] - word_end[word_idx])) + note_start_idx
        if word_end[word_idx] > note_end[note_end_idx] + tol:
            note_end_idx = min(len(note_end) - 1, note_end_idx + 1)
            
        word_note_seq = []
        word_note_dur = []
        for note_idx in range(note_start_idx, note_end_idx + 1):
            if note_idx == note_start_idx:
                start = word_start[word_idx]
            else:
                start = note_start[note_idx]
            if note_idx == note_end_idx:
                end = word_end[word_idx]
            else:
                end = note_end[note_idx]
            if word_note_seq and word_note_seq[-1] == note_seq[note_idx]:
                word_note_dur[-1] += (end - start)
            else:
                word_note_seq.append(note_seq[note_idx])
                word_note_dur.append(end - start)
        new_note_seq.extend(word_note_seq)
        new_note_dur.extend(word_note_dur)
        note_slur.extend([0] + [1] * (len(word_note_seq) - 1))
        
    return new_note_seq, new_note_dur, note_slur


if __name__ == "__main__":
    print("==============================================================================")
    print("  DELTA SYNTH - CSV to DS Converter with Consonant Expansion & Vibrato v1.1")
    print("==============================================================================")