import { Search } from "lucide-react";

/**
 * Input personalizado estilo Consolita: glass, focus violeta, opcional icono/suffix.
 */
export default function Field({
  label,
  hint,
  icon = null,
  suffix = null,
  as = "input",
  className = "",
  type = "text",
  ...props
}) {
  const Tag = as === "textarea" ? "textarea" : as === "select" ? "select" : "input";
  const showSearch = icon === "search" || type === "search";

  const shellExtra = [
    showSearch || icon ? "has-icon" : "",
    suffix ? "has-suffix" : "",
    className.includes("pill") ? "pill" : "",
    className.includes("compact") ? "compact" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <label className={`field-block ${className}`}>
      {label ? <span className="field-label">{label}</span> : null}
      <div className={`field-shell ${shellExtra}`}>
        {showSearch ? (
          <span className="field-icon" aria-hidden="true">
            <Search size={14} />
          </span>
        ) : icon ? (
          <span className="field-icon" aria-hidden="true">
            {icon}
          </span>
        ) : null}
        <Tag
          className="field-control"
          type={as === "input" ? (type === "search" ? "text" : type) : undefined}
          {...props}
        />
        {suffix ? <span className="field-suffix">{suffix}</span> : null}
      </div>
      {hint ? <span className="field-hint">{hint}</span> : null}
    </label>
  );
}
