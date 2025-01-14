import glob
import numpy as np

#######################################
#######################################

import sys
sys.path.append('../../../')

#######################################
#######################################

import affpose.ARLAffPose.cfg as config

################################
# TRAIN
################################
print('\n-------- TRAIN --------')

# real
real_gt_label_addr = config.DATA_DIRECTORY_TRAIN + 'rgb/' + '*' + config.RGB_EXT
real_files = np.sort(np.array(glob.glob(real_gt_label_addr)))
# TODO: selecting every ith images.
total_idx = np.arange(0, len(real_files), 1)  # config.SELECT_EVERY_ITH_FRAME_TRAIN)
# train_idx = np.random.choice(total_idx, size=int(400), replace=False)
real_files = np.sort(np.array(real_files)[total_idx])
print('Loaded {} Images'.format(len(real_files)))

# syn
syn_gt_label_addr = config.SYN_DATA_DIRECTORY_TRAIN + 'rgb/' + '*' + config.RGB_EXT
syn_train_files = np.sort(np.array(glob.glob(syn_gt_label_addr)))
syn_gt_label_addr = config.SYN_DATA_DIRECTORY_VAL + 'rgb/' + '*' + config.RGB_EXT
syn_val_files = np.sort(np.array(glob.glob(syn_gt_label_addr)))
syn_files = np.sort(np.array(np.hstack([syn_train_files, syn_val_files])))
# TODO: selecting every ith images.
total_idx = np.arange(0, len(syn_files), 1)  # config.SELECT_EVERY_ITH_FRAME_TEST)
syn_files = np.sort(np.array(syn_files)[total_idx])
print('Loaded {} Images'.format(len(syn_files)))

# combined
files = np.array(np.hstack([real_files, syn_files]))
print("Chosen Train: {}".format(len(files)))

f_train = open(config.TRAIN_FILE, 'w')
# ===================== train ====================
for i, file in enumerate(files):
    str_num = file.split(config.RGB_EXT)[0]
    f_train.write(str_num)
    f_train.write('\n')
f_train.close()
print('wrote {} files'.format(i+1))

################################
# VAL
################################
print('\n-------- VAL --------')

# real
real_gt_label_addr = config.DATA_DIRECTORY_VAL + 'rgb/' + '*' + config.RGB_EXT
real_files = np.sort(np.array(glob.glob(real_gt_label_addr)))
# TODO: selecting every ith images.
total_idx = np.arange(0, len(real_files), 1)  # config.SELECT_EVERY_ITH_FRAME_TEST)
# val_idx = np.random.choice(total_idx, size=int(100), replace=False)
real_files = np.sort(np.array(real_files)[total_idx])
print("Chosen Val: {}".format(len(real_files)))

# # syn
# syn_gt_label_addr = config.SYN_DATA_DIRECTORY_VAL + 'rgb/' + '*' + config.RGB_EXT
# syn_val_files = np.sort(np.array(glob.glob(syn_gt_label_addr)))
# syn_files = np.sort(np.array(syn_val_files))
# # TODO: selecting every ith images.
# total_idx = np.arange(0, len(syn_files), config.SELECT_EVERY_ITH_FRAME_TEST)
# syn_files = np.sort(np.array(syn_files)[total_idx])
# print('Loaded {} Images'.format(len(syn_files)))

# combined
files = real_files  # np.array(np.hstack([real_files, syn_files]))
print("Chosen Train: {}".format(len(files)))

f_val = open(config.VAL_FILE, 'w')
# ===================== train ====================
for i, file in enumerate(files):
    str_num = file.split(config.RGB_EXT)[0]
    f_val.write(str_num)
    f_val.write('\n')
f_val.close()
print('wrote {} files'.format(i+1))

# ################################
# # TEST
# ################################
# print('\n-------- TEST --------')
#
# # test
# real_gt_label_addr = config.DATA_DIRECTORY_TEST + 'rgb/' + '*' + config.RGB_EXT
# real_files = np.sort(np.array(glob.glob(real_gt_label_addr)))
# # selecting every ith images.
# total_idx = np.arange(0, len(real_files), config.SELECT_EVERY_ITH_FRAME_TEST)
# files = np.array(real_files)[total_idx]
# print("Chosen Test: {}".format(len(files)))
#
# f_test = open(config.TEST_FILE, 'w')
# # ===================== train ====================
# for i, file in enumerate(files):
#     str_num = file.split(config.RGB_EXT)[0]
#     f_test.write(str_num)
#     f_test.write('\n')
# print('wrote {} files'.format(i+1))

# ################################
# # TEST
# ################################
# print('\n-------- Single --------')
#
# # single
# real_gt_label_addr = config.DATA_DIRECTORY_SINGLE + 'rgb/' + '*' + config.RGB_EXT
# real_files = np.sort(np.array(glob.glob(real_gt_label_addr)))
# files = real_files
# # selecting every ith images.
# # total_idx = np.arange(0, len(real_files), config.SELECT_EVERY_ITH_FRAME_TEST)
# # files = np.array(real_files)[total_idx]
# print("Chosen Test: {}".format(len(files)))
#
# f_single = open(config.SINGLE_FILE, 'w')
# # ===================== train ====================
# for i, file in enumerate(files):
#     str_num = file.split(config.RGB_EXT)[0]
#     f_single.write(str_num)
#     f_single.write('\n')
# f_single.close()
# print('wrote {} files to {}'.format(i+1, config.SINGLE_FILE))