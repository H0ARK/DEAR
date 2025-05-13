#!/usr/bin/env python3
import requests
import json
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get Linear API key and team ID from environment variables
api_key = os.getenv("LINEAR_API_KEY")
team_id = os.getenv("LINEAR_TEAM_ID")

print(f"Using API Key: {api_key}")
print(f"Using Team ID: {team_id}")

# GraphQL endpoint
url = "https://api.linear.app/graphql"

# Headers with authorization
headers = {
    "Authorization": api_key,
    "Content-Type": "application/json"
}

# Test: Get team information
print("\nTest: Get team information")
query_team = """
query {
  teams {
    nodes {
      id
      name
      key
      states {
        nodes {
          id
          name
          type
        }
      }
    }
  }
}
"""

response_team = requests.post(
    url,
    headers=headers,
    json={"query": query_team}
)

print("Status Code:", response_team.status_code)
print("Response:")
print(json.dumps(response_team.json(), indent=2))

# If we got a successful response, let's try to get issues
if response_team.status_code == 200 and "data" in response_team.json() and response_team.json()["data"] is not None:
    # Get the first team's ID
    teams = response_team.json()["data"]["teams"]["nodes"]
    if teams:
        first_team_id = teams[0]["id"]
        first_team_name = teams[0]["name"]
        print(f"\nFound team: {first_team_name} with ID: {first_team_id}")

        # Test: Get issues for the first team
        print("\nTest: Get issues for the first team")
        query_issues = """
        query GetTeamIssues($teamId: String!) {
          team(id: $teamId) {
            issues {
              nodes {
                id
                title
                description
                state {
                  name
                }
              }
            }
          }
        }
        """

        variables_issues = {
            "teamId": first_team_id
        }

        print("Request payload:", json.dumps({"query": query_issues, "variables": variables_issues}, indent=2))
        response_issues = requests.post(
            url,
            headers=headers,
            json={"query": query_issues, "variables": variables_issues}
        )

        print("Status Code:", response_issues.status_code)
        print("Response:")
        print(json.dumps(response_issues.json(), indent=2))
    else:
        print("No teams found in the response.")
