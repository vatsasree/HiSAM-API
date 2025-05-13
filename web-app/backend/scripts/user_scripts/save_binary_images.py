import os
import argparse
import xml.etree.ElementTree as ET
import base64

# TEI XML namespace
NS = {'tei': 'http://www.tei-c.org/ns/1.0'}


def run(xml_path, output_dir):
    tree = ET.parse(xml_path)
    root = tree.getroot()
    
    facsimile = root.find('tei:facsimile', NS)
    if facsimile is None:
        print("No <facsimile> tag found.")
        return
    
    for surface in facsimile.findall('tei:surface', NS):
        graphic = surface.find('tei:graphic', NS)
        if graphic is None:
            continue
        image_filename = graphic.get('url')
        output_path = os.path.join(output_dir, image_filename)
        for binary in surface.findall('tei:binaryObject', NS):
            b64_data = ''.join(binary.text.strip().split())  # remove whitespace

            with open(output_path, 'wb') as f:
                f.write(base64.b64decode(b64_data))


            

    

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Overlay scribbles on images using TEI XML annotations.")
    parser.add_argument("--xml_path", required=True, help="Path to the TEI XML file")
    parser.add_argument("--output_dir", required=True, help="Directory to save images with overlays")

    args = parser.parse_args()
    run(args.xml_path, args.output_dir)
    

"""
python save_binary_images.py --xml_path /path/to/file.xml --output_dir /path/to/
"""