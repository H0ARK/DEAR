#!/usr/bin/env python3
import requests
import json
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get Linear API key from environment variables
api_key = os.getenv("LINEAR_API_KEY")
if not api_key:
    api_key = ""  # Use the key from your .env file

# GraphQL endpoint
url = "https://api.linear.app/graphql"

# Headers with authorization
headers = {
    "Authorization": api_key,
    "Content-Type": "application/json"
}

# GraphQL query to get teams
query = """
query {
  teams {
    nodes {
      id
      name
    }
  }
}
"""

# Make the request
response = requests.post(
    url,
    headers=headers,
    json={"query": query}
)

# Print the response
print("Status Code:", response.status_code)
print("Response:")
print(json.dumps(response.json(), indent=2))
