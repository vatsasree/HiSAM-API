import json
import cv2
import matplotlib.pyplot as plt
import numpy as np
import os
os.environ['TQDM_DISABLE']='True'
from tqdm import tqdm
import shutil
from sklearn.decomposition import PCA
from torch.utils.data import TensorDataset, DataLoader
import pickle
import sys
import torch
# from .src.linetr import TLDr_Trainer
# from .src.binarizer import TLDr_BinDecoder
# from .seamgen import compute_lower_seams, compute_upper_seams
from src.ml_models.LineTR.src.linetr import TLDr_Trainer
from src.ml_models.LineTR.src.binarizer import TLDr_BinDecoder
from src.ml_models.LineTR.seamgen import compute_lower_seams, compute_upper_seams


PATCH_SIZE = 256
MIN_WINDOW_SIZE = 96
BATCH_SIZE = 24
MAX_MERGING_ITERS = 5


DATASET = sys.argv[-1]

COLORS_PKL_PATH = "/data3/amal.joseph/template_api/store/model_files/linetrckp/colors_new.pkl"
LINETR_CHECKPOINT = "/data3/amal.joseph/template_api/store/model_files/linetrckp/best_scr.ckpt"
LINETR_BINARIZER_CHECKPOINT = "/data3/amal.joseph/template_api/store/model_files/linetrckp/best_bin.ckpt"

class Infer:
	def __init__(self):
		self.contexts = np.array([6, 7, 8], dtype=np.int32)
		# self.device = torch.device('cuda:1' if torch.cuda.is_available() else 'cpu')
		self.device = "cuda:0"
		self.model = TLDr_Trainer.load_from_checkpoint(LINETR_CHECKPOINT).to(self.device)
		self.bin_model = TLDr_BinDecoder.load_from_checkpoint(
			LINETR_BINARIZER_CHECKPOINT, encoder=self.model.encoder
		).to(self.device)
		self.model.freeze()
		self.bin_model.freeze()
		self.model.eval()
		print(f"using device {self.model.query_content.device}")
		# self.device = self.model.query_content.device
		self.all_data = []
		self.region = 0.7
		self.model = self.model
		self.matching_threshold = 0.35
		self.name = None
		self.prob_thresh = 0.9
		with open(COLORS_PKL_PATH, "rb") as f:
			self.colors = pickle.load(f)

	def infer_patches(self, infer_bin=False):
		tensors = torch.cat([tile["tensor"].unsqueeze(0) for tile in self.img_tiles], dim=0)
		for i in range(0, len(tensors), BATCH_SIZE):
			x = tensors[i:i+BATCH_SIZE]
			n = x.size(0)
			x = x.to(self.device)
			# print(f'\n\n\n {self.device} \n {next(self.model.parameters()).device} \n {x.device} \n\n\n\n')
			_, outputs = self.model(x)
			outputs = outputs.detach().cpu().numpy()
			if infer_bin:
				heat_map = self.bin_model(x).detach().cpu().numpy()
			for j in range(n):
				self.img_tiles[i + j]["outputs"] = outputs[j]
				if infer_bin:
					self.img_tiles[i + j]["heat_map"] = cv2.resize(heat_map[j], self.img_tiles[i + j]["patch_size"])
		return self.img_tiles




	def pad_img(self, img, padding_top, padding_left, padding_bottom, padding_right):
		padded_img = np.zeros((img.shape[0] + padding_top + padding_bottom, img.shape[1] + padding_left + padding_right, 3))
		padded_img.fill(255)
		padded_img = padded_img.astype(np.uint8)
		padded_img[padding_top:-padding_bottom, padding_left:-padding_right, :] = img
		return padded_img

	
	def prepare_folders(self):
		if os.path.exists(f"outputs_{self.name}"):
			shutil.rmtree(f"outputs_{self.name}")
		os.mkdir(f"outputs_{self.name}")
		
		if os.path.exists(f"heatmaps_{self.name}"):
			shutil.rmtree(f"heatmaps_{self.name}")
		os.mkdir(f"heatmaps_{self.name}")


	def remove_outliers(self):

		for i in range(self.n_lines):
			line_pts_y, line_pts_x = np.where(self.global_canvas == i + 1)
			if len(line_pts_y) == 0:
				continue
			max_weight = np.max(self.global_weight_canvas[line_pts_y, line_pts_x])
			if max_weight < 2.0:
				# at max a point is vouched for by two lines
				self.global_weight_canvas[line_pts_y, line_pts_x] = 0 
			else:
				self.global_weight_canvas[line_pts_y, line_pts_x] = max_weight

		img_ = cv2.cvtColor(self.img, cv2.COLOR_BGR2GRAY).astype(np.uint8)   
		_, otsu_threshold = cv2.threshold(img_, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU) 
		kernel = np.ones((3, 3), dtype=np.uint8)  
		# kernel = np.ones((3, 3)) / 9 
		otsu_threshold = 255 - cv2.dilate((255 - otsu_threshold), kernel, iterations=3) 
		# assert len(np.unique(otsu_threshold)) == 2 
		# cv2.imwrite(f"otsu.jpg", otsu_threshold) 

		self.global_canvas[self.global_weight_canvas == 0] = 0 
		# self.global_canvas[otsu_threshold == 255] = 0 

		global_canvas_vis = self.img.copy() 
		global_canvas_vis[self.global_canvas > 0] = (255, 0, 0)  
		# cv2.imwrite(f"global_canvas_vis.jpg", global_canvas_vis) 

		# global_canvas_vis = self.global_canvas.copy() 
		# global_canvas_vis[self.global_canvas > 0] = 255   
		# cv2.imwrite(f"global_canvas_vis.jpg", global_canvas_vis) 


		# removing gaps in global canvas
		new_global_canvas = np.zeros_like(self.global_canvas)
		n_lines_new = 0
		for i in range(self.n_lines):

			# obtaining points with index in global_canvas
			line_pts_y, line_pts_x = np.where(self.global_canvas == i + 1)
			if len(line_pts_x) == 0:
				continue
			new_global_canvas[line_pts_y, line_pts_x] = n_lines_new + 1
			n_lines_new += 1
		
		self.global_canvas = new_global_canvas
		self.n_lines = n_lines_new

		img_scribbled = self.img.copy()
		for i in range(self.n_lines): 
			line_pts_y, line_pts_x = np.where(self.global_canvas == i + 1) 
			line_pts = np.stack((line_pts_x, line_pts_y), axis=-1) 
			cv2.polylines(img_scribbled, [line_pts], False, (255, 0, 0), 2) 
		
		# cv2.imwrite(f"img_scribbled.jpg", img_scribbled) 

		return
	

	def reproject_bin(self):
		global_heat_map = np.zeros((self.img.shape[0], self.img.shape[1]))



		# for window in tqdm(self.img_tiles):
		for window in self.img_tiles:
			patch_size = window["patch_size"]


			padded_global_heat_map = np.zeros((self.img.shape[0]+patch_size[1]//2+patch_size[1], self.img.shape[1]+patch_size[0]//2+patch_size[0]))

			padded_global_heat_map[patch_size[1]//2:patch_size[1]//2+self.img.shape[0], patch_size[0]//2:patch_size[0]//2+self.img.shape[1]] = global_heat_map


			top_left = window["tl"]
			bottom_right = (window["tl"][0] + window["patch_size"][0], window["tl"][1] + window["patch_size"][1])


			padded_global_heat_map[top_left[1]:bottom_right[1], top_left[0]:bottom_right[0]] += window["heat_map"]


			global_heat_map = padded_global_heat_map[patch_size[1]//2:patch_size[1]//2+self.img.shape[0], patch_size[0]//2:patch_size[0]//2+self.img.shape[1]]


		max_val = np.max(global_heat_map)
		min_val = np.min(global_heat_map)
		global_heat_map = (global_heat_map - min_val) / (max_val - min_val)
		self.global_heat_map = ((1.0 - global_heat_map) * 255).astype(np.uint8)

		return 


	def reproject(self):
		"""
		Algorithm:
		Iterate over all the patches. Project some points onto the global canvas. For each point keep record of which line in the global space does it belong to. When a patch projects to a location that has already been seen, then for each line in the new patch there are two options:
			1. It is starting a new line that has not been seen before.
			2. It is enforcing an existing line
		"""

		# the global canvas on which points would be projected
		self.global_canvas = np.zeros((self.img.shape[0], self.img.shape[1]))
		

		# the global weight canvas storing the strength of each point
		self.global_weight_canvas = np.zeros((self.img.shape[0], self.img.shape[1]))
		

		# the number of distinct text lines in the global canvas till now
		self.n_lines = 0


		# for window in tqdm(self.img_tiles):
		for window in self.img_tiles:
			patch_size = window["patch_size"]
			

			# padding the global canvas
			padded_global_canvas = np.zeros((self.img.shape[0]+patch_size[1]//2+patch_size[1], self.img.shape[1]+patch_size[0]//2+patch_size[0]))
			padded_global_canvas[patch_size[1]//2:patch_size[1]//2+self.img.shape[0], patch_size[0]//2:patch_size[0]//2+self.img.shape[1]] = self.global_canvas


			# padding the global weight canvas
			padded_weight_canvas = np.zeros((self.img.shape[0]+patch_size[1]//2+patch_size[1], self.img.shape[1]+patch_size[0]//2+patch_size[0]))
			padded_weight_canvas[patch_size[1]//2:patch_size[1]//2+self.img.shape[0], patch_size[0]//2:patch_size[0]//2+self.img.shape[1]] = self.global_weight_canvas


			# top left and bottom right of the current window
			top_left = window["tl"]
			bottom_right = (window["tl"][0] + window["patch_size"][0], window["tl"][1] + window["patch_size"][1])
			

			# sampling a current snapshot of the corresponding window of the global canvas and the global weight canvas
			canvas = padded_global_canvas[top_left[1]:bottom_right[1], top_left[0]:bottom_right[0]]
			weight_canvas = padded_weight_canvas[top_left[1]:bottom_right[1], top_left[0]:bottom_right[0]]
			

			# sanity check
			assert canvas.shape[0] == patch_size[1]
			assert canvas.shape[1] == patch_size[0]
			

			# iterating over the outputs
			for line in window["outputs"]:
				probability_score = line[3]
				if probability_score < self.prob_thresh:
					continue
				

				mean_x_new = line[0] * patch_size[0]
				mean_y_new = line[1] * patch_size[0]
				slope_new = line[2]


				def line_equation(x):
					return slope_new * (x - mean_x_new) + mean_y_new
				

				# sampling the points
				x = np.linspace(0, patch_size[0] - 1, patch_size[0] // 2).astype(np.int32)
				y = line_equation(x).astype(np.int32)
				mask = (y < patch_size[0]) & (y >= 0)
				x = x[mask]
				y = y[mask]
				

				# new_pts are the points obtained freshly from the window that I am considering right now
				new_pts = np.stack((x, y), axis=-1)
				
				# using these new points, I want to update my estimate of the global canvas
				# if new_line = True, that means that this given line in the window represents an entirely new line in the global canvas
				# and if new_line = False, that means this given line can be merged to some existing line in the global canvas
				new_line = True
				
				
				# in the global canvas, the ith line is represented by (i + 1) pixel valued points
				for i in range(self.n_lines):
					# all the points associated with that line already present in the canvas
					line_pts = np.where(canvas == i + 1)

					
					# sanity check
					assert len(line_pts) > 0

					
					line_pts = (line_pts[1], line_pts[0])
					line_pts = np.stack((line_pts[0], line_pts[1]), axis=-1)
					

					# match variable denotes if THIS line in the global canvas matches well with the new line in the window that I am currently looking at
					match = False
					

					# calculating pairwise distances
					line_pts_mat = np.repeat(line_pts[None, :, :], len(new_pts), 0)
					new_pts_mat = np.repeat(new_pts[:, None, :], len(line_pts), 1)
					cost_mat = np.linalg.norm(line_pts_mat - new_pts_mat, axis=-1)
					if cost_mat.size == 0:
						continue
					cost_mat = np.min(cost_mat, axis=1)
					mask = cost_mat < self.matching_threshold * self.median_gap
					mask_cnt = mask.astype(np.int32).sum()
					if mask_cnt > 0.33 * cost_mat.size:
					# if np.any(cost_mat < self.matching_threshold * self.median_gap):
						match = True
						new_line = False
					

					# if we could not match to THIS existing line (the ith existing line), then we will search for match with another existing line!
					if not match:
						continue
					

					# reinforce the existing line
					line_pts = np.where((canvas == i + 1))
					line_pts = (line_pts[1], line_pts[0])
					pts = np.stack((line_pts[0], line_pts[1]), axis=-1)


					# concatenating the existing points (in the global canvas) with the newly sampled fresh points from the window
					# perform a PCA after combining the existing points and the newly sampled points
					# the hypothesis is that the line obtained after the PCA is better than what was before
					# then ERASE the earlier line from the canvas, and writing the new, PCA refined version
					# and you replace the canvas (which is a small window) on the global canvas

					pts = np.concatenate((pts, new_pts), axis=0)
					pca = PCA()
					pca.fit(pts)
					first_principal_component = pca.components_[0]
					if np.isclose(first_principal_component[0], 0):
						continue
					slope_pca = first_principal_component[1] / first_principal_component[0]
					mean_pca = pca.mean_
					def line_equation(x):
						return slope_pca * (x - mean_pca[0]) + mean_pca[1]
					

					# these represent the fresh points
					x = np.linspace(0, patch_size[0] - 1, patch_size[0] // 2).astype(np.int32)
					y = line_equation(x).astype(np.int32)
					mask = (y < patch_size[1]) & (y >= 0)
					x = x[mask]
					y = y[mask]


					# ERASING all the existing points
					canvas[line_pts[1], line_pts[0]] = 0


					# writing the new information
					canvas[y, x] = i + 1
					weight_canvas[y, x] += probability_score


					# replacing the canvas on the global canvas
					padded_global_canvas[top_left[1]:bottom_right[1], top_left[0]:bottom_right[0]] = canvas
					padded_weight_canvas[top_left[1]:bottom_right[1], top_left[0]:bottom_right[0]] = weight_canvas


				# when NO match was found
				if new_line:
					self.n_lines += 1
					assert len(new_pts) > 0


					# marking the pixel locations corresponding to the n_lines waali line
					canvas[new_pts[:, 1], new_pts[:, 0]] = self.n_lines
					weight_canvas[new_pts[:, 1], new_pts[:, 0]] = probability_score


					padded_global_canvas[top_left[1]:bottom_right[1], top_left[0]:bottom_right[0]] = canvas
					padded_weight_canvas[top_left[1]:bottom_right[1], top_left[0]:bottom_right[0]] = weight_canvas


			self.global_canvas = padded_global_canvas[patch_size[1]//2:patch_size[1]//2+self.img.shape[0], patch_size[0]//2:patch_size[0]//2+self.img.shape[1]]
			self.global_weight_canvas = padded_weight_canvas[patch_size[1]//2:patch_size[1]//2+self.img.shape[0], patch_size[0]//2:patch_size[0]//2+self.img.shape[1]]


		# THIS LEADS TO OVER-CROPPING NEAR THE ENDS, HENCE COMMENTING OUT
		# removing all those points who were predicted only once
		# on an average every point will be predicted 6 times
		# self.global_weight_canvas[self.global_weight_canvas < 1.5] = 0.0
		# self.global_canvas[self.global_weight_canvas == 0.0] = 0.0 


		merging_iters = 0
		while True:
			change = False
			scr_mat = np.zeros((self.n_lines, self.n_lines), dtype=np.int32)
			for line1_id in range(self.n_lines):
				scr_mat[line1_id, line1_id] = 1

				# collecting line1_pts
				line1_pts_y, line1_pts_x = np.where((self.global_canvas == line1_id + 1))
				if len(line1_pts_x) == 0:
					continue
				line1_pts = np.stack((line1_pts_x, line1_pts_y), axis=-1)
				for line2_id in range(line1_id + 1, self.n_lines):

					# collecting line2_pts
					line2_pts_y, line2_pts_x = np.where((self.global_canvas == line2_id + 1))
					if len(line2_pts_x) == 0:
						continue
					line2_pts = np.stack((line2_pts_x, line2_pts_y), axis=-1)
					

					# making the cost matrix
					line1_pts_mat = np.repeat(line1_pts[None, :, :], len(line2_pts), axis=0)
					line2_pts_mat = np.repeat(line2_pts[:, None, :], len(line1_pts), axis=1)
					cost_mat = np.linalg.norm(line1_pts_mat - line2_pts_mat, axis=-1)
					cost_mat = np.min(cost_mat, axis=-1)


					# the matching cost function
					# 1 first find points that are "cousins"
					# 2 if at least half of the "cousins" are "close", merge them
					cousins = (cost_mat <= 2 * self.median_gap).sum()
					siblings = (cost_mat <= self.matching_threshold * self.median_gap).sum()
					if siblings > cousins // 3:
						# merge them
						change = True
						scr_mat[line1_id, line2_id] = 1
						scr_mat[line2_id, line1_id] = 1
			

			assert np.allclose(scr_mat, scr_mat.T)
			if not change or merging_iters >= MAX_MERGING_ITERS:
				break
			merging_iters += 1

			vis = -np.ones((self.n_lines), dtype=np.int32)

			def dfs(group, first):
				vis[first] = group
				for second in range(self.n_lines):
					if not scr_mat[first][second] or vis[second] == group or second == first:
						continue
					assert vis[second] == -1
					dfs(group, second)
				
			
			for first in range(self.n_lines):
				if vis[first] == -1:
					dfs(first, first)
				assert vis[first] != -1

			assert not np.any(vis == -1)
			
			new_global_canvas = np.zeros_like(self.global_canvas)
			n_lines_new = 0
			groups = np.unique(vis)
			for group in groups:
				members = np.where(vis == group)[0]
				for member in members:
					new_global_canvas[self.global_canvas == member + 1] = n_lines_new + 1
				n_lines_new += 1
			
			self.global_canvas = new_global_canvas
			self.n_lines = n_lines_new

		if self.n_lines == 0:
			print(f"NO LINES!")

		return
	

	def sample_patches(self, patch_size, stride_x, stride_y):
		padded_img = self.pad_img(self.img, patch_size[1]//2, patch_size[0]//2, patch_size[1], patch_size[0])
		self.padded_img = padded_img

		img_tiles = [{"img": padded_img[i:i+patch_size[1], j:j+patch_size[0]], "tl": (j, i)} for i in range(0, padded_img.shape[0]-patch_size[1]+1, stride_y) for j in range(0, padded_img.shape[1]-patch_size[0]+1, stride_x)]
		for i, tile in enumerate(img_tiles):
			tile["img"] = cv2.resize(tile["img"], (PATCH_SIZE, PATCH_SIZE))
			img_np = tile["img"]
			img_tensor_float = torch.from_numpy(img_np.astype(np.float32))
			tile["tensor"] = (img_tensor_float / 255.0 - 0.5)
			tile["tensor"] = tile["tensor"].permute(2, 0, 1)
			tile["patch_size"] = patch_size
			tile["img_path"] = self.img_path
		return img_tiles
	

	def find_best_patch_sizes(self):
		# finding the best patch sizes
		self.img_tiles = []
		for i, patch_size in enumerate(self.query_patch_sizes): # ENUMERATE REMOVE
			self.img_tiles += self.sample_patches(patch_size, patch_size[0] , patch_size[1] // 2)

		self.infer_patches(infer_bin=True)
		for i, tile in enumerate(self.img_tiles):
			outputs = tile["outputs"]
			outputs = outputs[outputs[:, 3] > self.prob_thresh]
			tile["outputs"] = outputs
		# valid_context_img_tiles = []
		# for patch_size in self.query_patch_sizes:
		# 	filtered_img_tiles = [tile for tile in self.img_tiles if tile["patch_size"] == patch_size]
		# 	n_lines = np.array([len(tile["outputs"]) for tile in filtered_img_tiles], dtype=np.int32)
		# 	n_lines = n_lines[n_lines > 0]
		# 	unique_nlines, counts = np.unique(n_lines, return_counts=True)
		# 	mode = unique_nlines[np.argmax(counts)]
		# 	valid_context_img_tiles += filtered_img_tiles

		all_gaps = []
		for tile in self.img_tiles:
			tile_y_sorted = np.sort(tile["outputs"][:, 1])
			if len(tile_y_sorted) <= 1:
				continue
			gap = np.median(np.abs(np.diff(tile_y_sorted))).item() * tile["patch_size"][1]
			assert gap >= 0 and not np.isnan(gap)
			all_gaps.append(gap)

		if len(all_gaps) == 0:
			proposed_patch_sizes = [(64, 64), (96, 96), (128, 128), (256, 256)]
			self.median_gap = 50.0
			self.patch_sizes = []

			# performing sanity check on the patch sizes
			for patch_size in proposed_patch_sizes:
				if patch_size[1] <= self.img.shape[0] * 2 and patch_size[0] <= self.img.shape[1] * 2:
					self.patch_sizes.append(patch_size)

			# if no patch could pass the sanity check
			if self.patch_sizes == []:
				min_side = min(self.img.shape[0], self.img.shape[1])
				self.patch_sizes.append((min_side // 3, min_side // 3))

		else:
			self.median_gap = np.median(all_gaps)
			proposed_patch_sizes = (self.contexts * self.median_gap).astype(np.int32)
			proposed_patch_sizes = [(patch_size, patch_size) for patch_size in proposed_patch_sizes]
			self.patch_sizes = []

			# sanity check on the patch sizes
			for patch_size in proposed_patch_sizes:
				if patch_size[1] <= self.img.shape[0] * 2 and patch_size[0] <= self.img.shape[1] * 2:
					self.patch_sizes.append(patch_size)
			
			# if no patch could pass the sanity check
			if self.patch_sizes == []:
				min_side = min(self.img.shape[0], self.img.shape[1])
				self.patch_sizes.append((min_side // 3, min_side // 3))

	

	def process_image(self, img_path):
		self.img_path = img_path

		# reading image
		self.img = cv2.imread(self.img_path)
		if self.img is None:
			return False
		
		if self.img.shape[0] < 256 or self.img.shape[1] < 256:
			self.query_patch_sizes = [(64, 64), (96, 96), (128, 128), (256, 256)]
		else:
			self.query_patch_sizes = [(128, 128), (256, 256), (384, 284), (512, 512)]
		
		# finding the patch sizes
		self.find_best_patch_sizes()


		# sampling the patches
		self.img_tiles = []
		for patch_size in self.patch_sizes:
			self.img_tiles += self.sample_patches(patch_size, patch_size[0] // 3, patch_size[1] // 2)

		# performing inference on all patches using dataloader
		self.infer_patches(infer_bin=True)


		# at this point the appropriate patches have been sampled
		# reprojecting the sampled points on the whole image and forming lines
		self.reproject()


		# reprojecting the heatmap outputs on the whole whole image
		self.reproject_bin()

		self.global_weight_canvas = self.global_weight_canvas * self.global_heat_map 




		# saving the heat map
		heatmap = np.repeat(self.global_heat_map[:, :, None], 3, axis=-1)



		# removing the outliers!
		self.remove_outliers()

		# sorting the scribbles
		scribbles = []
		for i in range(self.n_lines):
			pts_y, pts_x = np.where(self.global_canvas == i + 1)
			ids = np.argsort(pts_x)
			pts_x = pts_x[ids]
			pts_y = pts_y[ids]
			scribble_pts = np.stack((pts_x, pts_y), axis=-1)
			scribbles.append(scribble_pts)
		scribbles = sorted(scribbles, key=lambda scribble: np.mean(scribble[:, 1]))


		new_global_canvas = np.zeros_like(self.global_canvas)
		for i in range(self.n_lines):
			pts_x = scribbles[i][:, 0]
			pts_y = scribbles[i][:, 1]
			new_global_canvas[pts_y, pts_x] = i + 1
		self.global_canvas = new_global_canvas


		# in case there are no predicted lines in the image
		if len(scribbles) == 0:
			return
		

		self.scribbles = scribbles


		# merging based on the reading order
		# based on the assumption that in palm leaf manuscripts lines go all the way from left to the right
		self.merge_based_on_reading_order()



		# preparing masks for seam generation
		all_regions_up = []
		all_regions_down = []
		all_initpoints = []
		all_endpoints = []
		for i in range(self.n_lines):
			scribble_pts = self.scribbles[i]
			upper_pts = (scribble_pts - np.array([0.0, self.median_gap * self.region])).astype(np.int32)
			lower_pts = (scribble_pts + np.array([0.0, self.median_gap * self.region])).astype(np.int32)
			region_up = np.concatenate((upper_pts, np.flipud(scribble_pts)))
			region_down = np.concatenate((scribble_pts, np.flipud(lower_pts)))
			all_regions_up.append(region_up)
			all_regions_down.append(region_down)
			all_initpoints.append(scribble_pts[0])
			all_endpoints.append(scribble_pts[-1])
		
		all_initpoints = np.array(all_initpoints, dtype=np.int32)
		all_endpoints = np.array(all_endpoints, dtype=np.int32)


		# making changes to the global heat map to dilate it and blur it
		kernel_h = int(self.median_gap) // 9
		if kernel_h % 2 == 0:
			kernel_h += 1
		kernel_w = 2 * kernel_h + 1
		kernel_size = (kernel_h, kernel_w)
		self.global_heat_map = cv2.dilate(self.global_heat_map, (kernel_size), iterations=1)
		self.global_heat_map = cv2.GaussianBlur(self.global_heat_map, (3, 3), 3)
		upper_seams = compute_upper_seams(self.global_heat_map, all_regions_up, all_initpoints, all_endpoints)
		lower_seams = compute_lower_seams(self.global_heat_map, all_regions_down, all_initpoints, all_endpoints)


		# writing seams in the xy points format
		upper_seams_xy = [np.array(
						[np.arange(all_initpoints[i][0], all_endpoints[i][0] + 1, dtype=np.int32), upper_seams[all_initpoints[i][0]:all_endpoints[i][0] + 1, i]]
					).T for i in range(self.n_lines)]
		
		lower_seams_xy = [np.array(
						[np.arange(all_initpoints[i][0], all_endpoints[i][0] + 1, dtype=np.int32), lower_seams[all_initpoints[i][0]:all_endpoints[i][0] + 1, i]]
					).T for i in range(self.n_lines)]


		img_ = cv2.cvtColor(self.img, cv2.COLOR_BGR2GRAY).astype(np.uint8)   
		_, otsu_threshold = cv2.threshold(img_, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU) 
		kernel = np.ones((3, 3), dtype=np.uint8)  
		# kernel = np.ones((3, 3)) / 9 
		otsu_threshold = 255 - cv2.dilate((255 - otsu_threshold), kernel, iterations=3) 
		self.global_canvas[otsu_threshold == 255] = 0 
		polygons = []  
		for i in range(self.n_lines): 
			line_pts_y, line_pts_x = np.where(self.global_canvas == i + 1)  
			min_x = np.min(line_pts_x) 
			max_x = np.max(line_pts_x) 
			upper_seam = upper_seams_xy[i] 
			upper_seam = upper_seam[(upper_seam[:, 0] > min_x) & (upper_seam[:, 0] < max_x)] 
			lower_seam = lower_seams_xy[i] 
			lower_seam = lower_seam[(lower_seam[:, 0] > min_x) & (lower_seam[:, 0] < max_x)] 
			polygons.append(np.concatenate([upper_seam, np.flipud(lower_seam)], axis=0)) 
		return scribbles, polygons, self.global_heat_map
	


	def merge_based_on_reading_order(self):
		left_extreme = 100000000
		right_extreme = 0
		for i, scribble in enumerate(self.scribbles):
			left_extreme = min(np.min(scribble[:, 0]), left_extreme)
			right_extreme = max(np.max(scribble[:, 0]), right_extreme)
		extent = right_extreme - left_extreme
		outliers = []
		for i, scribble in enumerate(self.scribbles):
			if np.max(scribble[:, 0]) - np.min(scribble[:, 0]) >= extent * 0.6667:
				continue
			outliers.append(i)
		scr_mat = np.zeros((self.n_lines, self.n_lines), dtype=np.int32)
		merged = []
		for i in range(self.n_lines):
			if i not in outliers or i in merged:
				continue
			for j in range(i + 1, self.n_lines):
				if j not in outliers or j in merged:
					continue
				scr1_pts = self.scribbles[i]
				scr2_pts = self.scribbles[j]
				new_scr = np.concatenate((scr1_pts, scr2_pts), axis=0)
				new_extent = np.max(new_scr[:, 0]) - np.min(new_scr[:, 0])
				if new_extent < 0.667 * extent:
					continue
				scr1_y_pts = self.scribbles[i][:, 1]
				scr2_y_pts = self.scribbles[j][:, 1]
				scr1_mat = np.repeat(scr1_y_pts[None, :], len(scr2_y_pts), 0)
				scr2_mat = np.repeat(scr2_y_pts[:, None], len(scr1_y_pts), 1)
				cost_mat = np.abs(scr1_mat - scr2_mat)
				if cost_mat.size == 0:
					continue
				cost_mat = np.min(cost_mat, axis=1)
				if np.any(cost_mat < self.matching_threshold * self.median_gap):
					scr_mat[i][j] = 1
					merged += [i]
					merged += [j]
					print(f"{i} and {j} are merged!")

		scr_mat = scr_mat + scr_mat.T
		assert np.allclose(scr_mat, scr_mat.T)
		assert np.allclose(np.diag(scr_mat), np.zeros(self.n_lines))


		vis = -np.ones((self.n_lines), dtype=np.int32)


		def dfs(group, first):
			vis[first] = group
			for second in range(self.n_lines):
				if not scr_mat[first][second]:
					continue
				if vis[second] == group:
					continue
				assert vis[second] == -1
				dfs(group, second)
			
		for first in range(self.n_lines):
			if vis[first] == -1:
				dfs(first, first)
			assert vis[first] != -1


		assert not np.any(vis == -1)

		new_global_canvas = np.zeros_like(self.global_canvas)
		n_lines_new = 0
		groups = np.unique(vis)
		for group in groups:
			members = np.where(vis == group)[0]
			for member in members:
				pts_y, pts_x = np.where(self.global_canvas == member + 1)
				new_global_canvas[self.global_canvas == member + 1] = n_lines_new + 1
			n_lines_new += 1
		
		self.global_canvas = new_global_canvas
		self.n_lines = n_lines_new

		new_scribbles = []
		for i in range(self.n_lines):
			pts_y, pts_x = np.where(self.global_canvas == i + 1)
			ids = np.argsort(pts_x)
			pts_x = pts_x[ids]
			pts_y = pts_y[ids]
			new_scribbles.append(np.stack((pts_x, pts_y), axis=-1))
		
		self.scribbles = new_scribbles
