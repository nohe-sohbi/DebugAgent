import React, { useState } from 'react';

function App() {
  const [question, setQuestion] = useState('');
  const [files, setFiles] = useState([]);

  const handleFileChange = (e) => {
    setFiles([...e.target.files]);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    const droppedFiles = Array.from(e.dataTransfer.files);
    setFiles(droppedFiles);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
  };

  const handleSubmit = async () => {
    if (files.length === 0) {
      alert('Please select a project/file.');
      return;
    }

    const formData = new FormData();
    formData.append('project_path', files[0].path); // Sending the path of the first file
    formData.append('question', question);

    try {
      const response = await fetch('/analyze', {
        method: 'POST',
        body: formData,
      });
      const data = await response.json();
      console.log(data);
      // Handle response
    } catch (error) {
      console.error('Error submitting analysis request:', error);
    }
  };

  return (
    <div className="min-h-screen bg-gray-100 flex items-center justify-center">
      <div className="bg-white p-8 rounded-lg shadow-md w-full max-w-2xl">
        <h1 className="text-2xl font-bold mb-6 text-center text-gray-700">Project Analysis</h1>

        <div className="mb-6">
          <label htmlFor="question" className="block text-gray-700 text-sm font-bold mb-2">
            Your Question
          </label>
          <textarea
            id="question"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            className="shadow appearance-none border rounded w-full py-2 px-3 text-gray-700 leading-tight focus:outline-none focus:shadow-outline h-24"
            placeholder="What do you want to know about your project?"
          />
        </div>

        <div className="mb-4">
          <label className="block text-gray-700 text-sm font-bold mb-2">
            Project Files
          </label>
          <div
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            className="border-dashed border-2 border-gray-300 p-6 rounded-lg text-center cursor-pointer hover:border-gray-500"
          >
            <p className="text-gray-500">Drag and drop a folder or files here</p>
          </div>
        </div>

        <div className="mb-6">
          <label className="block text-gray-700 text-sm font-bold mb-2">
            Or select files
          </label>
          <input
            type="file"
            multiple
            webkitdirectory="true"
            onChange={handleFileChange}
            className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
          />
        </div>

        {files.length > 0 && (
          <div className="mb-4">
            <h3 className="text-lg font-semibold text-gray-700">Selected Files:</h3>
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
            className="bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded focus:outline-none focus:shadow-outline"
          >
            Analyze Project
          </button>
        </div>
      </div>
    </div>
  );
}

export default App;
