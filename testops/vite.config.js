import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// La démonstration publique est un build statique : pas de serveur, donc pas de
// socket. Le client réel est remplacé par un équivalent local, et le site est
// servi depuis un sous-chemin sur GitHub Pages.
// Jamais en test : la variable laissée dans un terminal remplacerait le client
// que les tests moquent, et 32 d'entre eux tomberaient sans rapport avec la cause.
export default defineConfig(() => {
  const demo = process.env.VITE_DEMO === '1' && !process.env.VITEST;

  return {
    plugins: [react()],
    base: demo ? '/robot-testops/' : '/',
    resolve: {
      alias: demo ? { 'socket.io-client': '/src/demo/socket.js' } : {},
    },
    server: {
      host: '127.0.0.1',
      port: 3000,
      strictPort: true,
    },
    build: {
      outDir: 'build',
    },
    test: {
      environment: 'jsdom',
      setupFiles: './src/setupTests.js',
      // Vite expose toute variable `VITE_*` de l'environnement : celle laissée dans un
      // terminal après un build de démonstration ferait basculer l'application en mode
      // simulé, et les tests échoueraient loin de la cause.
      env: { VITE_DEMO: '' },
    },
  };
});
