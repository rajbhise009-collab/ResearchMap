"use client";
import "./states.css";
// Loading and error states, shared by every page that loads a library file.
// Never blank: loading shows the shape of what is coming plus one plain line;
// an error says what failed and offers the one fix a reader can try. No
// progress bars or percentages (there is no honest number to show).

export function LoadingCards({ label, count = 3, detail = false }: {
  label: string;
  count?: number;
  /** A detail page: a title block and paragraphs instead of a list of cards. */
  detail?: boolean;
}) {
  return (
    <div className="loading-state">
      <p className="loading-line" role="status">
        <span className="swatch" aria-hidden /> {label}
      </p>
      <div aria-hidden>
        {detail ? (
          <div className="skel-detail">
            <div className="skel-head" />
            <div className="skel-title" />
            <div className="skel-title b" />
            <div className="skel-line" /><div className="skel-line" /><div className="skel-line s" />
          </div>
        ) : (
          Array.from({ length: count }, (_, i) => (
            <div className="skel-block" key={i}>
              <div className="skel-head" />
              <div className="skel-title" />
              <div className="skel-title b" />
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export function LoadError({ what }: { what: string }) {
  return (
    <div className="load-error" role="alert">
      <h2>Couldn&rsquo;t load {what}.</h2>
      <p>The connection may have dropped, or the site was updated while this page was open.</p>
      <button type="button" className="cta" onClick={() => window.location.reload()}>
        Reload the page
      </button>
    </div>
  );
}
