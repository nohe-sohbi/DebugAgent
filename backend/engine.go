package main

import (
	"debugagent/config"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	"github.com/sirupsen/logrus"
)

// AnalyzeRequest defines the structure for the API request.
type AnalyzeRequest struct {
	ProjectPath string
	Question    string
}

// AnalysisEngine orchestrates the project analysis.
type AnalysisEngine struct {
	kb           *KnowledgeBase
	ollamaClient *OllamaClient
	request      AnalyzeRequest
}

// StreamingAnalysisEngine orchestrates the project analysis with streaming updates.
type StreamingAnalysisEngine struct {
	kb           *KnowledgeBase
	ollamaClient *OllamaClient
	request      AnalyzeRequest
}

// NewAnalysisEngine creates a new AnalysisEngine.
func NewAnalysisEngine(req AnalyzeRequest) (*AnalysisEngine, error) {
	kb := NewKnowledgeBase(req.ProjectPath)
	ollamaClient, err := NewOllamaClient()
	if err != nil {
		return nil, fmt.Errorf("failed to create Ollama client: %w", err)
	}

	return &AnalysisEngine{
		kb:           kb,
		ollamaClient: ollamaClient,
		request:      req,
	}, nil
}

// RunAnalysis runs the full analysis process.
func (e *AnalysisEngine) RunAnalysis() (string, error) {
	logrus.Info("1. Starting initial project analysis...")
	if err := e.initialAnalysis(); err != nil {
		// Log the error but continue, as some information may have been gathered.
		e.kb.AddNote(fmt.Sprintf("Error during initial analysis: %v", err))
	}

	logrus.Info("2. Starting exploration loop...")
	if err := e.explorationLoop(); err != nil {
		// Log and continue, as we might still be able to provide a partial answer.
		e.kb.AddNote(fmt.Sprintf("Error during exploration loop: %v", err))
	}

	logrus.Info("3. Generating final answer...")
	finalAnswer, err := e.generateFinalAnswer()
	if err != nil {
		return "", fmt.Errorf("failed to generate final answer: %w", err)
	}

	return finalAnswer, nil
}

// initialAnalysis performs the initial analysis of the project.
func (e *AnalysisEngine) initialAnalysis() error {
	// Analyze directory structure
	structure, err := getDirectoryStructure(e.kb.ProjectPath, config.AppConfig.Analysis.MaxDirectoryDepth, 0)
	if err != nil {
		return fmt.Errorf("failed to get directory structure: %w", err)
	}
	e.kb.ProjectStructure = structure
	e.kb.AddHistory("Directory structure analysis complete.")

	// Read README file
	readmePath := filepath.Join(e.kb.ProjectPath, "README.md")
	if _, err := os.Stat(readmePath); err == nil {
		content, err := readFileContent(readmePath)
		if err != nil {
			e.kb.AddNote(fmt.Sprintf("Error reading README: %v", err))
		} else {
			e.kb.AddFileContent(readmePath, content)
			e.kb.ReadmeContent = content[:min(500, len(content))]
			e.kb.AddHistory("README.md file read.")
		}
	}

	// Identify project type
	typePrompt := fmt.Sprintf(`
Initial project context for %s:
Project Structure (partial): %v
---
Based on the structure, what is the type of this project (e.g., Go Backend, React Frontend)?
Be brief (1 sentence).`, filepath.Base(e.kb.ProjectPath), e.kb.ProjectStructure)
	projectType, err := e.ollamaClient.ollamaRequest("You are a software architecture expert.", typePrompt)
	if err == nil {
		e.kb.SetProjectType(strings.TrimSpace(projectType))
		e.kb.AddHistory(fmt.Sprintf("Estimated project type: %s", e.kb.ProjectType))
	}
	return nil
}

// explorationLoop runs the exploration loop.
func (e *AnalysisEngine) explorationLoop() error {
	for i := 0; i < config.AppConfig.Analysis.MaxExplorationIterations; i++ {
		logrus.Infof("--- Iteration %d/%d ---", i+1, config.AppConfig.Analysis.MaxExplorationIterations)

		plan, err := e.planNextSteps()
		if err != nil {
			e.kb.AddNote(fmt.Sprintf("Planning error in iteration %d: %v", i, err))
			continue
		}

		if len(plan) == 0 || (len(plan) == 1 && plan[0] == "FINISH") {
			logrus.Info("Empty or 'FINISH' plan received, ending exploration.")
			break
		}
		e.kb.ExplorationPlan = plan

		e.executePlan(plan)
	}
	return nil
}

// planNextSteps plans the next steps in the exploration.
func (e *AnalysisEngine) planNextSteps() ([]string, error) {
	contextSummary := e.kb.getContextSummary(e.request.Question, config.AppConfig.Analysis.MaxPromptLength)
	planPrompt := fmt.Sprintf(`
Objective: Answer "%s"
Current Context:
%s
---
Propose the next 3-5 logical steps. Use actions: READ_FILE <path>, ANALYZE <subject>, FINISH.
MANDATORY output format: Simple numbered list.
Example:
1. READ_FILE main.go
2. ANALYZE the application entry point
`, e.request.Question, contextSummary)

	planSystemPrompt := "You are a code exploration planner. Respond ONLY with the numbered list of actions."
	rawPlan, err := e.ollamaClient.ollamaRequest(planSystemPrompt, planPrompt)
	if err != nil {
		return nil, err
	}
	return parsePlan(rawPlan), nil
}


func parsePlan(planStr string) []string {
	lines := strings.Split(planStr, "\n")
	plan := make([]string, 0)
	actionRegex := regexp.MustCompile(`^\s*\d+\.\s*(READ_FILE|ANALYZE|FINISH)\s*(.*)$`)

	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		matches := actionRegex.FindStringSubmatch(line)
		if len(matches) > 1 {
			action := strings.TrimSpace(matches[1])
			if action == "FINISH" {
				plan = append(plan, "FINISH")
				break // Stop processing further lines once FINISH is found
			}

			if len(matches) > 2 {
				args := strings.TrimSpace(matches[2])
				if args != "" {
					plan = append(plan, fmt.Sprintf("%s %s", action, args))
				}
			}
		}
	}
	return plan
}

// executePlan executes the given exploration plan.
func (e *AnalysisEngine) executePlan(plan []string) {
	for _, step := range plan {
		logrus.Infof("Executing step: %s", step)
		parts := strings.SplitN(step, " ", 2)
		action := parts[0]
		args := ""
		if len(parts) > 1 {
			args = parts[1]
		}

		switch action {
		case "READ_FILE":
			e.executeReadFile(args)
		case "ANALYZE":
			e.executeAnalyze(args)
		}
	}
}

// executeReadFile reads a file and adds its content to the knowledge base.
func (e *AnalysisEngine) executeReadFile(filePath string) {
	fullPath := filepath.Join(e.kb.ProjectPath, filePath)
	content, err := readFileContent(fullPath)
	if err != nil {
		e.kb.AddNote(fmt.Sprintf("Failed to read '%s': %v", filePath, err))
	} else {
		e.kb.AddFileContent(fullPath, content)
	}
}

// executeAnalyze analyzes a subject and adds the result to the knowledge base.
func (e *AnalysisEngine) executeAnalyze(subject string) {
	analysisPrompt := fmt.Sprintf(`
Context: %s
---
Analyze the following question: "%s"`, e.kb.getContextSummary(e.request.Question, config.AppConfig.Analysis.MaxPromptLength), subject)
	analysisResult, err := e.ollamaClient.ollamaRequest("You are a code analysis assistant.", analysisPrompt)
	if err != nil {
		e.kb.AddNote(fmt.Sprintf("Failed to analyze '%s': %v", subject, err))
	} else {
		e.kb.AddNote(fmt.Sprintf("Analysis of '%s': %s", subject, analysisResult))
	}
}

// generateFinalAnswer generates the final answer based on the collected knowledge.
func (e *AnalysisEngine) generateFinalAnswer() (string, error) {
	finalContext := e.kb.getContextSummary(e.request.Question, config.AppConfig.Analysis.MaxPromptLength)
	finalPrompt := fmt.Sprintf(`
Final collected context:
%s
---
Synthesize all this information to provide a complete and structured answer to the user's initial question: "%s"`, finalContext, e.request.Question)

	return e.ollamaClient.ollamaRequest("You are an expert AI assistant who synthesizes technical information.", finalPrompt)
}

// NewStreamingAnalysisEngine creates a new StreamingAnalysisEngine.
func NewStreamingAnalysisEngine(req AnalyzeRequest) (*StreamingAnalysisEngine, error) {
	kb := NewKnowledgeBase(req.ProjectPath)
	ollamaClient, err := NewOllamaClient()
	if err != nil {
		return nil, fmt.Errorf("failed to create Ollama client: %w", err)
	}

	return &StreamingAnalysisEngine{
		kb:           kb,
		ollamaClient: ollamaClient,
		request:      req,
	}, nil
}

// sendEvent sends a streaming event to the client
func (e *StreamingAnalysisEngine) sendEvent(w http.ResponseWriter, eventType, step, message string, iteration, total int, data string) {
	event := map[string]interface{}{
		"type":      eventType,
		"step":      step,
		"message":   message,
		"iteration": iteration,
		"total":     total,
		"data":      data,
	}
	eventData, _ := json.Marshal(event)
	fmt.Fprintf(w, "data: %s\n\n", eventData)
	if f, ok := w.(http.Flusher); ok {
		f.Flush()
	}
}

// RunStreamingAnalysis runs the full analysis process with streaming updates.
func (e *StreamingAnalysisEngine) RunStreamingAnalysis(w http.ResponseWriter) {
	e.sendEvent(w, "progress", "initial", "Starting initial project analysis...", 0, 0, "")

	if err := e.initialStreamingAnalysis(w); err != nil {
		e.kb.AddNote(fmt.Sprintf("Error during initial analysis: %v", err))
		e.sendEvent(w, "error", "initial", fmt.Sprintf("Error during initial analysis: %v", err), 0, 0, "")
	}

	e.sendEvent(w, "progress", "exploration", "Starting exploration loop...", 0, 0, "")

	if err := e.explorationStreamingLoop(w); err != nil {
		e.kb.AddNote(fmt.Sprintf("Error during exploration loop: %v", err))
		e.sendEvent(w, "error", "exploration", fmt.Sprintf("Error during exploration: %v", err), 0, 0, "")
	}

	e.sendEvent(w, "progress", "final", "Generating final answer...", 0, 0, "")

	finalAnswer, err := e.generateStreamingFinalAnswer(w)
	if err != nil {
		e.sendEvent(w, "error", "final", fmt.Sprintf("Error generating final answer: %v", err), 0, 0, "")
		return
	}

	e.sendEvent(w, "result", "complete", "Analysis completed successfully!", 0, 0, finalAnswer)
}

// initialStreamingAnalysis performs the initial analysis with streaming updates.
func (e *StreamingAnalysisEngine) initialStreamingAnalysis(w http.ResponseWriter) error {
	e.sendEvent(w, "step", "structure", "Analyzing directory structure...", 0, 0, "")

	// Analyze directory structure
	structure, err := getDirectoryStructure(e.kb.ProjectPath, config.AppConfig.Analysis.MaxDirectoryDepth, 0)
	if err != nil {
		return fmt.Errorf("failed to get directory structure: %w", err)
	}
	e.kb.ProjectStructure = structure
	e.kb.AddHistory("Directory structure analysis complete.")

	e.sendEvent(w, "step", "readme", "Reading README file...", 0, 0, "")

	// Read README file
	readmePath := filepath.Join(e.kb.ProjectPath, "README.md")
	if _, err := os.Stat(readmePath); err == nil {
		content, err := readFileContent(readmePath)
		if err != nil {
			e.kb.AddNote(fmt.Sprintf("Error reading README: %v", err))
		} else {
			e.kb.AddFileContent(readmePath, content)
			e.kb.ReadmeContent = content[:min(500, len(content))]
			e.kb.AddHistory("README.md file read.")
			e.sendEvent(w, "step", "readme", "README file processed successfully", 0, 0, "")
		}
	} else {
		e.sendEvent(w, "step", "readme", "No README file found", 0, 0, "")
	}

	e.sendEvent(w, "step", "type", "Identifying project type...", 0, 0, "")

	// Identify project type
	typePrompt := fmt.Sprintf(`
Initial project context for %s:
Project Structure (partial): %v
---
Based on the structure, what is the type of this project (e.g., Go Backend, React Frontend)?
Be brief (1 sentence).`, filepath.Base(e.kb.ProjectPath), e.kb.ProjectStructure)
	projectType, err := e.ollamaClient.ollamaRequest("You are a software architecture expert.", typePrompt)
	if err == nil {
		e.kb.SetProjectType(strings.TrimSpace(projectType))
		e.kb.AddHistory(fmt.Sprintf("Estimated project type: %s", e.kb.ProjectType))
		e.sendEvent(w, "step", "type", fmt.Sprintf("Identified as: %s", e.kb.ProjectType), 0, 0, "")
	}
	return nil
}

// explorationStreamingLoop runs the exploration loop with streaming updates.
func (e *StreamingAnalysisEngine) explorationStreamingLoop(w http.ResponseWriter) error {
	maxIterations := config.AppConfig.Analysis.MaxExplorationIterations
	for i := 0; i < maxIterations; i++ {
		e.sendEvent(w, "step", "iteration", fmt.Sprintf("Planning iteration %d of %d...", i+1, maxIterations), i+1, maxIterations, "")

		plan, err := e.planNextSteps()
		if err != nil {
			e.kb.AddNote(fmt.Sprintf("Planning error in iteration %d: %v", i, err))
			e.sendEvent(w, "error", "planning", fmt.Sprintf("Planning error: %v", err), i+1, maxIterations, "")
			continue
		}

		if len(plan) == 0 || (len(plan) == 1 && plan[0] == "FINISH") {
			e.sendEvent(w, "step", "finish", "Analysis complete - no more steps needed", i+1, maxIterations, "")
			break
		}
		e.kb.ExplorationPlan = plan

		e.executeStreamingPlan(w, plan, i+1, maxIterations)
	}
	return nil
}

// executeStreamingPlan executes the given exploration plan with streaming updates.
func (e *StreamingAnalysisEngine) executeStreamingPlan(w http.ResponseWriter, plan []string, iteration, total int) {
	for stepIndex, step := range plan {
		e.sendEvent(w, "step", "execute", fmt.Sprintf("Executing: %s", step), iteration, total, "")
		parts := strings.SplitN(step, " ", 2)
		action := parts[0]
		args := ""
		if len(parts) > 1 {
			args = parts[1]
		}

		switch action {
		case "READ_FILE":
			e.executeStreamingReadFile(w, args, iteration, total, stepIndex+1, len(plan))
		case "ANALYZE":
			e.executeStreamingAnalyze(w, args, iteration, total, stepIndex+1, len(plan))
		}
	}
}

// executeStreamingReadFile reads a file with streaming updates.
func (e *StreamingAnalysisEngine) executeStreamingReadFile(w http.ResponseWriter, filePath string, iteration, total, stepNum, totalSteps int) {
	e.sendEvent(w, "step", "read", fmt.Sprintf("Reading file: %s", filePath), iteration, total, "")
	fullPath := filepath.Join(e.kb.ProjectPath, filePath)
	content, err := readFileContent(fullPath)
	if err != nil {
		e.kb.AddNote(fmt.Sprintf("Failed to read '%s': %v", filePath, err))
		e.sendEvent(w, "error", "read", fmt.Sprintf("Failed to read %s: %v", filePath, err), iteration, total, "")
	} else {
		e.kb.AddFileContent(fullPath, content)
		e.sendEvent(w, "step", "read", fmt.Sprintf("Successfully read: %s (%d bytes)", filePath, len(content)), iteration, total, "")
	}
}

// executeStreamingAnalyze analyzes a subject with streaming updates.
func (e *StreamingAnalysisEngine) executeStreamingAnalyze(w http.ResponseWriter, subject string, iteration, total, stepNum, totalSteps int) {
	e.sendEvent(w, "step", "analyze", fmt.Sprintf("Analyzing: %s", subject), iteration, total, "")
	analysisPrompt := fmt.Sprintf(`
Context: %s
---
Analyze the following question: "%s"`, e.kb.getContextSummary(e.request.Question, config.AppConfig.Analysis.MaxPromptLength), subject)
	analysisResult, err := e.ollamaClient.ollamaRequest("You are a code analysis assistant.", analysisPrompt)
	if err != nil {
		e.kb.AddNote(fmt.Sprintf("Failed to analyze '%s': %v", subject, err))
		e.sendEvent(w, "error", "analyze", fmt.Sprintf("Analysis failed for %s: %v", subject, err), iteration, total, "")
	} else {
		e.kb.AddNote(fmt.Sprintf("Analysis of '%s': %s", subject, analysisResult))
		e.sendEvent(w, "step", "analyze", fmt.Sprintf("Analysis complete: %s", subject), iteration, total, "")
	}
}

// generateStreamingFinalAnswer generates the final answer with streaming updates.
func (e *StreamingAnalysisEngine) generateStreamingFinalAnswer(w http.ResponseWriter) (string, error) {
	e.sendEvent(w, "step", "synthesis", "Synthesizing collected information...", 0, 0, "")
	finalContext := e.kb.getContextSummary(e.request.Question, config.AppConfig.Analysis.MaxPromptLength)
	finalPrompt := fmt.Sprintf(`
Final collected context:
%s
---
Synthesize all this information to provide a complete and structured answer to the user's initial question: "%s"`, finalContext, e.request.Question)

	e.sendEvent(w, "step", "generating", "Generating final answer with AI...", 0, 0, "")
	return e.ollamaClient.ollamaRequest("You are an expert AI assistant who synthesizes technical information.", finalPrompt)
}

// planNextSteps plans the next steps in the exploration for streaming engine.
func (e *StreamingAnalysisEngine) planNextSteps() ([]string, error) {
	contextSummary := e.kb.getContextSummary(e.request.Question, config.AppConfig.Analysis.MaxPromptLength)
	planPrompt := fmt.Sprintf(`
Objective: Answer "%s"
Current Context:
%s
---
Propose the next 3-5 logical steps. Use actions: READ_FILE <path>, ANALYZE <subject>, FINISH.
MANDATORY output format: Simple numbered list.
Example:
1. READ_FILE main.go
2. ANALYZE the application entry point
`, e.request.Question, contextSummary)

	planSystemPrompt := "You are a code exploration planner. Respond ONLY with the numbered list of actions."
	rawPlan, err := e.ollamaClient.ollamaRequest(planSystemPrompt, planPrompt)
	if err != nil {
		return nil, err
	}
	return parsePlan(rawPlan), nil
}
