import React, { useState } from 'react';
import axios from 'axios';

function ParserForm({ onParse }) {
  const [emailContent, setEmailContent] = useState('');
  const [emailImage, setEmailImage] = useState(null);
  const [parsingMethod, setParsingMethod] = useState('meta-llama/Llama-3.2-1B');
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Use localhost instead of 'backend' hostname
  const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || 'http://localhost:5000';

  const handleSubmit = async (e) => {
    e.preventDefault();
    console.log('Submit button clicked');
    setError('');
    setIsSubmitting(true);

    try {
      if (!emailContent && !emailImage) {
        throw new Error('Please provide email content or upload an image/PDF.');
      }

      const formData = new FormData();
      if (emailContent) {
        formData.append('email_content', emailContent);
        console.log('Email content added to formData');
      }
      if (emailImage) {
        formData.append('email_image', emailImage);
        console.log('Email image added to formData:', emailImage.name);
      }
      formData.append('parsing_method', parsingMethod);
      console.log('Parsing method selected:', parsingMethod);

      console.log(`Sending POST request to ${BACKEND_URL}/parse_email`);
      const response = await axios.post(`${BACKEND_URL}/parse_email`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        },
        withCredentials: true,
        // Add timeout and retry configuration
        timeout: 10000,
        retries: 3,
        // Add CORS headers
        validateStatus: function (status) {
          return status >= 200 && status < 500;
        }
      });
      
      console.log('Received response:', response.data);
      if (response.data.task_id) {
        onParse(response.data);
      } else {
        throw new Error('No task ID received from server');
      }
    } catch (err) {
      console.error('Error during submission:', err);
      const errorMessage = err.response?.data?.error || 
                          err.message || 
                          'Unable to connect to the parsing service. Please check if the backend server is running.';
      setError(errorMessage);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="form-group">
        <label htmlFor="email-content" className="block text-sm font-medium mb-2">
          Paste Email Content:
        </label>
        <textarea
          id="email-content"
          name="email_content"
          rows="10"
          className="w-full p-2 border rounded"
          placeholder="Paste your email content here..."
          value={emailContent}
          onChange={(e) => setEmailContent(e.target.value)}
        />
      </div>

      <div className="form-group">
        <label htmlFor="email-image" className="block text-sm font-medium mb-2">
          Or Upload Email Image or PDF:
        </label>
        <input
          type="file"
          id="email-image"
          name="email_image"
          className="w-full"
          accept="image/png,image/jpeg,application/pdf"
          onChange={(e) => setEmailImage(e.target.files[0])}
        />
      </div>

      <div className="form-group">
        <label htmlFor="parsing-method" className="block text-sm font-medium mb-2">
          Select Parsing Method:
        </label>
        <select
          id="parsing-method"
          name="parsing_method"
          className="w-full p-2 border rounded"
          value={parsingMethod}
          onChange={(e) => setParsingMethod(e.target.value)}
        >
          <option value="meta-llama/Llama-3.2-1B">Llama 1B</option>
          <option value="meta-llama/Llama-3.2-3B">Llama 3B</option>
        </select>
      </div>

      {error && (
        <div className="p-3 bg-red-100 border border-red-400 text-red-700 rounded">
          {error}
        </div>
      )}

      <button
        type="submit"
        disabled={isSubmitting}
        className={`w-full p-3 text-white rounded ${
          isSubmitting ? 'bg-gray-400' : 'bg-blue-500 hover:bg-blue-600'
        }`}
      >
        {isSubmitting ? 'Parsing...' : 'Parse Email'}
      </button>
    </form>
  );
}

export default ParserForm;