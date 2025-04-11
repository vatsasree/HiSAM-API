import torch
import torch.nn as nn
import math


class SelfAttention(nn.Module):
    def __init__(self, hidden_dim=512, n_heads=8):
        super().__init__()
        assert hidden_dim % n_heads == 0
        self.hidden_dim = hidden_dim
        self.n_heads = n_heads
        self.v_dim = self.hidden_dim // self.n_heads
        self.Q = nn.Linear(self.hidden_dim, self.hidden_dim)
        self.K = nn.Linear(self.hidden_dim, self.hidden_dim)
        self.V = nn.Linear(self.hidden_dim, self.hidden_dim)
        self.softmax = nn.Softmax(dim=-1)
        self.mlp = nn.Linear(self.hidden_dim, self.hidden_dim)

    def attention(self, query, key, value):
        scores = self.softmax((query @ key.transpose(-2, -1)) / math.sqrt(self.v_dim))
        return scores @ value

    def forward(self, x):
        query = self.Q(x).reshape(x.shape[0], -1, self.n_heads, self.v_dim).transpose(1, 2)
        key = self.K(x).reshape(x.shape[0], -1, self.n_heads, self.v_dim).transpose(1, 2)
        value = self.V(x).reshape(x.shape[0], -1, self.n_heads, self.v_dim).transpose(1, 2)
        x = self.attention(query, key, value)
        x = x.transpose(1, 2).reshape(x.shape[0], -1, self.hidden_dim)
        return self.mlp(x)
    


class RCDCrossAttention(nn.Module):
    def __init__(self, hidden_dim=128, n_heads=8, dropout=0.1):
        super().__init__()
        assert hidden_dim % n_heads == 0
        self.hidden_dim = hidden_dim
        self.n_heads = n_heads
        self.v_dim = self.hidden_dim // self.n_heads
        self.Q_x = nn.Linear(self.hidden_dim, self.hidden_dim)
        self.Q_y = nn.Linear(self.hidden_dim, self.hidden_dim)
        self.K_x = nn.Linear(self.hidden_dim, self.hidden_dim)
        self.K_y = nn.Linear(self.hidden_dim, self.hidden_dim)
        self.V = nn.Linear(self.hidden_dim, self.hidden_dim)
        self.mlp = nn.Linear(self.hidden_dim, self.hidden_dim)
        self.softmax = nn.Softmax(dim=-1)
        self.dropout = nn.Dropout(dropout)

    
    def forward(self, tgt, memory, query_pos_x, query_pos_y, key_pos_x, key_pos_y):
        # memory2 is used for value
        # memory is used for key

        # shape of memory is N, H, W, C
        self.n, self.h, self.w, self.c = memory.shape
        self.n_q = tgt.shape[1]

        # collapsing the memory along the 1st dimension (zero indexed)
        query_x = (self.Q_x(tgt + query_pos_x)).reshape(self.n, -1, self.n_heads, self.v_dim).transpose(1, 2)
        memory_x = memory + key_pos_x
        memory_x = torch.mean(memory_x, dim=1)
        # print(f"memory.shape: {memory.shape}")
        # print(f"memory_x.shape: {memory_x.shape}")
        key_x = self.K_x(memory_x).reshape(self.n, -1, self.n_heads, self.v_dim).transpose(1, 2)
        value = self.V(memory).reshape(self.n, self.h, self.w, self.n_heads, self.v_dim).permute(0, 3, 1, 2, 4)
        # print(f"query_x.shape: {query_x.shape}")
        # print(f"key_x.shape: {key_x.shape}")
        # print(f"value.shape: {value.shape}")
        scores = self.softmax((query_x @ key_x.transpose(-2, -1)) / math.sqrt(self.v_dim))
        # print(f"scores.shape: {scores.shape}")
        z = (scores @ value.transpose(2, 3).flatten(start_dim=-2, end_dim=-1)).reshape(self.n, self.n_heads, self.n_q, self.h, self.c // self.n_heads)

        # print()
        # print()
        # print()

        # collapsing the memory along the 2nd dimension
        memory_y = memory + key_pos_y
        memory_y = torch.mean(memory_y, dim=2)
        query_y = (self.Q_y(tgt + query_pos_y)).reshape(tgt.shape[0], -1, self.n_heads, self.v_dim).transpose(1, 2)
        key_y = self.K_y(memory_y).reshape(memory_y.shape[0], -1, self.n_heads, self.v_dim).transpose(1, 2)
        # print(f"query_y.shape: {query_y.shape}")
        # print(f"key_y.shape: {key_y.shape}")
        # print(f"z.shape: {z.shape}")
        scores = self.softmax((query_y @ key_y.transpose(-2, -1)) / math.sqrt(self.v_dim))
        # print(f"scores.shape: {scores.shape}")
        out = torch.sum(scores.unsqueeze(-1) * z, dim=-2)
        # print(f"out.shape: {out.shape}")
        out = out.transpose(1, 2).flatten(start_dim=-2)
        return self.dropout(self.mlp(out))
        


