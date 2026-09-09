import { useEffect, useState, useRef } from 'react';
import { io } from 'socket.io-client';
import {
  FiActivity,
  FiPlay,
  FiStopCircle,
  FiAlertTriangle,
  FiCheckCircle,
  FiXCircle,
  FiClock,
  FiTerminal,
  FiFileText,
  FiExternalLink,
  FiFolder,
} from 'react-icons/fi';
import { motion } from 'framer-motion';
import { API_BASE_URL, SOCKET_URL } from '../config/api';
import RunMatrix from '../components/RunMatrix';
import ActionButton from '../components/ActionButton';
import RunContext from '../components/execution/RunContext';
import { LogBlockList } from '../components/execution/logBlocks';
import '../css/TestInProgressPage.css';

/* ──────────────────────────────────────────
   SessionPanel : un panneau par session
   ────────────────────────────────────────── */
const SessionPanel = ({ sessionId, browser, workflow, context, socketRef, onComplete }) => {
  const [logs, setLogs] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [logFileLink, setLogFileLink] = useState('');
  const [mergedLogFileLink, setMergedLogFileLink] = useState('');
  const [logDirectory, setLogDirectory] = useState('');
  const [status, setSuiteStatus] = useState(null);
  const [mergedStatus, setMergedStatus] = useState(null);
  const [isRerunComplete, setIsRerunComplete] = useState(false);
  const [duration, setDuration] = useState(0);
  const [progress, setProgress] = useState(null);
  const [stopRequested, setStopRequested] = useState(false);

  const timerRef = useRef(null);
  const startTimeRef = useRef(null);
  const logsContainerRef = useRef(null);
  const testExecutions = useRef({});
  const onCompleteRef = useRef(onComplete);
  onCompleteRef.current = onComplete;

  // Rejoindre la room de cette session
  useEffect(() => {
    const socket = socketRef.current;
    if (!socket || !sessionId) return;

    socket.emit('join_session', { session_id: sessionId });

    const handleLog = (data) => {
      if (data.session_id && data.session_id !== sessionId) return;
      const text = typeof data === 'object' ? data.message : data;
      // Un nom de keyword peut contenir « PASS » ou « Test: » : quand le listener
      // annonce la nature de la ligne, elle prime sur la lecture du texte.
      const declared = typeof data === 'object' ? data.level : null;

      const isTestStart = text.includes('Test:') || text.includes('Test n°');
      const isSuccess = text.includes('PASS') || text.includes('avec succès');
      const isSkipped = text.includes('a été ignoré');
      const isError = text.includes('FAIL') || text.includes('a échoué');
      const isErrorDetail = text.startsWith('Message:');

      let type = 'info';
      let testName = null;
      let executionId = null;

      if (declared === 'keyword' || declared === 'keyword-failed') {
        type = declared;
      } else if (isTestStart) {
        type = 'test-start';
        testName = text;
        if (!testExecutions.current[testName]) {
          testExecutions.current[testName] = { count: 1, executions: [] };
        } else {
          testExecutions.current[testName].count++;
        }
        executionId = `${testName}_exec_${testExecutions.current[testName].count}`;
        testExecutions.current[testName].executions.push({ id: executionId, status: null });
      } else if (isSuccess) {
        type = 'success';
      } else if (isSkipped) {
        type = 'skip';
      } else if (isErrorDetail) {
        type = 'error-detail';
      } else if (isError) {
        type = 'error';
      }

      setLogs((prev) => [
        ...prev,
        { text, type, timestamp: new Date().toISOString(), testName, executionId },
      ]);
      if (logsContainerRef.current) {
        requestAnimationFrame(() => {
          // La ref peut avoir ete liberee entre la planification et l'appel (demontage).
          const container = logsContainerRef.current;
          if (container) container.scrollTop = container.scrollHeight;
        });
      }
    };

    const handleComplete = (data) => {
      if (data?.session_id && data.session_id !== sessionId) return;
      setIsLoading(false);
      if (onCompleteRef.current) onCompleteRef.current(sessionId);
    };

    const handleStatus = (data) => {
      if (data.session_id && data.session_id !== sessionId) return;
      if (data.is_merged) {
        setMergedStatus(data);
        setIsRerunComplete(true);
      } else {
        setSuiteStatus(data);
      }
    };

    const handleLogLink = (data) => {
      if (data.session_id && data.session_id !== sessionId) return;
      const filename = data.log_link;
      const isMerged = data.is_merged || false;
      const hasRerun = data.has_rerun || false;
      const sid = sessionId;

      if (isMerged) {
        setMergedLogFileLink(`${API_BASE_URL}/logs/${sid}/merged/${encodeURIComponent(filename)}`);
        setIsRerunComplete(true);
      } else if (hasRerun) {
        setLogFileLink(`${API_BASE_URL}/logs/${sid}/original/${encodeURIComponent(filename)}`);
      } else {
        setLogFileLink(`${API_BASE_URL}/logs/${sid}/standard/${encodeURIComponent(filename)}`);
      }
    };

    const handleLogDir = (data) => {
      if (data.session_id && data.session_id !== sessionId) return;
      setLogDirectory(data.log_directory);
    };

    const handleProgress = (data) => {
      if (data.session_id && data.session_id !== sessionId) return;
      setProgress({ done: data.done, total: data.total, phase: data.phase || 'run' });
    };

    socket.on('log', handleLog);
    socket.on('execution-complete', handleComplete);
    socket.on('final-status', handleStatus);
    socket.on('progress', handleProgress);
    socket.on('log-link', handleLogLink);
    socket.on('log-directory', handleLogDir);

    return () => {
      socket.off('log', handleLog);
      socket.off('execution-complete', handleComplete);
      socket.off('final-status', handleStatus);
      socket.off('progress', handleProgress);
      socket.off('log-link', handleLogLink);
      socket.off('log-directory', handleLogDir);
      socket.emit('leave_session', { session_id: sessionId });
    };
  }, [sessionId, socketRef]);

  // Timer
  useEffect(() => {
    if (isLoading) {
      startTimeRef.current = Date.now();
      timerRef.current = setInterval(() => {
        setDuration(Math.floor((Date.now() - startTimeRef.current) / 1000));
      }, 1000);
    } else if (timerRef.current) {
      clearInterval(timerRef.current);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [isLoading]);

  const formatDuration = (s) => {
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${sec.toString().padStart(2, '0')}`;
  };

  const openDirectory = async () => {
    try {
      await fetch(`${API_BASE_URL}/open-directory`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId }),
      });
    } catch (err) {
      console.error('Erreur ouverture dossier:', err);
    }
  };

  const handleStop = async () => {
    setStopRequested(true);
    try {
      await fetch(`${API_BASE_URL}/stop-test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId }),
      });
    } catch (error) {
      console.error('Erreur arrêt:', error);
    }
  };

  const displayStatus = isRerunComplete ? mergedStatus : status;
  // Le verdict se lit dans les compteurs : le deduire d'une phrase confond
  // « 0 echoues » avec « echoue ».
  const failedCount = displayStatus?.failed ?? 0;
  const rerunCount = displayStatus?.rerun ?? 0;
  const verdictTone = isLoading
    ? 'status-running'
    : failedCount > 0
      ? 'status-failed'
      : stopRequested || rerunCount > 0
        ? 'status-warned'
        : 'status-success';

  const verdictText = () => {
    if (isLoading) return stopRequested ? 'Arrêt en cours…' : 'Exécution en cours';
    // Interrompu : les tests non joués ne sont ni des succès ni des échecs.
    if (stopRequested) return 'Exécution interrompue';
    if (!displayStatus?.total) return displayStatus?.status || 'Exécution terminée';
    const { total, passed, failed } = displayStatus;
    const parts = [`${total} tests`, `${passed} passés`];
    if (failed) parts.push(`${failed} échoués`);
    return parts.join(' · ');
  };

  const browserLabel =
    browser === 'chromium'
      ? 'Chrome'
      : browser === 'webkit'
        ? 'Safari'
        : browser === 'firefox'
          ? 'Firefox'
          : browser;

  return (
    <div className="session-panel">
      <div className="session-panel-header">
        <RunContext context={context} fallback={browserLabel} />
        <span className="session-id-label">{sessionId}</span>
        {isLoading && (
          <ActionButton
            tone="danger"
            icon={FiStopCircle}
            className="small session-stop-btn"
            onClick={handleStop}
          >
            Arrêter
          </ActionButton>
        )}
      </div>

      <div className="execution-summary">
        <div className="summary-cards">
          <motion.div
            className={`summary-card status-card ${verdictTone}`}
            initial={{ y: 20, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ duration: 0.3 }}
          >
            <div className="card-header">
              <div className="card-title">État</div>
              {isLoading && <div className="status-pulse"></div>}
            </div>
            <div className="card-content status-content">
              <div className="status-icon">
                {isLoading ? (
                  <FiActivity className="animated-icon" />
                ) : failedCount > 0 ? (
                  <FiXCircle className="error-icon" />
                ) : stopRequested || rerunCount > 0 ? (
                  <FiAlertTriangle className="warned-icon" />
                ) : (
                  <FiCheckCircle className="success-icon" />
                )}
              </div>
              <div className="status-details">
                <div className="status-message">{verdictText()}</div>
                {isLoading && progress?.total > 0 && (
                  <div className={`status-progress phase-${progress.phase}`}>
                    <div className="status-progress-bar">
                      <span style={{ width: `${(progress.done / progress.total) * 100}%` }} />
                    </div>
                    <span className="status-progress-label">
                      {progress.phase === 'rerun' ? 'rejeu ' : ''}
                      {progress.done}/{progress.total} tests
                    </span>
                  </div>
                )}
                {rerunCount > 0 && !isLoading && (
                  <div className="status-rerun">
                    dont {rerunCount} passé{rerunCount > 1 ? 's' : ''} au rejeu
                  </div>
                )}
                <div className="status-timer">
                  <FiClock /> {formatDuration(duration)}
                </div>
              </div>
            </div>
          </motion.div>

          <motion.div
            className="summary-card reports-card"
            initial={{ y: 20, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ duration: 0.3, delay: 0.1 }}
          >
            <div className="card-header">
              <div className="card-title">Résultats</div>
            </div>
            <div className="card-content reports-content">
              {isLoading ? (
                <div className="reports-loading">
                  <div className="reports-placeholder">
                    <div className="placeholder-icon">
                      <FiFileText />
                    </div>
                    <div className="placeholder-text">Rapports disponibles à la fin</div>
                  </div>
                </div>
              ) : (
                <div className="reports-links">
                  {logFileLink && (
                    <a
                      href={logFileLink}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="report-link"
                    >
                      <span className="report-link-icon">
                        <FiFileText />
                      </span>
                      <div className="report-link-content">
                        <div className="report-link-title">
                          Log {isRerunComplete ? '(initial)' : ''}
                        </div>
                      </div>
                      <FiExternalLink className="report-external-icon" />
                    </a>
                  )}
                  {mergedLogFileLink && (
                    <a
                      href={mergedLogFileLink}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="report-link merged-link"
                    >
                      <span className="report-link-icon">
                        <FiFileText />
                      </span>
                      <div className="report-link-content">
                        <div className="report-link-title">Log fusionné</div>
                      </div>
                      <FiExternalLink className="report-external-icon" />
                    </a>
                  )}
                  {logDirectory && (
                    <div
                      className="report-link directory-link"
                      onClick={openDirectory}
                      style={{ cursor: 'pointer' }}
                    >
                      <span className="report-link-icon">
                        <FiFolder />
                      </span>
                      <div className="report-link-content">
                        <div className="report-link-title">Dossier</div>
                      </div>
                      <span className="report-open-icon">Ouvrir</span>
                    </div>
                  )}
                </div>
              )}
            </div>
          </motion.div>
        </div>
      </div>

      <div className="logs-section">
        <div className="logs-header">
          <div className="logs-title">
            <FiTerminal className="logs-icon" />
            <h2>Logs</h2>
          </div>
        </div>
        <div className="logs-container" ref={logsContainerRef}>
          {logs.length === 0 ? (
            <div className="no-logs-message">
              <div className="no-logs-icon">
                <FiFileText size={26} />
              </div>
              <p>{isLoading ? 'En attente des logs...' : 'Aucun log'}</p>
            </div>
          ) : (
            <LogBlockList logs={logs} running={isLoading} />
          )}
        </div>
      </div>
    </div>
  );
};

/* ──────────────────────────────────────────
   TestInProgress : conteneur multi-session
   ────────────────────────────────────────── */
const TestInProgress = ({
  setPage,
  lastTestFunction,
  activeSessions = [],
  launchErrors = [],
  onSessionComplete,
  onClearSessions,
}) => {
  const socketRef = useRef(null);
  const [results, setResults] = useState({});

  useEffect(() => {
    const socket = io(SOCKET_URL);
    socketRef.current = socket;

    const handleTestResult = (data) => {
      if (!data?.session_id || !data?.longname) return;
      setResults((prev) => ({
        ...prev,
        [data.session_id]: {
          ...prev[data.session_id],
          [data.longname]: {
            name: data.name || data.longname,
            status: data.status,
            message: data.message || '',
          },
        },
      }));
    };

    socket.on('test-result', handleTestResult);
    return () => {
      socket.off('test-result', handleTestResult);
      socket.disconnect();
    };
  }, []);

  const handleRelaunch = async () => {
    if (lastTestFunction) {
      if (onClearSessions) onClearSessions();
      setResults({});
      try {
        await lastTestFunction();
      } catch (e) {
        console.error(e);
      }
    }
  };

  const allCompleted = activeSessions.length > 0 && activeSessions.every((s) => s.completed);
  const runningCount = activeSessions.filter((s) => !s.completed).length;

  return (
    <motion.div
      className="huly-execution-container"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      <div className="huly-execution-navbar">
        <div className="navbar-left">
          <h1>Exécution de test</h1>
          {activeSessions.length > 1 && (
            <span className="session-count-badge">
              {activeSessions.length} sessions
              {runningCount > 0 && ` (${runningCount} en cours)`}
            </span>
          )}
        </div>
      </div>

      <div className="huly-execution-content">
        {launchErrors.length > 0 && (
          <div className="launch-errors" aria-label="Erreurs de lancement">
            {launchErrors.map((error, index) => (
              <div className="launch-error" role="alert" key={`${error.target}-${index}`}>
                <FiAlertTriangle className="launch-error-icon" />
                <strong>{error.target}</strong>
                <span>{error.message}</span>
              </div>
            ))}
          </div>
        )}
        {activeSessions.length > 1 && <RunMatrix sessions={activeSessions} results={results} />}
        <div className={`sessions-grid sessions-${Math.min(activeSessions.length, 3)}`}>
          {activeSessions.map((s) => (
            <SessionPanel
              key={s.sessionId}
              sessionId={s.sessionId}
              browser={s.browser}
              workflow={s.workflow}
              context={s.context}
              socketRef={socketRef}
              onComplete={onSessionComplete}
            />
          ))}
          {activeSessions.length === 0 && launchErrors.length === 0 && (
            <div className="no-sessions-message">
              <p>Aucune session active</p>
            </div>
          )}
        </div>
      </div>

      <div className="huly-actions-bar">
        <div className="action-buttons-group"></div>
        <div className="action-buttons-group">
          {allCompleted && (
            <ActionButton icon={FiPlay} onClick={handleRelaunch}>
              Relancer
            </ActionButton>
          )}
        </div>
      </div>
    </motion.div>
  );
};

export default TestInProgress;
