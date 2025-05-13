import argparse
import os
import requests
import mimetypes

# API endpoint for submitting files
API_URL = "https://skeleton.iiit.ac.in/api/v1/polylines/process/"
# Replace this with your actual API token
API_TOKEN = "YOUR TOKEN"

def gather_files(input_dir):
    """
    Collect all files with allowed extensions (.jpg, .jpeg, .png, .pdf)
    from the specified input directory.
    """
    allowed_exts = {'.jpg', '.jpeg', '.png', '.pdf'}

    # List all files in the directory that match allowed extensions
    file_paths = [
        os.path.join(input_dir, f)
        for f in os.listdir(input_dir)
        if os.path.isfile(os.path.join(input_dir, f)) and os.path.splitext(f)[1].lower() in allowed_exts
    ]
    return file_paths

def submit_job(file_paths):
    """
    Submits the collected files to the API for processing.
    """
    headers = {
        "accept": "application/json",
        "X-API-Token": API_TOKEN,  # Include API token for authentication
    }

    files = []
    for path in file_paths:
        # Guess the MIME type of the file, fallback to 'application/octet-stream' if unknown
        mime_type, _ = mimetypes.guess_type(path)
        mime_type = mime_type or "application/octet-stream"
        
        # Prepare the file tuple for multipart/form-data upload
        files.append(("files", (os.path.basename(path), open(path, "rb"), mime_type)))

    try:
        print("Sending files to server.")
        
        # Send POST request with files and headers to the API
        response = requests.post(API_URL, headers=headers, files=files)
        response.raise_for_status()  # Raise an error if the response contains HTTP error status
        
        # Parse and print the response
        data = response.json()
        print("Job Submitted Successfully")
        print(f"Job ID         : {data.get('job_id')}")
        print(f"Message        : {data.get('message')}")
        print(f"Document Count : {data.get('document_count')}")

    except requests.exceptions.HTTPError as e:
        # Handle specific HTTP errors
        print("HTTP Error:", e.response.status_code)
        print("Response Text:", e.response.text)
    except Exception as e:
        # Handle any other exceptions
        print("Error during job submission:", e)

if __name__ == "__main__":
    # Set up command-line interface
    parser = argparse.ArgumentParser(description="Submit files or a folder to the API.")
    
    # Mutually exclusive group to ensure only one input method is provided
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--files", nargs="+", help="List of file paths to upload")
    group.add_argument("--input-dir", help="Directory containing files to upload")
    # (Note: args.files is referenced but not actually defined in the arguments, should be fixed if used.)

    args = parser.parse_args()

    # Gather file paths from the specified input directory
    file_paths = gather_files(args.input_dir)

    if not file_paths:
        print("No valid files found to submit.")
    else:
        # Submit the collected files to the API
        submit_job(file_paths)

# Example usage:
# python submit_job.py --input-dir /path/to/
# python submit_job.py --input-dir /data3/amal.joseph/temp_dir/sample_docs/