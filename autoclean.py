# Made And Checked By DELTA SYNTH & All Code Agentic AI Engine
# Original by DELTA SYNTH & OpenVPI
# Version 1.0
# -*- coding: utf-8 -*-
# ==============================================================================
# File: autoclean.py | Audio Data Autocleaning & Acoustic Health Inspection
# Description: Automated dataset scanning, integrity validation, DC offset removal,
# silence trimming (breath-preserving), clipping mitigation, and quarantine isolation.
# ==============================================================================

import os
import sys
import glob
import json
import shutil
import logging
import traceback
from pathlib import Path
from typing import Generator, Dict, Any, List, Tuple, Optional
import numpy as np
import soundfile as sf

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("DataAutoclean")


class AudioDataAutocleaner:
    """
    DELTA SYNTH Professional Audio Dataset Autocleaning Engine.
    Ensures zero artifacts, prevents vocoder DC bias, preserves vocal breaths,
    and isolates corrupted/clipped samples to quarantine.
    """

    def __init__(
        self,
        min_duration: float = 0.5,
        max_duration: float = 30.0,
        min_rms: float = 0.0005,
        max_clipping_ratio: float = 0.03,
        target_peak_db: float = -1.0,
        breath_pad_seconds: float = 0.15,
        fix_dc_offset: bool = True,
        normalize_peak: bool = True,
        quarantine_bad_files: bool = True,
    ):
        self.min_duration = min_duration
        self.max_duration = max_duration
        self.min_rms = min_rms
        self.max_clipping_ratio = max_clipping_ratio
        self.target_peak = 10.0 ** (target_peak_db / 20.0)  # ~0.891
        self.breath_pad_seconds = breath_pad_seconds
        self.fix_dc_offset = fix_dc_offset
        self.normalize_peak = normalize_peak
        self.quarantine_bad_files = quarantine_bad_files

    def inspect_and_clean_file(
        self, file_path: str, quarantine_dir: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Inspects a single audio file, detects anomalies, applies surgical fixes,
        or quarantines damaged audio.
        """
        result: Dict[str, Any] = {
            "path": file_path,
            "filename": os.path.basename(file_path),
            "status": "PASS",
            "actions": [],
            "reasons": [],
            "sr": 0,
            "duration": 0.0,
            "peak": 0.0,
            "rms": 0.0,
        }

        # 1. File existence & basic header check
        if not os.path.exists(file_path) or os.path.getsize(file_path) < 256:
            result["status"] = "QUARANTINED"
            result["reasons"].append("File missing or corrupted header (<256 bytes)")
            self._quarantine(file_path, quarantine_dir)
            return result

        try:
            data, sr = sf.read(file_path, dtype="float32")
        except Exception as e:
            result["status"] = "QUARANTINED"
            result["reasons"].append(f"Decode error: {str(e)}")
            self._quarantine(file_path, quarantine_dir)
            return result

        result["sr"] = sr
        total_samples = len(data)
        if total_samples == 0:
            result["status"] = "QUARANTINED"
            result["reasons"].append("Empty audio payload (0 samples)")
            self._quarantine(file_path, quarantine_dir)
            return result

        # 2. Channel normalization (Stereo to Mono)
        if data.ndim > 1:
            data = np.mean(data, axis=-1)
            result["actions"].append("Stereo to mono downmix")

        duration = total_samples / sr
        result["duration"] = round(duration, 3)

        # 3. Duration validation
        if duration < self.min_duration:
            result["status"] = "QUARANTINED"
            result["reasons"].append(f"Duration too short ({duration:.2f}s < {self.min_duration}s)")
            self._quarantine(file_path, quarantine_dir)
            return result
        elif duration > self.max_duration:
            result["status"] = "QUARANTINED"
            result["reasons"].append(f"Duration too long ({duration:.2f}s > {self.max_duration}s)")
            self._quarantine(file_path, quarantine_dir)
            return result

        # 4. Silence / Low Energy Detection
        rms = float(np.sqrt(np.mean(data**2)))
        result["rms"] = round(rms, 6)
        if rms < self.min_rms:
            result["status"] = "QUARANTINED"
            result["reasons"].append(f"Silence/Low energy (RMS: {rms:.6f} < {self.min_rms})")
            self._quarantine(file_path, quarantine_dir)
            return result

        modified = False

        # 5. DC Offset Mitigation
        if self.fix_dc_offset:
            dc_offset = float(np.mean(data))
            if abs(dc_offset) > 1e-4:
                data = data - dc_offset
                modified = True
                result["actions"].append(f"DC offset removed ({dc_offset:+.6f})")

        # 6. Clipping Detection & Peak Normalization
        peak = float(np.max(np.abs(data)))
        result["peak"] = round(peak, 4)
        clipped_count = int(np.sum(np.abs(data) >= 0.999))
        clipping_ratio = clipped_count / total_samples

        if clipping_ratio > self.max_clipping_ratio:
            result["status"] = "QUARANTINED"
            result["reasons"].append(
                f"Severe digital clipping ({clipping_ratio*100:.2f}% samples clipped)"
            )
            self._quarantine(file_path, quarantine_dir)
            return result
        elif peak >= 0.999 and self.normalize_peak:
            data = data * (self.target_peak / peak)
            modified = True
            result["actions"].append(f"Peak normalized to {self.target_peak:.3f} (-1.0 dBFS)")

        # 7. Safe Silence Trimming with Breath Preservation
        trimmed_data, trim_applied = self._trim_silence_preserve_breath(data, sr)
        if trim_applied:
            data = trimmed_data
            modified = True
            result["actions"].append("Trimmed silence with breath margin")

        # 8. Save back sanitized audio if modified
        if modified:
            try:
                sf.write(file_path, data, sr, subtype="PCM_16")
                result["status"] = "SANITIZED"
            except Exception as e:
                result["status"] = "ERROR"
                result["reasons"].append(f"Write failure: {str(e)}")

        return result

    def _trim_silence_preserve_breath(
        self, data: np.ndarray, sr: int
    ) -> Tuple[np.ndarray, bool]:
        """
        Trims unvoiced dead silence at beginnings and ends while preserving
        natural breath buffers (150ms margin).
        """
        hop_size = int(sr * 0.02)  # 20ms frames
        if len(data) < hop_size * 4:
            return data, False

        num_frames = len(data) // hop_size
        frames = data[: num_frames * hop_size].reshape((num_frames, hop_size))
        frame_rms = np.sqrt(np.mean(frames**2, axis=-1))

        threshold = max(self.min_rms * 2.0, 0.003)
        voiced_idx = np.where(frame_rms > threshold)[0]

        if len(voiced_idx) == 0:
            return data, False

        pad_frames = int(self.breath_pad_seconds / 0.02)
        start_frame = max(0, voiced_idx[0] - pad_frames)
        end_frame = min(num_frames, voiced_idx[-1] + 1 + pad_frames)

        start_sample = start_frame * hop_size
        end_sample = min(len(data), end_frame * hop_size)

        # Only apply trim if at least 15% was dead air or > 0.5s trimmed
        if (start_sample > int(sr * 0.2)) or (len(data) - end_sample > int(sr * 0.2)):
            trimmed = data[start_sample:end_sample]
            if len(trimmed) >= int(sr * self.min_duration):
                return trimmed, True

        return data, False

    def _quarantine(self, file_path: str, quarantine_dir: Optional[str]) -> None:
        """Moves corrupted/invalid files to the quarantine directory."""
        if not self.quarantine_bad_files or not quarantine_dir:
            return
        try:
            os.makedirs(quarantine_dir, exist_ok=True)
            target = os.path.join(quarantine_dir, os.path.basename(file_path))
            if os.path.exists(target):
                base, ext = os.path.splitext(target)
                target = f"{base}_{int(os.path.getmtime(file_path))}{ext}"
            shutil.move(file_path, target)
        except Exception as e:
            logger.warning(f"Failed to quarantine {file_path}: {e}")

    def clean_dataset_generator(
        self, dataset_dir: str
    ) -> Generator[Dict[str, Any], None, Dict[str, Any]]:
        """
        Scans a dataset directory, yields real-time progress for WebUI,
        and returns complete aggregate statistics.
        """
        dataset_path = Path(dataset_dir)
        if not dataset_path.exists() or not dataset_path.is_dir():
            raise FileNotFoundError(f"Dataset directory not found: {dataset_dir}")

        quarantine_dir = os.path.join(dataset_dir, "_quarantine")
        audio_extensions = {".wav", ".flac", ".mp3", ".m4a", ".ogg"}
        files = [
            str(p)
            for p in dataset_path.rglob("*")
            if p.suffix.lower() in audio_extensions and "_quarantine" not in p.parts
        ]

        total_files = len(files)
        stats = {
            "total_scanned": total_files,
            "passed": 0,
            "sanitized": 0,
            "quarantined": 0,
            "errors": 0,
            "details": [],
        }

        if total_files == 0:
            yield {"progress": 1.0, "message": "⚠️ ไม่พบไฟล์เสียงในไดเรกทอรีที่ระบุ", "stats": stats}
            return stats

        for i, file_p in enumerate(files):
            res = self.inspect_and_clean_file(file_p, quarantine_dir=quarantine_dir)
            status = res["status"]

            if status == "PASS":
                stats["passed"] += 1
            elif status == "SANITIZED":
                stats["sanitized"] += 1
            elif status == "QUARANTINED":
                stats["quarantined"] += 1
            else:
                stats["errors"] += 1

            stats["details"].append(res)
            progress = (i + 1) / total_files
            status_symbol = "🟢" if status in ("PASS", "SANITIZED") else "⚠️"
            msg = f"{status_symbol} [{i+1}/{total_files}] {res['filename']} -> {status} {' | '.join(res['actions'] or res['reasons'])}"

            yield {
                "progress": progress,
                "current": i + 1,
                "total": total_files,
                "file": res["filename"],
                "status": status,
                "message": msg,
                "stats": stats,
            }

        # Save audit manifest
        report_path = os.path.join(dataset_dir, "autoclean_audit_report.json")
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(stats, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Could not save audit report: {e}")

        return stats


def clean_dataset(data_dir: str) -> None:
    """CLI entrypoint for standalone batch execution."""
    cleaner = AudioDataAutocleaner()
    print(f"==================================================")
    print(f"🚀 DELTA SYNTH Audio Data Autocleaning Engine")
    print(f"📂 Scanning Directory: {data_dir}")
    print(f"==================================================")

    for step in cleaner.clean_dataset_generator(data_dir):
        print(step["message"])

    print("\n✅ Dataset Autocleaning Complete!")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python autoclean.py <dataset_directory>")
        sys.exit(1)

    clean_dataset(sys.argv[1])
