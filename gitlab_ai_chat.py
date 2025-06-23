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
}

# API polling settings
API_POLLING = {
    'interval': 2,  # seconds
    'max_retries': 30,
}


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
        self.debug = config.debug
        self.current_user_id = None
        
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
                verify=False,  # Disable SSL verification
                timeout=30  # Add timeout to prevent hanging requests
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
        
        user_data = data.get("data", {}).get("currentUser")
        if user_data and "id" in user_data:
            self.current_user_id = user_data["id"]
            
        return user_data

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

    def send_message(self, message: str) -> Optional[str]:
        """
        Send a message to GitLab AI chat and return the response
        """
        client_subscription_id = str(uuid.uuid4())
        
        # Get available conversation types
        conversation_types = self.get_available_conversation_types()
        if self.debug:
            print(f"Available conversation types: {conversation_types}")
        
        # Choose the appropriate conversation type
        conversation_type = "DUO_CHAT_LEGACY"  # Default
        if "DUO_CHAT" in conversation_types:
            conversation_type = "DUO_CHAT"
        elif "AGENTIC_CHAT" in conversation_types:
            conversation_type = "AGENTIC_CHAT"
                
        print(f"Using conversation type: {conversation_type}")
        
        # GraphQL mutation for GitLab 17.11.3-ee
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
        
        # Base variables
        variables = {
            "question": message,
            "clientSubscriptionId": client_subscription_id,
            "platformOrigin": PLATFORM_ORIGIN,
            "conversationType": conversation_type
        }
        
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
        
        # Try to use websocket connection first if supported
        if self.current_user_id:
            try:
                response = self._try_websocket_connection(request_id, client_subscription_id)
                if response:
                    return response
            except Exception as e:
                if self.debug:
                    print(f"Websocket connection failed: {str(e)}")
                print("Falling back to polling for response...")
        
        # Fall back to polling
        return self._pull_ai_message(request_id, "ASSISTANT")
        
    def _try_websocket_connection(self, request_id: str, subscription_id: str) -> Optional[str]:
        """Try to use websocket connection to get streaming response"""
        # This is a placeholder for websocket implementation
        # In a real implementation, you would use a websocket library to connect to GitLab's ActionCable
        # and subscribe to the GraphqlChannel with the aiCompletionResponse subscription
        return None
        
    def _pull_ai_message(self, request_id: str, role: str) -> Optional[str]:
        """Pull AI message using the pull handler pattern from the VS Code extension"""
        print("Waiting for response", end="", flush=True)
        
        for retry in range(API_POLLING['max_retries']):
            print(".", end="", flush=True)
            
            response = self._get_ai_message(request_id, role)
            
            if response:
                print("\n")  # Add a newline after the progress dots
                return response
                
            # If we've tried several times, try alternative approaches
            if retry == 10:
                print("\nTrying alternative approach...")
                alt_response = self._try_alternative_approaches(request_id)
                if alt_response:
                    return alt_response
                    
            time.sleep(API_POLLING['interval'])
            
        print("\nReached timeout while fetching response.")
        return None
        
    def _get_ai_message(self, request_id: str, role: str) -> Optional[str]:
        """Get AI message from GitLab API"""
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
        
        variables = {
            "requestIds": [request_id],
            "roles": [role]
        }
        
        try:
            data = self._graphql_request(query, variables)
            
            if "errors" in data:
                if self.debug:
                    print(f"\nGraphQL errors: {json.dumps(data.get('errors', []), indent=2)}")
                return None
                
            nodes = data.get("data", {}).get("aiMessages", {}).get("nodes", [])
            
            for node in nodes:
                if node.get("role") == role.lower() and node.get("content"):
                    return node.get("content")
                    
            return None
        except Exception as e:
            if self.debug:
                print(f"\nError getting AI message: {str(e)}")
            return None
            
    def _try_alternative_approaches(self, request_id: str) -> Optional[str]:
        """Try alternative approaches to get the AI response"""
        # Try different query structures
        approaches = [
            self._try_direct_ai_message_query,
            self._try_thread_messages_query,
            self._try_conversation_query
        ]
        
        for approach in approaches:
            try:
                response = approach(request_id)
                if response:
                    return response
            except Exception as e:
                if self.debug:
                    print(f"Alternative approach error: {str(e)}")
                    
        return None
        
    def _try_direct_ai_message_query(self, request_id: str) -> Optional[str]:
        """Try querying the AI message directly by ID"""
        query = """
        query getAiMessage($id: ID!) {
          aiMessage(id: $id) {
            requestId
            role
            content
            timestamp
            errors
          }
        }
        """
        
        variables = {
            "id": request_id
        }
        
        data = self._graphql_request(query, variables)
        
        if "errors" in data:
            return None
            
        ai_message = data.get("data", {}).get("aiMessage", {})
        if ai_message and ai_message.get("role") == "assistant" and ai_message.get("content"):
            return ai_message.get("content")
            
        return None
        
    def _try_thread_messages_query(self, request_id: str) -> Optional[str]:
        """Try querying the thread messages if we have a thread ID"""
        if not self.thread_id:
            return None
            
        query = """
        query getThreadMessages($threadId: AiConversationThreadID!) {
          aiConversationThread(id: $threadId) {
            messages {
              nodes {
                requestId
                role
                content
                timestamp
              }
            }
          }
        }
        """
        
        variables = {
            "threadId": self.thread_id
        }
        
        data = self._graphql_request(query, variables)
        
        if "errors" in data:
            return None
            
        nodes = data.get("data", {}).get("aiConversationThread", {}).get("messages", {}).get("nodes", [])
        
        # Find the most recent assistant message
        assistant_messages = [node for node in nodes if node.get("role") == "assistant"]
        if assistant_messages:
            # Sort by timestamp (newest first)
            assistant_messages.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
            return assistant_messages[0].get("content")
            
        return None
        
    def _try_conversation_query(self, request_id: str) -> Optional[str]:
        """Try querying the conversation if we have a thread ID"""
        if not self.thread_id:
            return None
            
        query = """
        query getConversation($threadId: AiConversationThreadID!) {
          aiConversationThread(id: $threadId) {
            conversation {
              lastMessage {
                role
                content
              }
            }
          }
        }
        """
        
        variables = {
            "threadId": self.thread_id
        }
        
        data = self._graphql_request(query, variables)
        
        if "errors" in data:
            return None
            
        last_message = data.get("data", {}).get("aiConversationThread", {}).get("conversation", {}).get("lastMessage", {})
        
        if last_message and last_message.get("role") == "assistant" and last_message.get("content"):
            return last_message.get("content")
            
        return None

    def clear_chat(self) -> bool:
        """Clear the current chat conversation"""
        if not self.thread_id:
            print("No active conversation to clear")
            return True
            
        # Use the special message for clearing chat
        result = self.send_message(SPECIAL_MESSAGES["CLEAR"])
        if result is not None:
            self.thread_id = None
            self.request_ids = []
            return True
        return False


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
