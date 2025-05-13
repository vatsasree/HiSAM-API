import os
import cv2
import argparse
import numpy as np
import xml.etree.ElementTree as ET
from pdf2image import convert_from_path
from shutil import copyfile, rmtree


# TEI XML namespace
NS = {'tei': 'http://www.tei-c.org/ns/1.0'}


def process_documents(docs_dir, output_dir):
    documents = [os.path.join(docs_dir, file) for file in os.listdir(docs_dir)]
    temp_dir = os.path.join(output_dir, 'tmp_folder')
    os.makedirs(temp_dir, exist_ok=True)
    for document in documents:
        if document.endswith('.pdf'):
            doc_images = convert_from_path(document, use_cropbox=True)
            for i, image in enumerate(doc_images):
                temp_image_name = document.split('/')[-1].replace('.pdf', '') + f'_page_{i+1}.jpg'
                temp_image_name = os.path.join(temp_dir, temp_image_name)
                image.save(temp_image_name)
        else:
            copyfile(document, os.path.join(temp_dir, document.split('/')[-1]))
    return temp_dir
    
def run(docs_dir, xml_path, output_dir):
    temp_dir = process_documents(docs_dir, output_dir)
    tree = ET.parse(xml_path)
    root = tree.getroot()
    
    facsimile = root.find('tei:facsimile', NS)
    if facsimile is None:
        print("No <facsimile> tag found.")
        return
    
    for surface in facsimile.findall('tei:surface', NS):
        surface_id = surface.get('{http://www.w3.org/XML/1998/namespace}id')
        graphic = surface.find('tei:graphic', NS)
        if graphic is None:
            continue
        image_filename = graphic.get('url')
        image_path = os.path.join(temp_dir, image_filename)
        if os.path.exists(image_path):
            image = cv2.imread(image_path)

            output_path = os.path.join(output_dir, image_filename)
            for path in surface.findall('tei:path', NS):
                points_str = path.get('points')
                if not points_str:
                    continue
                points = [tuple(map(int, pt.split(','))) for pt in points_str.split()]
                pts = np.array(points)
                image = cv2.polylines(image, [pts], isClosed=False, color=(0, 255, 0), thickness=2)
            cv2.imwrite(output_path, image)
        else:
            print('Skipping {image_filename}. ')
    
    rmtree(temp_dir)
    


            

    

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Overlay scribbles on images using TEI XML annotations.")
    parser.add_argument("--xml_path", required=True, help="Path to the TEI XML file")
    parser.add_argument("--docs_dir", required=True, help="Directory where the original images are stored")
    parser.add_argument("--output_dir", required=True, help="Directory to save images with overlays")

    args = parser.parse_args()
    run(args.docs_dir, args.xml_path, args.output_dir)
    

"""
python overlay_scribbles_from_tei.py --docs_dir /data3/amalj/temp_dir/sample_docs/ --xml_path /path/to/file.xml --output_dir /path/to/
"""