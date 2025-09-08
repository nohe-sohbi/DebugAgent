import React, { useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';

function App() {
  const { t } = useTranslation();
  const [question, setQuestion] = useState('');
  const [files, setFiles] = useState([]);
  const [answer, setAnswer] = useState('');
  const [loading, setLoading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isUploading, setIsUploading] = useState(false);
  const [streamingProgress, setStreamingProgress] = useState([]);
  const [currentStep, setCurrentStep] = useState('');
  const [analysisComplete, setAnalysisComplete] = useState(false);
  const [showAnalysisModal, setShowAnalysisModal] = useState(false);
  const [retryCount, setRetryCount] = useState(0);
  const fileInputRef = useRef();
  const eventSourceRef = useRef(null);
  const abortControllerRef = useRef(null);

  // Cleanup on component unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  const handleFileChange = (e) => {
    setFiles([...e.target.files]);
  };

  const handleClearFiles = () => {
    setFiles([]);
    if (fileInputRef.current) {
      fileInputRef.current.value = null;
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    const droppedFiles = Array.from(e.dataTransfer.files);
    setFiles(droppedFiles);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
  };

  const handleDropAreaClick = () => {
    if (fileInputRef.current) {
      fileInputRef.current.click();
    }
  };

  const handleSubmit = () => {
    if (files.length === 0) {
      alert(t('pleaseSelectProject'));
      return;
    }

    // Clean up previous connections
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    // Reset states
    setAnswer('');
    setStreamingProgress([]);
    setCurrentStep('');
    setAnalysisComplete(false);
    setUploadProgress(0);
    setIsUploading(true);
    setLoading(false);
    setShowAnalysisModal(true);
    setRetryCount(0);

    // Create abort controller for this request
    abortControllerRef.current = new AbortController();

    // First, upload files using regular POST
    const formData = new FormData();
    formData.append('question', question);
    for (const file of files) {
      formData.append('files', file, file.webkitRelativePath || file.name);
    }

    // Use fetch for streaming analysis
    fetch('http://localhost:8080/analyze-stream', {
      method: 'POST',
      body: formData,
      signal: abortControllerRef.current.signal
    })
    .then(response => {
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      setIsUploading(false);
      setLoading(true);
      
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      
      const readStream = () => {
        reader.read().then(({ done, value }) => {
          if (done) {
            setLoading(false);
            return;
          }
          
          const chunk = decoder.decode(value);
          const lines = chunk.split('\n');
          
          lines.forEach(line => {
            if (line.startsWith('data: ')) {
              try {
                const eventData = JSON.parse(line.slice(6));
                handleStreamEvent(eventData);
              } catch (e) {
                console.warn('Failed to parse SSE data:', line);
              }
            }
          });
          
          readStream();
        }).catch(error => {
          if (error.name === 'AbortError') {
            console.log('Stream aborted');
            return;
          }
          console.error('Stream reading error:', error);
          handleStreamError(error);
        });
      };
      
      readStream();
    })
    .catch(error => {
      if (error.name === 'AbortError') {
        console.log('Request aborted');
        return;
      }
      console.error('Fetch error:', error);
      handleStreamError(error);
    });
  };

  const handleStreamError = (error) => {
    console.error('Stream error:', error);
    setIsUploading(false);

    // Only close modal on critical errors, not transient ones
    if (retryCount < 3 && !error.message.includes('abort')) {
      setRetryCount(prev => prev + 1);
      setCurrentStep(`Connection issue, retrying... (${retryCount + 1}/3)`);

      // Retry after a short delay
      setTimeout(() => {
        handleSubmit();
      }, 2000);
    } else {
      setLoading(false);
      setShowAnalysisModal(false);
      setCurrentStep('Error: ' + error.message);
    }
  };

  const handleStreamEvent = (eventData) => {
    console.log('Stream event:', eventData);
    
    setStreamingProgress(prev => [...prev, eventData]);
    
    switch (eventData.type) {
      case 'progress':
        setCurrentStep(`${eventData.message}`);
        break;
      case 'step':
        setCurrentStep(`${eventData.message}`);
        break;
      case 'result':
        setAnswer(eventData.data);
        setCurrentStep('Analysis completed!');
        setAnalysisComplete(true);
        setLoading(false);
        setShowAnalysisModal(false);
        break;
      case 'error':
        setCurrentStep(`Error: ${eventData.message}`);
        // Don't immediately close on backend errors, let retry logic handle it
        if (eventData.message.includes('fatal') || eventData.message.includes('critical')) {
          setLoading(false);
          setShowAnalysisModal(false);
        }
        break;
      default:
        break;
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center p-4">
      <div className="bg-white p-8 rounded-xl shadow-xl w-full max-w-4xl border border-gray-200">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-gray-800 mb-2">{t('projectAnalysis')}</h1>
          <p className="text-gray-600">Upload your project files and get AI-powered insights</p>
        </div>

        <div className="mb-8">
          <label htmlFor="question" className="block text-gray-800 text-sm font-semibold mb-3">
            {t('yourQuestion')}
          </label>
          <textarea
            id="question"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            className="w-full py-3 px-4 border-2 border-gray-200 rounded-lg text-gray-700 leading-relaxed focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-200 transition-all h-28 resize-none"
            placeholder={t('questionPlaceholder')}
          />
        </div>

        <div className="mb-6">
          <label className="block text-gray-800 text-sm font-semibold mb-3">
            {t('projectFiles')}
          </label>
          <div
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onClick={handleDropAreaClick}
            className="border-dashed border-2 border-blue-300 p-8 rounded-xl text-center cursor-pointer hover:border-blue-500 hover:bg-blue-50 transition-all duration-200 bg-blue-25"
          >
            <div className="flex flex-col items-center">
              <svg className="w-12 h-12 text-blue-400 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
              <p className="text-gray-700 mb-1 font-medium">{t('dragAndDrop')}</p>
              <p className="text-sm text-gray-500">or click to select files</p>
            </div>
          </div>
        </div>

        <div className="mb-6">
          <label className="block text-gray-800 text-sm font-semibold mb-3">
            {t('orSelectFiles')}
          </label>
          <input
            type="file"
            multiple
            webkitdirectory="true"
            onChange={handleFileChange}
            ref={fileInputRef}
            className="block w-full text-sm text-gray-600 file:mr-4 file:py-3 file:px-6 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-blue-500 file:text-white hover:file:bg-blue-600 file:cursor-pointer file:transition-colors"
          />
        </div>

        {files.length > 0 && (
          <div className="mb-6">
            <div className="flex justify-between items-center mb-3">
              <h3 className="text-lg font-semibold text-gray-800">{t('selectedFiles')}</h3>
              <button
                onClick={handleClearFiles}
                className="px-3 py-1 text-sm text-red-600 hover:text-red-800 hover:bg-red-50 rounded-lg transition-colors"
              >
                {t('clearSelection')}
              </button>
            </div>
            <div className="bg-gray-50 p-4 rounded-lg max-h-40 overflow-y-auto border border-gray-200">
              {files.map((file, index) => (
                <div key={index} className="flex items-center text-sm text-gray-700 mb-2 last:mb-0">
                  <svg className="w-4 h-4 text-blue-500 mr-2 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  <span className="truncate">{file.webkitRelativePath || file.name}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="flex items-center justify-center">
          <button
            onClick={handleSubmit}
            className="bg-gradient-to-r from-blue-500 to-blue-600 hover:from-blue-600 hover:to-blue-700 text-white font-semibold py-3 px-8 rounded-lg focus:outline-none focus:ring-4 focus:ring-blue-200 disabled:from-gray-400 disabled:to-gray-500 disabled:cursor-not-allowed transition-all duration-200 shadow-lg hover:shadow-xl"
            disabled={isUploading || loading}
          >
            <div className="flex items-center">
              {(isUploading || loading) && (
                <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
              )}
              {isUploading
                ? `${t('uploading')}... ${uploadProgress}%`
                : loading
                ? t('analyzing')
                : t('analyzeProject')}
            </div>
          </button>
        </div>

        {isUploading && (
          <div className="mt-6">
            <div className="flex justify-between text-sm text-gray-600 mb-2">
              <span>Uploading files...</span>
              <span>{uploadProgress}%</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-3 shadow-inner">
              <div
                className="bg-gradient-to-r from-blue-500 to-blue-600 h-3 rounded-full transition-all duration-300 shadow-sm"
                style={{ width: `${uploadProgress}%` }}
              ></div>
            </div>
          </div>
        )}

        {/* Streaming Progress Display */}
        {showAnalysisModal && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
            <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[80vh] overflow-hidden">
              <div className="flex justify-between items-center p-6 border-b border-gray-200">
                <h3 className="text-xl font-semibold text-gray-800">Analysis Progress</h3>
                <button
                  onClick={() => {
                    setShowAnalysisModal(false);
                    setLoading(false);
                    if (abortControllerRef.current) {
                      abortControllerRef.current.abort();
                    }
                  }}
                  className="text-gray-400 hover:text-gray-600 text-2xl font-bold w-8 h-8 flex items-center justify-center rounded-full hover:bg-gray-100 transition-colors"
                  title="Close analysis"
                >
                  ×
                </button>
              </div>
              <div className="p-6">
                <div className="bg-gradient-to-r from-blue-50 to-indigo-50 p-4 rounded-lg border border-blue-200">
                  <div className="mb-4">
                    <div className="flex items-center">
                      <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-blue-500 mr-3"></div>
                      <span className="text-blue-700 font-medium">{currentStep}</span>
                    </div>
                  </div>

                  {/* Progress Log */}
                  <div className="max-h-60 overflow-y-auto bg-white p-4 rounded-lg border border-gray-200 text-sm">
                    {streamingProgress.map((event, index) => (
                      <div key={index} className={`mb-2 last:mb-0 p-2 rounded ${
                        event.type === 'error' ? 'bg-red-50 text-red-700 border-l-4 border-red-400' :
                        event.type === 'result' ? 'bg-green-50 text-green-700 border-l-4 border-green-400' :
                        event.type === 'step' ? 'bg-blue-50 text-blue-700 border-l-4 border-blue-400' :
                        'bg-gray-50 text-gray-700 border-l-4 border-gray-400'
                      }`}>
                        {event.iteration > 0 && (
                          <span className="text-gray-500 text-xs mr-2 font-mono">[{event.iteration}/{event.total}]</span>
                        )}
                        <span className="font-semibold">{event.step}:</span> {event.message}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {answer && (
          <div className="mt-8">
            <h2 className="text-2xl font-bold mb-4 text-gray-800 flex items-center">
              <svg className="w-6 h-6 text-green-500 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              {t('analysisResult')}
            </h2>
            <div className="bg-gradient-to-r from-green-50 to-blue-50 p-6 rounded-xl border border-green-200 shadow-sm">
              <div className="prose prose-sm max-w-none">
                <p className="text-gray-800 leading-relaxed whitespace-pre-wrap">{answer}</p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
