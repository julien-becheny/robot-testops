import { useEffect, useState } from 'react';
import { FiAlertTriangle, FiCheckCircle, FiPlay, FiSmartphone, FiZap } from 'react-icons/fi';
import { API_BASE_URL } from '../config/api';
import { BROWSERS, DEVICES } from '../components/Header';
import ActionButton from '../components/ActionButton';
import '../css/LaunchPage.css';

const labelOf = (list, value) => list.find((entry) => entry.value === value)?.label || value;

const smokeDescriptor = (selectedBrowsers, selectedDevices) => {
  const combos = selectedBrowsers.flatMap((browser) =>
    selectedDevices.map((device) => `${labelOf(BROWSERS, browser)} · ${labelOf(DEVICES, device)}`)
  );

  return {
    icon: FiZap,
    title: 'Smoke test',
    subtitle:
      'Vérifie que la chaîne complète répond : navigateur, application, assertions. À jouer avant tout le reste.',
    cards: [
      {
        label: 'Ce qui va tourner',
        value: '00_smoke.robot',
        hint: 'Suite web SauceDemo',
      },
      {
        label: 'Sur quelles cibles',
        value: `${combos.length} combinaison${combos.length > 1 ? 's' : ''}`,
        hint: combos.join(', '),
      },
      {
        label: 'Pendant le run',
        value: 'Logs en direct',
        hint: 'Un run par combinaison, lancés à la suite',
      },
    ],
    steps: [
      "Ouvre le navigateur sur l'URL cible affichée en haut.",
      'Joue la suite smoke sur chaque combinaison sélectionnée.',
      'Bascule sur « Exécution » : logs en direct, puis rapport.',
    ],
    actionLabel: 'Lancer le smoke test',
  };
};

const appiumDescriptor = () => ({
  icon: FiSmartphone,
  title: 'Tests sur mobile physique',
  subtitle:
    "Joue les tests sur l'appareil Android connecté, via Appium. Les tests multi-moteur partent aussi dans les runs habituels, avec Playwright : ils sont écrits une seule fois.",
  cards: [
    {
      label: 'Ce qui va tourner',
      value: 'appium/ + multi_moteur/',
      hint: 'Spécifiquement mobile, et tests portables',
    },
    {
      label: 'Moteur',
      value: 'Appium',
      hint: 'Chrome sur appareil réel ou émulateur',
    },
    {
      label: 'Avant le run',
      value: 'Appium démarré',
      hint: "Lancé automatiquement, run annulé s'il ne répond pas",
    },
  ],
  steps: [
    "Démarre le serveur Appium s'il ne tourne pas déjà, et attend qu'il réponde.",
    "Joue les suites mobile sur l'appareil connecté.",
    'Bascule sur « Exécution » : logs en direct, puis rapport.',
  ],
  actionLabel: 'Lancer sur mobile',
});

// Etat reel de la chaine mobile plutot qu'un avertissement permanent : affiche en
// continu, il ne se distinguerait plus du bruit le jour ou l'appareil manque vraiment.
const MobileStatus = () => {
  const [state, setState] = useState(null);

  useEffect(() => {
    let alive = true;
    fetch(`${API_BASE_URL}/mobile-preflight`)
      .then((res) => res.json())
      .then((data) => alive && setState(data))
      .catch(() => alive && setState({ unreachable: true }));
    return () => {
      alive = false;
    };
  }, []);

  if (!state) return null;

  if (state.unreachable) {
    return (
      <p className="launch-warning">
        <FiAlertTriangle size={15} />
        <span>Etat mobile indisponible : le backend n’a pas répondu.</span>
      </p>
    );
  }

  if (state.ok) {
    const device = state.checks?.find((check) => check.name === 'Appareil Android')?.detail;
    const server = state.appium_online ? 'Appium en ligne' : 'Appium sera démarré au lancement';
    return (
      <p className="launch-status-ok">
        <FiCheckCircle size={15} />
        <span>{device ? `Appareil ${device} détecté · ${server}` : server}</span>
      </p>
    );
  }

  const missing = (state.checks || []).filter((check) => check.ok === false);
  return (
    <div className="launch-warning launch-warning-list">
      <FiAlertTriangle size={15} />
      <ul>
        {missing.map((check) => (
          <li key={check.name}>
            {check.name} : {check.detail}
            {check.hint ? ` - ${check.hint}` : ''}
          </li>
        ))}
      </ul>
    </div>
  );
};

const LaunchPage = ({ kind, selectedBrowsers = [], selectedDevices = [], onLaunch }) => {
  const descriptor =
    kind === 'smoke' ? smokeDescriptor(selectedBrowsers, selectedDevices) : appiumDescriptor();
  const Icon = descriptor.icon;

  return (
    <div className="launch-page">
      <header className="launch-head">
        <span className="launch-head-icon">
          <Icon size={26} />
        </span>
        <div>
          <h1 className="launch-title">{descriptor.title}</h1>
          <p className="launch-subtitle">{descriptor.subtitle}</p>
        </div>
      </header>

      <div className="launch-cards">
        {descriptor.cards.map((card) => (
          <div key={card.label} className="launch-card">
            <span className="launch-card-label">{card.label}</span>
            <span className="launch-card-value">{card.value}</span>
            <span className="launch-card-hint">{card.hint}</span>
          </div>
        ))}
      </div>

      <section className="launch-steps">
        <h2 className="launch-section-title">Déroulé</h2>
        <ol>
          {descriptor.steps.map((step, index) => (
            <li key={step}>
              <span className="launch-step-index">{index + 1}</span>
              <span>{step}</span>
            </li>
          ))}
        </ol>
      </section>

      {descriptor.warning && (
        <p className="launch-warning">
          <FiAlertTriangle size={15} />
          <span>{descriptor.warning}</span>
        </p>
      )}

      {kind === 'appium' && <MobileStatus />}

      <div className="launch-action">
        <ActionButton icon={FiPlay} onClick={onLaunch}>
          {descriptor.actionLabel}
        </ActionButton>
        <span className="launch-note">
          Plateforme, navigateurs, appareils et URL cible se règlent dans la barre du haut.
        </span>
      </div>
    </div>
  );
};

export default LaunchPage;
