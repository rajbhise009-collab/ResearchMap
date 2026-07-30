import type { Caveat } from "../../lib/types";

export default function Caveats({ caveats }: { caveats: Caveat[] }) {
  if (!caveats.length) return null;
  return (
    <div className="caveats">
      {caveats.map((c) => (
        <div className="caveat" key={c.code}>
          <span className="k">{c.label}:</span>
          <span>{c.detail}</span>
        </div>
      ))}
    </div>
  );
}
