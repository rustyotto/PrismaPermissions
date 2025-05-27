import requests
import csv
import time

# --- Configuration ---
# Using the API base URL from your previous error log.
PRISMA_CLOUD_API_URL = "https://api.prismacloud.io"
ACCESS_KEY = "YOUR_ACCESS_KEY_ID"  # Replace with your Access Key ID
SECRET_KEY = "YOUR_SECRET_KEY"    # Replace with your Secret Key

# Global variable to store the auth token
TOKEN = ""
# Delay between individual API calls in seconds.
# IMPORTANT: With one call per account, this is crucial to avoid rate limiting.
API_CALL_DELAY = 0.5  # Adjust as needed (0.5 to 1 second is a good start)

# --- Function to handle API Login ---
def login_to_prisma_cloud():
    """Logs into Prisma Cloud and stores the auth token globally."""
    global TOKEN
    payload = {"username": ACCESS_KEY, "password": SECRET_KEY}
    headers = {"Content-Type": "application/json", "Accept": "application/json; charset=UTF-8"}
    login_url = f"{PRISMA_CLOUD_API_URL}/login"
    print(f"Attempting login to: {login_url}...")
    try:
        response = requests.post(login_url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        TOKEN = response.json().get("token")
        if TOKEN:
            print("Login successful.")
            return True
        else:
            print("Login successful, but no token was received.")
            return False
    except requests.exceptions.HTTPError as errh:
        print(f"Http Error during login: {errh}")
        response_text = errh.response.text if errh.response else "No response body"
        print(f"Response body: {response_text}")
    except requests.exceptions.RequestException as err:
        print(f"An error occurred during login: {err}")
    return False

# --- Function to List Cloud Accounts ---
def list_cloud_accounts():
    """Lists all cloud accounts from Prisma Cloud."""
    if not TOKEN:
        print("Authentication token not found. Please login first.")
        return []
    headers = {"x-redlock-auth": TOKEN, "Accept": "application/json; charset=UTF-8"}
    list_accounts_url = f"{PRISMA_CLOUD_API_URL}/cloud" # This endpoint seems to be correct for listing
    print(f"Fetching cloud accounts from: {list_accounts_url}...")
    try:
        response = requests.get(list_accounts_url, headers=headers, timeout=60)
        response.raise_for_status()
        accounts = response.json()
        # We need accountId and preferably name and cloudType for the report
        # Let's ensure we get what we need for the next step and the report
        valid_accounts_info = []
        for acc in accounts:
            if acc.get("accountId"):
                valid_accounts_info.append({
                    "accountId": acc["accountId"],
                    "name": acc.get("name", "N/A"),
                    "cloudType": acc.get("cloudType", "N/A")
                })
        print(f"Successfully retrieved {len(valid_accounts_info)} cloud accounts with IDs.")
        return valid_accounts_info
    except requests.exceptions.HTTPError as errh:
        print(f"Http Error listing accounts: {errh}")
        response_text = errh.response.text if errh.response else "No response body"
        print(f"Response body: {response_text}")
    except requests.exceptions.RequestException as err:
        print(f"Error listing accounts: {err}")
    return []

# --- Function to Get Cloud Account Config Status (using the new endpoint) ---
def get_permission_messages_for_accounts(accounts_info_list):
    """
    Fetches config status for each account ID using the /account/{accountId}/config/status endpoint
    and extracts permission/error messages.
    'accounts_info_list' is a list of dicts, each with 'accountId', 'name', 'cloudType'.
    Returns a list of dictionaries, where each dictionary is a row for the report.
    """
    if not TOKEN:
        print("Authentication token not found. Please login first.")
        return []
    if not accounts_info_list:
        print("No accounts info provided to fetch status for.")
        return []

    headers = {"x-redlock-auth": TOKEN, "Accept": "application/json; charset=UTF-8"}
    all_report_entries = []
    
    total_accounts = len(accounts_info_list)
    for index, account_info in enumerate(accounts_info_list):
        account_id_to_check = account_info["accountId"]
        account_name = account_info["name"]
        account_cloud_type = account_info["cloudType"]
        current_account_num = index + 1

        status_url = f"{PRISMA_CLOUD_API_URL}/account/{account_id_to_check}/config/status"
        print(f"Fetching config status for account {current_account_num} of {total_accounts} (ID: {account_id_to_check}) from {status_url}...")
        
        response = None # Initialize response
        try:
            response = requests.get(status_url, headers=headers, timeout=30)
            response.raise_for_status() # Will raise an exception for 4xx/5xx errors
            
            # Assuming the direct response from this endpoint is the array of components
            # (like the samples you provided for AWS and GCP)
            config_status_components = response.json() 
            
            if not isinstance(config_status_components, list) or not config_status_components:
                print(f"  No valid component data returned for account ID: {account_id_to_check}. Response was: {config_status_components}")
                all_report_entries.append({
                    "AccountID": account_id_to_check, "AccountName": account_name,
                    "CloudType": account_cloud_type, "Category": "Overall Account Status",
                    "ServiceContext": "N/A", "Status": "No Data/Invalid Format",
                    "Message": "No valid component data returned from API or response format was unexpected."
                })
            else:
                processed_issue_for_this_account = False
                for error_category in config_status_components:
                    category_name = error_category.get("name", "Unnamed Category")
                    category_status = error_category.get("status", "unknown")
                    category_message = error_category.get("message", "")

                    if category_status != "ok":
                        processed_issue_for_this_account = True
                        if category_message:
                            all_report_entries.append({
                                "AccountID": account_id_to_check, "AccountName": account_name,
                                "CloudType": account_cloud_type, "Category": category_name,
                                "ServiceContext": f"Overall {category_name}",
                                "Status": category_status, "Message": category_message
                            })
                        sub_components = error_category.get("subComponents")
                        if isinstance(sub_components, list):
                            for sub_component in sub_components:
                                sub_name = sub_component.get("name", "Unnamed SubComponent")
                                sub_status = sub_component.get("status", "unknown")
                                sub_message = sub_component.get("message", "")
                                if sub_status != "ok" and sub_message:
                                    all_report_entries.append({
                                        "AccountID": account_id_to_check, "AccountName": account_name,
                                        "CloudType": account_cloud_type, "Category": category_name,
                                        "ServiceContext": sub_name, "Status": sub_status,
                                        "Message": sub_message
                                    })
                
                if not processed_issue_for_this_account: # All components were "ok"
                    all_report_entries.append({
                        "AccountID": account_id_to_check, "AccountName": account_name,
                        "CloudType": account_cloud_type, "Category": "Overall Config Status",
                        "ServiceContext": "N/A", "Status": "OK",
                        "Message": "All configuration components reported OK."
                    })

            if API_CALL_DELAY > 0:
                time.sleep(API_CALL_DELAY)

        except requests.exceptions.HTTPError as errh:
            response_text = errh.response.text if errh.response else "No response object or text."
            print(f"  Http Error {errh.response.status_code} getting config status for account ID {account_id_to_check}: {errh}")
            print(f"  Response body: {response_text}")
            all_report_entries.append({
                "AccountID": account_id_to_check, "AccountName": account_name,
                "CloudType": account_cloud_type, "Category": "API Error",
                "ServiceContext": "N/A", "Status": "Error",
                "Message": f"HTTP Error {errh.response.status_code}: {response_text}"
            })
            if API_CALL_DELAY > 0: time.sleep(API_CALL_DELAY)
        except requests.exceptions.RequestException as err:
            print(f"  Request Error getting config status for account ID {account_id_to_check}: {err}")
            all_report_entries.append({
                "AccountID": account_id_to_check, "AccountName": account_name,
                "CloudType": account_cloud_type, "Category": "API Error",
                "ServiceContext": "N/A", "Status": "Error",
                "Message": f"Request Error: {err}"
            })
            if API_CALL_DELAY > 0: time.sleep(API_CALL_DELAY)
        except json.JSONDecodeError as json_err:
            print(f"  JSON Decode Error for account ID {account_id_to_check}. Response was not valid JSON: {json_err}")
            response_text = response.text if response else "No response object."
            all_report_entries.append({
                "AccountID": account_id_to_check, "AccountName": account_name,
                "CloudType": account_cloud_type, "Category": "API Error",
                "ServiceContext": "N/A", "Status": "Error",
                "Message": f"Invalid JSON response from server: {response_text[:200]}..." # Log snippet
            })
            if API_CALL_DELAY > 0: time.sleep(API_CALL_DELAY)
        except Exception as e:
            print(f"  An unexpected error processing account ID {account_id_to_check}: {e}")
            all_report_entries.append({
                "AccountID": account_id_to_check, "AccountName": account_name,
                "CloudType": account_cloud_type, "Category": "Script Error",
                "ServiceContext": "N/A", "Status": "Error",
                "Message": f"Unexpected script error: {e}"
            })
            if API_CALL_DELAY > 0: time.sleep(API_CALL_DELAY)
    
    return all_report_entries

# --- Main Script Execution ---
def main():
    """Main function to orchestrate the script."""
    if PRISMA_CLOUD_API_URL == "https://api.your-region.prismacloud.io" or \
       ACCESS_KEY == "YOUR_ACCESS_KEY_ID" or \
       SECRET_KEY == "YOUR_SECRET_KEY":
        print("ERROR: Please update PRISMA_CLOUD_API_URL, ACCESS_KEY, and SECRET_KEY with your actual details at the top of the script.")
        return

    if login_to_prisma_cloud():
        accounts_info = list_cloud_accounts() # Now gets list of dicts with id, name, cloudType
        
        if accounts_info:
            report_lines = get_permission_messages_for_accounts(accounts_info)
            
            if not report_lines:
                print("No report data generated. This could be due to errors or no issues found.")
                return

            output_filename = "prisma_cloud_config_status_report.csv"
            header = ["AccountID", "AccountName", "CloudType", "Category", "ServiceContext", "Status", "Message"]
            
            print(f"\n--- Writing Cloud Account Config Status Report to {output_filename} ---")
            try:
                with open(output_filename, 'w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=header)
                    writer.writeheader()
                    writer.writerows(report_lines)
                print(f"Report successfully written to {output_filename}")
            except IOError:
                print(f"IOError writing report to {output_filename}. Check permissions or path.")
            except Exception as e:
                print(f"An unexpected error occurred while writing the CSV file: {e}")
        else:
            print("No cloud accounts were retrieved to process.")

if __name__ == "__main__":
    main()