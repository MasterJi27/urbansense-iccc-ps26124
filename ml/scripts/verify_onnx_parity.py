"""Verify that the exported ONNX detects the same boxes as the PyTorch checkpoint.

Raw YOLO tensors differ slightly between PyTorch CPU and ONNX Runtime (kernel/oneDNN order), so a
1e-3 tensor equality test is the wrong gate. This script compares what production actually uses:
the decoded detection list (class, box, confidence) after NMS.

  python ml/scripts/verify_onnx_parity.py \
    --pt ml/models/road_damage/runs/pothole_opt_v2/weights/best.pt \
    --onnx ml/models/road_damage/runs/pothole_opt_v2/weights/best.onnx \
    --data data/rdd_pothole_opt_v2/data_kent_holdout.yaml --split test --limit 20
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml" / "scripts"))

import eval_rdd  # noqa: E402

IMGSZ = 640


def letterbox(image):
    """Same geometry as `backend/app/services/rdd_cloud.py::_letterbox`."""
    from PIL import Image

    w, h = image.size
    scale = min(IMGSZ / w, IMGSZ / h)
    nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    resized = image.resize((nw, nh), Image.BILINEAR)
    canvas = Image.new("RGB", (IMGSZ, IMGSZ), (114, 114, 114))
    pad_x = (IMGSZ - nw) // 2
    pad_y = (IMGSZ - nh) // 2
    canvas.paste(resized, (pad_x, pad_y))
    return canvas


def tensor_for(path: Path) -> np.ndarray:
    from PIL import Image, ImageOps

    image = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    arr = np.asarray(letterbox(image), dtype=np.float32) / 255.0
    return np.transpose(arr, (2, 0, 1))[None, ...]


def decode(raw: np.ndarray, conf: float, iou: float) -> np.ndarray:
    """Ultralytics NMS on a raw [1, 4+nc, 8400] tensor -> [N, 6] (x1,y1,x2,y2,conf,cls)."""
    import torch

    try:
        from ultralytics.utils.nms import non_max_suppression
    except ImportError:  # older Ultralytics releases kept it in utils.ops
        from ultralytics.utils.ops import non_max_suppression

    t = torch.from_numpy(raw)
    keep = non_max_suppression(t, conf_thres=conf, iou_thres=iou, max_det=300, agnostic=False)
    d = keep[0]
    return d.cpu().numpy() if isinstance(d, torch.Tensor) else np.zeros((0, 6))


def match(a: np.ndarray, b: np.ndarray) -> tuple[int, float, float]:
    """Greedy same-class match. Returns (matched, min_iou_of_matched, max_conf_delta)."""
    if len(a) != len(b):
        return 0, 0.0, float("inf")
    used = np.zeros(len(b), dtype=bool)
    min_iou = 1.0
    max_dc = 0.0
    matched = 0
    for box in a:
        best, best_iou = -1, -1.0
        for j, other in enumerate(b):
            if used[j] or int(other[5]) != int(box[5]):
                continue
            xx1, yy1 = max(box[0], other[0]), max(box[1], other[1])
            xx2, yy2 = min(box[2], other[2]), min(box[3], other[3])
            inter = max(0.0, xx2 - xx1) * max(0.0, yy2 - yy1)
            area_a = max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])
            area_b = max(0.0, other[2] - other[0]) * max(0.0, other[3] - other[1])
            iou = inter / (area_a + area_b - inter + 1e-9)
            if iou > best_iou:
                best, best_iou = j, iou
        if best >= 0 and best_iou >= 0.5:
            used[best] = True
            matched += 1
            min_iou = min(min_iou, best_iou)
            max_dc = max(max_dc, abs(float(box[4]) - float(b[best][4])))
    return matched, min_iou, max_dc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pt", type=Path, required=True)
    ap.add_argument("--onnx", type=Path, required=True)
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--split", default="test")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--conf", type=float, default=0.18)
    ap.add_argument("--iou", type=float, default=0.45)
    ap.add_argument("--raw-tol", type=float, default=0.05, help="sanity bound on raw output, not the pass gate")
    args = ap.parse_args()

    import onnxruntime as ort
    import torch
    from ultralytics import YOLO

    torch_model = YOLO(str(args.pt)).model.eval()
    sess = ort.InferenceSession(str(args.onnx), providers=["CPUExecutionProvider"])
    input_name = sess.get_inputs()[0].name
    print(f"pt   {args.pt}")
    print(f"onnx {args.onnx}")
    print(f"onnx input {sess.get_inputs()[0].shape} -> output {sess.get_outputs()[0].shape}")

    _, cfg = eval_rdd.materialize_data_yaml(args.data)
    images = eval_rdd.split_images(cfg, args.split)[: args.limit]
    print(f"checking {len(images)} images from {args.data} split={args.split}, conf={args.conf}")

    worst_raw = 0.0
    raw_fail = 0
    total_pt = total_onnx = total_matched = 0
    worst_iou = 1.0
    worst_dc = 0.0
    bad = []
    for path in images:
        x = tensor_for(path)
        with torch.no_grad():
            raw_pt = torch_model(torch.from_numpy(x))
        if isinstance(raw_pt, (list, tuple)):
            raw_pt = raw_pt[0]
        pt_raw = raw_pt.cpu().numpy()
        onnx_raw = sess.run(None, {input_name: x})[0]
        if pt_raw.shape != onnx_raw.shape:
            print(f"FAIL shape {path.name}: pt {pt_raw.shape} onnx {onnx_raw.shape}")
            bad.append(path.name)
            continue
        raw_diff = float(np.abs(pt_raw - onnx_raw).max())
        worst_raw = max(worst_raw, raw_diff)
        if raw_diff > args.raw_tol:
            raw_fail += 1

        a = decode(pt_raw, args.conf, args.iou)
        b = decode(onnx_raw, args.conf, args.iou)
        total_pt += len(a)
        total_onnx += len(b)
        matched, min_iou, dc = match(a, b)
        total_matched += matched
        worst_iou = min(worst_iou, min_iou)
        worst_dc = max(worst_dc, dc)
        if matched != len(a) or len(a) != len(b):
            bad.append(f"{path.name} (pt {len(a)}, onnx {len(b)}, matched {matched})")

    print(f"\nraw max|diff|       = {worst_raw:.6g} (sanity bound {args.raw_tol}; above: {raw_fail}/{len(images)})")
    print(f"detections pt/onnx  = {total_pt}/{total_onnx}")
    print(f"matched             = {total_matched}")
    print(f"worst matched IoU   = {worst_iou:.4f}")
    print(f"worst conf delta    = {worst_dc:.4f}")
    if bad or total_pt != total_onnx or total_matched != total_pt:
        print(f"FAILED: {len(bad)} image(s) disagree: {bad[:5]}")
        return 1
    print("OK: ONNX and PyTorch produce the same detections on this sample")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
