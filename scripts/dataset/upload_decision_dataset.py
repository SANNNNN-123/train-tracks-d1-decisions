"""Upload only the reviewed HF export; never upload the workspace or .env."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import argparse,os
from pathlib import Path
from urllib.parse import urlparse
from huggingface_hub import HfApi
root=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument('repo_id',nargs='?',help='Defaults to HF_DATASET_PATH in the project .env');p.add_argument('--public',action='store_true');args=p.parse_args()
# Read dotenv assignments as data, never execute them.
values={}
if (root/'.env').exists():
    for line in (root/'.env').read_text(encoding='utf-8-sig').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            k,v=line.split('=',1);values[k.strip()]=v.strip().strip('\"').strip("'")
token=os.getenv('HF_TOKEN') or values.get('HF_TOKEN') or values.get('HUGGINGFACE_TOKEN') or values.get('HUGGINGFACE_HUB_TOKEN')
if not token: raise SystemExit('Set HF_TOKEN in .env or the environment.')
repo_id=args.repo_id or os.getenv('HF_DATASET_PATH') or values.get('HF_DATASET_PATH')
if not repo_id: raise SystemExit('Pass a dataset repo ID or set HF_DATASET_PATH in .env.')
if repo_id.startswith(('https://','http://')):
    parsed=urlparse(repo_id)
    parts=[part for part in parsed.path.split('/') if part]
    if parsed.netloc.lower() not in {'huggingface.co','www.huggingface.co'} or len(parts)<3 or parts[0]!='datasets':
        raise SystemExit('HF_DATASET_PATH URL must have the form https://huggingface.co/datasets/namespace/repository.')
    repo_id='/'.join(parts[1:3])
folder=root/'decision-dataset'/'huggingface'
if not (folder/'validation.json').exists():raise SystemExit('Validated export is not ready.')
api=HfApi(token=token)
api.create_repo(repo_id,repo_type='dataset',private=not args.public,exist_ok=True)
api.upload_folder(repo_id=repo_id,repo_type='dataset',folder_path=str(folder),allow_patterns=['README.md','data/*.parquet','validation.json'],commit_message='Upload audited Train Tracks decision dataset')
print('https://huggingface.co/datasets/'+repo_id)
