import { ReactNode } from 'react';
import { EngineStatusPanel, EngineStatusData } from './EngineStatusPanel';

export interface AppShellProps {
  children: ReactNode;
  activeTab: 'studio' | 'transcripts' | 'history';
  onTabChange: (tab: 'studio' | 'transcripts' | 'history') => void;
  serviceOnline?: boolean;
  engineStatus?: EngineStatusData;
}

export const AppShell: React.FC<AppShellProps> = ({
  children,
  activeTab,
  onTabChange,
  serviceOnline = true,
  engineStatus,
}) => {
  return (
    <div className="saas-app-shell">
      {/* Skip Navigation Link for Screen Readers and Keyboard Navigation */}
      <a href="#main-content" className="skip-to-content-link">
        Skip to main content
      </a>

      {/* Accessible Sidebar Navigation */}
      <aside className="app-sidebar" aria-label="Application Sidebar">
        <div className="brand-lockup">
          <div className="brand-logo" aria-hidden="true">
            <span>A</span>
          </div>
          <div className="brand-text">
            <span className="brand-name">AcademiaAI</span>
            <span className="brand-sub">Voice Co-Pilot</span>
          </div>
        </div>

        <nav className="sidebar-nav" aria-label="Main Navigation">
          <div className="nav-group-label" id="workspace-label">
            WORKSPACE
          </div>
          <ul className="nav-list" role="menu" aria-labelledby="workspace-label">
            <li role="none">
              <button
                type="button"
                role="menuitem"
                className={`nav-button ${activeTab === 'studio' ? 'is-active' : ''}`}
                onClick={() => onTabChange('studio')}
                aria-current={activeTab === 'studio' ? 'page' : undefined}
              >
                <span className="nav-icon" aria-hidden="true">🎙</span>
                <span className="nav-label">Voice Studio</span>
              </button>
            </li>

            <li role="none">
              <button
                type="button"
                role="menuitem"
                className={`nav-button ${activeTab === 'transcripts' ? 'is-active' : ''}`}
                onClick={() => onTabChange('transcripts')}
                aria-current={activeTab === 'transcripts' ? 'page' : undefined}
              >
                <span className="nav-icon" aria-hidden="true">📄</span>
                <span className="nav-label">Live Transcripts</span>
              </button>
            </li>

            <li role="none">
              <button
                type="button"
                role="menuitem"
                className={`nav-button ${activeTab === 'history' ? 'is-active' : ''}`}
                onClick={() => onTabChange('history')}
                aria-current={activeTab === 'history' ? 'page' : undefined}
              >
                <span className="nav-icon" aria-hidden="true">🕒</span>
                <span className="nav-label">Session History</span>
              </button>
            </li>
          </ul>
        </nav>

        {/* Engine Status Panel */}
        <EngineStatusPanel status={engineStatus} />

        <div className="sidebar-footer">
          <div className="user-profile-badge">
            <div className="avatar-circle" aria-hidden="true">
              U
            </div>
            <div className="profile-details">
              <span className="profile-name">Academia User</span>
              <span className="profile-role">Standard Workspace</span>
            </div>
          </div>
        </div>
      </aside>

      {/* Main App Layout */}
      <div className="app-main-layout">
        <header className="app-topbar" role="banner">
          <div className="topbar-breadcrumb">
            <span className="crumb-root">WORKSPACE</span>
            <span className="crumb-separator" aria-hidden="true">/</span>
            <span className="crumb-current">
              {activeTab === 'studio' && 'VOICE STUDIO'}
              {activeTab === 'transcripts' && 'TRANSCRIPTS'}
              {activeTab === 'history' && 'RECORDING HISTORY'}
            </span>
          </div>

          <div className="topbar-actions">
            <div
              className="system-health-pill"
              role="status"
              aria-label={`System status: ${serviceOnline ? 'Service Online' : 'Service Offline'}`}
            >
              <span
                className={`health-dot ${serviceOnline ? 'is-online' : 'is-offline'}`}
                aria-hidden="true"
              />
              <span className="health-label">
                {serviceOnline ? 'SYSTEM READY' : 'OFFLINE'}
              </span>
            </div>
          </div>
        </header>

        <main id="main-content" className="app-content-container" tabIndex={-1}>
          {children}
        </main>

        <footer className="app-footer" role="contentinfo">
          <span className="footer-copyright">
            © {new Date().getFullYear()} AcademiaAI · AI Voice Co-Pilot
          </span>
          <span className="footer-standard">
            Enterprise Voice Interface · WCAG 2.1 AA Compliant
          </span>
        </footer>
      </div>
    </div>
  );
};
