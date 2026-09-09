// Ce sur quoi le run est PARTI, figé au lancement : la barre du haut, elle, peut changer.
import { BROWSERS, DEVICES } from '../Header';
import '../../css/execution/RunContext.css';

const RunContext = ({ context, fallback }) => {
  if (!context) return <span className="run-context-fallback">{fallback}</span>;

  const browser = BROWSERS.find((b) => b.value === context.browser);
  const device = DEVICES.find((d) => d.value === context.device);
  const DeviceIcon = device?.icon;

  return (
    <div className="run-context">
      {context.env && (
        <span className="run-context-item" title={context.env.base || ''}>
          <span className="run-context-planet" aria-hidden="true" />
          {context.env.label}
        </span>
      )}
      <span className="run-context-item">
        {browser ? (
          <>
            <img src={browser.icon} alt="" width="15" height="15" />
            {browser.label}
          </>
        ) : (
          fallback
        )}
      </span>
      {DeviceIcon && (
        <span className="run-context-item">
          <DeviceIcon size={14} />
          {device.label}
        </span>
      )}
    </div>
  );
};

export default RunContext;
