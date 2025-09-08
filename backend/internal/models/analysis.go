package models

// AnalysisEngine orchestrates the project analysis.
type AnalysisEngine struct {
	KB           *KnowledgeBase
	LLMClient    interface{} // LLM client interface (will be properly typed)
	Request      AnalyzeRequest
	FileResolver interface{} // FileResolver interface
}

// StreamingAnalysisEngine orchestrates the project analysis with streaming updates.
type StreamingAnalysisEngine struct {
	KB           *KnowledgeBase
	LLMClient    interface{} // LLM client interface (will be properly typed)
	Request      AnalyzeRequest
	FileResolver interface{} // FileResolver interface
}

// DependencyFileMapping defines fallback strategies for different file types.
var DependencyFileMapping = map[string][]string{
	"composer": {"composer.json", "composer.lock"},
	"npm":      {"package.json", "package-lock.json", "yarn.lock"},
	"python":   {"requirements.txt", "pyproject.toml", "setup.py", "Pipfile"},
	"go":       {"go.mod", "go.sum"},
	"rust":     {"Cargo.toml", "Cargo.lock"},
	"java":     {"pom.xml", "build.gradle", "build.gradle.kts"},
	"dotnet":   {"*.csproj", "*.sln", "project.json"},
	"ruby":     {"Gemfile", "Gemfile.lock", "*.gemspec"},
}
