import os
import cv2
import numpy as np
import pyclipper
import random
import torch
import skimage
from shapely.geometry import Polygon
from PIL import Image
import matplotlib.pyplot as plt
from pdf2image import convert_from_path
import time
import json

def process_pdf(pdf_path):
    images_directory = pdf_path.replace(".pdf", "")
    # print("pdf", images_directory)
    os.makedirs(images_directory, exist_ok=True)
    images = convert_from_path(pdf_path)
    for i, image in enumerate(images):
        image_path = os.path.join(images_directory, f"image_{i}.jpg")
        image.save(image_path, "JPEG")

    output_directory = os.path.join(images_directory, "results")
    os.makedirs(output_directory, exist_ok=True)

def show_points(coords, ax, marker_size=40):
    ax.scatter(coords[:, 0], coords[:, 1],
               color='green',
               marker='*',
               s=marker_size,
               edgecolor='white',
               linewidth=0.25)
    
def json_writer(json_queue, output_file):
    """Writes JSON objects to a JSONL file effieciently"""
    with open(output_file, "w", encoding="utf-8") as f:
        while True:
            json_obj = json_queue.get()
            if json_obj is None:
                break # Stop when None is received
            f.write(json.dumps(json_obj) + "\n")

def show_mask(mask, ax, random_color=False, color=None):
    if random_color:
        color = np.concatenate([np.random.random(3), np.array([0.5])], axis=0)
    else:
        color = color if color is not None else np.array([30/255, 144/255, 255/255, 0.5])
    h, w = mask.shape[-2:]
    mask_image = mask.reshape(h, w, 1) * color.reshape(1, 1, -1)
    ax.imshow(mask_image)


def show_hi_masks(masks, filename, image):
    plt.figure(figsize=(15, 15), dpi=200)
    plt.imshow(image)
    for hi_mask in masks:
        hi_mask = hi_mask[0]
        show_mask(hi_mask, plt.gca(), random_color=True)
    plt.axis('off')
    plt.savefig(filename, bbox_inches='tight')
    plt.close()


def save_binary_mask(mask: np.array, filename):
    """
    Saves a single-channel binary mask (0 or 1) as an 8-bit image (0 or 255).
    """
    if len(mask.shape) == 3:
        assert mask.shape[0] == 1, "Expected shape (1, H, W) for the mask."
        mask = mask[0].astype(np.uint8)*255
    elif len(mask.shape) == 2:
        mask = mask.astype(np.uint8)*255
    else:
        raise NotImplementedError("Mask shape not recognized.")
    mask_image = Image.fromarray(mask)
    mask_image.save(filename)


def unclip(p, unclip_ratio=2.0):
    """
    Expands the polygon p by a certain ratio.
    """
    poly = Polygon(p)
    distance = poly.area * unclip_ratio / poly.length
    offset = pyclipper.PyclipperOffset()
    offset.AddPath(p, pyclipper.JT_ROUND, pyclipper.ET_CLOSEDPOLYGON)
    expanded = np.array(offset.Execute(distance))
    return expanded


def set_random_seeds(seed=42):
    """
    Sets random seeds for reproducibility.
    """
    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)
    torch.cuda.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)