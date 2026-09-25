import { useState, useEffect, useCallback, useRef } from 'react';
import '../css/Header.css';
import { API_BASE_URL, setConfigVar } from '../config/api';
import { FiChevronDown, FiGitBranch, FiMonitor, FiSmartphone, FiTablet } from 'react-icons/fi';
import BrandMark from './BrandMark';
import DeviceGlyph from './DeviceGlyph';
import chromiumLogo from '../assets/chromium.svg';
import firefoxLogo from '../assets/firefox.svg';
import safariLogo from '../assets/safari.svg';

export const BROWSERS = [
  { label: 'Chromium', value: 'chromium', icon: chromiumLogo },
  { label: 'Firefox', value: 'firefox', icon: firefoxLogo },
  { label: 'Safari', value: 'webkit', icon: safariLogo },
];

export const DEVICES = [
  { label: 'Desktop', value: 'desktop', icon: FiMonitor, viewport: '1920x1080' },
  { label: 'Tablette', value: 'tablet', icon: FiTablet, viewport: '768x1024' },
  { label: 'Mobile', value: 'mobile', icon: FiSmartphone, viewport: '375x812' },
];

export const SLOWMO_PRESETS = [
  { label: 'Off', value: '0:00:00' },
  { label: '0.5 s', value: '0:00:00.5' },
  { label: '1 s', value: '0:00:01' },
  { label: '2 s', value: '0:00:02' },
];

export const TRACING_PRESETS = [
  { label: 'Off', value: 'off' },
  { label: 'Activée', value: 'on' },
];

const BACKEND_RETRY_MS = 1000;
const BACKEND_MAX_RETRIES = 30;

// Une sélection ne descend jamais à zéro : un run sans navigateur n'existe pas.
const toggled = (list, value) =>
  list.includes(value)
    ? list.length > 1
      ? list.filter((v) => v !== value)
      : list
    : [...list, value];

const Presets = ({ label, presets, value, onChange }) => (
  <div className="ctx-option" role="group" aria-label={label}>
    <span className="ctx-label">{label}</span>
    <div className="ctx-presets">
      {presets.map((preset) => (
        <button
          key={preset.value}
          type="button"
          className={`ctx-preset ${value === preset.value ? 'active' : ''}`}
          onClick={() => onChange(preset.value)}
        >
          {preset.label}
        </button>
      ))}
    </div>
  </div>
);

const Header = ({
  selectedBrowsers = ['chromium'],
  onBrowsersChange,
  selectedDevices = ['desktop'],
  onDevicesChange,
  onEnvironmentChange,
}) => {
  const [gitBranch, setGitBranch] = useState('');
  const [envList, setEnvList] = useState([]);
  const [environment, setEnvironment] = useState('');
  const [backendState, setBackendState] = useState('loading');
  const [slowMo, setSlowMo] = useState('0:00:00');
  const [tracing, setTracing] = useState('off');
  const [panelOpen, setPanelOpen] = useState(false);
  const [mobileStatus, setMobileStatus] = useState(null);
  const [appiumBusy, setAppiumBusy] = useState(false);
  const headerRef = useRef(null);

  const fetchGitBranch = useCallback(async () => {
    const res = await fetch(`${API_BASE_URL}/git-info`);
    const data = await res.json();
    setGitBranch(data.branch);
  }, []);

  const fetchConfig = useCallback(async () => {
    const res = await fetch(`${API_BASE_URL}/config-vars`);
    const data = await res.json();
    setSlowMo(data.RF_SLOW_MO || '0:00:00');
    setTracing(data.RF_TRACING || 'off');
  }, []);

  const fetchEnvironments = useCallback(async () => {
    const res = await fetch(`${API_BASE_URL}/environments`);
    const data = await res.json();
    setEnvList(data.environments || []);
    setEnvironment(data.active || '');
  }, []);

  // L'interface s'ouvre parfois avant que le backend écoute : réessayer plutôt qu'afficher une config vide.
  useEffect(() => {
    let cancelled = false;
    let attempts = 0;
    let timer;
    const load = async () => {
      try {
        await Promise.all([fetchGitBranch(), fetchConfig(), fetchEnvironments()]);
        if (!cancelled) setBackendState('ready');
      } catch {
        attempts += 1;
        if (cancelled) return;
        if (attempts >= BACKEND_MAX_RETRIES) {
          setBackendState('unreachable');
          return;
        }
        timer = setTimeout(load, BACKEND_RETRY_MS);
      }
    };
    load();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [fetchGitBranch, fetchConfig, fetchEnvironments]);

  // Les pages affichent la meme cible que la barre : elles la recoivent d'ici.
  useEffect(() => {
    if (!onEnvironmentChange) return;
    onEnvironmentChange({
      status: backendState,
      env: envList.find((entry) => entry.id === environment) || null,
      list: envList,
    });
  }, [backendState, envList, environment, onEnvironmentChange]);

  useEffect(() => {
    if (!panelOpen) return undefined;
    const onClickOutside = (e) => {
      if (headerRef.current && !headerRef.current.contains(e.target)) setPanelOpen(false);
    };
    document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, [panelOpen]);

  useEffect(() => {
    if (!panelOpen) return;
    fetch(`${API_BASE_URL}/mobile-preflight`)
      .then((r) => r.json())
      .then(setMobileStatus)
      .catch(() => setMobileStatus(null));
  }, [panelOpen]);

  const handleSlowMoChange = (value) => {
    setSlowMo(value);
    setConfigVar('RF_SLOW_MO', value);
  };

  const handleTracingChange = (value) => {
    setTracing(value);
    setConfigVar('RF_TRACING', value);
  };

  const handleEnvironmentChange = (id) => {
    setEnvironment(id);
    setConfigVar('RF_ENVIRONMENT', id);
  };

  const pollMobileUntil = (predicate, tries = 8) => {
    let n = 0;
    const tick = () => {
      fetch(`${API_BASE_URL}/mobile-preflight`)
        .then((r) => r.json())
        .then((d) => {
          setMobileStatus(d);
          n += 1;
          if (!predicate(d) && n < tries) setTimeout(tick, 1500);
          else setAppiumBusy(false);
        })
        .catch(() => setAppiumBusy(false));
    };
    setTimeout(tick, 1500);
  };

  const startAppium = () => {
    setAppiumBusy(true);
    fetch(`${API_BASE_URL}/mobile/appium/start`, { method: 'POST' })
      .then(() => pollMobileUntil((d) => d.appium_online))
      .catch(() => setAppiumBusy(false));
  };

  const stopAppium = () => {
    setAppiumBusy(true);
    fetch(`${API_BASE_URL}/mobile/appium/stop`, { method: 'POST' })
      .then(() => pollMobileUntil((d) => !d.appium_online, 4))
      .catch(() => setAppiumBusy(false));
  };

  const activeEnv = envList.find((env) => env.id === environment);
  const sessions = selectedBrowsers.length * selectedDevices.length;
  const usable = backendState === 'ready' && envList.length > 0;

  const triggerLabel = () => {
    if (backendState === 'loading') return 'Chargement…';
    if (backendState === 'unreachable') return 'API injoignable';
    if (envList.length === 0) return 'Aucun environnement déclaré';
    return activeEnv?.label || '';
  };

  return (
    <header className="header" ref={headerRef}>
      <div className="header-bar">
        <BrandMark size={30} />

        <button
          type="button"
          className={`ctx-trigger tier-${activeEnv?.tier || 'demo'} ${panelOpen ? 'open' : ''} ${
            usable ? '' : 'idle'
          }`}
          aria-expanded={panelOpen}
          aria-label="Contexte des prochains runs"
          disabled={!usable}
          title={activeEnv?.base || ''}
          onClick={() => setPanelOpen((o) => !o)}
        >
          <span className="ctx-planet" aria-hidden="true" />
          <span className="ctx-trigger-env">{triggerLabel()}</span>
          {usable && (
            <>
              <span className="ctx-trigger-sep" />
              <span className="ctx-trigger-icons">
                {selectedBrowsers.map((value) => {
                  const browser = BROWSERS.find((b) => b.value === value);
                  return browser ? (
                    <img key={value} src={browser.icon} alt={browser.label} width="16" />
                  ) : null;
                })}
              </span>
              <span className="ctx-trigger-sep" />
              <span className="ctx-trigger-icons">
                {selectedDevices.map((value) => (
                  <DeviceGlyph key={value} device={value} size={17} />
                ))}
              </span>
              {sessions > 1 && <span className="ctx-trigger-count">{sessions} sessions</span>}
              <FiChevronDown size={14} className="ctx-trigger-caret" />
            </>
          )}
        </button>

        {gitBranch && (
          <span className="header-branch" title="Branche du code de test">
            <FiGitBranch size={12} />
            {gitBranch}
          </span>
        )}
      </div>

      {panelOpen && (
        <div className="ctx-panel">
          <div className="ctx-columns">
            <div className="ctx-column" role="group" aria-label="Environnement">
              <span className="ctx-label">Environnement</span>
              <div className="ctx-choices">
                {envList.map((env) => (
                  <button
                    key={env.id}
                    type="button"
                    className={`ctx-choice wide tier-${env.tier || 'demo'} ${
                      env.id === environment ? 'active' : ''
                    }`}
                    aria-pressed={env.id === environment}
                    title={env.base || ''}
                    onClick={() => handleEnvironmentChange(env.id)}
                  >
                    <span className="ctx-planet" aria-hidden="true" />
                    {env.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="ctx-column" role="group" aria-label="Navigateurs">
              <span className="ctx-label">
                Navigateurs
                <button
                  type="button"
                  className="ctx-all"
                  onClick={() =>
                    onBrowsersChange?.(
                      selectedBrowsers.length === BROWSERS.length
                        ? [BROWSERS[0].value]
                        : BROWSERS.map((b) => b.value)
                    )
                  }
                >
                  {selectedBrowsers.length === BROWSERS.length ? 'Réduire' : 'Tous'}
                </button>
              </span>
              <div className="ctx-choices">
                {BROWSERS.map((browser) => (
                  <button
                    key={browser.value}
                    type="button"
                    className={`ctx-choice ${
                      selectedBrowsers.includes(browser.value) ? 'active' : ''
                    }`}
                    aria-pressed={selectedBrowsers.includes(browser.value)}
                    onClick={() => onBrowsersChange?.(toggled(selectedBrowsers, browser.value))}
                  >
                    <img src={browser.icon} alt="" width="22" />
                    {browser.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="ctx-column" role="group" aria-label="Appareils">
              <span className="ctx-label">
                Appareils
                <button
                  type="button"
                  className="ctx-all"
                  onClick={() =>
                    onDevicesChange?.(
                      selectedDevices.length === DEVICES.length
                        ? [DEVICES[0].value]
                        : DEVICES.map((d) => d.value)
                    )
                  }
                >
                  {selectedDevices.length === DEVICES.length ? 'Réduire' : 'Tous'}
                </button>
              </span>
              <div className="ctx-choices">
                {DEVICES.map((device) => (
                  <button
                    key={device.value}
                    type="button"
                    className={`ctx-choice ${selectedDevices.includes(device.value) ? 'active' : ''}`}
                    aria-pressed={selectedDevices.includes(device.value)}
                    onClick={() => onDevicesChange?.(toggled(selectedDevices, device.value))}
                  >
                    <DeviceGlyph device={device.value} size={24} />
                    {device.label}
                    <em className="ctx-choice-hint">{device.viewport.split('x')[0]} px</em>
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="ctx-options">
            <Presets
              label="Ralenti"
              presets={SLOWMO_PRESETS}
              value={slowMo}
              onChange={handleSlowMoChange}
            />
            <Presets
              label="Trace Playwright"
              presets={TRACING_PRESETS}
              value={tracing}
              onChange={handleTracingChange}
            />

            <div className="ctx-option ctx-mobile">
              <span className="ctx-label">
                Mobile (Appium)
                {mobileStatus && (
                  <span className={`ctx-badge ${mobileStatus.ok ? 'ok' : 'ko'}`}>
                    {mobileStatus.ok ? 'Prêt' : 'Incomplet'}
                  </span>
                )}
              </span>
              {mobileStatus ? (
                <>
                  <div className="ctx-checks">
                    {(mobileStatus.checks || []).map((check, i) => (
                      <span key={i} className="ctx-check" title={check.hint || ''}>
                        <span
                          className={`ctx-dot ${
                            check.ok === true ? 'ok' : check.ok === false ? 'ko' : 'na'
                          }`}
                        />
                        {check.name}
                      </span>
                    ))}
                  </div>
                  <button
                    type="button"
                    className="ctx-appium"
                    disabled={appiumBusy}
                    onClick={mobileStatus.appium_online ? stopAppium : startAppium}
                  >
                    {appiumBusy
                      ? 'Patientez…'
                      : mobileStatus.appium_online
                        ? '■ Arrêter Appium'
                        : '▶ Démarrer Appium'}
                  </button>
                </>
              ) : (
                <span className="ctx-hint">Vérification…</span>
              )}
            </div>
          </div>

          <div className="ctx-foot">
            {sessions === 1
              ? '1 session'
              : `${sessions} sessions - chaque combinaison navigateur × appareil est jouée`}
          </div>
        </div>
      )}
    </header>
  );
};

export default Header;
