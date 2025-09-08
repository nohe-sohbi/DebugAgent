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
  const fileInputRef = useRef();
  const eventSourceRef = useRef(null);

  // Cleanup on component unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
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

  const handleSubmit = () => {
    if (files.length === 0) {
      alert(t('pleaseSelectProject'));
      return;
    }

    // Clean up previous EventSource if exists
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    // Reset states
    setAnswer('');
    setStreamingProgress([]);
    setCurrentStep('');
    setAnalysisComplete(false);
    setUploadProgress(0);
    setIsUploading(true);
    setLoading(false);

    // First, upload files using regular POST
    const formData = new FormData();
    formData.append('question', question);
    for (const file of files) {
      formData.append('files', file, file.webkitRelativePath || file.name);
    }

    // Use fetch for streaming analysis
    fetch('http://localhost:8080/analyze-stream', {
      method: 'POST',
      body: formData
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
          console.error('Stream reading error:', error);
          setLoading(false);
          setCurrentStep('Error: ' + error.message);
        });
      };
      
      readStream();
    })
    .catch(error => {
      console.error('Fetch error:', error);
      setIsUploading(false);
      setLoading(false);
      setCurrentStep('Error: ' + error.message);
    });
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
        break;
      case 'error':
        setCurrentStep(`Error: ${eventData.message}`);
        setLoading(false);
        break;
      default:
        break;
    }
  };

  return (
    <div className="min-h-screen bg-gray-100 flex items-center justify-center">
      <div className="bg-white p-8 rounded-lg shadow-md w-full max-w-2xl">
        <h1 className="text-2xl font-bold mb-6 text-center text-gray-700">{t('projectAnalysis')}</h1>

        <div className="mb-6">
          <label htmlFor="question" className="block text-gray-700 text-sm font-bold mb-2">
            {t('yourQuestion')}
          </label>
          <textarea
            id="question"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            className="shadow appearance-none border rounded w-full py-2 px-3 text-gray-700 leading-tight focus:outline-none focus:shadow-outline h-24"
            placeholder={t('questionPlaceholder')}
          />
        </div>

        <div className="mb-4">
          <label className="block text-gray-700 text-sm font-bold mb-2">
            {t('projectFiles')}
          </label>
          <div
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            className="border-dashed border-2 border-gray-300 p-6 rounded-lg text-center cursor-pointer hover:border-gray-500"
          >
            <p className="text-gray-500">{t('dragAndDrop')}</p>
          </div>
        </div>

        <div className="mb-6">
          <label className="block text-gray-700 text-sm font-bold mb-2">
            {t('orSelectFiles')}
          </label>
          <input
            type="file"
            multiple
            webkitdirectory="true"
            onChange={handleFileChange}
            ref={fileInputRef}
            className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
          />
        </div>

        {files.length > 0 && (
          <div className="mb-4">
            <div className="flex justify-between items-center mb-2">
              <h3 className="text-lg font-semibold text-gray-700">{t('selectedFiles')}</h3>
              <button
                onClick={handleClearFiles}
                className="text-sm text-red-500 hover:text-red-700"
              >
                {t('clearSelection')}
              </button>
            </div>
            <ul>
              {files.map((file, index) => (
                <li key={index} className="text-gray-600">{file.name}</li>
              ))}
            </ul>
          </div>
        )}

        <div className="flex items-center justify-center">
          <button
            onClick={handleSubmit}
            className="bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded focus:outline-none focus:shadow-outline disabled:bg-blue-300"
            disabled={isUploading || loading}
          >
            {isUploading
              ? `${t('uploading')}... ${uploadProgress}%`
              : loading
              ? t('analyzing')
              : t('analyzeProject')}
          </button>
        </div>

        {isUploading && (
          <div className="w-full bg-gray-200 rounded-full h-2.5 mt-4">
            <div
              className="bg-blue-600 h-2.5 rounded-full"
              style={{ width: `${uploadProgress}%` }}
            ></div>
          </div>
        )}

        {/* Streaming Progress Display */}
        {loading && (
          <div className="mt-6">
            <h3 className="text-lg font-semibold text-gray-700 mb-3">Analysis Progress</h3>
            <div className="bg-gray-50 p-4 rounded-lg">
              <div className="mb-2">
                <div className="flex items-center">
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-500 mr-2"></div>
                  <span className="text-sm text-blue-600 font-medium">{currentStep}</span>
                </div>
              </div>
              
              {/* Progress Log */}
              <div className="max-h-40 overflow-y-auto bg-white p-3 rounded border text-xs">
                {streamingProgress.map((event, index) => (
                  <div key={index} className={`mb-1 ${
                    event.type === 'error' ? 'text-red-600' :
                    event.type === 'result' ? 'text-green-600' :
                    event.type === 'step' ? 'text-blue-600' :
                    'text-gray-600'
                  }`}>
                    {event.iteration > 0 && (
                      <span className="text-gray-400 mr-2">[{event.iteration}/{event.total}]</span>
                    )}
                    <span className="font-medium">{event.step}:</span> {event.message}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {answer && (
          <div className="mt-6">
            <h2 className="text-xl font-bold mb-4 text-gray-700">{t('analysisResult')}</h2>
            <div className="bg-gray-50 p-4 rounded-lg">
              <p className="text-gray-800">{answer}</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
