# ==============================================================================
# Date: 2026-10-31
# File Name: variance_binarizer.py
# Version: 1.5
# Credit: Made And Checked By DELTA SYNTH & Staff
#         Original by DiffSinger Project
# Location: preprocessing/variance_binarizer.py
# Description: Variance Binarizer with standardized bilingual logging and robust VRAM safeguards.
# ==============================================================================

import csv
import json
import os
import pathlib
import gc
import traceback

import librosa
import numpy as np
import torch
import torch.nn.functional as F
from scipy import interpolate

from basics.base_binarizer import BaseBinarizer, BinarizationError
from basics.base_pe import BasePE
from modules.fastspeech.tts_modules import LengthRegulator
from modules.pe import initialize_pe
from utils.binarizer_utils import (
    SinusoidalSmoothingConv1d,
    get_mel2ph_torch,
    get_energy_librosa,
    get_breathiness,
    get_voicing,
    get_tension_base_harmonic,
)
from utils.decomposed_waveform import DecomposedWaveform
from utils.hparams import hparams
from utils.infer_utils import resample_align_curve
from utils.pitch_utils import interp_f0
from utils.plot import distribution_to_figure

os.environ["OMP_NUM_THREADS"] = "1"
VARIANCE_ITEM_ATTRIBUTES = [
    'spk_id', 'languages', 'tokens', 'ph_dur', 'midi', 'ph2word', 'mel2ph',
    'note_midi', 'note_rest', 'note_dur', 'note_glide', 'mel2note',
    'base_pitch', 'pitch', 'uv', 'energy', 'breathiness', 'voicing', 'tension'
]
WAV_CANDIDATE_EXTENSIONS = ['.wav', '.flac']
DS_INDEX_SEP = '#'

pitch_extractor: BasePE = None
midi_smooth: SinusoidalSmoothingConv1d = None
energy_smooth: SinusoidalSmoothingConv1d = None
breathiness_smooth: SinusoidalSmoothingConv1d = None
voicing_smooth: SinusoidalSmoothingConv1d = None
tension_smooth: SinusoidalSmoothingConv1d = None


def log_bilingual(th, en):
    """แสดงผลข้อความ 2 ภาษาตามมาตรฐานของ DELTA SYNTH"""
    print(f"[TH] {th}\n[EN] {en}", flush=True)


class VarianceBinarizer(BaseBinarizer):
    def __init__(self):
        super().__init__(data_attrs=VARIANCE_ITEM_ATTRIBUTES)

        self.use_glide_embed = hparams.get('use_glide_embed', False)
        glide_types = hparams.get('glide_types', [])
        
        if 'none' in glide_types:
            raise ValueError("| [ERROR] Type name 'none' is reserved in glide_types.")
            
        self.glide_map = {'none': 0, **{typename: idx + 1 for idx, typename in enumerate(glide_types)}}
        self.predict_variances = any(hparams.get(f'predict_{k}', False) for k in ['energy', 'breathiness', 'voicing', 'tension'])
        self.lr = LengthRegulator().to(self.device)
        self.prefer_ds = self.binarization_args.get('prefer_ds', False)
        self.cached_ds = {}
        
        log_bilingual(
            f"VarianceBinarizer เริ่มต้นสำเร็จ: Predict Variances={self.predict_variances}, Prefer DS={self.prefer_ds}",
            f"VarianceBinarizer Initialized: Predict Variances={self.predict_variances}, Prefer DS={self.prefer_ds}"
        )

    def load_attr_from_ds(self, ds_id, name, attr, idx=0):
        item_name = f'{ds_id}:{name}'
        item_name_with_idx = f'{item_name}{DS_INDEX_SEP}{idx}'
        if item_name_with_idx in self.cached_ds:
            ds = self.cached_ds[item_name_with_idx][0]
        elif item_name in self.cached_ds:
            ds = self.cached_ds[item_name][idx]
        else:
            ds_path = self.raw_data_dirs[ds_id] / 'ds' / f'{name}{DS_INDEX_SEP}{idx}.ds'
            cache_key = item_name_with_idx if ds_path.exists() else item_name
            if not ds_path.exists():
                ds_path = self.raw_data_dirs[ds_id] / 'ds' / f'{name}.ds'
            if not ds_path.exists():
                return None
            with open(ds_path, 'r', encoding='utf8') as f:
                ds = json.load(f)
            if not isinstance(ds, list):
                ds = [ds]
            self.cached_ds[cache_key] = ds
            ds = ds[0] if cache_key == item_name_with_idx else ds[idx]
        return ds.get(attr)

    def load_meta_data(self, raw_data_dir: pathlib.Path, ds_id, spk, lang):
        meta_data_dict = {}
        trans_file = raw_data_dir / 'transcriptions.csv'
        log_bilingual(f"โหลดข้อมูลกำกับสำหรับ Variance: {trans_file}", f"Loading Variance metadata: {trans_file}")

        with open(trans_file, 'r', encoding='utf8') as f:
            for utterance_label in csv.DictReader(f):
                item_name = utterance_label['name']
                item_base_name, *item_seg_idx = item_name.rsplit(DS_INDEX_SEP, maxsplit=1)
                item_idx = int(item_seg_idx[0]) if item_seg_idx else 0

                def require(attr, optional=False):
                    value = self.load_attr_from_ds(ds_id, item_base_name, attr, item_idx) if self.prefer_ds else None
                    if value is None:
                        value = utterance_label.get(attr)
                    if value is None and not optional:
                        raise ValueError(f"| [ERROR] คุณลักษณะ '{attr}' ขาดหายไปใน '{item_name}' / Missing required attribute.")
                    return value

                wav_fn = next((raw_data_dir / 'wavs' / f'{item_name}{ext}' for ext in WAV_CANDIDATE_EXTENSIONS if (raw_data_dir / 'wavs' / f'{item_name}{ext}').exists()), None)
                if wav_fn is None and not self.prefer_ds:
                    raise FileNotFoundError(f"| [ERROR] ไม่พบไฟล์เสียงสำหรับ '{item_name}' / Waveform file not found.")

                temp_dict = {
                    'ds_idx': item_idx, 'spk_id': self.spk_map[spk], 'spk_name': spk,
                    'language_id': self.lang_map[lang], 'language_name': lang,
                    'wav_fn': str(wav_fn) if wav_fn is not None else None,
                    'lang_seq': [(self.lang_map[lang if '/' not in p else p.split('/', maxsplit=1)[0]] if self.phoneme_dictionary.is_cross_lingual(p if '/' in p else f'{lang}/{p}') else 0) for p in require('ph_seq').split()],
                    'ph_seq': self.phoneme_dictionary.encode(require('ph_seq'), lang=lang),
                    'ph_dur': [float(x) for x in require('ph_dur').split()],
                    'ph_text': require('ph_seq'),
                }
                meta_data_dict[f'{ds_id}:{item_name}'] = temp_dict
        
        log_bilingual(
            f"โหลดข้อมูลกำกับ Variance สำเร็จ: รวม {len(meta_data_dict)} รายการ",
            f"Variance metadata loaded successfully: Total {len(meta_data_dict)} items."
        )
        return meta_data_dict

    def check_coverage(self):
        super().check_coverage()
        if not hparams.get('predict_pitch', False):
            return
        
        midi_map = {}
        for item_name in self.items:
            for midi in self.items[item_name].get('note_seq', []):
                if midi != 'rest':
                    m = librosa.note_to_midi(midi, round_midi=True)
                    midi_map[m] = midi_map.get(m, 0) + 1
                    
        log_bilingual(
            "===== สรุปการกระจายตัวของระดับเสียง (MIDI Pitch Distribution Summary) =====",
            "===== MIDI Pitch Distribution Summary ====="
        )
        
        if midi_map:
            midis = sorted(midi_map.keys())
            notes = [librosa.midi_to_note(m, unicode=False) for m in range(midis[0], midis[-1] + 1)]
            plt = distribution_to_figure('MIDI Pitch Distribution Summary', 'MIDI Key', 'Occurrences', notes, [midi_map.get(m, 0) for m in range(midis[0], midis[-1] + 1)])
            filename = self.binary_data_dir / 'midi_distribution.jpg'
            plt.savefig(fname=filename, bbox_inches='tight', pad_inches=0.25)
            log_bilingual(
                f"บันทึกกราฟการกระจายระดับเสียงที่: '{filename}'",
                f"Saved pitch distribution plot to: '{filename}'"
            )

    @torch.no_grad()
    def process_item(self, item_name, meta_data, binarization_args):
        try:
            ds_id, name = item_name.split(':', maxsplit=1)
            name = name.rsplit(DS_INDEX_SEP, maxsplit=1)[0]
            ds_id, ds_seg_idx = int(ds_id), meta_data['ds_idx']
            seconds = sum(meta_data['ph_dur'])
            processed_input = {
                'name': item_name, 'wav_fn': meta_data['wav_fn'], 'spk_id': meta_data['spk_id'],
                'spk_name': meta_data['spk_name'], 'seconds': seconds,
                'languages': np.array(meta_data['lang_seq'], dtype=np.int64),
                'tokens': np.array(meta_data['ph_seq'], dtype=np.int64),
                'ph_text': meta_data['ph_text'],
            }

            ph_dur_sec = torch.FloatTensor(meta_data['ph_dur']).to(self.device)
            ph_acc = torch.round(torch.cumsum(ph_dur_sec, dim=0) / self.timestep + 0.5).long()
            ph_dur = torch.diff(ph_acc, dim=0, prepend=torch.LongTensor([0]).to(self.device))
            length = int(ph_acc[-1])
            processed_input['ph_dur'] = ph_dur.cpu().numpy()
            processed_input['length'] = length
            mel2ph = get_mel2ph_torch(self.lr, ph_dur_sec, length, self.timestep, device=self.device)

            if hparams.get('predict_pitch', False) or self.predict_variances:
                processed_input['mel2ph'] = mel2ph.cpu().numpy()

            waveform = None
            if meta_data['wav_fn'] is not None:
                waveform, _ = librosa.load(meta_data['wav_fn'], sr=hparams['audio_sample_rate'], mono=True)

            global pitch_extractor
            if pitch_extractor is None:
                pitch_extractor = initialize_pe()
            f0 = uv = None
            
            if f0 is None and waveform is not None:
                f0, uv = pitch_extractor.get_pitch(
                    waveform, samplerate=hparams['audio_sample_rate'], length=length,
                    hop_size=hparams['hop_size'], f0_min=hparams['f0_min'], f0_max=hparams['f0_max'],
                    interp_uv=True
                )
            if uv is not None and uv.all():
                log_bilingual(
                    f"ข้ามไฟล์ '{item_name}': ไม่พบค่า F0",
                    f"Skipped '{item_name}': empty ground truth f0"
                )
                return None
                
            if f0 is not None:
                pitch = torch.from_numpy(librosa.hz_to_midi(f0.astype(np.float32)).astype(np.float32)).to(self.device)
                if hparams.get('predict_pitch', False) or self.predict_variances:
                    processed_input['pitch'] = pitch.cpu().numpy()
                    processed_input['uv'] = uv
            return processed_input

        except Exception as e:
            log_bilingual(
                f"เกิดข้อผิดพลาดในการประมวลผล Variance Item '{item_name}': {e}",
                f"Error processing Variance Item '{item_name}': {e}"
            )
            traceback.print_exc()
            return None
        finally:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                gc.collect()

    def arrange_data_augmentation(self, data_iterator):
        return {}