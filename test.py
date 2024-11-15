import os
import logging
import random
import lpips
from torch.utils.data import DataLoader
import torch
from utils.utils_dataset import define_Dataset
import utils.utils_option as option
import utils.utils_image as util
import utils.utils_logger as utils_logger
from utils.utils_training import seed_everywhere
from models.usrnet_train import define_Model

import wandb
from datetime import datetime

def main():
    wandbconfig = False
    opt = option.parse('./options/train_usrnet.json')
    util.mkdirs((path for key, path in opt['path'].items() if 'pretrained' not in key))
    optim_name = f'bs{opt["datasets"]["train"]["dataloader_batch_size"]}-loss_{opt["train"]["G_lossfn_type"]}-lr_{opt["train"]["G_optimizer_lr"]}-G_scheduler_milestones_{opt["train"]["G_scheduler_milestones"]}'
    run_id = datetime.now().strftime("%Y%m%d-%H%M")
    expr_name = f'USRNet-{run_id}-{optim_name}'
    model_path = 'model_zoo/usrnet.pth'
    border = opt['scale']
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    # ----------------------------------------
    # save opt to  a '../option.json' file
    # ----------------------------------------
    option.save(opt)

    # ----------------------------------------
    # return None for missing key
    # ----------------------------------------
    opt = option.dict_to_nonedict(opt)

    # ----------------------------------------
    # configure logger
    # ----------------------------------------
    logger_name = 'train'
    utils_logger.logger_info(logger_name, os.path.join(opt['path']['log'], logger_name+'.log'))
    logger = logging.getLogger(logger_name)
    logger.info(option.dict2str(opt))
    if wandbconfig:
        wandb.init(
            project="USRNet",
            name=expr_name,
            config=opt,
        )

    # ----------------------------------------
    # seed
    # ----------------------------------------
    seed = opt['train']['manual_seed']
    if seed is None:
        seed = random.randint(1, 10000)
    logger.info('Random seed: {}'.format(seed))
    seed_everywhere(seed)

    '''
    # ----------------------------------------
    # Step--2 (creat dataloader)
    # ----------------------------------------
    '''

    # ----------------------------------------
    # 1) create_dataset
    # 2) creat_dataloader for train and test
    # ----------------------------------------
    for phase, dataset_opt in opt['datasets'].items():
        if phase == 'test':
            test_set = define_Dataset(dataset_opt)
            test_loader = DataLoader(test_set, batch_size=1,
                                     shuffle=False, num_workers=1,
                                     drop_last=False, pin_memory=True)

        
    '''
    # ----------------------------------------
    # Step--3 (initialize model)
    # ----------------------------------------
    '''
    model = define_Model(opt)
    model.init_train()
    model.netG.eval()
    for key, v in model.netG.named_parameters():
        v.requires_grad = False
    print('success')

    lpips_model = lpips.LPIPS(net='vgg').to(model.device)
    idx = 0
    avg_psnr = 0
    avg_lpips = 0

    for test_data in test_loader:
        idx += 1
        if idx>1:
            break
        image_name_ext = os.path.basename(test_data['L_path'][0])
        img_name, ext = os.path.splitext(image_name_ext)
        img_dir = os.path.join(opt['path']['images'], img_name)
        util.mkdir(img_dir)
        model.feed_data(test_data)
        model.test()
        visuals = model.current_visuals()
        E_img = util.tensor2uint(visuals['E'])
        H_img = util.tensor2uint(visuals['H'])
        # -----------------------
        # calculate PSNR
        # -----------------------
        current_psnr = util.calculate_psnr(E_img, H_img, border=border)
        # -----------------------
        # calculate LPIPS
        # -----------------------
        lpips_value = lpips_model.forward(visuals['E'].to(model.device), visuals['H'].to(model.device)).item()
        print(lpips_value)
        logger.info('{:->4d}--> {:>10s} | {:<4.2f}dB | LPIPS: {:.3f}'.format(idx, image_name_ext, current_psnr, lpips_value))
        # # # wandb.log({"iter": current_step, "PSNR": current_psnr, "LPIPS": lpips_value})
        avg_psnr += current_psnr
        avg_lpips += lpips_value
    avg_psnr = avg_psnr / idx
    avg_lpips = avg_lpips / idx
    # testing log
    logger.info('<Average PSNR : {:<.2f}dB, Average LPIPS: {:.3f}\n'.format(avg_psnr, avg_lpips))

if __name__ == '__main__':
    main()