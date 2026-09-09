import { useState, useEffect, useCallback } from 'react';
import io from 'socket.io-client';
import { FiCheckCircle } from 'react-icons/fi';
import '../css/ExecutionStatusIndicator.css';
import { API_BASE_URL } from '../config/api';

const ExecutionStatusIndicator = () => {
  const [isExecutionRunning, setIsExecutionRunning] = useState(false);
  const [runningCount, setRunningCount] = useState(0);
  const [lastUpdate, setLastUpdate] = useState(null);

  const checkExecutionStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/execution-status`);
      const data = await res.json();

      setIsExecutionRunning(data.is_running);
      setRunningCount(data.running_count || 0);
      setLastUpdate(new Date());
    } catch (err) {
      console.error('Erreur vérification statut:', err);
    }
  }, []);

  useEffect(() => {
    const socket = io(API_BASE_URL);

    checkExecutionStatus();

    socket.on('execution_status_changed', (data) => {
      setIsExecutionRunning(data.isRunning);
      setRunningCount(data.runningCount || 0);
      setLastUpdate(new Date());
    });

    return () => {
      socket.disconnect();
    };
  }, [checkExecutionStatus]);

  if (!lastUpdate) {
    return null;
  }

  if (isExecutionRunning) {
    return (
      <div
        className="execution-status-indicator idle"
        title={`${runningCount} session(s) en cours`}
      >
        <div className="status-icon">�</div>
        {runningCount > 1 && <span className="running-count">{runningCount}</span>}
      </div>
    );
  }

  return (
    <div className="execution-status-indicator idle" title="TestOps disponible">
      <div className="status-icon">
        <FiCheckCircle size={16} />
      </div>
    </div>
  );
};

export default ExecutionStatusIndicator;
