# data: datasets (not in git)

Everything in this folder except this README is ignored by git: about 25 GB. Back it up yourself.
Do not move it to another drive: the prepared splits use hard links to the extracted images, and a copy would duplicate them.

| Folder or file | What it is |
| --- | --- |
| `RDD2022_released_through_CRDDC2022.zip` | The official RDD2022 archive from Figshare (13 GB). Source of everything below. |
| `rdd2022_raw/` | India extracted from that zip: images and VOC XML. |
| `rdd_india/` | India as YOLO labels, **random** 80/10/10 split. Frozen: every number published so far was measured here. The split leaks (the same stretch of road lands in train and test), so do not use it for new claims. |
| `rdd_india_simsplit/` | India again, but images that look alike stay in one split. **Use this for honest evaluation.** Train 2579, val 322, test 322. `split_info.json` records how. |
| `rdd_simsplit_mix/` | `rdd_india_simsplit` plus 13,362 extra training images (Japan, US, Czech, China MotorBike). Val and test are the India ones. 15,941 train images. The clean training set. |
| `rdd_hf_mix/` | Frozen random India plus the same extras (16,345 train). Used for the older runs, including the shipped model. Leaky val and test. |
| `rdd_hf_mb/` | Frozen random India plus China MotorBike only (4,629 train). Used for one older run. |
| `hf_unified/` | Download from Hugging Face (`TamAko783/Unified_Road_Defect_Dataset`): the two tar files and `kept/`, the extracted Japan, Czech, US and China MotorBike subset. |
| `hf_dronefreak_rdd2022/` | Another RDD2022 copy from Hugging Face. No script reads it now. |
| `*.log` | Training and evaluation logs. |

`data.yaml` files carry an absolute `path:`. The scripts rewrite it at run time (`eval_rdd.materialize_data_yaml`), so a moved
folder keeps working.

Classes everywhere: `D00` longitudinal crack, `D10` transverse crack, `D20` alligator crack, `D40` pothole.
Norway and the China drone set are not mixed in: different climate, and a drone view is not a bus windshield.

Scripts that build these folders are in `../ml/scripts`.
