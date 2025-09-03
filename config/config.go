package config

import (
	"os"
	"path/filepath"

	"gopkg.in/yaml.v3"
)

// ServerConfig defines the server configuration.
type ServerConfig struct {
	Port int `yaml:"port"`
}

// OllamaConfig defines the Ollama configuration.
type OllamaConfig struct {
	Host  string `yaml:"host"`
	Model string `yaml:"model"`
}

// AnalysisConfig defines the analysis parameters.
type AnalysisConfig struct {
	MaxExplorationIterations int    `yaml:"max_exploration_iterations"`
	MaxDirectoryDepth        int    `yaml:"max_directory_depth"`
	MaxFileReadSize          int64  `yaml:"max_file_read_size"`
	MaxPromptLength          int    `yaml:"max_prompt_length"`
}

// ExplorerConfig defines the file explorer configuration.
type ExplorerConfig struct {
	IgnoreDirs       []string `yaml:"ignore_dirs"`
	IgnorePrefixes   []string `yaml:"ignore_prefixes"`
	IgnoreExtensions []string `yaml:"ignore_extensions"`
}

// LoggingConfig defines the logging configuration.
type LoggingConfig struct {
	Level  string `yaml:"level"`
	Format string `yaml:"format"`
	Output string `yaml:"output"`
}

// Config is the top-level configuration struct.
type Config struct {
	Server   ServerConfig   `yaml:"server"`
	Ollama   OllamaConfig   `yaml:"ollama"`
	Analysis AnalysisConfig `yaml:"analysis"`
	Explorer ExplorerConfig `yaml:"explorer"`
	Logging  LoggingConfig  `yaml:"logging"`
}

// AppConfig holds the loaded configuration.
var AppConfig *Config

// LoadConfig loads the configuration from the config.yaml file.
func LoadConfig() error {
	// Find the root directory of the project
	// This is a bit of a hack, but it works for this project structure.
	// A more robust solution would be to use build tags or other methods.
	goModPath, err := findGoMod()
	if err != nil {
		return err
	}
	rootDir := filepath.Dir(goModPath)
	configPath := filepath.Join(rootDir, "config.yaml")

	data, err := os.ReadFile(configPath)
	if err != nil {
		return err
	}

	var cfg Config
	if err := yaml.Unmarshal(data, &cfg); err != nil {
		return err
	}

	AppConfig = &cfg
	return nil
}

// findGoMod finds the path to the go.mod file.
func findGoMod() (string, error) {
	dir, err := os.Getwd()
	if err != nil {
		return "", err
	}

	for {
		goModPath := filepath.Join(dir, "go.mod")
		if _, err := os.Stat(goModPath); err == nil {
			return goModPath, nil
		}

		parent := filepath.Dir(dir)
		if parent == dir {
			return "", os.ErrNotExist
		}
		dir = parent
	}
}
