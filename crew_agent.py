import os
from crewai import Agent, Crew, Process, Task, LLM
from crewai.tools import tool

# 1. Point CrewAI directly to your local Ornith model in VRAM
# We forcefully set the 16k context to allow code file ingestion
local_ornith = LLM(
    model="ollama/ornith:9b-q4_K_M",
    base_url="http://localhost:11434",
    config={
        "options": {
            "num_ctx": 16384,
            "temperature": 0.3
        }
    }
)

# 2. Build the Bare-Metal file tools (No Docker needed)
@tool("Read Code File")
def read_code_file(file_name: str) -> str:
    """Reads the text content of a code script from your working directory."""
    try:
        with open(file_name, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error opening file: {str(e)}"

@tool("Save New Code File")
def save_code_file(file_name: str, code_content: str) -> str:
    """Saves or overwrites a Python file with new clean programming blocks."""
    try:
        with open(file_name, "w", encoding="utf-8") as f:
            f.write(code_content)
        return f"Success: written code data to {file_name}"
    except Exception as e:
        return f"Write Error: {str(e)}"

# 3. Create the Main A2A Orchestrator Agent
# Since Ornith is a 3-in-1 self-scaffolding model, this single Agent handles
# architecture, execution, and validation internally.
architect_agent = Agent(
    role="Principal AI Engineer",
    goal="Analyze existing local project scripts and generate flawless functional upgrades.",
    backstory="You are an expert systems engineer. You leverage your self-scaffolding training to run checks before outputting code.",
    verbose=True,
    tools=[read_code_file, save_code_file],
    llm=local_ornith
)

# 4. Define the Automation Task
code_audit_task = Task(
    description=(
        "Analyze the ported FluidVoice Windows scripts: settings.py, main.py, transcription.py, hotkey_manager.py, "
        "overlay.py, llm_client.py, terminal_service.py, chat_history.py, text_injection.py, and ui/settings_window.py. "
        "Verify their structural integrity and confirm that the macOS features (Command Mode, Edit/Rewrite Mode, "
        "Custom Dictionary post-replacements, File Transcription progress, and Stats) have been correctly integrated."
    ),
    expected_output="A verification report confirming the successful migration of macOS FluidVoice features to Windows.",
    agent=architect_agent
)

# 5. Initialize and Launch the Crew
coding_crew = Crew(
    agents=[architect_agent],
    tasks=[code_audit_task],
    process=Process.sequential
)

if __name__ == "__main__":
    print("🚀 Initializing Bare-Metal Agent Pipeline with Ornith 9B...")
    result = coding_crew.kickoff()
    print("\n🏁 PIPELINE EXECUTION COMPLETE:")
    print(result)
