"""Download the open base models ft_lab uses into the HF cache (free, open weights)."""
from huggingface_hub import snapshot_download

from ft_lab import config as C

if __name__ == "__main__":
    for m in (C.SIZE_BASE, C.EXTRACT_BASE):
        p = snapshot_download(m, allow_patterns=["*.json", "*.safetensors", "*.txt", "merges.txt"])
        print(m, p, flush=True)
