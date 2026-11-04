# ==============================================================================
# Date: 25 ตุลาคม พ.ศ. 2569 / 25 October 2026
# File Name: variance_task.py
# Version: 1.6
# Credit: Made And Checked By DELTA SYNTH & All Code Agentic AI Engine
#         Original by DiffSinger Project
# Location: training/variance_task.py
# Description: ภารกิจฝึกสอนโมเดลความแปรปรวนเสียง Variance Task เพิ่มระบบแจ้งเตือนสองภาษา และระบบจัดการ VRAM แบบเรียลไทม์
# ==============================================================================

import gc
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
from modules.losses import DurationLoss, DiffusionLoss, RectifiedFlowLoss
from modules.metrics import (
    RawCurveAccuracy, RawCurveR2Score, RhythmCorrectness, PhonemeDurationAccuracy
)
from modules.toplevel import DiffSingerVariance
from utils.hparams import hparams
from utils.plot import dur_to_figure, pitch_note_to_figure, curve_to_figure

matplotlib.use('Agg')


class VarianceDataset(BaseDataset):
    def __init__(self, prefix, preload=False):
        super(VarianceDataset, self).__init__(prefix, hparams['dataset_size_key'], preload)
        need_energy = hparams.get('predict_energy', False)
        need_breathiness = hparams.get('predict_breathiness', False)
        need_voicing = hparams.get('predict_voicing', False)
        need_tension = hparams.get('predict_tension', False)
        self.predict_variances = need_energy or need_breathiness or need_voicing or need_tension

    def collater(self, samples):
        batch = super().collater(samples)
        if batch['size'] == 0:
            return batch

        tokens = utils.collate_nd([s['tokens'] for s in samples], 0)
        ph_dur = utils.collate_nd([s['ph_dur'] for s in samples], 0)
        batch.update({
            'tokens': tokens,
            'ph_dur': ph_dur
        })

        if hparams.get('use_spk_id', False):
            batch['spk_ids'] = torch.LongTensor([s['spk_id'] for s in samples])
        if hparams.get('use_lang_id', False):
            batch['languages'] = utils.collate_nd([s['languages'] for s in samples], 0)
        if hparams.get('predict_dur', False):
            batch['ph2word'] = utils.collate_nd([s['ph2word'] for s in samples], 0)
            batch['midi'] = utils.collate_nd([s['midi'] for s in samples], 0)
        if hparams.get('predict_pitch', False):
            batch['note_midi'] = utils.collate_nd([s['note_midi'] for s in samples], -1)
            batch['note_rest'] = utils.collate_nd([s['note_rest'] for s in samples], True)
            batch['note_dur'] = utils.collate_nd([s['note_dur'] for s in samples], 0)
            if hparams.get('use_glide_embed', False):
                batch['note_glide'] = utils.collate_nd([s['note_glide'] for s in samples], 0)
            batch['mel2note'] = utils.collate_nd([s['mel2note'] for s in samples], 0)
            batch['base_pitch'] = utils.collate_nd([s['base_pitch'] for s in samples], 0)
        if hparams.get('predict_pitch', False) or self.predict_variances:
            batch['mel2ph'] = utils.collate_nd([s['mel2ph'] for s in samples], 0)
            batch['pitch'] = utils.collate_nd([s['pitch'] for s in samples], 0)
            batch['uv'] = utils.collate_nd([s['uv'] for s in samples], True)
        if hparams.get('predict_energy', False):
            batch['energy'] = utils.collate_nd([s['energy'] for s in samples], 0)
        if hparams.get('predict_breathiness', False):
            batch['breathiness'] = utils.collate_nd([s['breathiness'] for s in samples], 0)
        if hparams.get('predict_voicing', False):
            batch['voicing'] = utils.collate_nd([s['voicing'] for s in samples], 0)
        if hparams.get('predict_tension', False):
            batch['tension'] = utils.collate_nd([s['tension'] for s in samples], 0)

        return batch


def random_retake_masks(b, t, device):
    B_masks = torch.randint(low=0, high=4, size=(b, 1), dtype=torch.long, device=device) == 0
    T_masks = utils.random_continuous_masks(b, t, dim=1, device=device)
    return B_masks | T_masks


class VarianceTask(BaseTask):
    def __init__(self):
        super().__init__()
        self.dataset_cls = VarianceDataset

        self.diffusion_type = hparams.get('diffusion_type', 'ddpm')
        self.use_spk_id = hparams.get('use_spk_id', False)
        self.use_lang_id = hparams.get('use_lang_id', False)

        self.predict_dur = hparams.get('predict_dur', False)
        if self.predict_dur:
            self.lambda_dur_loss = hparams['lambda_dur_loss']

        self.predict_pitch = hparams.get('predict_pitch', False)
        if self.predict_pitch:
            self.lambda_pitch_loss = hparams['lambda_pitch_loss']

        self.variance_prediction_list = []
        if hparams.get('predict_energy', False):
            self.variance_prediction_list.append('energy')
        if hparams.get('predict_breathiness', False):
            self.variance_prediction_list.append('breathiness')
        if hparams.get('predict_voicing', False):
            self.variance_prediction_list.append('voicing')
        if hparams.get('predict_tension', False):
            self.variance_prediction_list.append('tension')
            
        self.predict_variances = len(self.variance_prediction_list) > 0
        self.lambda_var_loss = hparams.get('lambda_var_loss', 1.0)
        super()._finish_init()

        # Fuse LYNXNet2 backbone kernels
        self._fused_kernels_patched = 0
        self._fused_kernel_backbones = []
        if hparams.get('use_fused_kernels', False):
            try:
                from modules.backbones.lynxnet2 import LYNXNet2
                from modules.kernels.integration import patch_diffusion_module
                from lightning.pytorch.utilities.rank_zero import rank_zero_info
                
                for predictor_attr, args_key in (
                    ('pitch_predictor', 'pitch_prediction_args'),
                    ('variance_predictor', 'variances_prediction_args'),
                ):
                    predictor = getattr(self.model, predictor_attr, None)
                    if predictor is None:
                        continue
                    glu = (hparams.get(args_key) or {}).get('backbone_args', {}).get('glu_type', 'swiglu')
                    n = patch_diffusion_module(predictor, glu_type=glu)
                    self._fused_kernels_patched += n
                    
                    if n > 0:
                        for attr in ('denoise_fn', 'velocity_fn'):
                            backbone = getattr(predictor, attr, None)
                            if isinstance(backbone, LYNXNet2):
                                self._fused_kernel_backbones.append(backbone)
                    rank_zero_info(
                        f'| [SUCCESS / สำเร็จ] Fused kernels patched: {n} blocks in {predictor_attr}'
                    )
            except ImportError as e:
                from lightning.pytorch.utilities.rank_zero import rank_zero_info
                rank_zero_info(f'| [WARN / คำเตือน] Fused kernels unavailable: {e}')
            except Exception as e:
                from lightning.pytorch.utilities.rank_zero import rank_zero_info
                rank_zero_info(f'| [ERROR / ข้อผิดพลาด] Unexpected error in Variance kernels: {e}')

    def on_fit_start(self):
        if self._fused_kernels_patched > 0 and self.device.type == 'cuda':
            try:
                from modules.kernels.integration import warmup_fused_backbones
                from lightning.pytorch.utilities.rank_zero import rank_zero_info
                
                warmup_fused_backbones(
                    self._fused_kernel_backbones,
                    max_frames=hparams['max_batch_frames'],
                    precision=self.trainer.precision,
                )
                rank_zero_info('| [SUCCESS / สำเร็จ] Variance GPU Kernels warmed up successfully / เตรียมพร้อมระบบประมวลผล Variance เรียบร้อย')
            except Exception as e:
                print(f"| [WARN / คำเตือน] Warmup exception caught: {e}")

    def _build_model(self):
        return DiffSingerVariance(
            vocab_size=len(self.phoneme_dictionary),
        )

    def build_losses_and_metrics(self):
        if self.predict_dur:
            dur_hparams = hparams['dur_prediction_args']
            self.dur_loss = DurationLoss(
                offset=dur_hparams['log_offset'],
                loss_type=dur_hparams['loss_type'],
                lambda_pdur=dur_hparams['lambda_pdur_loss'],
                lambda_wdur=dur_hparams['lambda_wdur_loss'],
                lambda_sdur=dur_hparams['lambda_sdur_loss']
            )
            self.register_validation_loss('dur_loss')
            self.register_validation_metric('rhythm_corr', RhythmCorrectness(tolerance=0.05))
            self.register_validation_metric('ph_dur_acc', PhonemeDurationAccuracy(tolerance=0.2))
            
        if self.predict_pitch:
            if self.diffusion_type == 'ddpm':
                self.pitch_loss = DiffusionLoss(loss_type=hparams['main_loss_type'])
            elif self.diffusion_type == 'reflow':
                self.pitch_loss = RectifiedFlowLoss(
                    loss_type=hparams['main_loss_type'], log_norm=hparams.get('main_loss_log_norm', False)
                )
            else:
                raise ValueError(f'| [ERROR / ข้อผิดพลาด] Unknown diffusion type / ไม่รู้จักรูปแบบ: {self.diffusion_type}')
            self.register_validation_loss('pitch_loss')
            self.register_validation_metric('pitch_acc', RawCurveAccuracy(tolerance=0.5))
            self.register_validation_metric('pitch_r2', RawCurveR2Score())
            
        if self.predict_variances:
            if self.diffusion_type == 'ddpm':
                self.var_loss = DiffusionLoss(loss_type=hparams['main_loss_type'])
            elif self.diffusion_type == 'reflow':
                self.var_loss = RectifiedFlowLoss(
                    loss_type=hparams['main_loss_type'], log_norm=hparams.get('main_loss_log_norm', False)
                )
            else:
                raise ValueError(f'| [ERROR / ข้อผิดพลาด] Unknown diffusion type / ไม่รู้จักรูปแบบ: {self.diffusion_type}')
            self.register_validation_loss('var_loss')
            for name in self.variance_prediction_list:
                self.register_validation_metric(f'{name}_r2', RawCurveR2Score())

    def run_model(self, sample, infer=False):
        spk_ids = sample.get('spk_ids') if self.use_spk_id else None
        languages = sample.get('languages') if self.use_lang_id else None
        txt_tokens = sample['tokens']
        ph_dur = sample['ph_dur']
        ph2word = sample.get('ph2word')
        midi = sample.get('midi')
        mel2ph = sample.get('mel2ph')

        note_midi = sample.get('note_midi')
        note_rest = sample.get('note_rest')
        note_dur = sample.get('note_dur')
        note_glide = sample.get('note_glide')
        mel2note = sample.get('mel2note')

        base_pitch = sample.get('base_pitch')
        pitch = sample.get('pitch')
        energy = sample.get('energy')
        breathiness = sample.get('breathiness')
        voicing = sample.get('voicing')
        tension = sample.get('tension')

        pitch_retake = variance_retake = None
        if (self.predict_pitch or self.predict_variances) and not infer and mel2ph is not None:
            b = sample['size']
            t = mel2ph.shape[1]
            device = mel2ph.device
            if self.predict_pitch:
                pitch_retake = random_retake_masks(b, t, device)
            if self.predict_variances:
                variance_retake = {
                    v_name: random_retake_masks(b, t, device)
                    for v_name in self.variance_prediction_list
                }

        output = self.model(
            txt_tokens, languages=languages,
            midi=midi, ph2word=ph2word,
            ph_dur=ph_dur, mel2ph=mel2ph,
            note_midi=note_midi, note_rest=note_rest,
            note_dur=note_dur, note_glide=note_glide, mel2note=mel2note,
            base_pitch=base_pitch, pitch=pitch,
            energy=energy, breathiness=breathiness, voicing=voicing, tension=tension,
            pitch_retake=pitch_retake, variance_retake=variance_retake,
            spk_id=spk_ids, infer=infer
        )

        dur_pred, pitch_pred, variances_pred = output
        
        if infer:
            if dur_pred is not None:
                dur_pred = dur_pred.round().long()
            return dur_pred, pitch_pred, variances_pred
        else:
            losses = {}
            if dur_pred is not None:
                losses['dur_loss'] = self.lambda_dur_loss * self.dur_loss(dur_pred, ph_dur, ph2word=ph2word)
                
            non_padding = (mel2ph > 0).unsqueeze(-1) if mel2ph is not None else None
            
            if pitch_pred is not None:
                if self.diffusion_type == 'ddpm':
                    pitch_x_recon, pitch_noise = pitch_pred
                    pitch_loss = self.pitch_loss(pitch_x_recon, pitch_noise, non_padding=non_padding)
                elif self.diffusion_type == 'reflow':
                    pitch_v_pred, pitch_v_gt, t = pitch_pred
                    pitch_loss = self.pitch_loss(pitch_v_pred, pitch_v_gt, t=t, non_padding=non_padding)
                else:
                    raise ValueError(f"| [ERROR] Unknown diffusion type: {self.diffusion_type}")
                losses['pitch_loss'] = self.lambda_pitch_loss * pitch_loss
                
            if variances_pred is not None:
                if self.diffusion_type == 'ddpm':
                    var_x_recon, var_noise = variances_pred
                    var_loss = self.var_loss(var_x_recon, var_noise, non_padding=non_padding)
                elif self.diffusion_type == 'reflow':
                    var_v_pred, var_v_gt, t = variances_pred
                    var_loss = self.var_loss(var_v_pred, var_v_gt, t=t, non_padding=non_padding)
                else:
                    raise ValueError(f"| [ERROR] Unknown diffusion type: {self.diffusion_type}")
                losses['var_loss'] = self.lambda_var_loss * var_loss

            return losses

    def _validation_step(self, sample, batch_idx):
        losses = self.run_model(sample, infer=False)
        if min(sample['indices']) < hparams['num_valid_plots']:
            def sample_get(key, idx, abs_idx):
                return sample[key][idx][:self.valid_dataset.metadata[key][abs_idx]].unsqueeze(0)

            dur_preds, pitch_preds, variances_preds = self.run_model(sample, infer=True)
            for i in range(len(sample['indices'])):
                data_idx = sample['indices'][i]
                if data_idx < hparams['num_valid_plots']:
                    if dur_preds is not None:
                        dur_len = self.valid_dataset.metadata['ph_dur'][data_idx]
                        tokens = sample_get('tokens', i, data_idx)
                        gt_dur = sample_get('ph_dur', i, data_idx)
                        pred_dur = dur_preds[i][:dur_len].unsqueeze(0)
                        ph2word = sample_get('ph2word', i, data_idx)
                        mask = tokens != 0
                        self.valid_metrics['rhythm_corr'].update(
                            pdur_pred=pred_dur, pdur_target=gt_dur, ph2word=ph2word, mask=mask
                        )
                        self.valid_metrics['ph_dur_acc'].update(
                            pdur_pred=pred_dur, pdur_target=gt_dur, ph2word=ph2word, mask=mask
                        )
                        self.plot_dur(
                            data_idx, gt_dur, pred_dur,
                            txt=self.valid_dataset.metadata['ph_texts'][data_idx].split()
                        )
                    if pitch_preds is not None:
                        pitch_len = self.valid_dataset.metadata['pitch'][data_idx]
                        pred_pitch = sample_get('base_pitch', i, data_idx) + pitch_preds[i][:pitch_len].unsqueeze(0)
                        gt_pitch = sample_get('pitch', i, data_idx)
                        mask = (sample_get('mel2ph', i, data_idx) > 0) & ~sample_get('uv', i, data_idx)
                        self.valid_metrics['pitch_acc'].update(pred=pred_pitch, target=gt_pitch, mask=mask)
                        self.valid_metrics['pitch_r2'].update(pred=pred_pitch, target=gt_pitch, mask=mask)
                        self.plot_pitch(
                            data_idx,
                            gt_pitch=gt_pitch,
                            pred_pitch=pred_pitch,
                            note_midi=sample_get('note_midi', i, data_idx),
                            note_dur=sample_get('note_dur', i, data_idx),
                            note_rest=sample_get('note_rest', i, data_idx)
                        )
                    for name in self.variance_prediction_list:
                        variance_len = self.valid_dataset.metadata[name][data_idx]
                        gt_variances = sample[name][i][:variance_len].unsqueeze(0)
                        pred_variances = variances_preds[name][i][:variance_len].unsqueeze(0)
                        mask = (sample_get('mel2ph', i, data_idx) > 0) & ~sample_get('uv', i, data_idx)
                        self.valid_metrics[f'{name}_r2'].update(pred=pred_variances, target=gt_variances, mask=mask)
                        self.plot_curve(
                            data_idx,
                            gt_curve=gt_variances,
                            pred_curve=pred_variances,
                            curve_name=name
                        )
        return losses, sample['size']

    def plot_dur(self, data_idx, gt_dur, pred_dur, txt=None):
        try:
            gt_dur = gt_dur[0].cpu().numpy()
            pred_dur = pred_dur[0].cpu().numpy()
            title_text = f"{self.valid_dataset.metadata['spk_names'][data_idx]} - {self.valid_dataset.metadata['names'][data_idx]}"
            fig = dur_to_figure(gt_dur, pred_dur, txt, title_text)
            self.logger.all_rank_experiment.add_figure(f'dur_{data_idx}', fig, self.global_step)
        except Exception:
            pass

    def plot_pitch(self, data_idx, gt_pitch, pred_pitch, note_midi, note_dur, note_rest):
        try:
            gt_pitch = gt_pitch[0].cpu().numpy()
            pred_pitch = pred_pitch[0].cpu().numpy()
            note_midi = note_midi[0].cpu().numpy()
            note_dur = note_dur[0].cpu().numpy()
            note_rest = note_rest[0].cpu().numpy()
            title_text = f"{self.valid_dataset.metadata['spk_names'][data_idx]} - {self.valid_dataset.metadata['names'][data_idx]}"
            fig = pitch_note_to_figure(gt_pitch, pred_pitch, note_midi, note_dur, note_rest, title_text)
            self.logger.all_rank_experiment.add_figure(f'pitch_{data_idx}', fig, self.global_step)
        except Exception:
            pass

    def plot_curve(self, data_idx, gt_curve, pred_curve, base_curve=None, grid=None, curve_name='curve'):
        try:
            gt_curve = gt_curve[0].cpu().numpy()
            pred_curve = pred_curve[0].cpu().numpy()
            if base_curve is not None:
                base_curve = base_curve[0].cpu().numpy()
            title_text = f"{self.valid_dataset.metadata['spk_names'][data_idx]} - {self.valid_dataset.metadata['names'][data_idx]}"
            fig = curve_to_figure(gt_curve, pred_curve, base_curve, grid=grid, title=title_text)
            self.logger.all_rank_experiment.add_figure(f'{curve_name}_{data_idx}', fig, self.global_step)
        except Exception:
            pass

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