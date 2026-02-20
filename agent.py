import ollama

# 1. Define the tools (The "Hands" you give the model)
def read_file(filepath):
    """Reads a file from the local system."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {str(e)}"

def write_file(filepath, content):
    """Writes content to a file. WARNING: Overwrites existing files."""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Successfully wrote to {filepath}"
    except Exception as e:
        return f"Error writing file: {str(e)}"

# 2. Main Chat Loop
def run_chat():
    print("🤖 File Agent Initialized. (Type 'quit' to exit)")
    print("⚠️  Warning: This agent can OVERWRITE your files. Use with caution.\n")
    
    # History of the conversation
    messages = []

    while True:
        user_input = input("You: ")
        if user_input.lower() in ['quit', 'exit']: break

        # Add user message to history
        messages.append({'role': 'user', 'content': user_input})

        # Send to Ollama with access to our tools
        response = ollama.chat(
            model='glm-4.7:cloud', # Make sure you have this model pulled
            messages=messages,
            tools=[read_file, write_file], # <--- Giving the tools here
        )

        # Check if the model wants to use a tool
        if response.message.tool_calls:
            for tool in response.message.tool_calls:
                
                # Perform the actual file operation
                func_name = tool.function.name
                args = tool.function.arguments
                print(f"⚙️  Model is calling tool: {func_name} on {args.get('filepath')}")

                if func_name == 'read_file':
                    output = read_file(args['filepath'])
                elif func_name == 'write_file':
                    output = write_file(args['filepath'], args['content'])
                else:
                    output = "Error: Unknown tool"

                # Feed the tool output back to the model so it knows what happened
                messages.append(response.message)
                messages.append({'role': 'tool', 'content': output, 'name': func_name})

            # Get the model's final response after the tool usage
            final_response = ollama.chat(model='llama3.2', messages=messages)
            print(f"Agent: {final_response.message.content}")
            messages.append(final_response.message)

        else:
            # Standard response if no file access was needed
            print(f"Agent: {response.message.content}")
            messages.append(response.message)

if __name__ == "__main__":
    run_chat()