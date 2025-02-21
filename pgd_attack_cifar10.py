from __future__ import print_function
import os
import argparse
import matplotlib.pyplot as plt
import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision
from torch.autograd import Variable
import torch.optim as optim
from torchvision import datasets, transforms
from models.wideresnet import *
from models.resnet import *


parser = argparse.ArgumentParser(description='PyTorch CIFAR PGD Attack Evaluation')
parser.add_argument('--test-batch-size', type=int, default=200, metavar='N',
                    help='input batch size for testing (default: 200)')
parser.add_argument('--no-cuda', action='store_true', default=False,
                    help='disables CUDA training')
parser.add_argument('--epsilon', default=0.031,
                    help='perturbation')
parser.add_argument('--num-steps', default=20,
                    help='perturb number of steps')
parser.add_argument('--step-size', default=0.003,
                    help='perturb step size')
parser.add_argument('--random',
                    default=True,
                    help='random initialization for PGD')
parser.add_argument('--model-path',
                    default='./checkpoints/model_cifar_wrn.pt',
                    help='model for white-box attack evaluation')
parser.add_argument('--source-model-path',
                    default='./checkpoints/model_cifar_wrn.pt',
                    help='source model for black-box attack evaluation')
parser.add_argument('--target-model-path',
                    default='./checkpoints/model_cifar_wrn.pt',
                    help='target model for black-box attack evaluation')
parser.add_argument('--white-box-attack', default=True,
                    help='whether perform white-box attack')

args = parser.parse_args()

# settings
use_cuda = not args.no_cuda and torch.cuda.is_available()
device = torch.device("cuda" if use_cuda else "cpu")
kwargs = {'num_workers': 1, 'pin_memory': True} if use_cuda else {}

# set up data loader
transform_test = transforms.Compose([transforms.ToTensor(),])
testset = torchvision.datasets.CIFAR10(root='../data', train=False, download=True, transform=transform_test)
test_loader = torch.utils.data.DataLoader(testset, batch_size=args.test_batch_size, shuffle=False, **kwargs)
def plot_dataset_digits(dataset, name, k):
    fig = plt.figure(figsize=(13, 8))
    columns = 3
    rows = 2
    # ax enables access to manipulate each of subplots
    ax = []

    for i in range(columns * rows):
        img = dataset[i]
        # create subplot and append to ax
        ax.append(fig.add_subplot(rows, columns, i + 1))
        ax[-1].set_title("CIFAR")  # set title
        plt.imshow(img)

    # plt.show()  # finally, render the plot
    plt.savefig('./results/img'+name+'{}'.format(k)+'.png')

def _pgd_whitebox(model,
                  X,
                  y,
                  k,
                  epsilon=args.epsilon,
                  num_steps=args.num_steps,
                  step_size=args.step_size):
    out = model(X)
    err = (out.data.max(1)[1] != y.data).float().sum()
    #loss_natural = nn.CrossEntropyLoss()(model(X), y)
    # print('natural loss: ', loss_natural)
    X_pgd = Variable(X.data, requires_grad=True)
    if args.random:
        random_noise = torch.FloatTensor(*X_pgd.shape).uniform_(-epsilon, epsilon).to(device)
        X_pgd = Variable(X_pgd.data + random_noise, requires_grad=True)

    for _ in range(num_steps):
        opt = optim.SGD([X_pgd], lr=1e-3)
        opt.zero_grad()

        with torch.enable_grad():
            loss = nn.CrossEntropyLoss()(model(X_pgd), y)
            # print('attack loss: ', loss)
        loss.backward()
        eta = step_size * X_pgd.grad.data.sign()
        X_pgd = Variable(X_pgd.data + eta, requires_grad=True)
        eta = torch.clamp(X_pgd.data - X.data, -epsilon, epsilon)
        X_pgd = Variable(X.data + eta, requires_grad=True)
        X_pgd = Variable(torch.clamp(X_pgd, 0, 1.0), requires_grad=True)
    err_pgd = (model(X_pgd).data.max(1)[1] != y.data).float().sum()
    perturbation = X_pgd - X
    #########################################
    X_p = Variable(X_pgd.data, requires_grad=True)
    if args.random:
        #先一个noise 均匀分布
        random_noise_2 = torch.FloatTensor(*X_p.shape).uniform_(-epsilon, epsilon).to(device)
        #生成最初的样本
        X_p = Variable(X_p.data + random_noise_2, requires_grad=True)

    for _ in range(num_steps):
        opt = optim.SGD([X_p], lr=1e-3)
        opt.zero_grad()

        with torch.enable_grad():
            loss = nn.CrossEntropyLoss()(model(X_p), y)
            #print('recover loss: ', loss)
        loss.backward()
        eta = - step_size * X_p.grad.data.sign()
        X_p = Variable(X_p.data + eta, requires_grad=True)#前面有random的noise
        eta = torch.clamp(X_p.data - X_pgd.data, -epsilon, epsilon)
        X_p = Variable(X_pgd.data + eta, requires_grad=True)
        X_p = Variable(torch.clamp(X_p, 0, 1.0), requires_grad=True)
        #向符号方向走
    per_red= X_p-X_pgd
    delta_p = per_red-perturbation
    delta_per = torch.norm(delta_p, dim=2)
    err_red = (model(X_p).data.max(1)[1] != y.data).float().sum()
    plot_dataset_digits(X.cpu().detach().numpy(), '_natural_',k)
    plot_dataset_digits(X_pgd.cpu().detach().numpy(), '_adv_',k)
    plot_dataset_digits(X_p.cpu().detach().numpy(), '_red_',k)
    #print('err pgd (white-box): ', err_pgd)

    return delta_per, err, err_red, err_pgd




def eval_adv_test_whitebox(model, device, test_loader):
    """
    evaluate model by white-box attack
    """
    model.eval()
    per_err_total = 0

    natural_err_total = 0
    robust_err_total = 0
    natural_err_total = 0

    for data, target in test_loader:
        data, target = data.to(device), target.to(device)
        # pgd attack
        X, y = Variable(data, requires_grad=True), Variable(target)
        delta_per,err_natural, err_recovered, err_attack = _pgd_whitebox(model, X, y,k)
        per_err_total += delta_per
        recovered_err_total += err_recovered
        attack_err_total += err_attack
        natural_err_total += err_natural
        k+=1
    print('natural_err_total: ', natural_err_total)
    print('natural_err_total: ', natural_err_total)
    print('robust_err_total: ', robust_err_total)





def main():

    if args.white_box_attack:
        # white-box attack
        print('pgd white-box attack')
        model = WideResNet().to(device)
        model.load_state_dict(torch.load(args.model_path))

        eval_adv_test_whitebox(model, device, test_loader)
    else:
        # black-box attack
        print('pgd black-box attack')
        model_target = WideResNet().to(device)
        model_target.load_state_dict(torch.load(args.target_model_path))
        model_source = WideResNet().to(device)
        model_source.load_state_dict(torch.load(args.source_model_path))

        eval_adv_test_blackbox(model_target, model_source, device, test_loader)


if __name__ == '__main__':
    main()
