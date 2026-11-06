# ==============================================================================
# Date: 05/11/2026 (พ.ศ. 2569)
# File Name: acoustic_binarizer.py
# Version: 1.7
# Credit: Made And Checked By DELTA SYNTH & All Code Agentic AI Engine
#         [ Original by DiffSinger Project ]
# Location: preprocessing/acoustic_binarizer.py
# Description: Acoustic Binarizer with standardized bilingual logging,
#              conditional waveform decomposition for fast feature extraction,
#              complete 4-mode data augmentation suite, UTF-8-BOM CSV resilience,
#              and robust VRAM/RAM safeguards.
# ==============================================================================

"""
    item: one piece of data
    item_name: data id
    wav_fn: wave file path
    spk: dataset name
    ph_seq: phoneme sequence
    ph_dur: phoneme durations
"""
import csv
import os
import pathlib
import random
import gc
import traceback
from copy import deepcopy

import librosa
import numpy as np
import torch

from basics.base_binarizer import BaseBinarizer
from basics.base_pe import BasePE
from modules.fastspeech.tts_modules import LengthRegulator
from modules.pe import initialize_pe
from utils.binarizer_utils import (
    SinusoidalSmoothingConv1d,
    get_mel_torch,
    get_mel2ph_torch,
    get_energy_librosa,
    get_breathiness,
    get_voicing,
    get_tension_base_harmonic,
)
from utils.decomposed_waveform import DecomposedWaveform
from utils.hparams import hparams

os.environ["OMP_NUM_THREADS"] = "1"
ACOUSTIC_ITEM_ATTRIBUTES = [
    'spk_id',
    'mel',
    'languages',
    'tokens',
    'mel2ph',
    'f0',
    'energy',
    'breathiness',
    'voicing',
    'tension',
    'key_shift',
    'speed',
]
WAV_CANDIDATE_EXTENSIONS = ['.wav', '.flac', '.WAV', '.FLAC', '.mp3', '.ogg']

pitch_extractor: BasePE = None
energy_smooth: SinusoidalSmoothingConv1d = None
breathiness_smooth: SinusoidalSmoothingConv1d = None
voicing_smooth: SinusoidalSmoothingConv1d = None
tension_smooth: SinusoidalSmoothingConv1d = None


def log_bilingual(th: str, en: str) -> None:
    """แสดงผลข้อความ 2 ภาษาตามมาตรฐานของ DELTA SYNTH"""
    print(f"[TH] {th}\n[EN] {en}", flush=True)


class AcousticBinarizer(BaseBinarizer):
    def __init__(self):
        super().__init__(data_attrs=ACOUSTIC_ITEM_ATTRIBUTES)
        self.lr = LengthRegulator().to(self.device)
        self.need_energy = hparams.get('use_energy_embed', False)
        self.need_breathiness = hparams.get('use_breathiness_embed', False)
        self.need_voicing = hparams.get('use_voicing_embed', False)
        self.need_tension = hparams.get('use_tension_embed', False)

        if hparams.get('mel_base') != 'e':
            raise ValueError(
                "| [ERROR] ค่า mel_base ต้องตั้งเป็น 'e' ตามมาตรฐานของระบบ "
                "/ Mel base must be set to 'e' according to 2nd stage of the migration plan."
            )

        log_bilingual(
            f"AcousticBinarizer กำหนดค่าสำเร็จ: อุปกรณ์={self.device}, ฐานสเปกโตรแกรม='e'",
            f"AcousticBinarizer Initialized: Device={self.device}, Mel Base='e'"
        )

    def load_meta_data(self, raw_data_dir: pathlib.Path, ds_id, spk, lang):
        meta_data_dict = {}
        trans_file = raw_data_dir / 'transcriptions.csv'

        log_bilingual(
            f"กำลังอ่านข้อมูลกำกับเสียง: {trans_file}",
            f"Loading metadata: {trans_file}"
        )

        if not trans_file.exists():
            raise FileNotFoundError(
                f"| [ERROR] ไม่พบไฟล์ข้อมูลกำกับเสียงที่ '{trans_file}' "
                f"/ Transcription file not found at '{trans_file}'."
            )

        # ใช้ encoding='utf-8-sig' เพื่อรองรับทั้ง UTF-8 ทั่วไป และ UTF-8 with BOM จาก Windows
        with open(trans_file, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for utterance_label in reader:
                item_name = utterance_label['name'].strip()
                wav_fn = None
                for ext in WAV_CANDIDATE_EXTENSIONS:
                    candidate_fn = raw_data_dir / 'wavs' / f'{item_name}{ext}'
                    if candidate_fn.exists():
                        wav_fn = candidate_fn
                        break

                if wav_fn is None:
                    candidate_direct = raw_data_dir / 'wavs' / item_name
                    if candidate_direct.exists():
                        wav_fn = candidate_direct

                if wav_fn is None:
                    raise FileNotFoundError(
                        f"| [ERROR] ไม่พบไฟล์เสียงสำหรับ '{item_name}' นามสกุลที่รองรับ: {WAV_CANDIDATE_EXTENSIONS} "
                        f"/ Waveform file not found for '{item_name}'. Supported extensions: {WAV_CANDIDATE_EXTENSIONS}"
                    )

                ph_seq_raw = utterance_label['ph_seq'].strip()
                ph_dur_raw = utterance_label['ph_dur'].strip()

                if not ph_seq_raw or not ph_dur_raw:
                    log_bilingual(
                        f"ข้ามรายการ '{item_name}': ข้อมูล ph_seq หรือ ph_dur ว่างเปล่า",
                        f"Skipping item '{item_name}': Empty ph_seq or ph_dur."
                    )
                    continue

                ph_seq_tokens = ph_seq_raw.split()
                ph_dur_values = [float(x) for x in ph_dur_raw.split()]
                ph_encoded = self.phoneme_dictionary.encode(ph_seq_raw, lang=lang)

                temp_dict = {
                    'wav_fn': str(wav_fn),
                    'spk_id': self.spk_map[spk],
                    'spk_name': spk,
                    'lang_seq': [
                        (
                            self.lang_map[lang if '/' not in p else p.split('/', maxsplit=1)[0]]
                            if self.phoneme_dictionary.is_cross_lingual(p if '/' in p else f'{lang}/{p}')
                            else 0
                        )
                        for p in ph_seq_tokens
                    ],
                    'ph_seq': ph_encoded,
                    'ph_dur': ph_dur_values,
                    'ph_text': ph_seq_raw,
                }

                if len(temp_dict['ph_seq']) != len(temp_dict['ph_dur']):
                    raise ValueError(
                        f"| [ERROR] ความยาวของ ph_seq ({len(temp_dict['ph_seq'])}) และ ph_dur ({len(temp_dict['ph_dur'])}) ไม่ตรงกันใน '{item_name}' "
                        f"/ Sequence length mismatch between ph_seq and ph_dur in '{item_name}'."
                    )
                if not all(ph_dur >= 0 for ph_dur in temp_dict['ph_dur']):
                    raise ValueError(
                        f"| [ERROR] พบค่าความยาวหน่วยเสียงติดลบใน '{item_name}' "
                        f"/ Negative phoneme duration values detected in '{item_name}'."
                    )

                meta_data_dict[f'{ds_id}:{item_name}'] = temp_dict

        log_bilingual(
            f"โหลดข้อมูลกำกับเสียงเรียบร้อย: รวมทั้งสิ้น {len(meta_data_dict)} รายการ",
            f"Metadata loaded successfully: Total {len(meta_data_dict)} items."
        )
        return meta_data_dict

    @torch.no_grad()
    def process_item(self, item_name, meta_data, binarization_args):
        try:
            waveform, _ = librosa.load(meta_data['wav_fn'], sr=hparams['audio_sample_rate'], mono=True)
            if waveform is None or len(waveform) == 0:
                log_bilingual(
                    f"ข้ามไฟล์ '{item_name}': ไฟล์เสียงว่างเปล่าหรือไม่สามารถโหลดได้",
                    f"Skipped '{item_name}': Audio waveform is empty or could not be loaded."
                )
                return None

            mel = get_mel_torch(
                waveform, hparams['audio_sample_rate'], num_mel_bins=hparams['audio_num_mel_bins'],
                hop_size=hparams['hop_size'], win_size=hparams['win_size'], fft_size=hparams['fft_size'],
                fmin=hparams['fmin'], fmax=hparams['fmax'],
                device=self.device
            )
            length = mel.shape[0]
            if length == 0:
                log_bilingual(
                    f"ข้ามไฟล์ '{item_name}': สเปกโตรแกรมมีความยาวเป็น 0",
                    f"Skipped '{item_name}': Mel spectrogram length is 0."
                )
                return None

            seconds = length * hparams['hop_size'] / hparams['audio_sample_rate']
            processed_input = {
                'name': item_name,
                'wav_fn': meta_data['wav_fn'],
                'spk_id': meta_data['spk_id'],
                'spk_name': meta_data['spk_name'],
                'seconds': seconds,
                'length': length,
                'mel': mel,
                'languages': np.array(meta_data['lang_seq'], dtype=np.int64),
                'tokens': np.array(meta_data['ph_seq'], dtype=np.int64),
                'ph_dur': np.array(meta_data['ph_dur']).astype(np.float32),
                'ph_text': meta_data['ph_text'],
            }

            processed_input['mel2ph'] = get_mel2ph_torch(
                self.lr, torch.from_numpy(processed_input['ph_dur']), length, self.timestep, device=self.device
            ).cpu().numpy()

            global pitch_extractor
            if pitch_extractor is None:
                log_bilingual("เริ่มต้นโหลดตัวสกัดระดับเสียง (Pitch Extractor)...", "Initializing Pitch Extractor...")
                pitch_extractor = initialize_pe()

            gt_f0, uv = pitch_extractor.get_pitch(
                waveform, samplerate=hparams['audio_sample_rate'], length=length,
                hop_size=hparams['hop_size'], f0_min=hparams['f0_min'], f0_max=hparams['f0_max'],
                interp_uv=True
            )
            if uv.all():
                log_bilingual(
                    f"ข้ามไฟล์ '{item_name}': ไม่พบสัญญาณเสียงที่มีระดับเสียง (Unvoiced ทั้งไฟล์)",
                    f"Skipped '{item_name}': empty ground truth f0"
                )
                return None
            processed_input['f0'] = gt_f0.astype(np.float32)

            if self.need_energy:
                energy = get_energy_librosa(
                    waveform, length, hop_size=hparams['hop_size'], win_size=hparams['win_size']
                ).astype(np.float32)

                global energy_smooth
                if energy_smooth is None:
                    energy_smooth = SinusoidalSmoothingConv1d(
                        round(hparams['energy_smooth_width'] / self.timestep)
                    ).eval().to(self.device)
                energy = energy_smooth(torch.from_numpy(energy).to(self.device)[None])[0]
                processed_input['energy'] = energy.cpu().numpy()

            # แยกองค์ประกอบเสียงเฉพาะเมื่อมีความจำเป็นต้องใช้ (Conditional Waveform Decomposition)
            if self.need_breathiness or self.need_voicing or self.need_tension:
                dec_waveform = DecomposedWaveform(
                    waveform, samplerate=hparams['audio_sample_rate'], f0=gt_f0 * ~uv,
                    hop_size=hparams['hop_size'], fft_size=hparams['fft_size'], win_size=hparams['win_size'],
                    algorithm=hparams['hnsep']
                )

                if self.need_breathiness:
                    breathiness = get_breathiness(dec_waveform, None, None, length=length)
                    global breathiness_smooth
                    if breathiness_smooth is None:
                        breathiness_smooth = SinusoidalSmoothingConv1d(
                            round(hparams['breathiness_smooth_width'] / self.timestep)
                        ).eval().to(self.device)
                    breathiness = breathiness_smooth(torch.from_numpy(breathiness).to(self.device)[None])[0]
                    processed_input['breathiness'] = breathiness.cpu().numpy()

                if self.need_voicing:
                    voicing = get_voicing(dec_waveform, None, None, length=length)
                    global voicing_smooth
                    if voicing_smooth is None:
                        voicing_smooth = SinusoidalSmoothingConv1d(
                            round(hparams['voicing_smooth_width'] / self.timestep)
                        ).eval().to(self.device)
                    voicing = voicing_smooth(torch.from_numpy(voicing).to(self.device)[None])[0]
                    processed_input['voicing'] = voicing.cpu().numpy()

                if self.need_tension:
                    tension = get_tension_base_harmonic(
                        dec_waveform, None, None, length=length, domain='logit'
                    )
                    global tension_smooth
                    if tension_smooth is None:
                        tension_smooth = SinusoidalSmoothingConv1d(
                            round(hparams['tension_smooth_width'] / self.timestep)
                        ).eval().to(self.device)
                    tension = tension_smooth(torch.from_numpy(tension).to(self.device)[None])[0]
                    if tension.isnan().any():
                        log_bilingual(
                            f"ข้ามไฟล์ '{item_name}': ค่าความตึงเสียง (Tension) ผิดปกติ (NaN)",
                            f"Skipped '{item_name}': Tension contains NaN values."
                        )
                        return None
                    processed_input['tension'] = tension.cpu().numpy()

            if hparams.get('use_key_shift_embed', False):
                processed_input['key_shift'] = 0.
            if hparams.get('use_speed_embed', False):
                processed_input['speed'] = 1.

            return processed_input

        except Exception as e:
            log_bilingual(
                f"เกิดข้อผิดพลาดในการประมวลผลไฟล์ '{item_name}': {e}",
                f"Error processing item '{item_name}': {e}"
            )
            traceback.print_exc()
            return None
        finally:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            gc.collect()

    def arrange_data_augmentation(self, data_iterator):
        aug_map = {}
        aug_list = []
        all_item_names = [item_name for item_name, _ in data_iterator]
        total_scale = 0

        if not all_item_names:
            return aug_map

        aug_pe = initialize_pe()

        log_bilingual(
            "เริ่มต้นกระบวนการเพิ่มความหลากหลายของข้อมูล (Data Augmentation Check)...",
            "Initializing Data Augmentation process..."
        )

        # 1. Random Pitch Shifting
        pitch_shift_args = self.augmentation_args.get('random_pitch_shifting', {})
        if pitch_shift_args.get('enabled', False):
            from augmentation.spec_stretch import SpectrogramStretchAugmentation
            key_shift_min, key_shift_max = pitch_shift_args['range']

            if not hparams.get('use_key_shift_embed', False):
                raise ValueError(
                    "| [ERROR] การทำ Random Pitch Shifting ต้องเปิดใช้งาน use_key_shift_embed == True "
                    "/ Random pitch shifting requires use_key_shift_embed == True."
                )
            if not (key_shift_min < 0 < key_shift_max):
                raise ValueError(
                    "| [ERROR] ช่วงของ Key Shift ต้องมีค่าต่ำสุดน้อยกว่า 0 และค่าสูงสุดมากกว่า 0 "
                    "/ Range must satisfy min < 0 < max."
                )

            aug_ins = SpectrogramStretchAugmentation(self.raw_data_dirs, pitch_shift_args, pe=aug_pe)
            scale = pitch_shift_args['scale']
            aug_item_names = random.choices(all_item_names, k=int(scale * len(all_item_names)))

            for aug_item_name in aug_item_names:
                rand = random.uniform(-1, 1)
                key_shift = key_shift_min * abs(rand) if rand < 0 else key_shift_max * rand
                aug_task = {
                    'name': aug_item_name,
                    'func': aug_ins.process_item,
                    'kwargs': {'key_shift': key_shift}
                }
                if aug_item_name in aug_map:
                    aug_map[aug_item_name].append(aug_task)
                else:
                    aug_map[aug_item_name] = [aug_task]
                aug_list.append(aug_task)
            total_scale += scale

            log_bilingual(
                f"กำหนดภารกิจ Random Pitch Shifting สำเร็จ: {len(aug_list)} รายการ",
                f"Random Pitch Shifting tasks scheduled successfully: {len(aug_list)} tasks."
            )

        # 2. Fixed Pitch Shifting
        fixed_pitch_args = self.augmentation_args.get('fixed_pitch_shifting', {})
        if fixed_pitch_args.get('enabled', False):
            from augmentation.spec_stretch import SpectrogramStretchAugmentation
            targets = fixed_pitch_args['targets']

            if not hparams.get('use_key_shift_embed', False):
                raise ValueError(
                    "| [ERROR] การทำ Fixed Pitch Shifting ต้องเปิดใช้งาน use_key_shift_embed == True "
                    "/ Fixed pitch shifting requires use_key_shift_embed == True."
                )
            if len(targets) != len(set(targets)):
                raise ValueError(
                    "| [ERROR] ค่าเป้าหมายใน targets ห้ามซ้ำกัน "
                    "/ Targets in fixed_pitch_shifting must not contain duplicates."
                )
            if 0.0 in targets:
                raise ValueError(
                    "| [ERROR] ค่าเป้าหมายใน targets ห้ามมี 0.0 "
                    "/ Targets in fixed_pitch_shifting must not contain 0.0."
                )

            aug_ins = SpectrogramStretchAugmentation(self.raw_data_dirs, fixed_pitch_args, pe=aug_pe)
            scale = fixed_pitch_args['scale']
            for target in targets:
                sub_item_names = random.choices(
                    all_item_names, k=int(scale * len(all_item_names) / len(targets))
                )
                for aug_item_name in sub_item_names:
                    aug_task = {
                        'name': aug_item_name,
                        'func': aug_ins.process_item,
                        'kwargs': {'key_shift': target}
                    }
                    if aug_item_name in aug_map:
                        aug_map[aug_item_name].append(aug_task)
                    else:
                        aug_map[aug_item_name] = [aug_task]
                    aug_list.append(aug_task)
            total_scale += scale

            log_bilingual(
                f"กำหนดภารกิจ Fixed Pitch Shifting สำเร็จ: รวมสะสม {len(aug_list)} รายการ",
                f"Fixed Pitch Shifting tasks scheduled: Total {len(aug_list)} tasks."
            )

        # 3. Fixed Time Stretching
        fixed_stretch_args = self.augmentation_args.get('fixed_time_stretching', {})
        if fixed_stretch_args.get('enabled', False):
            from augmentation.spec_stretch import SpectrogramStretchAugmentation
            targets = fixed_stretch_args['targets']

            if not hparams.get('use_speed_embed', False):
                raise ValueError(
                    "| [ERROR] การทำ Fixed Time Stretching ต้องเปิดใช้งาน use_speed_embed == True "
                    "/ Fixed time stretching requires use_speed_embed == True."
                )
            if len(targets) != len(set(targets)):
                raise ValueError(
                    "| [ERROR] ค่าเป้าหมายใน targets ห้ามซ้ำกัน "
                    "/ Targets in fixed_time_stretching must not contain duplicates."
                )
            if 1.0 in targets or not all(t > 0 for t in targets):
                raise ValueError(
                    "| [ERROR] ค่าเป้าหมายใน targets ต้องมากกว่า 0 และไม่เท่ากับ 1.0 "
                    "/ Targets must be greater than 0 and not equal to 1.0."
                )

            aug_ins = SpectrogramStretchAugmentation(self.raw_data_dirs, fixed_stretch_args, pe=aug_pe)
            scale = fixed_stretch_args['scale']
            for target in targets:
                sub_item_names = random.choices(
                    all_item_names, k=int(scale * len(all_item_names) / len(targets))
                )
                for aug_item_name in sub_item_names:
                    aug_task = {
                        'name': aug_item_name,
                        'func': aug_ins.process_item,
                        'kwargs': {'speed': target}
                    }
                    if aug_item_name in aug_map:
                        aug_map[aug_item_name].append(aug_task)
                    else:
                        aug_map[aug_item_name] = [aug_task]
                    aug_list.append(aug_task)
            total_scale += scale

            log_bilingual(
                f"กำหนดภารกิจ Fixed Time Stretching สำเร็จ: รวมสะสม {len(aug_list)} รายการ",
                f"Fixed Time Stretching tasks scheduled: Total {len(aug_list)} tasks."
            )

        # 4. Random Time Stretching
        random_stretch_args = self.augmentation_args.get('random_time_stretching', {})
        if random_stretch_args.get('enabled', False):
            from augmentation.spec_stretch import SpectrogramStretchAugmentation
            speed_min, speed_max = random_stretch_args['range']

            if not hparams.get('use_speed_embed', False):
                raise ValueError(
                    "| [ERROR] การทำ Random Time Stretching ต้องเปิดใช้งาน use_speed_embed == True "
                    "/ Random time stretching requires use_speed_embed == True."
                )
            if not (0 < speed_min < 1 < speed_max):
                raise ValueError(
                    "| [ERROR] ช่วงของความเร็วต้องอยู่ระหว่าง 0 < min < 1 < max "
                    "/ Speed range must satisfy 0 < min < 1 < max."
                )

            aug_ins = SpectrogramStretchAugmentation(self.raw_data_dirs, random_stretch_args, pe=aug_pe)
            scale = random_stretch_args['scale']
            aug_item_names = random.choices(all_item_names, k=int(scale * len(all_item_names)))

            for aug_item_name in aug_item_names:
                rand = random.uniform(-1, 1)
                speed = 1 + (speed_min - 1) * abs(rand) if rand < 0 else 1 + (speed_max - 1) * rand
                aug_task = {
                    'name': aug_item_name,
                    'func': aug_ins.process_item,
                    'kwargs': {'speed': speed}
                }
                if aug_item_name in aug_map:
                    aug_map[aug_item_name].append(aug_task)
                else:
                    aug_map[aug_item_name] = [aug_task]
                aug_list.append(aug_task)
            total_scale += scale

            log_bilingual(
                f"กำหนดภารกิจ Random Time Stretching สำเร็จ: รวมสะสม {len(aug_list)} รายการ",
                f"Random Time Stretching tasks scheduled: Total {len(aug_list)} tasks."
            )

        log_bilingual(
            f"จัดตาราง Data Augmentation เสร็จสิ้น: รวมทั้งหมด {len(aug_list)} ภารกิจ (Scale รวม={total_scale:.2f})",
            f"Data Augmentation scheduling completed: Total {len(aug_list)} tasks (Total scale={total_scale:.2f})."
        )

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        gc.collect()

        return aug_map
