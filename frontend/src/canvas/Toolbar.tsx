import type { ReactNode } from "react";

export const PEN_COLORS = [
  { name: "Negro", value: "#111111" },
  { name: "Rojo", value: "#d92d20" },
  { name: "Verde", value: "#16803c" },
  { name: "Azul", value: "#1d4ed8" },
];
export const PEN_SIZES = [
  { name: "Fino", value: 1.2 },
  { name: "Medio", value: 1.8 },
  { name: "Grueso", value: 3 },
];

export type ToolKind = "pen" | "highlighter" | "eraser" | "lasso";

interface Props {
  active: ToolKind;
  pen: number;
  size: number;
  canUndo: boolean;
  canRedo: boolean;
  hasSelection: boolean;
  onTool(kind: ToolKind): void;
  onPen(index: number): void;
  onSize(index: number): void;
  onUndo(): void;
  onRedo(): void;
  onDeleteSelection(): void;
  onBackground(): void;
  onAddPage(): void;
  onLibrary(): void;
  /** Entries of the "more" menu: page and export commands. */
  menu: { label: string; danger?: boolean; run(): void }[];
}

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {children}
    </svg>
  );
}

function Button(props: { label: string; pressed?: boolean; disabled?: boolean; onClick(): void; children: ReactNode }) {
  return (
    <button type="button" className="tool" aria-label={props.label} title={props.label} aria-pressed={props.pressed} disabled={props.disabled} onClick={props.onClick}>
      {props.children}
    </button>
  );
}

export function Toolbar(p: Props) {
  return (
    <div className="toolbar" role="toolbar" aria-label="Herramientas">
      <Button label="Biblioteca: materias y cuadernos" onClick={p.onLibrary}>
        <Icon>
          <path d="M5 4v16M9 4v16M13 5l5 15M4 20h16" />
        </Icon>
      </Button>
      <span className="sep" />
      <Button label="Lazo: seleccionar, mover y estirar" pressed={p.active === "lasso"} onClick={() => p.onTool("lasso")}>
        <Icon>
          <ellipse cx="12" cy="10" rx="8" ry="5.5" strokeDasharray="3 2.5" />
          <path d="M7 14.5c-1 1.5-1 3.5 1 5" />
        </Icon>
      </Button>
      <span className="sep" />
      {PEN_COLORS.map((c, i) => (
        <Button key={c.value} label={`Pluma ${c.name.toLowerCase()}`} pressed={p.active === "pen" && p.pen === i} onClick={() => p.onPen(i)}>
          <span className="swatch" style={{ background: c.value }} />
        </Button>
      ))}
      <span className="sep" />
      {PEN_SIZES.map((s, i) => (
        <Button key={s.value} label={`Grosor ${s.name.toLowerCase()}`} pressed={p.size === i} onClick={() => p.onSize(i)}>
          <span className="dot" style={{ width: 4 + i * 4, height: 4 + i * 4 }} />
        </Button>
      ))}
      <span className="sep" />
      <Button label="Resaltador" pressed={p.active === "highlighter"} onClick={() => p.onTool("highlighter")}>
        <Icon>
          <path d="M9 14l-3 3v3h3l3-3" />
          <path d="M9 14l7-9 4 4-8 8z" fill="#ffd400" />
        </Icon>
      </Button>
      <Button label="Borrador: borra y vuelve a la pluma" pressed={p.active === "eraser"} onClick={() => p.onTool("eraser")}>
        <Icon>
          <path d="M8 19l-4-4L14 5l6 6-8 8z" />
          <path d="M9.5 9.5l6 6M8 19h11" />
        </Icon>
      </Button>
      {p.hasSelection && (
        <Button label="Borrar la selección" onClick={p.onDeleteSelection}>
          <Icon>
            <path d="M5 7h14M10 7V4h4v3M7 7l1 13h8l1-13M10 11v6M14 11v6" />
          </Icon>
        </Button>
      )}
      <span className="sep" />
      <Button label="Deshacer" disabled={!p.canUndo} onClick={p.onUndo}>
        <Icon>
          <path d="M8 6L4 10l4 4" />
          <path d="M4 10h10a5 5 0 010 10h-3" />
        </Icon>
      </Button>
      <Button label="Rehacer" disabled={!p.canRedo} onClick={p.onRedo}>
        <Icon>
          <path d="M16 6l4 4-4 4" />
          <path d="M20 10H10a5 5 0 000 10h3" />
        </Icon>
      </Button>
      <span className="sep" />
      <Button label="Cambiar fondo: cuadrícula, rayado o blanco" onClick={p.onBackground}>
        <Icon>
          <rect x="4" y="4" width="16" height="16" rx="2" />
          <path d="M4 10h16M4 15h16M10 4v16M15 4v16" />
        </Icon>
      </Button>
      <Button label="Agregar página" onClick={p.onAddPage}>
        <Icon>
          <path d="M6 3h8l4 4v14H6z" />
          <path d="M12 10v6M9 13h6" />
        </Icon>
      </Button>
      {/* Native popover: opens and closes with no state of ours, and closes on a tap outside. */}
      <button type="button" className="tool" aria-label="Más: exportar y páginas" title="Más: exportar y páginas" popoverTarget="notebook-menu">
        <Icon>
          <circle cx="5" cy="12" r="1.2" />
          <circle cx="12" cy="12" r="1.2" />
          <circle cx="19" cy="12" r="1.2" />
        </Icon>
      </button>
      <div id="notebook-menu" popover="auto" className="menu">
        {p.menu.map((item) => (
          <button key={item.label} type="button" className={item.danger ? "danger" : undefined} popoverTarget="notebook-menu" popoverTargetAction="hide" onClick={item.run}>
            {item.label}
          </button>
        ))}
      </div>
    </div>
  );
}
