package config

import (
	"bytes"
	"fmt"
	"os"
	"strings"

	"github.com/spf13/viper"
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

// LoadConfig loads the configuration from file and environment variables.
func LoadConfig() error {
	v := viper.New()

	// Set default configuration file
	defaultConfig, err := os.ReadFile("config.default.yaml")
	if err != nil {
		return fmt.Errorf("could not read default config file: %w", err)
	}
	if err := v.ReadConfig(bytes.NewBuffer(defaultConfig)); err != nil {
		return fmt.Errorf("could not parse default config: %w", err)
	}

	// Set up viper to look for a config file named "config.yaml"
	v.SetConfigName("config")
	v.AddConfigPath(".")
	v.SetConfigType("yaml")

	// Attempt to read the user-provided config file and merge it
	if err := v.MergeInConfig(); err != nil {
		if _, ok := err.(viper.ConfigFileNotFoundError); !ok {
			return fmt.Errorf("could not read user config file: %w", err)
		}
	}

	// Set up environment variable overrides
	v.SetEnvPrefix("DEBUGAGENT")
	v.SetEnvKeyReplacer(strings.NewReplacer(".", "_"))
	v.AutomaticEnv()

	// Unmarshal the configuration into the AppConfig struct
	var cfg Config
	if err := v.Unmarshal(&cfg); err != nil {
		return fmt.Errorf("could not unmarshal config: %w", err)
	}

	AppConfig = &cfg
	return nil
}
