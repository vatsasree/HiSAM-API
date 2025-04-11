import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as opt
from torch.utils.data import DataLoader, TensorDataset, random_split, Subset
from torchvision.transforms import ToTensor
import pickle
import os
# import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment
import matplotlib.pyplot as plt
import shutil
from lightning.pytorch import LightningModule
import lightning as L
from copy import deepcopy
from lightning.pytorch.loggers import WandbLogger
from lightning.pytorch.callbacks import ModelCheckpoint
torch.manual_seed(1709)
from src.ml_models.LineTR.src.linetr import TLDr_Trainer
from src.ml_models.LineTR.src.dataset import BinDataset
from src.ml_models.LineTR.src.config_binarizer import * 



class TLDr_BinDecoder(LightningModule):
	def __init__(self, encoder):
		super().__init__()
		# the encoder
		self.encoder = encoder
		

		# the decoder layers
		self.hidden_dim = 256
		self.num_decoder_layers = 3
		self.n_heads = 8
		self.decoder_layers = nn.ModuleList([
			nn.TransformerDecoderLayer(self.hidden_dim, self.n_heads)
			for _ in range(self.num_decoder_layers)
		])


		# the flawed approach 
		# self.to_pixels = nn.Linear(256, 256)
		# self.to_pixels.bias = nn.Parameter(torch.tensor(0.25))


		# the convolution layers to successively get global features
		# this will start acting on the input image
		self.img_conv1 = nn.Conv2d(in_channels=3, out_channels=32, kernel_size=(3, 3), stride=(2, 2), padding=(1, 1))
		self.img_conv2 = nn.Conv2d(in_channels=32, out_channels=64, kernel_size=(3, 3), stride=(2, 2), padding=(1, 1))
		self.img_conv3 = nn.Conv2d(in_channels=64, out_channels=128, kernel_size=(3, 3), stride=(2, 2), padding=(1, 1))
		self.img_conv4 = nn.Conv2d(in_channels=128, out_channels=256, kernel_size=(3, 3), stride=(2, 2), padding=(1, 1))


		# the deconvolution layers to increase resolution of the feature map obtained after attention
		# this will start acting on the final embeddings output by the transformer decoder
		self.img_deconv4 = nn.ConvTranspose2d(in_channels=256, out_channels=128, kernel_size=(3, 3), stride=(2, 2), padding=(1, 1))
		self.img_deconv3 = nn.ConvTranspose2d(in_channels=128, out_channels=64, kernel_size=(3, 3), stride=(2, 2), padding=(1, 1))
		self.img_deconv2 = nn.ConvTranspose2d(in_channels=64, out_channels=32, kernel_size=(3, 3), stride=(2, 2), padding=(1, 1))
		self.img_deconv1 = nn.ConvTranspose2d(in_channels=32, out_channels=1, kernel_size=(3, 3), stride=(2, 2), padding=(1, 1))


		# convolution layers to merge the outputs of the transformer decoder with the heirarchical features extracted from the image by the convolution layers
		self.merge_conv4 = nn.Conv2d(in_channels=512, out_channels=256, kernel_size=(3, 3), stride=(1, 1), padding=(1, 1))
		self.merge_conv3 = nn.Conv2d(in_channels=256, out_channels=128, kernel_size=(3, 3), stride=(1, 1), padding=(1, 1))
		self.merge_conv2 = nn.Conv2d(in_channels=128, out_channels=64, kernel_size=(3, 3), stride=(1, 1), padding=(1, 1))
		self.merge_conv1 = nn.Conv2d(in_channels=64, out_channels=32, kernel_size=(3, 3), stride=(1, 1), padding=(1, 1))
		

		# sigmoid on the last feature map to predict probabilities
		self.sigmoid = nn.Sigmoid()


		# if visualizing
		if VISUALIZE:
			self.input_vis = 0
			self.vis_step = 0


	def forward(self, x):
		# getting heirarchical features from the image using convolution layers
		# would be of the format (B, C, H, W)
		x_feat1 = self.img_conv1(x)
		x_feat2 = self.img_conv2(x_feat1)
		x_feat3 = self.img_conv3(x_feat2)
		x_feat4 = self.img_conv4(x_feat3)
		
		
		# permuted to (B, H, W, C) and reshaped to (B, Q, E)
		x_feat = x_feat4.permute(0, 2, 3, 1).reshape(x.size(0), -1, self.hidden_dim)
		# permute to make batch the second dimension, i.e. (Q, B, E)
		x_feat = x_feat.permute(1, 0, 2)
		

		# the original input is passed to the encoder
		x = self.encoder(x)
		# permute the encoder memory to make batch the second dimension
		x = x.permute(1, 0, 2)


		# the decoder pass
		# self attention with the encoder memory, cross attention with the final conv layer features (x_feat)
		for i in range(self.num_decoder_layers):
			x = self.decoder_layers[i](x, x_feat)


		# permute back to (B, Q, E)
		x = x.permute(1, 0, 2)


		# reshape from (B, Q, E) to (B, H, W, C)
		x = x.reshape(x.size(0), 16, 16, self.hidden_dim)
		# permute to bring the channels to the front, (B, C, W, H)
		x = x.permute(0, 3, 1, 2)

		
		# concatenate the decoder outputs with the corresponding level features from the initial conv layers
		x_merged_feat4 = torch.cat([x_feat4, x], dim=1)

		# performing a merging convolution to reduce the number of channels
		x_merged_feat4 = self.merge_conv4(x_merged_feat4)

		# perform a deconvolution to upscale the features
		x_merged_feat4 = self.img_deconv4(x_merged_feat4)

		# pad the features to the power of 2
		x_merged_feat4 = F.pad(x_merged_feat4, (1, 0, 1, 0))
		

		# repeat the above process for further levels


		x_merged_feat3 = torch.cat([x_merged_feat4, x_feat3], dim=1)
		x_merged_feat3 = self.merge_conv3(x_merged_feat3)
		x_merged_feat3 = self.img_deconv3(x_merged_feat3)
		x_merged_feat3 = F.pad(x_merged_feat3, (1, 0, 1, 0))


		x_merged_feat2 = torch.cat([x_merged_feat3, x_feat2], dim=1)
		x_merged_feat2 = self.merge_conv2(x_merged_feat2)
		x_merged_feat2 = self.img_deconv2(x_merged_feat2)
		x_merged_feat2 = F.pad(x_merged_feat2, (1, 0, 1, 0))


		x_merged_feat1 = torch.cat([x_merged_feat2, x_feat1], dim=1)
		x_merged_feat1 = self.merge_conv1(x_merged_feat1)
		x_merged_feat1 = self.img_deconv1(x_merged_feat1)
		x_merged_feat1 = F.pad(x_merged_feat1, (1, 0, 1, 0))


		# this should be of the shape of the final image (B, 1, 256, 256)
		x = x_merged_feat1
		
		
		# in this case this is the default shape already
		x = self.sigmoid(x)
		return x.squeeze(1)


	def training_step(self, batch, batch_idx):
		# inference
		x, y = batch
		n = x.size(0)
		outputs = self(x)
		

		# visualization
		if VISUALIZE and self.input_vis < 10:
			img = (x[0] + 0.5) * 255.0
			img = img.permute(1, 2, 0)
			img = img.cpu().numpy().astype(np.int32)
			img = np.ascontiguousarray(img)
			

			bin_img = (y[0] + 0.5) * 255.0
			bin_img = bin_img.cpu().numpy().astype(np.int32)
			bin_img = np.ascontiguousarray(bin_img)
			
			fig, axs = plt.subplots(1, 2)
			axs[0].imshow(img)
			axs[1].imshow(bin_img)
			plt.savefig(f"{self.input_vis}.jpg")
			plt.close()

			self.input_vis += 1


		# starting batch_wise
		batch_loss_pos = 0.0
		batch_loss_neg = 0.0
		

		# computing the loss
		# using focal loss
		pos_mask = (y == 1)
		batch_loss_pos += -torch.sum(POS_FOCAL_COEFF * ((1 - outputs[pos_mask]) ** 2) * (torch.log(outputs[pos_mask])))
		neg_mask = (y == 0)
		batch_loss_neg += -torch.sum(NEG_FOCAL_COEFF * ((outputs[neg_mask]) ** 2) * (torch.log(1 - outputs[neg_mask])))
		
		batch_loss = batch_loss_pos + batch_loss_neg

		batch_loss /= n
		batch_loss_pos /= n
		batch_loss_neg /= n


		# logging the averaged losses, but only at epoch end
		self.log("train_loss", batch_loss.item(), on_epoch=True, on_step=False, sync_dist=True, prog_bar=True)
		self.log("train_loss_pos", batch_loss_pos.item(), on_epoch=True, on_step=False, sync_dist=True, prog_bar=True)
		self.log("train_loss_neg", batch_loss_neg.item(), on_epoch=True, on_step=False, sync_dist=True, prog_bar=True)

		return batch_loss


	def validation_step(self, batch, batch_idx):
		# inference
		x, y = batch
		n = x.size(0)
		outputs = self(x)


		# # starting batch_wise
		# batch_loss = 0.0
		if VISUALIZE and self.input_vis < 100:
			img = (x[0] + 0.5) * 255.0
			img = img.permute(1, 2, 0)
			img = img.cpu().numpy().astype(np.int32)
			img = np.ascontiguousarray(img)
			

			bin_img = (outputs[0] + 0.5) * 255.0
			bin_img = bin_img.cpu().numpy().astype(np.int32)
			bin_img = np.ascontiguousarray(bin_img)
			
			fig, axs = plt.subplots(1, 2)
			axs[0].imshow(img)
			axs[1].imshow(bin_img)
			plt.savefig(f"{self.input_vis}.jpg")
			plt.close()

			self.input_vis += 1
			

		# starting batch_wise
		batch_loss_pos = 0.0
		batch_loss_neg = 0.0


		# computing the loss
		# using focal loss
		pos_mask = (y == 1)
		batch_loss_pos += -torch.sum(POS_FOCAL_COEFF * ((1 - outputs[pos_mask]) ** 2) * (torch.log(outputs[pos_mask])))
		neg_mask = (y == 0)
		batch_loss_neg += -torch.sum(NEG_FOCAL_COEFF * ((outputs[neg_mask]) ** 2) * (torch.log(1 - outputs[neg_mask])))
		
		batch_loss = batch_loss_pos + batch_loss_neg

		batch_loss /= n
		batch_loss_pos /= n
		batch_loss_neg /= n


		# logging the averaged losses, but only at epoch end
		self.log("val_loss", batch_loss.item(), on_epoch=True, on_step=False, sync_dist=True, prog_bar=True)
		self.log("val_loss_pos", batch_loss_pos.item(), on_epoch=True, on_step=False, sync_dist=True, prog_bar=True)
		self.log("val_loss_neg", batch_loss_neg.item(), on_epoch=True, on_step=False, sync_dist=True, prog_bar=True)

		return batch_loss


	def configure_optimizers(self):
		optimizer = torch.optim.AdamW(self.parameters(), LR)
		return optimizer