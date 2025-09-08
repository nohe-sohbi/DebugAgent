package models

// AnalyzeRequest defines the structure for the API request.
type AnalyzeRequest struct {
	ProjectPath string
	Question    string
}

// AnalyzeResponse defines the structure for the API response.
type AnalyzeResponse struct {
	Answer string `json:"answer"`
}
