import {
  Home,
  MessageCircle,
  Boxes,
  Wand2,
  Store,
  FolderOpen,
  ScrollText,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import BrandTypewriter from "./BrandTypewriter";
import avatarImg from "../assets/avatar.png";

function DiscordIcon({ size = 13, className = "" }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="currentColor"
      className={className}
      aria-hidden="true"
    >
      <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994.021-.041.001-.09-.041-.106a13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.929 1.793 8.18 1.793 12.061 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.894.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.028zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z" />
    </svg>
  );
}

export default function Sidebar({
  active,
  onNavigate,
  collapsed,
  onToggle,
  proxyOn,
  tricksCount = 0,
  lolaCount = 0,
}) {
  const sections = [
    {
      title: "Inicio",
      items: [{ id: "home", label: "Panel", icon: Home }],
    },
    {
      title: "Items",
      items: [
        { id: "lola", label: "Lola", icon: MessageCircle, badge: lolaCount || null },
        { id: "objetos", label: "Objetos", icon: Boxes },
        {
          id: "trucar",
          label: "Trucar",
          icon: Wand2,
          badge: tricksCount > 0 ? tricksCount : null,
        },
        { id: "tiendas", label: "Behaviors", icon: Store },
      ],
    },
    {
      title: "Sistema",
      items: [
        { id: "archivos", label: "Archivos", icon: FolderOpen },
        { id: "logs", label: "Logs", icon: ScrollText },
      ],
    },
  ];
  return (
    <aside className={`sidebar app-no-drag ${collapsed ? "collapsed" : ""}`}>
      <div className="sidebar-top">
        <div className="brand">
          <div className="brand-mark" title="naw">
            <img src={avatarImg} alt="naw" className="brand-avatar" />
            <span
              className={`live-dot ${proxyOn ? "on" : ""}`}
              title={proxyOn ? "Proxy activo" : "Proxy inactivo"}
            />
          </div>
          <div className="brand-info">
            <BrandTypewriter />
            <a
              href="https://discord.gg/HcKHSXKjeJ"
              target="_blank"
              rel="noreferrer"
              className="brand-discord"
              title="Discord: /naw9x19"
            >
              <DiscordIcon size={12} />
              <span>/naw9x19</span>
            </a>
          </div>
        </div>
        <button
          className="icon-btn"
          onClick={onToggle}
          title={collapsed ? "Expandir" : "Colapsar"}
        >
          {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
        </button>
      </div>

      <nav className="sidebar-nav">
        {sections.map((sec) => (
          <div key={sec.title} className="nav-section">
            <span className="nav-section-title">{sec.title}</span>
            {sec.items.map((item) => {
              const Icon = item.icon;
              return (
                <button
                  key={item.id}
                  className={`nav-item ${active === item.id ? "active" : ""}`}
                  onClick={() => onNavigate(item.id)}
                  title={item.badge ? `${item.label} (${item.badge})` : item.label}
                >
                  <Icon size={16} />
                  <span className="nav-text">{item.label}</span>
                  {item.badge != null && item.badge !== "" && item.badge !== 0 && !collapsed && (
                    <span className="nav-badge active-count">
                      {item.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        ))}
      </nav>
    </aside>
  );
}
