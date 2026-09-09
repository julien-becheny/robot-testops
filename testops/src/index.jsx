import ReactDOM from 'react-dom/client';
// Polices auto-hebergees : l'outil doit s'afficher a l'identique sans reseau.
import './css/fonts.css';
import App from './App';
import './index.css';

const render = () => ReactDOM.createRoot(document.getElementById('root')).render(<App />);

// Le backend simulé doit détourner `fetch` AVANT que la première page ne l'appelle.
if (import.meta.env.VITE_DEMO === '1') {
  Promise.all([import('./demo/backend'), import('./demo/banner')]).then(([backend, banner]) => {
    backend.installDemoBackend();
    banner.mountDemoRibbon();
    render();
  });
} else {
  render();
}
