import { useState } from 'react';
import { FiChevronsLeft, FiChevronsRight, FiTerminal } from 'react-icons/fi';
import Header from './Header';
import { HOME_ITEM, NAV_SECTIONS } from '../config/navigation';
import '../css/AppShell.css';

const AppShell = ({
  currentPage,
  onNavigate,
  runningCount = 0,
  sessionCount = 0,
  selectedBrowsers,
  onBrowsersChange,
  selectedDevices,
  onDevicesChange,
  onEnvironmentChange,
  children,
}) => {
  const [collapsed, setCollapsed] = useState(false);

  const renderItem = (item) => {
    const Icon = item.icon;
    const active = currentPage === item.id;
    return (
      <button
        key={item.id}
        type="button"
        className={`shell-nav-item ${active ? 'active' : ''}`}
        aria-current={active ? 'page' : undefined}
        title={collapsed ? item.label : undefined}
        onClick={() => onNavigate(item.id)}
      >
        <span className="shell-nav-icon">
          <Icon size={16} strokeWidth={1.7} />
        </span>
        <span className="shell-nav-label">{item.label}</span>
      </button>
    );
  };

  const executionActive = currentPage === 'execution';

  return (
    <div className={`shell ${collapsed ? 'collapsed' : ''}`}>
      <Header
        selectedBrowsers={selectedBrowsers}
        onBrowsersChange={onBrowsersChange}
        selectedDevices={selectedDevices}
        onDevicesChange={onDevicesChange}
        onEnvironmentChange={onEnvironmentChange}
      />

      <div className="shell-body">
        <nav className="shell-sidebar" aria-label="Navigation principale">
          <div className="shell-nav-scroll">
            <div className="shell-nav-section">{renderItem(HOME_ITEM)}</div>
            {NAV_SECTIONS.map((section) => (
              <div key={section.id} className="shell-nav-section">
                <span className="shell-nav-section-label">{section.label}</span>
                {section.items.map(renderItem)}
              </div>
            ))}
          </div>

          <div className="shell-sidebar-footer">
            {sessionCount > 0 && (
              <button
                type="button"
                className={`shell-nav-item shell-run-badge ${executionActive ? 'active' : ''} ${
                  runningCount > 0 ? 'live' : ''
                }`}
                aria-current={executionActive ? 'page' : undefined}
                title={collapsed ? 'Exécution' : undefined}
                onClick={() => onNavigate('execution')}
              >
                <span className="shell-nav-icon">
                  {runningCount > 0 ? <span className="shell-run-dot" /> : <FiTerminal size={16} />}
                </span>
                <span className="shell-nav-label">
                  {runningCount > 0
                    ? `${runningCount} run${runningCount > 1 ? 's' : ''} en cours`
                    : 'Dernière exécution'}
                </span>
              </button>
            )}

            <button
              type="button"
              className="shell-collapse"
              onClick={() => setCollapsed((c) => !c)}
              title={collapsed ? 'Déplier le menu' : 'Replier le menu'}
              aria-label={collapsed ? 'Déplier le menu' : 'Replier le menu'}
            >
              {collapsed ? <FiChevronsRight size={16} /> : <FiChevronsLeft size={16} />}
              <span className="shell-nav-label">Replier</span>
            </button>
          </div>
        </nav>

        <main className="shell-main">{children}</main>
      </div>
    </div>
  );
};

export default AppShell;
