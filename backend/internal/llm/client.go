package llm

// Client defines the interface for LLM clients.
type Client interface {
	// Request sends a request to the LLM with system message and user prompt.
	Request(systemMessage, userPrompt string) (string, error)
	
	// StreamRequest sends a streaming request to the LLM (for future implementation).
	StreamRequest(systemMessage, userPrompt string, callback func(string)) error
}
