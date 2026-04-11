# Testing Obsidian Code Blocks with `blog-validate`

This guide explains how to test code blocks in your Obsidian vault using a separate repository for configurations and mocks, triggered directly from Obsidian.

## 1. Prerequisites
- **Install `blog-validate` globally:**
  ```bash
  cd /path/to/blog-code-block-validator
  uv tool install .
  ```

## 2. Setup the Separate Test Repository
Create a new directory (e.g., `brainsync-tests`) outside of your vault and this validator repo.

### A. Create `blog-validate.toml`
In `brainsync-tests/`, create `blog-validate.toml`:
```toml
[blog]
# Path to your vault's newsletter patterns
content_path = "../vaults/BrainSync/newsletter/patterns"
# Use 'flat' layout for standard Obsidian .md files
layout = "flat"
```

### B. Add Mocks (Helpers)
Create a `blog-validate-helpers/` directory in `brainsync-tests/`.
Add any mocks your code needs. For example, `_ollama_mock.py`:
```python
import sys
from unittest.mock import MagicMock

# Mock ollama module
mock_ollama = MagicMock()
mock_ollama.chat.return_value = {'message': {'content': ' 7 '}}
sys.modules['ollama'] = mock_ollama

# Add any other global mocks or fixtures here
```
*Files starting with `_` are automatically executed before every test.*

## 3. Obsidian Integration
To trigger tests from within Obsidian:

1.  **Install the "Shell commands" plugin** in Obsidian.
2.  **Create a new Shell Command:**
    - **Command:** `cd /path/to/your/brainsync-tests && blog-validate check --post {{title}}`
    - **Variable:** `{{title}}` in Obsidian refers to the filename without extension (e.g., `pattern-01-harness-judgment`), which matches the `slug` extracted by the validator.
3.  **Assign a Hotkey:** Go to Obsidian hotkey settings and assign a shortcut (e.g., `Cmd+Option+T`) to your new shell command.

Now, whenever you are editing a pattern in Obsidian, you can press your hotkey to validate its code blocks against your mocks.
