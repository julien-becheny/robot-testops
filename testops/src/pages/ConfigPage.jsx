import { useState, useEffect, useCallback } from 'react';
import { FiCheck, FiEdit2, FiSave, FiTool, FiTrash2, FiX } from 'react-icons/fi';
import { API_BASE_URL } from '../config/api';
import '../css/ConfigPage.css';

const MASKED_CONFIG_VALUE = '********';
const SENSITIVE_KEY_MARKERS = ['PASSWORD', 'PASSWD', 'SECRET', 'TOKEN', 'API_KEY', 'APIKEY'];
const isSensitiveKey = (key) => SENSITIVE_KEY_MARKERS.some((marker) => key.includes(marker));

const ConfigPage = () => {
  const [configVars, setConfigVars] = useState({});
  const [loading, setLoading] = useState(true);
  const [editingKey, setEditingKey] = useState(null);
  const [editValue, setEditValue] = useState('');
  const [saveStatus, setSaveStatus] = useState(null);

  const fetchConfig = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/config-vars`);
      setConfigVars(await res.json());
    } catch (err) {
      console.error('Erreur chargement config:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  const startEditing = (key, value) => {
    setEditingKey(key);
    setEditValue(isSensitiveKey(key) ? '' : value || '');
    setSaveStatus(null);
  };

  const saveValue = useCallback(async () => {
    if (!editingKey || (isSensitiveKey(editingKey) && !editValue)) return;
    try {
      const res = await fetch(`${API_BASE_URL}/config-vars`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: editingKey, value: editValue || null }),
      });
      const data = await res.json();

      if (res.ok) {
        setConfigVars((prev) => ({ ...prev, [editingKey]: data.value }));
        setEditValue('');
        setSaveStatus('success');
        setTimeout(() => {
          setEditingKey(null);
          setSaveStatus(null);
        }, 1000);
      } else {
        setSaveStatus('error');
      }
    } catch {
      setSaveStatus('error');
    }
  }, [editingKey, editValue]);

  const cancelEditing = () => {
    setEditingKey(null);
    setEditValue('');
    setSaveStatus(null);
  };

  const clearSensitiveValue = useCallback(
    async (key) => {
      try {
        const res = await fetch(`${API_BASE_URL}/config-vars`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ key, value: null }),
        });
        const data = await res.json();
        if (!res.ok) return;
        setConfigVars((prev) => ({ ...prev, [key]: data.value }));
        if (editingKey === key) cancelEditing();
      } catch {
        setSaveStatus('error');
      }
    },
    [editingKey]
  );

  if (loading) {
    return (
      <div className="config-page">
        <p>Chargement...</p>
      </div>
    );
  }

  return (
    <div className="config-page">
      <div className="config-header">
        <h2>
          <FiTool size={18} /> Configuration
        </h2>
      </div>

      <div className="config-table">
        <div className="config-row header-row">
          <span className="config-key">Variable</span>
          <span className="config-value">Valeur</span>
          <span className="config-action">Action</span>
        </div>

        {Object.entries(configVars)
          .sort()
          .map(([key, value]) => {
            const sensitive = isSensitiveKey(key);
            const configuredSecret = sensitive && value === MASKED_CONFIG_VALUE;
            return (
              <div key={key} className="config-row">
                <span className="config-key">{key}</span>

                {editingKey === key ? (
                  <span className="config-value editing">
                    <input
                      type={sensitive ? 'password' : 'text'}
                      value={editValue}
                      onChange={(e) => setEditValue(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && saveValue()}
                      placeholder={sensitive ? 'Nouvelle valeur' : undefined}
                      autoFocus
                    />
                    <button
                      className="save-btn"
                      onClick={saveValue}
                      disabled={sensitive && !editValue}
                      title="Enregistrer"
                    >
                      {saveStatus === 'success' ? <FiCheck size={15} /> : <FiSave size={15} />}
                    </button>
                    <button className="cancel-btn" onClick={cancelEditing} title="Annuler">
                      <FiX size={15} />
                    </button>
                  </span>
                ) : (
                  <>
                    <span className="config-value">
                      {configuredSecret ? '••••••' : (value ?? '—')}
                    </span>
                    <span className="config-action">
                      <button
                        className="edit-btn"
                        onClick={() => startEditing(key, value)}
                        title="Modifier"
                      >
                        <FiEdit2 size={14} />
                      </button>
                      {configuredSecret && (
                        <button
                          className="clear-btn"
                          onClick={() => clearSensitiveValue(key)}
                          title="Effacer la valeur"
                          aria-label={`Effacer ${key}`}
                        >
                          <FiTrash2 />
                        </button>
                      )}
                    </span>
                  </>
                )}
              </div>
            );
          })}
      </div>
    </div>
  );
};

export default ConfigPage;
