import argparse
import requests
import json
import os

# Template URLs for checking the job status and downloading the TEI-P5 XML
API_STATUS_URL_TEMPLATE = "https://skeleton.iiit.ac.in/api/v1/polylines/status/{job_id}"
API_XML_URL_TEMPLATE = "https://skeleton.iiit.ac.in/api/v1/polylines/status/tei/{job_id}"

# Your API token for authentication (replace with your actual token)
API_TOKEN = "YOUR TOKEN"

def check_job_status(job_id):
    """
    Checks the status of the job by making a GET request to the API status endpoint.
    Prints the job status and details of the documents processed.
    """
    # Format the URL with the specific job ID
    url = API_STATUS_URL_TEMPLATE.format(job_id=job_id)
    headers = {
        "accept": "application/json",  # Requesting JSON format in response
        "X-API-Token": API_TOKEN       # API authentication token
    }

    try:
        # Send the GET request to check the status
        response = requests.get(url, headers=headers)
        # Raise an exception for any HTTP error responses (4xx, 5xx)
        response.raise_for_status()
        
        # Parse the JSON response
        status_data = response.json()

        print("\nJob Status:\n")
        # Print job ID and current status
        print(f"Job ID         : {status_data['job_id']}")
        print(f"Status         : {status_data['status']}")
        
        # If the response includes documents, print their paths and statuses
        if 'documents' in status_data:
            print("\nDocuments:")
            for doc in status_data['documents']:
                print(f" - Doc Path: {doc['doc_path']} | Status: {doc['status']}")

    except requests.exceptions.HTTPError as e:
        # Handle HTTP errors (invalid job ID, server issues, etc.)
        print(f"HTTP Error: {e.response.status_code}")
        print(e.response.text)
    except Exception as e:
        # Handle any other exceptions
        print("Error while checking job status:", e)

def download_xml(job_id, save_path):
    """
    Downloads the processed TEI-P5 XML result of the job and saves it to a file,
    or prints it to the console if no save path is provided.
    """
    # Format the URL to get the TEI-P5 XML result for the specific job ID
    url = API_XML_URL_TEMPLATE.format(job_id=job_id)
    headers = {
        "accept": "application/xml",  # Requesting XML format in response
        "X-API-Token": API_TOKEN      # API authentication token
    }

    try:
        # Send the GET request to download the XML
        response = requests.get(url, headers=headers)
        # Raise an exception for any HTTP error responses (4xx, 5xx)
        response.raise_for_status()

        # Get the XML data as a string
        xml_data = response.text

        # If a save path is provided, save the XML data to that location
        if save_path:
            # Create the full file path for saving the XML
            save_path = os.path.join(save_path, f'{job_id}.xml')
            # Open the file and write the XML data
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(xml_data)
            print(f"\nTEI-P5 XML result saved to: {save_path}")
        else:
            # If no save path, just print the XML data to the console
            print("\nProcessed XML:\n")
            print(xml_data)

    except requests.exceptions.HTTPError as e:
        # Handle HTTP errors (invalid job ID, server issues, etc.)
        print(f"HTTP Error: {e.response.status_code}")
        print(e.response.text)
    except Exception as e:
        # Handle any other exceptions
        print("Error while downloading XML:", e)

if __name__ == "__main__":
    # Set up the command-line argument parser
    parser = argparse.ArgumentParser(description="Check the status of a job and download the processed XML.")
    parser.add_argument("--job-id", required=True, help="The job ID returned after submission.")  # Required job ID
    parser.add_argument("--save-xml-to", help="Optional file path to save the XML result.")  # Optional save path

    # Parse the arguments provided by the user
    args = parser.parse_args()

    # Check the status of the job
    check_job_status(args.job_id)

    # If the user provided a save path, download and save the XML result
    if args.save_xml_to:
        download_xml(args.job_id, args.save_xml_to)

# Example command to run the script:
# python check_job_status.py --job-id JOB_ID --save-xml-to /path/to/
