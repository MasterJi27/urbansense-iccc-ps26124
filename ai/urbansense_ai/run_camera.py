"""Webcam / video file / RTSP → PerceptionPipeline → POST /observations."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import urllib.request


def login(base: str, email: str, password: str) -> str:
    req = urllib.request.Request(
        f"{base}/auth/login",
        data=json.dumps({"email": email, "password": password}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())["access_token"]


def post_obs(base: str, token: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"{base}/observations",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def main() -> None:
    p = argparse.ArgumentParser(description="UrbanSense camera perception pipeline")
    p.add_argument("--source", default="0", help="webcam index, video path, or rtsp://")
    p.add_argument("--api", default=os.environ.get("URBANSENSE_API", "http://127.0.0.1:8000"))
    p.add_argument("--email", default="operator@urbansense.local")
    p.add_argument("--password", default=os.environ.get("URBANSENSE_PASSWORD", ""))
    p.add_argument("--lat", type=float, default=28.6328)
    p.add_argument("--lon", type=float, default=77.2195)
    p.add_argument("--source-id", default="WEBCAM-01")
    p.add_argument("--display", action="store_true")
    p.add_argument("--max-frames", type=int, default=0)
    args = p.parse_args()
    if not args.password:
        p.error("pass --password or set URBANSENSE_PASSWORD")

    import cv2
    from urbansense_ai.pipeline import FrameContext, PerceptionPipeline

    token = login(args.api.rstrip("/"), args.email, args.password)
    pipe = PerceptionPipeline()
    print(json.dumps(pipe.capabilities(), indent=2))

    src: int | str = int(args.source) if args.source.isdigit() else args.source
    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        raise SystemExit(f"Cannot open source {args.source}")

    ctx = FrameContext(latitude=args.lat, longitude=args.lon, source_id=args.source_id)
    n = 0
    t0 = time.time()
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        n += 1
        payloads = pipe.process(frame, ctx)
        for body in payloads:
            try:
                r = post_obs(args.api.rstrip("/"), token, body)
                print(
                    f"posted {body['event_type']} sim={body['simulated']} "
                    f"status={body.get('extra', {}).get('ai_status')} "
                    f"event={r.get('event', {}).get('public_code')}"
                )
            except Exception as exc:
                print("post failed", exc)
        if args.display:
            cv2.imshow("UrbanSense", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
        if args.max_frames and n >= args.max_frames:
            break
    elapsed = time.time() - t0
    print(f"frames={n} fps={n / elapsed if elapsed else 0:.2f}")
    cap.release()
    if args.display:
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
