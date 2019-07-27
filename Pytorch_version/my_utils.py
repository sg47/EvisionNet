from __future__ import division
import shutil
import numpy as np
import torch
from path import Path
import datetime
from collections import OrderedDict
from matplotlib import cm
from matplotlib.colors import ListedColormap, LinearSegmentedColormap


def save_path_formatter(args, parser):
    def is_default(key, value):
        return value == parser.get_default(key)

    args_dict = vars(args)
    data_folder_name = str(Path(args_dict['data']).normpath().name)
    folder_string = [data_folder_name]
    if not is_default('epochs', args_dict['epochs']):
        folder_string.append('{}epochs'.format(args_dict['epochs']))
    keys_with_prefix = OrderedDict()
    keys_with_prefix['epoch_size'] = 'epoch_size'
    keys_with_prefix['sequence_length'] = 'seq'
    keys_with_prefix['rotation_mode'] = 'rot_'
    keys_with_prefix['padding_mode'] = 'padding_'
    keys_with_prefix['batch_size'] = 'b'
    keys_with_prefix['lr'] = 'lr'
    keys_with_prefix['photo_loss_weight'] = 'p'
    keys_with_prefix['mask_loss_weight'] = 'm'
    keys_with_prefix['smooth_loss_weight'] = 's'

    for key, prefix in keys_with_prefix.items():
        value = args_dict[key]
        if not is_default(key, value):
            folder_string.append('{}{}'.format(prefix, value))
    if args.intri_pred:
        folder_string.append('calib')
    save_path = Path(','.join(folder_string))
    timestamp = datetime.datetime.now().strftime("%m-%d-%H%M")
    return save_path / timestamp


def high_res_colormap(low_res_cmap, resolution=1000, max_value=1):
    # Construct the list colormap, with interpolated values for higer resolution
    # For a linear segmented colormap, you can just specify the number of point in
    # cm.get_cmap(name, lutsize) with the parameter lutsize
    x = np.linspace(0, 1, low_res_cmap.N)
    low_res = low_res_cmap(x)
    new_x = np.linspace(0, max_value, resolution)
    high_res = np.stack([np.interp(new_x, x, low_res[:, i]) for i in range(low_res.shape[1])], axis=1)
    return ListedColormap(high_res)


def opencv_rainbow(resolution=1000):
    # Construct the opencv equivalent of Rainbow
    opencv_rainbow_data = (
        (0.000, (1.00, 0.00, 0.00)),
        (0.400, (1.00, 1.00, 0.00)),
        (0.600, (0.00, 1.00, 0.00)),
        (0.800, (0.00, 0.00, 1.00)),
        (1.000, (0.60, 0.00, 1.00))
    )

    return LinearSegmentedColormap.from_list('opencv_rainbow', opencv_rainbow_data, resolution)


COLORMAPS = {'rainbow': opencv_rainbow(),
             'magma': high_res_colormap(cm.get_cmap('magma')),
             'bone': cm.get_cmap('bone', 10000)}


def log_output_tensorboard(writer, prefix, index, suffix, n_iter, depth, disp, warped, diff, mask):
    disp_to_show = tensor2array(disp[0], max_value=None, colormap='magma')
    depth_to_show = tensor2array(depth[0], max_value=None)
    writer.add_image('{} Dispnet Output Normalized {}/{}'.format(prefix, suffix, index), disp_to_show, n_iter)
    writer.add_image('{} Depth Output Normalized {}/{}'.format(prefix, suffix, index), depth_to_show, n_iter)
    # log warped images along with explainability mask
    for j, (warped_j, diff_j) in enumerate(zip(warped[0], diff[0])):
        whole_suffix = '{} {}/{}'.format(suffix, j, index)
        warped_to_show = tensor2array(warped_j)
        diff_to_show = tensor2array(0.5 * diff_j)
        writer.add_image('{} Warped Outputs {}'.format(prefix, whole_suffix), warped_to_show, n_iter)
        writer.add_image('{} Diff Outputs {}'.format(prefix, whole_suffix), diff_to_show, n_iter)
        if mask is not None:
            mask_to_show = tensor2array(mask[0, j], max_value=1, colormap='bone')
            writer.add_image('{} Exp mask Outputs {}'.format(prefix, whole_suffix), mask_to_show, n_iter)


def tensor2array(tensor, max_value=None, colormap='rainbow'):
    tensor = tensor.detach().cpu()
    if max_value is None:
        max_value = tensor.max().item()
    if tensor.ndimension() == 2 or tensor.size(0) == 1:
        norm_array = tensor.squeeze().numpy() / max_value
        array = COLORMAPS[colormap](norm_array).astype(np.float32)
        array = array.transpose(2, 0, 1)

    elif tensor.ndimension() == 3:
        assert (tensor.size(0) == 3)
        array = 0.5 + tensor.numpy() * 0.5
    return array


def save_checkpoint(save_path, dispnet_state, exp_pose_state, is_best, filename='checkpoint.pth.tar'):
    file_prefixes = ['dispnet', 'exp_pose']
    states = [dispnet_state, exp_pose_state]
    for (prefix, state) in zip(file_prefixes, states):
        torch.save(state, save_path / '{}_{}'.format(prefix, filename))

    if is_best:
        for prefix in file_prefixes:
            shutil.copyfile(save_path / '{}_{}'.format(prefix, filename),
                            save_path / '{}_model_best.pth.tar'.format(prefix))


def intrinsics_pred_decode(input):
    """
    https://www.jianshu.com/p/f1bd4ff84926
    :param input:
    :return:
    """
    input = torch.squeeze(input)
    ja = []
    for i in range(input.shape[0]):
        ja.append([0.0, 0.0, 0.0, 0.0, 1.0])
    jan = np.array(ja)
    jant = torch.from_numpy(jan)
    jant = jant.to(input.device).float()
    iante = torch.cat((input, jant), 1)
    index = [0, 4, 2, 5, 1, 3, 6, 7, 8]
    for i in range(input.shape[0]):
        iante[i] =iante[i][index]

    ianter = iante.reshape(input.shape[0], 3, 3)


    #print(ianter.shape)
    return ianter

    # i = torch.LongTensor([[0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3],
    #                       [0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1],
    #                       [0, 1, 2, 2, 0, 1, 2, 2, 0, 1, 2, 2, 0, 1, 2, 2]]).to(input.device)
    #
    # intrinsics = torch.sparse.FloatTensor(i, input.reshape(16), torch.Size([4, 3, 3])).to_dense()
    # intrinsics[0][2][2] = 1
    # intrinsics[1][2][2] = 1
    # intrinsics[2][2][2] = 1
    # intrinsics[3][2][2] = 1


if __name__ == '__main__':
    ia = [[11.1, 12.1, 13.1, 14.1],
          [11.2, 12.2, 13.2, 14.2],
          [11.3, 12.3, 13.3, 14.3],
          [11.4, 12.4, 13.4, 14.4],
          [11.5, 12.5, 13.5, 14.5]]
    ian = np.array(ia)
    iant = torch.from_numpy(ian)
    iant = iant.to(torch.device("cuda"))

    print(iant.shape)
    # torch.unsqueeze(iant, 0)
    ##==============================================
    ja = []
    for i in range(iant.shape[0]):
        ja.append([0.0, 0.0, 0.0, 0.0, 1.0])
    jan = np.array(ja)
    jant = torch.from_numpy(jan)
    jant = jant.to(iant.device)

    iante = torch.cat((iant, jant), 1)
    index = [0, 4, 2, 5, 1, 3, 6, 7, 8]
    for i in range(iant.shape[0]):
        iante[i] =iante[i][index]

    ianter = iante.reshape(5, 3, 3)


    print(ianter.shape)
    # iant.expand(2,2)
