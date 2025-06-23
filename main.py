#!/usr/bin/env python3
"""
Main script to run the GitLab AI chat interactive loop.
This script follows the task requirements for interactive task loop with user feedback.
"""

import os
import subprocess
import sys

def check_and_create_userinput_py():
    """Check if userinput.py exists and create it if it doesn't"""
    if not os.path.exists("userinput.py"):
        with open("userinput.py", "w") as f:
            f.write("# userinput.py\nuser_input = input(\"prompt: \")")
        print("Created userinput.py")

def run_gitlab_chat():
    """Run the GitLab AI chat script"""
    print("\nRunning GitLab AI Chat application...")
    try:
        subprocess.run(["python", "gitlab_ai_chat.py"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running GitLab AI Chat: {e}")
        return
    except KeyboardInterrupt:
        print("\nGitLab AI Chat terminated by user.")
        return

def run_interactive_loop():
    """Run the interactive task loop with user feedback"""
    check_and_create_userinput_py()
    
    while True:
        # Run the main task (GitLab AI Chat)
        run_gitlab_chat()
        
        # Ask user for next action
        result = subprocess.run(["python", "userinput.py"], capture_output=True, text=True)
        user_input = result.stdout.strip().replace("prompt: ", "")
        
        if user_input.lower() == "stop":
            print("Exiting the interactive task loop.")
            break
            
        # Process the user input for next task
        if user_input.lower() == "restart":
            print("Restarting GitLab AI Chat...")
            continue
        elif user_input.lower() == "help":
            print("\nCommands available:")
            print("  stop    - Exit the interactive task loop")
            print("  restart - Restart GitLab AI Chat")
            print("  help    - Show this help message")
        else:
            print(f"Unknown command: {user_input}")
            print("Type 'help' for a list of commands.")

if __name__ == "__main__":
    try:
        run_interactive_loop()
    except KeyboardInterrupt:
        print("\nProgram terminated by user.")
        sys.exit(0) 