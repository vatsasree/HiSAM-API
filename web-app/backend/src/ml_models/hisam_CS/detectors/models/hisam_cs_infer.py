import os
import cv2
import json
import glob
import numpy as np
from tqdm import tqdm
from PIL import Image
# from pdf2image import convert_from_path
# from shapely.geometry import Polygon

# Convert dict config -> Namespace so model_registry code sees args.checkpoint, etc.
from argparse import Namespace
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
print('SUCESSS imports!')
# Absolute imports to Hi-SAM
from hi_sam.modeling.build import model_registry
from hi_sam.modeling.auto_mask_generator import AutoMaskGenerator
from utils.crop_stitch import *
# Utilities
from utils.preprocess import (
    unclip,
    set_random_seeds,
    save_binary_mask,
    show_points,
    show_mask,
    show_hi_masks
)
from utils import utilities
from abc import ABC, abstractmethod

class Detector(ABC):

    @abstractmethod
    def preprocess(self):
        pass
    
    @abstractmethod
    def detect(self):
        pass

class HiSAMDetector(Detector):
    """
    Detector subclass using Hi-SAM for word-level bounding boxes.
    """

    def __init__(self, config):
        """
        config: A dictionary containing the relevant parameters, e.g.:
                {
                  "model_type": "vit_l",
                  "checkpoint": "path/to/hi_sam_l.pth",
                  "device": "cuda:8",
                  "total_points": 1500,
                  "batch_points": 100,
                  "layout_thresh": 0.5,
                  "seed": 42,
                  "use_fgmask": False,
                  "eval": True,
                  "eval_out_file": "./results_jsonl",
                  "existing_fgmask_input": "./datasets/HierText/val_fgmask/",
                  "output": "./demo_output"
                }
        """
        super().__init__()
        # Convert dict -> argparse.Namespace so the builder code can do args.checkpoint, etc.
        
        self.args = Namespace(**config)

        set_random_seeds(self.args.seed)

        # Access to core arguments
        self.detector_name = "hi_sam"
        self.model_type = self.args.model_type
        self.device = self.args.device
        self.total_points = self.args.total_points
        self.batch_points = self.args.batch_points
        self.layout_thresh = self.args.layout_thresh
        self.use_fgmask = self.args.use_fgmask
        self.eval_mode = self.args.eval
        self.eval_out_file = self.args.eval_out_file
        self.existing_fgmask_input = self.args.existing_fgmask_input
        self.output_dir = self.args.output

        # Build the HiSAM model
        print("Initializing Hi-SAM model...")
        # Pass the Namespace object to model_registry
        self.hisam = model_registry[self.model_type](self.args)
        self.hisam.eval()
        self.hisam.to(self.device)
        print("Model loaded.")

        # Decide if we should use efficient Hi-SAM
        self.efficient_hisam = (self.model_type in ["vit_s", "vit_t"])

        # Create the AutoMaskGenerator instance
        self.amg = AutoMaskGenerator(self.hisam, efficient_hisam=self.efficient_hisam)

    def preprocess(self, input):
        pass

    def detect(self, input_image_path=None):
        """
        Main detection workflow:
        1) Take a single image path as input.
        2) Run the Hi-SAM predictor on the image.
        3) Output word-level bounding boxes to JSONL (paragraphs→lines→words).
        """
        if input_image_path is None or not os.path.exists(input_image_path):
            raise ValueError("Please provide a valid path for the input image.")

        # Extract image name and directory
        img_id = os.path.splitext(os.path.basename(input_image_path))[0]
        images_directory = os.path.dirname(input_image_path)

        # Output directory
        output_directory = os.path.join(images_directory, "results")
        os.makedirs(output_directory, exist_ok=True)

        # Skip if already processed
        output_path = os.path.join(output_directory, f"{img_id}.jsonl")
        if os.path.exists(output_path):
            print(f"Skipping {img_id}, already processed.")
            return

        # Load image
        image_cv2 = cv2.imread(input_image_path)
        if image_cv2 is None:
            print("Could not read file:", input_image_path)
            return

        image_cv2 = cv2.cvtColor(image_cv2, cv2.COLOR_BGR2RGB)
        img_h, img_w = image_cv2.shape[:2]
        dims = (img_h, img_w)

        # Generate patches
        patches, metadata = generate_patches(input_image_path, img_id, 2, 2, 10)
        results = {}

        # If using an existing foreground mask
        if self.use_fgmask:
            fgmask_path = os.path.join(self.existing_fgmask_input, f"{img_id}.png")
            if os.path.exists(fgmask_path):
                fgmask = utilities.skimage.io.imread(fgmask_path)
                self.amg.set_fgmask(fgmask)

        # Full image inference
        self.amg.set_image(image_cv2)
        masks, scores, affinity = self.amg.predict(
            from_low_res=False,
            fg_points_num=self.total_points,
            batch_points_num=self.batch_points,
            score_thresh=0.5,
            nms_thresh=0.5,
        )
        results['original'] = {
            'masks': masks,
            'scores': scores,
            'affinity': affinity
        }

        # Patch-level inference
        for patch_index, patch in enumerate(patches):
            self.amg.set_image(patch)
            masks, scores, affinity = self.amg.predict(
                from_low_res=False,
                fg_points_num=self.total_points,
                batch_points_num=self.batch_points,
                score_thresh=0.5,
                nms_thresh=0.5,
            )
            results[f'patch_{patch_index}'] = {
                'masks': masks,
                'scores': scores,
                'affinity': affinity
            }

        # Post-processing
        if all([result['masks'] is None for result in results.values()]):
            final_result = {
                'image_id': img_id,
                'polygons': [],
                'l_polygons': [],
                'p_polygons': [],
                'words': [],
                'lines': [],
                'paragraphs': []
            }
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(json.dumps(final_result) + "\n")
            print(f"No predictions for {img_id}, empty JSONL written.")
        else:
            words_lines_paras = get_patch_level_words_lines_paras(results, self.layout_thresh, dims)
            result = combine_text_detections(words_lines_paras, metadata, img_id, output_directory, flag_for_cutting_stitching=True)

        print(f"Detection completed for {input_image_path}.")
        
        return result