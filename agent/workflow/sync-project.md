---
description: Sync project agent configuration with global startup templates
---

# Sync Project Workflow

This workflow updates the local agent configuration (`agent/`, `.cursorrules`, `GEMINI.md`) from the global startup templates.

1. Copy Global Rules
// turbo
2. Run the update command
   ```bash
   cp ~/Documents/startup/GEMINI.md .
   cp ~/Documents/startup/agent.md .
   cp ~/Documents/startup/.cursorrules .
   cp -r ~/Documents/startup/agent/rules/* agent/rules/
   cp -r ~/Documents/startup/agent/workflow/* agent/workflow/
   ```
