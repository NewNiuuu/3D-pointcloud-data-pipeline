# Low-Altitude 2D-to-3D Data Generation Pipeline

```yaml
document_type: agent_implementation_spec
target_reader: Claude Code
spec_version: 0.2.0
status: design_baseline
fact_verification_cutoff: 2026-08-23
execution_target: remote_server
local_workspace_role: design_and_control_plane
```

## 0. Agent Directive

This file is the canonical implementation specification for the initial server-side repository.

Normative terms:

- `MUST`: required invariant; do not change without explicit user approval.
- `MUST NOT`: prohibited behavior.
- `SHOULD`: default implementation choice; deviation requires a recorded reason.
- `MAY`: optional extension.
- `UNRESOLVED`: configuration requiring user decision or empirical validation.

Before modifying implementation:

1. Read this file completely.
2. Read `PROJECT_HANDOFF.md` for provenance and historical context.
3. Treat this file as authoritative for system organization.
4. If this file conflicts with a user-confirmed rule in `PROJECT_HANDOFF.md`, stop and report the conflict.
5. Do not silently resolve `UNRESOLVED` items.

## 1. System Objective

Build a data-generation and evaluation system for low-altitude UAV / near-ground aerial 3D scene understanding.

```text
Low-altitude 2D datasets
    ├── VGGT-Ω
    │     └── cameras + depth + confidence + point cloud
    ├── native labels + 2D/video expert models
    │     └── masks + tracks + semantics + specialist detections
    ├── 2D-to-3D lifting and fusion
    │     └── structured 3D metadata + provenance + confidence
    ├── downstream task designer/compiler
    │     └── 3D anchors + hidden targets + evidence + checkers + prompt bundles
    ├── Qwen adapter: 2D visual inputs + task-local 3D metadata
    ├── native point-cloud adapter
    └── multimodal 3D adapter
          └── portable low-altitude 3D task supervision
```

The initial output families are:

- 3D Semantic / Instance Segmentation
- 3D Object / Thin-Structure / Track Annotation
- Metric, Viewpoint, Visibility, Occupancy, Route, and Risk Tasks

- 3D Grounding
- 3D VQA
- 3D Caption
- 3D Task Decomposition
- 3D Dialogue

Candidate extensions include:

- Cross-view 3D Correspondence
- 3D Metadata Verification
- 3D Metadata Completion
- Viewpoint Transformation
- Next-best-view Prediction
- 3D Scene Graph Query
- Geometry-aware Retrieval
- 3D Change Reasoning
- Spatial Counterfactual Simulation
- Uncertainty-aware 3D Reasoning
- Route / Plan Critique
- Grounded Measurement Dialogue

## 2. Immutable Architecture Rules

1. VGGT-Ω MUST be the primary point-cloud reconstruction path.
2. Qwen MUST consume 2D images/video plus structured 3D metadata.
3. Qwen MUST NOT consume raw PLY/LAS point clouds in this architecture.
4. Depth Anything 3, WorldMirror, or other geometry models MAY be used as experts or consistency checks; they MUST NOT replace VGGT-Ω as the primary path.
5. A generated task MUST require 3D information. Ordinary 2D recognition questions are out of scope.
6. Metadata input MUST NOT directly expose the hidden answer or an equivalent derived field.
7. Deterministically computable values MUST be generated and checked by geometry/rule programs, not accepted solely from an LLM.
8. Metric and relative scale MUST remain distinct throughout the pipeline.
9. Pseudo-depth MUST NOT be represented as metric ground truth without an external metric anchor.
10. Every generated artifact MUST preserve provenance, version, source frames, coordinate frame, units, confidence, and parent artifact references.
11. Dataset splits MUST be scene-, location-, or trajectory-level. Per-frame random splitting is prohibited.
12. The initial implementation SHOULD prioritize a small end-to-end scene closure before large-scale generation.
13. Feishu source documents and existing Obsidian notes MUST NOT be modified by this project.

## 3. Four-Layer Architecture

```text
Layer 1: Dataset Source Registry and Selection
    output: verified dataset cards + sample manifests + selection decision

Layer 2: 2D-to-3D Metadata Extraction and Scene Construction
    output: versioned point clouds + scene packages + geometry/semantic/temporal metadata

Layer 3: Agent, Skills, Prompt Compilation, Validation, and Quality Monitoring
    output: validated samples + quality events + release manifests

Layer 4: Downstream Task Design and Capability Completion
    input: point cloud + cameras + scene metadata + quality/provenance
    output: portable 3D task annotations for Qwen, native point-cloud models, and multimodal 3D models
```

Layer boundaries MUST be implemented through versioned artifacts. In-memory-only implicit contracts are prohibited for production runs.

---

# Layer 1. Dataset Source Registry and Selection

## 4. Purpose

Layer 1 maintains a machine-readable registry of low-altitude / near-ground aerial datasets that can supply images, videos, labels, geometry anchors, or evaluation ground truth.

Layer 1 MUST:

- distinguish real and simulated data;
- distinguish native depth, rendered depth, stereo, SfM/MVS, direct LiDAR, and pseudo-depth;
- record metric-scale availability and scale source;
- record camera calibration, pose, timestamps, labels, and point-cloud availability;
- verify current official links, version, file inventory, license, redistribution constraints, and checksums before ingestion;
- compare candidates with the current Feishu registry without modifying Feishu;
- output dataset cards and small-sample manifests before any full download.

## 5. Existing Feishu Registry Snapshot

The following names were present in the Feishu snapshot captured on 2026-08-23 and were excluded from the prior “new candidate” list:

```yaml
feishu_existing_snapshot:
  - FloodNet
  - Open3DVQA
  - TDBench
  - LADI-v2
  - AVI-Math
  - AirCopBench
  - SpatialSky
  - UrbanVideo-Bench
  - MM-UAVBench
  - MME-RealWorld
  - Geo3DVQA
```

This is a historical snapshot, not a current truth. Before a new dataset-review cycle, an authorized read-only process SHOULD obtain the latest Feishu list and rerun name/alias/content deduplication.

## 6. Previously Identified New Candidates

The following candidates were not present in the historical Feishu snapshot. Their detailed availability and licensing are not yet fully verified.

| Priority | Dataset | Source | Available 3D-enabling signals | Initial role |
|---|---|---|---|---|
| S | UAVScenes | Real | RGB, Livox point cloud, 6DoF poses, calibration, semantic cloud/mesh | real semantic geometry anchor |
| S | Dronescapes | Real | video, SfM intrinsics/poses, metric depth, normals, semantic subset | real multi-view reconstruction |
| S | H3D / Hessigheim 3D | Real | dense airborne LiDAR, RGB, labeled cloud, textured mesh, multi-temporal data | high-quality 3D supervision |
| S | SkyLume | Real | five-direction cameras, repeated RTK flights, COLMAP poses, mesh/LiDAR depth, normals | repeated-flight geometry |
| S | UAVStereo | Real + simulated | stereo RGB, PFM disparity, mesh/LiDAR geometry | stereo geometry validation |
| S | UrbanScene3D | Real + simulated | LiDAR, textured mesh, images/poses, simulated depth/boxes/segmentation | mixed-domain scene understanding |
| S | ClaraVid | Simulated | metric depth, semantic/instance/dynamic masks, cameras, scene cloud | complete synthetic labels |
| A | NTU VIRAL | Real | stereo cameras, dual 3D LiDAR, IMU, UWB, Leica truth, calibration | sensor/pose validation |
| A | MUN-FRL | Real | monocular RGB, 3D LiDAR, IMU, RTK-GNSS, calibration | metric-scale real sequences |
| A | MARS-LVIG | Real | RGB, Livox, IMU, GNSS, RTK, DJI L1 map truth | real metric geometry |
| A | Mid-Air | Simulated | depth, normals, semantics, disparity, occlusion mask, poses, IMU/GPS | controlled synthetic scenes |
| A | UAV3D | Simulated | multi-UAV/multi-view RGB, pixel semantics, 3D boxes | multi-view object tasks |
| A | U2UData+ | Simulated | multi-UAV RGB + LiDAR, 3D boxes/tracks | collaborative perception |
| A | IllumUAV-Sim | Simulated | aligned day/night RGB, depth, normals, cameras | illumination robustness |
| B | UAPD / DAPM | Simulated | RGB, depth, randomized altitude/pose/FOV | viewpoint diversity |
| B | UAVPairs | Real | high-overlap multi-view images, SfM matching relations | correspondence tasks |
| B | UAVID3D | Real | RGB + thermal, high-overlap orbit imagery, GPS | multimodal reconstruction |
| B | Ready for 3D Reconstruction | Real | GCP/checkpoints, 2D correspondences, MVS subset, TLS cloud | scale/reconstruction evaluation |
| B | FlyAwareV2 | Real + simulated | RGB, depth, semantic masks; real depth includes monocular pseudo-depth | obstacle tasks with provenance caution |
| B | LAMBDA | Simulated | RGB, LiDAR, 4D radar, CSI, depth, IMU, multi-UAV | multimodal extension |
| C | UAVid | Real | 4K video, eight semantic classes; weak geometry/pose | semantic expert input |
| C | VisDrone | Real | large detection/tracking annotations; no depth or pose | 2D expert/task auxiliary source |

## 7. Dataset Card Contract

Each dataset MUST have a versioned card before ingestion.

```yaml
dataset_id: uavscenes
display_name: UAVScenes
card_version: 0.1.0
dataset_version: UNRESOLVED
source_type: real  # real | simulated | mixed

official_sources:
  project_url: UNRESOLVED
  repository_url: UNRESOLVED
  download_url: UNRESOLVED
  paper_url: UNRESOLVED

license:
  identifier: UNRESOLVED
  commercial_training: unknown
  derivative_point_cloud_redistribution: unknown
  model_weight_release: unknown
  verified_at: null

modalities:
  rgb: true
  video: UNRESOLVED
  lidar: true
  depth: false
  camera_intrinsics: true
  camera_extrinsics: true
  imu: UNRESOLVED
  gps_rtk: UNRESOLVED

geometry:
  depth_source: direct_lidar
  metric_scale: true
  scale_source: lidar
  coordinate_system: UNRESOLVED

annotations:
  semantic_2d: UNRESOLVED
  instance_2d: UNRESOLVED
  semantic_3d: true
  instance_3d: UNRESOLVED
  tracking: UNRESOLVED

ingestion:
  adapter_status: not_started
  sample_download_status: not_started
  verified_file_inventory: null
  checksums: null

risks: []
```

Allowed `depth_source` values:

```text
direct_lidar
stereo
sfm_mvs
rendered_depth
pseudo_depth
none
```

## 8. Dataset Selection Gates

A dataset MUST NOT enter full ingestion until:

1. Official source and version are recorded.
2. License and derivative-data constraints are reviewed.
3. A 1–3 scene sample is downloaded and inspected.
4. Required files are readable and aligned.
5. Camera and scale assumptions are validated.
6. Scene-level splitting is possible.
7. Its role in the initial benchmark is explicit.

Recommended initial roles, not final selections:

```yaml
real_multiview_reconstruction_candidates:
  - UAVScenes
  - Dronescapes

high_quality_3d_reference_candidates:
  - H3D
  - UAVStereo

complete_simulated_label_candidate:
  - ClaraVid
```

Dataset choice was resolved on 2026-08-24: **UAVScenes** is the single Phase-1 dataset. The
remaining names above stay candidates for later phases and MUST NOT be treated as selected.
Phase-1 eligibility additionally requires `metric_scale_policy: metric_required` (SPEC §36),
so relative-scale-only scenes are ineligible regardless of tier.

## 9. Layer 1 Outputs

```text
registry/datasets/<dataset_id>/dataset_card.yaml
registry/datasets/<dataset_id>/file_inventory.json
registry/datasets/<dataset_id>/license_review.yaml
registry/datasets/<dataset_id>/sample_manifest.json
registry/datasets/<dataset_id>/verification_report.json
registry/feishu_snapshot/<date>.yaml
registry/selection/phase_<n>.yaml
```

---

# Layer 2. 2D-to-3D Metadata Extraction and Data Pipeline

## 10. Purpose

Layer 2 transforms raw dataset scenes into point clouds, structured 3D metadata, deterministic targets, and task-local context suitable for Qwen.

## 11. Stage Graph

```text
L2-S0 Dataset Adapter / Scene Slicing
    input: raw dataset files + dataset card
    output: normalized scene manifest

L2-S1 Geometry Reconstruction
    input: normalized images/video + optional camera priors
    model: VGGT-Ω
    output: camera estimates + depth + confidence + point cloud

L2-S2 2D / Video Expert Perception
    input: normalized frames/video
    output: masks + detections + tracks + specialist predictions

L2-S2B Independent Geometry Experts
    input: normalized frames/video + optional camera priors
    output: metric/relative depth opinions + normals + validity + tracks + alignment residuals
    default priority: MoGe-3 -> DSINE -> DA3-1.1; DA3-Streaming only for long video

L2-S3 2D-to-3D Lifting and Fusion
    input: VGGT-Ω geometry + semantic/video predictions + aligned independent geometry evidence
    output: stable 3D objects/parts/regions/tracks

L2-S4 Metadata Derivation
    input: L0/L1 entities
    output: L2 relations + selected L3 temporal/action fields

L2-S5 Quality and Provenance
    input: all upstream artifacts
    output: immutable metadata snapshot + validation report

L2-S6 Task Compilation
    input: metadata snapshot + task spec
    output: hidden target + evidence + prompt bundle

L2-S7 Model Generation
    input: 2D views/video + task-local metadata + prompt bundle
    model: configured Qwen variant
    output: raw structured response

L2-S8 Sample Validation
    input: raw response + hidden target + checker
    output: validated sample or quarantine event
```

## 12. Normalized Scene Contract

```json
{
  "scene_id": "scene_000018",
  "dataset_id": "dataset_name",
  "dataset_version": "...",
  "split_group_id": "location_or_flight_id",
  "source_type": "real",
  "frames": [],
  "native_annotations": [],
  "sensor_calibration": {},
  "coordinate_frame": "dataset_native",
  "unit": "unknown",
  "scale": {
    "status": "relative",
    "source": "none",
    "uncertainty_m": null
  },
  "provenance": {}
}
```

All adapters MUST emit this contract or a versioned successor.

## 13. Geometry Reconstruction

VGGT-Ω outputs MAY include:

- camera pose encoding;
- camera extrinsics/intrinsics;
- depth;
- depth confidence;
- camera/register tokens;
- point cloud derived by depth back-projection;
- optional text-alignment embedding when a compatible checkpoint is used.

Implementation requirements:

1. Record exact model checkpoint and code revision.
2. Preserve input-frame IDs and sampling strategy.
3. Preserve raw depth confidence before thresholding.
4. Record all coordinate transforms.
5. Record whether metric alignment was applied and its anchor.
6. Generate geometry diagnostics for coverage, reprojection, density, drift, and invalid depth.
7. Detect and flag likely dynamic ghosting, sky depth, water/glass failures, repeated-texture drift, and thin-structure loss.

Metric scale example:

```json
{
  "coordinate_frame": "world",
  "unit": "meter",
  "scale": {
    "status": "metric",
    "source": "rtk_gps",
    "uncertainty_m": 0.08
  }
}
```

Relative-scale scenes MAY support topology, correspondence, relative position, visibility, and scale-invariant tasks. They MUST NOT generate absolute-meter targets.

## 14. Expert Model System

Two expert surveys dated 2026-08-23 establish separate semantic/video and independent-geometry stacks. Official assets were reviewed, but no checkpoint was downloaded and no candidate was tested on local UAV data. All recommendations remain subject to license review. The geometry validation baseline is 40–60 short clips plus 8–12 long clips; the full semantic comparison MAY expand to 100–300 clips.

### 14.1 Research Baseline Stack

| Function | Initial expert | Role in this pipeline |
|---|---|---|
| Open-vocabulary instance proposals and masks | Grounded-SAM-2: Grounding DINO + SAM 2.1 Base+ | semantic proposal, pixel mask, initial object identity |
| Video mask tracking | SAM 2.1 Base+ | propagate masks and 2D track IDs; periodically reinitialize from detector |
| Optical flow and motion evidence | SEA-RAFT | flow, uncertainty, forward/backward consistency, residual-motion evidence |
| Sky/water/stuff semantics | OneFormer with ADE20K/Mapillary labels | independent semantic reason masks |
| UAV obstacle semantics | CABiNet MobileNetV3-Small | UAV-specific obstacle/ground/vegetation evidence |
| Power-line specialist | PowerLine-MTYOLO Nano | cable masks and power-line proposals; domain-specific only |
| Independent metric geometry | MoGe-3 ViT-L | primary scale/normal/valid-mask/fine-detail second opinion; never replaces VGGT-Ω |
| Independent normal | DSINE with uncertainty | normal evidence independent of depth differentiation; license-gated |
| Depth/pose/scale cross-check | Depth Anything 3 / DA3-1.1 Apache-compatible variant | secondary depth/camera/sky/scale opinion; never fuse its second point cloud as truth |
| Long-video geometry | DA3-Streaming | chunked pose/depth/confidence with overlap and loop closure; activation is optional and license-gated |
| Point tracks and visibility | CoTracker3 | 2D tracks/visibility for temporal support; noncommercial license restricts deployment |
| Attribute/caption proposals | Florence-2 Base or Large | structured attribute/caption proposals, not geometric truth |
| Cross-view appearance embedding | DINOv2 Small or Base | ReID, clustering, and cross-view association features |

Grounded-SAM-2 is a modular system. Detector box/class confidence and SAM mask confidence MUST be stored separately. Bounding boxes MUST NOT be lifted as though every enclosed pixel belongs to the object.

### 14.2 Candidate Tiers

```yaml
A0_initial_candidates:
  - Grounded-SAM-2
  - SAM 2.1
  - SEA-RAFT
  - OneFormer
  - CABiNet
  - MoGe-3 ViT-L after weight-license confirmation
  - Depth Anything 3 / DA3-1.1 Apache-compatible variant
  - Florence-2

A1_accuracy_or_ablation_candidates:
  - FC-CLIP
  - Cutie
  - XMem
  - EdgeTAM
  - UniMatch
  - SAM 3.1 after license review
  - AerialMetric
  - MetricAnything
  - DSINE after license review
  - DA3-Streaming after dependency-license review
  - CoTracker3 for noncommercial research or separately authorized use
  - Trace Anything for noncommercial research or quality evaluation
  - MASt3R as sampled correspondence expert
  - OVMono3D or DetAny3D as UAV-unverified object-level ablation
  - PowerLine-MTYOLO
  - TTPLA-YOLACT
  - DINOv2
  - OTAS

B_or_later_candidates:
  - OpenSeeD
  - MemFlow
  - UFM
  - EDFNet after training and license clarification
  - PBSeg after license clarification
  - DINO-X API subject to deployment/privacy/version review
  - U2MOT
  - AnyChange
  - ChangeSAM
  - DAM subject to weight license
  - WorldMirror for inference/evaluation only; never training metadata
  - CUT3R as secondary long-video cross-check
```

Candidate tier is not permission to download, install, or use a model. `expert-registry-manager` MUST verify current source, checkpoint, code license, weight license, derivative-data constraints, runtime, and UAV validation status before activation.

### 14.3 Expert Scheduling

Recommended initial cadence:

```yaml
mask_tracking: every_frame
detector_reinitialization: every_5_to_15_frames_or_confidence_drop
optical_flow: adjacent_frames
depth_cross_check: keyframes
normal_cross_check: keyframes
uav_semantic_segmentation: keyframes_or_low_rate
attribute_extraction: 1_to_3_best_views_per_stable_track
change_detection: scene_level_offline_only
```

Exact cadence MUST remain configurable and MUST be profiled on the target server.

### 14.4 Dynamic Geometry Rule

Raw optical-flow magnitude MUST NOT be interpreted as object motion because UAV ego-motion produces global image flow.

Dynamic evidence MUST be based on residual flow:

```text
observed flow
  - static flow rendered from VGGT-Ω depth + camera motion
  = residual flow
```

The dynamic probability SHOULD combine:

- residual-flow magnitude;
- flow uncertainty;
- forward/backward consistency;
- instance mask membership;
- depth/reprojection consistency;
- temporal support.

Water, reflection, moving foliage, shadows, motion blur, and propeller artifacts MUST remain separate failure reasons rather than being silently classified as physical object motion.

### 14.5 Invalid Geometry Reasons

The pipeline MUST retain independent probability maps and reason codes for:

```text
sky
water
reflection_or_transparency
low_depth_confidence
reprojection_inconsistent
dynamic_geometry
out_of_bounds
```

A combined invalid probability MAY be computed, but it MUST NOT replace the component reason masks. Water MUST NOT be treated as equivalent to empty space; it is geometry that often violates stable Lambertian/rigid reconstruction assumptions.

### 14.6 Thin Obstacles

Thin-obstacle evidence is not mature enough to become automatic high-confidence truth.

Every thin-obstacle observation MUST retain:

- soft probability;
- skeleton/centerline;
- local width;
- boundary confidence;
- connected components;
- support-frame count;
- 3D line-fitting residual;
- source model and prompt/class definition.

A single-frame one-pixel detection without cross-frame or geometric support MUST be marked weak evidence or quarantined.

### 14.7 Flyable Space

No 2D segmentation model may directly emit the final `flyable_volume` truth.

```text
2D obstacle / ground / vegetation / sky / water evidence
    -> depth + camera lifting
    -> 3D occupied and uncertain evidence
    -> multi-view fusion
    -> occupancy / free-space representation
    -> UAV radius + clearance + uncertainty inflation
    -> flyable volume / unsafe corridor / bottleneck
```

Final free-space and route values MUST be derived in 3D by deterministic geometry or planning modules.

### 14.8 Expert Output Invariants

All experts MUST preserve:

- original frame, camera, timestamp, and image checksum;
- original image size;
- exact preprocessing homography or resize/crop transform;
- raw and calibrated confidence separately;
- model name, version, commit, checkpoint hash, license, runtime, and precision;
- dense output URI rather than embedding large arrays in metadata JSON;
- separate detection, mask, track, depth, and association confidence values.

No expert prediction becomes ground truth solely because a model emitted it. Fusion MUST retain source-specific confidence, expert disagreement, support views, and failure reason codes.

### 14.9 Cross-view Association

Video mask trackers MUST NOT be treated as complete cross-view ReID systems. Cross-view association SHOULD combine:

```text
appearance embedding
3D centroid / size / orientation
reprojection overlap
class compatibility
temporal gap and reachable-motion constraints
```

Hard merges SHOULD be avoided when evidence conflicts. The initial implementation SHOULD retain a probabilistic association/track graph and record merge/split lineage.

### 14.10 Common Expert I/O Contract

Common expert input MUST include:

```json
{
  "sample_id": "scene_001/cam_02/frame_000123",
  "scene_id": "scene_001",
  "camera_id": "cam_02",
  "frame_id": 123,
  "timestamp_ns": 1723456789000000000,
  "image_uri": "images/cam_02/000123.jpg",
  "image_sha256": "...",
  "original_size": [2160, 3840],
  "camera": {
    "K": [],
    "distortion_model": "opencv",
    "distortion": [],
    "T_world_from_camera": [],
    "coordinate_convention": "x_right_y_down_z_forward"
  },
  "vggt_omega": {
    "depth_uri": "depth/000123.exr",
    "confidence_uri": "depth_conf/000123.exr",
    "model_version": "...",
    "checkpoint_sha256": "..."
  }
}
```

Mask/track observations MUST preserve separate scores:

```json
{
  "observation_id": "obs_123_07",
  "track_id_2d": "track_0042",
  "class_candidates": [],
  "mask": {
    "encoding": "coco_rle",
    "data": "...",
    "mask_score": 0.91,
    "boundary_score": 0.72
  },
  "box_xyxy_original": [120.3, 88.2, 209.5, 164.8],
  "embedding_uri": "embeddings/obs_123_07.npy",
  "occlusion_score": 0.26,
  "is_keyframe_detection": true,
  "provenance": {}
}
```

Flow output MUST include observed flow, uncertainty, forward/backward error, rendered static flow, residual flow, and dynamic probability as separately addressable artifacts.

Lifted 3D instances SHOULD include centroid covariance, velocity covariance, point-support URI, mask confidence, depth confidence, multiview consistency, reprojection IoU, and expert disagreement.

### 14.11 Depth and Scale Taxonomy

Every depth artifact MUST declare exactly one of:

| Type | Meaning | Absolute metric tasks |
|---|---|---|
| `metric` | output is defined in meters, but UAV domain scale bias is still unverified | allowed only after domain calibration/gating |
| `externally_anchored` | scale recovered from RTK/GPS/IMU/altimeter/ToF/LiDAR/known baseline | allowed when anchor provenance and uncertainty pass |
| `relative` | multiplicative scale is unknown | prohibited |
| `affine_invariant` | scale and shift may both be unknown | prohibited |
| `pseudo` | unverified model estimate | weak label or quality signal only |

A model card using the word “metric” MUST NOT be treated as proof of acceptable UAV scale accuracy.

### 14.12 Coordinate and Scale Alignment

Every expert MUST store `H_original_to_model`, crop, padding, camera convention, and alignment version. Expert pixels MUST be transformed back to original-image coordinates before indexing VGGT-Ω rays or points.

Alignment rules:

1. Reliable metric expert plus external metric frame: solve SE(3) with fixed `scale=1`.
2. Relative expert geometry: solve robust Sim(3) using static camera centers and static 3D correspondences.
3. Framewise relative or affine depth: fit log-depth scale or scale+shift only on static, non-sky, non-water, non-reflective regions.
4. Dynamic objects MUST NOT participate in scene alignment.
5. Metric evaluation MUST report raw metric error before any Sim(3) fitting; otherwise scale error is hidden.
6. Loop closure or realignment MUST create a new coordinate/alignment version and MUST NOT silently overwrite prior metadata.

### 14.13 Disagreement and Confidence Calibration

Experts MUST NOT vote directly to create truth. After alignment, compute at least:

- log-depth disagreement;
- scale residual;
- normal-angle disagreement;
- cross-view reprojection error;
- camera translation/rotation residual;
- forward/backward track-cycle error;
- static-region temporal inconsistency;
- RGB/mask/depth-boundary displacement;
- valid/invalid reason conflicts.

Raw model confidence and agreement MUST be calibrated on held-out data into error-event probabilities such as:

```text
P(depth_error < threshold)
P(normal_error < threshold)
P(reprojection_error < threshold)
P(point_is_valid)
```

Calibration MAY use isotonic regression, Platt scaling, conformal calibration, or another validated method. Safety-related confidence SHOULD use a conservative composition such as the minimum of VGGT, expert, agreement, and visibility confidence. Multi-model agreement alone is not ground truth.

### 14.14 Circular-Validation Rules

- WorldMirror without VGGT priors MAY act as an independent evaluation cross-check.
- WorldMirror conditioned on VGGT depth/pose/K is a refiner and MUST NOT be used to prove VGGT correctness.
- WorldMirror outputs MUST NOT be used as Qwen/VLM training metadata under the currently reviewed license; it is inference/evaluation-only pending legal approval.
- MetricAnything and MoGe share architectural lineage and MUST NOT be counted as two independent votes.
- DA3 and VGGT-Ω may share representation/training biases; agreement does not imply independence.
- At least one normal signal SHOULD come from an independent normal estimator such as DSINE rather than only depth-derived normals.

### 14.15 Deterministic Geometry Boundary

Models MAY predict depth, normals, masks, tracks, visibility, embeddings, dynamic probability, and metric-scale priors.

Programs MUST compute:

- depth-to-point transforms;
- TSDF/voxel/ESDF occupancy;
- free/occupied/unknown state;
- ray visibility and occlusion;
- object centroid, robust size, and PCA orientation;
- clearance, reachability, candidate routes, and next-best-view information gain;
- TTC, swept-volume collision, and risk propagation;
- cross-frame consistency, expert disagreement, and confidence calibration.

Safety-critical clearance, TTC, collision risk, and flyability MUST NOT be estimated directly by Qwen or a general VLM.

## 15. 2D-to-3D Lifting and Fusion

Minimum expected flow:

1. Associate every 2D prediction with frame ID and pixel mask/box.
2. Use valid depth and camera parameters to lift pixels to 3D support points.
3. Reject or downweight uncertain depth and boundary pixels.
4. Transform support points into the canonical scene frame.
5. Match instances across views using semantic, appearance, geometry, and visibility constraints.
6. Fuse matched support into a stable entity.
7. Assign immutable entity IDs.
8. Compute geometry primitives and support statistics.
9. Record unresolved conflicts instead of force-merging.

Stable ID namespaces:

```text
<obj_021>    general object
<part_006>   object part
<wire_004>   thin linear obstacle
<region_009> spatial region
<route_002>  candidate route
<track_011>  temporal trajectory
<pose_007>   camera or observer pose
```

IDs MUST be stable within a metadata snapshot. Cross-version ID lineage SHOULD be recorded when entities split or merge.

## 16. Metadata Layers

### L0: Raw Geometry

- camera intrinsics/extrinsics and poses;
- depth and depth confidence;
- XYZ/RGB points;
- normals;
- coordinate frame, unit, scale status/source;
- reprojection error, coverage, density;
- transforms and geometry provenance.

### L1: 3D Entities

- object/part/region/route/track IDs;
- category and attributes;
- centroid, AABB, OBB, size, orientation;
- point/voxel/mesh instance support;
- visible views and occlusion ratio;
- static/dynamic state;
- wire centerline, endpoints, radius;
- planes and surfaces;
- semantic, geometry, and cross-view confidence.

### L2: 3D Relations

- distance and height difference;
- azimuth and elevation;
- observer-relative front/back/left/right/above/below;
- near/intersect/contain/support/connect/hang;
- occludes/visible-from;
- cross-view correspondence;
- topology and connectivity.

### L3: Temporal, Functional, and Action Metadata

- 3D trajectories, velocity, acceleration;
- TTC;
- occupancy and free space;
- visibility coverage;
- reachability;
- routes and minimum clearance;
- next-best-view;
- scene change;
- task preconditions and completion conditions.

Initial release MUST implement only the L3 fields required by selected tasks.

## 17. Object Contract

```json
{
  "object_id": "<wire_004>",
  "category": "power_line",
  "geometry": {
    "centerline": [[12.4, 8.1, 6.3], [15.7, 9.8, 6.6]],
    "radius_m": 0.012,
    "bbox_3d": [12.4, 8.1, 6.2, 15.7, 9.8, 6.7]
  },
  "visibility": {
    "visible_frames": ["f0012", "f0015"],
    "occlusion_ratio": 0.42
  },
  "confidence": {
    "semantic": 0.81,
    "geometry": 0.74,
    "cross_view_support": 3
  },
  "provenance": {
    "geometry_model": "VGGT-Omega",
    "semantic_model": "EDFNet",
    "source_frames": ["f0012", "f0015", "f0018"]
  }
}
```

## 18. Scene Package

```text
scene_000018/
├── scene.ply
├── scene_manifest.json
├── cameras.json
├── frames.json
├── objects.json
├── relations.json
├── tracks.json
├── navigation.json
├── quality.json
├── provenance.json
├── renders/
│   ├── rgb/
│   ├── depth/
│   ├── normal/
│   ├── semantic_id/
│   ├── instance_id/
│   └── bev/
└── tasks/
    ├── grounding.jsonl
    ├── vqa.jsonl
    ├── caption.jsonl
    ├── dialogue.jsonl
    └── task_decomposition.jsonl
```

`navigation.json` and some render directories MAY be absent in the initial version. Their absence MUST be explicit in `scene_manifest.json`.

## 19. Task Sample Contract

```json
{
  "sample_id": "sample_...",
  "task_type": "3d_vqa.metric_reasoning",
  "task_spec_version": "0.1.0",
  "scene_id": "scene_000018",
  "visual_inputs": ["view_003.jpg", "view_007.jpg"],
  "metadata_inputs": {
    "observer": {},
    "entities": [],
    "geometry_primitives": {}
  },
  "metadata_input_fields": [
    "observer.position",
    "entities.centerline"
  ],
  "hidden_target_fields": [
    "derived.minimum_distance"
  ],
  "question": "Which wire is closest to the UAV?",
  "target": {
    "object_id": "<wire_004>",
    "distance_m": 6.3
  },
  "evidence": {
    "used_entities": ["<wire_004>", "<wire_007>"],
    "used_fields": ["observer.position", "entities.centerline"],
    "derivation_program": "minimum_point_to_polyline_distance"
  },
  "checker": {
    "name": "check_minimum_distance_answer",
    "version": "0.1.0",
    "tolerance_m": 0.1
  },
  "quality": {
    "status": "pass",
    "answer_confidence": 0.88,
    "geometry_confidence": 0.84
  },
  "provenance": {}
}
```

## 20. Task Construction Rules

### 20.1 Program-first tasks

Applicable to grounding, metric VQA, situated relations, topology, correspondence, and many verification tasks.

Required order:

1. Select eligible scene/entity configuration.
2. Compute hidden target deterministically.
3. Record evidence and checker.
4. Construct visible metadata by applying field masks.
5. Verify absence of target leakage.
6. Ask the LLM to naturalize the question or produce the requested structured answer.
7. Validate against the hidden target.

### 20.2 Hybrid tasks

Applicable to caption and dialogue.

Required order:

1. Generate a deterministic structured claim set or dialogue state.
2. Provide only allowed claims/state to the LLM.
3. Generate natural language.
4. Extract or retain structured claims alongside text.
5. Validate factual coverage and unsupported-claim rate.

### 20.3 Model-first constrained tasks

Applicable to task decomposition, plan critique, and selected next-best-view tasks.

Required order:

1. Provide explicit entities, goals, constraints, and allowed actions.
2. Generate one or more structured candidates.
3. Validate geometry, preconditions, completion conditions, and constraint conflicts.
4. Accept, repair once, or quarantine.
5. Do not convert an infeasible task into a fabricated feasible plan.

---

# Layer 3. Agent, Skills, Prompts, Validation, and Quality

## 21. Purpose

Layer 3 converts repeatable decision procedures into Skills, compiles task-specific prompts from declarative specifications, validates outputs at every stage, and monitors sample/batch/release quality.

Skills MUST encode reusable workflow and decision rules. Individual prompt wording SHOULD live in versioned templates or task specifications rather than one Skill per task.

## 22. Agent Topology

Initial topology:

```text
Pipeline Orchestrator Agent
├── dataset-registry-manager
├── expert-registry-manager
├── scene-ingestion-validator
├── metadata-quality-gate
├── task-spec-designer
├── task-prompt-compiler
├── task-sample-auditor
└── dataset-quality-monitor
```

The Orchestrator Agent MUST:

- implement a state machine over immutable artifacts;
- pass only task-relevant context to each Skill;
- record transitions, failures, retries, and quarantine reasons;
- enforce hard quality gates;
- stop when required inputs, scale anchors, or provenance are missing;
- never lower quality thresholds to improve throughput;
- never alter a hidden target to match an LLM response.

## 23. Skill Contracts

### 23.1 `dataset-registry-manager`

Input:

- Feishu snapshot or current read-only export;
- prior registry;
- dataset research evidence;
- sample verification reports.

Output:

- normalized dataset cards;
- alias-aware deduplication report;
- verification status;
- phase-selection recommendation.

Hard failures:

- unknown source identity;
- unresolved license when full ingestion is requested;
- dataset alias collision;
- unsupported high-altitude satellite/remote-sensing source.

### 23.2 `expert-registry-manager`

Input:

- expert survey evidence;
- official repository/model-card metadata;
- server profiles;
- license review and UAV validation reports.

Output:

- versioned expert cards;
- enabled/disabled expert set per server profile;
- checkpoint and license manifest;
- scheduling policy;
- compatibility and fallback report.

Responsibilities:

- distinguish code license, weight license, API terms, and derivative-data constraints;
- audit transitive model/dependency licenses rather than only the top-level repository;
- record whether outputs may be used for training, evaluation-only, or quality-control-only;
- record input/output capability and coordinate convention;
- record model lineage/shared-bias groups so correlated experts are not counted as independent votes;
- prevent activation of models without an approved use status;
- preserve A0/A1/B/C research tier separately from deployment approval;
- bind preprocessing, checkpoint hash, runtime precision, and cadence;
- require UAV small-sample evidence before promoting an expert to production.

Hard failures:

- missing or incompatible license;
- unavailable or unverifiable checkpoint;
- undocumented input coordinate transform;
- output that cannot be aligned to frame/camera IDs;
- unrecorded API version or remote-data handling policy.
- output-use restrictions incompatible with the requested training/release purpose;
- unreviewed transitive checkpoint or dependency license.

### 23.3 `scene-ingestion-validator`

Input: raw sample + dataset card + adapter output.

Output: `ingestion_report.json`.

Checks:

- readability;
- timestamp/frame/calibration alignment;
- split leakage;
- required modality presence;
- depth source and metric-scale claim;
- minimum view overlap and reconstruction readiness.

### 23.4 `metadata-quality-gate`

Input: geometry, expert outputs, fused entities, derived metadata.

Output: immutable `metadata_snapshot.json` plus validation report.

Checks:

- JSON/schema validity;
- coordinate system and units;
- ID uniqueness and referential integrity;
- reprojection and cross-view consistency;
- numeric validity of boxes, lines, poses, and tracks;
- support views and confidence;
- provenance completeness;
- recomputability of derived fields;
- known geometry failure signatures.

The gate MUST additionally validate residual-flow construction, invalid-geometry reason masks, separation of detector/mask/track confidence, and thin-obstacle support evidence.

### 23.5 `task-spec-designer`

Input:

- available scene/metadata capabilities;
- downstream capability taxonomy;
- supervision strength and quality policy;
- target model adapters.

Output:

- versioned Task Specs;
- task capability-coverage matrix;
- 3D-necessity and low-altitude-specificity tests;
- required target/evidence/checker contracts.

Responsibilities:

- design tasks that cannot be solved by ordinary 2D recognition alone;
- bind every target to point-cloud geometry, stable IDs, voxels, routes, tracks, or deterministic spatial programs;
- mark supervision as strong, deterministic-derived, filtered pseudo, weak, or language-generated;
- define task eligibility by scale, visibility, uncertainty, and scene content;
- prevent duplicate task families that test the same capability under different wording;
- keep canonical task annotations independent of Qwen or any single model architecture.

### 23.6 `task-prompt-compiler`

Input: validated metadata snapshot + task spec + prompt template.

Output: `prompt_bundle.json`.

Responsibilities:

- enforce scene eligibility;
- compute hidden target;
- select visual inputs;
- extract the minimal task-local metadata subgraph;
- apply visible/hidden field masks;
- run target-leakage detection;
- bind output schema, checker, tolerance, refusal rules, and retry policy;
- generate primary and repair prompts.

### 23.7 `task-sample-auditor`

Input: prompt bundle + raw model output + hidden target + checker.

Output: validated sample or quarantine record.

Checks:

- schema compliance;
- valid IDs, enums, units, and numeric ranges;
- checker agreement;
- evidence sufficiency;
- ambiguity and solvability;
- target leakage;
- 3D necessity;
- unsupported entities/claims;
- caption claim fidelity;
- dialogue state consistency;
- plan constraint satisfaction.

Repair policy:

```yaml
format_error:
  action: structured_repair
  max_attempts: 1

language_error_with_correct_target:
  action: constrained_rewrite
  max_attempts: 1

geometry_or_evidence_error:
  action: return_upstream_or_quarantine
  max_attempts: 0

retry_exhausted:
  action: quarantine
```

### 23.8 `dataset-quality-monitor`

Input: quality events and validated samples across a run/batch/release.

Output:

- `quality_dashboard.json`;
- drift and failure reports;
- `release_manifest.json` or release block.

The monitor MUST report but MUST NOT autonomously change release thresholds.

## 24. Declarative Task Spec

```yaml
task_id: 3d_vqa.metric.minimum_distance
version: 0.1.0
task_family: 3d_vqa
generation_mode: program_first

required_scene_capabilities:
  scale_status: metric
  geometry:
    - observer_position
    - centerline

visual_input_policy:
  input_type: multi_view_image
  min_views: 2
  selection: support_and_context

metadata_input_fields:
  - observer.position
  - entities.object_id
  - entities.category
  - entities.geometry.centerline

hidden_target_fields:
  - derived.minimum_distance
  - target.object_id

derivation_program: minimum_point_to_polyline_distance
checker: check_minimum_distance_answer
prompt_template: 3d_vqa/metric_v1
output_schema: schemas/3d_vqa_metric_answer.schema.json

leakage_rules:
  forbidden_input_fields:
    - entities.distance_to_observer
    - derived.minimum_distance

quality_requirements:
  minimum_geometry_confidence: 0.80
  maximum_answer_count: 1
  numeric_tolerance_m: 0.10
```

Every Task Spec MUST define:

- why the task requires 3D;
- required scene capabilities;
- visible metadata fields;
- hidden targets;
- target derivation;
- visual input policy;
- output schema;
- checker and tolerance;
- leakage rules;
- refusal/eligibility conditions;
- quality thresholds.

## 25. Prompt Bundle

```json
{
  "prompt_bundle_id": "pb_...",
  "task_spec_id": "3d_vqa.metric.minimum_distance@0.1.0",
  "scene_id": "scene_000018",
  "metadata_snapshot_id": "meta_...",
  "model": {
    "provider": "UNRESOLVED",
    "name": "UNRESOLVED",
    "version": "UNRESOLVED",
    "parameters": {}
  },
  "visual_inputs": [],
  "system_prompt": "...",
  "task_prompt": "...",
  "metadata_context": {},
  "output_schema": {},
  "hidden_target_ref": "target_...",
  "checker": "check_minimum_distance_answer",
  "retry_policy": {
    "max_format_repairs": 1,
    "max_semantic_rewrites": 1
  }
}
```

Every generation prompt MUST state:

1. task role and coordinate-frame convention;
2. allowed visual and metadata evidence;
3. prohibition on inventing objects, relations, units, or scale;
4. ambiguity/insufficient-evidence refusal format;
5. strict output schema;
6. ID, enum, unit, and numeric precision rules;
7. requirement to output auditable evidence references;
8. prohibition on copying example IDs/numbers as current answers.

## 26. Task-Specific Prompt Requirements

### 26.1 3D Grounding

- Return only valid object/part/region/route/track IDs and required scores.
- Candidate metadata MUST NOT mark the target.
- Observer-relative language MUST bind to an explicit observer pose.
- Equal valid candidates MUST produce an ambiguity response.

### 26.2 3D VQA

- Metric questions require metric-scale eligibility.
- Situated questions require observer position, orientation, and axis convention.
- Numeric answers require units and checker tolerance.
- LLM-generated numbers MUST NOT replace deterministic targets.

### 26.3 3D Caption

- Input SHOULD contain a deterministic claim set.
- Output MUST preserve both natural language and structured claims.
- Claims unsupported by metadata and visual evidence are prohibited.

### 26.4 3D Task Decomposition

Each step MUST bind:

- action;
- target ID;
- goal region or waypoint;
- spatial constraints;
- preconditions;
- completion conditions;
- evidence.

Candidate plans MUST pass geometry and rule validation.

### 26.5 3D Dialogue

Every turn SHOULD include:

- dialogue state version;
- currently bound entities;
- observer pose;
- metadata snapshot version;
- unresolved references.

The model MUST ask for clarification when reference resolution is non-unique.

### 26.6 New Tasks

New task families MUST reuse the same compilation interface. Adding a task normally means adding:

```text
task spec
prompt template
output schema
derivation program
checker
quality tests
```

Creating a new Skill is justified only when the workflow or decision procedure differs materially from existing Skills.

## 27. Quality Gates

| Gate | Stage | Hard failure examples |
|---|---|---|
| G0 | Dataset / expert registry and ingestion | unreadable files, unknown source, split leakage, blocking dataset/model license issue |
| G1 | Geometry and expert inference | unknown coordinate frame, conflicting scale claim, unusable reconstruction, missing preprocessing transform |
| G2 | Metadata | broken IDs, missing critical provenance, invalid geometry, unrecomputable derived data, missing reason masks or confidence components |
| G3 | Task design and compilation | failed 3D necessity/low-altitude claim, leaked target, non-unique answer, missing checker, unmet scene capability |
| G4 | Model output | unrepairable schema, nonexistent entity references, invalid units |
| G5 | Sample audit | checker disagreement, insufficient evidence, unsupported claims, failed 3D necessity |
| G6 | Dataset release | excessive leakage/duplicates, distribution failure, dependency tests fail |

Allowed states:

```text
pass
warn
quarantine
reject
```

Hard failures MUST NOT be converted into a weighted quality score. Only gate-passing samples receive soft scores.

## 28. Quality Metrics

### 28.1 Sample Level

- schema validity;
- provenance completeness;
- geometry confidence;
- answer determinism;
- evidence sufficiency;
- target leakage;
- ambiguity;
- 3D necessity;
- visual/metadata consistency;
- language quality;
- uncertainty calibration.

### 28.2 Batch and Release Level

- pass/warn/quarantine/reject rates by gate;
- first-pass schema compliance;
- format-repair and semantic-rewrite rates;
- deterministic checker agreement;
- unsupported-claim rate;
- target-leakage rate;
- ambiguous-sample rate;
- exact and near-duplicate rate;
- task/category/difficulty/scene/scale/source distributions;
- real versus simulated distribution;
- quality drift between versions;
- failures grouped by dataset, model, task spec, prompt version, and reconstruction configuration.

Expert and lifting validation SHOULD additionally track:

- mask AP, mIoU, and boundary F-score;
- thin-structure recall, skeleton precision, connectivity, and 3D line-fit residual;
- tracking J&F, HOTA, IDF1, and ID switches;
- optical-flow EPE, forward/backward error, and ego-compensated dynamic IoU;
- lifted-point purity/completeness, cross-view 3D IoU, and reprojection IoU;
- depth disagreement, normal angular error, and scale drift;
- confidence calibration using ECE, Brier score, NLL, AUSE, and risk-coverage/AURC;
- latency, peak memory, FPS, joules/frame, temporary disk, final metadata bytes/frame, video-minute cost, and failure-retry rate.

## 29. 3D Dependency Evaluation

Every initial task family MUST be evaluated under:

```text
2D-only
metadata-only
2D+metadata
metadata field masking
metadata shuffle
spatial counterfactual
occluded or weak-visual-evidence subset
```

Claims that Qwen uses 3D metadata require both:

1. `2D+metadata` improves over `2D-only` on genuinely 3D-dependent tasks.
2. Shuffling, masking, or counterfactually changing relevant metadata produces predictable degradation or answer changes.

## 30. Artifact Lineage

Recommended immutable artifacts:

```text
run_manifest.json
dataset_card.yaml
sample_manifest.json
scene_manifest.json
ingestion_report.json
geometry_manifest.json
metadata_snapshot.json
metadata_validation_report.json
task_spec.yaml
prompt_bundle.json
raw_model_output.json
validated_sample.json
quality_event.jsonl
quality_dashboard.json
release_manifest.json
```

Every artifact MUST include:

- artifact ID and schema version;
- parent artifact IDs;
- dataset, scene, split, and run IDs;
- code/model/schema/task/prompt versions;
- creation timestamp and runtime profile;
- input checksums or content digests;
- state, error codes, warnings, and retry history.

Repair and regeneration MUST create new artifacts. Silent overwrite is prohibited.

## 31. Orchestrator State Machine

```text
REGISTERED
  -> SAMPLE_VERIFIED
  -> INGESTED
  -> GEOMETRY_READY
  -> EXPERT_OUTPUTS_READY
  -> METADATA_FUSED
  -> METADATA_VALIDATED
  -> TASK_COMPILED
  -> MODEL_OUTPUT_READY
  -> SAMPLE_VALIDATED
  -> RELEASE_CANDIDATE
  -> RELEASED

Any stage
  -> QUARANTINED
  -> REJECTED
```

Transitions MUST require the preceding gate report. A state label alone is not sufficient.

## 32. Recommended Repository Layout

```text
3D-data-Gen/
├── CLAUDE_CODE_PROJECT_SPEC.md
├── PROJECT_HANDOFF.md
├── docs/
│   ├── architecture.md
│   ├── quality-policy.md
│   └── server-profiles.md
├── registry/
│   ├── datasets/
│   ├── feishu_snapshot/
│   └── selection/
├── agents/
│   └── pipeline-orchestrator/
├── skills/
│   ├── dataset-registry-manager/
│   ├── expert-registry-manager/
│   ├── scene-ingestion-validator/
│   ├── metadata-quality-gate/
│   ├── task-spec-designer/
│   ├── task-prompt-compiler/
│   ├── task-sample-auditor/
│   └── dataset-quality-monitor/
├── adapters/
├── geometry/
├── experts/
├── fusion/
├── metadata/
├── task_specs/
│   ├── grounding/
│   ├── vqa/
│   ├── caption/
│   ├── task_decomposition/
│   ├── dialogue/
│   └── new_tasks/
├── task_adapters/
│   ├── qwen_2d_metadata/
│   ├── pointcloud_native/
│   └── multimodal_3d/
├── prompt_templates/
├── schemas/
├── checkers/
├── configs/
├── tests/
│   ├── fixtures/
│   ├── unit/
│   ├── contract/
│   └── integration/
└── scripts/
```

Do not scaffold the entire tree before the first vertical slice requires it.

## 33. Local Control Plane vs Server Execution Plane

### Local Control Plane

MUST own:

- specifications and Skills;
- schemas and Task Specs;
- prompt templates and checker contracts;
- quality thresholds and release rules;
- synthetic fixtures and contract tests;
- versioned server configuration bundles.

### Server Execution Plane

MUST own:

- dataset download/cache;
- VGGT-Ω and expert inference;
- 2D-to-3D lifting/fusion;
- configured Qwen calls;
- large-scale deterministic validation;
- metrics aggregation, quarantine, and release candidates.

The design MUST NOT hard-code local paths, server secrets, API keys, GPU models, or a specific scheduler. These belong in server profiles or secret management.

## 34. Initial Vertical Slice

Recommended default if the user does not override:

```yaml
datasets:
  count: 1
  type: real_multiview
  selection: UAVScenes                # RESOLVED 2026-08-24

scale_policy:
  metric_required: true               # RESOLVED 2026-08-24
  ineligible: [relative, affine_invariant, pseudo]

metadata_scope:
  layers: [L0, L1, minimal_L2]
  entities: [object]
  required_geometry: [camera, depth, point_cloud, centroid, obb, visibility]

task_scope:
  - 3d_grounding.object
  - 3d_vqa.metric_or_situated
  - cross_view_correspondence          # RESOLVED 2026-08-24 (chosen over metadata_verification)

evaluation:
  - 2d_only
  - metadata_only
  - 2d_plus_metadata
  - metadata_shuffle

expert_scope:
  instance_masks: Grounded-SAM-2
  tracking: SAM-2.1-BasePlus
  optical_flow: SEA-RAFT
  invalid_region_semantics: OneFormer
  uav_semantics: CABiNet-MobileNetV3-Small
  primary_geometry_cross_check: MoGe-3-ViT-L-after-license-confirmation
  independent_normal_cross_check: DSINE-after-license-confirmation
  secondary_depth_pose_cross_check: DA3-1.1-Apache-compatible-variant
  point_track_visibility: CoTracker3-noncommercial-research-only
  cross_view_embedding: DINOv2-Small-or-Base
  deterministic_geometry: TSDF-voxel-ESDF-raycast
```

Vertical-slice order:

1. Freeze IDs, artifact states, minimal schemas, and error codes.
2. Implement one dataset adapter over 1–3 scenes.
3. Run VGGT-Ω and produce geometry diagnostics.
4. Activate the minimum expert set only after license/checkpoint review.
5. Generate masks, tracks, residual-flow evidence, invalid-region masks, and MoGe-3 keyframe geometry cross-checks.
6. Lift/fuse masks into stable object-level metadata.
7. Implement deterministic geometry functions and checkers.
8. Define three Task Specs.
9. Compile prompt bundles without invoking Qwen.
10. Validate leakage and checker reproducibility.
11. Invoke Qwen on a small batch.
12. Audit samples and run dependency baselines.
13. Add DSINE only after testing whether independent normals provide measurable information gain.
14. Evaluate DA3-1.1 disagreement calibration; add DA3-Streaming only for long-video scope.
15. Only then consider Trace Anything, WorldMirror evaluation, thin-obstacle expansion, or additional L3 metadata.

## 35. Implementation Stop Conditions

Claude Code MUST stop and request direction when:

- the initial dataset is not selected and implementation would become dataset-specific;
- metric-scale policy is required but unresolved;
- a license condition blocks the intended use;
- the configured Qwen deployment mode is required but unresolved;
- a schema change would invalidate user-confirmed invariants;
- a quality threshold must be lowered to make progress;
- a task lacks a deterministic or independently auditable target;
- the proposed action would modify Feishu, existing Obsidian notes, or project-governance files outside explicit authorization.

## 36. Unresolved Decisions

```yaml
initial_dataset_selection: UAVScenes          # RESOLVED 2026-08-24; single real multi-view dataset
metric_scale_policy: metric_required          # RESOLVED 2026-08-24; relative-scale scenes are ineligible in v1
initial_task_selection:                       # RESOLVED 2026-08-24
  - 3d_grounding.object
  - 3d_vqa.metric_or_situated
  - cross_view_correspondence
qwen_deployment:
  provider: DEFERRED                          # RESOLVED 2026-08-24: compile-only phase, no model invocation
  model: DEFERRED
  api_or_local: DEFERRED
  budget: DEFERRED
  note: >
    Vertical-slice steps 1-10 (through leakage and checker-reproducibility validation)
    require no model call. Revisit before step 11.
independent_llm_judge: not_in_v1              # deterministic checkers only
quality_thresholds: spec_defaults_pending_calibration
human_audit_ratio: 1.0                        # first batch fully human-reviewed
server_orchestration_framework: none          # scripts + file-based state machine
final_primary_deliverable:
  options: [dataset, benchmark, trained_model, pipeline_toolchain]
  selection: pipeline_toolchain_plus_small_benchmark   # provisional; revisitable after Release A
```

Resolution provenance: the four blocking items were decided by the user on 2026-08-24; see
`PROJECT_HANDOFF.md` §19. The remaining entries are working defaults, not user-confirmed
invariants, and MAY be revised with a recorded reason.

## 37. Evidence Boundaries

- External fact verification cutoff: 2026-08-23.
- The 22 candidate datasets were researched but not all downloaded or fully validated.
- License, current download availability, file inventory, aliases, versions, and redistribution rights MUST be rechecked before ingestion.
- VGGT-Ω performance on target UAV scenes, thin structures, dynamic objects, weak textures, and large-scale blocks remains empirical.
- Two 2026-08-23 expert surveys reviewed official assets but downloaded no checkpoints and performed no local UAV tests.
- The semantic chain remains Grounded-SAM-2/SAM 2.1/SEA-RAFT/OneFormer/CABiNet; the revised geometry priority is MoGe-3 first, DSINE for independent normals, DA3-1.1 for secondary depth/pose/scale checks, and DA3-Streaming only for long-video scope.
- WorldMirror is restricted to inference/evaluation under the currently reviewed license and MUST NOT supply Qwen/VLM training metadata.
- MoGe, DSINE, CoTracker3, Trace Anything, MASt3R, WorldMirror, DA3 variants, and transitive dependencies all require per-checkpoint license review before activation.
- Thin-obstacle, small-aerial-target, dynamic-geometry, and attribute experts are especially dependent on domain validation.
- No claim of zero dataset-search omissions is allowed.

## 38. Primary External Components

```yaml
vggt_omega:
  repository: https://github.com/facebookresearch/vggt-omega
  project: https://vggt-omega.github.io/
  paper: https://arxiv.org/abs/2605.15195

depth_anything_3:
  repository: https://github.com/ByteDance-Seed/Depth-Anything-3

moge_3:
  repository: https://github.com/microsoft/MoGe

dsine:
  repository: https://github.com/baegwangbin/DSINE

cotracker_3:
  repository: https://github.com/facebookresearch/co-tracker

trace_anything:
  repository: https://github.com/ByteDance-Seed/TraceAnything

metric_anything:
  repository: https://github.com/metric-anything/metric-anything

hunyuan_worldmirror:
  repository: https://github.com/Tencent-Hunyuan/HunyuanWorld-Mirror

hy_world_2:
  repository: https://github.com/Tencent-Hunyuan/HY-World-2.0

qwen_3_5:
  documentation: https://help.aliyun.com/zh/model-studio/qwen3-5-plus
```

These URLs are references, not authorization to download, install, or execute components.

---

# Layer 4. Downstream Task Design and Capability Completion

## 39. Purpose

Layer 4 turns the scene package into high-quality downstream supervision. It is the product layer of the pipeline, not an optional language-generation appendix.

The canonical task representation MUST be model-independent. The same task record SHOULD support:

```text
Qwen adapter
    input: 2D images/video + task-local 3D metadata

Native point-cloud adapter
    input: point cloud/voxel/mesh + point/object/route targets

Multimodal 3D adapter
    input: point cloud + images/video + cameras + metadata
```

Qwen still MUST NOT consume raw point clouds in the current architecture. Point-cloud references remain part of the canonical annotation so future 3D models can use the same data.

## 40. Capability Objective

The dataset SHOULD complement abilities commonly underrepresented in indoor or ground-driving 3D training data:

- oblique, nadir, and rapidly changing aerial viewpoints;
- observer-pose-dependent spatial reasoning;
- altitude and metric-scale reasoning;
- sparse, thin, and safety-critical obstacles;
- open-air free/unknown/occupied space;
- long-range visibility and occlusion;
- cross-view identity under large viewpoint changes;
- dynamic obstacles under UAV ego-motion;
- route clearance, flyability, TTC, and swept-volume risk;
- active perception and next-best-view;
- uncertainty-aware decisions in sky/water/glass/weak-geometry regions.

## 41. Canonical Task Record

```json
{
  "sample_id": "task_sample_...",
  "task_spec_id": "uav.route.minimum_clearance@0.1.0",
  "scene_id": "scene_000018",
  "capability_tags": ["metric_geometry", "navigation", "risk"],
  "low_altitude_tags": ["flight_corridor", "thin_obstacle"],
  "supervision_level": "deterministic_derived",
  "inputs": {
    "pointcloud_ref": "scene.ply",
    "visual_inputs": ["f0012.jpg", "f0015.jpg"],
    "camera_refs": ["<pose_007>"],
    "metadata_snapshot_id": "meta_...",
    "visible_metadata_fields": []
  },
  "hidden_target": {
    "target_type": "route_clearance",
    "route_id": "<route_002>",
    "minimum_clearance_m": 1.35,
    "closest_obstacle_id": "<wire_004>"
  },
  "target_geometry": {
    "route_ref": "routes/route_002.json",
    "obstacle_point_indices_ref": "indices/wire_004.bin"
  },
  "evidence": {
    "used_entities": ["<route_002>", "<wire_004>"],
    "used_fields": [],
    "derivation_program": "minimum_route_to_centerline_clearance"
  },
  "checker": {
    "name": "check_route_clearance",
    "version": "0.1.0",
    "tolerance_m": 0.1
  },
  "quality": {},
  "provenance": {},
  "adapters": ["qwen_2d_metadata", "pointcloud_native", "multimodal_3d"]
}
```

Every target MUST map to at least one concrete 3D anchor:

- point indices or point mask;
- object/part ID and OBB;
- centerline or surface;
- voxel/occupancy region;
- camera/observer pose;
- 3D trajectory;
- route/waypoint graph;
- deterministic spatial relation over these anchors.

## 42. Supervision Levels

```text
strong
    native sensor, manual annotation, RTK/LiDAR/GCP, or verified ground truth

deterministic_derived
    computed from gate-passing geometry by a versioned program

filtered_pseudo
    VGGT-Ω/expert output passing confidence and multiview checks

weak
    model proposal, uncertain thin structure, attribute, or relation candidate

language_generated
    natural-language realization whose structured claims/target are independently checked
```

Strong and deterministic-derived labels SHOULD form evaluation data. Filtered-pseudo and weak labels SHOULD primarily form training data unless manually reviewed.

## 43. Task Design Invariants

Every Task Spec MUST pass:

### 43.1 3D Necessity

At least one condition MUST hold:

- target requires metric/relative 3D geometry;
- target is anchored to point-cloud entities not uniquely identifiable from one 2D view;
- answer changes under camera-pose or spatial counterfactual while appearance remains similar;
- task requires cross-view, occlusion, trajectory, occupancy, route, or topology information;
- a 2D-only baseline is demonstrably insufficient on the selected subset.

### 43.2 Low-Altitude Specificity

Each low-altitude-specialized task MUST use at least one of:

- UAV pose, altitude, heading, or camera orientation;
- thin obstacle or sparse open-air geometry;
- flyable/free/unknown volume;
- flight corridor, clearance, reachability, or route constraint;
- aerial active-view or visibility requirement;
- ego-motion-compensated dynamic risk;
- low-altitude scene content such as poles, wires, towers, vegetation, roofs, vehicles, people, or aerial targets.

### 43.3 Verifiability

- target MUST be recomputable or linked to independently reviewed ground truth;
- target MUST NOT appear in visible metadata;
- ambiguity MUST be represented explicitly;
- scale eligibility MUST be enforced;
- evidence and checker MUST be versioned;
- point-cloud/voxel/route target mapping MUST be valid;
- uncertain geometry MUST support `unknown`, interval, or refusal targets.

## 44. Task Family A: Native 3D Perception

| Task | Input | Target | Low-altitude contribution |
|---|---|---|---|
| 3D semantic segmentation | point cloud/voxel | point-wise semantic IDs | aerial roofs, vegetation, poles, wires, open-air regions |
| 3D instance segmentation | point cloud + optional images | instance point masks and stable IDs | sparse objects and large viewpoint changes |
| 3D object detection | point cloud/multimodal | centroid, size, orientation, OBB | oblique-view vehicles, people, towers, aerial targets |
| Thin-structure extraction | point cloud + wire masks | centerline, endpoints, connectivity, uncertainty | power lines, cables, branches, fences |
| Surface/region parsing | cloud/mesh | ground, roof, facade, vegetation, water, unknown regions | low-altitude scene layout |
| 3D tracking | point cloud sequence + cameras | object trajectory, visibility, velocity, covariance | moving objects under strong UAV ego-motion |

Weak thin-structure targets MUST remain distinguishable from verified labels.

## 45. Task Family B: 3D Spatial and Viewpoint Reasoning

| Task | Required metadata | Target/checker |
|---|---|---|
| Metric measurement | metric scale, object geometry, pose | distance/size/height/angle with tolerance |
| Observer-relative relation | observer pose, object centers/OBBs | left/right/front/behind/above/below |
| Structural topology | objects, centerlines, surfaces | connect/intersect/contain/support/hang |
| Visibility and occlusion | cameras, depth, object geometry | visible ratio, occluder ID, best view |
| Cross-view correspondence | masks, cameras, point support, embedding | same-object link and probability |
| Viewpoint transformation | two observer poses, object geometry | transformed situated relations |
| Spatial counterfactual | editable pose/object/route state | recomputed relations, visibility, or risk |
| Geometry-aware retrieval | scene/object spatial signature | matching scene/object group/trajectory |

These tasks SHOULD include hard cases where similar 2D appearance corresponds to different 3D answers.

## 46. Task Family C: Low-Altitude Flight, Safety, and Active Perception

| Task | 3D target | Deterministic basis |
|---|---|---|
| Occupancy/free/unknown prediction | voxel state or probability | TSDF/voxel/raycast plus uncertainty |
| Flyable-volume segmentation | safe/unsafe/unknown volume | occupancy + UAV radius + safety margin |
| Route feasibility | feasible flag and failure reason | swept UAV volume versus obstacles/unknown space |
| Minimum-clearance estimation | clearance and closest obstacle | route-to-surface/centerline distance |
| Corridor bottleneck localization | region/waypoint and limiting obstacle | ESDF minima along route |
| Dynamic collision risk | TTC, collision probability, swept-volume overlap | trajectory/covariance propagation |
| Thin-obstacle avoidance | safe side/waypoint/clearance | wire centerline + uncertainty inflation |
| Next-best-view | selected candidate pose | visibility gain, occlusion, travel cost, uncertainty |
| Inspection-view planning | ordered poses and coverage | target surface visibility and constraints |
| Unknown-space-aware decision | proceed/stop/request-view | free/unknown balance and risk threshold |

No task in this family may use a general VLM estimate as its numerical truth.

## 47. Task Family D: Grounded 3D Language and Interaction

### 47.1 3D Grounding

Targets MAY be object IDs, point masks, OBBs, parts, centerlines, regions, routes, poses, or trajectories.

Required subtypes:

- object/part grounding;
- relational and observer-relative grounding;
- occluded-object grounding;
- thin-obstacle grounding;
- route/waypoint/trajectory grounding.

### 47.2 3D VQA

Required capability groups:

- metric geometry;
- situated relations;
- topology;
- visibility/occlusion;
- temporal motion and TTC;
- route/clearance/risk;
- viewpoint transformation;
- uncertainty and evidence sufficiency;
- spatial counterfactuals.

### 47.3 3D Caption

Caption targets SHOULD cover object, part, region, scene layout, trajectory, visibility, risk, and flight-corridor descriptions. Every caption MUST retain structured claims.

### 47.4 3D Dialogue

Dialogue SHOULD test cross-turn grounding, changing observer pose, metadata updates, clarification under ambiguity, uncertain geometry, and route/risk revision.

### 47.5 3D Task Decomposition and Plan Critique

Each step MUST bind action, target ID, goal pose/region, spatial constraints, preconditions, completion conditions, and evidence. Include plan verification, conflict detection, missing-step completion, and infeasibility explanation.

## 48. Task Family E: Metadata, Scene Graph, and Change Reasoning

| Task | Target |
|---|---|
| Metadata verification | identify conflicting field/source/reason |
| Metadata completion | missing relation, visibility, trajectory, or uncertainty field |
| 3D scene-graph query | executable graph query and result IDs |
| Scene-graph consistency | invalid or impossible node/edge set |
| 3D change reasoning | added/removed/moved/reshaped object and evidence |
| Expert disagreement diagnosis | likely failure source and review decision |
| Evidence selection | minimal fields/views required to support an answer |

VLM-generated scene-graph relations are proposals, not unquestioned truth.

## 49. Capability Coverage Matrix

Every release MUST report coverage by:

```text
perception
metric_geometry
viewpoint_reasoning
cross_view_identity
visibility_occlusion
thin_structure
temporal_motion
occupancy_navigation
flight_safety
active_perception
uncertainty
grounded_language
planning_dialogue
```

It MUST also report distributions across:

- real/simulated;
- metric/externally anchored/relative;
- altitude band;
- nadir/oblique/front view;
- static/dynamic;
- clear/occluded;
- strong/deterministic/pseudo/weak supervision;
- urban/rural/forest/water/industrial/power-infrastructure scenes.

## 50. Task Quality Gates

Before release, each task sample MUST pass:

1. scene and metadata gates G0–G2;
2. valid point-cloud/voxel/object/route target reference;
3. scale and coordinate eligibility;
4. unique answer or explicit ambiguity target;
5. deterministic checker or independent ground truth;
6. target-leakage test;
7. 3D-necessity test;
8. low-altitude tag validation where claimed;
9. evidence sufficiency and provenance completeness;
10. supervision-level policy;
11. negative/hard-case validation;
12. applicable adapter contract tests.

Dataset-level validation MUST include 2D-only, metadata-only, 2D+metadata, pointcloud-only where applicable, metadata masking/shuffling, and spatial counterfactuals.

## 51. Recommended Task Release Order

### Release A: Core portable supervision

- 3D semantic/instance segmentation;
- object/part/thin-structure grounding;
- metric and situated 3D VQA;
- cross-view correspondence;
- visibility/occlusion;
- metadata verification and uncertainty targets.

### Release B: Low-altitude specialization

- thin-obstacle centerline and clearance;
- occupancy/free/unknown;
- flyable-volume segmentation;
- route feasibility and bottleneck localization;
- dynamic tracks, TTC, and swept-volume risk;
- next-best-view and inspection coverage.

### Release C: Language, planning, and long-horizon reasoning

- grounded 3D caption;
- pose-changing dialogue;
- task decomposition and plan critique;
- scene-graph query/completion;
- change reasoning and spatial counterfactuals.

Release A SHOULD be implemented first because it validates the point-cloud/metadata grounding interface. Release B is the primary low-altitude differentiator. Release C SHOULD only use structured targets and claims that already pass deterministic or independent validation.
