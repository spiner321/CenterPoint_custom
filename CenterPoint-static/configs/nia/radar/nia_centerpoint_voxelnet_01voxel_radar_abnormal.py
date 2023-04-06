import itertools
import logging

from det3d.utils.config_tool import get_downsample_factor

# tasks = [
#     dict(num_class=1, class_names=["car"]),
#     dict(num_class=2, class_names=["truck", "construction_vehicle"]),
#     dict(num_class=1, class_names=["bus"]),
#     dict(num_class=2, class_names=["motorcycle", "bicycle"]),
#     dict(num_class=1, class_names=["pedestrian"]),
# ]

tasks = [
    dict(num_class=1, class_names=["median_strip"]),
    dict(num_class=1, class_names=["road_sign"]),
    dict(num_class=1, class_names=["ramp_sect"]),
    dict(num_class=1, class_names=["sound_barrier"]),
    dict(num_class=1, class_names=["overpass"]),
    dict(num_class=1, class_names=["tunnel"]),
    dict(num_class=1, class_names=["street_trees"]),
]

# tasks = [
#     dict(num_class=1, class_names=["median_strip"]),
#     dict(num_class=2, class_names=["road_sign", "ramp_sect"]),
#     dict(num_class=1, class_names=["sound_barrier"]),
#     dict(num_class=2, class_names=["overpass", "tunnel"]),
#     dict(num_class=1, class_names=["street_trees"]),
# ]

class_names = list(itertools.chain(*[t["class_names"] for t in tasks]))

# training and testing settings
target_assigner = dict(
    tasks=tasks,
)

# model settings
model = dict(
    type="VoxelNet",
    pretrained=None,
    reader=dict(
        type="VoxelFeatureExtractorV3",
        num_input_features=4,
    ),
    backbone=dict(
        type="SpMiddleResNetFHD", num_input_features=4, ds_factor=8
    ),
    neck=dict(
        type="RPN",
        layer_nums=[5, 5],
        ds_layer_strides=[1, 2],
        ds_num_filters=[128, 256],
        us_layer_strides=[1, 2],
        us_num_filters=[256, 256],
        num_input_features=256,
        logger=logging.getLogger("RPN"),
    ),
    bbox_head=dict(
        type="CenterHead",
        in_channels=sum([256, 256]),
        tasks=tasks,
        dataset='nuscenes',
        weight=0.25,
        code_weights=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.2, 0.2, 1.0, 1.0],
        common_heads={'reg': (2, 2), 'height': (1, 2), 'dim':(3, 2), 'rot':(2, 2), 'vel': (2, 2)}, # (output_channel, num_conv)
        share_conv_channel=64,
        dcn_head=False 
    ),
)

assigner = dict(
    target_assigner=target_assigner,
    out_size_factor=get_downsample_factor(model),
    gaussian_overlap=0.1,
    max_objs=500,
    min_radius=2,
)


train_cfg = dict(assigner=assigner)

test_cfg = dict(
    post_center_limit_range=[-61.2, -61.2, -10.0, 61.2, 61.2, 10.0],
    nms=dict(
        nms_pre_max_size=1000,
        nms_post_max_size=83,
        nms_iou_threshold=0.2,
    ),
    score_threshold=0.1,
    pc_range=[-51.2, -51.2],
    out_size_factor=get_downsample_factor(model),
    voxel_size=[0.1, 0.1]
)


# dataset settings
dataset_type = "NIADataset"
nsweeps = 1
data_root = "/data/kimgh/CenterPoint-custom/CenterPoint-static/data"

db_sampler = dict(
    type="GT-AUG",
    enable=False,
    db_info_path= data_root + "/dbinfos_train_lidar.pkl",
    sample_groups=[
        dict(median_strip=3),
        dict(road_sign=3),
        dict(ramp_sect=7),
        dict(sound_barrier=3),
        dict(overpass=2),
        dict(tunnel=6),
        dict(street_trees=4),
    ],
    db_prep_steps=[
        dict(
            filter_by_min_num_points=dict(
                median_strip=5,
                road_sign=5,
                sound_barrier=5,
                ramp_sect=5,
                overpass=5,
                tunnel=5,
                street_trees=5,
            )
        ),
        dict(filter_by_difficulty=[-1],),
    ],
    global_random_rotation_range_per_object=[0, 0],
    rate=1.0,
)
train_preprocessor = dict(
    mode="train",
    shuffle_points=True,
    global_rot_noise=[-0.3925, 0.3925],
    global_scale_noise=[0.95, 1.05],
    db_sampler=db_sampler,
    class_names=class_names,
)

val_preprocessor = dict(
    mode="val",
    shuffle_points=False,
)

voxel_generator = dict(
    range=[-51.2, -51.2, -5.0, 51.2, 51.2, 3.0],
    voxel_size=[0.1, 0.1, 0.2],
    max_points_in_voxel=10,
    max_voxel_num=[90000, 120000],
)

train_pipeline = [
    dict(type="LoadPointCloudFromFile", dataset=dataset_type),
    dict(type="LoadPointCloudAnnotations", with_bbox=True),
    dict(type="Preprocess", cfg=train_preprocessor),
    dict(type="Voxelization", cfg=voxel_generator),
    dict(type="AssignLabel", cfg=train_cfg["assigner"]),
    dict(type="Reformat"),
]
test_pipeline = [
    dict(type="LoadPointCloudFromFile", dataset=dataset_type),
    dict(type="LoadPointCloudAnnotations", with_bbox=True),
    dict(type="Preprocess", cfg=val_preprocessor),
    dict(type="Voxelization", cfg=voxel_generator),
    dict(type="AssignLabel", cfg=train_cfg["assigner"]),
    dict(type="Reformat"),
]

train_anno = data_root + "/infos_train_filter_True_lidar.pkl"
val_anno = data_root + "/infos_test_abnormal_filter_True_radar.pkl"
# val_anno = "/workspace/CenterPoint-NIA/data/nia/infos_extreme_val_filter_True_lidar.pkl" # extreme
test_anno = None

data = dict(
    samples_per_gpu=3,
    workers_per_gpu=3
,
    train=dict(
        type=dataset_type,
        root_path=data_root,
        info_path=train_anno,
        ann_file=train_anno,
        nsweeps=nsweeps,
        class_names=class_names,
        pipeline=train_pipeline,
    ),
    val=dict(
        type=dataset_type,
        root_path=data_root,
        info_path=val_anno,
        test_mode=True,
        ann_file=val_anno,
        nsweeps=nsweeps,
        class_names=class_names,
        pipeline=test_pipeline,
    ),
    test=dict(
        type=dataset_type,
        root_path=data_root,
        info_path=test_anno,
        ann_file=test_anno,
        nsweeps=nsweeps,
        class_names=class_names,
        pipeline=test_pipeline,
    ),
)



optimizer_config = dict(grad_clip=dict(max_norm=35, norm_type=2))

# optimizer
optimizer = dict(
    type="adam", amsgrad=0.0, wd=0.01, fixed_wd=True, moving_average=False,
)
lr_config = dict(
    type="one_cycle", lr_max=0.001, moms=[0.95, 0.85], div_factor=10.0, pct_start=0.4,
)

checkpoint_config = dict(interval=1)
# yapf:disable
log_config = dict(
    interval=5,
    hooks=[
        dict(type="TextLoggerHook"),
    ],
)
# yapf:enable
# runtime settings
total_epochs = 1
device_ids = range(8)
dist_params = dict(backend="nccl", init_method="env://")
log_level = "INFO"
work_dir = './work_dirs/{}/'.format(__file__[__file__.rfind('/') + 1:-3])
checkpoint_dir = work_dir + 'latest.pth'
sensor = 'lidar'
load_from = None 
resume_from = None
workflow = [('train', 1)]