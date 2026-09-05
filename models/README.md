Place downloaded weights here (gitignored).

- road_damage/YOLOv8_Small_RDD.pt  (auto-downloaded from oracl4/RoadDamageDetection)
- road_damage/metrics.json         (written by `python scripts/train_rdd.py` — never invent mAP)
- traffic/yolov8n.pt                (Ultralytics COCO, auto-downloaded on first vehicle detect)
- traffic_sign/best.pt              (optional; Turkish YOLO from TrafficSignRecognition)
- anpr/plate.pt                     (optional dedicated plate detector)

Train India-only RDD2022 after converting VOC→YOLO. Settings shows EXPERIMENTAL until metrics.json exists from a real val pass.
