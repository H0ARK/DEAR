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

# Test 1: Get team tasks
print("\nTest 1: Get team tasks")
query_tasks = """
query GetTeamIssues($teamId: String!, $includeCompleted: Boolean!) {
  team(id: $teamId) {
    issues(first: 100, filter: {completed: {eq: $includeCompleted}}) {
      nodes {
        id
        title
        description
        state {
          name
        }
        assignee {
          id
        }
        team {
          id
        }
        priority
        parent {
          id
        }
        createdAt
        updatedAt
        completedAt
        labels {
          nodes {
            name
          }
        }
      }
    }
  }
}
"""

variables_tasks = {
    "teamId": team_id,
    "includeCompleted": False
}

response_tasks = requests.post(
    url,
    headers=headers,
    json={"query": query_tasks, "variables": variables_tasks}
)

print("Status Code:", response_tasks.status_code)
print("Response:")
print(json.dumps(response_tasks.json(), indent=2))

# Test 2: Get epics
print("\nTest 2: Get epics")
query_epics = """
query GetTeamEpics($teamId: String!) {
  team(id: $teamId) {
    issues(first: 50, filter: {isEpic: {eq: true}}) {
      nodes {
        id
        title
        description
        state {
          name
        }
        assignee {
          id
        }
        team {
          id
        }
        priority
        createdAt
        updatedAt
        completedAt
        labels {
          nodes {
            name
          }
        }
      }
    }
  }
}
"""

variables_epics = {
    "teamId": team_id
}

response_epics = requests.post(
    url,
    headers=headers,
    json={"query": query_epics, "variables": variables_epics}
)

print("Status Code:", response_epics.status_code)
print("Response:")
print(json.dumps(response_epics.json(), indent=2))
