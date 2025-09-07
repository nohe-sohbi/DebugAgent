import React, { useState, useRef } from 'react';
import { useTranslation } from 'react-i18next';

function App() {
  const { t } = useTranslation();
  const [question, setQuestion] = useState('');
  const [files, setFiles] = useState([]);
  const [answer, setAnswer] = useState('');
  const [loading, setLoading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef();

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

    const formData = new FormData();
    formData.append('question', question);
    for (const file of files) {
      formData.append('files', file, file.webkitRelativePath || file.name);
    }

    setAnswer('');
    setUploadProgress(0);
    setIsUploading(true);

    const xhr = new XMLHttpRequest();

    xhr.upload.addEventListener('progress', (event) => {
      if (event.lengthComputable) {
        const percentComplete = Math.round((event.loaded / event.total) * 100);
        setUploadProgress(percentComplete);
      }
    });

    xhr.addEventListener('load', () => {
      setIsUploading(false);
      setLoading(true); // Analysis starts now
      if (xhr.status === 200) {
        const data = JSON.parse(xhr.responseText);
        setAnswer(data.answer);
      } else {
        console.error('Error submitting analysis request:', xhr.statusText);
      }
      setLoading(false);
    });

    xhr.addEventListener('error', () => {
      setIsUploading(false);
      setLoading(false);
      console.error('Error submitting analysis request: An unknown error occurred.');
    });

    xhr.open('POST', 'http://localhost:8080/analyze', true);
    xhr.send(formData);
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
