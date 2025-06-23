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
import warnings
from dataclasses import dataclass
from typing import Dict, List, Optional, Any

# Suppress InsecureRequestWarning
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import requests


# Constants matching the VS Code extension
PLATFORM_ORIGIN = 'vs_code_extension'
SPECIAL_MESSAGES = {
    'RESET': '/reset',
    'CLEAR': '/clear',
    'CLEAN': '/clean'  # Deprecated, but remains for older versions of GitLab
}

# Minimum version constants
MINIMUM_PLATFORM_ORIGIN_FIELD_VERSION = '17.3.0'
MINIMUM_ADDITIONAL_CONTEXT_FIELD_VERSION = '17.5.0-pre'
MINIMUM_CONVERSATION_TYPE_VERSION = '17.10.0-pre'


@dataclass
class GitLabConfig:
    """Configuration for connecting to GitLab"""
    gitlab_url: str
    access_token: str
    debug: bool = False


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
        self.thread_id = None
        self.request_ids = []
        self.gitlab_version = None
        self.debug = config.debug
        
    def _graphql_request(self, query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        """Make a GraphQL request to GitLab API"""
        try:
            if self.debug:
                print(f"GraphQL Query: {query}")
                print(f"Variables: {json.dumps(variables, indent=2)}")
                
            response = requests.post(
                self.graphql_url,
                headers=self.headers,
                json={"query": query, "variables": variables},
                verify=False  # Disable SSL verification
            )
            
            if self.debug:
                print(f"Response Status: {response.status_code}")
                
            response.raise_for_status()
            data = response.json()
            
            if self.debug:
                print(f"Response Data: {json.dumps(data, indent=2)}")
                
            return data
        except requests.RequestException as e:
            print(f"Request error: {e}")
            if hasattr(e, 'response') and e.response:
                print(f"Response status: {e.response.status_code}")
                print(f"Response body: {e.response.text}")
            return {"errors": [{"message": str(e)}]}

    def version_gte(self, version: str, min_version: str) -> bool:
        """Check if GitLab version is greater than or equal to minimum version"""
        if not version or not min_version:
            return False
            
        # Simple version comparison - could be improved for more complex version strings
        v_parts = version.split('.')
        min_parts = min_version.split('.')
        
        # Compare major version
        if int(v_parts[0]) > int(min_parts[0]):
            return True
        if int(v_parts[0]) < int(min_parts[0]):
            return False
            
        # Compare minor version
        if int(v_parts[1]) > int(min_parts[1]):
            return True
        if int(v_parts[1]) < int(min_parts[1]):
            return False
            
        # Compare patch version (ignoring any suffixes like -pre)
        v_patch = v_parts[2].split('-')[0]
        min_patch = min_parts[2].split('-')[0]
        return int(v_patch) >= int(min_patch)

    def get_gitlab_version(self) -> Optional[str]:
        """Get the GitLab instance version"""
        if self.gitlab_version:
            return self.gitlab_version
            
        # Try metadata.version field (works in newer GitLab versions)
        query = """
        query getMetadataVersion {
          metadata {
            version
          }
        }
        """
        
        data = self._graphql_request(query, {})
        
        if "errors" not in data:
            version = data.get("data", {}).get("metadata", {}).get("version")
            if version:
                self.gitlab_version = version
                return version
                
        # If that fails, try the version field directly (older versions)
        query = """
        query getVersion {
          version
        }
        """
        
        data = self._graphql_request(query, {})
        
        if "errors" in data:
            if self.debug:
                print(f"Error getting GitLab version: {data['errors']}")
            return None
            
        version = data.get("data", {}).get("version")
        self.gitlab_version = version
        return version

    def check_chat_available(self) -> bool:
        """Check if GitLab AI chat is available for the current user"""
        query = """
        query duoChatAvailable {
          currentUser {
            duoChatAvailable
          }
        }
        """
        
        data = self._graphql_request(query, {})
        
        if "errors" in data:
            print(f"Error checking chat availability: {json.dumps(data['errors'], indent=2)}")
            return False
            
        return data.get("data", {}).get("currentUser", {}).get("duoChatAvailable", False)

    def get_current_user(self) -> Optional[Dict[str, Any]]:
        """Get the current user information"""
        query = """
        query getCurrentUser {
          currentUser {
            id
            username
            name
          }
        }
        """
        
        data = self._graphql_request(query, {})
        
        if "errors" in data:
            if self.debug:
                print(f"Error getting current user: {data['errors']}")
            return None
            
        return data.get("data", {}).get("currentUser")

    def get_available_conversation_types(self) -> List[str]:
        """Get the available conversation types for the current GitLab instance"""
        # Try to introspect the GraphQL schema to get available enum values
        query = """
        query getConversationTypes {
          __type(name: "AiConversationsThreadsConversationType") {
            enumValues {
              name
            }
          }
        }
        """
        
        data = self._graphql_request(query, {})
        
        if "errors" in data:
            if self.debug:
                print(f"Error getting conversation types: {data['errors']}")
            # Default to DUO_CHAT_LEGACY as fallback
            return ["DUO_CHAT_LEGACY"]
            
        enum_values = data.get("data", {}).get("__type", {}).get("enumValues", [])
        return [enum_value["name"] for enum_value in enum_values] if enum_values else ["DUO_CHAT_LEGACY"]

    def get_chat_mutation(self) -> Dict[str, Any]:
        """Get the appropriate chat mutation based on GitLab version"""
        version = self.get_gitlab_version()
        
        # Default to basic template for older versions
        if not version:
            return {
                "query": """
                mutation chat(
                  $question: String!
                  $resourceId: AiModelID
                  $currentFileContext: AiCurrentFileInput
                  $clientSubscriptionId: String
                ) {
                  aiAction(
                    input: {
                      chat: { resourceId: $resourceId, content: $question, currentFile: $currentFileContext }
                      clientSubscriptionId: $clientSubscriptionId
                    }
                  ) {
                    requestId
                    errors
                  }
                }
                """,
                "defaultVariables": {}
            }
            
        # For GitLab 17.10.0 and later
        if self.version_gte(version, MINIMUM_CONVERSATION_TYPE_VERSION):
            return {
                "query": """
                mutation chat(
                  $question: String!
                  $resourceId: AiModelID
                  $currentFileContext: AiCurrentFileInput
                  $clientSubscriptionId: String
                  $platformOrigin: String!
                  $additionalContext: [AiAdditionalContextInput!]
                  $conversationType: AiConversationsThreadsConversationType
                  $threadId: AiConversationThreadID
                ) {
                  aiAction(
                    input: {
                      chat: {
                        resourceId: $resourceId
                        content: $question
                        currentFile: $currentFileContext
                        additionalContext: $additionalContext
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
                """,
                "defaultVariables": {
                    "platformOrigin": PLATFORM_ORIGIN
                }
            }
            
        # For GitLab 17.5.0 and later
        if self.version_gte(version, MINIMUM_ADDITIONAL_CONTEXT_FIELD_VERSION):
            return {
                "query": """
                mutation chat(
                  $question: String!
                  $resourceId: AiModelID
                  $currentFileContext: AiCurrentFileInput
                  $clientSubscriptionId: String
                  $platformOrigin: String!
                  $additionalContext: [AiAdditionalContextInput!]
                ) {
                  aiAction(
                    input: {
                      chat: {
                        resourceId: $resourceId
                        content: $question
                        currentFile: $currentFileContext
                        additionalContext: $additionalContext
                      }
                      clientSubscriptionId: $clientSubscriptionId
                      platformOrigin: $platformOrigin
                    }
                  ) {
                    requestId
                    errors
                  }
                }
                """,
                "defaultVariables": {
                    "platformOrigin": PLATFORM_ORIGIN
                }
            }
            
        # For GitLab 17.3.0 and later
        if self.version_gte(version, MINIMUM_PLATFORM_ORIGIN_FIELD_VERSION):
            return {
                "query": """
                mutation chat(
                  $question: String!
                  $resourceId: AiModelID
                  $currentFileContext: AiCurrentFileInput
                  $clientSubscriptionId: String
                  $platformOrigin: String!
                ) {
                  aiAction(
                    input: {
                      chat: { resourceId: $resourceId, content: $question, currentFile: $currentFileContext }
                      clientSubscriptionId: $clientSubscriptionId
                      platformOrigin: $platformOrigin
                    }
                  ) {
                    requestId
                    errors
                  }
                }
                """,
                "defaultVariables": {
                    "platformOrigin": PLATFORM_ORIGIN
                }
            }
            
        # For GitLab 17.2 and earlier
        return {
            "query": """
            mutation chat(
              $question: String!
              $resourceId: AiModelID
              $currentFileContext: AiCurrentFileInput
              $clientSubscriptionId: String
            ) {
              aiAction(
                input: {
                  chat: { resourceId: $resourceId, content: $question, currentFile: $currentFileContext }
                  clientSubscriptionId: $clientSubscriptionId
                }
              ) {
                requestId
                errors
              }
            }
            """,
            "defaultVariables": {}
        }

    def send_message(self, message: str) -> Optional[str]:
        """
        Send a message to GitLab AI chat and return the response
        """
        client_subscription_id = str(uuid.uuid4())
        
        # Get version to determine which mutation to use
        version = self.get_gitlab_version()
        print(f"GitLab version: {version or 'Unknown'}")
        
        # Get the appropriate mutation based on version
        mutation_template = self.get_chat_mutation()
        mutation = mutation_template["query"]
        default_variables = mutation_template["defaultVariables"]
        
        # Get available conversation types if needed
        conversation_types = []
        if self.version_gte(version or "", MINIMUM_CONVERSATION_TYPE_VERSION):
            conversation_types = self.get_available_conversation_types()
            if self.debug:
                print(f"Available conversation types: {conversation_types}")
        
        # Base variables
        variables = {
            "question": message,
            "clientSubscriptionId": client_subscription_id,
            **default_variables
        }
        
        # Add conversation type if needed
        if self.version_gte(version or "", MINIMUM_CONVERSATION_TYPE_VERSION):
            # Choose the appropriate conversation type
            conversation_type = "DUO_CHAT_LEGACY"  # Default
            if "DUO_CHAT" in conversation_types:
                conversation_type = "DUO_CHAT"
            elif "AGENTIC_CHAT" in conversation_types:
                conversation_type = "AGENTIC_CHAT"
                
            print(f"Using conversation type: {conversation_type}")
            variables["conversationType"] = conversation_type
        
        # If we have a thread ID from a previous message, include it to continue the conversation
        if self.thread_id:
            variables["threadId"] = self.thread_id
        
        print("Sending message to GitLab AI...")
        
        data = self._graphql_request(mutation, variables)
        
        if "errors" in data:
            print(f"Error sending message: {json.dumps(data.get('errors', []), indent=2)}")
            return None
            
        ai_action = data.get("data", {}).get("aiAction", {})
        request_id = ai_action.get("requestId")
        
        if not request_id:
            print("No request ID returned")
            if self.debug:
                print(f"Response: {json.dumps(data, indent=2)}")
            return None
            
        # Store the thread ID for future messages in the same conversation
        if "threadId" in ai_action and ai_action["threadId"]:
            self.thread_id = ai_action["threadId"]
            if self.debug:
                print(f"Thread ID: {self.thread_id}")
            
        self.request_ids.append(request_id)
        if self.debug:
            print(f"Request ID: {request_id}")
        
        # Now poll for the response
        return self._poll_for_response(request_id)
        
    def _poll_for_response(self, request_id: str, max_retries: int = 60, interval: int = 1) -> Optional[str]:
        """Poll for the AI response using the request ID"""
        # Determine which query to use based on version
        version = self.get_gitlab_version()
        
        if self.version_gte(version or "", MINIMUM_ADDITIONAL_CONTEXT_FIELD_VERSION):
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
                  extras {
                    sources
                    additionalContext {
                      id
                      category
                      metadata
                    }
                  }
                }
              }
            }
            """
        else:
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
                  extras {
                    sources
                  }
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
            data = self._graphql_request(query, variables)
            
            if i % 5 == 0:
                print(".", end="", flush=True)
                
            if "errors" in data:
                print(f"\nError polling for response: {json.dumps(data.get('errors', []), indent=2)}")
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

    def clear_chat(self) -> bool:
        """Clear the current chat conversation"""
        if not self.thread_id:
            print("No active conversation to clear")
            return True
            
        # Use the special message for clearing chat
        return self.send_message(SPECIAL_MESSAGES["CLEAR"]) is not None


def setup_config() -> GitLabConfig:
    """Set up the GitLab configuration"""
    print("===== GitLab AI Chat Configuration =====")
    
    # Try to load from environment variables first
    gitlab_url = os.environ.get("GITLAB_URL", "")
    access_token = os.environ.get("GITLAB_TOKEN", "")
    debug = os.environ.get("GITLAB_DEBUG", "").lower() in ["true", "1", "yes"]
    
    if not gitlab_url:
        gitlab_url = input("GitLab URL (e.g., https://gitlab.com): ").strip()
        
    if not access_token:
        access_token = input("GitLab Personal Access Token: ").strip()
        
    debug_input = input("Enable debug mode? (y/N): ").strip().lower()
    if debug_input in ["y", "yes"]:
        debug = True
    
    return GitLabConfig(
        gitlab_url=gitlab_url,
        access_token=access_token,
        debug=debug
    )


def interactive_chat(client: GitLabAIChat):
    """Run an interactive chat session with GitLab AI"""
    print("\n===== GitLab AI Chat =====")
    print("Type 'exit' to quit, 'clear' to start a new conversation, 'debug' to toggle debug mode\n")
    
    # Get user info
    user = client.get_current_user()
    if user:
        print(f"Logged in as: {user.get('name')} (@{user.get('username')})")
    
    while True:
        user_input = input("\nYou: ")
        
        if user_input.lower() in ["exit", "quit", "stop"]:
            break
            
        if user_input.lower() == "clear":
            if client.clear_chat():
                print("Chat conversation cleared")
            continue
            
        if user_input.lower() == "debug":
            client.debug = not client.debug
            print(f"Debug mode {'enabled' if client.debug else 'disabled'}")
            continue
            
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
