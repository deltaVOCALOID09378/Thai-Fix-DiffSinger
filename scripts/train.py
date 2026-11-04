# ==============================================================================
# Date: 25/10/2026
# File Name: train_2.py
# Version: 1.2
# Location: Root Directory
# Credit: Made And Checked By DELTA SYNTH & All Code Agentic AI Engine
#         Original by DiffSinger Project
# Description: Applied robust task initiation and execution safeguards.
# ==============================================================================
import importlib
import os
import sys
import traceback
from pathlib import Path

root_dir = Path(__file__).parent.parent.resolve()
os.environ['PYTHONPATH'] = str(root_dir)
sys.path.insert(0, str(root_dir))

os.environ['TORCH_CUDNN_V8_API_ENABLED'] = '1'  # Prevent unacceptable slowdowns when using 16 precision

from utils.hparams import set_hparams, hparams

set_hparams()
if not hparams.get('nccl_p2p', True):
    print("Disabling NCCL P2P")
    os.environ['NCCL_P2P_DISABLE'] = '1'

def run_task():
    try:
        assert hparams.get('task_cls', '') != '', "| [ERROR] 'task_cls' is not specified."
        pkg = ".".join(hparams["task_cls"].split(".")[:-1])
        cls_name = hparams["task_cls"].split(".")[-1]
        task_cls = getattr(importlib.import_module(pkg), cls_name)

        task_cls.start()
    except Exception as e:
        print(f"| [ERROR] Training task encountered a fatal error: {e}")
        traceback.print_exc()
        sys.exit(-1)

if __name__ == '__main__':
    run_task()