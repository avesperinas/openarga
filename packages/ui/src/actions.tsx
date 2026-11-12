import { Icon, type IconName } from "./icons";

export interface QuickAction {
  icon: IconName;
  label: string;
  detail?: string;
  primary?: boolean;
  href?: string;
  onClick?: () => void;
}

export function QuickActions({ actions, label }: { actions: QuickAction[]; label: string }) {
  return (
    <nav className="quick-actions" aria-label={label}>
      {actions.map((action) => {
        const body = (
          <>
            <Icon name={action.icon} />
            <span className="quick-action-label">{action.label}</span>
            {action.detail && <span className="quick-action-detail">{action.detail}</span>}
          </>
        );
        return action.href ? (
          <a key={action.label} className="quick-action" data-primary={action.primary || undefined} href={action.href}>
            {body}
          </a>
        ) : (
          <button key={action.label} type="button" className="quick-action" data-primary={action.primary || undefined} onClick={action.onClick}>
            {body}
          </button>
        );
      })}
    </nav>
  );
}
