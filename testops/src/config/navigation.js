import { FiHome, FiSliders, FiTag, FiZap } from 'react-icons/fi';

// Source unique des entrées : la barre latérale et l'accueil lisent ce fichier.
// `color` n'habille que les gros blocs de l'accueil — le rail, lui, reste monochrome.
export const HOME_ITEM = { id: 'home', label: 'Accueil', icon: FiHome, color: '#38bdf8' };

export const NAV_SECTIONS = [
  {
    id: 'run',
    label: 'Exécuter',
    items: [
      {
        id: 'smoke',
        label: 'Smoke test',
        icon: FiZap,
        color: '#fbbf24',
        desc: 'Vérification rapide de la chaîne',
      },
      {
        id: 'tags',
        label: 'Exécution par tags',
        icon: FiTag,
        color: '#38bdf8',
        desc: 'Sélection ciblée dans les suites',
      },
    ],
  },
  {
    id: 'admin',
    label: 'Administrer',
    items: [
      {
        id: 'config',
        label: 'Configuration',
        icon: FiSliders,
        color: '#94a3b8',
        desc: "Variables d'environnement",
      },
    ],
  },
];

export const NAV_ITEMS = NAV_SECTIONS.flatMap((section) => section.items);

export const findNavItem = (id) => NAV_ITEMS.find((item) => item.id === id);
