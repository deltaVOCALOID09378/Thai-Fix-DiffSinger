# ==============================================================================
# Date: 2026-10-31
# File Name: acoustic_binarizer.py
# Version: 1.5
# Credit: Made And Checked By DELTA SYNTH & Staff
#         Original by DiffSinger Project
# Location: preprocessing/acoustic_binarizer.py
# Description: Acoustic Binarizer with standardized bilingual logging and robust VRAM safeguards.
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
WAV_CANDIDATE_EXTENSIONS = ['.wav', '.flac']

pitch_extractor: BasePE = None
energy_smooth: SinusoidalSmoothingConv1d = None
breathiness_smooth: SinusoidalSmoothingConv1d = None
voicing_smooth: SinusoidalSmoothingConv1d = None
tension_smooth: SinusoidalSmoothingConv1d = None


def log_bilingual(th, en):
    """แสดงผลข้อความ 2 ภาษาตามมาตรฐานของ DELTA SYNTH"""
    print(f"[TH] {th}\n[EN] {en}", flush=True)


class AcousticBinarizer(BaseBinarizer):
    def __init__(self):
        super().__init__(data_attrs=ACOUSTIC_ITEM_ATTRIBUTES)
        self.lr = LengthRegulator()
        self.need_energy = hparams.get('use_energy_embed', False)
        self.need_breathiness = hparams.get('use_breathiness_embed', False)
        self.need_voicing = hparams.get('use_voicing_embed', False)
        self.need_tension = hparams.get('use_tension_embed', False)
        
        if hparams.get('mel_base') != 'e':
            raise ValueError("| [ERROR] Mel base must be set to 'e' according to 2nd stage of the migration plan.")
            
        log_bilingual(
            f"AcousticBinarizer กำหนดค่าสำเร็จ: Device={self.device}, Mel Base='e'",
            f"AcousticBinarizer Initialized: Device={self.device}, Mel Base='e'"
        )

    def load_meta_data(self, raw_data_dir: pathlib.Path, ds_id, spk, lang):
        meta_data_dict = {}
        trans_file = raw_data_dir / 'transcriptions.csv'
        log_bilingual(f"กำลังอ่านข้อมูลกำกับเสียง: {trans_file}", f"Loading metadata: {trans_file}")
        
        with open(trans_file, 'r', encoding='utf-8') as f:
            for utterance_label in csv.DictReader(f):
                item_name = utterance_label['name']
                wav_fn = None
                for ext in WAV_CANDIDATE_EXTENSIONS:
                    candidate_fn = raw_data_dir / 'wavs' / f'{item_name}{ext}'
                    if candidate_fn.exists():
                        wav_fn = candidate_fn
                        break
                if wav_fn is None:
                    raise FileNotFoundError(
                        f"| [ERROR] ไม่พบไฟล์เสียงสำหรับ '{item_name}'. นามสกุลที่รองรับ: {WAV_CANDIDATE_EXTENSIONS} "
                        f"/ Waveform file not found for '{item_name}'."
                    )
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
                        for p in utterance_label['ph_seq'].split()
                    ],
                    'ph_seq': self.phoneme_dictionary.encode(utterance_label['ph_seq'], lang=lang),
                    'ph_dur': [float(x) for x in utterance_label['ph_dur'].split()],
                    'ph_text': utterance_label['ph_seq'],
                }
                
                if len(temp_dict['ph_seq']) != len(temp_dict['ph_dur']):
                    raise ValueError(f"| [ERROR] ความยาวของ ph_seq และ ph_dur ไม่ตรงกันใน '{item_name}' / Sequence length mismatch.")
                if not all(ph_dur >= 0 for ph_dur in temp_dict['ph_dur']):
                    raise ValueError(f"| [ERROR] พบค่าความยาวเสียงติดลบใน '{item_name}' / Negative duration values detected.")
                    
                meta_data_dict[f'{ds_id}:{item_name}'] = temp_dict

        log_bilingual(
            f"โหลดข้อมูลกำกับเสียงเรียบร้อย: รวม {len(meta_data_dict)} รายการ",
            f"Metadata loaded successfully: Total {len(meta_data_dict)} items."
        )
        return meta_data_dict

    @torch.no_grad()
    def process_item(self, item_name, meta_data, binarization_args):
        try:
            waveform, _ = librosa.load(meta_data['wav_fn'], sr=hparams['audio_sample_rate'], mono=True)
            mel = get_mel_torch(
                waveform, hparams['audio_sample_rate'], num_mel_bins=hparams['audio_num_mel_bins'],
                hop_size=hparams['hop_size'], win_size=hparams['win_size'], fft_size=hparams['fft_size'],
                fmin=hparams['fmin'], fmax=hparams['fmax'],
                device=self.device
            )
            length = mel.shape[0]
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
                log_bilingual("เริ่มต้นโหลดตัวสกัดระดับเสียง...", "Initializing Pitch Extractor...")
                pitch_extractor = initialize_pe()
                
            gt_f0, uv = pitch_extractor.get_pitch(
                waveform, samplerate=hparams['audio_sample_rate'], length=length,
                hop_size=hparams['hop_size'], f0_min=hparams['f0_min'], f0_max=hparams['f0_max'],
                interp_uv=True
            )
            if uv.all():
                log_bilingual(
                    f"ข้ามไฟล์ '{item_name}': ไม่พบสัญญาณเสียงที่มีระดับเสียง",
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
                        f"ข้ามไฟล์ '{item_name}': ค่า Tension ผิดปกติ (NaN)",
                        f"Skipped '{item_name}': Tension is NaN."
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
        aug_pe = initialize_pe()
        
        log_bilingual(
            "เริ่มต้นกระบวนการเพิ่มความหลากหลายของข้อมูล (Data Augmentation Check)",
            "Initializing Data Augmentation process."
        )
        
        if self.augmentation_args['random_pitch_shifting']['enabled']:
            from augmentation.spec_stretch import SpectrogramStretchAugmentation
            aug_args = self.augmentation_args['random_pitch_shifting']
            key_shift_min, key_shift_max = aug_args['range']
            
            if not hparams['use_key_shift_embed']:
                raise ValueError("| [ERROR] Random pitch shifting requires use_key_shift_embed == True.")
            if not (key_shift_min < 0 < key_shift_max):
                raise ValueError("| [ERROR] Range must be min < 0 < max.")

            aug_ins = SpectrogramStretchAugmentation(self.raw_data_dirs, aug_args, pe=aug_pe)
            scale = aug_args['scale']
            aug_item_names = random.choices(all_item_names, k=int(scale * len(all_item_names)))

            for aug_item_name in aug_item_names:
                rand = random.uniform(-1, 1)
                key_shift = key_shift_min * abs(rand) if rand < 0 else key_shift_max * rand
                aug_task = {'name': aug_item_name, 'func': aug_ins.process_item, 'kwargs': {'key_shift': key_shift}}
                if aug_item_name in aug_map:
                    aug_map[aug_item_name].append(aug_task)
                else:
                    aug_map[aug_item_name] = [aug_task]
                aug_list.append(aug_task)
            total_scale += scale
            
            log_bilingual(
                f"กำหนดภารกิจ Random Pitch Shifting สำเร็จ: {len(aug_list)} งาน",
                f"Random Pitch Shifting tasks scheduled successfully: {len(aug_list)} tasks."
            )

        return aug_map