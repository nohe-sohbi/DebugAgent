package logging

import (
	"debugagent/config"
	"io"
	"os"
	"strings"

	"github.com/sirupsen/logrus"
)

// InitLogger initializes the logger based on the configuration.
func InitLogger() {
	cfg := config.AppConfig.Logging

	// Set log level
	level, err := logrus.ParseLevel(cfg.Level)
	if err != nil {
		logrus.Warnf("Invalid log level '%s', using 'info' instead. Error: %v", cfg.Level, err)
		level = logrus.InfoLevel
	}
	logrus.SetLevel(level)

	// Set log format
	switch strings.ToLower(cfg.Format) {
	case "json":
		logrus.SetFormatter(&logrus.JSONFormatter{})
	default:
		logrus.SetFormatter(&logrus.TextFormatter{
			FullTimestamp: true,
		})
	}

	// Set log output
	var output io.Writer
	switch strings.ToLower(cfg.Output) {
	case "stdout":
		output = os.Stdout
	case "stderr":
		output = os.Stderr
	default:
		file, err := os.OpenFile(cfg.Output, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0666)
		if err != nil {
			logrus.Warnf("Failed to open log file '%s', using 'stdout' instead. Error: %v", cfg.Output, err)
			output = os.Stdout
		} else {
			output = file
		}
	}
	logrus.SetOutput(output)

	logrus.Info("Logger initialized successfully")
}
