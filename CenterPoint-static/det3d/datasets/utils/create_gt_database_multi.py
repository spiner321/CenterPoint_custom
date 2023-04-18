import pickle
from pathlib import Path
import os
import numpy as np

from det3d.core import box_np_ops
from det3d.datasets.dataset_factory import get_dataset
from tqdm import tqdm

from concurrent.futures import ProcessPoolExecutor
from functools import partial

dataset_name_map = {
    "NUSC": "NuScenesDataset",
    "WAYMO": "WaymoDataset",
    "NIA": "NIADataset"
}

def info_distribution(
        data_path,
        info_path=None,
        used_classes=None,
        dbinfo_path=None,
        relative_path=True,
        virtual=False,
        **kwargs,
):
    pipeline = [
        {
            "type": "LoadPointCloudFromFile",
            "dataset": dataset_name_map["NIA"],
        },
        {"type": "LoadPointCloudAnnotations", "with_bbox": True},
    ]

    if "nsweeps" in kwargs:
        dataset = get_dataset("NIA")(
            info_path=info_path,
            root_path=data_path,
            pipeline=pipeline,
            test_mode=True,
            nsweeps=kwargs["nsweeps"],
            virtual=virtual
        )
        nsweeps = dataset.nsweeps
    else:
        dataset = get_dataset("NIA")(
            info_path=info_path, root_path=data_path, test_mode=True, pipeline=pipeline
        )
        nsweeps = 1

    root_path = Path(data_path)

    all_db_infos = {}
    group_counter = 0

    for index in tqdm(range(len(dataset))):
        image_idx = index
        # modified to nuscenes
        sensor_data = dataset.get_sensor_data(index)
        if "image_idx" in sensor_data["metadata"]:
            image_idx = sensor_data["metadata"]["image_idx"]

        if nsweeps > 1:
            points = sensor_data["lidar"]["combined"]
        else:
            points = sensor_data["lidar"]["points"]

        annos = sensor_data["lidar"]["annotations"]
        gt_boxes = annos["boxes"]
        names = annos["names"]

        group_dict = {}
        group_ids = np.full([gt_boxes.shape[0]], -1, dtype=np.int64)
        if "group_ids" in annos:
            group_ids = annos["group_ids"]
        else:
            group_ids = np.arange(gt_boxes.shape[0], dtype=np.int64)
        difficulty = np.zeros(gt_boxes.shape[0], dtype=np.int32)
        if "difficulty" in annos:
            difficulty = annos["difficulty"]

        num_obj = gt_boxes.shape[0]
        if num_obj == 0:
            continue
        point_indices = box_np_ops.points_in_rbbox(points, gt_boxes)
        for i in range(num_obj):
            if (used_classes is None) or names[i] in used_classes:
                db_info = {
                    "name": names[i],
                    "image_idx": image_idx,
                    "gt_idx": i,
                    "box3d_lidar": gt_boxes[i],
                    "difficulty": difficulty[i],
                    # "group_id": -1,
                    # "bbox": bboxes[i],
                }
                local_group_id = group_ids[i]
                # if local_group_id >= 0:
                if local_group_id not in group_dict:
                    group_dict[local_group_id] = group_counter
                    group_counter += 1
                db_info["group_id"] = group_dict[local_group_id]
                if "score" in annos:
                    db_info["score"] = annos["score"][i]
                if names[i] in all_db_infos:
                    all_db_infos[names[i]].append(db_info)
                else:
                    all_db_infos[names[i]] = [db_info]

    print(str(info_path).split('/')[-1], "dataset length: ", len(dataset))
    for k, v in all_db_infos.items():
        print(f"load {len(v)} {k} database infos")

    # import json
    # import pickle
    # with open(f'{root_path}/all_db_infos.pkl', 'w') as f:
    #     pickle.dump(all_db_infos, f)



def get_gt_data(
    dataset_idx, dataset,
    dataset_class_name, data_path, info_path, used_classes, db_path, dbinfo_path, relative_path, virtual, nsweeps
    ):

    all_db_infos = {}
    group_counter = 0

    for index in tqdm(dataset_idx):
        image_idx = index
        # modified to nuscenes
        sensor_data = dataset.get_sensor_data(index)
        # print(sensor_data)
        if "image_idx" in sensor_data["metadata"]:
            image_idx = sensor_data["metadata"]["image_idx"]

        if nsweeps > 1:
            points = sensor_data["lidar"]["combined"]
        else:
            points = sensor_data["lidar"]["points"]

        annos = sensor_data["lidar"]["annotations"]
        gt_boxes = annos["boxes"]
        names = annos["names"]

        if dataset_class_name == 'WAYMO':
            # waymo dataset contains millions of objects and it is not possible to store
            # all of them into a single folder
            # we randomly sample a few objects for gt augmentation
            # We keep all cyclist as they are rare
            if index % 4 != 0:
                mask = (names == 'VEHICLE')
                mask = np.logical_not(mask)
                names = names[mask]
                gt_boxes = gt_boxes[mask]

            if index % 2 != 0:
                mask = (names == 'PEDESTRIAN')
                mask = np.logical_not(mask)
                names = names[mask]
                gt_boxes = gt_boxes[mask]

        group_dict = {}
        group_ids = np.full([gt_boxes.shape[0]], -1, dtype=np.int64)
        if "group_ids" in annos:
            group_ids = annos["group_ids"]
        else:
            group_ids = np.arange(gt_boxes.shape[0], dtype=np.int64)
        difficulty = np.zeros(gt_boxes.shape[0], dtype=np.int32)
        if "difficulty" in annos:
            difficulty = annos["difficulty"]

        num_obj = gt_boxes.shape[0]
        if num_obj == 0:
            continue
        point_indices = box_np_ops.points_in_rbbox(points, gt_boxes)
        for i in range(num_obj):
            if (used_classes is None) or names[i] in used_classes:
                filename = f"{image_idx}_{names[i]}_{i}.bin"
                dirpath = os.path.join(str(db_path), names[i])
                os.makedirs(dirpath, exist_ok=True)

                filepath = os.path.join(str(db_path), names[i], filename)
                gt_points = points[point_indices[:, i]]
                gt_points[:, :3] -= gt_boxes[i, :3]
                with open(filepath, "w") as f:
                    try:
                        gt_points.tofile(f)
                    except:
                        print("process {} files".format(index))
                        break

            if (used_classes is None) or names[i] in used_classes:
                if relative_path:
                    db_dump_path = os.path.join(db_path.stem, names[i], filename)
                else:
                    db_dump_path = str(filepath)

                db_info = {
                    "name": names[i],
                    "path": db_dump_path,
                    "image_idx": image_idx,
                    "gt_idx": i,
                    "box3d_lidar": gt_boxes[i],
                    "num_points_in_gt": gt_points.shape[0],
                    "difficulty": difficulty[i],
                    # "group_id": -1,
                    # "bbox": bboxes[i],
                }
                local_group_id = group_ids[i]
                # if local_group_id >= 0:
                if local_group_id not in group_dict:
                    group_dict[local_group_id] = group_counter
                    group_counter += 1
                db_info["group_id"] = group_dict[local_group_id]
                if "score" in annos:
                    db_info["score"] = annos["score"][i]
                if names[i] in all_db_infos:
                    all_db_infos[names[i]].append(db_info)
                else:
                    all_db_infos[names[i]] = [db_info]

    return all_db_infos


def create_groundtruth_database(
        dataset_class_name,
        data_path,
        info_path=None,
        used_classes=None,
        db_path=None,
        dbinfo_path=None,
        relative_path=True,
        virtual=False,
        **kwargs,
):
    pipeline = [
        {
            "type": "LoadPointCloudFromFile",
            "dataset": dataset_name_map[dataset_class_name],
        },
        {"type": "LoadPointCloudAnnotations", "with_bbox": True},
    ]

    if "nsweeps" in kwargs:
        dataset = get_dataset(dataset_class_name)(
            info_path=info_path,
            root_path=data_path,
            pipeline=pipeline,
            test_mode=True,
            nsweeps=kwargs["nsweeps"],
            virtual=virtual
        )
        nsweeps = dataset.nsweeps
    else:
        dataset = get_dataset(dataset_class_name)(
            info_path=info_path, root_path=data_path, test_mode=True, pipeline=pipeline
        )
        nsweeps = 1

    root_path = Path(data_path)

    if dataset_class_name in ["WAYMO", "NUSC"]:
        if db_path is None:
            if virtual:
                db_path = root_path / f"gt_database_{nsweeps}sweeps_withvelo_virtual"
            else:
                db_path = root_path / f"gt_database_{nsweeps}sweeps_withvelo"
        if dbinfo_path is None:
            if virtual:
                dbinfo_path = root_path / f"dbinfos_train_{nsweeps}sweeps_withvelo_virtual.pkl"
            else:
                dbinfo_path = root_path / f"dbinfos_train_{nsweeps}sweeps_withvelo.pkl"
    elif dataset_class_name in ["NIA"]:
        if db_path is None:
            if virtual:
                db_path = root_path / f"gt_database_{kwargs['sensor']}_virtual"
            else:
                db_path = root_path / f"gt_database_{kwargs['sensor']}"
        if dbinfo_path is None:
            if virtual:
                dbinfo_path = root_path / f"dbinfos_train_{kwargs['sensor']}_virtual.pkl"
            else:
                dbinfo_path = root_path / f"dbinfos_train_{kwargs['sensor']}.pkl"
    else:
        raise NotImplementedError()

    db_path.mkdir(parents=True, exist_ok=True)
    
    work_array = np.arange(len(dataset))[:40]

    num_process = kwargs['num_process']
    batch_size = len(work_array) // num_process
    start_end_idx = [{"start": i * batch_size, "end": (i + 1) * batch_size} for i in range(num_process+1)]

    results = []
    futures = []
    with ProcessPoolExecutor(max_workers=num_process) as executor:
        for idx in start_end_idx:
            batch = work_array[idx["start"]:idx["end"]]
            task = partial(
                            get_gt_data, 
                            batch,
                            dataset,
                            dataset_class_name,
                            data_path,
                            info_path,
                            used_classes,
                            db_path,
                            dbinfo_path,
                            relative_path,
                            virtual,
                            nsweeps
                            )
            future = executor.submit(task)
            futures.append(future)
            # all_db_infos.append(result)
        
        for future in futures:
            result = future.result()
            results.append(result)
    
    # from itertools import chain
    # from collections import defaultdict
    
    # reindexing group_id
    all_db_infos = {'median_strip': [],
                    'road_sign': [],
                    'overpass': [],
                    'ramp_sect': [],
                    'sound_barrier': [],
                    'street_trees': [],
                    'tunnel': [],
                    }

    group_counter = 0
    for dbinfo in results:

        for v_ls in dbinfo.values():
            for v in v_ls:
                v['group_id'] += group_counter

        for k_ls in dbinfo.keys():
            group_counter += len(dbinfo[k_ls])

        for k, v in dbinfo.items():
            if k in all_db_infos.keys():
                all_db_infos[k].extend(v)

    del_keys = []
    for k, v in all_db_infos.items():
        if len(v) == 0:
            del_keys.append(k)

    for k in del_keys:
        del all_db_infos[k]
        # all_db_infos.pop(k)


    print("dataset length: ", len(dataset))
    for k, v in all_db_infos.items():
        print(f"load {len(v)} {k} database infos")

    with open(dbinfo_path, "wb") as f:
        pickle.dump(all_db_infos, f)