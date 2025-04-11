import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as opt
from torch.utils.data import DataLoader, TensorDataset, random_split, Subset
from torchvision.transforms import ToTensor
import pickle
import os
import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment
import matplotlib.pyplot as plt
import sys
import shutil
from lightning.pytorch import LightningModule
import lightning as L
from lightning.pytorch.loggers import WandbLogger
from lightning.pytorch.callbacks import ModelCheckpoint
torch.manual_seed(1709)
from src.ml_models.LineTR.src.dataset import ManuscriptDataset, ManuscriptDatasetRotation
from copy import deepcopy
from src.ml_models.LineTR.src.transformer import TransformerDecoderLayer
from src.ml_models.LineTR.src.vit_pytorch import ViT
import math
from src.ml_models.LineTR.src.config import *


class TLDr_Trainer(LightningModule):
	def __init__(self):
		super().__init__()
		self.image_dim = 256
		self.patch_dim = 16
		self.hidden_dim = 256
		self.n_heads = 8
		self.num_encoder_layers = 6
		self.num_decoder_layers = 6
		self.encoder = ViT(
            image_size = self.image_dim,
            patch_size = self.patch_dim,
            dim = self.hidden_dim,
            depth = self.num_encoder_layers,
            heads = self.n_heads,
            mlp_dim = 2048,
            dropout = 0.1,
            emb_dropout = 0.1
        )
		# self.enc_to_dec = nn.Linear(768, self.hidden_dim)
		self.decoder_layers = nn.ModuleList([
			TransformerDecoderLayer(self.hidden_dim, self.n_heads)
			for _ in range(self.num_decoder_layers)
		])
		self.linear_prob = nn.Linear(self.hidden_dim, 2)
		self.softmax = nn.Softmax(dim=-1)
		self.linear_mean = nn.Linear(self.hidden_dim, 2)
		self.linear_mean.bias = nn.Parameter(torch.tensor([0.5, 0.0]))
		self.linear_slope = nn.Linear(self.hidden_dim, 1)
		self.linear_slope.bias = nn.Parameter(torch.tensor(0.0))
		self.query_content = nn.Parameter(torch.zeros(NUM_QUERIES, self.hidden_dim))
		self.adapt_pos1d = nn.Sequential(
			nn.Linear(self.hidden_dim, self.hidden_dim),
			nn.ReLU(),
			nn.Linear(self.hidden_dim, self.hidden_dim),
		)


		# hyperparameters
		self.initialize = False
		if VISUALIZE:
			self.input_vis = 0
			self.vis_step = 0
			self.colors = None
			with open(f"colors.pkl", "rb") as f:
				self.colors = pickle.load(f)
				

	def pos2posemb1d(self, pos, num_pos_feats=256, temperature=10000):
		scale = 2 * math.pi
		pos = pos * scale
		dim_t = torch.arange(num_pos_feats, dtype=torch.float32, device=pos.device)
		dim_t = temperature ** (2 * (dim_t // 2) / num_pos_feats)
		pos_x = pos[..., None] / dim_t
		posemb = torch.stack((pos_x[..., 0::2].sin(), pos_x[..., 1::2].cos()), dim=-1).flatten(-2)
		return posemb
				

	def forward(self, x):
		# encoder pass
		# encoder has position embeddings built in
		encoder_output = self.encoder(x)

		# assuming only square image input
		memory = encoder_output.reshape((x.size(0), 16, 16, 256))

		# converting to decoder channel size
		# memory = self.enc_to_dec(memory)

		# content queries
		tgt = self.query_content.unsqueeze(0).repeat(x.size(0), 1, 1)

		# positional queries
		ref_pts = torch.arange(0, NUM_QUERIES)
		query_pos_y = query_pos_x = self.adapt_pos1d((self.pos2posemb1d(ref_pts, self.hidden_dim)).to(self.local_rank))
		query_pos = self.adapt_pos1d((self.pos2posemb1d(ref_pts, self.hidden_dim)).to(self.local_rank))

		# positional encodings for the keys
		pos_row = torch.arange(memory.shape[2])
		pos_col = torch.arange(memory.shape[1])
		posemb_row = self.adapt_pos1d((self.pos2posemb1d(pos_row, self.hidden_dim)).to(self.local_rank))
		posemb_col = self.adapt_pos1d((self.pos2posemb1d(pos_col, self.hidden_dim)).to(self.local_rank))
		posemb_row = posemb_row.unsqueeze(0).repeat(memory.shape[1], 1, 1)
		posemb_col = posemb_col.unsqueeze(1).repeat(1, memory.shape[2], 1)
		key_pos_x = posemb_row
		key_pos_y = posemb_col

		# decoder pass
		x = tgt
		for i in range(self.num_decoder_layers):
			x = self.decoder_layers[i](x, memory, query_pos, query_pos_x, query_pos_y, key_pos_x, key_pos_y)

		logits = self.linear_prob(x)
		prob = self.softmax(logits)
		mean = self.linear_mean(x)
		slope = self.linear_slope(x)
		mean = torch.clamp(mean, 0.0, 1.0)
		slope = torch.clamp(slope, -1.0, 1.0)

		return encoder_output, torch.cat([mean, slope, prob, logits], dim=-1)


	def lines_miss_loss(self, outputs, y):
		lines_mask = ((y[:, 0] != 0) | (y[:, 1] != 0) | (y[:, 2] != 0))
		num_lines = int(lines_mask.sum())
		num_lines_pred = int((outputs[:, 3] > 0.5).sum())
		return abs(num_lines - num_lines_pred)


	def geometric_loss(self, outputs, y):
		outputs = torch.clone(outputs)
		y = torch.clone(y)
		mean_x = y[..., 0]
		mean_y = y[..., 1]
		slope = y[..., 2]
		mean_x_out = outputs[..., 0]
		mean_y_out = outputs[..., 1]
		slope_out = outputs[..., 2]
		def leq(x):
			return (x - mean_x) * slope + mean_y
		def leq_out(x):
			return (x - mean_x_out) * slope_out + mean_y_out
		yl = leq(0)
		yr = leq(1)
		outl = leq_out(0)
		outr = leq_out(1)
		return torch.abs(yl - outl)**2 + torch.abs(yr - outr)**2


	def line_geometric_loss(self, outputs, y):
		outputs = torch.clone(outputs)
		y = torch.clone(y)
		mean_x = y[0]
		mean_y = y[1]
		slope = y[2]
		mean_x_out = outputs[0]
		mean_y_out = outputs[1]
		slope_out = outputs[2]
		def leq(x):
			return (x - mean_x) * slope + mean_y
		def leq_out(x):
			return (x - mean_x_out) * slope_out + mean_y_out
		yl = leq(0)
		yr = leq(1)
		outl = leq_out(0)
		outr = leq_out(1)
		return torch.abs(yl - outl)**2 + torch.abs(yr - outr)**2


	def calc_loss_geometric(self, outputs, y, median_gaps):
		outputs = torch.clone(outputs)
		y = torch.clone(y)
		median_gaps = torch.clone(median_gaps)
		out_lines = outputs[:, :, :3]
		out_lines = out_lines.unsqueeze(1).repeat(1, NUM_QUERIES, 1, 1)
		y = y.unsqueeze(2).repeat(1, 1, NUM_QUERIES, 1)
		loss_geom = self.geometric_loss(out_lines, y)
		median_gaps = median_gaps.unsqueeze(-1).unsqueeze(-1)
		assert loss_geom[0, 1, 2] == self.line_geometric_loss(out_lines[0, 0, 2], y[0, 1, 0])
		loss_geom = loss_geom / median_gaps
		line_probs = -outputs[:, :, 3].unsqueeze(1).repeat(1, NUM_QUERIES, 1)
		cost_mat = MATCH_GEOM_COEFF * loss_geom + MATCH_CLS_COEFF * line_probs
		empty_cls_mask = ((y[:, :, :, 0] == 0) & (y[:, :, :, 1] == 0) & (y[:, :, :, 2] == 0))
		cost_mat[empty_cls_mask] = INF_MATCH_COST
		return loss_geom, line_probs, cost_mat


	def training_step(self, batch, batch_idx):
		# inference
		x, y = batch
		
		if VISUALIZE and self.input_vis < 5:
			img = (x[0] + 0.5) * 255.0
			img = img.permute(1, 2, 0)
			img = img.cpu().numpy().astype(np.int32)
			img = np.ascontiguousarray(img)
			lines = y[0]
			for line in lines:
				if line[0] == 0 and line[1] == 0 and line[2] == 0:
					continue
				mean_x = (line[0] * PATCH_SIZE).item()
				mean_y = (line[1] * PATCH_SIZE).item()
				slope = line[2].item()
				def line_equation(x_pts):
					return (x_pts - mean_x) * slope + mean_y
				x_pts_ = np.linspace(0, 255, 5).astype(np.int32)
				y_pts_ = line_equation(x_pts_).astype(np.int32)
				pts = np.stack((x_pts_, y_pts_), axis=-1)
				cv2.polylines(img, [pts], False, (255, 0, 0), 2)
			cv2.imwrite(f"{self.input_vis}.jpg", img)
			self.input_vis += 1
			

		n = x.size(0)
		encoder_output, outputs = self(x)


		# calculating the median gaps
		median_gaps = torch.empty((n)).to(self.local_rank)
		for i in range(y.size(0)):
			y_i = y[i]
			gnd_mean_y_sorted = torch.sort(y_i[(y_i[:, 0] != 0) | (y_i[:, 1] != 0) | (y_i[:, 2] != 0)][:, 1]).values
			if len(gnd_mean_y_sorted) <= 1:
				median_gap = 0.33
			else:
				median_gap = torch.median(torch.abs(torch.diff(gnd_mean_y_sorted)))
			median_gap = max(median_gap, 0.01)
			median_gaps[i] = median_gap


		# calculate pairwise cost
		loss_geom_mat, _, loss_mat = self.calc_loss_geometric(outputs, y, median_gaps)


		# starting batch_wise
		batch_loss = 0.0
		batch_loss_geom = 0.0
		batch_loss_pos_log = 0.0
		batch_loss_neg_log = 0.0
		batch_loss_focal_pos = 0.0
		batch_loss_focal_neg = 0.0
		
		if self.initialize:
			y[:, :, 0] = 0.5
			y[:, :, 1] = torch.linspace(0.0, 1.0, NUM_QUERIES)
			y[:, :, 2] = 0.0

			# outputs : (B, Q, 7)
			# outputs[:, :, 0] is mean_x
			# outputs[:, :, 1] : (B, Q)
			# outputs[:, :, 3] is prob+
			
			loss1 = torch.sum((outputs[:, :, :3] - y) ** 2)
			loss2 = torch.sum((outputs[:, :, 3] - 0.1) ** 2)
			loss3 = torch.sum((outputs[:, :, 4] - 0.9) ** 2)
			loss = loss1 + loss2 + loss3
			return loss

		for i in range(n):
			# calculating the median gap
			y_i = y[i]
			gnd_mean_y_sorted = torch.sort(y_i[(y_i[:, 0] != 0) | (y_i[:, 1] != 0) | (y_i[:, 2] != 0)][:, 1]).values
			if len(gnd_mean_y_sorted) <= 1:
				median_gap = 0.33
			else:
				median_gap = torch.median(torch.abs(torch.diff(gnd_mean_y_sorted)))
			median_gap = max(median_gap, 0.01)

			assert median_gap == median_gaps[i]
			
			# assignment
			all_gnd_ids, all_out_ids = linear_sum_assignment(loss_mat[i].detach().cpu().numpy())
			lines_mask = ((y[i, :, 0] != 0) | (y[i, :, 1] != 0) | (y[i, :, 2] != 0))
			num_lines = int(lines_mask.sum())
			# print(f"there are {num_lines} lines in the training batch!")
			if not self.initialize:
				assert num_lines < MAX_LINES
			gnd_ids = all_gnd_ids[:num_lines]
			out_ids = all_out_ids[:num_lines]
			
			# calculating losses based on assignment
			loss_geom = torch.sum(loss_geom_mat[i, gnd_ids, out_ids]) / median_gap
			loss_pos_log = torch.sum(-torch.log(outputs[i, out_ids, 3]))
			loss_neg_log = torch.sum(-torch.log(outputs[i, all_out_ids[num_lines:], 4]))

			# loss_focal_pos_unstable = -torch.sum(((torch.exp(outputs[i, out_ids, 6]) / (torch.exp(outputs[i, out_ids, 5]) + torch.exp(outputs[i, out_ids, 6])))**2) * (outputs[i, out_ids, 5] - torch.log(torch.exp(outputs[i, out_ids, 5]) + torch.exp(outputs[i, out_ids, 6]))))

			loss_focal_pos = -torch.sum((outputs[i, out_ids, 4]**2) * (outputs[i, out_ids, 5] - torch.log(torch.exp(outputs[i, out_ids, 5]) + torch.exp(outputs[i, out_ids, 6]))))

			# assert torch.allclose(torch.sum((outputs[i, out_ids, 5] - torch.log(torch.exp(outputs[i, out_ids, 5]) + torch.exp(outputs[i, out_ids, 6])))), -loss_pos_log)

			# loss_focal_neg_unstable = -torch.sum(((torch.exp(outputs[i, all_out_ids[num_lines:], 5]) / (torch.exp(outputs[i, all_out_ids[num_lines:], 5]) + torch.exp(outputs[i, all_out_ids[num_lines:], 6])))**2) * (outputs[i, all_out_ids[num_lines:], 6] - torch.log(torch.exp(outputs[i, all_out_ids[num_lines:], 5]) + torch.exp(outputs[i, all_out_ids[num_lines:], 6]))))

			loss_focal_neg = -torch.sum((outputs[i, all_out_ids[num_lines:], 3]**2) * (outputs[i, all_out_ids[num_lines:], 6] - torch.log(torch.exp(outputs[i, all_out_ids[num_lines:], 5]) + torch.exp(outputs[i, all_out_ids[num_lines:], 6]))))

			# assert torch.allclose(loss_focal_neg, loss_focal_neg_unstable)
			# assert torch.allclose(loss_focal_pos, loss_focal_pos_unstable)

			# assert torch.allclose(torch.sum((outputs[i, all_out_ids[num_lines:], 6] - torch.log(torch.exp(outputs[i, all_out_ids[num_lines:], 5]) + torch.exp(outputs[i, all_out_ids[num_lines:], 6])))), -loss_neg_log), f"{torch.sum((outputs[i, all_out_ids[num_lines:], 6] - torch.log(torch.exp(outputs[i, all_out_ids[num_lines:], 5]) + torch.exp(outputs[i, all_out_ids[num_lines:], 6]))))}, {-loss_neg_log}"


			loss = loss_focal_pos * POS_FOCAL_COEFF + loss_focal_neg * NEG_FOCAL_COEFF + loss_geom * GEOM_COEFF
			batch_loss += loss
			batch_loss_geom += loss_geom.item()
			batch_loss_pos_log += loss_pos_log.item()
			batch_loss_neg_log += loss_neg_log.item()
			batch_loss_focal_pos += loss_focal_pos.item()
			batch_loss_focal_neg += loss_focal_neg.item()

		# averaging the losses over the batch
		batch_loss /= n
		batch_loss_geom /= n
		batch_loss_pos_log /= n
		batch_loss_neg_log /= n
		batch_loss_focal_pos /= n
		batch_loss_focal_neg /= n

		# logging the averaged losses, but only at epoch end
		self.log("train_loss", batch_loss.item(), on_epoch=True, on_step=False, sync_dist=True, prog_bar=True)
		self.log("train_loss_geom", batch_loss_geom, on_epoch=True, on_step=False, sync_dist=True, prog_bar=True)
		self.log("train_loss_pos_log", batch_loss_pos_log, on_epoch=True, on_step=False, sync_dist=True, prog_bar=True)
		self.log("train_loss_neg_log", batch_loss_neg_log, on_epoch=True, on_step=False, sync_dist=True, prog_bar=True)
		self.log("train_loss_focal_pos", batch_loss_focal_pos, on_epoch=True, on_step=False, sync_dist=True, prog_bar=True)
		self.log("train_loss_focal_neg", batch_loss_focal_neg, on_epoch=True, on_step=False, sync_dist=True, prog_bar=True)

		return batch_loss


	def validation_step(self, batch, batch_idx):
		# inference
		x, y = batch
		n = x.size(0)
		encoder_output, outputs = self(x)


		if self.initialize:
			y[:, :, 0] = 0.5
			y[:, :, 1] = torch.linspace(0.0, 1.0, NUM_QUERIES)
			y[:, :, 2] = 0.0


		# calculating the median gaps
		median_gaps = torch.empty((n)).to(self.local_rank)
		for i in range(y.size(0)):
			y_i = y[i]
			gnd_mean_y_sorted = torch.sort(y_i[(y_i[:, 0] != 0) | (y_i[:, 1] != 0) | (y_i[:, 2] != 0)][:, 1]).values
			if len(gnd_mean_y_sorted) <= 1:
				median_gap = 0.33
			else:
				median_gap = torch.median(torch.abs(torch.diff(gnd_mean_y_sorted)))
			median_gap = max(median_gap, 0.01)
			median_gaps[i] = median_gap


		# calculate pairwise cost
		loss_geom_mat, _, loss_mat = self.calc_loss_geometric(outputs, y, median_gaps)
		

		# starting batch_wise
		batch_loss = 0.0
		batch_loss_geom = 0.0
		batch_loss_pos_log = 0.0
		batch_loss_neg_log = 0.0
		batch_loss_focal_pos = 0.0
		batch_loss_focal_neg = 0.0


		# going batch wise
		for i in range(n):
			# calculating median gap
			y_i = y[i]
			gnd_mean_y_sorted = torch.sort(y_i[(y_i[:, 0] != 0) | (y_i[:, 1] != 0) | (y_i[:, 2] != 0)][:, 1]).values
			if len(gnd_mean_y_sorted) <= 1:
				median_gap = 0.33
			else:
				median_gap = torch.median(torch.abs(torch.diff(gnd_mean_y_sorted)))
			median_gap = max(median_gap, 0.01)

			assert median_gap == median_gaps[i]
			
			# assignment
			all_gnd_ids, all_out_ids = linear_sum_assignment(loss_mat[i].detach().cpu().numpy())
			lines_mask = ((y[i, :, 0] != 0) | (y[i, :, 1] != 0) | (y[i, :, 2] != 0))
			num_lines = int(lines_mask.sum())
			# print(f"there are {num_lines} lines in the validation batch!")
			if not self.initialize:
				assert num_lines < MAX_LINES
			gnd_ids = all_gnd_ids[:num_lines]
			out_ids = all_out_ids[:num_lines]
			
			if VISUALIZE:
				loss_geom = loss_geom_mat[i, gnd_ids, out_ids]
				sel_mask = torch.zeros((NUM_QUERIES), dtype=torch.bool)
				sel_mask[out_ids] = True
				x_i = x[i]
				y_i = y[i]
				img = (x_i + 0.5) * 255
				img = img.permute(1, 2, 0).cpu().numpy()
				img = np.ascontiguousarray(img)
				img = img.astype(np.uint8)
				canvas = np.zeros((img.shape[0], img.shape[1]))
				out_i = outputs[i]
				for j, query in enumerate(out_i):
					mean_x = (query[0] * PATCH_SIZE).item()
					mean_y = (query[1] * PATCH_SIZE).item()
					slope = (query[2]).item()
					def line_equation(x_pts):
						return (x_pts - mean_x) * slope + mean_y
					x_pts_ = np.linspace(0, 255, 5).astype(np.int32)
					y_pts_ = line_equation(x_pts_).astype(np.int32)
					pts = np.stack((x_pts_, y_pts_), axis=-1)
					if sel_mask[j]:
						cv2.polylines(canvas, [pts], False, int(query[3] * 255), 3)
					else:
						cv2.polylines(canvas, [pts], False, int(query[3] * 255), 1)
						
				line_idx = 0
				for outline, gndline in zip(out_i[all_out_ids], y_i[all_gnd_ids]):
					if gndline[0] == 0 and gndline[1] == 0 and gndline[2] == 0:
						continue
					mean_x = (outline[0] * PATCH_SIZE).item()
					mean_y = (outline[1] * PATCH_SIZE).item()
					slope = outline[2].item()
					def line_equation(x):
						return slope * (x - mean_x) + mean_y
					x_pts = np.linspace(0, PATCH_SIZE-1, 5).astype(np.int32)
					y_pts = line_equation(x_pts).astype(np.int32)
					pts = np.stack((x_pts, y_pts), axis=-1)
					if outline[3] < 0.5:
						cv2.polylines(img, [pts], False, [0, 0, 0], 3)
					else:
						cv2.polylines(img, [pts], False, self.colors[line_idx], 3)

					mean_x = (gndline[0] * PATCH_SIZE).item()
					mean_y = (gndline[1] * PATCH_SIZE).item()
					slope = gndline[2].item()
					def line_equation(x):
						return slope * (x - mean_x) + mean_y
					x_pts = np.linspace(0, PATCH_SIZE-1, 16).astype(np.int32)
					y_pts = line_equation(x_pts).astype(np.int32)
					pts = np.stack((x_pts, y_pts), axis=-1)
					for pt in pts:
						cv2.circle(img, pt, 2, self.colors[line_idx], 2)
					line_idx += 1

				fig, axs = plt.subplots(1, 2, figsize=(20, 10))
				axs[0].imshow(img)
				axs[0].set_title(f"loss_geom: {loss_geom}\nqueries: {out_ids}")
				queries_map = axs[1].imshow(canvas)
				cbar = plt.colorbar(queries_map, ax=axs[1])
				ticks = cbar.get_ticks()
				ticks = (ticks / 255).tolist()
				ticks = [f"{tick:.2f}" for tick in ticks]
				cbar.ax.set_yticklabels(ticks)

				if not os.path.exists(f"ablation/{DESC}/valid_{self.local_rank}_{i}"):
					os.mkdir(f"ablation/{DESC}/valid_{self.local_rank}_{i}")
				if self.vis_step <= 9:
					plt.savefig(f"ablation/{DESC}/valid_{self.local_rank}_{i}/0000{self.vis_step}.jpg")
				elif self.vis_step <= 99:
					plt.savefig(f"ablation/{DESC}/valid_{self.local_rank}_{i}/000{self.vis_step}.jpg")
				elif self.vis_step <= 999:
					plt.savefig(f"ablation/{DESC}/valid_{self.local_rank}_{i}/00{self.vis_step}.jpg")
				elif self.vis_step <= 9999:
					plt.savefig(f"ablation/{DESC}/valid_{self.local_rank}_{i}/0{self.vis_step}.jpg")
				else:
					plt.savefig(f"ablation/{DESC}/valid_{self.local_rank}_{i}/{self.vis_step}.jpg")
				self.vis_step += 1
				plt.close()

			
			# calculating losses based on assignment
			loss_geom = torch.sum(loss_geom_mat[i, gnd_ids, out_ids]) / median_gap
			loss_pos_log = torch.sum(-torch.log(outputs[i, out_ids, 3]))
			loss_neg_log = torch.sum(-torch.log(outputs[i, all_out_ids[num_lines:], 4]))
			
			loss_focal_pos = -torch.sum((outputs[i, out_ids, 4]**2) * (outputs[i, out_ids, 5] - torch.log(torch.exp(outputs[i, out_ids, 5]) + torch.exp(outputs[i, out_ids, 6]))))

			loss_focal_neg = -torch.sum((outputs[i, all_out_ids[num_lines:], 3]**2) * (outputs[i, all_out_ids[num_lines:], 6] - torch.log(torch.exp(outputs[i, all_out_ids[num_lines:], 5]) + torch.exp(outputs[i, all_out_ids[num_lines:], 6]))))

			loss = loss_focal_pos * POS_FOCAL_COEFF + loss_focal_neg * NEG_FOCAL_COEFF + loss_geom * GEOM_COEFF
			batch_loss += loss
			batch_loss_geom += loss_geom.item()
			batch_loss_pos_log += loss_pos_log.item()
			batch_loss_neg_log += loss_neg_log.item()
			batch_loss_focal_pos += loss_focal_pos.item()
			batch_loss_focal_neg += loss_focal_neg.item()

		# averaging the losses over the batch
		batch_loss /= n
		batch_loss_geom /= n
		batch_loss_pos_log /= n
		batch_loss_neg_log /= n
		batch_loss_focal_pos /= n
		batch_loss_focal_neg /= n

		# logging the averaged losses, but only at epoch end
		self.log("val_loss", batch_loss.item(), on_epoch=True, on_step=False, sync_dist=True, prog_bar=True)
		self.log("val_loss_geom", batch_loss_geom, on_epoch=True, on_step=False, sync_dist=True, prog_bar=True)
		self.log("val_loss_pos_log", batch_loss_pos_log, on_epoch=True, on_step=False, sync_dist=True, prog_bar=True)
		self.log("val_loss_neg_log", batch_loss_neg_log, on_epoch=True, on_step=False, sync_dist=True, prog_bar=True)
		self.log("val_loss_focal_pos", batch_loss_focal_pos, on_epoch=True, on_step=False, sync_dist=True, prog_bar=True)
		self.log("val_loss_focal_neg", batch_loss_focal_neg, on_epoch=True, on_step=False, sync_dist=True, prog_bar=True)

		return batch_loss


	def configure_optimizers(self):
		optimizer = torch.optim.AdamW(self.parameters(), LR)
		return optimizer