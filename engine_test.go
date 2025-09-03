package main

import (
	"reflect"
	"testing"
)

func TestParsePlan(t *testing.T) {
	testCases := []struct {
		name     string
		planStr  string
		expected []string
	}{
		{
			name: "Simple plan",
			planStr: `
1. READ_FILE main.go
2. ANALYZE entry point
3. FINISH`,
			expected: []string{"READ_FILE main.go", "ANALYZE entry point", "FINISH"},
		},
		{
			name: "Plan with quoted paths",
			planStr: `
1. READ_FILE "path/to/my file.go"
2. ANALYZE "some subject with spaces"`,
			expected: []string{`READ_FILE "path/to/my file.go"`, `ANALYZE "some subject with spaces"`},
		},
		{
			name:     "Empty plan",
			planStr:  "",
			expected: []string{},
		},
		{
			name:     "Plan with only FINISH",
			planStr:  "1. FINISH",
			expected: []string{"FINISH"},
		},
		{
			name: "Plan with extra whitespace",
			planStr: `
  1.  READ_FILE   main.go
2.ANALYZE    subject`,
			expected: []string{"READ_FILE main.go", "ANALYZE subject"},
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			actual := parsePlan(tc.planStr)
			if !reflect.DeepEqual(actual, tc.expected) {
				t.Errorf("expected: %v, got: %v", tc.expected, actual)
			}
		})
	}
}
