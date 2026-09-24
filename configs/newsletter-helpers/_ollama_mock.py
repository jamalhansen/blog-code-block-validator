import sys

class MockOllama:
    def __init__(self):
        # Specific patterns are checked before generic ones
        self.responses = [
            ("Summarize", "Mock summary."),
            ("Rate relevance", " 7 "),
            ("Article 1", " 5 "),
            ("Article 2", " 9 "),
            ("Write a tweet", "This is a mock tweet about AI."),
            ("Edit this to be under 280 characters", "Mock compliant tweet."),
            ("Review this Python function", "No bugs found in mock.")
        ]
        self.default_response = {"message": {"content": "Default mock response"}}

    def chat(self, model, messages):
        prompt = messages[-1]['content']
        for key, content in self.responses:
            if key in prompt:
                return {"message": {"content": content}}
        return self.default_response

# Register as the 'ollama' module
sys.modules['ollama'] = MockOllama()
