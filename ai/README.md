UrbanSense AI
=============

Pluggable inference. No production model is bundled.

Implemented now
---------------
- DetectionEngine / TrackingEngine / OCRService / SeverityEngine interfaces
- SimulationDetector (explicitly simulated)
- SimulationOCR returning sample plate DL01AB1234 (simulated)
- RuleSeverity from detection confidence (not ML)

How to plug a real detector
---------------------------
Implement DetectionEngine.detect(frame) -> list[Detection] and inject it
in the mobile HIGH/MEDIUM modes or an edge gateway worker.

Future
------
- On-device TFLite / ONNX pothole and sign models
- ByteTrack / SORT vehicle tracking
- Real LPR OCR
- Learned fusion replacing SpatialTemporalFusionEngine
