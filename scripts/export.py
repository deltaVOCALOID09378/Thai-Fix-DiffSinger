# ==============================================================================
# Date: 25/10/2026
# File Name: export_2.py
# Version: 1.2
# Location: Root Directory
# Credit: Made And Checked By DELTA SYNTH & All Code Agentic AI Engine
#         Original by DiffSinger Project
# Description: DiffSinger ONNX Exporter with emb & dsconfig.yaml generation, fixed encoding and added VRAM safety.
# ==============================================================================
import os
import pathlib
import re
import sys
import traceback
import gc
from typing import List

import click
import torch
import yaml

root_dir = pathlib.Path(__file__).resolve().parent.parent
os.environ['PYTHONPATH'] = str(root_dir)
sys.path.insert(0, str(root_dir))

from utils.hparams import set_hparams, hparams

def find_exp(exp):
    if not (root_dir / 'checkpoints' / exp).exists():
        for subdir in (root_dir / 'checkpoints').iterdir():
            if not subdir.is_dir():
                continue
            if subdir.name.startswith(exp):
                print(f'| match ckpt by prefix: {subdir.name}')
                exp = subdir.name
                break
        else:
            raise click.BadParameter(
                f'There are no matching exp starting with \'{exp}\' in \'checkpoints\' folder. '
                'Please specify \'--exp\' as the folder name or prefix.'
            )
    else:
        print(f'| found ckpt by name: {exp}')
    return exp


def generate_extra_artifacts(exp_name, out_dir, ckpt_steps=None):
    """
    Generate missing dsconfig.yaml and .emb (Multi-speaker) after ONNX export.
    """
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Generate dsconfig.yaml
    dsconfig_path = out_dir / 'dsconfig.yaml'
    if not dsconfig_path.exists():
        print(f'| Generating missing dsconfig.yaml at {dsconfig_path}')
        dsconfig = {
            'phonemes': 'dictionary.txt',
            'acoustic': f'{exp_name}.onnx',
            'vocoder': 'nsf_hifigan.onnx',
            'hidden_size': hparams.get('hidden_size', 256),
            'use_spk_id': hparams.get('use_spk_id', False),
            'use_energy_embed': hparams.get('use_energy_embed', False),
            'use_breathiness_embed': hparams.get('use_breathiness_embed', False),
            'use_key_shift_embed': hparams.get('use_key_shift_embed', False),
            'use_speed_embed': hparams.get('use_speed_embed', False),
            'use_tension_embed': hparams.get('use_tension_embed', False),
            'use_voicing_embed': hparams.get('use_voicing_embed', False)
        }
        if hparams.get('use_spk_id', False):
            dsconfig['speakers'] = f'{exp_name}.emb'
            
        with open(dsconfig_path, 'w', encoding='utf-8') as f:
            yaml.dump(dsconfig, f, default_flow_style=False, sort_keys=False)
    else:
        print(f'| dsconfig.yaml already exists.')

    # 2. Generate .emb for Speaker ID
    if hparams.get('use_spk_id', False):
        emb_path = out_dir / f'{exp_name}.emb'
        if not emb_path.exists():
            print(f'| Generating missing .emb at {emb_path}')
            ckpt_dir = root_dir / 'checkpoints' / exp_name
            ckpt_file = None
            if ckpt_steps is not None:
                ckpt_file = ckpt_dir / f'model_ckpt_steps_{ckpt_steps}.ckpt'
            else:
                ckpts = list(ckpt_dir.glob('model_ckpt_steps_*.ckpt'))
                if ckpts:
                    ckpts.sort(key=lambda x: int(re.search(r'_(\d+)\.ckpt', x.name).group(1)))
                    ckpt_file = ckpts[-1]
            
            if ckpt_file and ckpt_file.exists():
                try:
                    cpt = torch.load(ckpt_file, map_location='cpu')
                    spk_weight = None
                    if 'state_dict' in cpt and 'model.spk_embed.weight' in cpt['state_dict']:
                        spk_weight = cpt['state_dict']['model.spk_embed.weight']
                    elif 'state_dict' in cpt and 'spk_embed.weight' in cpt['state_dict']:
                        spk_weight = cpt['state_dict']['spk_embed.weight']
                        
                    if spk_weight is not None:
                        spk_keys = hparams.get('spk_keys', [str(i) for i in range(spk_weight.shape[0])])
                        emb_dict = {}
                        for i, spk in enumerate(spk_keys):
                            if i < spk_weight.shape[0]:
                                emb_dict[spk] = spk_weight[i].cpu().numpy()
                        torch.save(emb_dict, emb_path)
                        print(f'| Successfully extracted and saved {exp_name}.emb')
                    else:
                        print('| Could not find speaker embeddings in the checkpoint.')
                except Exception as e:
                    print(f'| Error generating .emb: {e}')
            else:
                print('| No checkpoint found to extract .emb.')
        else:
            print(f'| .emb file already exists.')


def parse_spk_settings(export_spk, freeze_spk):
    if export_spk is None:
        export_spk = []
    else:
        export_spk = list(export_spk)
    from utils.infer_utils import parse_commandline_spk_mix
    spk_name_pattern = r'[0-9A-Za-z_-]+'
    export_spk_mix = []
    for spk in export_spk:
        assert '=' in spk or '|' not in spk, \
            'You must specify an alias with \'NAME=\' for each speaker mix.'
        if '=' in spk:
            alias, mix = spk.split('=', maxsplit=1)
            assert re.fullmatch(spk_name_pattern, alias) is not None, f'Invalid alias \'{alias}\' for speaker mix.'
            export_spk_mix.append((alias, parse_commandline_spk_mix(mix)))
        else:
            export_spk_mix.append((spk, {spk: 1.0}))
    freeze_spk_mix = None
    if freeze_spk is not None:
        assert '=' in freeze_spk or '|' not in freeze_spk, \
            'You must specify an alias with \'NAME=\' for each speaker mix.'
        if '=' in freeze_spk:
            alias, mix = freeze_spk.split('=', maxsplit=1)
            assert re.fullmatch(spk_name_pattern, alias) is not None, f'Invalid alias \'{alias}\' for speaker mix.'
            freeze_spk_mix = (alias, parse_commandline_spk_mix(mix))
        else:
            freeze_spk_mix = (freeze_spk, {freeze_spk: 1.0})
    return export_spk_mix, freeze_spk_mix


@click.group()
def main():
    pass


@main.command(help='Export DiffSinger acoustic model to ONNX format.')
@click.option(
    '--exp', type=click.STRING,
    required=True, metavar='EXP', callback=lambda ctx, param, value: find_exp(value),
    help='Choose an experiment to export.'
)
@click.option(
    '--ckpt', type=click.IntRange(min=0),
    required=False, metavar='STEPS',
    help='Checkpoint training steps.'
)
@click.option(
    '--out', type=click.Path(
        dir_okay=True, file_okay=False,
        path_type=pathlib.Path, resolve_path=True
    ),
    required=False,
    help='Output directory for the artifacts.'
)
@click.option(
    '--freeze_gender', type=click.FloatRange(min=-1, max=1),
    help='(for random pitch shifting) Freeze gender value into the model.'
)
@click.option(
    '--freeze_velocity', is_flag=True,
    help='(for random time stretching) Freeze default velocity value into the model.'
)
@click.option(
    '--export_spk', type=click.STRING,
    required=False, multiple=True,
    help='(for multi-speaker models) Export one or more speaker or speaker mixture keys.'
)
@click.option(
    '--freeze_spk', type=click.STRING,
    required=False,
    help='(for multi-speaker models) Freeze one speaker or speaker mixture into the model.'
)
def acoustic(
        exp: str,
        ckpt: int = None,
        out: pathlib.Path = None,
        freeze_gender: float = 0.,
        freeze_velocity: bool = False,
        export_spk: List[str] = None,
        freeze_spk: str = None
):
    if export_spk and freeze_spk:
        print('--export_spk is exclusive to --freeze_spk.')
        sys.exit(-1)
    if out is None:
        out = root_dir / 'artifacts' / exp
    export_spk_mix, freeze_spk_mix = parse_spk_settings(export_spk, freeze_spk)

    sys.argv = [
        sys.argv[0],
        '--exp_name',
        exp,
        '--infer'
    ]
    set_hparams()

    from deployment.exporters import DiffSingerAcousticExporter
    print(f'| Exporter: {DiffSingerAcousticExporter}')
    
    try:
        exporter = DiffSingerAcousticExporter(
            device=torch.device('cuda' if torch.cuda.is_available() else 'cpu'),
            cache_dir=root_dir / 'deployment' / 'cache',
            ckpt_steps=ckpt,
            freeze_gender=freeze_gender,
            freeze_velocity=freeze_velocity,
            export_spk=export_spk_mix,
            freeze_spk=freeze_spk_mix
        )
        exporter.export(out)
        generate_extra_artifacts(exp, out, ckpt)
    except KeyboardInterrupt:
        sys.exit(-1)
    except Exception as e:
        print(f"| [ERROR] Export acoustic failed: {e}")
        traceback.print_exc()
        sys.exit(-1)
    finally:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            gc.collect()


@main.command(help='Export DiffSinger variance model to ONNX format.')
@click.option(
    '--exp', type=click.STRING,
    required=True, metavar='EXP', callback=lambda ctx, param, value: find_exp(value),
    help='Choose an experiment to export.'
)
@click.option(
    '--ckpt', type=click.IntRange(min=0),
    required=False, metavar='STEPS',
    help='Checkpoint training steps.'
)
@click.option(
    '--out', type=click.Path(
        dir_okay=True, file_okay=False,
        path_type=pathlib.Path, resolve_path=True
    ),
    required=False,
    help='Output directory for the artifacts.'
)
@click.option(
    '--freeze_glide', is_flag=True,
    help='Freeze default glide embedding into the model.'
)
@click.option(
    '--freeze_expr', is_flag=True,
    help='Freeze default pitch expressiveness factor into the model.'
)
@click.option(
    '--export_spk', type=click.STRING,
    required=False, multiple=True,
    help='(for multi-speaker models) Export one or more speaker or speaker mixture keys.'
)
@click.option(
    '--freeze_spk', type=click.STRING,
    required=False,
    help='(for multi-speaker models) Freeze one speaker or speaker mixture into the model.'
)
def variance(
        exp: str,
        ckpt: int = None,
        out: str = None,
        freeze_glide: bool = False,
        freeze_expr: bool = False,
        export_spk: List[str] = None,
        freeze_spk: str = None
):
    if export_spk and freeze_spk:
        print('--export_spk is exclusive to --freeze_spk.')
        sys.exit(-1)
    if out is None:
        out = root_dir / 'artifacts' / exp
    export_spk_mix, freeze_spk_mix = parse_spk_settings(export_spk, freeze_spk)

    sys.argv = [
        sys.argv[0],
        '--exp_name',
        exp,
        '--infer'
    ]
    set_hparams()
    from deployment.exporters import DiffSingerVarianceExporter
    print(f'| Exporter: {DiffSingerVarianceExporter}')
    
    try:
        exporter = DiffSingerVarianceExporter(
            device=torch.device('cuda' if torch.cuda.is_available() else 'cpu'),
            cache_dir=root_dir / 'deployment' / 'cache',
            ckpt_steps=ckpt,
            freeze_glide=freeze_glide,
            freeze_expr=freeze_expr,
            export_spk=export_spk_mix,
            freeze_spk=freeze_spk_mix
        )
        exporter.export(out)
        generate_extra_artifacts(exp, out, ckpt)
    except KeyboardInterrupt:
        sys.exit(-1)
    except Exception as e:
        print(f"| [ERROR] Export variance failed: {e}")
        traceback.print_exc()
        sys.exit(-1)
    finally:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            gc.collect()


@main.command(help='Export NSF-HiFiGAN vocoder model to ONNX format.')
@click.option(
    '--config', type=click.Path(
        exists=True, file_okay=True, dir_okay=False, readable=True,
        path_type=pathlib.Path, resolve_path=True
    ),
    required=True,
    help='Specify a configuration file for the vocoder.'
)
@click.option(
    '--ckpt', type=click.Path(
        exists=True, file_okay=True, dir_okay=False, readable=True,
        path_type=pathlib.Path, resolve_path=True
    ),
    required=False,
    help='Specify a model path of the vocoder checkpoint.'
)
@click.option(
    '--out', type=click.Path(
        dir_okay=True, file_okay=False,
        path_type=pathlib.Path, resolve_path=True
    ),
    required=False,
    help='Output directory for the artifacts.'
)
@click.option(
    '--name', type=click.STRING,
    required=False, default='nsf_hifigan', show_default=False,
    help='Specify filename (without suffix) of the target model file.'
)
def nsf_hifigan(
        config: pathlib.Path,
        ckpt: pathlib.Path = None,
        out: pathlib.Path = None,
        name: str = None
):
    if out is None:
        out = root_dir / 'artifacts' / 'nsf_hifigan'

    set_hparams(config.as_posix())
    if ckpt is None:
        model_path = pathlib.Path(hparams['vocoder_ckpt']).resolve()
    else:
        model_path = ckpt

    from deployment.exporters import NSFHiFiGANExporter
    print(f'| Exporter: {NSFHiFiGANExporter}')
    
    try:
        exporter = NSFHiFiGANExporter(
            device=torch.device('cuda' if torch.cuda.is_available() else 'cpu'),
            cache_dir=root_dir / 'deployment' / 'cache',
            model_path=model_path,
            model_name=name
        )
        exporter.export(out)
    except KeyboardInterrupt:
        sys.exit(-1)
    except Exception as e:
        print(f"| [ERROR] Export NSF-HiFiGAN failed: {e}")
        traceback.print_exc()
        sys.exit(-1)
    finally:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            gc.collect()

if __name__ == '__main__':
    main()