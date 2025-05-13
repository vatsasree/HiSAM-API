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
    Converts PDF documents to images and copies other document types into a temporary folder.
    Returns the path of the temporary directory where the processed documents are stored.
    """
    # Get a list of all files in the specified documents directory
    documents = [os.path.join(docs_dir, file) for file in os.listdir(docs_dir)]
    
    # Create a temporary directory to store the images and copied documents
    temp_dir = os.path.join(output_dir, 'tmp_folder')
    os.makedirs(temp_dir, exist_ok=True)
    
    # Process each document in the documents directory
    for document in documents:
        if document.endswith('.pdf'):  # If the document is a PDF
            # Convert each page of the PDF into an image
            doc_images = convert_from_path(document, use_cropbox=True)
            for i, image in enumerate(doc_images):
                # Save each page as an image (JPG) in the temp directory
                temp_image_name = document.split('/')[-1].replace('.pdf', '') + f'_page_{i+1}.jpg'
                temp_image_name = os.path.join(temp_dir, temp_image_name)
                image.save(temp_image_name)
        else:  # If it's not a PDF (e.g., an image file)
            # Copy non-PDF files directly to the temporary directory
            copyfile(document, os.path.join(temp_dir, document.split('/')[-1]))
    
    # Return the path to the temporary folder containing the processed documents
    return temp_dir

def crop_image(image, coordinates, output_path):
    """
    Crops a given image based on the provided polygonal coordinates and saves the cropped image.
    """
    # Convert coordinates (points) into a NumPy array of integer points
    points = np.array(coordinates, dtype=np.int32)
    
    # Create a mask of the same size as the image, initialized to 0 (black)
    mask = np.zeros(image.shape[:2], dtype=np.uint8)
    
    # Fill the polygon defined by the coordinates with white (255) in the mask
    cv2.fillPoly(mask, [points], (255))
    
    # Perform bitwise AND between the mask and the original image to isolate the area inside the polygon
    cropped_image = cv2.bitwise_and(image, image, mask=mask)
    
    # Get the bounding box for the polygon to crop it to the minimum region of interest
    x, y, w, h = cv2.boundingRect(points)
    cropped_image = cropped_image[y:y+h, x:x+w]  # Crop the image based on the bounding box

    # Save the cropped image to the specified output path
    cv2.imwrite(output_path, cropped_image)

def run(docs_dir, xml_path, output_dir):
    """
    Main function that processes documents, reads the TEI XML, and crops images based on <zone> annotations.
    """
    # Process documents and store them in a temporary directory
    temp_dir = process_documents(docs_dir, output_dir)
    
    # Parse the TEI XML file to extract annotations
    tree = ET.parse(xml_path)
    root = tree.getroot()
    
    # Find the <facsimile> tag in the TEI XML, which contains the image and annotation data
    facsimile = root.find('tei:facsimile', NS)
    if facsimile is None:
        print("No <facsimile> tag found.")
        return  # Exit if <facsimile> tag is not found
    
    # Iterate through each <surface> in the <facsimile> section
    for surface in facsimile.findall('tei:surface', NS):
        # Get the surface ID for debugging or reference
        surface_id = surface.get('{http://www.w3.org/XML/1998/namespace}id')
        
        # Find the <graphic> tag which contains the reference to the image
        graphic = surface.find('tei:graphic', NS)
        if graphic is None:
            continue  # Skip if no <graphic> tag is found (no image to process)
        
        # Get the image filename from the <graphic> tag
        image_filename = graphic.get('url')
        image_path = os.path.join(temp_dir, image_filename)
        
        # If the image exists, process it
        if os.path.exists(image_path):
            # Read the image using OpenCV
            image = cv2.imread(image_path)
            
            # Define the output directory where cropped images will be stored
            output_path = os.path.join(output_dir, image_filename.split('.')[0])
            os.makedirs(output_path, exist_ok=True)  # Create the output directory if it doesn't exist
            
            # Iterate over the <zone> tags in each <surface> to crop the defined zones
            for i, zone in enumerate(surface.findall('tei:zone', NS)):
                # Get the 'points' attribute from the <zone>, which defines the polygon
                points_str = zone.get('points')
                if not points_str:
                    continue  # Skip if no points are defined for the zone
                
                # Parse the points and convert them into a list of tuples (coordinates)
                points = [tuple(map(int, pt.split(','))) for pt in points_str.split()]
                pts = np.array(points)  # Convert the points to a NumPy array
                
                # Crop the image based on the points (polygon) and save the cropped image
                crop_image(image, pts, f'{output_path}/{i}.jpg')
        else:
            # If the image file does not exist, print a message and skip
            print(f'Skipping {image_filename}.')
    
    # Clean up by removing the temporary directory created during processing
    rmtree(temp_dir)

if __name__ == "__main__":
    # Set up argument parsing for command-line inputs
    parser = argparse.ArgumentParser(description="Extract and crop textlines from TEI XML annotations on images.")
    
    # Required arguments: TEI XML file path, documents directory, and output directory
    parser.add_argument("--xml_path", required=True, help="Path to the TEI XML file")
    parser.add_argument("--docs_dir", required=True, help="Directory containing the original images or documents")
    parser.add_argument("--output_dir", required=True, help="Directory to save cropped images")

    # Parse the command-line arguments
    args = parser.parse_args()
    
    # Call the main function with parsed arguments
    run(args.docs_dir, args.xml_path, args.output_dir)
    

"""
Command-line usage example:
python extract_textlines_from_tei.py --docs_dir /path/to/ --xml_path /path/to/file.xml --output_dir /path/to/
"""