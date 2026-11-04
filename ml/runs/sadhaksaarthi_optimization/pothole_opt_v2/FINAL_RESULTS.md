# pothole_opt_v2 — final results

Generated: 2026-11-02T15:18:14+00:00
Run directory: `D:\Projects\sih_winner_2026_prototype\ml\models\road_damage\runs\pothole_opt_v2`
Selection split: Kent D40 val (80 images / 117 boxes); the 70-photo Kent holdout was never used for selection.

## Training

- Completed epochs: **45** (configured 120, patience 30)
- Wall time in training: **163.1 min**
- Best fitness epoch: **15** (mAP50 0.5962, mAP50-95 0.3603)
- `best.pt` is selected on kent_val; `last.pt` is epoch 45.

| epoch | mAP50 | mAP50-95 | D40 not available in results.csv | fitness |
|---:|---:|---:|---|---:|
| 1 | 0.4331 | 0.2569 | — | 0.2745 |
| 2 | 0.4669 | 0.2747 | — | 0.2939 |
| 3 | 0.5041 | 0.2807 | — | 0.3030 |
| 4 | 0.5438 | 0.3028 | — | 0.3269 |
| 5 | 0.5433 | 0.3103 | — | 0.3336 |
| 6 | 0.5810 | 0.3526 | — | 0.3754 |
| 7 | 0.5595 | 0.3275 | — | 0.3507 |
| 8 | 0.5940 | 0.3525 | — | 0.3766 |
| 9 | 0.5881 | 0.3312 | — | 0.3569 |
| 10 | 0.5857 | 0.3271 | — | 0.3530 |
| 11 | 0.5687 | 0.3258 | — | 0.3501 |
| 12 | 0.6007 | 0.3452 | — | 0.3708 |
| 13 | 0.5870 | 0.3371 | — | 0.3621 |
| 14 | 0.5857 | 0.3316 | — | 0.3570 |
| 15 | 0.5962 | 0.3603 | — | 0.3839 |
| 16 | 0.5826 | 0.3526 | — | 0.3756 |
| 17 | 0.5861 | 0.3357 | — | 0.3607 |
| 18 | 0.5910 | 0.3418 | — | 0.3667 |
| 19 | 0.5703 | 0.3456 | — | 0.3681 |
| 20 | 0.5862 | 0.3542 | — | 0.3774 |
| 21 | 0.5604 | 0.3315 | — | 0.3544 |
| 22 | 0.5635 | 0.3477 | — | 0.3693 |
| 23 | 0.5859 | 0.3441 | — | 0.3683 |
| 24 | 0.5934 | 0.3546 | — | 0.3784 |
| 25 | 0.5977 | 0.3495 | — | 0.3743 |
| 26 | 0.5841 | 0.3330 | — | 0.3581 |
| 27 | 0.6013 | 0.3494 | — | 0.3746 |
| 28 | 0.5896 | 0.3529 | — | 0.3766 |
| 29 | 0.5869 | 0.3516 | — | 0.3751 |
| 30 | 0.5913 | 0.3458 | — | 0.3704 |
| 31 | 0.6028 | 0.3467 | — | 0.3723 |
| 32 | 0.5936 | 0.3361 | — | 0.3618 |
| 33 | 0.5983 | 0.3442 | — | 0.3696 |
| 34 | 0.5863 | 0.3338 | — | 0.3591 |
| 35 | 0.5956 | 0.3376 | — | 0.3634 |
| 36 | 0.6073 | 0.3418 | — | 0.3684 |
| 37 | 0.6012 | 0.3510 | — | 0.3761 |
| 38 | 0.5857 | 0.3369 | — | 0.3618 |
| 39 | 0.5854 | 0.3293 | — | 0.3549 |
| 40 | 0.5886 | 0.3332 | — | 0.3587 |
| 41 | 0.5972 | 0.3383 | — | 0.3642 |
| 42 | 0.5876 | 0.3418 | — | 0.3664 |
| 43 | 0.5869 | 0.3351 | — | 0.3603 |
| 44 | 0.6018 | 0.3373 | — | 0.3637 |
| 45 | 0.5861 | 0.3323 | — | 0.3577 |

## India validation (322 images, not used for selection)

| model | mAP50 | mAP50-95 | D40 AP50 | D40 AP50-95 | D40 P | D40 R | D40 F1 | conf |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| shipped | 0.7501 | 0.3776 | 0.6631 | 0.3271 | 0.7330 | 0.5593 | 0.6344 | 0.234 |
| v1_ep14 | 0.6497 | 0.3094 | 0.6306 | 0.2907 | 0.5739 | 0.6383 | 0.6044 | 0.204 |
| v2_best | 0.6725 | 0.3308 | 0.6447 | 0.2942 | 0.6612 | 0.5957 | 0.6267 | 0.244 |
| v2_last | 0.6295 | 0.3151 | 0.6474 | 0.2733 | 0.6089 | 0.6353 | 0.6218 | 0.208 |

## India test (322 images, scored once after selection)

| model | mAP50 | mAP50-95 | D40 AP50 | D40 AP50-95 | D40 P | D40 R | D40 F1 | conf |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| shipped | 0.7039 | 0.3214 | 0.6577 | 0.3115 | 0.6430 | 0.5758 | 0.6075 | 0.186 |
| v1_ep14 | 0.6651 | 0.2748 | 0.6332 | 0.3084 | 0.6630 | 0.5606 | 0.6075 | 0.272 |
| v2_best | 0.6845 | 0.2933 | 0.6250 | 0.2988 | 0.6824 | 0.5636 | 0.6174 | 0.256 |
| v2_last | 0.6087 | 0.2545 | 0.6190 | 0.2746 | 0.6825 | 0.5472 | 0.6074 | 0.284 |

## Kent holdout (70 photos, 137 D40 boxes, never used for selection)

| model | D40 AP50 | D40 AP50-95 | D40 P | D40 R | D40 F1 | conf |
|---|---:|---:|---:|---:|---:|---:|
| shipped | 0.2555 | 0.1275 | 0.4036 | 0.2920 | 0.3388 | 0.185 |
| v1_ep14 | 0.6346 | 0.3746 | 0.6881 | 0.6058 | 0.6444 | 0.411 |
| v2_best | 0.6591 | 0.3799 | 0.6200 | 0.6642 | 0.6413 | 0.308 |
| v2_last | 0.6470 | 0.3619 | 0.6878 | 0.6496 | 0.6682 | 0.315 |

## Read this carefully

- India val/test overlap the base checkpoint's training data (the shipped model memorised them), so those columns are in-distribution, not field accuracy.
- The Kent holdout is the only split here that no candidate trained on. It is UK phone photography, not Indian roads; it measures pothole appearance transfer, not field performance.
- `v2_best` is selected on the 80-image Kent val; its Kent holdout score is therefore a fair second check, but the selection itself is noisy.
- Deployed as a model-only ONNX swap on 2026-11-04; see `docs/MODEL_OPTIMIZATION_REPORT.md` section 15. The production confidence threshold remains 0.18.
