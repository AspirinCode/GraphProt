import numpy as np
import torch
from torch.nn import MSELoss
import torch.nn.functional as F
from torch_scatter import scatter_mean
from torch_geometric.datasets import MNISTSuperpixels
import torch_geometric.transforms as T
from torch_geometric.data import DataLoader
from torch_geometric.utils import normalized_cut
from torch_geometric.nn import ChebConv, SplineConv, graclus, max_pool, max_pool_x

from DataSet import HDF5DataSet

index = np.arange(400)
#np.random.shuffle(index)

index_train = index[:300]
index_test = index[300:]

train_dataset = HDF5DataSet(root='./',database='graph_residue.hdf5',index=index_train)
train_loader = DataLoader(train_dataset, batch_size=10, shuffle=False)
d = train_dataset.get(1)

test_dataset = HDF5DataSet(root='./',database='graph_residue.hdf5',index=index_test)
test_loader = DataLoader(test_dataset, batch_size=10, shuffle=False)



def normalized_cut_2d(edge_index, pos):
    row, col = edge_index
    edge_attr = torch.norm(pos[row] - pos[col], p=2, dim=1)
    return normalized_cut(edge_index, edge_attr, num_nodes=pos.size(0))


class Net(torch.nn.Module):
    def __init__(self):
        super(Net, self).__init__()
        self.conv1 = SplineConv(d.num_features, 32, dim=3, kernel_size=5)
        self.conv2 = SplineConv(32, 64, dim=3, kernel_size=5)
        self.fc1 = torch.nn.Linear(64, 128)
        self.fc2 = torch.nn.Linear(128, 1)

    def forward(self, data):
        data.x = F.elu(self.conv1(data.x, data.edge_index,data.edge_attr))
        weight = normalized_cut_2d(data.edge_index, data.pos)
        cluster = graclus(data.edge_index, weight)
        data = max_pool(cluster, data)

        data.x = F.elu(self.conv2(data.x, data.edge_index, data.edge_attr))
        weight = normalized_cut_2d(data.edge_index, data.pos)
        cluster = graclus(data.edge_index, weight)
        x, batch = max_pool_x(cluster, data.x, data.batch)

        x = scatter_mean(x, batch, dim=0)
        x = F.elu(self.fc1(x))
        x = F.dropout(x, training=self.training)
        return F.log_softmax(self.fc2(x), dim=1)


device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
model = Net().to(device)
optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
loss = MSELoss()

def train(epoch):
    model.train()

    if epoch == 16:
        for param_group in optimizer.param_groups:
            param_group['lr'] = 0.001

    if epoch == 26:
        for param_group in optimizer.param_groups:
            param_group['lr'] = 0.0001

    for data in train_loader:
        data = data.to(device)
        optimizer.zero_grad()
        out = model(data).reshape(-1)
        loss(out, data.y).backward()
        optimizer.step()


def test():
    model.eval()
    loss_func = MSELoss()
    loss_val = 0

    for data in test_loader:
        data = data.to(device)
        pred = model(data).reshape(-1)
        loss_val += loss_func(pred,data.y)
    return loss_val


for epoch in range(1, 31):
    train(epoch)
    test_acc = test()
    print('Epoch: {:02d}, Test: {:.4f}'.format(epoch, test_acc))
