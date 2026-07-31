#!/usr/bin/env python3
"""
Export Needle fine-tuned .pkl checkpoint to .safetensors + vocab.txt
for the needle-rs WASM/Python runtime.

The JAX/Flax model stores layers as batched tensors (e.g. shape [12, 512, 512]
for 12 encoder layers). needle-rs expects individual per-layer tensors.
This script splits the batched tensors and renames to needle-rs convention.

Supports optional INT4 quantization of kernel weights. The needle-rs runtime
already detects prequantized tensors by the presence of `{name}.scale` tensors,
and uses on-the-fly dequantization in matvec with AVX2/NEON SIMD.

Usage:
  # Float32 export (default, current behavior):
  python3 scripts/export.py \
    --checkpoint checkpoints/needle_finetuned_*_best.pkl \
    --output-dir output/

  # INT4 quantized export (72% smaller):
  python3 scripts/export.py \
    --checkpoint checkpoints/needle_finetuned_*_best.pkl \
    --output-dir output/ \
    --quantize int4

Format (INT4):
  - Kernel tensors (attention projections wq/wk/wv/wo) are group-wise quantized
    with group_size=32 along the input axis.
  - Scale = max(|group|) / 7.0, clamped >= 1e-8.
  - Values packed as two nibbles per byte: low nibble = even row, high nibble = odd row.
    Row-major (pair-major): data[pair * out_feat + o].
  - Scales stored as f32 [num_groups, out_feat] in a companion tensor `{name}.scale`.
  - The Rust load_quant() function detects prequantized weights by checking for
    the .scale tensor and reads via get_raw() + get_f32().
  - Non-kernel tensors (embedding, norms, bias, gates, contrastive head) stay as f32.
"""

import argparse
import os
import pickle
import re

import numpy as np
from safetensors import numpy as st_np


# ── INT4 quantization ─────────────────────────────────────────────────────────


def quantize_kernel(w, group_size=32):
    """Quantize f32 weight matrix to packed INT4 + f32 scales.

    Matches Python _fake_quantize_int4 and Rust QuantizedWeight::quantize exactly.

    Args:
        w: np.ndarray of shape [in_feat, out_feat], dtype float32
        group_size: int, default 32

    Returns:
        packed: np.ndarray of shape [num_pairs, out_feat], dtype int8
                (packed nibbles, row-major pair-major)
        scales: np.ndarray of shape [num_groups, out_feat], dtype float32
    """
    in_feat, out_feat = w.shape
    gs = min(group_size, in_feat)
    pad = (gs - in_feat % gs) % gs
    in_padded = in_feat + pad
    num_groups = in_padded // gs

    # Pad along input axis (zeros for padded rows)
    if pad > 0:
        w_padded = np.pad(w, ((0, pad), (0, 0)))
    else:
        w_padded = w

    # Reshape into groups: [num_groups, gs, out_feat]
    w_grouped = w_padded.reshape(num_groups, gs, out_feat)

    # Compute scales: max(|w|) / 7, clamped >= 1e-8
    # shape: [num_groups, 1, out_feat] (keepdims for broadcasting)
    scale = np.max(np.abs(w_grouped), axis=1, keepdims=True) / 7.0
    scale = np.maximum(scale, 1e-8)

    # Quantize: clamp(round(w / scale), -8, 7)
    # np.round uses banker's rounding (matches jnp.round in training)
    w_q = np.clip(np.round(w_grouped / scale), -8, 7).astype(np.int8)

    # Pack nibbles: row-major (pair-major), low nibble = even row, high = odd row
    # data[pair * out_feat + o] = lo(w_q[2*p, o]) | hi(w_q[2*p+1, o]) << 4
    w_flat = w_q.reshape(in_padded, out_feat)
    num_pairs = in_padded // 2
    packed = np.zeros((num_pairs, out_feat), dtype=np.int8)
    for pair in range(num_pairs):
        r0 = pair * 2
        r1 = pair * 2 + 1
        lo = w_flat[r0].astype(np.uint8) & 0x0F
        hi = (w_flat[r1].astype(np.uint8) & 0x0F) << 4
        packed[pair] = (lo | hi).astype(np.int8)

    # Scales: [num_groups, out_feat] as f32
    scales_flat = scale.reshape(num_groups, out_feat).astype(np.float32)

    return packed, scales_flat


_QUANTIZABLE_SUFFIXES = frozenset({
    'self_attn.wq', 'self_attn.wk', 'self_attn.wv', 'self_attn.wo',
    'cross_attn.wq', 'cross_attn.wk', 'cross_attn.wv', 'cross_attn.wo',
    'gate_proj', 'up_proj', 'down_proj',
})


def _is_quantizable(name):
    """Return True if the tensor name should be INT4 quantized.

    Matches the set of tensors loaded via load_quant() in the Rust engine.
    These are the attention projection weights (wq/wk/wv/wo) and FFN weights
    (gate/up/down). Non-kernel tensors (embedding, norms, bias, contrastive
    head) stay as f32.
    """
    for suffix in _QUANTIZABLE_SUFFIXES:
        if name.endswith('.' + suffix):
            return True
    return False


# ── Flatten and rename ────────────────────────────────────────────────────────


def flatten_params(params, prefix=""):
    """Recursively flatten nested dict of arrays."""
    result = {}
    if isinstance(params, dict):
        for key, val in params.items():
            flat_key = f"{prefix}.{key}" if prefix else key
            result.update(flatten_params(val, flat_key))
    elif isinstance(params, (list, tuple)):
        for i, val in enumerate(params):
            flat_key = f"{prefix}.{i}" if prefix else str(i)
            result.update(flatten_params(val, flat_key))
    else:
        arr = np.asarray(params)
        if arr.size > 0:
            result[prefix] = arr
    return result


def split_and_rename(flat):
    """
    Split batched JAX layer tensors and rename to needle-rs convention.

    Returns a flat dict with needle-rs compatible names.
    """
    result = {}

    for name, arr in flat.items():
        arr = arr.astype(np.float32)

        # ── Top-level renames ──
        if name == 'embedding.embedding':
            result['embedding'] = arr
            continue
        if name == 'encoder.final_norm.scale':
            result['encoder_final_norm'] = arr
            continue
        if name == 'decoder.ZCRMSNorm_0.scale':
            result['decoder_final_norm'] = arr
            continue
        if name == 'log_temp':
            result['log_temp'] = arr.reshape(1)
            continue
        if name.startswith('contrastive_'):
            result[name] = arr  # Keep contrastive head names as-is
            continue

        # ── Encoder layers ──
        #   encoder.layers.EncoderBlock_0.XXX shape [12, ...]
        #   → encoder.{i}.YYY shape [...]
        m = re.match(r'^encoder\.layers\.EncoderBlock_0\.(.+)$', name)
        if m:
            suffix = m.group(1)
            num_layers = arr.shape[0]

            if suffix == 'ZCRMSNorm_0.scale':         # [12, 512] → per-layer [512]
                for i in range(num_layers):
                    result[f'encoder.{i}.norm'] = arr[i]
                continue
            if suffix == 'attn_gate':                   # [12] → per-layer scalar
                for i in range(num_layers):
                    result[f'encoder.{i}.self_attn_gate'] = np.array([float(arr[i])], dtype=np.float32)
                continue

            # Attention projections — suffix maps:
            proj_map = {
                'self_attn.q_proj.kernel': 'self_attn.wq',
                'self_attn.k_proj.kernel': 'self_attn.wk',
                'self_attn.v_proj.kernel': 'self_attn.wv',
                'self_attn.out_proj.kernel': 'self_attn.wo',
                'self_attn.q_norm.scale': 'self_attn.q_norm',
                'self_attn.k_norm.scale': 'self_attn.k_norm',
            }
            if suffix in proj_map:
                new_suffix = proj_map[suffix]
                for i in range(num_layers):
                    result[f'encoder.{i}.{new_suffix}'] = arr[i]
                continue

            # Fall through — rename unknown suffix
            for i in range(num_layers):
                result[f'encoder.{i}.{suffix}'] = arr[i]
            continue

        # ── Decoder layers ──
        #   decoder.layers.DecoderBlock_0.XXX shape [8, ...]
        #   → decoder.{i}.YYY shape [...]
        m = re.match(r'^decoder\.layers\.DecoderBlock_0\.(.+)$', name)
        if m:
            suffix = m.group(1)
            num_layers = arr.shape[0]

            # Norm renames
            norm_map = {
                'ZCRMSNorm_0.scale': 'self_attn_norm',
                'ZCRMSNorm_1.scale': 'cross_attn_norm',
            }
            if suffix in norm_map:
                new_suffix = norm_map[suffix]
                for i in range(num_layers):
                    result[f'decoder.{i}.{new_suffix}'] = arr[i]
                continue

            # Scalar gate renames
            gate_map = {
                'self_attn_gate': 'self_attn_gate',
                'cross_attn_gate': 'cross_attn_gate',
            }
            if suffix in gate_map:
                new_suffix = gate_map[suffix]
                for i in range(num_layers):
                    result[f'decoder.{i}.{new_suffix}'] = np.array([float(arr[i])], dtype=np.float32)
                continue

            # Attention projection renames for both self_attn and cross_attn
            for old_sfx, new_sfx in [
                ('self_attn.q_proj.kernel', 'self_attn.wq'),
                ('self_attn.k_proj.kernel', 'self_attn.wk'),
                ('self_attn.v_proj.kernel', 'self_attn.wv'),
                ('self_attn.out_proj.kernel', 'self_attn.wo'),
                ('self_attn.q_norm.scale', 'self_attn.q_norm'),
                ('self_attn.k_norm.scale', 'self_attn.k_norm'),
                ('cross_attn.q_proj.kernel', 'cross_attn.wq'),
                ('cross_attn.k_proj.kernel', 'cross_attn.wk'),
                ('cross_attn.v_proj.kernel', 'cross_attn.wv'),
                ('cross_attn.out_proj.kernel', 'cross_attn.wo'),
                ('cross_attn.q_norm.scale', 'cross_attn.q_norm'),
                ('cross_attn.k_norm.scale', 'cross_attn.k_norm'),
            ]:
                if suffix == old_sfx:
                    for i in range(num_layers):
                        result[f'decoder.{i}.{new_sfx}'] = arr[i]
                    break
            else:
                # Unknown suffix — keep as-is per layer
                for i in range(num_layers):
                    result[f'decoder.{i}.{suffix}'] = arr[i]
            continue

        # ── Anything else ──
        result[name] = arr

    return result


# ── Main ──────────────────────────────────────────────────────────────────────


def export_checkpoint(checkpoint_path, output_dir, quantize=None):
    """Export a checkpoint to safetensors.

    Args:
        checkpoint_path: Path to .pkl checkpoint
        output_dir: Output directory
        quantize: None or 'f32' for float32 (default), 'int4' for INT4 quantization
    """
    os.makedirs(output_dir, exist_ok=True)

    # 1. Load checkpoint
    print(f"Loading: {checkpoint_path}")
    with open(checkpoint_path, "rb") as f:
        data = pickle.load(f)

    params = data["params"]
    config = data["config"]
    print(f"  Model: d_model={config.get('d_model')}, "
          f"heads={config.get('num_heads')}, "
          f"layers={config.get('num_encoder_layers')}e/{config.get('num_decoder_layers')}d")

    # 2. Flatten and rename
    flat = flatten_params(params)
    renamed = split_and_rename(flat)

    # 3. Quantize kernel weights if requested
    if quantize == 'int4':
        quantized = {}
        for name, arr in renamed.items():
            if _is_quantizable(name) and arr.ndim == 2:
                packed, scales = quantize_kernel(arr)
                quantized[name] = packed
                quantized[f'{name}.scale'] = scales
            else:
                quantized[name] = arr
        renamed = quantized
        print(f"  Quantized kernel weights to INT4 (group_size=32)")

    # 4. Stats
    total_params = sum(v.size for v in renamed.values())
    total_bytes = sum(v.nbytes for v in renamed.values())
    print(f"  Tensors: {len(renamed)} (was {len(flat)})")
    print(f"  Parameters: {total_params:,} ({total_bytes / 1024 / 1024:.1f} MB)")

    for name, arr in sorted(renamed.items())[:5]:
        print(f"    {name}: {arr.shape} {arr.dtype}")
    if len(renamed) > 5:
        print(f"    ... and {len(renamed) - 5} more")

    # 5. Build config metadata for safetensors header
    metadata = {}
    for key in ('d_model', 'num_heads', 'num_kv_heads',
                'num_encoder_layers', 'num_decoder_layers',
                'vocab_size', 'max_seq_len', 'd_ff',
                'rope_theta', 'contrastive_dim', 'dropout_rate'):
        if key in config:
            metadata[key] = str(config[key])
    if 'max_enc_len' in config:
        metadata['max_enc_len'] = str(config['max_enc_len'])
    if 'max_dec_len' in config:
        metadata['max_dec_len'] = str(config['max_dec_len'])
    if 'dtype' in config:
        metadata['dtype'] = str(config['dtype'])
    if 'activation' in config:
        metadata['activation'] = str(config['activation'])
    if 'no_feedforward' in config:
        metadata['no_feedforward'] = str(config['no_feedforward'])

    # 6. Write safetensors
    st_path = os.path.join(output_dir, "needle.safetensors")
    st_np.save_file(renamed, st_path, metadata=metadata)
    st_size = os.path.getsize(st_path)
    print(f"\n  → {st_path} ({st_size / 1024 / 1024:.1f} MB)")

    # 7. Export vocab
    try:
        from needle.dataset.dataset import get_tokenizer
        tokenizer = get_tokenizer()
        vocab_path = os.path.join(output_dir, "vocab.txt")
        sp = tokenizer.sp
        pieces = []
        size = sp.get_piece_size() if hasattr(sp, "get_piece_size") else tokenizer.vocab_size
        for i in range(size):
            try:
                piece = sp.id_to_piece(i) if hasattr(sp, "id_to_piece") else sp.IdToPiece(i)
                if piece:
                    pieces.append(piece)
            except:
                pass
        with open(vocab_path, "w") as f:
            for piece in pieces:
                f.write(piece + "\n")
        v_size = os.path.getsize(vocab_path)
        print(f"  → {vocab_path} ({v_size:,} bytes, {len(pieces)} tokens)")
    except Exception as e:
        print(f"  Vocab export failed (non-fatal): {e}")

    total = sum(os.path.getsize(os.path.join(output_dir, f))
                for f in os.listdir(output_dir))
    print(f"\n  Total: {total / 1024 / 1024:.1f} MB in {output_dir}/")
    print("Done.")


def main():
    parser = argparse.ArgumentParser(
        description="Export Needle checkpoint to safetensors for needle-rs WASM runtime"
    )
    parser.add_argument("--checkpoint", required=True,
                        help="Path to .pkl checkpoint file")
    parser.add_argument("--output-dir", required=True,
                        help="Output directory for safetensors and vocab")
    parser.add_argument("--quantize", choices=['f32', 'int4'], default='f32',
                        help="Weight format: 'f32' (default, 100 MB) or 'int4' (28 MB, 72%% smaller)")
    args = parser.parse_args()

    export_checkpoint(args.checkpoint, args.output_dir, quantize=args.quantize)


if __name__ == "__main__":
    main()