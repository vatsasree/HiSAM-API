import os
import cv2
import argparse
import numpy as np
import xml.etree.ElementTree as ET
from pdf2image import convert_from_path
from shutil import copyfile, rmtree


# TEI XML namespace for easier access to TEI tags
NS = {'tei': 'http://www.tei-c.org/ns/1.0'}

def process_documents(docs_dir, output_dir):
    """
    Converts PDF documents to images and copies other documents into a temporary folder.
    Returns the path of the temporary directory where the documents are stored.
    """
    # Get list of all files in the specified documents directory
    documents = [os.path.join(docs_dir, file) for file in os.listdir(docs_dir)]
    
    # Temporary directory to store images and documents
    temp_dir = os.path.join(output_dir, 'tmp_folder')
    os.makedirs(temp_dir, exist_ok=True)  # Create temp directory if it doesn't exist
    
    # Process each document in the directory
    for document in documents:
        if document.endswith('.pdf'):  # If the document is a PDF
            # Convert each PDF page into an image
            doc_images = convert_from_path(document, use_cropbox=True)
            for i, image in enumerate(doc_images):
                # Save each page as an image (JPG)
                temp_image_name = document.split('/')[-1].replace('.pdf', '') + f'_page_{i+1}.jpg'
                temp_image_name = os.path.join(temp_dir, temp_image_name)
                image.save(temp_image_name)
        else:  # If it's not a PDF (assume image or other format)
            # Directly copy the document to the temp folder
            copyfile(document, os.path.join(temp_dir, document.split('/')[-1]))
    
    # Return the path to the temporary folder where files are stored
    return temp_dir
    
def run(docs_dir, xml_path, output_dir):
    """
    Main function that processes documents, parses the TEI XML, and overlays polygons on images.
    It saves the modified images in the output directory.
    """
    # Process documents and get the temporary folder with images
    temp_dir = process_documents(docs_dir, output_dir)
    
    # Parse the TEI XML file
    tree = ET.parse(xml_path)
    root = tree.getroot()
    
    # Find the <facsimile> tag in the XML (contains image references and annotations)
    facsimile = root.find('tei:facsimile', NS)
    if facsimile is None:
        print("No <facsimile> tag found.")
        return  # If no <facsimile> tag, exit the function
    
    # Iterate over each <surface> in the <facsimile> section
    for surface in facsimile.findall('tei:surface', NS):
        # Get the surface ID (for debugging, optional)
        surface_id = surface.get('{http://www.w3.org/XML/1998/namespace}id')
        
        # Find the <graphic> tag which contains the image URL
        graphic = surface.find('tei:graphic', NS)
        if graphic is None:
            continue  # Skip if no <graphic> tag is found
        
        # Get the image filename from the <graphic> tag
        image_filename = graphic.get('url')
        image_path = os.path.join(temp_dir, image_filename)
        
        # If the image exists, process it
        if os.path.exists(image_path):
            # Read the image using OpenCV
            image = cv2.imread(image_path)

            # Define the path where the modified image will be saved
            output_path = os.path.join(output_dir, image_filename)
            
            # Iterate over the <zone> tags inside the <surface> to overlay polygons
            for zone in surface.findall('tei:zone', NS):
                points_str = zone.get('points')  # Get points attribute from the <zone>
                if not points_str:
                    continue  # Skip if no points are specified
                
                # Convert the points string to a list of tuples (coordinates)
                points = [tuple(map(int, pt.split(','))) for pt in points_str.split()]
                pts = np.array(points)
                
                # Overlay the polygon (zone) onto the image using OpenCV
                image = cv2.polylines(image, [pts], isClosed=True, color=(0, 255, 0), thickness=2)
            
            # Save the modified image with polygons overlaid
            cv2.imwrite(output_path, image)
        else:
            # If the image path does not exist, print a message and skip
            print(f'Skipping {image_filename}.')
    
    # Clean up by removing the temporary directory
    rmtree(temp_dir)

if __name__ == "__main__":
    # Set up argument parsing to accept command-line inputs
    parser = argparse.ArgumentParser(description="Overlay polygons on images using TEI XML annotations.")
    
    # Required arguments: TEI XML path, documents directory, and output directory
    parser.add_argument("--xml_path", required=True, help="Path to the TEI XML file")
    parser.add_argument("--docs_dir", required=True, help="Directory where the original images are stored")
    parser.add_argument("--output_dir", required=True, help="Directory to save images with overlays")

    # Parse command-line arguments
    args = parser.parse_args()
    
    # Call the main function with parsed arguments
    run(args.docs_dir, args.xml_path, args.output_dir)
    

"""
Command-line usage example:
python overlay_polygons_from_tei.py --docs_dir /data3/amal.joseph/temp_dir/sample_docs/ --xml_path /path/to/file.xml --output_dir /path/to/
"""