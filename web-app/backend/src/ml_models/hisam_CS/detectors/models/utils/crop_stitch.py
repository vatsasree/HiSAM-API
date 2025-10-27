import cv2 
import numpy as np 
import os 

import collections
from typing import List, Optional, Union
import json
from shapely.geometry import Polygon
import pyclipper

class DisjointSet:
    """
    A disjoint set implementation from HierText
    github.com/tensorflow/models/blob/master/official/projects/unified_detector/utils/utilities.py
    """

    def __init__(self, num_elements: int):
        self._num_elements = num_elements
        self._parent = list(range(num_elements))

    def find(self, item: int) -> int:
        if self._parent[item] == item:
          return item
        else:
          self._parent[item] = self.find(self._parent[item])
          return self._parent[item]

    def union(self, i1: int, i2: int) -> None:
        r1 = self.find(i1)
        r2 = self.find(i2)
        self._parent[r1] = r2

    def to_group(self) -> List[List[int]]:
        """Return the grouping results.

        Returns:
            A list of integer lists. Each list represents the IDs belonging to the
          same group.
        """
        groups = collections.defaultdict(list)
        for i in range(self._num_elements):
          r = self.find(i)
          groups[r].append(i)
        return list(groups.values())

# bbox filtering
def calculate_overlap_percentage(large_box, small_box):

    large_x1, large_y1, large_x2, large_y2 = large_box
    small_x1, small_y1, small_x2, small_y2 = small_box

    overlap_x1 = max(large_x1, small_x1)
    overlap_y1 = max(large_y1, small_y1)
    overlap_x2 = min(large_x2, small_x2)
    overlap_y2 = min(large_y2, small_y2)

    overlap_area = max(0, overlap_x2 - overlap_x1) * max(0, overlap_y2 - overlap_y1)
    large_area = (large_x2 - large_x1) * (large_y2 - large_y1)
    small_area = (small_x2 - small_x1) * (small_y2 - small_y1)

    # overlap_percentage = (overlap_area / large_area) * 100
    overlap_percentage = (overlap_area/small_area)*100
    return overlap_percentage

def is_box_inside(large_box, small_box, threshold_percentage):

    large_x1, large_y1, large_x2, large_y2 = large_box
    small_x1, small_y1, small_x2, small_y2 = small_box

    overlap_percentage = calculate_overlap_percentage(large_box, small_box)
    # print("Overlap:",overlap_percentage)
    if (large_x1 < small_x1 and small_x2 < large_x2 and large_y1 < small_y1 and small_y2 < large_y2):
        return True
    elif (overlap_percentage >= threshold_percentage):
        return True
    else:
        return False

def filter_boxes(boxes, threshold_percentage=90, type='words'):
    """
    Filters out words whose bounding boxes are significantly inside another word's bounding box.
    
    :param words: List of lists where each inner list consists of [x1, y1, x2, y2] for a word.
    :param threshold_percentage: Overlap percentage threshold to consider a word inside another.
    :return: Filtered list of bounding boxes.
    """
    filtered = []
    
    for i, small_box in enumerate(boxes):
        inside = False
        for j, large_box in enumerate(boxes):
            if i != j:  # Avoid comparing a box with itself
                if is_box_inside(large_box, small_box, threshold_percentage):
                    inside = True
                    break
        if not inside:
            filtered.append(small_box)
    
    # return {'words':filtered}
    return {f'{type}':filtered}


def adjust_bbox_coordinates(bbox: List[int], patch_left: int, patch_upper: int) -> List[int]:
    """Adjust bounding box coordinates from patch-relative to original-image-relative."""
    return [
        bbox[0] + patch_left,  # x1
        bbox[1] + patch_upper,  # y1
        bbox[2] + patch_left,  # x2
        bbox[3] + patch_upper,  # y2
    ]

def bbox_intersects(bbox1: List[int], bbox2: List[int]) -> bool:
    """Check if two bounding boxes intersect."""
    return not (
        bbox1[2] < bbox2[0] or  # bbox1 is to the left of bbox2
        bbox1[0] > bbox2[2] or  # bbox1 is to the right of bbox2
        bbox1[3] < bbox2[1] or  # bbox1 is above bbox2
        bbox1[1] > bbox2[3]     # bbox1 is below bbox2
    )
    
def is_bbox1_inside_bbox2(bbox1: List[int], bbox2: List[int]) -> bool:
    """Check if bbox1 is completely inside bbox2."""
    return (
        bbox1[0] >= bbox2[0] and
        bbox1[1] >= bbox2[1] and
        bbox1[2] <= bbox2[2] and
        bbox1[3] <= bbox2[3]
    )

def bbox_union(bbox1: List[int], bbox2: List[int]) -> List[int]:
    """Compute the union of two bounding boxes."""
    return [
        min(bbox1[0], bbox2[0]), 
        min(bbox1[1], bbox2[1]),
        max(bbox1[2], bbox2[2]), 
        max(bbox1[3], bbox2[3])
    ]

def bbox_area(vertices):
    # Assuming vertices are [x_min, y_min, x_max, y_max]
    x_min, y_min, x_max, y_max = vertices
    return max(0, x_max - x_min) * max(0, y_max - y_min)

def bbox_overlap_area(vertices1, vertices2):
    x_min1, y_min1, x_max1, y_max1 = vertices1
    x_min2, y_min2, x_max2, y_max2 = vertices2
    
    # Calculate the intersection coordinates
    x_min_inter = max(x_min1, x_min2)
    y_min_inter = max(y_min1, y_min2)
    x_max_inter = min(x_max1, x_max2)
    y_max_inter = min(y_max1, y_max2)
    
    # Calculate intersection area
    inter_width = max(0, x_max_inter - x_min_inter)
    inter_height = max(0, y_max_inter - y_min_inter)
    return inter_width * inter_height

# changed the function to avoid errors 
def unclip(p, unclip_ratio=2.0):
    poly = Polygon(p)
    if poly.length == 0:
        return np.array([p])
    distance = poly.area * unclip_ratio / poly.length
    offset = pyclipper.PyclipperOffset()
    offset.AddPath(p, pyclipper.JT_ROUND, pyclipper.ET_CLOSEDPOLYGON)
    expanded = offset.Execute(distance)
    
    if not expanded:
        return np.array([p])
    
    expanded = [np.array(exp) for exp in expanded]
    
    if not expanded:
        return np.array([p])
    
    return np.array(expanded)


def get_overlap_region_from_metadata(metadata):
    """Get the overlap region for a specific image."""
    patches = metadata["patches"]
    # patch_1_coordinates = patches[0]["left"], patches[0]["upper"], patches[0]["right"], patches[0]["lower"]
    patch_2_coordinates = patches[1]["left"], patches[1]["upper"], patches[1]["right"], patches[1]["lower"]
    patch_3_coordinates = patches[2]["left"], patches[2]["upper"], patches[2]["right"], patches[2]["lower"]
    # patch_4_coordinates = patches[3]["left"], patches[3]["upper"], patches[3]["right"], patches[3]["lower"]
    
    vertical_overlap_coordinates = patch_2_coordinates[0], patch_2_coordinates[1], patch_3_coordinates[2], patch_3_coordinates[3]
    horizontal_overlap_coordinates = patch_3_coordinates[0], patch_3_coordinates[1], patch_2_coordinates[2], patch_2_coordinates[3]
    
    # print(f"Vertical overlap coordinates: {vertical_overlap_coordinates}")
    # print(f"Horizontal overlap coordinates: {horizontal_overlap_coordinates}")
    
    # expand the overlap region by expand_factor(ef) pixels
    ef = 10
    vertical_overlap_coordinates = [vertical_overlap_coordinates[0] - ef, vertical_overlap_coordinates[1], vertical_overlap_coordinates[2] + ef, vertical_overlap_coordinates[3]]
    horizontal_overlap_coordinates = [horizontal_overlap_coordinates[0], horizontal_overlap_coordinates[1] - ef, horizontal_overlap_coordinates[2], horizontal_overlap_coordinates[3] + ef]    
    return vertical_overlap_coordinates, horizontal_overlap_coordinates

def get_non_overlapping_regions(vertical_overlap_coordinates, horizontal_overlap_coordinates):
    """Get the non-overlapping regions from the overlap region."""
    patch_0_coordinates = [0, 0, vertical_overlap_coordinates[0], horizontal_overlap_coordinates[1]]
    patch_1_coordinates = [vertical_overlap_coordinates[2], 0, horizontal_overlap_coordinates[2], horizontal_overlap_coordinates[1]]
    patch_2_coordinates = [0, horizontal_overlap_coordinates[3], vertical_overlap_coordinates[0], vertical_overlap_coordinates[3]]
    patch_3_coordinates = [vertical_overlap_coordinates[2], horizontal_overlap_coordinates[3], horizontal_overlap_coordinates[2], vertical_overlap_coordinates[3]]
    
    return patch_0_coordinates, patch_1_coordinates, patch_2_coordinates, patch_3_coordinates

def merge_text_detections_for_region(region_detections):
    """ 
    This function merges the text detections for a specific region.
    """
    merged_text_detections = []
    
    while region_detections:
        
        merged = False
        current_detection = region_detections.pop(0)
        for i, merged_detection in enumerate(merged_text_detections):
            if bbox_intersects(merged_detection, current_detection):
                overlap_area = bbox_overlap_area(merged_detection, current_detection)
                # merged_word_area = bbox_area(merged_detection)
                union_area = bbox_area(merged_detection) + bbox_area(current_detection) - overlap_area
                # can change the threshold here
                # print(overlap_area/union_area)
                if overlap_area / union_area > 0.1:
                # print(overlap_area/merged_word_area)
                # if overlap_area / merged_word_area > 0.2:
                    merged_text_detections[i] = bbox_union(merged_detection, current_detection)
                    merged = True
                    break
        if not merged:
            merged_text_detections.append(current_detection)
        
    return merged_text_detections

def merge_text_detections(original_text_detections, patch_detections, metadata):
    """
    original_text_detections: List of text detections from the original document
    patch_detections: List of lists of text detections from the patches
    metadata: Metadata of the image and patches
    
    Merge overlapping text bounding boxes from patches and the original document.
    Text detections can be words, lines, or paragraphs. 
    Logic to merge remains the same:
    1. Deal with non overlapping regions first - these are those parts of the document which do not overlap with any patch
       Here we need to merge the text detections from the original document with the 
       text detections from the non-overlapping regions only from the corresponding patch
    2. Deal with overlapping regions next - these are those parts of the document which overlap with one or more patches 
       Here we need to merge the text detections from the original document with the
       text detections from the overlapping regions from all the patches
    """
    
    final_merged_text_detections = [] # to be returned
    
    adjusted_patch_detections = []
    
    # firstly adjust all the patch detections to the original image coordinates
    for patch_index, patch_detections in enumerate(patch_detections):
        patch_left = metadata["patches"][patch_index]["left"]
        patch_upper = metadata["patches"][patch_index]["upper"]
        adjusted_patch_detections.append([
            adjust_bbox_coordinates(bbox, patch_left, patch_upper) for bbox in patch_detections
        ])
    
    # Get the overlap region
    vertical_overlap_coordinates, horizontal_overlap_coordinates = get_overlap_region_from_metadata(metadata)
    
    # Get the non-overlapping regions
    patch_0_coordinates, patch_1_coordinates, patch_2_coordinates, patch_3_coordinates = get_non_overlapping_regions(vertical_overlap_coordinates, horizontal_overlap_coordinates)
    
    # the merging will be done in 5 regions:
    # 1. tope left region - patch 0 coordinates (which does not overlap with any patch)
    # 2. top right region - patch 1 coordinates (which does not overlap with any patch)
    # 3. bottom left region - patch 2 coordinates (which does not overlap with any patch)
    # 4. bottom right region - patch 3 coordinates (which does not overlap with any patch)
    # 5. overlap region - vertical_overlap_coordinates, horizontal_overlap_coordinates (which overlaps with all patches) 
    # The overlap region is in a plus shape 
    
    # firstly segregate the text detections from each patch into the 5 regions
    region_0_detections = []
    region_1_detections = []
    region_2_detections = []
    region_3_detections = []
    overlap_detections = []
    
    for patch_index, patch_detections in enumerate(adjusted_patch_detections):
        for bbox in patch_detections:
            if is_bbox1_inside_bbox2(bbox, patch_0_coordinates):
                region_0_detections.append(bbox)
            elif is_bbox1_inside_bbox2(bbox, patch_1_coordinates):
                region_1_detections.append(bbox)
            elif is_bbox1_inside_bbox2(bbox, patch_2_coordinates):
                region_2_detections.append(bbox)
            elif is_bbox1_inside_bbox2(bbox, patch_3_coordinates):
                region_3_detections.append(bbox)
            else:
                overlap_detections.append(bbox)
                
    # now segregate the text detections from the original document into the 5 regions
    for bbox in original_text_detections:
        # print("og bbox: ", bbox)
        if is_bbox1_inside_bbox2(bbox, patch_0_coordinates):
            region_0_detections.append(bbox)
        elif is_bbox1_inside_bbox2(bbox, patch_1_coordinates):
            region_1_detections.append(bbox)
        elif is_bbox1_inside_bbox2(bbox, patch_2_coordinates):
            region_2_detections.append(bbox)
        elif is_bbox1_inside_bbox2(bbox, patch_3_coordinates):
            region_3_detections.append(bbox)
        else:
            overlap_detections.append(bbox)
            
    # merge the text detections from the 5 regions separately
    merged_region_0_detections = merge_text_detections_for_region(region_0_detections)
    merged_region_1_detections = merge_text_detections_for_region(region_1_detections)
    merged_region_2_detections = merge_text_detections_for_region(region_2_detections)
    merged_region_3_detections = merge_text_detections_for_region(region_3_detections)
    merged_overlap_detections = merge_text_detections_for_region(overlap_detections)
    
    # combine the results from all the regions
    final_merged_text_detections = merged_region_0_detections + merged_region_1_detections + merged_region_2_detections + merged_region_3_detections + merged_overlap_detections
    
    return final_merged_text_detections


def generate_patches(image_path, image_name: str, m: int, n: int, overlap_percentage: int):
    """Divides the image into overlapping patches and returns metadata."""
    
    # Load the image using OpenCV
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"Image at path {image_path} could not be loaded.")
    
    height, width, channels = image.shape
    
    # Calculate patch size with overlap
    patch_width = (width + (m - 1) * (100 - overlap_percentage) * (width // m) / 100) // m
    patch_height = (height + (n - 1) * (100 - overlap_percentage) * (height // n) / 100) // n

    # Calculate overlap in pixels
    overlap_x = int(patch_width * (overlap_percentage / 100))
    overlap_y = int(patch_height * (overlap_percentage / 100))

    # Adjust patch width and height to ensure full coverage
    patch_width = int((width + (m - 1) * overlap_x) / m)
    patch_height = int((height + (n - 1) * overlap_y) / n)

    # Initialize metadata
    metadata = {
        "original_width": width,
        "original_height": height,
        "n": n,
        "m": m,
        "overlap_percentage": overlap_percentage,
        "patches": []
    }

    patches = []  # List to store image patches

    # Iterate over the grid
    for i in range(n):
        for j in range(m):
            # Calculate the coordinates for the patch
            left = j * (patch_width - overlap_x)
            upper = i * (patch_height - overlap_y)
            right = left + patch_width
            lower = upper + patch_height
            
            # Ensure the last patch covers the remaining pixels
            if j == m - 1:
                right = width
            if i == n - 1:
                lower = height

            # Crop the patch
            patch = image[upper:lower, left:right]

            # Store patch metadata
            metadata["patches"].append({
                "patch_index": (i, j),
                "left": left,
                "upper": upper,
                "right": right,
                "lower": lower,
                "overlap_x": overlap_x,
                "overlap_y": overlap_y
            })

            patches.append(patch)

    # print(f"Generated {len(patches)} patches for image {image_name}")
    return patches, metadata


# def get_patch_level_words_lines_paras(results, layout_thresh, dims):
#     # results is a dictionary with keys as 'original', 'patch_0', 'patch_1', 'patch_2', 'patch_3'
#     # iterate over each key and get the words, lines and paragraphs
    
#     img_h, img_w = dims

#     words_lines_paras = {}
#     for key, result in results.items():
#         # all of these are lists of vertices - each vertex is a list of 4 integers
#         words = []
#         polygons = []
#         line_polygons = []
#         lines = []
#         paragraphs = []
        
#         if result['masks'] is not None:
#             masks = (result['masks'][:, 0, :, :]).astype(np.uint8)
#             line_indices = []
#             for index, mask in enumerate(masks):
#                 temp_line = []   
#                 temp_line_polygons = []
#                 contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
#                 for cont in contours:
#                     epsilon = 0.002 * cv2.arcLength(cont, True)
#                     approx = cv2.approxPolyDP(cont, epsilon, True)
#                     points = approx.reshape((-1, 2))
#                     if points.shape[0] < 4:
#                         continue
#                     try:
#                         pts = unclip(points)
#                     except:
#                         continue
                    
#                     if len(pts) != 1:
#                         continue
#                     pts = pts[0].astype(np.int32)
#                     if Polygon(pts).area < 32:
#                         continue
#                     pts[:, 0] = np.clip(pts[:, 0], 0, img_w)
#                     pts[:, 1] = np.clip(pts[:, 1], 0, img_h)
#                     cnt_list = pts.tolist()
#                     # print('cnt_list', cnt_list)
#                     xmin = min(v[0] for v in cnt_list)
#                     ymin = min(v[1] for v in cnt_list)
#                     xmax = max(v[0] for v in cnt_list)
#                     ymax = max(v[1] for v in cnt_list)

#                     word = [xmin, ymin, xmax, ymax]                   
#                     words.append(word)
#                     polygons.append(cnt_list)
#                     temp_line.append(word)
#                     temp_line_polygons.append(np.array(cnt_list))
#                 if temp_line:
#                     # find the coordinate of the line (bounding box)
#                     x_min = min([word[0] for word in temp_line])
#                     y_min = min([word[1] for word in temp_line])
#                     x_max = max([word[2] for word in temp_line])
#                     y_max = max([word[3] for word in temp_line])
#                     line_coords = [x_min, y_min, x_max, y_max]
#                     lines.append(line_coords)
#                     line_indices.append(index)

#                     all_points = np.concatenate(temp_line_polygons)
#                     hull = cv2.convexHull(all_points)
#                     hull = hull.reshape(-1,2).tolist()

#                     line_polygons.append(hull)
                    
#             # now we need to group the lines into paragraphs
            
#             line_grouping = DisjointSet(len(line_indices))
#             affinity = result['affinity'][line_indices][:, line_indices]
#             for i1, i2 in zip(*np.where(affinity > layout_thresh)):
#                 line_grouping.union(i1, i2)
#             line_groups = line_grouping.to_group()
#             for line_group in line_groups:
#                 paragraph = []
#                 for line_index in line_group:
#                     paragraph.append(lines[line_index])
#                 if paragraph:
#                     x_min = min([line[0] for line in paragraph])
#                     y_min = min([line[1] for line in paragraph])
#                     x_max = max([line[2] for line in paragraph])
#                     y_max = max([line[3] for line in paragraph])
#                     paragraph_coords = [x_min, y_min, x_max, y_max]
#                     paragraphs.append(paragraph_coords)           
#         # for now we are not considering lines and paragraphs
#         words_lines_paras[key] = {
#             'polygon': polygons,
#             'l_polygons': line_polygons,
#             'words': words,
#             'lines': lines,
#             'paragraphs': paragraphs
#         }

#     return words_lines_paras


# def combine_text_detections(words_lines_paras, metadata, img_id, output_directory, flag_for_cutting_stitching=True):
#     """ 
#     This function is a helper function to combine the text detections from all patches.
#     It will call the merge_text_detections function for words, lines and paragraphs separately.
#     """

#     original_words = words_lines_paras['original']['words']
#     original_lines = words_lines_paras['original']['lines']
#     original_paragraphs = words_lines_paras['original']['paragraphs']
#     polygons = words_lines_paras['original']['polygon']
#     line_polygons = words_lines_paras['original']['l_polygons']
    
#     if flag_for_cutting_stitching:
        
#         patch_words = [words_lines_paras[f'patch_{i}']['words'] for i in range(4)]
#         patch_lines = [words_lines_paras[f'patch_{i}']['lines'] for i in range(4)]
#         patch_paragraphs = [words_lines_paras[f'patch_{i}']['paragraphs'] for i in range(4)]
        
#         # merge words
#         combined_words = merge_text_detections(original_words, patch_words, metadata)
#         combined_lines = merge_text_detections(original_lines, patch_lines, metadata)
#         combined_paragraphs = merge_text_detections(original_paragraphs, patch_paragraphs, metadata)

#         filtered_words = filter_boxes(combined_words)
#         filtered_lines = filter_boxes(combined_lines, type='lines')
#         filtered_paras = filter_boxes(combined_paragraphs, type='paras')

#         combined_words = filtered_words['words']
#         combined_lines = filtered_lines['lines']
#         combined_paras = filtered_paras['paras']
        
#     else:
#         combined_words = original_words
#         combined_lines = original_lines
#         combined_paragraphs = original_paragraphs
#         polygons = polygons
#     # save the results in the eval_out_file
#     result = {
#         'image_id': img_id,
#         'polygon': polygons,
#         'l_polygon': line_polygons,
#         'words': combined_words,
#         'lines': combined_lines,
#         'paragraphs': combined_paragraphs
#     }
#below functions added to get paralevel polygons
def get_patch_level_words_lines_paras(results, layout_thresh, dims):
    # results is a dictionary with keys as 'original', 'patch_0', 'patch_1', ...
    img_h, img_w = dims

    words_lines_paras = {}
    for key, result in results.items():
        words = []
        polygons = []         # word polygons
        line_polygons = []    # line polygons
        paragraph_polygons = []  # NEW: paragraph polygons
        lines = []
        paragraphs = []
        
        if result['masks'] is not None:
            masks = (result['masks'][:, 0, :, :]).astype(np.uint8)
            line_indices = []
            for index, mask in enumerate(masks):
                temp_line = []   
                temp_line_polygons = []
                contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
                for cont in contours:
                    epsilon = 0.002 * cv2.arcLength(cont, True)
                    approx = cv2.approxPolyDP(cont, epsilon, True)
                    points = approx.reshape((-1, 2))
                    if points.shape[0] < 4:
                        continue
                    try:
                        pts = unclip(points)
                    except:
                        continue
                    
                    if len(pts) != 1:
                        continue
                    pts = pts[0].astype(np.int32)
                    if Polygon(pts).area < 32:
                        continue
                    pts[:, 0] = np.clip(pts[:, 0], 0, img_w)
                    pts[:, 1] = np.clip(pts[:, 1], 0, img_h)
                    cnt_list = pts.tolist()

                    xmin = min(v[0] for v in cnt_list)
                    ymin = min(v[1] for v in cnt_list)
                    xmax = max(v[0] for v in cnt_list)
                    ymax = max(v[1] for v in cnt_list)

                    word = [xmin, ymin, xmax, ymax]                   
                    words.append(word)
                    polygons.append(cnt_list)
                    temp_line.append(word)
                    temp_line_polygons.append(np.array(cnt_list))
                if temp_line:
                    # bounding box for line
                    x_min = min([word[0] for word in temp_line])
                    y_min = min([word[1] for word in temp_line])
                    x_max = max([word[2] for word in temp_line])
                    y_max = max([word[3] for word in temp_line])
                    line_coords = [x_min, y_min, x_max, y_max]
                    lines.append(line_coords)
                    line_indices.append(index)

                    # convex hull for line polygon
                    all_points = np.concatenate(temp_line_polygons)
                    hull = cv2.convexHull(all_points)
                    hull = hull.reshape(-1,2).tolist()
                    line_polygons.append(hull)
                    
            # group lines into paragraphs
            line_grouping = DisjointSet(len(line_indices))
            affinity = result['affinity'][line_indices][:, line_indices]
            for i1, i2 in zip(*np.where(affinity > layout_thresh)):
                line_grouping.union(i1, i2)
            line_groups = line_grouping.to_group()

            for line_group in line_groups:
                paragraph = []
                paragraph_line_polygons = []
                for line_index in line_group:
                    paragraph.append(lines[line_index])
                    paragraph_line_polygons.append(np.array(line_polygons[line_index]))

                if paragraph:
                    # paragraph bounding box
                    x_min = min([line[0] for line in paragraph])
                    y_min = min([line[1] for line in paragraph])
                    x_max = max([line[2] for line in paragraph])
                    y_max = max([line[3] for line in paragraph])
                    paragraph_coords = [x_min, y_min, x_max, y_max]
                    paragraphs.append(paragraph_coords)

                    # convex hull for paragraph polygon
                    all_points = np.concatenate(paragraph_line_polygons)
                    hull = cv2.convexHull(all_points)
                    hull = hull.reshape(-1,2).tolist()
                    paragraph_polygons.append(hull)
                    
        words_lines_paras[key] = {
            'polygon': polygons,
            'l_polygons': line_polygons,
            'p_polygons': paragraph_polygons,   # NEW
            'words': words,
            'lines': lines,
            'paragraphs': paragraphs
        }

    return words_lines_paras


def combine_text_detections(words_lines_paras, metadata, img_id, output_directory, flag_for_cutting_stitching=True):
    """ 
    Combine text detections from all patches.
    """
    original_words = words_lines_paras['original']['words']
    original_lines = words_lines_paras['original']['lines']
    original_paragraphs = words_lines_paras['original']['paragraphs']
    polygons = words_lines_paras['original']['polygon']
    line_polygons = words_lines_paras['original']['l_polygons']
    paragraph_polygons = words_lines_paras['original']['p_polygons']  # NEW
    
    if flag_for_cutting_stitching:
        patch_words = [words_lines_paras[f'patch_{i}']['words'] for i in range(4)]
        patch_lines = [words_lines_paras[f'patch_{i}']['lines'] for i in range(4)]
        patch_paragraphs = [words_lines_paras[f'patch_{i}']['paragraphs'] for i in range(4)]
        
        combined_words = merge_text_detections(original_words, patch_words, metadata)
        combined_lines = merge_text_detections(original_lines, patch_lines, metadata)
        combined_paragraphs = merge_text_detections(original_paragraphs, patch_paragraphs, metadata)

        filtered_words = filter_boxes(combined_words)
        filtered_lines = filter_boxes(combined_lines, type='lines')
        filtered_paras = filter_boxes(combined_paragraphs, type='paras')

        combined_words = filtered_words['words']
        combined_lines = filtered_lines['lines']
        combined_paragraphs = filtered_paras['paras']
        
    else:
        combined_words = original_words
        combined_lines = original_lines
        combined_paragraphs = original_paragraphs

    # final result
    result = {
        'image_id': img_id,
        'polygon': polygons,
        'l_polygon': line_polygons,
        'p_polygon': paragraph_polygons,   # NEW
        'words': combined_words,
        'lines': combined_lines,
        'paragraphs': combined_paragraphs
    }

    # save
    # out_file = os.path.join(output_directory, f"{img_id}.jsonl")
    # with open(out_file, "w") as f:
    #     f.write(json.dumps(result) + "\n")
    
    # TODO: make modifications to make visualisations possible, currently not included with refactored code
    # if args.eval:
    #     if args.visualise_detection:
    #         # create visdir if it does not exist
    #         os.makedirs(args.visualise_detection, exist_ok=True)
            
    #         visualise_words_path = os.path.join(args.visualise_detection, img_id+'_words.png')
    #         draw_text_detections(image, combined_words, visualise_words_path)  
            
    #         visualise_lines_path = os.path.join(args.visualise_detection, img_id+'_lines.png')
    #         draw_text_detections(image, combined_lines, visualise_lines_path)
            
    #         visualise_paragraphs_path = os.path.join(args.visualise_detection, img_id+'_paragraphs.png')
    #         draw_text_detections(image, combined_paragraphs, visualise_paragraphs_path)
            
    
    out_file = os.path.join(output_directory, f"{img_id}.jsonl")
    with open(out_file, 'w', encoding='utf-8') as fw:
        json.dump(result, fw)

    return result