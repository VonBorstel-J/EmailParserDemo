import React from 'react';
import axios from 'axios';

function ParsedResult({ data, taskId }) {
  console.log(`ParsedResult Component Rendered for taskId: ${taskId}`, data);

  const handleExport = async (type) => {
    console.log(`Export button clicked for type: ${type}`);
    try {
      console.log(`Sending GET request to /export_${type}/${taskId}`);
      const response = await axios.get(`/export_${type}/${taskId}`, {
        responseType: 'blob'
      });
      console.log(`Received response for export_${type}:`, response);

      const blob = new Blob([response.data], { type: response.headers['content-type'] });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `parsed_results.${type}`);
      document.body.appendChild(link);
      link.click();
      console.log(`Triggered download for parsed_results.${type}`);
      link.parentNode.removeChild(link);
      window.URL.revokeObjectURL(url);
      console.log(`Cleaned up download link and revoked object URL.`);
    } catch (error) {
      console.error(`Failed to export as ${type.toUpperCase()}:`, error);
      alert(`Failed to export as ${type.toUpperCase()}: ${error.message}`);
    }
  };

  return (
    <div className="result-container">
      <h2>Parsed Results:</h2>
      <pre>{JSON.stringify(data, null, 4)}</pre>
      <div className="export-buttons">
        <button onClick={() => handleExport('pdf')}>Export as PDF</button>
        <button onClick={() => handleExport('csv')}>Export as CSV</button>
      </div>
    </div>
  );
}

export default ParsedResult;
