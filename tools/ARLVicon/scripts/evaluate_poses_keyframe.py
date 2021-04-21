import os
import glob

import copy
import random

import numpy as np
import numpy.ma as ma

import cv2
from PIL import Image
import matplotlib.pyplot as plt

import scipy.io as scio
from scipy.spatial.transform import Rotation as R

from sklearn.neighbors import KDTree

import torch
import torch.nn as nn
import torch.nn.parallel
import torch.backends.cudnn as cudnn
import torch.optim as optim
import torch.utils.data
import torchvision.datasets as dset
import torchvision.transforms as transforms
import torchvision.utils as vutils
import torch.nn.functional as F
from torch.autograd import Variable

#######################################
#######################################

from lib.network import PoseNet, PoseRefineNet
from lib.transformations import euler_matrix, quaternion_matrix, quaternion_from_matrix

#######################################
#######################################

from tools.ARLVicon.utils import helper_utils

from tools.ARLVicon import cfg as config
from tools.ARLVicon.utils.dataset import vicon_dataset_utils

from tools.ARLVicon.utils.pose.load_obj_ply_files import load_obj_ply_files
from tools.ARLVicon.utils.bbox.extract_bboxs_from_label import get_obj_bbox

#######################################
#######################################

def main():

    ##################################
    ## DENSEFUSION
    ##################################

    estimator = PoseNet(num_points=config.NUM_PT, num_obj=config.NUM_OBJECTS)
    estimator.cuda()
    estimator.load_state_dict(torch.load(config.PRE_TRAINED_MODEL))
    estimator.eval()

    refiner = PoseRefineNet(num_points=config.NUM_PT, num_obj=config.NUM_OBJECTS)
    refiner.cuda()
    refiner.load_state_dict(torch.load(config.PRE_TRAINED_REFINE_MODEL))
    refiner.eval()

    ###################################
    # Load Ply files
    ###################################

    cld, cld_obj_centered, cld_obj_part_centered, obj_classes, obj_part_classes, obj_ids, obj_part_ids = load_obj_ply_files()

    ##################################
    ##################################

    # image_files = open('{}'.format(config.TRAIN_FILE), "r")
    # image_files = open('{}'.format(config.VAL_FILE), "r")
    image_files = open('{}'.format(config.TEST_FILE), "r")
    image_files = image_files.readlines()
    print("Loaded Files: {}".format(len(image_files)))

    # select random test images
    # np.random.seed(0)
    # num_files = 25
    # random_idx = np.random.choice(np.arange(0, int(len(image_files)), 1), size=int(num_files), replace=False)
    # image_files = np.array(image_files)[random_idx]
    # print("Chosen Files: {}".format(len(image_files)))

    ##################################
    ##################################

    for image_idx, image_addr in enumerate(image_files):

        ##################################
        # init
        ##################################

        image_addr = image_addr.rstrip()
        dataset_dir = image_addr.split('rgb/')[0]
        image_num = image_addr.split('rgb/')[-1]

        print('\nimage:{}/{}, file:{}'.format(image_idx+1, len(image_files), image_addr))

        rgb_addr = dataset_dir + 'rgb/' + image_num + config.RGB_EXT
        depth_addr = dataset_dir + 'depth/' + image_num + config.DEPTH_EXT
        label_addr = dataset_dir + 'masks_obj/' + image_num + config.OBJ_LABEL_EXT

        rgb = np.array(Image.open(rgb_addr))[..., :3]
        depth = np.array(Image.open(depth_addr))
        label = np.array(Image.open(label_addr))

        ##################################
        ### RESIZE & CROP
        ##################################

        rgb = cv2.resize(rgb, config.RESIZE, interpolation=cv2.INTER_CUBIC)
        label = cv2.resize(label, config.RESIZE, interpolation=cv2.INTER_NEAREST)
        depth = cv2.resize(depth, config.RESIZE, interpolation=cv2.INTER_NEAREST)

        rgb = helper_utils.crop(pil_img=rgb, crop_size=config.CROP_SIZE, is_img=True)
        label = helper_utils.crop(pil_img=label, crop_size=config.CROP_SIZE)
        depth = helper_utils.crop(pil_img=depth, crop_size=config.CROP_SIZE)

        ##################################
        # META
        ##################################

        # gt pose
        meta_addr = dataset_dir + 'meta/' + image_num + config.META_EXT
        meta = scio.loadmat(meta_addr)

        cv2_gt_img = rgb.copy()
        cv2_pred_img = rgb.copy()

        ##################################
        ##################################

        obj_ids = np.array(meta['object_class_ids']).flatten()
        label_obj_ids = np.unique(label)[1:]

        # TODO: MATLAB EVAL
        class_ids_list = [obj_ids]
        pose_est_gt = []
        pose_est_df_wo_refine = []
        pose_est_df_iterative = []

        ##################################
        ##################################

        for idx, obj_id in enumerate(obj_ids):
            if obj_id in label_obj_ids:
                print("Object:", obj_classes[int(obj_id) - 1])
                obj_color = vicon_dataset_utils.obj_color_map(obj_id)

                ##################################
                # GT POSE
                ##################################

                obj_meta_idx = str(1000 + obj_id)[1:]
                target_r = meta['obj_rotation_' + np.str(obj_meta_idx)]
                target_t = meta['obj_translation_' + np.str(obj_meta_idx)]

                # TODO: MATLAB EVAL
                gt_quart = quaternion_from_matrix(target_r)
                my_pred = np.append(np.array(gt_quart), np.array(target_t))
                pose_est_gt.append(my_pred.tolist())

                # projecting 3D model to 2D image
                imgpts, jac = cv2.projectPoints(cld[obj_id] * 1e3, target_r, target_t * 1e3, config.CAM_MAT, config.CAM_DIST)
                cv2_gt_img = cv2.polylines(cv2_gt_img, helper_utils.sort_imgpts(imgpts), True, obj_color)

                # draw pose
                rotV, _ = cv2.Rodrigues(target_r)
                points = np.float32([[100, 0, 0], [0, 100, 0], [0, 0, 100], [0, 0, 0]]).reshape(-1, 3)
                axisPoints, _ = cv2.projectPoints(points, rotV, target_t * 1e3, config.CAM_MAT, config.CAM_DIST)
                cv2_gt_img = cv2.line(cv2_gt_img, tuple(axisPoints[3].ravel()), tuple(axisPoints[0].ravel()), (255, 0, 0), 3)
                cv2_gt_img = cv2.line(cv2_gt_img, tuple(axisPoints[3].ravel()), tuple(axisPoints[1].ravel()), (0, 255, 0), 3)
                cv2_gt_img = cv2.line(cv2_gt_img, tuple(axisPoints[3].ravel()), tuple(axisPoints[2].ravel()), (0, 0, 255), 3)

                try:
                    ##################################
                    # MASK
                    ##################################

                    mask_label = ma.getmaskarray(ma.masked_equal(label, obj_id))
                    mask_rgb = np.repeat(mask_label, 3).reshape(label.shape[0], label.shape[1], -1) * rgb
                    # mask_depth = mask_label * ma.getmaskarray(ma.masked_not_equal(depth, 0))
                    mask_depth = mask_label * depth

                    ##################################
                    # BBOX
                    ##################################

                    x1, y1, x2, y2 = get_obj_bbox(mask_label, obj_id, config.HEIGHT, config.WIDTH, config.BORDER_LIST)

                    # drawing bbox
                    cv2_gt_img = cv2.rectangle(cv2_gt_img, (x1, y1), (x2, y2), obj_color, 2)

                    cv2_gt_img = cv2.putText(cv2_gt_img,
                                              vicon_dataset_utils.map_obj_id_to_name(obj_id),
                                              (x1, y1 - 5),
                                              cv2.FONT_ITALIC,
                                              0.4,
                                              obj_color)

                    cv2_pred_img = cv2.rectangle(cv2_pred_img, (x1, y1), (x2, y2), obj_color, 2)

                    cv2_pred_img = cv2.putText(cv2_pred_img,
                                             vicon_dataset_utils.map_obj_id_to_name(obj_id),
                                             (x1, y1 - 5),
                                             cv2.FONT_ITALIC,
                                             0.4,
                                             obj_color)

                    ##################################
                    # Select Region of Interest
                    ##################################

                    choose = mask_depth[y1:y2, x1:x2].flatten().nonzero()[0]

                    if len(choose) > config.NUM_PT:
                        c_mask = np.zeros(len(choose), dtype=int)
                        c_mask[:config.NUM_PT] = 1
                        np.random.shuffle(c_mask)
                        choose = choose[c_mask.nonzero()]
                    else:
                        choose = np.pad(choose, (0, config.NUM_PT - len(choose)), 'wrap')

                    rgb_masked = np.transpose(np.array(rgb)[:, :, :3], (2, 0, 1))[:, y1:y2, x1:x2]
                    depth_masked = depth[y1:y2, x1:x2].flatten()[choose][:, np.newaxis].astype(np.float32)
                    xmap_masked = config.XMAP[y1:y2, x1:x2].flatten()[choose][:, np.newaxis].astype(np.float32)
                    ymap_masked = config.YMAP[y1:y2, x1:x2].flatten()[choose][:, np.newaxis].astype(np.float32)
                    choose = np.array([choose])

                    ######################################
                    # create point cloud from depth image
                    ######################################

                    pt2 = depth_masked / config.CAMERA_SCALE
                    pt0 = (ymap_masked - config.CAM_CX) * pt2 / config.CAM_FX
                    pt1 = (xmap_masked - config.CAM_CY) * pt2 / config.CAM_FY
                    cloud = np.concatenate((pt0, pt1, pt2), axis=1)

                    ######################################
                    ######################################

                    img_masked = np.array(rgb)[:, :, :3]
                    img_masked = np.transpose(img_masked, (2, 0, 1))
                    # y1:y2, x1:x2
                    img_masked = img_masked[:, y1:y2, x1:x2]

                    cloud = torch.from_numpy(cloud.astype(np.float32))
                    choose = torch.LongTensor(choose.astype(np.int32))
                    img_masked = config.NORM(torch.from_numpy(img_masked.astype(np.float32)))
                    index = torch.LongTensor([obj_id - 1])

                    cloud = Variable(cloud).cuda()
                    choose = Variable(choose).cuda()
                    img_masked = Variable(img_masked).cuda()
                    index = Variable(index).cuda()

                    cloud = cloud.view(1, config.NUM_PT, 3)
                    img_masked = img_masked.view(1, 3, img_masked.size()[1], img_masked.size()[2])

                    #######################################
                    #######################################

                    pred_r, pred_t, pred_c, emb = estimator(img_masked, cloud, choose, index)
                    pred_r = pred_r / torch.norm(pred_r, dim=2).view(1, config.NUM_PT, 1)

                    pred_c = pred_c.view(config.BATCH_SIZE, config.NUM_PT)
                    how_max, which_max = torch.max(pred_c, 1)
                    pred_t = pred_t.view(config.BATCH_SIZE * config.NUM_PT, 1, 3)
                    points = cloud.view(config.BATCH_SIZE * config.NUM_PT, 1, 3)

                    my_r = pred_r[0][which_max[0]].view(-1).cpu().data.numpy()
                    my_t = (points + pred_t)[which_max[0]].view(-1).cpu().data.numpy()
                    my_pred = np.append(my_r, my_t)
                    # TODO: MATLAB EVAL
                    pose_est_df_wo_refine.append(my_pred.tolist())

                    for ite in range(0, config.REFINE_ITERATIONS):
                        T = Variable(torch.from_numpy(my_t.astype(np.float32))).cuda().view(1, 3).repeat(config.NUM_PT, 1).contiguous().view(1, config.NUM_PT, 3)
                        my_mat = quaternion_matrix(my_r)
                        R = Variable(torch.from_numpy(my_mat[:3, :3].astype(np.float32))).cuda().view(1, 3, 3)
                        my_mat[0:3, 3] = my_t

                        new_cloud = torch.bmm((cloud - T), R).contiguous()
                        pred_r, pred_t = refiner(new_cloud, emb, index)
                        pred_r = pred_r.view(1, 1, -1)
                        pred_r = pred_r / (torch.norm(pred_r, dim=2).view(1, 1, 1))
                        my_r_2 = pred_r.view(-1).cpu().data.numpy()
                        my_t_2 = pred_t.view(-1).cpu().data.numpy()
                        my_mat_2 = quaternion_matrix(my_r_2)

                        my_mat_2[0:3, 3] = my_t_2

                        my_mat_final = np.dot(my_mat, my_mat_2)
                        my_r_final = copy.deepcopy(my_mat_final)
                        my_r_final[0:3, 3] = 0
                        my_r_final = quaternion_from_matrix(my_r_final, True)
                        my_t_final = np.array([my_mat_final[0][3], my_mat_final[1][3], my_mat_final[2][3]])

                        my_pred = np.append(my_r_final, my_t_final)
                        my_r = my_r_final
                        my_t = my_t_final
                    # TODO: MATLAB EVAL
                    pose_est_df_iterative.append(my_pred.tolist())

                    ############################
                    # pred
                    ############################

                    obj_r = quaternion_matrix(my_r)[0:3, 0:3]
                    obj_t = my_t

                    # projecting 3D model to 2D image
                    imgpts, jac = cv2.projectPoints(cld[obj_id] * 1e3, obj_r, obj_t * 1e3, config.CAM_MAT, config.CAM_DIST)
                    cv2_pred_img = cv2.polylines(cv2_pred_img, helper_utils.sort_imgpts(imgpts), True, obj_color)

                    # draw pose
                    rotV, _ = cv2.Rodrigues(obj_r)
                    points = np.float32([[100, 0, 0], [0, 100, 0], [0, 0, 100], [0, 0, 0]]).reshape(-1, 3)
                    axisPoints, _ = cv2.projectPoints(points, rotV, obj_t * 1e3, config.CAM_MAT, config.CAM_DIST)
                    cv2_pred_img = cv2.line(cv2_pred_img, tuple(axisPoints[3].ravel()), tuple(axisPoints[0].ravel()), (255, 0, 0), 3)
                    cv2_pred_img = cv2.line(cv2_pred_img, tuple(axisPoints[3].ravel()), tuple(axisPoints[1].ravel()), (0, 255, 0), 3)
                    cv2_pred_img = cv2.line(cv2_pred_img, tuple(axisPoints[3].ravel()), tuple(axisPoints[2].ravel()), (0, 0, 255), 3)

                    ############################
                    # Error Metrics
                    ############################

                    T_pred, R_pred = obj_t, obj_r
                    T_gt, R_gt = target_t, target_r

                    # ADD
                    pred = np.dot(cld[obj_id], R_pred)
                    pred = np.add(pred, T_pred)
                    target = np.dot(cld[obj_id], R_gt)
                    target = np.add(target, T_gt)
                    ADD = np.mean(np.linalg.norm(pred - target, axis=1))

                    # ADD-S
                    tree = KDTree(pred)
                    dist, ind = tree.query(target)
                    ADD_S = np.mean(dist)

                    # translation
                    T_error = np.linalg.norm(T_pred - T_gt)

                    # rot
                    error_cos = 0.5 * (np.trace(R_pred @ np.linalg.inv(R_gt)) - 1.0)
                    error_cos = min(1.0, max(-1.0, error_cos))
                    error = np.arccos(error_cos)
                    R_error = 180.0 * error / np.pi

                    print("\tADD: {:.2f} [cm]".format(ADD * 100))  # [cm]
                    print("\tADD-S: {:.2f} [cm]".format(ADD_S * 100))
                    print("\tT: {:.2f} [cm]".format(T_error * 100))  # [cm]
                    print("\tRot: {:.2f} [deg]".format(R_error))

                except ZeroDivisionError:
                    print("DenseFusion Detector Lost keyframe ..")
                    # TODO: MATLAB EVAL
                    pose_est_df_wo_refine.append([0.0 for i in range(7)])
                    pose_est_df_iterative.append([0.0 for i in range(7)])

            #####################
            # PLOTTING
            #####################
            depth = helper_utils.convert_16_bit_depth_to_8_bit(depth)
            color_label = vicon_dataset_utils.colorize_obj_mask(label)

            # cv2.imshow('rgb', cv2.cvtColor(rgb, cv2.COLOR_BGR2RGB))
            # cv2.imshow('depth', depth)
            # cv2.imshow('heatmap', cv2.applyColorMap(depth, cv2.COLORMAP_JET))
            # cv2.imshow('label', cv2.cvtColor(color_label, cv2.COLOR_BGR2RGB))
            cv2.imshow('gt_pose', cv2.cvtColor(cv2_gt_img, cv2.COLOR_BGR2RGB))
            cv2.imshow('pred_pose', cv2.cvtColor(cv2_pred_img, cv2.COLOR_BGR2RGB))

            cv2.waitKey(1)

            ############################
            # TODO: MATLAB EVAL
            ############################

            scio.savemat('{0}/{1}.mat'.format(config.EVAL_FOLDER_GT, '%04d' % image_idx),
                         {"class_ids": class_ids_list, 'poses': pose_est_gt})
            scio.savemat('{0}/{1}.mat'.format(config.EVAL_FOLDER_DF_WO_REFINE, '%04d' % image_idx),
                         {"class_ids": class_ids_list, 'poses': pose_est_df_wo_refine})
            scio.savemat('{0}/{1}.mat'.format(config.EVAL_FOLDER_DF_ITERATIVE, '%04d' % image_idx),
                         {"class_ids": class_ids_list, 'poses': pose_est_df_iterative})

            print("*** Finished {0}/{1} keyframes ***\n".format(image_idx + 1, len(image_files)))

if __name__ == '__main__':
    main()