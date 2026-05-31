import { useI18n, type Language } from "../../i18n";

const LANGUAGE_OPTIONS: Array<{ value: Language; label: string; description: string }> = [
  { value: "en", label: "English", description: "Default" },
  { value: "zh-CN", label: "Chinese", description: "Simplified Chinese" },
];

type GlobalSettingsDrawerProps = {
  open: boolean;
  onClose(): void;
};

export function GlobalSettingsDrawer({ open, onClose }: GlobalSettingsDrawerProps) {
  const { language, setLanguage } = useI18n();
  const current = LANGUAGE_OPTIONS.find((o) => o.value === language) ?? LANGUAGE_OPTIONS[0];

  if (!open) return null;

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside
        className="settings-drawer global-settings-drawer"
        role="dialog"
        aria-modal="true"
        aria-label="Global settings"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="drawer-header">
          <div>
            <h2>Global Settings</h2>
            <p>Workbench preferences and interface display.</p>
          </div>
          <button type="button" className="ghost-button drawer-close" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="drawer-body">
          <section className="drawer-section">
            <div className="drawer-section-heading">
              <div>
                <h3>Interface</h3>
                <p>Choose the display language for the workbench.</p>
              </div>
            </div>

            <div className="global-setting-row">
              <div>
                <strong>Language</strong>
                <span>Current: <span data-i18n-skip>{current.label}</span></span>
              </div>
              <div className="language-choice-group" role="radiogroup" aria-label="Language">
                {LANGUAGE_OPTIONS.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    className={language === option.value ? "ghost-button language-choice active" : "ghost-button language-choice"}
                    aria-pressed={language === option.value}
                    onClick={() => setLanguage(option.value)}
                  >
                    <strong data-i18n-skip>{option.label}</strong>
                    <small data-i18n-skip>{option.description}</small>
                  </button>
                ))}
              </div>
            </div>
          </section>
        </div>
      </aside>
    </div>
  );
}
