import React from 'react';
import ParserForm from './components/ParserForm';
import ParsedResult from './components/ParsedResult';
import axios from 'axios';

function App() {
  const [parsedData, setParsedData] = React.useState(null);
  const [taskId, setTaskId] = React.useState(null);
  const [progress, setProgress] = React.useState(0);
  const [status, setStatus] = React.useState('');
  const [error, setError] = React.useState('');

  React.useEffect(() => {
    console.log('useEffect triggered. Current taskId:', taskId);
    let interval = null;
    if (taskId) {
      console.log('Starting interval to check task status for taskId:', taskId);
      interval = setInterval(async () => {
        try {
          console.log(`Fetching status for taskId: ${taskId}`);
          const response = await axios.get(`/parse_status/${taskId}`);
          const data = response.data;
          console.log('Received status:', data);
          setProgress(data.progress);
          setStatus(data.status);
          if (data.status === 'completed') {
            console.log('Task completed. Parsed data received.');
            setParsedData(data.result);
            clearInterval(interval);
          } else if (data.status === 'failed') {
            console.log('Task failed with error:', data.result);
            setError(data.result);
            clearInterval(interval);
          }
        } catch (err) {
          console.error(`Error fetching status for taskId ${taskId}:`, err);
          setError(`Error fetching status: ${err.message}`);
          clearInterval(interval);
        }
      }, 1000);
    }
    return () => {
      if (interval) {
        console.log('Clearing interval for taskId:', taskId);
        clearInterval(interval);
      }
    };
  }, [taskId]);

  const handleParse = (data) => {
    console.log('handleParse called with data:', data);
    setTaskId(data.task_id);
    setProgress(0);
    setStatus('processing');
    setParsedData(null);
    setError('');
  };

  return (
    <div className="container">
      <h1>Keystone Email Parser</h1>
      <ParserForm onParse={handleParse} />
      {taskId && (
        <div className="progress-container">
          <label>Parsing Progress:</label>
          <progress value={progress} max="100">{progress}%</progress>
          <span>{progress}%</span>
        </div>
      )}
      {status === 'completed' && parsedData && (
        <ParsedResult data={parsedData} taskId={taskId} />
      )}
      {status === 'failed' && (
        <div className="notification error">
          Parsing failed: {error}
        </div>
      )}
    </div>
  );
}

export default App;
