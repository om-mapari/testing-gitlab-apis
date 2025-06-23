#!/usr/bin/env python3
"""
GitLab AI Chat Console Client

This script allows direct interaction with GitLab AI chat through the command line,
without needing the VS Code extension. It uses the same GraphQL API endpoints
as the extension.
"""

import json
import os
import sys
import time
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional, Any

import requests


@dataclass
class GitLabConfig:
    """Configuration for connecting to GitLab"""
    gitlab_url: str
    access_token: str


class GitLabAIChat:
    """
    GitLab AI Chat client that uses GraphQL API to interact with GitLab AI
    """

    def __init__(self, config: GitLabConfig):
        self.config = config
        self.graphql_url = f"{config.gitlab_url.rstrip('/')}/api/graphql"
        self.headers = {
            "Authorization": f"Bearer {config.access_token}",
            "Content-Type": "application/json"
        }
        self.conversation_id = None
        self.request_ids = []
        self.thread_id = None

    def check_chat_available(self) -> bool:
        """Check if GitLab AI chat is available for the current user"""
        query = """
        query duoChatAvailable {
          currentUser {
            duoChatAvailable
          }
        }
        """
        
        response = requests.post(
            self.graphql_url,
            headers=self.headers,
            json={"query": query}
        )
        
        if response.status_code != 200:
            print(f"Error checking chat availability: {response.status_code}")
            print(response.text)
            return False
            
        data = response.json()
        if "errors" in data:
            print(f"GraphQL errors: {data['errors']}")
            return False
            
        return data.get("data", {}).get("currentUser", {}).get("duoChatAvailable", False)

    def send_message(self, message: str) -> Optional[str]:
        """
        Send a message to GitLab AI chat and return the response
        """
        client_subscription_id = str(uuid.uuid4())
        
        # GraphQL mutation to send the prompt
        mutation = """
        mutation chat(
          $question: String!
          $clientSubscriptionId: String
          $platformOrigin: String!
          $conversationType: AiConversationsThreadsConversationType
          $threadId: AiConversationThreadID
        ) {
          aiAction(
            input: {
              chat: { 
                content: $question
              }
              clientSubscriptionId: $clientSubscriptionId
              platformOrigin: $platformOrigin
              conversationType: $conversationType
              threadId: $threadId
            }
          ) {
            requestId
            errors
            threadId
          }
        }
        """
        
        variables = {
            "question": message,
            "clientSubscriptionId": client_subscription_id,
            "platformOrigin": "vscode-extension",  # This matches what the extension uses
            "conversationType": "DUO_CHAT"  # Use the standard DUO_CHAT type
        }
        
        # If we have a thread ID from a previous message, include it to continue the conversation
        if self.thread_id:
            variables["threadId"] = self.thread_id
        
        print("Sending message to GitLab AI...")
        
        response = requests.post(
            self.graphql_url,
            headers=self.headers,
            json={"query": mutation, "variables": variables}
        )
        
        if response.status_code != 200:
            print(f"Error sending message: {response.status_code}")
            print(response.text)
            return None
            
        data = response.json()
        
        if "errors" in data:
            print(f"GraphQL errors: {json.dumps(data['errors'], indent=2)}")
            return None
            
        ai_action = data.get("data", {}).get("aiAction", {})
        request_id = ai_action.get("requestId")
        
        if not request_id:
            print("No request ID returned")
            print(f"Response: {json.dumps(data, indent=2)}")
            return None
            
        # Store the thread ID for future messages in the same conversation
        if "threadId" in ai_action and ai_action["threadId"]:
            self.thread_id = ai_action["threadId"]
            
        self.request_ids.append(request_id)
        
        # Now poll for the response
        return self._poll_for_response(request_id)
        
    def _poll_for_response(self, request_id: str, max_retries: int = 60, interval: int = 1) -> Optional[str]:
        """Poll for the AI response using the request ID"""
        query = """
        query getAiMessages($requestIds: [ID!], $roles: [AiMessageRole!]) {
          aiMessages(requestIds: $requestIds, roles: $roles) {
            nodes {
              requestId
              role
              content
              contentHtml
              timestamp
              errors
            }
          }
        }
        """
        
        variables = {
            "requestIds": [request_id],
            "roles": ["ASSISTANT"]  # Only get assistant responses
        }
        
        print("Waiting for response", end="", flush=True)
        
        for i in range(max_retries):
            response = requests.post(
                self.graphql_url,
                headers=self.headers,
                json={"query": query, "variables": variables}
            )
            
            if i % 5 == 0:
                print(".", end="", flush=True)
                
            if response.status_code != 200:
                print(f"\nError polling for response: {response.status_code}")
                print(response.text)
                time.sleep(interval)
                continue
                
            data = response.json()
            if "errors" in data:
                print(f"\nGraphQL errors: {data['errors']}")
                time.sleep(interval)
                continue
                
            nodes = data.get("data", {}).get("aiMessages", {}).get("nodes", [])
            
            for node in nodes:
                if node.get("role") == "assistant" and node.get("content"):
                    print("\n")  # Add a newline after the progress dots
                    return node.get("content")
            
            time.sleep(interval)
            
        print("\nTimed out waiting for response")
        return None


def setup_config() -> GitLabConfig:
    """Set up the GitLab configuration"""
    print("===== GitLab AI Chat Configuration =====")
    
    # Try to load from environment variables first
    gitlab_url = os.environ.get("GITLAB_URL", "")
    access_token = os.environ.get("GITLAB_TOKEN", "")
    
    if not gitlab_url:
        gitlab_url = input("GitLab URL (e.g., https://gitlab.com): ").strip()
        
    if not access_token:
        access_token = input("GitLab Personal Access Token: ").strip()
    
    return GitLabConfig(
        gitlab_url=gitlab_url,
        access_token=access_token
    )


def interactive_chat(client: GitLabAIChat):
    """Run an interactive chat session with GitLab AI"""
    print("\n===== GitLab AI Chat =====")
    print("Type 'exit' to quit\n")
    
    while True:
        user_input = input("\nYou: ")
        if user_input.lower() in ["exit", "quit", "stop"]:
            break
            
        response = client.send_message(user_input)
        if response:
            print(f"\nGitLab AI: {response}")
        else:
            print("\nGitLab AI: No response received or an error occurred.")


def main():
    # Get configuration
    config = setup_config()
    
    # Create client
    client = GitLabAIChat(config)
    
    # Check if chat is available
    if not client.check_chat_available():
        print("GitLab AI Chat is not available for your account.")
        print("Please check your GitLab instance version and your permissions.")
        return
    
    print("GitLab AI Chat is available for your account!")
    
    # Start interactive chat
    interactive_chat(client)


if __name__ == "__main__":
    main() 