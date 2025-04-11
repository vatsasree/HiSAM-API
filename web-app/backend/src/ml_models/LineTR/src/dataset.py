import torch
from torch.utils.data import DataLoader, TensorDataset, random_split
import pickle
import PIL
from PIL import Image
import numpy as np
import cv2
import torchvision.transforms.v2 as v2
from src.ml_models.LineTR.src.config import *
import os


class ManuscriptDatasetRotation(torch.utils.data.Dataset):
	def __init__(self, version=4):
		self.version = version
		avg_n_lines = 0
		loaded_data = None
		with open(f"./patches{self.version}/lines{self.version}.pkl", "rb") as f:
			loaded_data = pickle.load(f)
		self.loaded_data = loaded_data
		self.len = len(loaded_data)
		self.y = torch.zeros((self.len, NUM_QUERIES, 3))
		for i, datapoint in enumerate(loaded_data):
			num_lines = len(datapoint["lines"])
			avg_n_lines += num_lines
			for j in range(num_lines):
				self.y[i][j] = torch.tensor(loaded_data[i]["lines"][j])
				self.y[i][j][0] = self.y[i][j][0] / float(PATCH_SIZE)
				self.y[i][j][1] = self.y[i][j][1] / float(PATCH_SIZE)
		
		print(f"average number of lines is {float(avg_n_lines) / self.len}")
		
		self.augmentations = [
			v2.ElasticTransform(alpha=50.0),
			v2.ColorJitter(brightness=.5, hue=.05),
			v2.GaussianBlur(kernel_size=(11, 11), sigma=(0.1, 0.1)),
			v2.RandomAdjustSharpness(sharpness_factor=5)
		]
		

	def rot_aug(self, img, y):
		rot_y = torch.zeros((NUM_QUERIES, 3))
		degrees = torch.randint(low=0, high=10, size=(1,))
		sign = 2 * torch.randint(0, 2, (1,)) - 1
		degrees = degrees * sign
		img = img.rotate(degrees)
		theta = torch.deg2rad(torch.tensor(degrees))
		c = torch.cos(theta)
		s = torch.sin(theta)
		rot_mat = torch.tensor([
			[c, -s],
			[s, c]
		])
		for line_idx, line in enumerate(y):
			if line[0] == 0 and line[1] == 0 and line[2] == 0:
				continue
			extent = min(line[0], PATCH_SIZE - line[0])
			llim = line[0] - extent
			rlim = line[0] + extent
			left_pt = torch.tensor([llim, (llim - line[0]) * line[2] + line[1]])
			right_pt = torch.tensor([rlim, (rlim - line[0]) * line[2] + line[1]])
			left_pt -= 0.5
			right_pt -= 0.5
			left_pt[1] *= -1
			right_pt[1] *= -1
			left_pt = rot_mat @ left_pt
			right_pt = rot_mat @ right_pt
			left_pt[1] *= -1
			right_pt[1] *= -1
			left_pt += 0.5
			right_pt += 0.5
			rot_y[line_idx][:2] = (left_pt + right_pt) / 2
			rot_y[line_idx][2] = (right_pt[1] - left_pt[1]) / (right_pt[0] - left_pt[0])
			
        # scaling to remove rotation artifacts (the black triangles)
		scale_factor = torch.sin(torch.abs(theta)) + torch.cos(torch.abs(theta))
		img = np.array(img)
		new_side = int(PATCH_SIZE * scale_factor)
		img = cv2.resize(img, (new_side, new_side))
		shift = (new_side - PATCH_SIZE) // 2
		num_lines = ((y[:, 0] != 0) | (y[:, 1] != 0) | (y[:, 2] != 0)).sum()
		rot_y[:num_lines, :2] *= new_side
		rot_y[:num_lines, :2] -= shift
		rot_y[:num_lines, :2] /= PATCH_SIZE
		img = img[shift:new_side-shift, shift:new_side-shift, :]
		img = cv2.resize(img, (PATCH_SIZE, PATCH_SIZE))
		assert img.shape == ((PATCH_SIZE, PATCH_SIZE, 3))
		return Image.fromarray(img), rot_y


	def __len__(self):
		return self.len
	

	def __getitem__(self, index):
		img = cv2.imread(f"./patches{self.version}/windows{self.version}/{index}.jpg")
		img = Image.fromarray(img)
		y = self.y[index]
		rot_or_not = torch.randint(0, 2, (1,))
		if rot_or_not:
			img, y = self.rot_aug(img, y)
		for aug in self.augmentations:
			if torch.randint(0, 2, (1,)) >= 1:
				img = aug(img)
		img = np.array(img)
		img_t = torch.from_numpy(img).permute(2, 0, 1).type(torch.float32)
		img_t = img_t / 255.0 - 0.5
		return (img_t, y)

		# img = Image.open(f"../prepare_training_data/tilesv3/{index}.jpg")
		# # for aug in self.augmentations:
		# # 	if random.randint(0, 3) >= 1:
		# # 		img = aug(img)
		# transform = transforms.Compose([
		# 	transforms.ToTensor(),
		# ])
		# img_t = transform(img).type(torch.float32).contiguous()
		# img_t = img_t - 0.5
		# y = self.y[index]
		# return (img_t, y)
	

class ManuscriptDataset(torch.utils.data.Dataset):
	def __init__(self, version):
		self.version = version
		avg_n_lines = 0
		loaded_data = None
		with open(f"./patches{self.version}/lines{self.version}.pkl", "rb") as f:
			loaded_data = pickle.load(f)
		self.loaded_data = loaded_data
		self.len = len(loaded_data)
		self.y = torch.zeros((self.len, NUM_QUERIES, 3))
		for i, datapoint in enumerate(loaded_data):
			num_lines = len(datapoint["lines"])
			avg_n_lines += num_lines
			for j in range(num_lines):
				self.y[i][j] = torch.tensor(loaded_data[i]["lines"][j])
				self.y[i][j][0] = self.y[i][j][0] / float(PATCH_SIZE)
				self.y[i][j][1] = self.y[i][j][1] / float(PATCH_SIZE)
		
		print(f"average number of lines is {float(avg_n_lines) / self.len}")


		# self.augmentations = [
		# 	v2.ElasticTransform(alpha=50.0),
		# 	v2.ColorJitter(brightness=.5, hue=.05),
		# 	v2.GaussianBlur(kernel_size=(5, 5), sigma=(0.1, 0.1)),
		# 	v2.RandomAdjustSharpness(sharpness_factor=5)
		# ]

	def __len__(self):
		return self.len
	
	def __getitem__(self, index):
		img = cv2.imread(f"./patches{self.version}/windows{self.version}/{index}.jpg")
		img_t = torch.from_numpy(img).permute(2, 0, 1).type(torch.float32)
		img_t = img_t / 255.0 - 0.5
		y = self.y[index]
		return (img_t, y)

		# img = Image.open(f"../prepare_training_data/tilesv3/{index}.jpg")
		# # for aug in self.augmentations:
		# # 	if random.randint(0, 3) >= 1:
		# # 		img = aug(img)
		# transform = transforms.Compose([
		# 	transforms.ToTensor(),
		# ])
		# img_t = transform(img).type(torch.float32).contiguous()
		# img_t = img_t - 0.5
		# y = self.y[index]
		# return (img_t, y)
	

class BinDataset(torch.utils.data.Dataset):
	def __init__(self, version):
		self.version = version
		filenames = os.listdir(f"bin_patches{self.version}/windows{self.version}/")
		self.len = len(filenames)


		# self.augmentations = [
		# 	v2.ElasticTransform(alpha=50.0),
		# 	v2.ColorJitter(brightness=.5, hue=.05),
		# 	v2.GaussianBlur(kernel_size=(5, 5), sigma=(0.1, 0.1)),
		# 	v2.RandomAdjustSharpness(sharpness_factor=5)
		# ]

	def __len__(self):
		return self.len
	
	def __getitem__(self, index):
		img = cv2.imread(f"./bin_patches{self.version}/windows{self.version}/{index}.jpg")
		img_t = torch.from_numpy(img).permute(2, 0, 1).type(torch.float32)
		img_t = img_t / 255.0 - 0.5
		
		bin_img = cv2.imread(f"./bin_patches{self.version}/bin_windows{self.version}/{index}.jpg", cv2.IMREAD_GRAYSCALE)
		_, bin_img = cv2.threshold(bin_img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
		bin_img_t = torch.from_numpy(bin_img).type(torch.float32)
		bin_img_t[bin_img_t == 255] = 1.0
		bin_img_t[bin_img_t == 0] = 0.0
		return (img_t, bin_img_t)

		# img = Image.open(f"../prepare_training_data/tilesv3/{index}.jpg")
		# # for aug in self.augmentations:
		# # 	if random.randint(0, 3) >= 1:
		# # 		img = aug(img)
		# transform = transforms.Compose([
		# 	transforms.ToTensor(),
		# ])
		# img_t = transform(img).type(torch.float32).contiguous()
		# img_t = img_t - 0.5
		# y = self.y[index]
		# return (img_t, y)