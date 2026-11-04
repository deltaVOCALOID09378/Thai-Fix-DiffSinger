# ==============================================================================
# Date: 25 ตุลาคม พ.ศ. 2569 / 25 October 2026
# File Name: acoustic_task.py
# Version: 1.6
# Credit: Made And Checked By DELTA SYNTH & All Code Agentic AI Engine
#         Original by DiffSinger Project
# Location: training/acoustic_task.py
# Description: ภารกิจฝึกสอนโมเดลเนื้อเสียง Acoustic Task อัปเกรดระบบแจ้งเตือนสองภาษา และบังคับใช้ VRAM Safety Protocol
# ==============================================================================

import gc
import math
import matplotlib
import torch
import torch.distributions
import torch.optim
import torch.utils.data
import traceback

import utils
import utils.infer_utils
from basics.base_dataset import BaseDataset
from basics.base_task import BaseTask
from basics.base_vocoder import BaseVocoder
from modules.aux_decoder import build_aux_loss
from modules.losses import DiffusionLoss, RectifiedFlowLoss
from modules.toplevel import DiffSingerAcoustic, ShallowDiffusionOutput
from modules.vocoders.registry import get_vocoder_cls
from utils.hparams import hparams
from utils.plot import spec_to_figure

matplotlib.use('Agg')


class AcousticDataset(BaseDataset):
    def __init__(self, prefix, preload=False):
        super(AcousticDataset, self).__init__(prefix, hparams['dataset_size_key'], preload)
        self.required_variances = {}
        if hparams.get('use_energy_embed', False):
            self.required_variances['energy'] = 0.0
        if hparams.get('use_breathiness_embed', False):
            self.required_variances['breathiness'] = 0.0
        if hparams.get('use_voicing_embed', False):
            self.required_variances['voicing'] = 0.0
        if hparams.get('use_tension_embed', False):
            self.required_variances['tension'] = 0.0

        self.need_key_shift = hparams.get('use_key_shift_embed', False)
        self.need_speed = hparams.get('use_speed_embed', False)
        self.need_spk_id = hparams.get('use_spk_id', False)
        self.need_lang_id = hparams.get('use_lang_id', False)

    def collater(self, samples):
        batch = super().collater(samples)
        if batch['size'] == 0:
            return batch

        tokens = utils.collate_nd([s['tokens'] for s in samples], 0)
        f0 = utils.collate_nd([s['f0'] for s in samples], 0.0)
        mel2ph = utils.collate_nd([s['mel2ph'] for s in samples], 0)
        mel = utils.collate_nd([s['mel'] for s in samples], math.log(1e-5))
        batch.update({
            'tokens': tokens,
            'mel2ph': mel2ph,
            'mel': mel,
            'f0': f0,
        })
        for v_name, v_pad in self.required_variances.items():
            batch[v_name] = utils.collate_nd([s[v_name] for s in samples], v_pad)
        if self.need_key_shift:
            batch['key_shift'] = torch.FloatTensor([s['key_shift'] for s in samples])[:, None]
        if self.need_speed:
            batch['speed'] = torch.FloatTensor([s['speed'] for s in samples])[:, None]
        if self.need_spk_id:
            batch['spk_ids'] = torch.LongTensor([s['spk_id'] for s in samples])
        if self.need_lang_id:
            batch['languages'] = utils.collate_nd([s['languages'] for s in samples], 0)
        return batch


class AcousticTask(BaseTask):
    def __init__(self):
        super().__init__()
        self.dataset_cls = AcousticDataset
        self.diffusion_type = hparams.get('diffusion_type', 'ddpm')
        assert self.diffusion_type in ['ddpm', 'reflow'], f"| [ERROR] Unknown diffusion type / ไม่รู้จักรูปแบบ Diffusion นี้: {self.diffusion_type}"
        self.use_shallow_diffusion = hparams.get('use_shallow_diffusion', False)
        
        if self.use_shallow_diffusion:
            self.shallow_args = hparams['shallow_diffusion_args']
            self.train_aux_decoder = self.shallow_args['train_aux_decoder']
            self.train_diffusion = self.shallow_args['train_diffusion']

        self.use_vocoder = hparams.get('infer', False) or hparams.get('val_with_vocoder', False)
        if self.use_vocoder:
            self.vocoder: BaseVocoder = get_vocoder_cls(hparams)()
            
        self.logged_gt_wav = set()
        self.required_variances = []
        if hparams.get('use_energy_embed', False):
            self.required_variances.append('energy')
        if hparams.get('use_breathiness_embed', False):
            self.required_variances.append('breathiness')
        if hparams.get('use_voicing_embed', False):
            self.required_variances.append('voicing')
        if hparams.get('use_tension_embed', False):
            self.required_variances.append('tension')
        super()._finish_init()

        # Fuse LYNXNet2 backbone kernels with Safe Error Handling
        self._fused_kernels_patched = 0
        if hparams.get('use_fused_kernels', False):
            try:
                from modules.kernels.integration import patch_diffusion_module
                from lightning.pytorch.utilities.rank_zero import rank_zero_info
                
                glu_type = hparams.get('backbone_args', {}).get('glu_type', 'swiglu')
                self._fused_kernels_patched = patch_diffusion_module(
                    self.model.diffusion,
                    glu_type=glu_type,
                )
                rank_zero_info(f'| [SUCCESS / สำเร็จ] Fused kernels patched: {self._fused_kernels_patched} LYNXNet2 blocks / แพตช์ระบบสำเร็จ')
            except ImportError as e:
                from lightning.pytorch.utilities.rank_zero import rank_zero_info
                rank_zero_info(f'| [WARN / คำเตือน] Fused kernels unavailable (Running Eager Mode): {e}')
            except Exception as e:
                from lightning.pytorch.utilities.rank_zero import rank_zero_info
                rank_zero_info(f'| [ERROR / ข้อผิดพลาด] Unexpected error in Fused kernels: {e}')

    def on_fit_start(self):
        if self._fused_kernels_patched > 0 and self.device.type == 'cuda':
            try:
                from modules.kernels.integration import warmup_fused_backbones
                from lightning.pytorch.utilities.rank_zero import rank_zero_info
                
                backbones = [
                    backbone for attr in ('denoise_fn', 'velocity_fn')
                    if (backbone := getattr(self.model.diffusion, attr, None)) is not None
                ]
                warmup_fused_backbones(
                    backbones,
                    max_frames=hparams['max_batch_frames'],
                    precision=self.trainer.precision,
                )
                rank_zero_info('| [SUCCESS / สำเร็จ] GPU Kernels warmed up successfully / เตรียมความพร้อมหน่วยประมวลผล GPU เรียบร้อย')
            except Exception as e:
                print(f"| [WARN / คำเตือน] Kernel warmup failed gracefully: {e}")

    def _build_model(self):
        return DiffSingerAcoustic(
            vocab_size=len(self.phoneme_dictionary),
            out_dims=hparams['audio_num_mel_bins']
        )

    def build_losses_and_metrics(self):
        if self.use_shallow_diffusion:
            self.aux_mel_loss = build_aux_loss(self.shallow_args['aux_decoder_arch'])
            self.lambda_aux_mel_loss = hparams['lambda_aux_mel_loss']
            self.register_validation_loss('aux_mel_loss')
            
        if self.diffusion_type == 'ddpm':
            self.mel_loss = DiffusionLoss(loss_type=hparams['main_loss_type'])
        elif self.diffusion_type == 'reflow':
            self.mel_loss = RectifiedFlowLoss(
                loss_type=hparams['main_loss_type'], log_norm=hparams['main_loss_log_norm']
            )
        else:
            raise ValueError(f"| [ERROR / ข้อผิดพลาด] Unknown diffusion type / ไม่รู้จักรูปแบบ Diffusion นี้: {self.diffusion_type}")
        self.register_validation_loss('mel_loss')

    def run_model(self, sample, infer=False):
        txt_tokens = sample['tokens']
        target = sample['mel']
        mel2ph = sample['mel2ph']
        f0 = sample['f0']
        languages = sample.get('languages')
        key_shift = sample.get('key_shift')
        speed = sample.get('speed')
        spk_id = sample.get('spk_ids')
        variances = {v_name: sample[v_name] for v_name in self.required_variances}

        output = self.model(
            txt_tokens, mel2ph=mel2ph, f0=f0, key_shift=key_shift, speed=speed,
            spk_id=spk_id, languages=languages, variances=variances,
            gt_spec=target, infer=infer
        )
        return output

    def _training_step(self, sample):
        losses = {}
        output = self.run_model(sample, infer=False)
        
        if self.use_shallow_diffusion:
            aux_out, diff_out = output
            if self.train_aux_decoder:
                losses['aux_mel_loss'] = self.lambda_aux_mel_loss * self.aux_mel_loss(aux_out, sample['mel'])
            if self.train_diffusion:
                losses['mel_loss'] = self.mel_loss(diff_out, sample['mel'])
        else:
            losses['mel_loss'] = self.mel_loss(output, sample['mel'])
            
        return losses

    def on_train_epoch_end(self):
        super().on_train_epoch_end()
        # VRAM Safety Protocol Enforcement
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def on_validation_epoch_end(self):
        super().on_validation_epoch_end()
        # DELTA VRAM Cleanup Optimization
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()