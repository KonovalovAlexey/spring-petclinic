import os
import requests
import base64
import boto3
from collections import defaultdict
from git import Repo

# get parameters
def get_parameter_from_ssm(parameter_name):
    ssm = boto3.client('ssm', region_name='eu-central-1') # Change region_name as necessary
    response = ssm.get_parameter(
        Name=parameter_name,
        WithDecryption=True 
    )
    return response['Parameter']['Value']

def update_remote_url_with_token(repo_path, github_token):
    repo = Repo(repo_path)
    remote_url = repo.remotes.origin.url
    new_url = remote_url.replace("https://", f"https://{github_token}@")
    repo.remotes.origin.set_url(new_url)

# Leave a comment in GitHub PR comment window
def post_github_comment(organization, repo_name, pull_request_number, ai_parameter_value, comment, file_path=None):
    url = f"https://api.github.com/repos/{organization}/{repo_name}/issues/{pull_request_number}/comments"
    headers = {
        "Authorization": f"token {github_token_value}",
        "Content-Type": "application/json"
    }

    if file_path:
        data = {
            "body": f"{file_path}\n```\n {comment}"
        }
    else:
        data = {
            "body": f"{comment}"
        }

    response = requests.post(url, headers=headers, json=data)
    return response.json()

def communicate_with_ai(api_endpoint, api_key, file_content, file_name, issues):
    request_headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + api_key
    }
    request_data = {
        "model": f"{llm_model}",
        "prompt": f"Please fix SonarQube issues for this file: {file_name}\nContent: {file_content} \n It has such issues: {', '.join(issues)}. I need code only. No text!",
        "max_tokens": 1500,
        "temperature": 0.7
    }

    response = requests.post(api_endpoint, headers=request_headers, json=request_data)

    if response.status_code == 200:
        error_fix = response.json()["choices"][0]["text"]
        return error_fix.strip()
    else:
        return None

def check_local_branch_exists(repo_path, branch_name):
    found = False
    repo = Repo(repo_path)
    for branch in repo.branches:
        if branch.name == branch_name:
            found = True
            break
    return found

def create_and_checkout_branch(repo_path, branch_name):
    repo = Repo(repo_path)
    if not check_local_branch_exists(repo_path, branch_name):
        repo.git.branch(branch_name)
    repo.git.checkout(branch_name)

def commit_and_push(repo_path, branch_name, commit_message):
    repo = Repo(repo_path)
    repo.git.add(A=True)
    repo.index.commit(commit_message)
    repo.git.push("origin", branch_name)

# Update variables and retrieve environment values
project_key = os.getenv("PROJECT_KEY")
pull_request_number = os.getenv("PULL_NUM")
source_branch = os.getenv("CODEBUILD_WEBHOOK_HEAD_REF")
source_branch = source_branch.split('/')[-1]  # Remove 'refs/heads/' prefix from the source_branch
repo_name = os.getenv("REPO_NAME")
organization = os.getenv("ORGANIZATION")
sonar_parameter_name = os.getenv("SONAR_TOKEN")
api_endpoint = "https://api.openai.com/v1/completions"
api_key_parameter_name = os.getenv("OPENAI_API_KEY")
github_token_name = os.getenv("GITHUB_TOKEN_NAME")
llm_model = "text-davinci-003"

# Receive and decrypt values from SSM Parameter Store
sonar_parameter_value = get_parameter_from_ssm(sonar_parameter_name)
ai_parameter_value = get_parameter_from_ssm(api_key_parameter_name)
github_token_value = get_parameter_from_ssm(github_token_name)

headers = {
    "Authorization": "Basic " + base64.b64encode((sonar_parameter_value + ":").encode()).decode()
}

# Update sonar_analysis_branch and local_repo_path variables
sonar_analysis_branch = f"{source_branch}-sonar-analysis"
local_repo_path = os.getenv("CODEBUILD_SRC_DIR")

# Post a comment if the branch from the sonar_analysis_branch value already exists and interrupt the script
if check_local_branch_exists(local_repo_path, sonar_analysis_branch):
    comment = f"The branch **{sonar_analysis_branch}** created by AI already exists. Please review it. If you need to execute the AI handler one more time please remove the branch **{sonar_analysis_branch}**"
    post_github_comment(organization, repo_name, pull_request_number, ai_parameter_value, comment)
else:
    # Create and switch to the new branch if it doesn't exist
    create_and_checkout_branch(local_repo_path, sonar_analysis_branch)

    # Get project quality gate status
    status_url = "https://sonarcloud.io/api/qualitygates/project_status?projectKey=" + project_key
    status_response = requests.get(status_url, headers=headers).json()

    # Handle issues based on quality_gate_status
    quality_gate_status = status_response["projectStatus"]["status"]

    files_updated = False

    if quality_gate_status != "OK":
        # Extract issues and file paths
        issues_url = "https://sonarcloud.io/api/issues/search?projects=" + project_key + "&statuses=OPEN,REOPENED,CONFIRMED"
        issues_response = requests.get(issues_url, headers=headers).json()

        issues_by_file = defaultdict(list)

        # Group issues by file
        for issue in issues_response["issues"]:
            component = issue["component"]
            file_path = [comp["path"] for comp in issues_response["components"] if comp["key"] == component][0]
            message = issue["message"]
            issues_by_file[file_path].append(message)

        # Iterate over files with issues and process them
        for file_path, issues in issues_by_file.items():
            print(f"File: {file_path}")

            # Read file content
            try:
                with open(file_path, "r") as file:
                    file_content = file.read()
            except FileNotFoundError:
                print("  - File not found in the specified directory.")
                continue

            # Call communicate_with_ai function with file name and issues
            error_fix = communicate_with_ai(api_endpoint, ai_parameter_value, file_content, file_path, issues)

            if error_fix:
                print(f"  - Suggested fix: {error_fix}")
                # Post the suggested fix as a comment on Github
                post_github_comment(organization, repo_name, pull_request_number, ai_parameter_value, error_fix, file_path)
                
                files_updated = True
                # Update the file content
                with open(file_path, "w") as file:
                    file.write(error_fix)

        if files_updated:
            # Update the remote repository URL with the GitHub token for authentication
            update_remote_url_with_token(local_repo_path, github_token_value)
            # Commit and push the changes to the 'sonar-analysis' branch
            commit_and_push(local_repo_path, sonar_analysis_branch, "Automated sonar-analysis fixes")
            comment = f"A new branch with AI fixes created - {sonar_analysis_branch}. Please review it."
            post_github_comment(organization, repo_name, pull_request_number, ai_parameter_value, comment)
