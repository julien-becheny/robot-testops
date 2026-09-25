import { useState, useCallback, useRef } from 'react';
import { API_BASE_URL } from './config/api';
import AppShell from './components/AppShell';
import MenuPage from './pages/HomePage';
import TestInProgress from './pages/ExecutionPage';
import ConfigPage from './pages/ConfigPage';
import LaunchPage from './pages/LaunchPage';
import TagSelectorPage from './pages/TagSelectorPage';
import LoadTestPage from './pages/LoadTestPage';
import CampaignPage from './pages/CampaignPage';
import CoveragePage from './pages/CoveragePage';
import HealthPage from './pages/HealthPage';

const VIEWPORT_MAP = {
  desktop: '1920x1080',
  tablet: '768x1024',
  mobile: '375x812',
};

// Un menu deroulant discret ne protege pas d'un run lance sur la mauvaise installation.
const allowedOnTarget = (env) =>
  env?.tier !== 'prod' ||
  window.confirm(
    `Ce run va s'ex\u00e9cuter sur la PRODUCTION :\n\n${env.label}\n${env.base}\n\nContinuer ?`
  );

function App() {
  const [currentPage, setCurrentPage] = useState('home');
  const [activeSessions, setActiveSessions] = useState([]);
  const [launchErrors, setLaunchErrors] = useState([]);
  const [selectedBrowsers, setSelectedBrowsers] = useState(['chromium']);
  const [selectedDevices, setSelectedDevices] = useState(['desktop']);
  // Le header porte la lecture de la configuration : les pages s'y raccrochent au lieu de la refaire.
  const [environmentInfo, setEnvironmentInfo] = useState({
    status: 'loading',
    env: null,
    list: [],
  });
  const [preselectedTags, setPreselectedTags] = useState([]);
  const lastTestFunctionRef = useRef(null);

  const openTags = useCallback((tags = []) => {
    setPreselectedTags(tags);
    setCurrentPage('tags');
  }, []);

  // Le contexte est fige au lancement : changer la barre pendant un run ne doit pas
  // reecrire ce sur quoi ce run est parti.
  const addSession = (sessionId, browser, workflow, context) => {
    setActiveSessions((prev) => [
      ...prev,
      { sessionId, browser, workflow, context, completed: false },
    ]);
  };

  const markSessionComplete = (sessionId) => {
    setActiveSessions((prev) =>
      prev.map((s) => (s.sessionId === sessionId ? { ...s, completed: true } : s))
    );
  };

  const clearSessions = () => {
    setActiveSessions([]);
    setLaunchErrors([]);
  };

  const launchSession = useCallback(async (browser, device, endpoint, body, workflow, context) => {
    const target = `${browser}-${device}`;
    try {
      const viewport = VIEWPORT_MAP[device] || '1920x1080';
      const res = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...body, browser, viewport }),
      });
      const data = await res.json();
      if (!res.ok || !data.session_id) {
        const message =
          typeof data.error === 'string' && data.error
            ? data.error
            : res.ok
              ? "La réponse de l'API ne contient aucune session."
              : "L'API a refusé le lancement.";
        setLaunchErrors((prev) => [...prev, { target, message }]);
        return;
      }
      addSession(data.session_id, target, workflow, context);
    } catch (err) {
      console.error(`Erreur lancement ${browser}/${device}:`, err);
      setLaunchErrors((prev) => [
        ...prev,
        { target, message: "Impossible de joindre l'API TestOps." },
      ]);
    }
  }, []);

  // Porte d'entrée unique de l'exécution : la garde de production ne peut pas être contournée.
  const startRun = useCallback(
    async (runFn) => {
      if (!allowedOnTarget(environmentInfo.env)) return;
      lastTestFunctionRef.current = runFn;
      clearSessions();
      setCurrentPage('execution');
      await runFn();
    },
    [environmentInfo.env]
  );

  const handleRunTest = useCallback(
    async (workflow = 'smoke') => {
      const browsers = [...selectedBrowsers];
      const devices = [...selectedDevices];
      const env = environmentInfo.env;
      const runFn = async () => {
        for (const browser of browsers) {
          for (const device of devices) {
            await launchSession(browser, device, '/run-test', { workflow }, workflow, {
              env,
              browser,
              device,
            });
          }
        }
      };

      await startRun(runFn);
    },
    [selectedBrowsers, selectedDevices, environmentInfo.env, launchSession, startRun]
  );

  const handleRunByTags = useCallback(
    async (includeTags, excludeTags, rerunFailed = false, isRandom = false, nbSelection = 0) => {
      const browsers = [...selectedBrowsers];
      const devices = [...selectedDevices];
      const env = environmentInfo.env;
      const runFn = async () => {
        const body = {
          include_tags: includeTags,
          exclude_tags: excludeTags,
          rerun_failed: rerunFailed,
          is_random: isRandom,
          nb_selection: nbSelection,
        };
        const workflow = isRandom ? 'randomized' : 'tag_filtered';
        for (const browser of browsers) {
          for (const device of devices) {
            await launchSession(browser, device, '/run-by-tags', body, workflow, {
              env,
              browser,
              device,
            });
          }
        }
      };

      await startRun(runFn);
    },
    [selectedBrowsers, selectedDevices, environmentInfo.env, launchSession, startRun]
  );

  const handleRunCampaign = useCallback(
    async (campaignId, browser, device, count) => {
      const env = environmentInfo.env;
      const runFn = async () => {
        const res = await fetch(`${API_BASE_URL}/campaigns/${campaignId}/run`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ browser, device, count }),
        });
        const data = await res.json();
        if (data.session_id) {
          addSession(data.session_id, `${browser}-${device}`, 'campaign', { env, browser, device });
        }
      };

      await startRun(runFn);
    },
    [environmentInfo.env, startRun]
  );

  const handleRunAppium = useCallback(async () => {
    const env = environmentInfo.env;
    const runFn = async () => {
      const res = await fetch(`${API_BASE_URL}/run-appium`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      const data = await res.json();
      if (data.session_id) {
        addSession(data.session_id, 'appium', 'appium', { env, browser: 'appium' });
      }
    };

    await startRun(runFn);
  }, [environmentInfo.env, startRun]);

  const renderPage = () => {
    switch (currentPage) {
      case 'config':
        return <ConfigPage />;
      case 'smoke':
        return (
          <LaunchPage
            kind="smoke"
            selectedBrowsers={selectedBrowsers}
            selectedDevices={selectedDevices}
            onLaunch={() => handleRunTest('smoke')}
          />
        );
      case 'appium':
        return <LaunchPage kind="appium" onLaunch={handleRunAppium} />;
      case 'load':
        return <LoadTestPage />;
      case 'campaign':
        return <CampaignPage onRunCampaign={handleRunCampaign} />;
      case 'coverage':
        return <CoveragePage />;
      case 'health':
        return <HealthPage />;
      case 'tags':
        return (
          <TagSelectorPage
            onRunByTags={handleRunByTags}
            initialTags={preselectedTags}
            selectedBrowsers={selectedBrowsers}
            selectedDevices={selectedDevices}
          />
        );
      default:
        return (
          <MenuPage
            setPage={setCurrentPage}
            onLaunchSmoke={() => handleRunTest('smoke')}
            onOpenTags={openTags}
            runningCount={activeSessions.filter((s) => !s.completed).length}
            environmentStatus={environmentInfo.status}
          />
        );
    }
  };

  const runningCount = activeSessions.filter((s) => !s.completed).length;
  const onExecution = currentPage === 'execution';

  return (
    <AppShell
      currentPage={currentPage}
      onNavigate={setCurrentPage}
      runningCount={runningCount}
      sessionCount={activeSessions.length}
      selectedBrowsers={selectedBrowsers}
      onBrowsersChange={setSelectedBrowsers}
      selectedDevices={selectedDevices}
      onDevicesChange={setSelectedDevices}
      onEnvironmentChange={setEnvironmentInfo}
    >
      {/* Rendue en continu : la demonter perdrait les logs, le chrono et le lien du rapport,
          que seul le direct alimente. */}
      {(onExecution || activeSessions.length > 0) && (
        <div className="shell-page" hidden={!onExecution}>
          <TestInProgress
            setPage={setCurrentPage}
            lastTestFunction={lastTestFunctionRef.current}
            activeSessions={activeSessions}
            launchErrors={launchErrors}
            onSessionComplete={markSessionComplete}
            onClearSessions={clearSessions}
          />
        </div>
      )}
      {!onExecution && renderPage()}
    </AppShell>
  );
}

export default App;
