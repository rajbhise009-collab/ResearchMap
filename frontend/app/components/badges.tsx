import type { Tier } from "../../lib/types";

export function TierBadge({ tier }: { tier: Tier }) {
  return (
    <span className={`tier ${tier}`} title={`Confidence tier: ${tier}`}>
      <span className="dot" />
      {tier} confidence
    </span>
  );
}

export function GapPill({ gap }: { gap: string }) {
  return <span className="pill gap">{gap.replace(/_/g, " ")}</span>;
}

export function AbstractBadge() {
  return (
    <span
      className="badge-abstract"
      title="Abstract-only paper — yields ~11x fewer own-work limitations than full text"
    >
      abstract-only
    </span>
  );
}

const CONFIRM_LABEL: Record<string, string> = {
  substantive: "SUBSTANTIVE",
  trivial: "TRIVIAL (larger-eval / apply-to-dataset)",
  not_addressing: "NOT ADDRESSING",
  unconfirmed: "UNCONFIRMED",
};

export function ConfirmBadge({ status }: { status: string | null }) {
  const s = status || "unconfirmed";
  return <span className={`confirm ${s}`}>{CONFIRM_LABEL[s] ?? s}</span>;
}
